from __future__ import annotations

import json
import os
import tempfile
import unittest
from dataclasses import replace
from datetime import date
from decimal import Decimal, getcontext
from pathlib import Path
from unittest.mock import patch

from streamlit.testing.v1 import AppTest

from apps.visual_analytics.view_model import (
    UNAVAILABLE,
    build_analysis_view,
    build_dataset_view,
    build_evidence_view,
    build_provenance_stages,
    build_research_overview,
    dataset_label,
    execution_environment_fields,
    format_decimal,
    format_digest,
    format_money,
    format_percentage,
)
from ea_research_lab.application.data_plane import ANALYSIS_RESULT_REF
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.platform_commands import (
    AnalyzeDatasetsCommandRequest,
    DatasetInputReference,
    TransformEvidenceCommandRequest,
)
from ea_research_lab.application.platform_queries import PlatformQueries, _run_summary
from ea_research_lab.domain.evidence import EvidenceCollectionOutcome
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceObjectId,
    TestDefinitionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
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
    ResearchRunDetail,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from ea_research_lab.infrastructure.sqlite_research_query import SqliteResearchQuery
from tests.test_mt5_strategy_tester import _execution_document
from tests.test_platform_commands import (
    CORE_PARAMETERS_REF,
    _Provider,
    _build_request,
    _build_result,
    _commands,
    _context,
    _definitions,
    _known_report_bytes,
    _run_request,
)
from tests.test_sqlite_data_plane_chain import (
    _dataset,
    _payload,
    _plain,
    _run,
    _successful_build,
)
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderVerdict,
)


ROOT = Path(__file__).resolve().parents[1]
APP = ROOT / "apps" / "visual_analytics" / "app.py"
FIXTURES = ROOT / "tests" / "fixtures" / "schemas" / "valid"
CORE_RESULT_REF = SchemaRef(
    SchemaName("execution-core-analysis-result"), SchemaVersion(0, 1, 0)
)


def _analysis_detail() -> AnalysisDetail:
    result = json.loads(
        (FIXTURES / "execution-core-analysis-result.json").read_text(
            encoding="utf-8"
        )
    )
    return AnalysisDetail(
        AnalysisSummary(
            new_entity_id(AnalysisResultId),
            UtcTimestamp.parse("2026-08-12T12:00:00Z"),
            ANALYSIS_RESULT_REF,
            CORE_RESULT_REF,
            Sha256Digest("a" * 64),
            new_entity_id(AnalysisDefinitionId),
            DefinitionVersion("visual-test-1"),
        ),
        (DatasetContentReference(new_entity_id(DatasetId), Sha256Digest("b" * 64)),),
        CORE_PARAMETERS_REF,
        new_entity_id(EnvironmentConfigurationId),
        SchemaReferencedPayload(CORE_RESULT_REF, result),
    )


def _run_detail(status: str = "completed") -> ResearchRunDetail:
    durable = _run(status=status)
    return ResearchRunDetail(
        _run_summary(durable),
        _successful_build().build_record_id,
        TestDefinitionId.parse(durable.test_definition.value["test_definition_id"]),
        EnvironmentConfigurationId.parse(
            durable.run_manifest.value["environment_configuration_id"]
        ),
        ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
        tuple(item.reference for item in durable.evidence_history),
        ExperimentContextProjection(
            "EURUSD",
            "H1",
            date(2026, 1, 1),
            date(2026, 6, 30),
            Decimal("1000"),
            "USD",
            "1:100",
        ),
    )


def _summary() -> ExecutionSummaryProjection:
    return ExecutionSummaryProjection(135, 43, 92, Decimal("2.63"), "USD", Decimal("1000.00"))


def _dataset_detail(
    schema: SchemaRef = SchemaRef(
        SchemaName("execution-summary"), SchemaVersion(0, 1, 0)
    ),
) -> DatasetDetail:
    dataset_id = new_entity_id(DatasetId)
    manifest = _run_detail().evidence_history[-1]
    summary = DatasetSummary(
        dataset_id,
        UtcTimestamp.parse("2026-08-12T12:00:00Z"),
        SchemaRef(SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)),
        schema,
        Sha256Digest("c" * 64),
        new_entity_id(TransformationId),
        DefinitionVersion("visual-transform-1"),
    )
    return DatasetDetail(summary, (manifest,), (), None)


def _mt5_test_definition(build):
    request = _run_request(build, _context())
    document = _plain(request.test_definition.value)
    document["execution_configuration"] = {
        "schema_ref": "urn:ea-research-lab:schema:mt5-strategy-tester-execution:0.1.0",
        "value": _execution_document(),
    }
    return SchemaReferencedPayload(request.test_definition.schema_ref, document)


def _seed_complete(database: Path, *, include_analysis: bool = True):
    build = _successful_build()
    provider = _Provider(
        ExecutionProviderVerdict.COMPLETED,
        (
            CapturedExecutionOutput(
                _known_report_bytes(),
                "text/html",
                provider_namespace="metatrader5.strategy-tester.report",
            ),
        ),
    )
    with (
        SqliteDataPlane(database) as data_plane,
        SqliteResearchQuery(database) as discovery,
    ):
        commands, _ = _commands(
            data_plane, lambda request: _build_result(build), provider
        )
        api = PlatformApi(
            commands,
            PlatformQueries(data_plane, discovery),
            commands._logger,
        )
        context = _context()
        api.build_artifact(_build_request(build, context))
        run_request = replace(
            _run_request(build, context),
            test_definition=_mt5_test_definition(build),
        )
        run = api.execute_run(run_request)
        transformed = api.transform_evidence(
            TransformEvidenceCommandRequest(
                context, run.run_id, run.evidence_manifest, _definitions()
            )
        )
        if include_analysis:
            api.analyze_datasets(
                AnalyzeDatasetsCommandRequest(
                    context,
                    tuple(
                        DatasetInputReference(item.dataset_id, item.content_digest)
                        for item in transformed.datasets
                    ),
                    new_entity_id(AnalysisDefinitionId),
                    DefinitionVersion("visual-test-1"),
                    SchemaReferencedPayload(
                        CORE_PARAMETERS_REF,
                        {
                            "schema_name": "execution-core-analysis-parameters",
                            "schema_version": "0.1.0",
                        },
                    ),
                    new_entity_id(EnvironmentConfigurationId),
                )
            )
    return run.run_id


def _seed_run(database: Path, status: str) -> None:
    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(_successful_build())
        data_plane.publish_run(
            _run(
                status=status,
                evidence_outcome=(
                    EvidenceCollectionOutcome.CANCELLED
                    if status == "cancelled"
                    else EvidenceCollectionOutcome.COLLECTION_FAILED
                ),
            )
        )


def _seed_many_runs(database: Path, count: int) -> None:
    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(_successful_build())
        for _ in range(count):
            data_plane.publish_run(_run())


def _seed_unknown_dataset(database: Path) -> None:
    build = _successful_build()
    run = _run()
    base = _dataset(run)
    payload = SchemaReferencedPayload(
        SchemaRef(SchemaName("telemetry-envelope"), SchemaVersion(0, 1, 0)),
        {
            "schema_name": "telemetry-envelope",
            "schema_version": "0.1.0",
            "run_id": str(run.run_id),
            "stream_id": "opaque-provider-stream",
            "sequence": 0,
            "timestamp": "2026-08-12T12:00:00Z",
            "producer_namespace": "portable.fake",
            "event_type": "provider-owned-event",
            "payload_schema": "urn:ea-research-lab:schema:opaque-provider-payload:0.1.0",
            "payload": {"opaque": True},
        },
    )
    content = DatasetContent(payload)
    manifest = _plain(base.manifest.value)
    manifest["dataset_schema"] = str(payload.schema_ref)
    manifest["content_digest"] = str(content.content_digest)
    dataset = Dataset(
        content,
        base.provenance,
        SchemaReferencedPayload(base.manifest.schema_ref, manifest),
        base.created_at,
    )
    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(build)
        data_plane.publish_run(run)
        data_plane.publish_dataset(dataset)


def _run_app(database: Path) -> AppTest:
    with patch.dict(os.environ, {"EA_RESEARCH_LAB_DATABASE": str(database)}):
        return AppTest.from_file(str(APP)).run(timeout=20)


class VisualViewModelTests(unittest.TestCase):
    def test_formatting_is_explicit_and_unavailable_is_not_numeric(self) -> None:
        original_precision = getcontext().prec
        getcontext().prec = 3
        try:
            self.assertEqual(format_money(Decimal("2.63"), "USD"), "USD 2.63")
            self.assertEqual(format_percentage(Decimal("0.002630000000")), "0.263%")
            self.assertEqual(format_decimal(Decimal("1.014300000000")), "1.0143")
        finally:
            getcontext().prec = original_precision
        self.assertEqual(format_money(None, "USD"), UNAVAILABLE)
        self.assertEqual(format_percentage(None), UNAVAILABLE)

    def test_overview_uses_semantic_values_without_research_recalculation(self) -> None:
        model = build_research_overview(_run_detail(), _summary(), _analysis_detail())
        metrics = {item.label: item.value for item in model.primary_metrics}
        self.assertEqual(metrics["Net Profit"], "USD 2.63")
        self.assertEqual(metrics["Total Trades"], "135")
        self.assertEqual(metrics["Profit Factor"], "10.5")
        self.assertIn("Event-Balance Max Drawdown", metrics)
        self.assertEqual(
            tuple((item.label, item.value) for item in model.winning_losing),
            (("Winning", 43), ("Losing", 92)),
        )
        self.assertEqual(
            tuple(item.label for item in model.realized_pnl_summary),
            ("Minimum", "Median", "Mean", "Maximum"),
        )

    def test_missing_analysis_and_summary_remain_unavailable(self) -> None:
        model = build_research_overview(_run_detail("failed"), None, None)
        self.assertTrue(all(item.value == UNAVAILABLE for item in model.primary_metrics))
        self.assertEqual(model.winning_losing, ())
        self.assertEqual(model.realized_pnl_summary, ())

    def test_dataset_labels_are_exact_and_unknown_schemas_remain_generic(self) -> None:
        known = _dataset_detail()
        unknown = _dataset_detail(
            SchemaRef(SchemaName("telemetry-envelope"), SchemaVersion(0, 1, 0))
        )
        known_view = build_dataset_view(known.summary, known)
        unknown_view = build_dataset_view(unknown.summary, unknown)

        self.assertEqual(known_view.label, "Execution Summary")
        self.assertEqual(unknown_view.label, "Dataset")
        self.assertEqual(unknown_view.dataset_id, str(unknown.summary.dataset_id))
        self.assertEqual(format_digest(Sha256Digest("a" * 64)), "sha256:aaaaaaaaaaaa…")

    def test_analysis_view_exposes_only_exact_bounded_result_metrics(self) -> None:
        detail = _analysis_detail()
        labels = {str(detail.input_datasets[0].dataset_id): "Execution Summary"}
        model = build_analysis_view(detail, labels)

        self.assertEqual(model.analysis_result_id, str(detail.summary.analysis_result_id))
        self.assertEqual(model.inputs[0].label, "Execution Summary")
        self.assertEqual(model.result_digest, str(detail.summary.result_digest))
        self.assertEqual(
            {item.label for item in model.bounded_metrics},
            {
                "Net Return",
                "Win Rate",
                "Loss Rate",
                "Expected Payoff",
                "Profit Factor",
                "Average Winner",
                "Average Losing Magnitude",
                "Payoff Ratio",
                "Realized Event Count",
                "Realized PnL Minimum",
                "Realized PnL Median",
                "Realized PnL Mean",
                "Realized PnL Maximum",
                "Longest Positive Streak",
                "Longest Negative Streak",
                "Event-Balance Max Drawdown",
                "Event-Balance Max Drawdown Rate",
            },
        )
        unsupported = replace(detail, bounded_result=None)
        self.assertEqual(build_analysis_view(unsupported, labels).bounded_metrics, ())

    def test_provenance_and_evidence_models_preserve_full_audit_values(self) -> None:
        run = _run_detail()
        dataset = _dataset_detail()
        analysis = replace(
            _analysis_detail(),
            input_datasets=(
                DatasetContentReference(
                    dataset.summary.dataset_id, dataset.summary.content_digest
                ),
            ),
        )
        chain = CanonicalChainProjection(
            ProvenanceSummary(
                run.build_record_id,
                run.summary.artifact_id,
                Sha256Digest("e" * 64),
                run.summary.test_definition_revision_id,
                run.summary.run_id,
                run.evidence_history,
                analysis.input_datasets,
                analysis.summary.analysis_result_id,
            ),
            run,
            (dataset.summary,),
            analysis,
        )
        stages = build_provenance_stages(chain)
        evidence = EvidenceObjectSummary(
            run.evidence_history[-1].manifest_id,
            new_entity_id(RawEvidenceObjectId),
            "text/html",
            42,
            Sha256Digest("d" * 64),
            provider_namespace="metatrader5.strategy-tester.report",
        )
        evidence_view = build_evidence_view(evidence)

        self.assertEqual(
            tuple(item.label for item in stages),
            (
                "Build",
                "Artifact",
                "Test Definition",
                "Run",
                "Raw Evidence Manifest",
                "Dataset",
                "Analysis Result",
            ),
        )
        self.assertEqual(stages[-1].digest, str(analysis.summary.result_digest))
        self.assertEqual(evidence_view.byte_length, "42 bytes")
        self.assertEqual(evidence_view.payload_schema, UNAVAILABLE)
        self.assertFalse(hasattr(evidence_view, "content"))
        self.assertEqual(
            dict(execution_environment_fields(run))["Execution Runtime Version"],
            UNAVAILABLE,
        )

    def test_reproducibility_reasons_remain_recorded_text_not_a_score(self) -> None:
        run = replace(
            _run_detail(),
            execution_reproducibility=ReproducibilityAssessment(
                ReproducibilityLevel.BEST_EFFORT,
                (ReproducibilityReason("provider_limit", "Exact replay unavailable."),),
            ),
        )
        model = build_research_overview(run, None, None)
        self.assertEqual(model.reproducibility, "best_effort")
        self.assertEqual(model.reproducibility_reasons, ("Exact replay unavailable.",))


class VisualAppTests(unittest.TestCase):
    def test_complete_research_overview_renders_selection_metrics_and_charts(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "visual.sqlite3"
            run_id = _seed_complete(database)
            app = _run_app(database)

        self.assertEqual(list(app.exception), [])
        self.assertEqual(app.selectbox[0].value, str(run_id))
        self.assertIn("Run Overview", tuple(item.value for item in app.header))
        metric_labels = {item.label for item in app.metric}
        self.assertTrue(
            {
                "Net Profit",
                "Net Return",
                "Total Trades",
                "Win Rate",
                "Profit Factor",
                "Payoff Ratio",
                "Event-Balance Max Drawdown",
                "Event-Balance Max Drawdown Rate",
                "Build Provider",
                "Build Provider Version",
                "Build Executable Digest",
                "Execution Runtime Version",
            }.issubset(metric_labels)
        )
        values = {item.label: item.value for item in app.metric}
        self.assertEqual(values["Build Provider"], "metaeditor")
        self.assertEqual(values["Build Provider Version"], "5.0.0.6104")
        self.assertEqual(values["Execution Runtime Version"], UNAVAILABLE)
        self.assertEqual(len(app.get("vega_lite_chart")), 2)
        subheaders = {item.value for item in app.subheader}
        self.assertIn("Winning vs Losing Executions", subheaders)
        self.assertIn("Realized PnL Statistical Summary", subheaders)
        self.assertNotIn("model=1", " ".join(item.value for item in app.text))
        self.assertEqual(
            {item.label for item in app.button},
            {
                "Previous Runs",
                "Next Runs",
                "Previous Datasets",
                "Next Datasets",
                "Previous Analysis Results",
                "Next Analysis Results",
                "Previous Evidence Objects",
                "Next Evidence Objects",
            },
        )
        self.assertEqual(
            tuple(item.label for item in app.tabs),
            ("Overview", "Datasets", "Analysis", "Provenance", "Evidence"),
        )
        self.assertIn("Datasets", tuple(item.value for item in app.header))
        self.assertIn("Analysis", tuple(item.value for item in app.header))
        self.assertIn(
            "Reproducibility and Provenance",
            tuple(item.value for item in app.header),
        )
        self.assertIn(
            "Canonical provenance verified",
            tuple(item.value for item in app.success),
        )
        self.assertIn("Evidence Metadata", tuple(item.value for item in app.header))
        self.assertIn("Evidence Object", tuple(item.value for item in app.subheader))
        rendered = " ".join(
            item.value
            for family in (app.text, app.caption, app.markdown, app.code)
            for item in family
        )
        self.assertNotIn("<html", rendered.lower())
        self.assertNotIn("MA_CROSS", rendered)

    def test_dataset_selection_and_analysis_drilldown_render_bounded_metadata(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "drilldown.sqlite3"
            _seed_complete(database)
            with patch.dict(os.environ, {"EA_RESEARCH_LAB_DATABASE": str(database)}):
                app = AppTest.from_file(str(APP)).run(timeout=20)
                self.assertGreaterEqual(len(app.selectbox[1].options), 3)
                original = app.selectbox[1].value
                selected = app.selectbox[1].options[1]
                app.selectbox[1].select(selected).run(timeout=20)

        self.assertEqual(list(app.exception), [])
        self.assertNotEqual(app.selectbox[1].value, original)
        self.assertTrue(selected.endswith(app.selectbox[1].value))
        self.assertTrue(any("dataset_" in item.value for item in app.code))
        self.assertTrue(any("analysisresult_" in item.value for item in app.code))
        self.assertIn("Analysis Inputs", tuple(item.value for item in app.subheader))
        self.assertIn(
            "Bounded Result Metrics", tuple(item.value for item in app.subheader)
        )

    def test_empty_and_safe_error_states_do_not_expose_internals(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            empty = Path(name) / "empty.sqlite3"
            with SqliteDataPlane(empty):
                pass
            empty_app = _run_app(empty)
            missing_app = _run_app(Path(name) / "missing.sqlite3")

        self.assertEqual(list(empty_app.exception), [])
        self.assertIn(
            "No research Runs are available on this page.",
            tuple(item.value for item in empty_app.info),
        )
        self.assertEqual(list(missing_app.exception), [])
        message = missing_app.error[0].value
        self.assertEqual(message, "Research data could not be loaded safely.")
        self.assertNotIn("sqlite", message.lower())

    def test_failed_and_cancelled_runs_render_as_research_states(self) -> None:
        for status in ("failed", "cancelled"):
            with self.subTest(status=status), tempfile.TemporaryDirectory() as name:
                database = Path(name) / f"{status}.sqlite3"
                _seed_run(database, status)
                app = _run_app(database)
                self.assertEqual(list(app.exception), [])
                values = {item.label: item.value for item in app.metric}
                self.assertEqual(values["Run Status"], status)
                self.assertEqual(values["Net Profit"], UNAVAILABLE)
                self.assertGreaterEqual(
                    sum(item.value == UNAVAILABLE for item in app.info), 2
                )

    def test_run_without_analysis_preserves_available_execution_summary(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "without-analysis.sqlite3"
            _seed_complete(database, include_analysis=False)
            app = _run_app(database)
        values = {item.label: item.value for item in app.metric}
        self.assertEqual(values["Run Status"], "completed")
        self.assertEqual(values["Net Profit"], "USD 0.38")
        self.assertEqual(values["Total Trades"], "2")
        self.assertEqual(values["Net Return"], UNAVAILABLE)

    def test_unknown_dataset_and_missing_analysis_are_safe_bounded_states(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "unknown-dataset.sqlite3"
            _seed_unknown_dataset(database)
            app = _run_app(database)

        self.assertEqual(list(app.exception), [])
        self.assertTrue(
            any(option.startswith("Dataset") for option in app.selectbox[1].options)
        )
        self.assertIn("No Analysis Results", tuple(item.value for item in app.info))
        rendered = " ".join(
            item.value
            for family in (app.text, app.caption, app.markdown, app.code)
            for item in family
        )
        self.assertNotIn("provider-owned-event", rendered)

    def test_provenance_failure_is_safe_and_never_marked_verified(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "provenance-failure.sqlite3"
            _seed_complete(database)
            with patch.object(
                PlatformApi,
                "get_canonical_chain",
                side_effect=RuntimeError("internal provenance detail"),
            ):
                app = _run_app(database)

        self.assertEqual(list(app.exception), [])
        self.assertIn(
            "Canonical provenance could not be verified safely.",
            tuple(item.value for item in app.error),
        )
        self.assertNotIn(
            "Canonical provenance verified",
            tuple(item.value for item in app.success),
        )
        self.assertNotIn(
            "internal provenance detail",
            " ".join(item.value for item in app.error),
        )

    def test_evidence_collection_outcome_remains_independent_from_run_status(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "collection-failed.sqlite3"
            _seed_run(database, "completed")
            app = _run_app(database)
        values = {item.label: item.value for item in app.metric}
        self.assertEqual(values["Run Status"], "completed")
        self.assertEqual(values["Evidence Collection"], "collection_failed")

    def test_cursor_navigation_keeps_only_presentation_state(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "paged.sqlite3"
            _seed_many_runs(database, 21)
            with patch.dict(
                os.environ, {"EA_RESEARCH_LAB_DATABASE": str(database)}
            ):
                app = AppTest.from_file(str(APP)).run(timeout=20)
                run_buttons = {item.label: item for item in app.button}
                self.assertTrue(run_buttons["Previous Runs"].disabled)
                self.assertFalse(run_buttons["Next Runs"].disabled)
                run_buttons["Next Runs"].click().run(timeout=20)
                app.run(timeout=20)
                run_buttons = {item.label: item for item in app.button}
                self.assertFalse(run_buttons["Previous Runs"].disabled)
                self.assertTrue(run_buttons["Next Runs"].disabled)
                self.assertIn(
                    "1 Run(s) on this bounded page",
                    tuple(item.value for item in app.caption),
                )


if __name__ == "__main__":
    unittest.main()
