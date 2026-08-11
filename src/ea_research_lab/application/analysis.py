"""Deterministic execution-summary analysis operation."""

from __future__ import annotations

import hashlib
import json
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
_CORE_PARAMETERS_REF = SchemaRef(
    SchemaName("execution-core-analysis-parameters"), SchemaVersion(0, 1, 0)
)
_CORE_CONTENT_REF = SchemaRef(
    SchemaName("execution-core-analysis-result"), SchemaVersion(0, 1, 0)
)
_REALIZED_EVENTS_REF = SchemaRef(
    SchemaName("realized-execution-event-series"), SchemaVersion(0, 1, 0)
)
_BALANCE_EVENTS_REF = SchemaRef(
    SchemaName("account-balance-event-series"), SchemaVersion(0, 1, 0)
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
        if self.analysis_parameters.schema_ref not in {
            _PARAMETERS_REF,
            _CORE_PARAMETERS_REF,
        }:
            raise InvalidValueError("Analysis parameters use an unsupported schema.")
        validate_document(_plain_json(self.analysis_parameters.value))
        if self.analysis_parameters.schema_ref == _PARAMETERS_REF:
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
        return AnalysisOutcome(
            _create_result(request, _CONTENT_REF, content_document), None
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


def analyze_execution_core(request: AnalysisRequest) -> AnalysisOutcome:
    """Compute the direct deterministic Analysis Core result."""

    if not isinstance(request, AnalysisRequest):
        raise TypeError("Analysis requires an AnalysisRequest.")
    try:
        content_document = _analyze_execution_core(request)
        return AnalysisOutcome(
            _create_result(request, _CORE_CONTENT_REF, content_document), None
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
    if request.analysis_parameters.schema_ref != _PARAMETERS_REF:
        raise InvalidValueError("Execution-summary analysis parameters are invalid.")
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


def _analyze_execution_core(request: AnalysisRequest) -> dict[str, object]:
    if request.analysis_parameters.schema_ref != _CORE_PARAMETERS_REF:
        raise InvalidValueError("Execution Core analysis parameters are invalid.")
    datasets = {dataset.content.payload.schema_ref: dataset for dataset in request.datasets}
    expected = {_INPUT_REF, _REALIZED_EVENTS_REF, _BALANCE_EVENTS_REF}
    if len(request.datasets) != 3 or set(datasets) != expected:
        raise InvalidValueError("Execution Core requires its three exact Datasets.")

    documents = {
        schema_ref: _plain_json(dataset.content.payload.value)
        for schema_ref, dataset in datasets.items()
    }
    for document in documents.values():
        validate_document(document)

    currencies = {document["currency"] for document in documents.values()}
    if len(currencies) != 1:
        raise InvalidValueError("Execution Core Dataset currencies are inconsistent.")
    manifests = {
        dataset.provenance.input_manifests for dataset in datasets.values()
    }
    if len(manifests) != 1 or not next(iter(manifests)):
        raise InvalidValueError(
            "Execution Core Dataset evidence provenance is inconsistent."
        )

    summary = documents[_INPUT_REF]
    realized = documents[_REALIZED_EVENTS_REF]
    balances = documents[_BALANCE_EVENTS_REF]
    outcomes = _realized_outcomes(realized)
    balance_values = _event_balances(balances)
    return {
        "schema_name": str(_CORE_CONTENT_REF.name),
        "schema_version": str(_CORE_CONTENT_REF.version),
        "currency": next(iter(currencies)),
        "input_content_digests": {
            "execution_summary": str(datasets[_INPUT_REF].content.content_digest),
            "realized_execution_event_series": str(
                datasets[_REALIZED_EVENTS_REF].content.content_digest
            ),
            "account_balance_event_series": str(
                datasets[_BALANCE_EVENTS_REF].content.content_digest
            ),
        },
        "aggregate_metrics": _aggregate_metrics(summary),
        "realized_execution_distribution": _distribution(outcomes),
        "realized_execution_sequence": _sequence(outcomes),
        "event_balance_analysis": _balance_analysis(balance_values),
        "integrity": {
            "input_currency_consistent": True,
            "input_evidence_manifest_consistent": True,
        },
    }


def _aggregate_metrics(summary: Mapping[str, object]) -> dict[str, object]:
    net_profit = _decimal(summary["net_profit"])
    gross_profit = _decimal(summary["gross_profit"])
    gross_loss = abs(_decimal(summary["gross_loss"]))
    initial_deposit = _decimal(summary["initial_deposit"])
    total_trades = Decimal(summary["total_trades"])
    winning_trades = Decimal(summary["winning_trades"])
    losing_trades = Decimal(summary["losing_trades"])
    average_winning = _divide(gross_profit, winning_trades)
    average_losing = _divide(gross_loss, losing_trades)

    if average_winning is None:
        payoff_ratio = _unavailable("zero_winning_trades")
    elif average_losing is None:
        payoff_ratio = _unavailable("zero_losing_trades")
    elif average_losing == 0:
        payoff_ratio = _unavailable("zero_average_losing_magnitude")
    else:
        payoff_ratio = _value(_divide(average_winning, average_losing))

    return {
        "net_return": _ratio(
            net_profit, initial_deposit, "zero_initial_deposit"
        ),
        "win_rate": _ratio(
            winning_trades, total_trades, "zero_total_trades"
        ),
        "loss_rate": _ratio(
            losing_trades, total_trades, "zero_total_trades"
        ),
        "expected_payoff": _ratio(
            net_profit, total_trades, "zero_total_trades"
        ),
        "profit_factor": _ratio(
            gross_profit, gross_loss, "zero_gross_loss"
        ),
        "average_winning_result": (
            _value(average_winning)
            if average_winning is not None
            else _unavailable("zero_winning_trades")
        ),
        "average_losing_magnitude": (
            _value(average_losing)
            if average_losing is not None
            else _unavailable("zero_losing_trades")
        ),
        "payoff_ratio": payoff_ratio,
        "gross_profit_return": _ratio(
            gross_profit, initial_deposit, "zero_initial_deposit"
        ),
        "gross_loss_return": _ratio(
            gross_loss, initial_deposit, "zero_initial_deposit"
        ),
    }


def _realized_outcomes(document: Mapping[str, object]) -> tuple[Decimal, ...]:
    events = document["events"]
    if [event["sequence"] for event in events] != list(range(len(events))):
        raise InvalidValueError("Realized execution-event order is invalid.")
    identifiers = tuple(event["source_record_id"] for event in events)
    if len(set(identifiers)) != len(identifiers):
        raise InvalidValueError("Realized execution-event identity is ambiguous.")
    outcomes = tuple(_decimal(event["realized_pnl"]) for event in events)
    if not outcomes:
        raise InvalidValueError("Realized execution-event series is empty.")
    return outcomes


def _event_balances(document: Mapping[str, object]) -> tuple[Decimal, ...]:
    observations = document["observations"]
    if [item["sequence"] for item in observations] != list(
        range(len(observations))
    ):
        raise InvalidValueError("Account balance-event order is invalid.")
    identifiers = tuple(item["source_record_id"] for item in observations)
    if len(set(identifiers)) != len(identifiers):
        raise InvalidValueError("Account balance-event identity is ambiguous.")
    balances = tuple(_decimal(item["balance"]) for item in observations)
    if not balances:
        raise InvalidValueError("Account balance-event series is empty.")
    return balances


def _distribution(values: tuple[Decimal, ...]) -> dict[str, object]:
    with localcontext() as context:
        context.prec = _precision(*values)
        count = Decimal(len(values))
        mean = sum(values, Decimal(0)) / count
        ordered = sorted(values)
        middle = len(ordered) // 2
        median = (
            ordered[middle]
            if len(ordered) % 2
            else (ordered[middle - 1] + ordered[middle]) / Decimal(2)
        )
        mean_absolute_deviation = (
            sum((abs(value - mean) for value in values), Decimal(0)) / count
        )
    return {
        "count": len(values),
        "minimum": _value(min(values)),
        "maximum": _value(max(values)),
        "arithmetic_mean": _value(mean),
        "median": _value(median),
        "mean_absolute_deviation": _value(mean_absolute_deviation),
    }


def _sequence(values: tuple[Decimal, ...]) -> dict[str, int]:
    positive = negative = longest_positive = longest_negative = zeros = 0
    for value in values:
        if value > 0:
            positive += 1
            negative = 0
            longest_positive = max(longest_positive, positive)
        elif value < 0:
            negative += 1
            positive = 0
            longest_negative = max(longest_negative, negative)
        else:
            positive = negative = 0
            zeros += 1
    return {
        "longest_positive_streak": longest_positive,
        "longest_negative_streak": longest_negative,
        "zero_result_count": zeros,
    }


def _balance_analysis(balances: tuple[Decimal, ...]) -> dict[str, object]:
    running_peak = balances[0]
    maximum_amount = Decimal(0)
    rates: list[Decimal] = []
    for balance in balances:
        running_peak = max(running_peak, balance)
        amount = running_peak - balance
        maximum_amount = max(maximum_amount, amount)
        if running_peak != 0:
            rates.append(_divide(amount, running_peak))
    return {
        "event_balance_max_drawdown": {
            "amount": _value(maximum_amount),
            "rate": (
                _value(max(rates))
                if rates
                else _unavailable("zero_running_peak")
            ),
        }
    }


def _decimal(value: object) -> Decimal:
    if not isinstance(value, str):
        raise InvalidValueError("Analysis requires decimal strings.")
    try:
        parsed = Decimal(value)
    except InvalidOperation as error:
        raise InvalidValueError("Analysis decimal input is invalid.") from error
    if not parsed.is_finite():
        raise InvalidValueError("Analysis decimal input must be finite.")
    return parsed


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
    quotient = _divide(numerator, denominator)
    return _unavailable(reason) if quotient is None else _value(quotient)


def _divide(numerator: Decimal, denominator: Decimal) -> Decimal | None:
    if denominator == 0:
        return None
    with localcontext() as context:
        context.prec = _precision(numerator, denominator)
        return numerator / denominator


def _unavailable(reason: str) -> dict[str, str]:
    return {"unavailable_reason": reason}


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
    canonical_bytes = json.dumps(
        _plain_json(dataset.content.payload.value),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")
    content_digest = hashlib.sha256(canonical_bytes).hexdigest()
    if (
        document["dataset_id"] != str(dataset.provenance.dataset_id)
        or document["dataset_schema"] != str(dataset.content.payload.schema_ref)
        or document["content_digest"] != str(dataset.content.content_digest)
        or canonical_bytes != dataset.content.canonical_bytes
        or content_digest != str(dataset.content.content_digest)
    ):
        raise InvalidValueError("Analysis Dataset identity is inconsistent.")


def _create_result(
    request: AnalysisRequest,
    content_ref: SchemaRef,
    content_document: dict[str, object],
) -> AnalysisResult:
    validate_document(content_document)
    content = AnalysisContent(
        SchemaReferencedPayload(content_ref, content_document)
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
    envelope_document = _envelope_document(request, provenance, content, created_at)
    validate_document(envelope_document)
    return AnalysisResult(
        content,
        provenance,
        request.datasets,
        SchemaReferencedPayload(_RESULT_REF, envelope_document),
        created_at,
    )


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
