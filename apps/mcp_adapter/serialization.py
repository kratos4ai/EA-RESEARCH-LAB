"""Explicit MCP-safe serialization for allow-listed Platform API values."""

from collections.abc import Mapping
from datetime import date
from decimal import Decimal
from enum import StrEnum

from ea_research_lab.application.research_query import Page
from ea_research_lab.application.platform_commands import (
    AnalysisCommandResult,
    BuildCommandResult,
    RunCommandResult,
    TransformEvidenceCommandResult,
)
from ea_research_lab.domain.evidence import RawEvidenceManifestRef
from ea_research_lab.domain.identifiers import EntityId, RequestId
from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    AnalysisSummary,
    CanonicalChainProjection,
    DatasetContentReference,
    DatasetDetail,
    DatasetSummary,
    EvidenceObjectSummary,
    ExecutionSummaryProjection,
    ExperimentContextProjection,
    ProvenanceSummary,
    ProviderRuntimeProjection,
    ResearchRunDetail,
    ResearchRunSummary,
)
from ea_research_lab.domain.values import SchemaRef, Sha256Digest, UtcTimestamp


def serialize_decimal(value: Decimal) -> str:
    if not isinstance(value, Decimal) or not value.is_finite():
        raise TypeError("MCP Decimal serialization requires a finite Decimal.")
    return str(value)


def serialize_timestamp(value: UtcTimestamp) -> str:
    if not isinstance(value, UtcTimestamp):
        raise TypeError("MCP timestamp serialization requires a UtcTimestamp.")
    return str(value)


def serialize_date(value: date) -> str:
    if not isinstance(value, date):
        raise TypeError("MCP date serialization requires a date.")
    return value.isoformat()


def serialize_entity_id(value: EntityId) -> str:
    if not isinstance(value, EntityId):
        raise TypeError("MCP identifier serialization requires an EntityId.")
    return str(value)


def serialize_digest(value: Sha256Digest) -> str:
    if not isinstance(value, Sha256Digest):
        raise TypeError("MCP digest serialization requires a Sha256Digest.")
    return str(value)


def serialize_enum(value: StrEnum) -> str:
    if not isinstance(value, StrEnum):
        raise TypeError("MCP enum serialization requires a StrEnum.")
    return value.value


def serialize_schema_ref(value: SchemaRef) -> str:
    if not isinstance(value, SchemaRef):
        raise TypeError("MCP schema serialization requires a SchemaRef.")
    return str(value)


def serialize_evidence_manifest_ref(
    value: RawEvidenceManifestRef,
) -> dict[str, str]:
    if not isinstance(value, RawEvidenceManifestRef):
        raise TypeError("MCP evidence serialization requires a manifest reference.")
    return {
        "manifest_id": serialize_entity_id(value.manifest_id),
        "run_id": serialize_entity_id(value.run_id),
        "content_digest": serialize_digest(value.content_digest),
    }


def serialize_research_run_summary(value: ResearchRunSummary) -> dict[str, object]:
    if not isinstance(value, ResearchRunSummary):
        raise TypeError("MCP Run serialization requires a ResearchRunSummary.")
    return {
        "run_id": serialize_entity_id(value.run_id),
        "artifact_id": serialize_entity_id(value.artifact_id),
        "test_definition_revision_id": serialize_entity_id(
            value.test_definition_revision_id
        ),
        "status": value.status,
        "created_at": serialize_timestamp(value.created_at),
        "started_at": (
            None if value.started_at is None else serialize_timestamp(value.started_at)
        ),
        "finished_at": (
            None
            if value.finished_at is None
            else serialize_timestamp(value.finished_at)
        ),
        "manifest_schema": serialize_schema_ref(value.manifest_schema),
        "evidence_manifest": (
            None
            if value.evidence_manifest is None
            else serialize_evidence_manifest_ref(value.evidence_manifest)
        ),
        "evidence_outcome": (
            None
            if value.evidence_outcome is None
            else serialize_enum(value.evidence_outcome)
        ),
    }


def serialize_research_run_page(
    value: Page[ResearchRunSummary],
) -> dict[str, object]:
    if not isinstance(value, Page) or any(
        not isinstance(item, ResearchRunSummary) for item in value.items
    ):
        raise TypeError("MCP Run page serialization requires Run summaries.")
    return {
        "items": [serialize_research_run_summary(item) for item in value.items],
        "next_cursor": value.next_cursor,
    }


def serialize_experiment_context(
    value: ExperimentContextProjection,
) -> dict[str, str]:
    if not isinstance(value, ExperimentContextProjection):
        raise TypeError("MCP experiment serialization requires its projection.")
    return {
        "instrument": value.instrument,
        "timeframe": value.timeframe,
        "start_date": serialize_date(value.start_date),
        "end_date": serialize_date(value.end_date),
        "requested_initial_capital": serialize_decimal(
            value.requested_initial_capital
        ),
        "currency": value.currency,
        "leverage": value.leverage,
    }


def serialize_provider_runtime(value: ProviderRuntimeProjection) -> dict[str, object]:
    if not isinstance(value, ProviderRuntimeProjection):
        raise TypeError("MCP runtime serialization requires its projection.")
    return {
        "role": value.role,
        "provider_namespace": value.provider_namespace,
        "version": value.version,
        "executable_digest": (
            None
            if value.executable_digest is None
            else serialize_digest(value.executable_digest)
        ),
    }


def serialize_research_run_detail(value: ResearchRunDetail) -> dict[str, object]:
    if not isinstance(value, ResearchRunDetail):
        raise TypeError("MCP Run detail serialization requires its projection.")
    return {
        "summary": serialize_research_run_summary(value.summary),
        "build_record_id": serialize_entity_id(value.build_record_id),
        "test_definition_id": serialize_entity_id(value.test_definition_id),
        "environment_configuration_id": serialize_entity_id(
            value.environment_configuration_id
        ),
        "execution_reproducibility": {
            "level": serialize_enum(value.execution_reproducibility.level),
            "reasons": [
                {"code": reason.code, "detail": reason.detail}
                for reason in value.execution_reproducibility.reasons
            ],
        },
        "evidence_history": [
            serialize_evidence_manifest_ref(item) for item in value.evidence_history
        ],
        "experiment_context": (
            None
            if value.experiment_context is None
            else serialize_experiment_context(value.experiment_context)
        ),
        "provider_runtimes": [
            serialize_provider_runtime(item) for item in value.provider_runtimes
        ],
    }


def serialize_evidence_object_summary(
    value: EvidenceObjectSummary,
) -> dict[str, object]:
    if not isinstance(value, EvidenceObjectSummary):
        raise TypeError("MCP Evidence serialization requires its summary.")
    return {
        "manifest_id": serialize_entity_id(value.manifest_id),
        "object_id": serialize_entity_id(value.object_id),
        "media_type": value.media_type,
        "byte_length": value.byte_length,
        "content_digest": serialize_digest(value.content_digest),
        "payload_schema": (
            None
            if value.payload_schema is None
            else serialize_schema_ref(value.payload_schema)
        ),
        "provider_namespace": value.provider_namespace,
    }


def serialize_evidence_object_page(
    value: Page[EvidenceObjectSummary],
) -> dict[str, object]:
    if not isinstance(value, Page) or any(
        not isinstance(item, EvidenceObjectSummary) for item in value.items
    ):
        raise TypeError("MCP Evidence page serialization requires summaries.")
    return {
        "items": [serialize_evidence_object_summary(item) for item in value.items],
        "next_cursor": value.next_cursor,
    }


def serialize_dataset_summary(value: DatasetSummary) -> dict[str, str]:
    if not isinstance(value, DatasetSummary):
        raise TypeError("MCP Dataset serialization requires its summary.")
    return {
        "dataset_id": serialize_entity_id(value.dataset_id),
        "created_at": serialize_timestamp(value.created_at),
        "manifest_schema": serialize_schema_ref(value.manifest_schema),
        "content_schema": serialize_schema_ref(value.content_schema),
        "content_digest": serialize_digest(value.content_digest),
        "transformation_id": serialize_entity_id(value.transformation_id),
        "transformation_version": str(value.transformation_version),
    }


def serialize_dataset_page(value: Page[DatasetSummary]) -> dict[str, object]:
    if not isinstance(value, Page) or any(
        not isinstance(item, DatasetSummary) for item in value.items
    ):
        raise TypeError("MCP Dataset page serialization requires summaries.")
    return {
        "items": [serialize_dataset_summary(item) for item in value.items],
        "next_cursor": value.next_cursor,
    }


def serialize_execution_summary(
    value: ExecutionSummaryProjection,
) -> dict[str, object]:
    if not isinstance(value, ExecutionSummaryProjection):
        raise TypeError("MCP execution summary requires its projection.")
    return {
        "total_trades": value.total_trades,
        "winning_trades": value.winning_trades,
        "losing_trades": value.losing_trades,
        "net_profit": serialize_decimal(value.net_profit),
        "currency": value.currency,
        "initial_deposit": serialize_decimal(value.initial_deposit),
    }


def serialize_dataset_detail(value: DatasetDetail) -> dict[str, object]:
    if not isinstance(value, DatasetDetail):
        raise TypeError("MCP Dataset detail serialization requires its projection.")
    return {
        "summary": serialize_dataset_summary(value.summary),
        "input_manifests": [
            serialize_evidence_manifest_ref(item) for item in value.input_manifests
        ],
        "input_datasets": [serialize_entity_id(item) for item in value.input_datasets],
        "transformation_parameters_schema": (
            None
            if value.transformation_parameters_schema is None
            else serialize_schema_ref(value.transformation_parameters_schema)
        ),
        "execution_summary": (
            None
            if value.execution_summary is None
            else serialize_execution_summary(value.execution_summary)
        ),
    }


def serialize_analysis_summary(value: AnalysisSummary) -> dict[str, str]:
    if not isinstance(value, AnalysisSummary):
        raise TypeError("MCP Analysis serialization requires its summary.")
    return {
        "analysis_result_id": serialize_entity_id(value.analysis_result_id),
        "created_at": serialize_timestamp(value.created_at),
        "envelope_schema": serialize_schema_ref(value.envelope_schema),
        "result_schema": serialize_schema_ref(value.result_schema),
        "result_digest": serialize_digest(value.result_digest),
        "analysis_definition_id": serialize_entity_id(
            value.analysis_definition_id
        ),
        "analysis_version": str(value.analysis_version),
    }


def serialize_analysis_page(value: Page[AnalysisSummary]) -> dict[str, object]:
    if not isinstance(value, Page) or any(
        not isinstance(item, AnalysisSummary) for item in value.items
    ):
        raise TypeError("MCP Analysis page serialization requires summaries.")
    return {
        "items": [serialize_analysis_summary(item) for item in value.items],
        "next_cursor": value.next_cursor,
    }


def serialize_dataset_content_reference(
    value: DatasetContentReference,
) -> dict[str, str]:
    if not isinstance(value, DatasetContentReference):
        raise TypeError("MCP Dataset reference serialization requires its projection.")
    return {
        "dataset_id": serialize_entity_id(value.dataset_id),
        "content_digest": serialize_digest(value.content_digest),
    }


def _decimal_result(value: object) -> dict[str, str]:
    if not isinstance(value, Mapping):
        raise TypeError("Bounded Analysis decimal result is invalid.")
    if set(value) == {"value"} and isinstance(value["value"], str):
        return {"value": value["value"]}
    if set(value) == {"unavailable_reason"} and isinstance(
        value["unavailable_reason"], str
    ):
        return {"unavailable_reason": value["unavailable_reason"]}
    raise TypeError("Bounded Analysis decimal result is invalid.")


def serialize_execution_core_result(value: Mapping[str, object]) -> dict[str, object]:
    """Serialize only execution-core-analysis-result/0.1.0 fields."""

    try:
        digests = value["input_content_digests"]
        aggregate = value["aggregate_metrics"]
        distribution = value["realized_execution_distribution"]
        sequence = value["realized_execution_sequence"]
        drawdown = value["event_balance_analysis"]["event_balance_max_drawdown"]
        integrity = value["integrity"]
        if not all(
            isinstance(item, Mapping)
            for item in (digests, aggregate, distribution, sequence, drawdown, integrity)
        ):
            raise TypeError
        return {
            "schema_name": value["schema_name"],
            "schema_version": value["schema_version"],
            "currency": value["currency"],
            "input_content_digests": {
                name: digests[name]
                for name in (
                    "execution_summary",
                    "realized_execution_event_series",
                    "account_balance_event_series",
                )
            },
            "aggregate_metrics": {
                name: _decimal_result(aggregate[name])
                for name in (
                    "net_return",
                    "win_rate",
                    "loss_rate",
                    "expected_payoff",
                    "profit_factor",
                    "average_winning_result",
                    "average_losing_magnitude",
                    "payoff_ratio",
                    "gross_profit_return",
                    "gross_loss_return",
                )
            },
            "realized_execution_distribution": {
                "count": distribution["count"],
                **{
                    name: _decimal_result(distribution[name])
                    for name in (
                        "minimum",
                        "maximum",
                        "arithmetic_mean",
                        "median",
                        "mean_absolute_deviation",
                    )
                },
            },
            "realized_execution_sequence": {
                name: sequence[name]
                for name in (
                    "longest_positive_streak",
                    "longest_negative_streak",
                    "zero_result_count",
                )
            },
            "event_balance_analysis": {
                "event_balance_max_drawdown": {
                    "amount": _decimal_result(drawdown["amount"]),
                    "rate": _decimal_result(drawdown["rate"]),
                }
            },
            "integrity": {
                name: integrity[name]
                for name in (
                    "input_currency_consistent",
                    "input_evidence_manifest_consistent",
                )
            },
        }
    except (KeyError, TypeError) as error:
        raise TypeError("Bounded Analysis result is invalid.") from error


def serialize_analysis_detail(value: AnalysisDetail) -> dict[str, object]:
    if not isinstance(value, AnalysisDetail):
        raise TypeError("MCP Analysis detail serialization requires its projection.")
    return {
        "summary": serialize_analysis_summary(value.summary),
        "input_datasets": [
            serialize_dataset_content_reference(item) for item in value.input_datasets
        ],
        "analysis_parameters_schema": serialize_schema_ref(
            value.analysis_parameters_schema
        ),
        "computation_environment_id": serialize_entity_id(
            value.computation_environment_id
        ),
        "bounded_result": (
            None
            if value.bounded_result is None
            else serialize_execution_core_result(value.bounded_result.value)
        ),
    }


def serialize_provenance_summary(value: ProvenanceSummary) -> dict[str, object]:
    if not isinstance(value, ProvenanceSummary):
        raise TypeError("MCP provenance serialization requires its projection.")
    return {
        "build_record_id": serialize_entity_id(value.build_record_id),
        "artifact_id": serialize_entity_id(value.artifact_id),
        "artifact_digest": serialize_digest(value.artifact_digest),
        "test_definition_revision_id": serialize_entity_id(
            value.test_definition_revision_id
        ),
        "run_id": serialize_entity_id(value.run_id),
        "evidence_manifests": [
            serialize_evidence_manifest_ref(item) for item in value.evidence_manifests
        ],
        "datasets": [
            serialize_dataset_content_reference(item) for item in value.datasets
        ],
        "analysis_result_id": serialize_entity_id(value.analysis_result_id),
    }


def serialize_canonical_chain(
    value: CanonicalChainProjection,
) -> dict[str, object]:
    if not isinstance(value, CanonicalChainProjection):
        raise TypeError("MCP canonical chain serialization requires its projection.")
    return {
        "provenance": serialize_provenance_summary(value.provenance),
        "run": serialize_research_run_detail(value.run),
        "datasets": [serialize_dataset_summary(item) for item in value.datasets],
        "analysis": serialize_analysis_detail(value.analysis),
    }


def serialize_error(
    code: str, message: str, request_id: RequestId
) -> dict[str, object]:
    if (
        not isinstance(code, str)
        or not code
        or not isinstance(message, str)
        or not message
        or not isinstance(request_id, RequestId)
    ):
        raise TypeError("MCP error serialization requires bounded safe values.")
    return {
        "error": {
            "code": code,
            "message": message,
            "request_id": serialize_entity_id(request_id),
        }
    }


def serialize_build_command_result(value: BuildCommandResult) -> dict[str, object]:
    if not isinstance(value, BuildCommandResult):
        raise TypeError("MCP Build serialization requires a BuildCommandResult.")
    return {
        "request_id": serialize_entity_id(value.request_id),
        "build_record_id": serialize_entity_id(value.build_record_id),
        "outcome": None if value.outcome is None else serialize_enum(value.outcome),
        "artifact_id": (
            None if value.artifact_id is None else serialize_entity_id(value.artifact_id)
        ),
        "published": value.published,
    }


def serialize_run_command_result(value: RunCommandResult) -> dict[str, object]:
    if not isinstance(value, RunCommandResult):
        raise TypeError("MCP Run serialization requires a RunCommandResult.")
    return {
        "request_id": serialize_entity_id(value.request_id),
        "run_id": serialize_entity_id(value.run_id),
        "status": value.status,
        "evidence_outcome": (
            None
            if value.evidence_outcome is None
            else serialize_enum(value.evidence_outcome)
        ),
        "evidence_manifest": (
            None
            if value.evidence_manifest is None
            else serialize_evidence_manifest_ref(value.evidence_manifest)
        ),
        "published": value.published,
    }


def serialize_transform_command_result(
    value: TransformEvidenceCommandResult,
) -> dict[str, object]:
    if not isinstance(value, TransformEvidenceCommandResult):
        raise TypeError(
            "MCP transformation serialization requires its command result."
        )
    return {
        "request_id": serialize_entity_id(value.request_id),
        "run_id": serialize_entity_id(value.run_id),
        "datasets": [
            {
                "dataset_id": serialize_entity_id(item.dataset_id),
                "content_digest": serialize_digest(item.content_digest),
                "content_schema": serialize_schema_ref(item.content_schema),
                "published": item.published,
            }
            for item in value.datasets
        ],
    }


def serialize_analysis_command_result(
    value: AnalysisCommandResult,
) -> dict[str, object]:
    if not isinstance(value, AnalysisCommandResult):
        raise TypeError("MCP Analysis serialization requires its command result.")
    return {
        "request_id": serialize_entity_id(value.request_id),
        "analysis_result_id": (
            None
            if value.analysis_result_id is None
            else serialize_entity_id(value.analysis_result_id)
        ),
        "result_digest": (
            None
            if value.result_digest is None
            else serialize_digest(value.result_digest)
        ),
        "result_schema": (
            None
            if value.result_schema is None
            else serialize_schema_ref(value.result_schema)
        ),
        "published": value.published,
    }
