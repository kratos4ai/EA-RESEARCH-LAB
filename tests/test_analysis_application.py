from __future__ import annotations

import hashlib
import unittest
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import timedelta
from decimal import localcontext
from unittest.mock import patch

import ea_research_lab.application.analysis as analysis_application
from ea_research_lab.application.analysis import (
    AnalysisRequest,
    analyze_execution_summaries,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.evidence import RawEvidenceManifestRef
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RequestId,
    RunId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
    DatasetProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)


DATASET_MANIFEST_REF = SchemaRef(
    SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)
)
EXECUTION_SUMMARY_REF = SchemaRef(
    SchemaName("execution-summary"), SchemaVersion(0, 1, 0)
)
PARAMETERS_REF = SchemaRef(
    SchemaName("execution-summary-analysis-parameters"), SchemaVersion(0, 1, 0)
)
CREATED_AT = UtcTimestamp.parse("2026-08-11T12:00:00Z")


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _summary(
    *,
    currency: str = "USD",
    deposit: str = "1000.00",
    profit: str = "100.00",
    total: int = 10,
    winning: int = 6,
    losing: int = 4,
) -> dict[str, object]:
    return {
        "schema_name": "execution-summary",
        "schema_version": "0.1.0",
        "currency": currency,
        "initial_deposit": deposit,
        "net_profit": profit,
        "gross_profit": "100.00",
        "gross_loss": "0.00",
        "total_trades": total,
        "winning_trades": winning,
        "losing_trades": losing,
    }


def _dataset(
    value: dict[str, object],
    *,
    schema_ref: SchemaRef = EXECUTION_SUMMARY_REF,
    transformation_id: TransformationId | None = None,
    dataset_id: DatasetId | None = None,
    created_at: UtcTimestamp = CREATED_AT,
) -> Dataset:
    content = DatasetContent(SchemaReferencedPayload(schema_ref, value))
    provenance = DatasetProvenance(
        dataset_id or new_entity_id(DatasetId),
        transformation_id or new_entity_id(TransformationId),
        DefinitionVersion("execution-summary-1"),
        input_manifests=(
            RawEvidenceManifestRef(
                new_entity_id(RawEvidenceManifestId),
                new_entity_id(RunId),
                Sha256Digest("a" * 64),
            ),
        ),
    )
    manifest = {
        "schema_name": "dataset-manifest",
        "schema_version": "0.2.0",
        "dataset_id": str(provenance.dataset_id),
        "input_manifests": [
            {
                "manifest_id": str(provenance.input_manifests[0].manifest_id),
                "run_id": str(provenance.input_manifests[0].run_id),
                "content_digest": str(
                    provenance.input_manifests[0].content_digest
                ),
            }
        ],
        "input_datasets": [],
        "transformation_id": str(provenance.transformation_id),
        "transformation_version": str(provenance.transformation_version),
        "created_at": str(created_at),
        "dataset_schema": str(schema_ref),
        "content_digest": str(content.content_digest),
    }
    return Dataset(
        content,
        provenance,
        SchemaReferencedPayload(DATASET_MANIFEST_REF, manifest),
        created_at,
    )


def _parameters(baseline: Dataset | None = None) -> SchemaReferencedPayload:
    value: dict[str, object] = {
        "schema_name": "execution-summary-analysis-parameters",
        "schema_version": "0.1.0",
    }
    if baseline is not None:
        value["baseline_content_digest"] = str(baseline.content.content_digest)
    return SchemaReferencedPayload(PARAMETERS_REF, value)


def _request(
    *datasets: Dataset,
    baseline: Dataset | None = None,
) -> AnalysisRequest:
    return AnalysisRequest(
        RequestContext(new_entity_id(RequestId), "analysis-test"),
        datasets,
        new_entity_id(AnalysisDefinitionId),
        DefinitionVersion("execution-summary-analysis-1"),
        _parameters(baseline),
        new_entity_id(EnvironmentConfigurationId),
    )


def _metric(result: object, dataset: Dataset) -> Mapping[str, object]:
    digest = str(dataset.content.content_digest)
    return next(
        item
        for item in result.content.payload.value["metrics"]
        if item["dataset_content_digest"] == digest
    )


def _contains_key(value: object, key: str) -> bool:
    if isinstance(value, Mapping):
        return key in value or any(
            _contains_key(item, key) for item in value.values()
        )
    if isinstance(value, tuple):
        return any(_contains_key(item, key) for item in value)
    return False


def _assert_no_float(test: unittest.TestCase, value: object) -> None:
    test.assertNotIsInstance(value, float)
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_no_float(test, item)
    elif isinstance(value, tuple):
        for item in value:
            _assert_no_float(test, item)


class ExecutionSummaryAnalysisTests(unittest.TestCase):
    def test_metrics_use_deterministic_decimal_formulas(self) -> None:
        dataset = _dataset(
            _summary(total=3, winning=2, losing=1)
        )

        with localcontext() as context:
            context.prec = 3
            outcome = analyze_execution_summaries(_request(dataset))
        metric = _metric(outcome.result, dataset)

        self.assertIsNone(outcome.failure)
        self.assertEqual(metric["net_return"], {"value": "0.100000000000"})
        self.assertEqual(metric["win_rate"], {"value": "0.666666666667"})
        self.assertEqual(metric["loss_rate"], {"value": "0.333333333333"})
        _assert_no_float(self, outcome.result.content.payload.value)

    def test_negative_zero_is_normalized(self) -> None:
        dataset = _dataset(_summary(profit="-0.00"))

        metric = _metric(analyze_execution_summaries(_request(dataset)).result, dataset)

        self.assertEqual(metric["net_return"], {"value": "0.000000000000"})

    def test_zero_denominators_are_explicitly_unavailable(self) -> None:
        dataset = _dataset(
            _summary(deposit="0.00", total=0, winning=0, losing=0)
        )

        metric = _metric(analyze_execution_summaries(_request(dataset)).result, dataset)

        self.assertEqual(
            metric["net_return"],
            {"unavailable_reason": "zero_initial_deposit"},
        )
        self.assertEqual(
            metric["win_rate"],
            {"unavailable_reason": "zero_total_trades"},
        )
        self.assertEqual(metric["loss_rate"], metric["win_rate"])

    def test_result_content_ignores_dataset_entity_and_timestamp(self) -> None:
        transformation_id = new_entity_id(TransformationId)
        first = _dataset(_summary(), transformation_id=transformation_id)
        second = _dataset(
            _summary(),
            transformation_id=transformation_id,
            created_at=UtcTimestamp(CREATED_AT.value + timedelta(seconds=1)),
        )

        first_result = analyze_execution_summaries(_request(first)).result
        second_result = analyze_execution_summaries(_request(second)).result

        self.assertNotEqual(
            first.provenance.dataset_id, second.provenance.dataset_id
        )
        self.assertEqual(
            first_result.content.canonical_bytes,
            second_result.content.canonical_bytes,
        )
        self.assertEqual(
            first_result.content.content_digest,
            second_result.content.content_digest,
        )

    def test_repeated_analysis_preserves_content_not_entity_identity(self) -> None:
        request = _request(_dataset(_summary()))
        timestamps = (
            UtcTimestamp.parse("2026-08-11T12:01:00Z"),
            UtcTimestamp.parse("2026-08-11T12:02:00Z"),
        )

        with patch.object(analysis_application, "_now", side_effect=timestamps):
            first = analyze_execution_summaries(request).result
            second = analyze_execution_summaries(request).result

        self.assertNotEqual(
            first.provenance.analysis_result_id,
            second.provenance.analysis_result_id,
        )
        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.content.canonical_bytes, second.content.canonical_bytes)
        self.assertEqual(first.content.content_digest, second.content.content_digest)

    def test_multi_dataset_analysis_requires_explicit_baseline(self) -> None:
        transformation_id = new_entity_id(TransformationId)
        first = _dataset(_summary(), transformation_id=transformation_id)
        second = _dataset(
            _summary(profit="200.00"), transformation_id=transformation_id
        )

        with self.assertRaises(InvalidValueError):
            _request(first, second)

    def test_baseline_deltas_are_candidate_minus_baseline_without_ranking(self) -> None:
        transformation_id = new_entity_id(TransformationId)
        baseline = _dataset(_summary(), transformation_id=transformation_id)
        candidate = _dataset(
            _summary(profit="200.00", total=20, winning=15, losing=5),
            transformation_id=transformation_id,
        )

        result = analyze_execution_summaries(
            _request(candidate, baseline, baseline=baseline)
        ).result
        comparison = result.content.payload.value["comparisons"][0]

        self.assertEqual(
            comparison["baseline_content_digest"],
            str(baseline.content.content_digest),
        )
        self.assertTrue(comparison["comparable"])
        self.assertEqual(comparison["reasons"], ())
        self.assertEqual(
            comparison["deltas"],
            {
                "net_return": {"value": "0.100000000000"},
                "win_rate": {"value": "0.150000000000"},
                "loss_rate": {"value": "-0.150000000000"},
                "net_profit": {"value": "100.000000000000"},
            },
        )
        self.assertFalse(_contains_key(result.content.payload.value, "rank"))

    def test_currency_mismatch_allows_rates_but_rejects_money_delta(self) -> None:
        transformation_id = new_entity_id(TransformationId)
        baseline = _dataset(_summary(), transformation_id=transformation_id)
        candidate = _dataset(
            _summary(currency="EUR", profit="200.00"),
            transformation_id=transformation_id,
        )

        result = analyze_execution_summaries(
            _request(baseline, candidate, baseline=baseline)
        ).result
        comparison = result.content.payload.value["comparisons"][0]

        self.assertFalse(comparison["comparable"])
        self.assertTrue(comparison["rate_comparable"])
        self.assertFalse(comparison["monetary_comparable"])
        self.assertEqual(comparison["reasons"], ("currency_mismatch",))
        self.assertEqual(
            comparison["deltas"]["net_profit"],
            {"unavailable_reason": "currency_mismatch"},
        )
        self.assertEqual(
            comparison["deltas"]["net_return"],
            {"value": "0.100000000000"},
        )

    def test_incompatible_schema_is_explicitly_not_comparable(self) -> None:
        transformation_id = new_entity_id(TransformationId)
        baseline = _dataset(_summary(), transformation_id=transformation_id)
        incompatible = _dataset(
            {"schema_name": "other-summary", "schema_version": "0.1.0"},
            schema_ref=SchemaRef(
                SchemaName("other-summary"), SchemaVersion(0, 1, 0)
            ),
            transformation_id=transformation_id,
        )

        result = analyze_execution_summaries(
            _request(baseline, incompatible, baseline=baseline)
        ).result
        comparison = result.content.payload.value["comparisons"][0]

        self.assertFalse(comparison["comparable"])
        self.assertFalse(comparison["rate_comparable"])
        self.assertEqual(comparison["reasons"], ("dataset_schema_mismatch",))
        self.assertEqual(
            _metric(result, incompatible)["net_return"],
            {"unavailable_reason": "incompatible_dataset_schema"},
        )

    def test_incompatible_transformation_is_not_comparable(self) -> None:
        baseline = _dataset(_summary())
        candidate = _dataset(_summary(profit="200.00"))

        result = analyze_execution_summaries(
            _request(baseline, candidate, baseline=baseline)
        ).result
        comparison = result.content.payload.value["comparisons"][0]

        self.assertFalse(comparison["comparable"])
        self.assertFalse(comparison["rate_comparable"])
        self.assertEqual(comparison["reasons"], ("transformation_mismatch",))
        self.assertEqual(
            comparison["deltas"]["net_return"],
            {"unavailable_reason": "not_structurally_comparable"},
        )

    def test_result_contract_and_provenance_bind_exact_content(self) -> None:
        dataset = _dataset(_summary())

        result = analyze_execution_summaries(_request(dataset)).result
        envelope = _plain(result.envelope.value)

        validate_document(_plain(result.content.payload.value))
        validate_document(envelope)
        self.assertEqual(envelope["schema_version"], "0.2.0")
        self.assertEqual(
            envelope["result_digest"],
            hashlib.sha256(result.content.canonical_bytes).hexdigest(),
        )
        self.assertEqual(
            envelope["provenance"]["input_datasets"],
            [
                {
                    "dataset_id": str(dataset.provenance.dataset_id),
                    "content_digest": str(dataset.content.content_digest),
                }
            ],
        )
        self.assertEqual(result.input_datasets, (dataset,))
        self.assertEqual(
            result.input_datasets[0].provenance.input_manifests,
            dataset.provenance.input_manifests,
        )
        self.assertEqual(
            envelope["provenance"]["analysis_definition_id"],
            str(result.provenance.analysis_definition_id),
        )
        self.assertEqual(
            envelope["provenance"]["analysis_version"],
            str(result.provenance.analysis_version),
        )
        self.assertEqual(
            envelope["provenance"]["analysis_parameters"]["schema_ref"],
            str(result.provenance.analysis_parameters.schema_ref),
        )
        self.assertEqual(
            envelope["provenance"]["computation_environment_id"],
            str(result.provenance.computation_environment_id),
        )

    def test_result_is_immutable_and_failure_is_safe(self) -> None:
        dataset = _dataset(_summary())
        result = analyze_execution_summaries(_request(dataset)).result

        with self.assertRaises(FrozenInstanceError):
            result.content.canonical_bytes = b"changed"
        with self.assertRaises(TypeError):
            result.content.payload.value["metrics"] = ()

        invalid = _dataset({**_summary(), "initial_deposit": "invalid"})
        failure = analyze_execution_summaries(_request(invalid))
        self.assertIsNone(failure.result)
        self.assertEqual(failure.failure.code.value, "analysis_failed")
        self.assertNotIn("invalid", str(failure.failure.to_dict()))


if __name__ == "__main__":
    unittest.main()
