"""Pure presentation models for the read-only Research Overview."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from decimal import Context, Decimal, localcontext

from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    CanonicalChainProjection,
    DatasetDetail,
    DatasetSummary,
    EvidenceObjectSummary,
    ExecutionSummaryProjection,
    ResearchRunDetail,
)
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


UNAVAILABLE = "Unavailable"
_EXECUTION_SUMMARY = SchemaRef(
    SchemaName("execution-summary"), SchemaVersion(0, 1, 0)
)
_REALIZED_EVENTS = SchemaRef(
    SchemaName("realized-execution-event-series"), SchemaVersion(0, 1, 0)
)
_EVENT_BALANCE = SchemaRef(
    SchemaName("account-balance-event-series"), SchemaVersion(0, 1, 0)
)


@dataclass(frozen=True, slots=True)
class MetricCard:
    label: str
    value: str
    help_text: str | None = None


@dataclass(frozen=True, slots=True)
class ChartPoint:
    label: str
    value: int | Decimal


@dataclass(frozen=True, slots=True)
class ResearchOverview:
    run_id: str
    status: str
    evidence_outcome: str
    reproducibility: str
    reproducibility_reasons: tuple[str, ...]
    experiment_context: tuple[tuple[str, str], ...]
    primary_metrics: tuple[MetricCard, ...]
    winning_losing: tuple[ChartPoint, ...]
    realized_pnl_summary: tuple[ChartPoint, ...]


@dataclass(frozen=True, slots=True)
class DatasetView:
    label: str
    dataset_id: str
    content_schema: str
    content_digest: str
    manifest_schema: str
    transformation_id: str
    transformation_version: str
    input_manifests: tuple[str, ...]
    input_datasets: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class AnalysisInputView:
    label: str
    dataset_id: str
    content_digest: str


@dataclass(frozen=True, slots=True)
class AnalysisView:
    analysis_result_id: str
    definition_id: str
    definition_version: str
    result_schema: str
    result_digest: str
    parameters_schema: str
    computation_environment_id: str
    inputs: tuple[AnalysisInputView, ...]
    bounded_metrics: tuple[MetricCard, ...]


@dataclass(frozen=True, slots=True)
class ProvenanceStage:
    label: str
    identity: str
    digest: str | None = None


@dataclass(frozen=True, slots=True)
class EvidenceObjectView:
    object_id: str
    manifest_id: str
    media_type: str
    byte_length: str
    content_digest: str
    payload_schema: str
    provider_namespace: str


def format_money(value: Decimal | None, currency: str | None) -> str:
    if value is None or currency is None:
        return UNAVAILABLE
    return f"{currency} {value:,.2f}"


def format_percentage(value: Decimal | None) -> str:
    if value is None:
        return UNAVAILABLE
    with localcontext(Context(prec=50)):
        return f"{value * Decimal(100):.3f}%"


def format_decimal(value: Decimal | None) -> str:
    if value is None:
        return UNAVAILABLE
    return f"{value:.4f}".rstrip("0").rstrip(".")


def format_digest(value: object) -> str:
    digest = str(value)
    return f"sha256:{digest[:12]}…"


def dataset_label(schema: SchemaRef) -> str:
    return {
        _EXECUTION_SUMMARY: "Execution Summary",
        _REALIZED_EVENTS: "Realized Execution Events",
        _EVENT_BALANCE: "Account Balance Events",
    }.get(schema, "Dataset")


def build_dataset_view(summary: DatasetSummary, detail: DatasetDetail) -> DatasetView:
    return DatasetView(
        dataset_label(summary.content_schema),
        str(summary.dataset_id),
        str(summary.content_schema),
        str(summary.content_digest),
        str(summary.manifest_schema),
        str(summary.transformation_id),
        str(summary.transformation_version),
        tuple(str(item.manifest_id) for item in detail.input_manifests),
        tuple(str(item) for item in detail.input_datasets),
    )


def build_analysis_view(
    detail: AnalysisDetail, dataset_labels: Mapping[str, str]
) -> AnalysisView:
    result = (
        detail.bounded_result.value if detail.bounded_result is not None else None
    )
    aggregate = _mapping(result, "aggregate_metrics")
    distribution = _mapping(result, "realized_execution_distribution")
    sequence = _mapping(result, "realized_execution_sequence")
    drawdown = _mapping(_mapping(result, "event_balance_analysis"), "event_balance_max_drawdown")
    currency = _text(result, "currency")
    metrics = (
        MetricCard("Net Return", format_percentage(_decimal(aggregate, "net_return"))),
        MetricCard("Win Rate", format_percentage(_decimal(aggregate, "win_rate"))),
        MetricCard("Loss Rate", format_percentage(_decimal(aggregate, "loss_rate"))),
        MetricCard(
            "Expected Payoff",
            format_money(_decimal(aggregate, "expected_payoff"), currency),
        ),
        MetricCard("Profit Factor", format_decimal(_decimal(aggregate, "profit_factor"))),
        MetricCard(
            "Average Winner",
            format_money(_decimal(aggregate, "average_winning_result"), currency),
        ),
        MetricCard(
            "Average Losing Magnitude",
            format_money(_decimal(aggregate, "average_losing_magnitude"), currency),
        ),
        MetricCard("Payoff Ratio", format_decimal(_decimal(aggregate, "payoff_ratio"))),
        MetricCard("Realized Event Count", _integer(distribution, "count")),
        MetricCard(
            "Realized PnL Minimum",
            format_money(_decimal(distribution, "minimum"), currency),
        ),
        MetricCard(
            "Realized PnL Median",
            format_money(_decimal(distribution, "median"), currency),
        ),
        MetricCard(
            "Realized PnL Mean",
            format_money(_decimal(distribution, "arithmetic_mean"), currency),
        ),
        MetricCard(
            "Realized PnL Maximum",
            format_money(_decimal(distribution, "maximum"), currency),
        ),
        MetricCard(
            "Longest Positive Streak",
            _integer(sequence, "longest_positive_streak"),
        ),
        MetricCard(
            "Longest Negative Streak",
            _integer(sequence, "longest_negative_streak"),
        ),
        MetricCard(
            "Event-Balance Max Drawdown",
            format_money(_decimal(drawdown, "amount"), currency),
            "Based on observed account-balance events, not continuous equity.",
        ),
        MetricCard(
            "Event-Balance Max Drawdown Rate",
            format_percentage(_decimal(drawdown, "rate")),
            "Based on observed account-balance events, not continuous equity.",
        ),
    ) if result is not None else ()
    return AnalysisView(
        str(detail.summary.analysis_result_id),
        str(detail.summary.analysis_definition_id),
        str(detail.summary.analysis_version),
        str(detail.summary.result_schema),
        str(detail.summary.result_digest),
        str(detail.analysis_parameters_schema),
        str(detail.computation_environment_id),
        tuple(
            AnalysisInputView(
                dataset_labels.get(str(item.dataset_id), "Dataset"),
                str(item.dataset_id),
                str(item.content_digest),
            )
            for item in detail.input_datasets
        ),
        metrics,
    )


def build_provenance_stages(
    chain: CanonicalChainProjection,
) -> tuple[ProvenanceStage, ...]:
    provenance = chain.provenance
    return (
        ProvenanceStage("Build", str(provenance.build_record_id)),
        ProvenanceStage(
            "Artifact", str(provenance.artifact_id), str(provenance.artifact_digest)
        ),
        ProvenanceStage(
            "Test Definition", str(provenance.test_definition_revision_id)
        ),
        ProvenanceStage("Run", str(provenance.run_id)),
        *(
            ProvenanceStage(
                "Raw Evidence Manifest",
                str(item.manifest_id),
                str(item.content_digest),
            )
            for item in provenance.evidence_manifests
        ),
        *(
            ProvenanceStage("Dataset", str(item.dataset_id), str(item.content_digest))
            for item in provenance.datasets
        ),
        ProvenanceStage(
            "Analysis Result",
            str(provenance.analysis_result_id),
            str(chain.analysis.summary.result_digest),
        ),
    )


def build_evidence_view(summary: EvidenceObjectSummary) -> EvidenceObjectView:
    return EvidenceObjectView(
        str(summary.object_id),
        str(summary.manifest_id),
        summary.media_type,
        f"{summary.byte_length:,} bytes",
        str(summary.content_digest),
        UNAVAILABLE if summary.payload_schema is None else str(summary.payload_schema),
        UNAVAILABLE if summary.provider_namespace is None else summary.provider_namespace,
    )


def execution_environment_fields(
    run: ResearchRunDetail,
) -> tuple[tuple[str, str], ...]:
    build = next((item for item in run.provider_runtimes if item.role == "build"), None)
    return (
        ("Environment Configuration", str(run.environment_configuration_id)),
        (
            "Build Provider",
            UNAVAILABLE if build is None else build.provider_namespace,
        ),
        (
            "Build Provider Version",
            UNAVAILABLE if build is None or build.version is None else build.version,
        ),
        (
            "Build Executable Digest",
            UNAVAILABLE
            if build is None or build.executable_digest is None
            else format_digest(build.executable_digest),
        ),
        ("Execution Runtime Version", UNAVAILABLE),
    )


def build_research_overview(
    run: ResearchRunDetail,
    execution_summary: ExecutionSummaryProjection | None,
    analysis: AnalysisDetail | None,
) -> ResearchOverview:
    result = (
        analysis.bounded_result.value
        if analysis is not None and analysis.bounded_result is not None
        else None
    )
    currency = (
        execution_summary.currency
        if execution_summary is not None
        else _text(result, "currency")
    )
    aggregate = _mapping(result, "aggregate_metrics")
    distribution = _mapping(result, "realized_execution_distribution")
    event_balance = _mapping(result, "event_balance_analysis")
    drawdown = _mapping(event_balance, "event_balance_max_drawdown")
    context = run.experiment_context
    experiment_context = (
        (
            ("Instrument", context.instrument),
            ("Timeframe", context.timeframe),
            ("Start", context.start_date.isoformat()),
            ("End", context.end_date.isoformat()),
            (
                "Requested initial capital",
                format_money(context.requested_initial_capital, context.currency),
            ),
            ("Currency", context.currency),
            ("Leverage", context.leverage),
        )
        if context is not None
        else tuple(
            (label, UNAVAILABLE)
            for label in (
                "Instrument",
                "Timeframe",
                "Start",
                "End",
                "Requested initial capital",
                "Currency",
                "Leverage",
            )
        )
    )
    summary = execution_summary
    drawdown_help = "Based on observed account-balance events, not continuous equity."
    metrics = (
        MetricCard(
            "Net Profit",
            format_money(None if summary is None else summary.net_profit, currency),
        ),
        MetricCard("Net Return", format_percentage(_decimal(aggregate, "net_return"))),
        MetricCard(
            "Total Trades",
            UNAVAILABLE if summary is None else str(summary.total_trades),
        ),
        MetricCard("Win Rate", format_percentage(_decimal(aggregate, "win_rate"))),
        MetricCard(
            "Profit Factor",
            format_decimal(_decimal(aggregate, "profit_factor")),
        ),
        MetricCard(
            "Payoff Ratio",
            format_decimal(_decimal(aggregate, "payoff_ratio")),
        ),
        MetricCard(
            "Event-Balance Max Drawdown",
            format_money(_decimal(drawdown, "amount"), currency),
            drawdown_help,
        ),
        MetricCard(
            "Event-Balance Max Drawdown Rate",
            format_percentage(_decimal(drawdown, "rate")),
            drawdown_help,
        ),
    )
    winning_losing = (
        ()
        if summary is None
        else (
            ChartPoint("Winning", summary.winning_trades),
            ChartPoint("Losing", summary.losing_trades),
        )
    )
    realized = tuple(
        ChartPoint(label, value)
        for label, key in (
            ("Minimum", "minimum"),
            ("Median", "median"),
            ("Mean", "arithmetic_mean"),
            ("Maximum", "maximum"),
        )
        if (value := _decimal(distribution, key)) is not None
    )
    reproducibility = run.execution_reproducibility
    return ResearchOverview(
        str(run.summary.run_id),
        run.summary.status,
        (
            UNAVAILABLE
            if run.summary.evidence_outcome is None
            else run.summary.evidence_outcome.value
        ),
        reproducibility.level.value,
        tuple(reason.detail for reason in reproducibility.reasons),
        experiment_context,
        metrics,
        winning_losing,
        realized,
    )


def _mapping(value: object, key: str) -> Mapping[str, object] | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, Mapping) else None


def _decimal(value: Mapping[str, object] | None, key: str) -> Decimal | None:
    candidate = _mapping(value, key)
    if candidate is None or set(candidate) != {"value"}:
        return None
    raw = candidate["value"]
    try:
        parsed = Decimal(raw)
    except (TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _text(value: object, key: str) -> str | None:
    if not isinstance(value, Mapping):
        return None
    candidate = value.get(key)
    return candidate if isinstance(candidate, str) and candidate else None


def _integer(value: Mapping[str, object] | None, key: str) -> str:
    if value is None:
        return UNAVAILABLE
    candidate = value.get(key)
    return str(candidate) if type(candidate) is int else UNAVAILABLE
