"""Deterministic execution-summary analysis operation."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation, ROUND_HALF_EVEN, localcontext

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.analysis import AnalysisContent, AnalysisResult
from ea_research_lab.domain.dataset import Dataset
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    EnvironmentConfigurationId,
)
from ea_research_lab.domain.provenance import (
    AnalysisProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    UtcTimestamp,
)


_DATASET_MANIFEST_REF = SchemaRef(
    SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)
)
_INPUT_REF = SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0))
_PARAMETERS_REF = SchemaRef(
    SchemaName("execution-summary-analysis-parameters"), SchemaVersion(0, 1, 0)
)
_CONTENT_REF = SchemaRef(
    SchemaName("execution-summary-analysis-result"), SchemaVersion(0, 1, 0)
)
_RESULT_REF = SchemaRef(SchemaName("analysis-result"), SchemaVersion(0, 2, 0))
_QUANTUM = Decimal("0.000000000001")


@dataclass(frozen=True, slots=True)
class AnalysisRequest:
    context: RequestContext
    datasets: tuple[Dataset, ...]
    analysis_definition_id: AnalysisDefinitionId
    analysis_version: DefinitionVersion
    analysis_parameters: SchemaReferencedPayload
    computation_environment_id: EnvironmentConfigurationId

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, RequestContext)
            or not isinstance(self.analysis_definition_id, AnalysisDefinitionId)
            or not isinstance(self.analysis_version, DefinitionVersion)
            or not isinstance(self.analysis_parameters, SchemaReferencedPayload)
            or not isinstance(
                self.computation_environment_id, EnvironmentConfigurationId
            )
        ):
            raise InvalidValueError("Analysis request is invalid.")
        try:
            datasets = tuple(self.datasets)
        except TypeError as error:
            raise InvalidValueError(
                "Analysis requires an ordered Dataset collection."
            ) from error
        if not datasets or any(not isinstance(item, Dataset) for item in datasets):
            raise InvalidValueError("Analysis requires at least one valid Dataset.")
        if len({item.provenance.dataset_id for item in datasets}) != len(datasets):
            raise InvalidValueError("Analysis cannot repeat a Dataset identity.")
        if len({item.content.content_digest for item in datasets}) != len(datasets):
            raise InvalidValueError("Analysis cannot repeat Dataset content.")
        for dataset in datasets:
            _validate_dataset(dataset)
        if self.analysis_parameters.schema_ref != _PARAMETERS_REF:
            raise InvalidValueError("Analysis parameters use an unsupported schema.")
        validate_document(_plain_json(self.analysis_parameters.value))
        baseline = self.analysis_parameters.value.get("baseline_content_digest")
        digests = {str(item.content.content_digest) for item in datasets}
        if len(datasets) > 1 and baseline is None:
            raise InvalidValueError("Multi-Dataset analysis requires a baseline.")
        if baseline is not None and baseline not in digests:
            raise InvalidValueError("Analysis baseline is not an input Dataset.")
        object.__setattr__(
            self,
            "datasets",
            tuple(sorted(datasets, key=lambda item: str(item.content.content_digest))),
        )


@dataclass(frozen=True, slots=True)
class AnalysisOutcome:
    result: AnalysisResult | None
    failure: ApplicationError | None

    def __post_init__(self) -> None:
        if (self.result is None) == (self.failure is None):
            raise InvalidValueError("Analysis outcome requires success or failure.")
        if self.result is not None and not isinstance(self.result, AnalysisResult):
            raise InvalidValueError("Analysis outcome result is invalid.")
        if self.failure is not None and not isinstance(
            self.failure, ApplicationError
        ):
            raise InvalidValueError("Analysis outcome failure is invalid.")


def analyze_execution_summaries(request: AnalysisRequest) -> AnalysisOutcome:
    """Compute the one approved deterministic execution-summary analysis."""

    if not isinstance(request, AnalysisRequest):
        raise TypeError("Analysis requires an AnalysisRequest.")
    try:
        content_document = _analyze(request)
        validate_document(content_document)
        content = AnalysisContent(
            SchemaReferencedPayload(_CONTENT_REF, content_document)
        )
        result_id = new_entity_id(AnalysisResultId)
        created_at = _now()
        provenance = AnalysisProvenance(
            result_id,
            request.analysis_definition_id,
            request.analysis_version,
            request.analysis_parameters,
            request.computation_environment_id,
            tuple(item.provenance.dataset_id for item in request.datasets),
        )
        envelope_document = _envelope_document(
            request, provenance, content, created_at
        )
        validate_document(envelope_document)
        return AnalysisOutcome(
            AnalysisResult(
                content,
                provenance,
                request.datasets,
                SchemaReferencedPayload(_RESULT_REF, envelope_document),
                created_at,
            ),
            None,
        )
    except Exception as error:
        return AnalysisOutcome(
            None,
            ApplicationError(
                ApplicationErrorCode.ANALYSIS_FAILED,
                "Analysis failed.",
                request_id=request.context.request_id,
                cause=error,
            ),
        )


def _analyze(request: AnalysisRequest) -> dict[str, object]:
    baseline_digest = request.analysis_parameters.value.get(
        "baseline_content_digest"
    )
    by_digest = {
        str(dataset.content.content_digest): dataset for dataset in request.datasets
    }
    baseline = None if baseline_digest is None else by_digest[baseline_digest]
    if baseline is not None and baseline.content.payload.schema_ref != _INPUT_REF:
        raise InvalidValueError("Analysis baseline schema is unsupported.")

    summaries = {
        digest: _summary(dataset) for digest, dataset in by_digest.items()
    }
    metrics = [
        _metric_document(digest, summaries[digest]) for digest in sorted(summaries)
    ]
    comparisons = []
    if baseline is not None:
        for digest in sorted(set(summaries) - {baseline_digest}):
            comparisons.append(
                _comparison_document(
                    baseline,
                    by_digest[digest],
                    summaries[baseline_digest],
                    summaries[digest],
                )
            )
    return {
        "schema_name": str(_CONTENT_REF.name),
        "schema_version": str(_CONTENT_REF.version),
        "baseline_content_digest": baseline_digest,
        "metrics": metrics,
        "comparisons": comparisons,
    }


def _summary(dataset: Dataset) -> dict[str, object] | None:
    if dataset.content.payload.schema_ref != _INPUT_REF:
        return None
    document = _plain_json(dataset.content.payload.value)
    validate_document(document)
    try:
        return {
            "currency": document["currency"],
            "net_profit": Decimal(document["net_profit"]),
            "net_return": _ratio(
                Decimal(document["net_profit"]),
                Decimal(document["initial_deposit"]),
                "zero_initial_deposit",
            ),
            "win_rate": _ratio(
                Decimal(document["winning_trades"]),
                Decimal(document["total_trades"]),
                "zero_total_trades",
            ),
            "loss_rate": _ratio(
                Decimal(document["losing_trades"]),
                Decimal(document["total_trades"]),
                "zero_total_trades",
            ),
        }
    except (InvalidOperation, KeyError, TypeError) as error:
        raise InvalidValueError("Execution summary numeric content is invalid.") from error


def _metric_document(
    digest: str, summary: dict[str, object] | None
) -> dict[str, object]:
    if summary is None:
        unavailable = {"unavailable_reason": "incompatible_dataset_schema"}
        return {
            "dataset_content_digest": digest,
            "currency": None,
            "net_return": unavailable,
            "win_rate": unavailable,
            "loss_rate": unavailable,
        }
    return {
        "dataset_content_digest": digest,
        "currency": summary["currency"],
        "net_return": summary["net_return"],
        "win_rate": summary["win_rate"],
        "loss_rate": summary["loss_rate"],
    }


def _comparison_document(
    baseline: Dataset,
    candidate: Dataset,
    baseline_summary: dict[str, object],
    candidate_summary: dict[str, object] | None,
) -> dict[str, object]:
    reasons = []
    same_schema = (
        candidate.content.payload.schema_ref == baseline.content.payload.schema_ref
    )
    same_transformation = (
        candidate.provenance.transformation_id
        == baseline.provenance.transformation_id
        and candidate.provenance.transformation_version
        == baseline.provenance.transformation_version
    )
    if not same_schema:
        reasons.append("dataset_schema_mismatch")
    if not same_transformation:
        reasons.append("transformation_mismatch")
    rate_comparable = same_schema and same_transformation
    same_currency = (
        candidate_summary is not None
        and candidate_summary["currency"] == baseline_summary["currency"]
    )
    if rate_comparable and not same_currency:
        reasons.append("currency_mismatch")
    monetary_comparable = rate_comparable and same_currency
    structural_unavailable = {"unavailable_reason": "not_structurally_comparable"}
    deltas = {
        name: (
            _difference(candidate_summary[name], baseline_summary[name])
            if rate_comparable
            else structural_unavailable
        )
        for name in ("net_return", "win_rate", "loss_rate")
    }
    deltas["net_profit"] = (
        _subtract(
            candidate_summary["net_profit"], baseline_summary["net_profit"]
        )
        if monetary_comparable
        else {
            "unavailable_reason": (
                "currency_mismatch"
                if rate_comparable
                else "not_structurally_comparable"
            )
        }
    )
    return {
        "baseline_content_digest": str(baseline.content.content_digest),
        "candidate_content_digest": str(candidate.content.content_digest),
        "comparable": monetary_comparable,
        "rate_comparable": rate_comparable,
        "monetary_comparable": monetary_comparable,
        "reasons": reasons,
        "deltas": deltas,
    }


def _ratio(numerator: Decimal, denominator: Decimal, reason: str) -> dict[str, str]:
    if denominator == 0:
        return {"unavailable_reason": reason}
    with localcontext() as context:
        context.prec = _precision(numerator, denominator)
        return _value(numerator / denominator)


def _difference(
    candidate: dict[str, str], baseline: dict[str, str]
) -> dict[str, str]:
    if "value" not in candidate or "value" not in baseline:
        return {"unavailable_reason": "metric_unavailable"}
    return _subtract(Decimal(candidate["value"]), Decimal(baseline["value"]))


def _subtract(candidate: Decimal, baseline: Decimal) -> dict[str, str]:
    with localcontext() as context:
        context.prec = _precision(candidate, baseline)
        return _value(candidate - baseline)


def _value(value: Decimal) -> dict[str, str]:
    with localcontext() as context:
        context.prec = _precision(value)
        normalized = value.quantize(_QUANTUM, rounding=ROUND_HALF_EVEN)
    if normalized == 0:
        normalized = abs(normalized)
    return {"value": f"{normalized:.12f}"}


def _precision(*values: Decimal) -> int:
    return max(50, *(max(value.adjusted() + 1, 0) + 20 for value in values))


def _validate_dataset(dataset: Dataset) -> None:
    if dataset.manifest.schema_ref != _DATASET_MANIFEST_REF:
        raise InvalidValueError("Analysis requires Dataset Manifest 0.2.0.")
    document = _plain_json(dataset.manifest.value)
    validate_document(document)
    if (
        document["dataset_id"] != str(dataset.provenance.dataset_id)
        or document["dataset_schema"] != str(dataset.content.payload.schema_ref)
        or document["content_digest"] != str(dataset.content.content_digest)
    ):
        raise InvalidValueError("Analysis Dataset identity is inconsistent.")


def _envelope_document(
    request: AnalysisRequest,
    provenance: AnalysisProvenance,
    content: AnalysisContent,
    created_at: UtcTimestamp,
) -> dict[str, object]:
    return {
        "schema_name": str(_RESULT_REF.name),
        "schema_version": str(_RESULT_REF.version),
        "analysis_result_id": str(provenance.analysis_result_id),
        "created_at": str(created_at),
        "provenance": {
            "input_datasets": [
                {
                    "dataset_id": str(dataset.provenance.dataset_id),
                    "content_digest": str(dataset.content.content_digest),
                }
                for dataset in request.datasets
            ],
            "analysis_definition_id": str(provenance.analysis_definition_id),
            "analysis_version": str(provenance.analysis_version),
            "analysis_parameters": {
                "schema_ref": str(provenance.analysis_parameters.schema_ref),
                "value": _plain_json(provenance.analysis_parameters.value),
            },
            "computation_environment_id": str(
                provenance.computation_environment_id
            ),
        },
        "result_schema": str(content.payload.schema_ref),
        "result_digest": str(content.content_digest),
        "result": _plain_json(content.payload.value),
    }


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _now() -> UtcTimestamp:
    return UtcTimestamp(datetime.now(timezone.utc))
