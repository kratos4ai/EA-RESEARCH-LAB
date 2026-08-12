from __future__ import annotations

import unittest
from types import SimpleNamespace
from unittest.mock import Mock

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.research_query import Page
from ea_research_lab.domain.evidence import EvidenceCollectionOutcome
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    BuildRecordId,
    DatasetId,
    RequestId,
    RunId,
)
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaName,
    SchemaRef,
    SchemaVersion,
)
from tools.inspect_research_checkpoint import render_report


class InspectResearchCheckpointTests(unittest.TestCase):
    def test_report_uses_the_complete_query_navigation_and_marks_gaps(self) -> None:
        api = Mock(spec=PlatformApi)
        context = RequestContext(new_entity_id(RequestId), "operator-test")
        build_id = new_entity_id(BuildRecordId)
        run_id = new_entity_id(RunId)
        dataset_ids = tuple(new_entity_id(DatasetId) for _ in range(3))
        analysis_id = new_entity_id(AnalysisResultId)
        run_summary = SimpleNamespace(
            run_id=run_id,
            status="completed",
            created_at="2026-08-12T00:00:00Z",
            started_at="2026-08-12T00:00:01Z",
            finished_at="2026-08-12T00:00:02Z",
            artifact_id="artifact_test",
            test_definition_revision_id="testrev_test",
            evidence_manifest=SimpleNamespace(
                manifest_id="rawmanifest_test",
                content_digest="a" * 64,
            ),
            evidence_outcome=EvidenceCollectionOutcome.COMPLETED,
        )
        run = SimpleNamespace(
            summary=run_summary,
            environment_configuration_id="envcfg_test",
            execution_reproducibility=ReproducibilityAssessment(
                ReproducibilityLevel.BEST_EFFORT,
                (
                    ReproducibilityReason(
                        "provider_replay_not_guaranteed",
                        "The provider does not guarantee replay.",
                    ),
                ),
            ),
            evidence_history=(run_summary.evidence_manifest,),
        )
        dataset_summaries = tuple(
            SimpleNamespace(
                dataset_id=item,
                content_schema=f"schema-{index}",
                content_digest=str(index) * 64,
            )
            for index, item in enumerate(dataset_ids, start=1)
        )
        datasets = tuple(SimpleNamespace(summary=item) for item in dataset_summaries)
        analysis_summary = SimpleNamespace(
            analysis_result_id=analysis_id,
            result_schema="execution-core-analysis-result/0.1.0",
            result_digest="b" * 64,
            analysis_definition_id="analysisdef_test",
            analysis_version="1",
        )
        analysis = SimpleNamespace(
            summary=analysis_summary,
            analysis_parameters_schema="parameters/0.1.0",
            computation_environment_id="envcfg_analysis",
            bounded_result=SimpleNamespace(
                schema_ref=SchemaRef(
                    SchemaName("execution-core-analysis-result"),
                    SchemaVersion(0, 1, 0),
                ),
                value={
                    "aggregate_metrics": {
                        "net_return": {"value": "0.100000000000"}
                    }
                },
            ),
        )
        provenance = SimpleNamespace(
            build_record_id=build_id,
            artifact_id="artifact_test",
            test_definition_revision_id="testrev_test",
            run_id=run_id,
            evidence_manifests=(run_summary.evidence_manifest,),
            datasets=tuple(
                SimpleNamespace(
                    dataset_id=item.dataset_id,
                    content_digest=item.content_digest,
                )
                for item in dataset_summaries
            ),
            analysis_result_id=analysis_id,
        )
        api.list_research_runs.return_value = Page((run_summary,), None)
        api.get_research_run.return_value = run
        api.list_run_datasets.return_value = Page(dataset_summaries, None)
        api.get_dataset.side_effect = datasets
        api.list_dataset_analyses.return_value = Page((analysis_summary,), None)
        api.get_analysis.return_value = analysis
        api.get_canonical_chain.return_value = SimpleNamespace(provenance=provenance)

        report = render_report(api, context, build_id)

        self.assertIn("| Net return | AVAILABLE | 0.100000000000 |", report)
        self.assertIn(
            "| Total trades | NOT AVAILABLE THROUGH PLATFORM API | not exposed |",
            report,
        )
        self.assertIn("`MA_CROSS`: NOT AVAILABLE THROUGH PLATFORM API", report)
        api.list_research_runs.assert_called_once()
        api.get_research_run.assert_called_once_with(context, run_id)
        api.list_run_datasets.assert_called_once()
        self.assertEqual(api.get_dataset.call_count, 3)
        self.assertEqual(api.list_dataset_analyses.call_count, 3)
        api.get_analysis.assert_called_once_with(context, analysis_id)
        api.get_canonical_chain.assert_called_once_with(
            context, build_id, run_id, analysis_id
        )
        for command in (
            "build_artifact",
            "execute_run",
            "transform_evidence",
            "analyze_datasets",
        ):
            getattr(api, command).assert_not_called()

    def test_ambiguous_run_requires_an_explicit_identity(self) -> None:
        api = Mock(spec=PlatformApi)
        api.list_research_runs.return_value = Page(
            (
                SimpleNamespace(run_id=new_entity_id(RunId)),
                SimpleNamespace(run_id=new_entity_id(RunId)),
            ),
            None,
        )
        with self.assertRaisesRegex(ValueError, "--run-id"):
            render_report(
                api,
                RequestContext(new_entity_id(RequestId)),
                new_entity_id(BuildRecordId),
            )
        api.get_research_run.assert_not_called()


if __name__ == "__main__":
    unittest.main()
