from __future__ import annotations

import tempfile
import unittest
from pathlib import Path

from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.platform_commands import (
    AnalyzeDatasetsCommandRequest,
    DatasetInputReference,
    TransformEvidenceCommandRequest,
)
from ea_research_lab.application.platform_queries import PlatformQueries
from ea_research_lab.application.data_plane import DataPlaneError
from ea_research_lab.application.research_query import PageRequest
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    EnvironmentConfigurationId,
    RunId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.semantic import CanonicalChainProjection
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from ea_research_lab.infrastructure.sqlite_research_query import SqliteResearchQuery
from tests.test_platform_commands import (
    _Provider,
    _build_request,
    _build_result,
    _commands,
    _context,
    _definitions,
    _known_report_bytes,
    _run_request,
    _successful_build,
)
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderVerdict,
)


CORE_PARAMETERS_REF = SchemaRef(
    SchemaName("execution-core-analysis-parameters"), SchemaVersion(0, 1, 0)
)


class PlatformApiTests(unittest.TestCase):
    def test_portable_command_to_query_vertical_uses_only_platform_api(self) -> None:
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
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "platform.sqlite3"
            with (
                SqliteDataPlane(database) as data_plane,
                SqliteResearchQuery(database) as discovery,
            ):
                commands, records = _commands(
                    data_plane, lambda request: _build_result(build), provider
                )
                api = PlatformApi(
                    commands,
                    PlatformQueries(data_plane, discovery),
                    commands._logger,
                )
                context = _context()

                built = api.build_artifact(_build_request(build, context))
                run = api.execute_run(_run_request(build, context))
                transformed = api.transform_evidence(
                    TransformEvidenceCommandRequest(
                        context,
                        run.run_id,
                        run.evidence_manifest,
                        _definitions(),
                    )
                )
                analyzed = api.analyze_datasets(
                    AnalyzeDatasetsCommandRequest(
                        context,
                        tuple(
                            DatasetInputReference(
                                item.dataset_id, item.content_digest
                            )
                            for item in transformed.datasets
                        ),
                        new_entity_id(AnalysisDefinitionId),
                        DefinitionVersion("phase07-core-1"),
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

                runs = api.list_research_runs(context, PageRequest(1))
                run_detail = api.get_research_run(context, run.run_id)
                datasets = api.list_run_datasets(
                    context, run.run_id, PageRequest(3)
                )
                dataset_detail = api.get_dataset(
                    context, transformed.datasets[0].dataset_id
                )
                analyses = api.list_dataset_analyses(
                    context, transformed.datasets[0].dataset_id, PageRequest(1)
                )
                analysis_detail = api.get_analysis(
                    context, analyzed.analysis_result_id
                )
                chain = api.get_canonical_chain(
                    context,
                    built.build_record_id,
                    run.run_id,
                    analyzed.analysis_result_id,
                )
                with self.assertRaises(DataPlaneError):
                    api.get_research_run(context, new_entity_id(RunId))

        self.assertTrue(built.published)
        self.assertTrue(run.published)
        self.assertTrue(all(item.published for item in transformed.datasets))
        self.assertTrue(analyzed.published)
        self.assertEqual(runs.items[0].run_id, run.run_id)
        self.assertEqual(run_detail.summary.run_id, run.run_id)
        self.assertEqual(len(datasets.items), 3)
        self.assertEqual(
            dataset_detail.summary.dataset_id, transformed.datasets[0].dataset_id
        )
        self.assertEqual(
            analyses.items[0].analysis_result_id, analyzed.analysis_result_id
        )
        self.assertIsNotNone(analysis_detail.bounded_result)
        self.assertIsInstance(chain, CanonicalChainProjection)
        events = tuple(record.event_name for record in records.records)
        self.assertIn("platform.query.get_canonical_chain.started", events)
        self.assertIn("platform.query.get_canonical_chain.completed", events)
        self.assertIn("platform.query.get_research_run.failed", events)
        query_record = next(
            record
            for record in records.records
            if record.event_name == "platform.query.get_canonical_chain.started"
        )
        self.assertEqual(query_record.request_id, str(context.request_id))
        self.assertEqual(query_record.caller_id, context.caller_id)
        serialized = " ".join(str(record.__dict__) for record in records.records)
        for forbidden in (
            "sqlite3",
            "select ",
            "strategy-tester-report",
            "input_content_digests",
        ):
            self.assertNotIn(forbidden, serialized.lower())


if __name__ == "__main__":
    unittest.main()
