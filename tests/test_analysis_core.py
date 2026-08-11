from __future__ import annotations

import json
import unittest
from collections.abc import Mapping
from datetime import timedelta
from decimal import ROUND_DOWN, localcontext
from pathlib import Path
from unittest.mock import patch

import ea_research_lab.application.analysis as analysis_application
from ea_research_lab.application.analysis import (
    AnalysisRequest,
    analyze_execution_core,
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


FIXTURES = Path(__file__).parent / "fixtures" / "schemas" / "valid"
DATASET_MANIFEST_REF = SchemaRef(
    SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)
)
SUMMARY_REF = SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0))
REALIZED_REF = SchemaRef(
    SchemaName("realized-execution-event-series"), SchemaVersion(0, 1, 0)
)
BALANCE_REF = SchemaRef(
    SchemaName("account-balance-event-series"), SchemaVersion(0, 1, 0)
)
PARAMETERS_REF = SchemaRef(
    SchemaName("execution-core-analysis-parameters"), SchemaVersion(0, 1, 0)
)
CREATED_AT = UtcTimestamp.parse("2026-08-11T12:00:00Z")


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _manifest_ref(digest: str = "a") -> RawEvidenceManifestRef:
    return RawEvidenceManifestRef(
        new_entity_id(RawEvidenceManifestId),
        new_entity_id(RunId),
        Sha256Digest(digest * 64),
    )


def _dataset(
    schema_ref: SchemaRef,
    value: dict[str, object],
    manifest_ref: RawEvidenceManifestRef,
    *,
    created_at: UtcTimestamp = CREATED_AT,
) -> Dataset:
    content = DatasetContent(SchemaReferencedPayload(schema_ref, value))
    provenance = DatasetProvenance(
        new_entity_id(DatasetId),
        new_entity_id(TransformationId),
        DefinitionVersion(f"{schema_ref.name}-1"),
        input_manifests=(manifest_ref,),
    )
    manifest = {
        "schema_name": "dataset-manifest",
        "schema_version": "0.2.0",
        "dataset_id": str(provenance.dataset_id),
        "input_manifests": [
            {
                "manifest_id": str(manifest_ref.manifest_id),
                "run_id": str(manifest_ref.run_id),
                "content_digest": str(manifest_ref.content_digest),
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


def _summary(**overrides: object) -> dict[str, object]:
    value = {
        "schema_name": "execution-summary",
        "schema_version": "0.1.0",
        "currency": "USD",
        "initial_deposit": "10000.00",
        "net_profit": "0.38",
        "gross_profit": "0.42",
        "gross_loss": "-0.04",
        "total_trades": 2,
        "winning_trades": 1,
        "losing_trades": 1,
    }
    value.update(overrides)
    return value


def _realized(*values: str, currency: str = "USD") -> dict[str, object]:
    return {
        "schema_name": "realized-execution-event-series",
        "schema_version": "0.1.0",
        "currency": currency,
        "time_basis": "source_local_time_without_offset",
        "events": [
            {
                "sequence": index,
                "source_record_id": f"event-{index}",
                "local_time": f"2026-08-03T00:00:{index:02d}",
                "instrument": "EURUSD",
                "side": "buy" if index % 2 else "sell",
                "volume": "0.01",
                "price": "1.00000",
                "realized_pnl": value,
                "commission": "0.00",
                "swap": "0.00",
            }
            for index, value in enumerate(values)
        ],
    }


def _balances(*values: str, currency: str = "USD") -> dict[str, object]:
    return {
        "schema_name": "account-balance-event-series",
        "schema_version": "0.1.0",
        "currency": currency,
        "time_basis": "source_local_time_without_offset",
        "observations": [
            {
                "sequence": index,
                "source_record_id": f"balance-{index}",
                "local_time": f"2026-08-03T00:00:{index:02d}",
                "balance": value,
            }
            for index, value in enumerate(values)
        ],
    }


def _datasets(
    *,
    summary: dict[str, object] | None = None,
    realized: dict[str, object] | None = None,
    balances: dict[str, object] | None = None,
    manifest_ref: RawEvidenceManifestRef | None = None,
) -> tuple[Dataset, Dataset, Dataset]:
    evidence = manifest_ref or _manifest_ref()
    return (
        _dataset(SUMMARY_REF, summary or _summary(), evidence),
        _dataset(REALIZED_REF, realized or _realized("-0.04", "0.42"), evidence),
        _dataset(
            BALANCE_REF,
            balances
            or _balances(
                "10000.00", "10000.00", "9999.96", "9999.96", "10000.38"
            ),
            evidence,
        ),
    )


def _request(
    datasets: tuple[Dataset, ...],
    *,
    definition_id: AnalysisDefinitionId | None = None,
    environment_id: EnvironmentConfigurationId | None = None,
) -> AnalysisRequest:
    return AnalysisRequest(
        RequestContext(new_entity_id(RequestId), "analysis-core-test"),
        datasets,
        definition_id or new_entity_id(AnalysisDefinitionId),
        DefinitionVersion("execution-core-analysis-1"),
        SchemaReferencedPayload(
            PARAMETERS_REF,
            {
                "schema_name": "execution-core-analysis-parameters",
                "schema_version": "0.1.0",
            },
        ),
        environment_id or new_entity_id(EnvironmentConfigurationId),
    )


def _assert_no_float(test: unittest.TestCase, value: object) -> None:
    test.assertNotIsInstance(value, float)
    if isinstance(value, Mapping):
        for item in value.values():
            _assert_no_float(test, item)
    elif isinstance(value, tuple):
        for item in value:
            _assert_no_float(test, item)


class ExecutionCoreAnalysisTests(unittest.TestCase):
    def test_known_inputs_produce_exact_core_result_and_provenance(self) -> None:
        datasets = _datasets()

        outcome = analyze_execution_core(_request(datasets))
        result = outcome.result
        expected = json.loads(
            (FIXTURES / "execution-core-analysis-result.json").read_text(
                encoding="utf-8"
            )
        )
        expected["input_content_digests"] = {
            "execution_summary": str(datasets[0].content.content_digest),
            "realized_execution_event_series": str(
                datasets[1].content.content_digest
            ),
            "account_balance_event_series": str(
                datasets[2].content.content_digest
            ),
        }

        self.assertIsNone(outcome.failure)
        self.assertEqual(_plain(result.content.payload.value), expected)
        _assert_no_float(self, result.content.payload.value)
        validate_document(_plain(result.content.payload.value))
        validate_document(_plain(result.envelope.value))
        self.assertEqual(
            result.envelope.value["result_digest"],
            str(result.content.content_digest),
        )
        self.assertEqual(
            {
                item["content_digest"]
                for item in result.envelope.value["provenance"]["input_datasets"]
            },
            {str(dataset.content.content_digest) for dataset in datasets},
        )

    def test_every_aggregate_zero_denominator_is_explicit(self) -> None:
        zero = analyze_execution_core(
            _request(
                _datasets(
                    summary=_summary(
                        initial_deposit="0.00",
                        net_profit="0.00",
                        gross_profit="0.00",
                        gross_loss="0.00",
                        total_trades=0,
                        winning_trades=0,
                        losing_trades=0,
                    )
                )
            )
        ).result.content.payload.value["aggregate_metrics"]
        self.assertEqual(zero["net_return"], {"unavailable_reason": "zero_initial_deposit"})
        self.assertEqual(zero["win_rate"], {"unavailable_reason": "zero_total_trades"})
        self.assertEqual(zero["loss_rate"], {"unavailable_reason": "zero_total_trades"})
        self.assertEqual(zero["expected_payoff"], {"unavailable_reason": "zero_total_trades"})
        self.assertEqual(zero["profit_factor"], {"unavailable_reason": "zero_gross_loss"})
        self.assertEqual(zero["average_winning_result"], {"unavailable_reason": "zero_winning_trades"})
        self.assertEqual(zero["average_losing_magnitude"], {"unavailable_reason": "zero_losing_trades"})
        self.assertEqual(zero["payoff_ratio"], {"unavailable_reason": "zero_winning_trades"})
        self.assertEqual(zero["gross_profit_return"], {"unavailable_reason": "zero_initial_deposit"})
        self.assertEqual(zero["gross_loss_return"], {"unavailable_reason": "zero_initial_deposit"})

        no_losses = analyze_execution_core(
            _request(
                _datasets(
                    summary=_summary(
                        gross_loss="0.00", total_trades=1, losing_trades=0
                    )
                )
            )
        ).result.content.payload.value["aggregate_metrics"]
        self.assertEqual(no_losses["payoff_ratio"], {"unavailable_reason": "zero_losing_trades"})

        zero_average_loss = analyze_execution_core(
            _request(_datasets(summary=_summary(gross_loss="0.00")))
        ).result.content.payload.value["aggregate_metrics"]
        self.assertEqual(
            zero_average_loss["payoff_ratio"],
            {"unavailable_reason": "zero_average_losing_magnitude"},
        )

    def test_distribution_sequence_and_negative_zero_are_deterministic(self) -> None:
        datasets = _datasets(
            realized=_realized("1.00", "2.00", "0.00", "-1.00", "-2.00", "-3.00", "-0.00", "4.00")
        )

        result = analyze_execution_core(_request(datasets)).result.content.payload.value
        distribution = result["realized_execution_distribution"]
        sequence = result["realized_execution_sequence"]

        self.assertEqual(distribution["count"], 8)
        self.assertEqual(distribution["minimum"], {"value": "-3.000000000000"})
        self.assertEqual(distribution["maximum"], {"value": "4.000000000000"})
        self.assertEqual(distribution["arithmetic_mean"], {"value": "0.125000000000"})
        self.assertEqual(distribution["median"], {"value": "0.000000000000"})
        self.assertEqual(
            distribution["mean_absolute_deviation"],
            {"value": "1.656250000000"},
        )
        self.assertEqual(
            sequence,
            {
                "longest_positive_streak": 2,
                "longest_negative_streak": 3,
                "zero_result_count": 2,
            },
        )

    def test_event_balance_drawdown_uses_running_peak_only(self) -> None:
        result = analyze_execution_core(
            _request(
                _datasets(balances=_balances("100.00", "120.00", "90.00", "110.00"))
            )
        ).result.content.payload.value["event_balance_analysis"]

        self.assertEqual(
            result["event_balance_max_drawdown"],
            {
                "amount": {"value": "30.000000000000"},
                "rate": {"value": "0.250000000000"},
            },
        )
        self.assertNotIn("equity", result)

        zero_peak = analyze_execution_core(
            _request(_datasets(balances=_balances("0.00", "0.00")))
        ).result.content.payload.value["event_balance_analysis"]
        self.assertEqual(
            zero_peak["event_balance_max_drawdown"]["rate"],
            {"unavailable_reason": "zero_running_peak"},
        )

    def test_content_is_independent_from_dataset_entities_and_timestamps(self) -> None:
        evidence = _manifest_ref()
        first_datasets = _datasets(manifest_ref=evidence)
        second_datasets = tuple(
            _dataset(
                dataset.content.payload.schema_ref,
                _plain(dataset.content.payload.value),
                evidence,
                created_at=UtcTimestamp(CREATED_AT.value + timedelta(seconds=1)),
            )
            for dataset in first_datasets
        )
        definition_id = new_entity_id(AnalysisDefinitionId)
        environment_id = new_entity_id(EnvironmentConfigurationId)
        timestamps = (
            UtcTimestamp.parse("2026-08-11T12:01:00Z"),
            UtcTimestamp.parse("2026-08-11T12:02:00Z"),
        )

        with patch.object(analysis_application, "_now", side_effect=timestamps):
            first = analyze_execution_core(
                _request(
                    first_datasets,
                    definition_id=definition_id,
                    environment_id=environment_id,
                )
            ).result
            second = analyze_execution_core(
                _request(
                    second_datasets,
                    definition_id=definition_id,
                    environment_id=environment_id,
                )
            ).result

        self.assertNotEqual(
            tuple(item.provenance.dataset_id for item in first_datasets),
            tuple(item.provenance.dataset_id for item in second_datasets),
        )
        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.content.canonical_bytes, second.content.canonical_bytes)
        self.assertEqual(first.content.content_digest, second.content.content_digest)

    def test_content_is_independent_from_process_decimal_context(self) -> None:
        datasets = _datasets(realized=_realized("1.00", "2.00", "-1.00"))
        expected = analyze_execution_core(_request(datasets)).result.content

        with localcontext() as context:
            context.prec = 3
            context.rounding = ROUND_DOWN
            actual = analyze_execution_core(_request(datasets)).result.content

        self.assertEqual(actual.canonical_bytes, expected.canonical_bytes)
        self.assertEqual(actual.content_digest, expected.content_digest)

    def test_invalid_digest_schema_empty_series_and_integrity_fail_closed(self) -> None:
        tampered = _datasets()
        object.__setattr__(tampered[0].content, "canonical_bytes", b"tampered")
        with self.assertRaises(InvalidValueError):
            _request(tampered)

        valid = _datasets()
        wrong_schema = _dataset(
            SchemaRef(SchemaName("other-dataset"), SchemaVersion(0, 1, 0)),
            {"schema_name": "other-dataset", "schema_version": "0.1.0"},
            valid[0].provenance.input_manifests[0],
        )
        wrong = analyze_execution_core(_request((valid[0], valid[1], wrong_schema)))
        self.assertIsNone(wrong.result)
        self.assertIsNotNone(wrong.failure)

        empty = _datasets(realized=_realized())
        empty_outcome = analyze_execution_core(_request(empty))
        self.assertIsNone(empty_outcome.result)
        self.assertIsNotNone(empty_outcome.failure)

        currency = _datasets(realized=_realized("1.00", currency="EUR"))
        currency_outcome = analyze_execution_core(_request(currency))
        self.assertIsNone(currency_outcome.result)
        self.assertIsNotNone(currency_outcome.failure)

        inconsistent = list(_datasets())
        inconsistent[2] = _dataset(
            BALANCE_REF,
            _balances("10000.00"),
            _manifest_ref("b"),
        )
        provenance = analyze_execution_core(_request(tuple(inconsistent)))
        self.assertIsNone(provenance.result)
        self.assertIsNotNone(provenance.failure)


if __name__ == "__main__":
    unittest.main()
