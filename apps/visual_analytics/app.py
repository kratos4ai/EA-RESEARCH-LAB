"""Local read-only Streamlit client for EA Research Lab."""

from __future__ import annotations

import argparse
import logging
import os
from pathlib import Path

import streamlit as st

from apps.visual_analytics.view_model import (
    UNAVAILABLE,
    AnalysisView,
    DatasetView,
    ResearchOverview,
    build_analysis_view,
    build_dataset_view,
    build_evidence_view,
    build_provenance_stages,
    build_research_overview,
    dataset_label,
    execution_environment_fields,
    format_digest,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.research_query import PageRequest
from ea_research_lab.domain.identifiers import AnalysisResultId, DatasetId, RequestId, RunId
from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    DatasetDetail,
    DatasetSummary,
    ExecutionSummaryProjection,
    ResearchRunDetail,
    ResearchRunSummary,
)
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion
from ea_research_lab.infrastructure.composition import compose_read_only_platform


_PAGE_LIMIT = 20
_EXECUTION_SUMMARY = SchemaRef(
    SchemaName("execution-summary"), SchemaVersion(0, 1, 0)
)


def main() -> None:
    st.set_page_config(page_title="EA Research Lab", layout="wide")
    st.title("EA Research Lab")
    st.caption("Read-only Visual Analytics")
    database = _database_path()
    if database is None:
        st.error("Provide an explicit research database path.")
        return
    _reset_state_for_database(database)
    context = RequestContext(new_entity_id(RequestId), "visual-analytics")
    logger = logging.getLogger("ea_research_lab.visual_analytics")
    try:
        with compose_read_only_platform(database, logger) as api:
            _render_research_runs(api, context)
    except Exception:
        st.error("Research data could not be loaded safely.")


def _render_research_runs(api: PlatformApi, context: RequestContext) -> None:
    st.header("Research Runs")
    page = api.list_research_runs(
        context, PageRequest(_PAGE_LIMIT, st.session_state.page_cursor)
    )
    if not page.items:
        st.info("No research Runs are available on this page.")
        _render_keyset_pagination("run", page.next_cursor, "Runs")
        return
    labels = {str(item.run_id): _run_label(item) for item in page.items}
    run_ids = tuple(labels)
    selected = st.session_state.get("selected_run")
    if selected not in run_ids:
        st.session_state.selected_run = run_ids[0]
    selected = st.selectbox(
        "Select a Run",
        run_ids,
        format_func=labels.__getitem__,
        key="selected_run",
    )
    st.caption(f"{len(run_ids)} Run(s) on this bounded page")
    _render_keyset_pagination("run", page.next_cursor, "Runs")
    _reset_drilldown_for_run(selected)
    detail = api.get_research_run(context, RunId.parse(selected))
    execution_summary, analysis = _overview_inputs(api, context, detail.summary.run_id)
    _render_selected_run(
        api,
        context,
        detail,
        build_research_overview(detail, execution_summary, analysis),
        analysis,
    )


def _overview_inputs(
    api: PlatformApi, context: RequestContext, run_id: RunId
) -> tuple[ExecutionSummaryProjection | None, AnalysisDetail | None]:
    datasets = api.list_run_datasets(context, run_id, PageRequest(_PAGE_LIMIT))
    summary = next(
        (item for item in datasets.items if item.content_schema == _EXECUTION_SUMMARY),
        None,
    )
    if summary is None:
        return None, None
    execution_summary = api.get_dataset(
        context, summary.dataset_id
    ).execution_summary
    analyses = api.list_dataset_analyses(
        context, summary.dataset_id, PageRequest(1)
    )
    analysis = (
        None
        if not analyses.items
        else api.get_analysis(context, analyses.items[0].analysis_result_id)
    )
    return execution_summary, analysis


def _render_overview(model: ResearchOverview) -> None:
    st.header("Run Overview")
    st.caption(model.run_id)
    status_columns = st.columns(3)
    status_columns[0].metric("Run Status", model.status)
    status_columns[1].metric("Evidence Collection", model.evidence_outcome)
    status_columns[2].metric("Reproducibility", model.reproducibility)
    for reason in model.reproducibility_reasons:
        st.caption(reason)

    st.subheader("Experiment Context")
    context_columns = st.columns(4)
    for index, (label, value) in enumerate(model.experiment_context):
        context_columns[index % len(context_columns)].metric(label, value)

    st.subheader("Core Research Metrics")
    metric_columns = st.columns(4)
    for index, metric in enumerate(model.primary_metrics):
        metric_columns[index % len(metric_columns)].metric(
            metric.label, metric.value, help=metric.help_text
        )

    st.subheader("Winning vs Losing Executions")
    if model.winning_losing:
        st.bar_chart(
            {point.label: [point.value] for point in model.winning_losing},
            horizontal=True,
        )
    else:
        st.info(UNAVAILABLE)

    st.subheader("Realized PnL Statistical Summary")
    st.caption(
        "Minimum, median, mean, and maximum realized event PnL; not a distribution."
    )
    if model.realized_pnl_summary:
        st.bar_chart(
            {
                point.label: [float(point.value)]
                for point in model.realized_pnl_summary
            },
            horizontal=True,
        )
    else:
        st.info(UNAVAILABLE)


def _render_selected_run(
    api: PlatformApi,
    context: RequestContext,
    run: ResearchRunDetail,
    overview: ResearchOverview,
    overview_analysis: AnalysisDetail | None,
) -> None:
    dataset_page = api.list_run_datasets(
        context,
        run.summary.run_id,
        PageRequest(_PAGE_LIMIT, st.session_state.dataset_cursor),
    )
    dataset_summary, dataset_detail = _select_dataset(api, context, dataset_page.items)
    _, analysis_detail, analysis_next = _select_analysis(
        api, context, dataset_summary
    )
    selected_analysis = analysis_detail or overview_analysis

    overview_tab, datasets_tab, analysis_tab, provenance_tab, evidence_tab = st.tabs(
        ("Overview", "Datasets", "Analysis", "Provenance", "Evidence")
    )
    with overview_tab:
        _render_overview(overview)
        st.subheader("Execution Environment")
        columns = st.columns(3)
        for index, (label, value) in enumerate(execution_environment_fields(run)):
            columns[index % len(columns)].metric(label, value)
        st.caption(
            "Build-provider facts are historical Build evidence. Execution runtime "
            "version remains unavailable when it was not retained canonically."
        )
    with datasets_tab:
        _render_datasets(dataset_page.items, dataset_summary, dataset_detail)
        _render_keyset_pagination("dataset", dataset_page.next_cursor, "Datasets")
    with analysis_tab:
        _render_analysis(
            analysis_detail,
            dataset_page.items,
            dataset_summary,
        )
        _render_keyset_pagination("analysis", analysis_next, "Analysis Results")
    with provenance_tab:
        _render_provenance(api, context, run, selected_analysis)
    with evidence_tab:
        _render_evidence(api, context, run)


def _select_dataset(
    api: PlatformApi,
    context: RequestContext,
    summaries: tuple[DatasetSummary, ...],
) -> tuple[DatasetSummary | None, DatasetDetail | None]:
    if not summaries:
        return None, None
    labels = {
        str(item.dataset_id): f"{dataset_label(item.content_schema)} · {item.dataset_id}"
        for item in summaries
    }
    identifiers = tuple(labels)
    selected = st.session_state.get("selected_dataset")
    if selected not in identifiers:
        st.session_state.selected_dataset = identifiers[0]
    selected = st.selectbox(
        "Select a Dataset",
        identifiers,
        format_func=labels.__getitem__,
        key="selected_dataset",
    )
    _reset_analysis_for_dataset(selected)
    summary = next(item for item in summaries if str(item.dataset_id) == selected)
    return summary, api.get_dataset(context, DatasetId.parse(selected))


def _select_analysis(
    api: PlatformApi,
    context: RequestContext,
    dataset: DatasetSummary | None,
) -> tuple[object | None, AnalysisDetail | None, str | None]:
    if dataset is None:
        return None, None, None
    page = api.list_dataset_analyses(
        context,
        dataset.dataset_id,
        PageRequest(_PAGE_LIMIT, st.session_state.analysis_cursor),
    )
    if not page.items:
        return None, None, page.next_cursor
    labels = {
        str(item.analysis_result_id): (
            f"{item.analysis_version} · {item.analysis_result_id}"
        )
        for item in page.items
    }
    identifiers = tuple(labels)
    selected = st.session_state.get("selected_analysis")
    if selected not in identifiers:
        st.session_state.selected_analysis = identifiers[0]
    selected = st.selectbox(
        "Select an Analysis Result",
        identifiers,
        format_func=labels.__getitem__,
        key="selected_analysis",
    )
    summary = next(
        item for item in page.items if str(item.analysis_result_id) == selected
    )
    return (
        summary,
        api.get_analysis(context, AnalysisResultId.parse(selected)),
        page.next_cursor,
    )


def _render_datasets(
    summaries: tuple[DatasetSummary, ...],
    selected_summary: DatasetSummary | None,
    detail: DatasetDetail | None,
) -> None:
    st.header("Datasets")
    if not summaries or selected_summary is None or detail is None:
        st.info("No Datasets")
        return
    st.caption(f"{len(summaries)} Dataset(s) on this bounded page")
    model = build_dataset_view(selected_summary, detail)
    _render_dataset_detail(model)


def _render_dataset_detail(model: DatasetView) -> None:
    st.subheader(model.label)
    st.code(model.dataset_id)
    rows = {
        "Content schema": model.content_schema,
        "Content digest": format_digest(model.content_digest),
        "Manifest schema": model.manifest_schema,
        "Transformation": model.transformation_id,
        "Transformation version": model.transformation_version,
        "Input Evidence Manifests": ", ".join(model.input_manifests) or UNAVAILABLE,
        "Input Datasets": ", ".join(model.input_datasets) or UNAVAILABLE,
    }
    st.table(rows)
    with st.expander("Complete Dataset content digest"):
        st.code(model.content_digest)


def _render_analysis(
    detail: AnalysisDetail | None,
    datasets: tuple[DatasetSummary, ...],
    selected_dataset: DatasetSummary | None,
) -> None:
    st.header("Analysis")
    if selected_dataset is None:
        st.info("Select a Dataset to discover Analysis Results.")
        return
    if detail is None:
        st.info("No Analysis Results")
        return
    labels = {str(item.dataset_id): dataset_label(item.content_schema) for item in datasets}
    model = build_analysis_view(detail, labels)
    _render_analysis_detail(model)


def _render_analysis_detail(model: AnalysisView) -> None:
    st.subheader("Analysis Result")
    st.code(model.analysis_result_id)
    st.table(
        {
            "Analysis Definition": model.definition_id,
            "Definition version": model.definition_version,
            "Result schema": model.result_schema,
            "Result digest": format_digest(model.result_digest),
            "Parameters schema": model.parameters_schema,
            "Computation environment": model.computation_environment_id,
        }
    )
    st.subheader("Analysis Inputs")
    for item in model.inputs:
        st.markdown(f"**{item.label}**")
        st.code(item.dataset_id)
        st.caption(format_digest(item.content_digest))
    with st.expander("Complete Analysis and input digests"):
        st.code(model.result_digest)
        for item in model.inputs:
            st.code(item.content_digest)
    st.subheader("Bounded Result Metrics")
    if not model.bounded_metrics:
        st.info("Result content is unavailable for this schema; metadata remains visible.")
        return
    columns = st.columns(3)
    for index, metric in enumerate(model.bounded_metrics):
        columns[index % len(columns)].metric(
            metric.label, metric.value, help=metric.help_text
        )


def _render_provenance(
    api: PlatformApi,
    context: RequestContext,
    run: ResearchRunDetail,
    analysis: AnalysisDetail | None,
) -> None:
    st.header("Reproducibility and Provenance")
    st.metric("Reproducibility Level", run.execution_reproducibility.level.value)
    if run.execution_reproducibility.reasons:
        for reason in run.execution_reproducibility.reasons:
            st.caption(f"{reason.code}: {reason.detail}")
    else:
        st.caption("No reproducibility reasons were recorded.")
    if analysis is None:
        st.info("Verified provenance is unavailable until an Analysis Result is selected.")
        return
    try:
        chain = api.get_canonical_chain(
            context,
            run.build_record_id,
            run.summary.run_id,
            analysis.summary.analysis_result_id,
        )
    except Exception:
        st.error("Canonical provenance could not be verified safely.")
        return
    st.success("Canonical provenance verified")
    for stage in build_provenance_stages(chain):
        st.markdown(f"**{stage.label}**")
        st.code(stage.identity)
        if stage.digest is not None:
            st.caption(format_digest(stage.digest))
            with st.expander(f"Complete {stage.label} digest · {stage.identity}"):
                st.code(stage.digest)


def _render_evidence(
    api: PlatformApi, context: RequestContext, run: ResearchRunDetail
) -> None:
    st.header("Evidence Metadata")
    reference = run.summary.evidence_manifest
    if reference is None:
        st.info("No sealed Raw Evidence Manifest is available.")
        return
    try:
        page = api.list_run_evidence_objects(
            context,
            run.summary.run_id,
            reference.manifest_id,
            PageRequest(_PAGE_LIMIT, st.session_state.evidence_cursor),
        )
    except Exception:
        st.error("Evidence metadata could not be loaded safely.")
        return
    st.caption(f"Manifest {reference.manifest_id}")
    st.caption(f"Collection outcome: {run.summary.evidence_outcome.value}")
    if not page.items:
        st.info("No Evidence Objects")
    for summary in page.items:
        model = build_evidence_view(summary)
        st.subheader("Evidence Object")
        st.code(model.object_id)
        st.table(
            {
                "Media type": model.media_type,
                "Byte length": model.byte_length,
                "Content digest": format_digest(model.content_digest),
                "Payload schema": model.payload_schema,
                "Provider namespace": model.provider_namespace,
            }
        )
        with st.expander(f"Complete Evidence digest · {model.object_id}"):
            st.code(model.content_digest)
    _render_keyset_pagination("evidence", page.next_cursor, "Evidence Objects")


def _render_keyset_pagination(
    prefix: str, next_cursor: str | None, label: str
) -> None:
    cursor_key = "page_cursor" if prefix == "run" else f"{prefix}_cursor"
    history_key = (
        "cursor_history" if prefix == "run" else f"{prefix}_cursor_history"
    )
    previous, following = st.columns(2)
    if previous.button(
        f"Previous {label}",
        key=f"previous_{prefix}",
        disabled=not st.session_state[history_key],
        use_container_width=True,
    ):
        history = st.session_state[history_key]
        st.session_state[cursor_key] = history[-1]
        st.session_state[history_key] = history[:-1]
        _clear_selection(prefix)
        st.rerun()
    if following.button(
        f"Next {label}",
        key=f"next_{prefix}",
        disabled=next_cursor is None,
        use_container_width=True,
    ):
        st.session_state[history_key] = [
            *st.session_state[history_key],
            st.session_state[cursor_key],
        ]
        st.session_state[cursor_key] = next_cursor
        _clear_selection(prefix)
        st.rerun()


def _clear_selection(prefix: str) -> None:
    if prefix == "run":
        st.session_state.selected_run = None
    elif prefix == "dataset":
        st.session_state.selected_dataset = None
        st.session_state.selected_analysis = None
        st.session_state.analysis_cursor = None
        st.session_state.analysis_cursor_history = []
    elif prefix == "analysis":
        st.session_state.selected_analysis = None


def _reset_drilldown_for_run(run_id: str) -> None:
    if st.session_state.get("drilldown_run") != run_id:
        st.session_state.drilldown_run = run_id
        st.session_state.dataset_cursor = None
        st.session_state.dataset_cursor_history = []
        st.session_state.selected_dataset = None
        st.session_state.analysis_cursor = None
        st.session_state.analysis_cursor_history = []
        st.session_state.selected_analysis = None
        st.session_state.evidence_cursor = None
        st.session_state.evidence_cursor_history = []


def _reset_analysis_for_dataset(dataset_id: str) -> None:
    if st.session_state.get("drilldown_dataset") != dataset_id:
        st.session_state.drilldown_dataset = dataset_id
        st.session_state.analysis_cursor = None
        st.session_state.analysis_cursor_history = []
        st.session_state.selected_analysis = None


def _database_path() -> Path | None:
    parser = argparse.ArgumentParser(add_help=False)
    parser.add_argument("--database")
    arguments, _ = parser.parse_known_args()
    value = arguments.database or os.environ.get("EA_RESEARCH_LAB_DATABASE")
    return None if value is None else Path(value).expanduser().resolve()


def _reset_state_for_database(database: Path) -> None:
    identity = str(database)
    if st.session_state.get("database_identity") != identity:
        st.session_state.database_identity = identity
        st.session_state.page_cursor = None
        st.session_state.cursor_history = []
        st.session_state.selected_run = None
        st.session_state.drilldown_run = None
        st.session_state.drilldown_dataset = None


def _run_label(run: ResearchRunSummary) -> str:
    return f"{run.status.upper()} · {run.created_at} · {run.run_id}"


main()
