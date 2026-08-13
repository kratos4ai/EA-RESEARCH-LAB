from __future__ import annotations

import copy
import hashlib
import logging
import tempfile
import unittest
from pathlib import Path

from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.data_plane import TEST_DEFINITION_REF, DurableRun
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_commands import (
    AnalyzeDatasetsCommandRequest,
    DatasetInputReference,
    TransformEvidenceCommandRequest,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    EnvironmentConfigurationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
)
from ea_research_lab.infrastructure.composition import compose_read_only_platform
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from tests.test_platform_commands import (
    _build_request,
    _context,
    _definitions,
    _run_request,
)
from tests.test_research_query import _seed
from tests.test_sqlite_data_plane_chain import (
    _dataset,
    _payload,
    _plain,
    _run,
    _successful_build,
)
from tests.test_mt5_strategy_tester import _execution_document


def _logger(name: str) -> logging.Logger:
    logger = logging.Logger(name)
    logger.addHandler(logging.NullHandler())
    return logger


class ReadOnlyCompositionTests(unittest.TestCase):
    def test_exact_provider_configuration_is_available_as_neutral_context(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "research.sqlite3"
            build = _successful_build()
            original = _run()
            definition = copy.deepcopy(_plain(original.test_definition.value))
            definition["execution_configuration"] = {
                "schema_ref": (
                    "urn:ea-research-lab:schema:"
                    "mt5-strategy-tester-execution:0.1.0"
                ),
                "value": _execution_document(),
            }
            run = DurableRun(
                _payload(TEST_DEFINITION_REF, definition),
                original.run_manifest,
                original.evidence_history,
            )
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                data_plane.publish_run(run)
                data_plane.publish_dataset(_dataset(run))

            with compose_read_only_platform(
                database, _logger("experiment-context-test")
            ) as api:
                detail = api.get_research_run(_context(), run.run_id)
                context = detail.experiment_context

            self.assertEqual(context.instrument, "EURUSD")
            self.assertEqual(context.timeframe, "M1")
            self.assertFalse(hasattr(context, "modeling_mode"))
            self.assertEqual(detail.provider_runtimes[0].role, "build")
            self.assertEqual(
                detail.provider_runtimes[0].provider_namespace, "metaeditor"
            )
            self.assertEqual(detail.provider_runtimes[0].version, "5.0.0.6104")

    def test_queries_work_and_all_commands_fail_without_database_mutation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "research.sqlite3"
            runs, datasets, _ = _seed(database)
            before = hashlib.sha256(database.read_bytes()).digest()
            context = _context()
            build = _successful_build()

            with compose_read_only_platform(
                database, _logger("read-only-platform-test")
            ) as api:
                detail = api.get_research_run(context, runs[0].run_id)
                build_result = api.build_artifact(_build_request(build, context))
                run_result = api.execute_run(_run_request(build, context))
                transform_result = api.transform_evidence(
                    TransformEvidenceCommandRequest(
                        context,
                        runs[0].run_id,
                        runs[0].evidence_history[-1].reference,
                        _definitions(),
                    )
                )
                analysis_result = api.analyze_datasets(
                    AnalyzeDatasetsCommandRequest(
                        context,
                        (
                            DatasetInputReference(
                                datasets[0].provenance.dataset_id,
                                datasets[0].content.content_digest,
                            ),
                        ),
                        new_entity_id(AnalysisDefinitionId),
                        DefinitionVersion("read-only-test"),
                        SchemaReferencedPayload(
                            SchemaRef(
                                SchemaName("execution-core-analysis-parameters"),
                                SchemaVersion(0, 1, 0),
                            ),
                            {
                                "schema_name": "execution-core-analysis-parameters",
                                "schema_version": "0.1.0",
                            },
                        ),
                        new_entity_id(EnvironmentConfigurationId),
                    )
                )

            self.assertEqual(detail.summary.run_id, runs[0].run_id)
            self.assertEqual(
                {result.failure.code for result in (
                    build_result,
                    run_result,
                    transform_result,
                    analysis_result,
                )},
                {ApplicationErrorCode.INVALID_CONFIGURATION},
            )
            self.assertFalse(build_result.published)
            self.assertFalse(run_result.published)
            self.assertEqual(transform_result.datasets, ())
            self.assertFalse(analysis_result.published)
            self.assertEqual(hashlib.sha256(database.read_bytes()).digest(), before)


if __name__ == "__main__":
    unittest.main()
