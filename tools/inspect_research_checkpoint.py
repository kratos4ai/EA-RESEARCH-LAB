"""Render one persisted research checkpoint through PlatformApi queries only."""

from __future__ import annotations

import argparse
import hashlib
import logging
import shutil
import tempfile
from collections.abc import Mapping
from pathlib import Path

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.platform_commands import PlatformCommands
from ea_research_lab.application.platform_queries import PlatformQueries
from ea_research_lab.application.research_query import PageRequest
from ea_research_lab.domain.identifiers import BuildRecordId, RequestId, RunId
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from ea_research_lab.infrastructure.sqlite_research_query import SqliteResearchQuery


_UNAVAILABLE = "NOT AVAILABLE THROUGH PLATFORM API"
_CORE_RESULT = "urn:ea-research-lab:schema:execution-core-analysis-result:0.1.0"
_METRICS = (
    ("Total trades", None),
    ("Winning trades", None),
    ("Losing trades", None),
    ("Net profit", None),
    ("Net return", ("aggregate_metrics", "net_return")),
    ("Win rate", ("aggregate_metrics", "win_rate")),
    ("Loss rate", ("aggregate_metrics", "loss_rate")),
    ("Expected payoff", ("aggregate_metrics", "expected_payoff")),
    ("Profit factor", ("aggregate_metrics", "profit_factor")),
    ("Average winner", ("aggregate_metrics", "average_winning_result")),
    (
        "Average losing magnitude",
        ("aggregate_metrics", "average_losing_magnitude"),
    ),
    ("Payoff ratio", ("aggregate_metrics", "payoff_ratio")),
    ("Realized PnL minimum", ("realized_execution_distribution", "minimum")),
    ("Realized PnL maximum", ("realized_execution_distribution", "maximum")),
    (
        "Realized PnL mean",
        ("realized_execution_distribution", "arithmetic_mean"),
    ),
    ("Realized PnL median", ("realized_execution_distribution", "median")),
    (
        "Mean absolute deviation",
        ("realized_execution_distribution", "mean_absolute_deviation"),
    ),
    (
        "Longest positive streak",
        ("realized_execution_sequence", "longest_positive_streak"),
    ),
    (
        "Longest negative streak",
        ("realized_execution_sequence", "longest_negative_streak"),
    ),
    (
        "Zero-result count",
        ("realized_execution_sequence", "zero_result_count"),
    ),
    (
        "Event-balance maximum drawdown amount",
        ("event_balance_analysis", "event_balance_max_drawdown", "amount"),
    ),
    (
        "Event-balance maximum drawdown rate",
        ("event_balance_analysis", "event_balance_max_drawdown", "rate"),
    ),
)


def render_report(
    api: PlatformApi,
    context: RequestContext,
    build_record_id: BuildRecordId,
    run_id: RunId | None = None,
) -> str:
    """Navigate one checkpoint and render only PlatformApi-visible information."""

    runs = api.list_research_runs(context, PageRequest(200))
    if runs.next_cursor is not None:
        raise ValueError("Research database contains more than 200 Runs.")
    selected = _select_run(runs.items, run_id)
    run = api.get_research_run(context, selected.run_id)

    dataset_page = api.list_run_datasets(context, selected.run_id, PageRequest(200))
    if dataset_page.next_cursor is not None:
        raise ValueError("Research Run contains more than 200 Datasets.")
    datasets = tuple(
        api.get_dataset(context, item.dataset_id) for item in dataset_page.items
    )

    analysis_ids = set()
    for dataset in datasets:
        page = api.list_dataset_analyses(
            context, dataset.summary.dataset_id, PageRequest(200)
        )
        if page.next_cursor is not None:
            raise ValueError("Research Dataset contains more than 200 Analyses.")
        analysis_ids.update(item.analysis_result_id for item in page.items)
    if len(analysis_ids) != 1:
        raise ValueError("Research checkpoint must resolve to exactly one Analysis.")
    analysis = api.get_analysis(context, analysis_ids.pop())
    chain = api.get_canonical_chain(
        context,
        build_record_id,
        selected.run_id,
        analysis.summary.analysis_result_id,
    )
    return _markdown(run, datasets, analysis, chain)


def inspect_database(
    database: Path, build_record_id: BuildRecordId, run_id: RunId | None = None
) -> str:
    """Compose against a disposable copy so the canonical database is untouched."""

    if not database.is_file():
        raise ValueError("Research database does not exist.")
    before = _digest(database)
    with tempfile.TemporaryDirectory(prefix="earl-inspect-") as name:
        copy = Path(name) / "research.sqlite3"
        shutil.copy2(database, copy)
        logger = logging.getLogger("ea_research_lab.operator")
        with SqliteDataPlane(copy) as data_plane, SqliteResearchQuery(copy) as query:
            commands = PlatformCommands(
                data_plane,
                _disabled_command,
                _disabled_command,
                _disabled_command,
                _disabled_command,
                logger,
            )
            api = PlatformApi(commands, PlatformQueries(data_plane, query), logger)
            report = render_report(
                api,
                RequestContext(new_entity_id(RequestId), "research-operator"),
                build_record_id,
                run_id,
            )
    if _digest(database) != before:
        raise RuntimeError("Canonical research database changed during inspection.")
    return report


def _select_run(runs, requested):
    if requested is not None:
        selected = tuple(item for item in runs if item.run_id == requested)
        if len(selected) != 1:
            raise ValueError("Requested Run was not discovered.")
        return selected[0]
    if len(runs) != 1:
        raise ValueError("Specify --run-id when the database does not contain one Run.")
    return runs[0]


def _markdown(run, datasets, analysis, chain) -> str:
    result = (
        analysis.bounded_result.value
        if analysis.bounded_result is not None
        and str(analysis.bounded_result.schema_ref) == _CORE_RESULT
        else None
    )
    reproducibility = run.execution_reproducibility
    evidence = run.summary.evidence_manifest
    lines = [
        "# Research Checkpoint Inspection",
        "",
        "## Research Execution",
        "",
        f"- Run: `{run.summary.run_id}`",
        f"- Status: `{run.summary.status}`",
        f"- Created: `{run.summary.created_at}`",
        f"- Started: `{run.summary.started_at}`",
        f"- Finished: `{run.summary.finished_at}`",
        f"- Artifact: `{run.summary.artifact_id}`",
        f"- Test Definition revision: `{run.summary.test_definition_revision_id}`",
        "",
        "## Environment",
        "",
        "| Information | Availability | Value |",
        "|---|---|---|",
    ]
    for label in (
        "Symbol",
        "Timeframe",
        "Start/end",
        "Initial deposit",
        "Modeling mode",
        "Leverage",
    ):
        lines.append(f"| {label} | {_UNAVAILABLE} | not exposed |")
    reasons = "; ".join(
        f"{item.code}: {item.detail}" for item in reproducibility.reasons
    ) or "no reasons recorded"
    lines.extend(
        (
            f"| Reproducibility assessment | AVAILABLE | "
            f"`{reproducibility.level.value}`; {reasons} |",
            f"| Environment configuration identity | AVAILABLE | "
            f"`{run.environment_configuration_id}` |",
            f"| MetaTrader version | {_UNAVAILABLE} | not exposed |",
            f"| MetaEditor/build environment | {_UNAVAILABLE} | not exposed |",
            "",
            "## Research Outcome",
            "",
            f"- Execution lifecycle: `{run.summary.status}`",
            f"- Evidence collection: `{run.summary.evidence_outcome.value}`",
            f"- Analysis Result: `{analysis.summary.analysis_result_id}`",
            f"- Analysis schema: `{analysis.summary.result_schema}`",
            f"- Analysis digest: `{analysis.summary.result_digest}`",
            "",
            "## Core Metrics",
            "",
            "| Metric | Availability | Value |",
            "|---|---|---|",
        )
    )
    for label, path in _METRICS:
        value = _metric(result, path)
        lines.append(
            f"| {label} | {'AVAILABLE' if value is not None else _UNAVAILABLE} "
            f"| {value if value is not None else 'not exposed'} |"
        )

    lines.extend(("", "## Datasets", ""))
    for dataset in datasets:
        summary = dataset.summary
        lines.append(
            f"- `{summary.dataset_id}` - `{summary.content_schema}` - "
            f"SHA-256 `{summary.content_digest}`"
        )
    lines.extend(
        (
            "",
            "Dataset payloads are not available through the current PlatformApi.",
            "",
            "## Analysis",
            "",
            f"- Definition: `{analysis.summary.analysis_definition_id}`",
            f"- Version: `{analysis.summary.analysis_version}`",
            f"- Parameters schema: `{analysis.analysis_parameters_schema}`",
            f"- Computation environment: `{analysis.computation_environment_id}`",
            "- The bounded Execution Core result is available inline.",
            "",
            "## Provenance",
            "",
            "```text",
            f"Build {chain.provenance.build_record_id}",
            f"  -> Artifact {chain.provenance.artifact_id}",
            f"  -> Test Definition {chain.provenance.test_definition_revision_id}",
            f"  -> Run {chain.provenance.run_id}",
        )
    )
    for item in chain.provenance.evidence_manifests:
        lines.append(
            f"  -> Evidence {item.manifest_id} sha256:{item.content_digest}"
        )
    for item in chain.provenance.datasets:
        lines.append(f"  -> Dataset {item.dataset_id} sha256:{item.content_digest}")
    lines.extend(
        (
            f"  -> Analysis {chain.provenance.analysis_result_id}",
            "```",
            "",
            "## Evidence / Operational Findings",
            "",
            f"- Sealed manifest: `{evidence.manifest_id}`",
            f"- Manifest digest: `{evidence.content_digest}`",
            f"- Collection outcome: `{run.summary.evidence_outcome.value}`",
            f"- Evidence revision count: `{len(run.evidence_history)}`",
            f"- `MA_CROSS`: {_UNAVAILABLE}",
            f"- `POSITION_OPEN`: {_UNAVAILABLE}",
            f"- `POSITION_CLOSE`: {_UNAVAILABLE}",
            f"- `POSITION_REVERSE`: {_UNAVAILABLE}",
            f"- `TRADE_ERROR`: {_UNAVAILABLE}",
            "",
            "## Information Unavailable Through PlatformApi",
            "",
            "- Execution-summary counts and net profit.",
            "- Test Definition execution configuration and SUT inputs.",
            "- MetaTrader and MetaEditor versions or provider evidence.",
            "- Raw Evidence descriptors, bytes, logs, and event drill-down.",
            "- Dataset content.",
            "- Build Record discovery; its identity must be supplied to request "
            "the canonical chain.",
        )
    )
    return "\n".join(lines) + "\n"


def _metric(result, path):
    if result is None or path is None:
        return None
    value = result
    try:
        for key in path:
            value = value[key]
    except (KeyError, TypeError):
        return None
    if isinstance(value, Mapping):
        if "value" in value:
            return value["value"]
        if "unavailable_reason" in value:
            return f"unavailable: {value['unavailable_reason']}"
        return None
    return str(value)


def _digest(path: Path) -> str:
    with path.open("rb") as stream:
        return hashlib.file_digest(stream, "sha256").hexdigest()


def _disabled_command(*args, **kwargs):
    raise RuntimeError("Research inspection cannot execute Commands.")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Inspect one persisted checkpoint through PlatformApi queries."
    )
    parser.add_argument("database", type=Path)
    parser.add_argument("--build-record-id", required=True, type=BuildRecordId.parse)
    parser.add_argument("--run-id", type=RunId.parse)
    arguments = parser.parse_args()
    print(
        inspect_database(
            arguments.database, arguments.build_record_id, arguments.run_id
        ),
        end="",
    )


if __name__ == "__main__":
    main()
