from __future__ import annotations

import json
import logging
import unittest
from datetime import timedelta
from pathlib import Path

from ea_research_lab.application.analysis import analyze_execution_core
from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
    BuildWorkflowResult,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.data_plane import DataPlaneError, DurableBuild, DurableRun
from ea_research_lab.application.dataset import TransformationRequest, transform_dataset
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.execution import execute_run
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_commands import (
    AnalyzeDatasetsCommandRequest,
    DatasetInputReference,
    ExecuteRunCommandRequest,
    PlatformCommands,
    TransformEvidenceCommandRequest,
    TransformationDefinition,
)
from ea_research_lab.domain.build import (
    BuildInputScope,
    BuildOutcome,
    BuildProviderObservation,
)
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderObservation,
    ExecutionProviderVerdict,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import EvidenceProvenance, SchemaReferencedPayload
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    ReproducibilityLevel,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    SourceRevision,
)
from ea_research_lab.infrastructure.mt5_report import (
    Mt5AccountBalanceEventSeriesTransformer,
    Mt5RealizedExecutionEventSeriesTransformer,
    Mt5ReportTransformer,
)
from tests.test_sqlite_data_plane import (
    CONFIGURATION_REF,
    EVIDENCE_REF,
    _failed_build,
    _fixture,
    _successful_build,
)
from tests.test_sqlite_data_plane_chain import _dataset, _run


FIXTURES = Path(__file__).parent / "fixtures"
CORE_PARAMETERS_REF = SchemaRef(
    SchemaName("execution-core-analysis-parameters"), SchemaVersion(0, 1, 0)
)


class _MemoryDataPlane:
    def __init__(self) -> None:
        self.builds = {}
        self.runs = {}
        self.datasets = {}
        self.analyses = {}
        self.published: list[str] = []
        self.fail_on: str | None = None

    def _publish(self, kind: str, key, value) -> None:
        if self.fail_on == kind:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable publication failed.",
            )
        getattr(self, f"{kind}s")[key] = value
        self.published.append(kind)

    def publish_build(self, build) -> None:
        self._publish("build", build.build_record_id, build)

    def load_build(self, build_record_id):
        return self.builds[build_record_id]

    def publish_run(self, run) -> None:
        self._publish("run", run.run_id, run)

    def load_run(self, run_id):
        return self.runs[run_id]

    def publish_dataset(self, dataset) -> None:
        self._publish("dataset", dataset.provenance.dataset_id, dataset)

    def load_dataset(self, dataset_id):
        return self.datasets[dataset_id]

    def publish_analysis(self, result) -> None:
        if self.fail_on == "analysis":
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable publication failed.",
            )
        self.analyses[result.provenance.analysis_result_id] = result
        self.published.append("analysis")

    def load_analysis(self, result_id):
        return self.analyses[result_id]


class _Provider:
    def __init__(self, verdict: ExecutionProviderVerdict, outputs=()) -> None:
        self.verdict = verdict
        self.outputs = tuple(outputs)
        self.requests = []

    def execute(self, request):
        self.requests.append(request)
        return ExecutionProviderObservation(
            self.verdict,
            SchemaReferencedPayload(
                SchemaRef(
                    SchemaName("execution-provider-evidence"),
                    SchemaVersion(0, 1, 0),
                ),
                {"bounded": True},
            ),
            self.outputs,
        )


class _Records(logging.Handler):
    def __init__(self) -> None:
        super().__init__()
        self.records = []

    def emit(self, record) -> None:
        self.records.append(record)


def _context() -> RequestContext:
    return RequestContext(new_entity_id(RequestId), "portable-client")


def _payload(name: str, value: dict[str, object]) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(
        SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0)), value
    )


def _build_request(build: DurableBuild, context: RequestContext) -> BuildRequest:
    return BuildRequest(
        context,
        build.build_record_id,
        SourceRevision("git", "ea-research-lab", "revision", True),
        BuildSourceSpecification(
            BuildSourceInput(
                BuildInputScope.WORKSPACE, "Experts/Disposable.mq5", b"source"
            )
        ),
        EnvironmentConfigurationId.parse(
            build.build_record.value["build_configuration_id"]
        ),
        SchemaReferencedPayload(
            CONFIGURATION_REF,
            _fixture("metaeditor-build-configuration-v0.2.0.json"),
        ),
        timedelta(seconds=30),
    )


def _build_result(build: DurableBuild) -> BuildWorkflowResult:
    provider = build.build_record.value.get("provider_evidence")
    observation = (
        None
        if provider is None
        else BuildProviderObservation(
            SchemaReferencedPayload(EVIDENCE_REF, provider["value"]),
            build.artifact_acceptance is not None,
        )
    )
    failure = (
        None
        if build.outcome is BuildOutcome.SUCCEEDED
        else ApplicationError(
            ApplicationErrorCode.BUILD_PROVIDER_FAILED, "Build attempt failed."
        )
    )
    return BuildWorkflowResult(
        build.outcome,
        build.build_record,
        build.build_input_manifest,
        observation,
        build.artifact_acceptance,
        failure,
    )


def _test_definition(build: DurableBuild) -> SchemaReferencedPayload:
    return _payload(
        "test-definition",
        {
            "schema_name": "test-definition",
            "schema_version": "0.1.0",
            "test_definition_id": str(new_entity_id(TestDefinitionId)),
            "test_definition_revision_id": str(
                new_entity_id(TestDefinitionRevisionId)
            ),
            "artifact_id": str(build.artifact_acceptance.artifact.artifact_id),
            "execution_configuration": {
                "schema_ref": "urn:ea-research-lab:schema:example-execution:0.1.0",
                "value": {"opaque": True},
            },
            "sut_inputs": {
                "schema_ref": "urn:ea-research-lab:schema:example-inputs:0.1.0",
                "value": {},
            },
        },
    )


def _run_request(
    build: DurableBuild, context: RequestContext
) -> ExecuteRunCommandRequest:
    return ExecuteRunCommandRequest(
        context,
        new_entity_id(RunId),
        build.build_record_id,
        build.artifact_acceptance.artifact.artifact_id,
        _test_definition(build),
        new_entity_id(EnvironmentConfigurationId),
        _payload("execution-environment", {"captured": True}),
        timedelta(seconds=30),
        ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
    )


def _definitions():
    return tuple(
        TransformationDefinition(
            new_entity_id(TransformationId), DefinitionVersion(f"phase07-{index}")
        )
        for index in range(3)
    )


def _known_report_bytes() -> bytes:
    source = (
        FIXTURES / "mt5" / "strategy-tester-report-known-activity.html"
    ).read_text(encoding="utf-8")
    return b"\xff\xfe" + source.encode("utf-16le")


def _logger():
    logger = logging.Logger(f"platform-commands-{id(object())}")
    records = _Records()
    logger.addHandler(records)
    return logger, records


def _commands(data_plane, build_workflow, provider):
    logger, records = _logger()
    commands = PlatformCommands(
        data_plane,
        build_workflow,
        lambda request, reproducibility: execute_run(
            provider, request, reproducibility
        ),
        _transformation_workflow,
        analyze_execution_core,
        logger,
    )
    return commands, records


def _transformation_workflow(context, evidence, definitions):
    transformers = (
        Mt5ReportTransformer(),
        Mt5RealizedExecutionEventSeriesTransformer(),
        Mt5AccountBalanceEventSeriesTransformer(),
    )
    return tuple(
        transform_dataset(
            transformer,
            TransformationRequest(
                context,
                EvidenceProvenance(evidence.manifest, evidence.reference),
                evidence.raw_evidence,
                definition.transformation_id,
                definition.version,
                definition.parameters,
            ),
        )
        for transformer, definition in zip(transformers, definitions, strict=True)
    )


class PlatformCommandTests(unittest.TestCase):
    def test_successful_and_failed_build_outcomes_are_published_commands(self) -> None:
        for build in (_successful_build(), _failed_build(with_input=True)):
            with self.subTest(outcome=build.outcome):
                data_plane = _MemoryDataPlane()
                context = _context()
                seen = []
                commands, _ = _commands(
                    data_plane,
                    lambda request: seen.append(request) or _build_result(build),
                    _Provider(ExecutionProviderVerdict.COMPLETED),
                )
                result = commands.build_artifact(_build_request(build, context))

                self.assertEqual(seen[0].context, context)
                self.assertEqual(result.outcome, build.outcome)
                self.assertTrue(result.published)
                self.assertIsNone(result.failure)
                self.assertEqual(data_plane.builds[build.build_record_id], build)
                self.assertEqual(
                    result.artifact_id is not None,
                    build.outcome is BuildOutcome.SUCCEEDED,
                )

    def test_build_publication_failure_is_safe_and_not_success(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        data_plane.fail_on = "build"
        commands, records = _commands(
            data_plane,
            lambda request: _build_result(build),
            _Provider(ExecutionProviderVerdict.COMPLETED),
        )
        result = commands.build_artifact(_build_request(build, _context()))

        self.assertFalse(result.published)
        self.assertEqual(result.outcome, BuildOutcome.SUCCEEDED)
        self.assertIsNotNone(result.artifact_id)
        self.assertEqual(result.failure.code, ApplicationErrorCode.DATA_PLANE_FAILED)
        self.assertEqual(records.records[-1].error_code, "data_plane_failed")

    def test_run_outcomes_and_evidence_remain_research_facts(self) -> None:
        cases = (
            (ExecutionProviderVerdict.COMPLETED, "completed", "completed"),
            (ExecutionProviderVerdict.FAILED, "failed", "failed"),
            (ExecutionProviderVerdict.CANCELLED, "cancelled", "cancelled"),
        )
        for verdict, status, evidence_outcome in cases:
            with self.subTest(verdict=verdict):
                build = _successful_build()
                data_plane = _MemoryDataPlane()
                data_plane.builds[build.build_record_id] = build
                context = _context()
                provider = _Provider(
                    verdict,
                    (
                        CapturedExecutionOutput(
                            b"bounded evidence",
                            "text/plain",
                            provider_namespace="portable.fake",
                        ),
                    ),
                )
                commands, _ = _commands(
                    data_plane, lambda request: _build_result(build), provider
                )
                request = _run_request(build, context)
                result = commands.execute_run(request)

                self.assertEqual(provider.requests[0].context, context)
                self.assertEqual(result.status, status)
                self.assertEqual(result.evidence_outcome.value, evidence_outcome)
                self.assertTrue(result.published)
                self.assertIsNone(result.failure)
                self.assertIn(request.run_id, data_plane.runs)

    def test_run_publication_failure_is_safe_and_not_success(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        data_plane.builds[build.build_record_id] = build
        data_plane.fail_on = "run"
        commands, _ = _commands(
            data_plane,
            lambda request: _build_result(build),
            _Provider(ExecutionProviderVerdict.COMPLETED),
        )
        result = commands.execute_run(_run_request(build, _context()))

        self.assertFalse(result.published)
        self.assertEqual(result.status, "completed")
        self.assertIsNotNone(result.evidence_manifest)
        self.assertEqual(result.failure.code, ApplicationErrorCode.DATA_PLANE_FAILED)

    def test_transform_publishes_three_bounded_deterministic_references(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        data_plane.builds[build.build_record_id] = build
        report = _known_report_bytes()
        provider = _Provider(
            ExecutionProviderVerdict.COMPLETED,
            (
                CapturedExecutionOutput(
                    report,
                    "text/html",
                    provider_namespace="metatrader5.strategy-tester.report",
                ),
            ),
        )
        commands, _ = _commands(
            data_plane, lambda request: _build_result(build), provider
        )
        run_result = commands.execute_run(_run_request(build, _context()))
        request = TransformEvidenceCommandRequest(
            _context(),
            run_result.run_id,
            run_result.evidence_manifest,
            _definitions(),
        )
        result = commands.transform_evidence(request)

        self.assertIsNone(result.failure)
        self.assertEqual(
            tuple(str(item.content_schema.name) for item in result.datasets),
            (
                "execution-summary",
                "realized-execution-event-series",
                "account-balance-event-series",
            ),
        )
        self.assertEqual(len(data_plane.datasets), 3)
        self.assertTrue(all(item.published for item in result.datasets))
        self.assertFalse(hasattr(result.datasets[0], "content"))

    def test_transform_publication_failure_preserves_prior_publications(self) -> None:
        class SecondPublicationFails(_MemoryDataPlane):
            def publish_dataset(self, dataset) -> None:
                if len(self.datasets) == 1:
                    raise DataPlaneError(
                        ApplicationErrorCode.DATA_PLANE_FAILED,
                        "Durable publication failed.",
                    )
                super().publish_dataset(dataset)

        build = _successful_build()
        data_plane = SecondPublicationFails()
        data_plane.builds[build.build_record_id] = build
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
        commands, _ = _commands(
            data_plane, lambda request: _build_result(build), provider
        )
        run = commands.execute_run(_run_request(build, _context()))
        result = commands.transform_evidence(
            TransformEvidenceCommandRequest(
                _context(), run.run_id, run.evidence_manifest, _definitions()
            )
        )

        self.assertEqual(result.failure.code, ApplicationErrorCode.DATA_PLANE_FAILED)
        self.assertEqual(len(data_plane.datasets), 1)
        self.assertEqual(len(result.datasets), 3)
        self.assertEqual(
            tuple(item.published for item in result.datasets),
            (True, False, False),
        )

    def test_analysis_reuses_core_and_publishes_only_bounded_reference(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        data_plane.builds[build.build_record_id] = build
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
        calls = []
        logger, _ = _logger()

        def analysis_workflow(request):
            calls.append(request)
            return analyze_execution_core(request)

        commands = PlatformCommands(
            data_plane,
            lambda request: _build_result(build),
            lambda request, reproducibility: execute_run(
                provider, request, reproducibility
            ),
            _transformation_workflow,
            analysis_workflow,
            logger,
        )
        run = commands.execute_run(_run_request(build, _context()))
        transformed = commands.transform_evidence(
            TransformEvidenceCommandRequest(
                _context(), run.run_id, run.evidence_manifest, _definitions()
            )
        )
        request = AnalyzeDatasetsCommandRequest(
            _context(),
            tuple(
                DatasetInputReference(item.dataset_id, item.content_digest)
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
        result = commands.analyze_datasets(request)

        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0].context, request.context)
        self.assertTrue(result.published)
        self.assertIsNone(result.failure)
        self.assertIn(result.analysis_result_id, data_plane.analyses)
        self.assertFalse(hasattr(result, "result"))

        data_plane.fail_on = "analysis"
        failed_publication = commands.analyze_datasets(request)
        self.assertFalse(failed_publication.published)
        self.assertIsNotNone(failed_publication.analysis_result_id)
        self.assertIsNotNone(failed_publication.result_digest)
        self.assertEqual(
            failed_publication.failure.code,
            ApplicationErrorCode.DATA_PLANE_FAILED,
        )

    def test_analysis_digest_mismatch_fails_before_analysis(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        data_plane.builds[build.build_record_id] = build
        commands, _ = _commands(
            data_plane,
            lambda request: _build_result(build),
            _Provider(ExecutionProviderVerdict.COMPLETED),
        )
        dataset = _dataset(_run())
        data_plane.datasets[dataset.provenance.dataset_id] = dataset
        request = AnalyzeDatasetsCommandRequest(
            _context(),
            (DatasetInputReference(dataset.provenance.dataset_id, type(dataset.content.content_digest)("f" * 64)),),
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
        result = commands.analyze_datasets(request)

        self.assertFalse(result.published)
        self.assertEqual(result.failure.code, ApplicationErrorCode.INVALID_PROVENANCE)

    def test_audit_records_only_safe_boundary_facts(self) -> None:
        build = _successful_build()
        data_plane = _MemoryDataPlane()
        commands, records = _commands(
            data_plane,
            lambda request: _build_result(build),
            _Provider(ExecutionProviderVerdict.COMPLETED),
        )
        request = _build_request(build, _context())
        commands.build_artifact(request)

        self.assertEqual(len(records.records), 2)
        self.assertEqual(records.records[0].request_id, str(request.context.request_id))
        self.assertEqual(records.records[0].caller_id, "portable-client")
        self.assertEqual(
            records.records[-1].event_name,
            "platform.command.build_artifact.completed",
        )
        serialized = " ".join(str(record.__dict__) for record in records.records)
        for forbidden in ("source", "sqlite", "select ", "raw evidence"):
            self.assertNotIn(forbidden, serialized.lower())


if __name__ == "__main__":
    unittest.main()
