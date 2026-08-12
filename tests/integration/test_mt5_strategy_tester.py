from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from unittest.mock import patch

import ea_research_lab.infrastructure.mt5_strategy_tester as mt5_adapter
from ea_research_lab.application.analysis import (
    AnalysisRequest,
    analyze_execution_core,
    analyze_execution_summaries,
)
from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
    execute_build,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.data_plane import (
    CanonicalChainRequest,
    DurableBuild,
    DurableRun,
    reconstruct_canonical_chain,
)
from ea_research_lab.application.dataset import (
    TransformationRequest,
    transform_dataset,
)
from ea_research_lab.application.execution import ExecutionRequest, execute_run
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import AcceptedArtifact, BuildInputScope, BuildOutcome
from ea_research_lab.domain.evidence import EvidenceCollectionOutcome
from ea_research_lab.domain.execution import ExecutionProviderVerdict
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
    EvidenceProvenance,
    SchemaReferencedPayload,
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
    SourceRevision,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.metaeditor import (
    MetaEditorConfiguration,
    execute_metaeditor_build_attempt,
)
from ea_research_lab.infrastructure.mt5_report import (
    Mt5AccountBalanceEventSeriesTransformer,
    Mt5RealizedExecutionEventSeriesTransformer,
    Mt5ReportTransformer,
)
from ea_research_lab.infrastructure.mt5_strategy_tester import (
    Mt5StrategyTesterConfiguration,
    Mt5StrategyTesterProvider,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane


_TERMINAL = os.environ.get("EA_RESEARCH_LAB_MT5_TERMINAL")
_DATA_ROOT = os.environ.get("EA_RESEARCH_LAB_MT5_DATA_ROOT")
_ARTIFACT = os.environ.get("EA_RESEARCH_LAB_MT5_ARTIFACT")
_METAEDITOR = os.environ.get("EA_RESEARCH_LAB_METAEDITOR")
_ENVIRONMENT_KEYS = (
    "SystemRoot",
    "WINDIR",
    "PATH",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
)


def _ref(name: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0))


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@unittest.skipUnless(
    os.environ.get("EA_RESEARCH_LAB_MT5_INTEGRATION") == "1",
    "controlled MT5 integration is not enabled",
)
class Mt5StrategyTesterIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("EA_RESEARCH_LAB_MT5_CONTROLLED_ARTIFACT") != "1":
            raise unittest.SkipTest("controlled no-trading Artifact is not acknowledged")
        if not _TERMINAL or not _DATA_ROOT or not _ARTIFACT:
            raise unittest.SkipTest(
                "terminal, data root, and controlled Artifact are not configured"
            )
        cls.terminal = Path(_TERMINAL)
        cls.data_root = Path(_DATA_ROOT)
        cls.artifact_path = Path(_ARTIFACT)
        if (
            not cls.terminal.is_file()
            or not cls.data_root.is_dir()
            or not cls.artifact_path.is_file()
        ):
            raise unittest.SkipTest("configured integration files are unavailable")
        if cls._related_processes_present():
            raise unittest.SkipTest("existing MT5 processes make ownership ambiguous")

    @staticmethod
    def _related_processes_present() -> bool:
        return any(
            image in subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            ).stdout
            for image in ("terminal64.exe", "metatester64.exe")
        )

    def test_controlled_strategy_tester_completion(self) -> None:
        terminal_content = self.terminal.read_bytes()
        environment = {
            key: os.environ[key]
            for key in _ENVIRONMENT_KEYS
            if os.environ.get(key)
        }
        configuration = Mt5StrategyTesterConfiguration(
            self.terminal,
            Sha256Digest(hashlib.sha256(terminal_content).hexdigest()),
            self.data_root,
            environment,
            "main",
            "demo",
        )
        artifact_content = self.artifact_path.read_bytes()
        artifact_digest = hashlib.sha256(artifact_content).hexdigest()
        artifact = AcceptedArtifact(
            new_entity_id(ArtifactId),
            new_entity_id(BuildRecordId),
            Sha256Digest(hashlib.sha256(artifact_content).hexdigest()),
            artifact_content,
        )
        execution = {
            "schema_name": "mt5-strategy-tester-execution",
            "schema_version": "0.1.0",
            "provider": "metatrader5-strategy-tester",
            "symbol": os.environ.get("EA_RESEARCH_LAB_MT5_SYMBOL", "EURUSD"),
            "period": "M1",
            "model": 1,
            "execution_mode": 0,
            "from_date": os.environ.get(
                "EA_RESEARCH_LAB_MT5_FROM_DATE", "2026-08-03"
            ),
            "to_date": os.environ.get(
                "EA_RESEARCH_LAB_MT5_TO_DATE", "2026-08-04"
            ),
            "deposit": 10000,
            "currency": "USD",
            "leverage": "1:100",
        }
        definition = SchemaReferencedPayload(
            _ref("test-definition"),
            {
                "schema_name": "test-definition",
                "schema_version": "0.1.0",
                "test_definition_id": str(new_entity_id(TestDefinitionId)),
                "test_definition_revision_id": str(
                    new_entity_id(TestDefinitionRevisionId)
                ),
                "artifact_id": str(artifact.artifact_id),
                "execution_configuration": {
                    "schema_ref": str(_ref("mt5-strategy-tester-execution")),
                    "value": execution,
                },
                "sut_inputs": {
                    "schema_ref": "urn:ea-research-lab:schema:controlled-empty-inputs:0.1.0",
                    "value": {},
                },
            },
        )
        request = ExecutionRequest(
            RequestContext(new_entity_id(RequestId), "controlled-mt5-integration"),
            new_entity_id(RunId),
            artifact,
            definition,
            new_entity_id(EnvironmentConfigurationId),
            configuration.payload,
            timedelta(seconds=60),
        )

        staged_digests: list[str] = []
        generated_configs: list[str] = []
        original_stage = mt5_adapter._write_exact_artifact
        original_config = mt5_adapter._write_start_config

        def record_stage(path: Path, execution_request: ExecutionRequest) -> None:
            original_stage(path, execution_request)
            staged_digests.append(hashlib.sha256(path.read_bytes()).hexdigest())

        def record_config(*args: object) -> None:
            original_config(*args)
            generated_configs.append(Path(args[0]).read_text(encoding="utf-8"))

        with (
            patch.object(mt5_adapter, "_write_exact_artifact", record_stage),
            patch.object(mt5_adapter, "_write_start_config", record_config),
        ):
            result = execute_run(
                Mt5StrategyTesterProvider(configuration),
                request,
                ReproducibilityAssessment(
                    ReproducibilityLevel.BEST_EFFORT,
                    (
                        ReproducibilityReason(
                            "provider_replay_not_guaranteed",
                            "The external provider does not guarantee bitwise replay.",
                        ),
                    ),
                ),
            )
        observation = result.provider_observation
        self.assertIsNone(result.failure)

        self.assertIs(
            observation.verdict,
            ExecutionProviderVerdict.COMPLETED,
            dict(observation.provider_evidence.value),
        )
        self.assertTrue(observation.provider_evidence.value["report_observed"])
        self.assertTrue(observation.provider_evidence.value["terminal_log_observed"])
        self.assertTrue(observation.provider_evidence.value["tester_log_observed"])
        self.assertTrue(observation.provider_evidence.value["ownership_established"])
        self.assertEqual(result.run_manifest.value["status"], "completed")
        self.assertEqual(
            result.evidence_manifest.outcome,
            EvidenceCollectionOutcome.COMPLETED,
        )
        self.assertEqual(len(result.raw_evidence), len(observation.captured_outputs))
        for collected, output in zip(
            result.raw_evidence,
            observation.captured_outputs,
        ):
            self.assertEqual(collected.content, output.content)
            self.assertEqual(
                str(collected.evidence_object.content_digest),
                hashlib.sha256(output.content).hexdigest(),
            )
        self.assertEqual(
            result.evidence_manifest.objects,
            tuple(item.evidence_object for item in result.raw_evidence),
        )
        self.assertEqual(result.evidence_manifest.run_id, request.run_id)
        self.assertEqual(result.evidence_manifest_ref.run_id, request.run_id)
        validate_document(_plain(result.evidence_manifest_payload.value))
        validate_document(_plain(result.run_manifest.value))
        transformation = transform_dataset(
            Mt5ReportTransformer(),
            TransformationRequest(
                request.context,
                EvidenceProvenance(
                    result.evidence_manifest,
                    result.evidence_manifest_ref,
                ),
                result.raw_evidence,
                new_entity_id(TransformationId),
                DefinitionVersion("mt5-execution-summary-1"),
            ),
        )
        self.assertIsNone(
            transformation.failure,
            repr(transformation.failure.cause) if transformation.failure else None,
        )
        self.assertIsNotNone(transformation.dataset)
        dataset = transformation.dataset
        assert dataset is not None
        self.assertEqual(
            dict(dataset.content.payload.value),
            {
                "schema_name": "execution-summary",
                "schema_version": "0.1.0",
                "currency": "USD",
                "initial_deposit": "10000.00",
                "net_profit": "0.00",
                "gross_profit": "0.00",
                "gross_loss": "0.00",
                "total_trades": 0,
                "winning_trades": 0,
                "losing_trades": 0,
            },
        )
        validate_document(_plain(dataset.content.payload.value))
        validate_document(_plain(dataset.manifest.value))
        self.assertEqual(
            dataset.manifest.value["content_digest"],
            str(dataset.content.content_digest),
        )
        analysis = analyze_execution_summaries(
            AnalysisRequest(
                request.context,
                (dataset,),
                new_entity_id(AnalysisDefinitionId),
                DefinitionVersion("execution-summary-analysis-1"),
                SchemaReferencedPayload(
                    SchemaRef(
                        SchemaName("execution-summary-analysis-parameters"),
                        SchemaVersion(0, 1, 0),
                    ),
                    {
                        "schema_name": "execution-summary-analysis-parameters",
                        "schema_version": "0.1.0",
                    },
                ),
                new_entity_id(EnvironmentConfigurationId),
            )
        )
        self.assertIsNone(
            analysis.failure,
            repr(analysis.failure.cause) if analysis.failure else None,
        )
        self.assertIsNotNone(analysis.result)
        analysis_result = analysis.result
        assert analysis_result is not None
        metrics = analysis_result.content.payload.value["metrics"][0]
        self.assertEqual(metrics["net_return"], {"value": "0.000000000000"})
        self.assertEqual(
            metrics["win_rate"],
            {"unavailable_reason": "zero_total_trades"},
        )
        self.assertEqual(metrics["loss_rate"], metrics["win_rate"])
        validate_document(_plain(analysis_result.content.payload.value))
        validate_document(_plain(analysis_result.envelope.value))
        self.assertEqual(
            analysis_result.envelope.value["result_digest"],
            str(analysis_result.content.content_digest),
        )
        self.assertEqual(
            result.run_manifest.value["raw_evidence_manifest"],
            {
                "manifest_id": str(result.evidence_manifest_ref.manifest_id),
                "run_id": str(result.evidence_manifest_ref.run_id),
                "content_digest": str(
                    result.evidence_manifest_ref.content_digest
                ),
            },
        )
        self.assertEqual(
            dataset.manifest.value["input_manifests"],
            (result.run_manifest.value["raw_evidence_manifest"],),
        )
        self.assertEqual(
            dataset.manifest.value["transformation_id"],
            str(dataset.provenance.transformation_id),
        )
        self.assertEqual(
            dataset.manifest.value["transformation_version"],
            str(dataset.provenance.transformation_version),
        )
        self.assertIs(analysis_result.input_datasets[0], dataset)
        self.assertEqual(
            analysis_result.envelope.value["provenance"]["input_datasets"][0],
            {
                "dataset_id": str(dataset.provenance.dataset_id),
                "content_digest": str(dataset.content.content_digest),
            },
        )
        self.assertEqual(staged_digests, [artifact_digest])
        self.assertEqual(
            hashlib.sha256(self.artifact_path.read_bytes()).hexdigest(),
            artifact_digest,
        )
        config = generated_configs[0]
        for setting in (
            "AllowLiveTrading=0",
            "AllowDllImport=0",
            "Optimization=0",
            "ShutdownTerminal=1",
            "UseLocal=1",
            "UseRemote=0",
            "UseCloud=0",
            "Visual=0",
        ):
            self.assertIn(setting, config)
        self.assertFalse(self._related_processes_present())


@unittest.skipUnless(
    os.environ.get("EA_RESEARCH_LAB_MT5_INTEGRATION") == "1"
    and os.environ.get("EA_RESEARCH_LAB_METAEDITOR_INTEGRATION") == "1",
    "controlled Phase 05 MT5 integration is not enabled",
)
class Phase06PersistedMt5IntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if os.environ.get("EA_RESEARCH_LAB_MT5_CONTROLLED_ACTIVITY_FIXTURE") != "1":
            raise unittest.SkipTest(
                "controlled known-activity fixture is not acknowledged"
            )
        if not _TERMINAL or not _DATA_ROOT or not _METAEDITOR:
            raise unittest.SkipTest(
                "terminal, data root, and MetaEditor are not configured"
            )
        cls.terminal = Path(_TERMINAL)
        cls.data_root = Path(_DATA_ROOT)
        cls.metaeditor = Path(_METAEDITOR)
        cls.source = (
            Path(__file__).parents[1]
            / "fixtures"
            / "mt5"
            / "phase05-known-activity.mq5"
        )
        if not all(
            (
                cls.terminal.is_file(),
                cls.data_root.is_dir(),
                cls.metaeditor.is_file(),
                cls.source.is_file(),
            )
        ):
            raise unittest.SkipTest("configured integration files are unavailable")
        if cls._related_processes_present():
            raise unittest.SkipTest(
                "existing MT5 or MetaEditor processes make ownership ambiguous"
            )

    @staticmethod
    def _related_processes_present() -> bool:
        return any(
            image in subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            ).stdout
            for image in ("MetaEditor64.exe", "terminal64.exe", "metatester64.exe")
        )

    @staticmethod
    def _environment() -> dict[str, str]:
        return {
            key: os.environ[key]
            for key in _ENVIRONMENT_KEYS
            if os.environ.get(key)
        }

    def test_known_activity_vertical_survives_persistence_and_reload(self) -> None:
        environment = self._environment()
        metaeditor_configuration = MetaEditorConfiguration(
            self.metaeditor,
            Sha256Digest(hashlib.sha256(self.metaeditor.read_bytes()).hexdigest()),
            environment,
        )
        build_request = BuildRequest(
            RequestContext(new_entity_id(RequestId), "phase05-mt5-build"),
            new_entity_id(BuildRecordId),
            SourceRevision(
                "git", "ea-research-lab", "phase05-known-activity", True
            ),
            BuildSourceSpecification(
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Main.mq5",
                    self.source.read_bytes(),
                )
            ),
            new_entity_id(EnvironmentConfigurationId),
            metaeditor_configuration.payload,
            timedelta(seconds=30),
        )
        with tempfile.TemporaryDirectory(prefix="earl-phase05-integration-") as name:
            build = execute_build(
                build_request,
                lambda active: execute_metaeditor_build_attempt(
                    active,
                    configuration=metaeditor_configuration,
                    workspace_parent=Path(name),
                    logical_name="phase05-known-activity",
                    artifact_version="integration-1",
                    built_at=UtcTimestamp(datetime.now(UTC)),
                ),
            )
        self.assertIs(build.outcome, BuildOutcome.SUCCEEDED)
        self.assertIsNotNone(build.artifact_acceptance)
        artifact = build.artifact_acceptance.artifact

        terminal_configuration = Mt5StrategyTesterConfiguration(
            self.terminal,
            Sha256Digest(hashlib.sha256(self.terminal.read_bytes()).hexdigest()),
            self.data_root,
            environment,
            "main",
            "demo",
        )
        execution = {
            "schema_name": "mt5-strategy-tester-execution",
            "schema_version": "0.1.0",
            "provider": "metatrader5-strategy-tester",
            "symbol": "EURUSD",
            "period": "M1",
            "model": 1,
            "execution_mode": 0,
            "from_date": "2026-08-03",
            "to_date": "2026-08-04",
            "deposit": 10000,
            "currency": "USD",
            "leverage": "1:100",
        }
        definition = SchemaReferencedPayload(
            _ref("test-definition"),
            {
                "schema_name": "test-definition",
                "schema_version": "0.1.0",
                "test_definition_id": str(new_entity_id(TestDefinitionId)),
                "test_definition_revision_id": str(
                    new_entity_id(TestDefinitionRevisionId)
                ),
                "artifact_id": str(artifact.artifact_id),
                "execution_configuration": {
                    "schema_ref": str(_ref("mt5-strategy-tester-execution")),
                    "value": execution,
                },
                "sut_inputs": {
                    "schema_ref": (
                        "urn:ea-research-lab:schema:controlled-empty-inputs:0.1.0"
                    ),
                    "value": {},
                },
            },
        )
        execution_request = ExecutionRequest(
            RequestContext(new_entity_id(RequestId), "phase05-mt5-run"),
            new_entity_id(RunId),
            artifact,
            definition,
            new_entity_id(EnvironmentConfigurationId),
            terminal_configuration.payload,
            timedelta(seconds=90),
        )
        run = execute_run(
            Mt5StrategyTesterProvider(terminal_configuration),
            execution_request,
            ReproducibilityAssessment(
                ReproducibilityLevel.BEST_EFFORT,
                (
                    ReproducibilityReason(
                        "provider_replay_not_guaranteed",
                        "The external provider does not guarantee bitwise replay.",
                    ),
                ),
            ),
        )
        self.assertIsNone(run.failure)
        self.assertEqual(run.run_manifest.value["status"], "completed")
        self.assertIs(
            run.evidence_manifest.outcome, EvidenceCollectionOutcome.COMPLETED
        )
        evidence = EvidenceProvenance(
            run.evidence_manifest, run.evidence_manifest_ref
        )
        summary_outcome = transform_dataset(
            Mt5ReportTransformer(),
            TransformationRequest(
                execution_request.context,
                evidence,
                run.raw_evidence,
                new_entity_id(TransformationId),
                DefinitionVersion("mt5-execution-summary-1"),
            ),
        )
        realized_outcome = transform_dataset(
            Mt5RealizedExecutionEventSeriesTransformer(),
            TransformationRequest(
                execution_request.context,
                evidence,
                run.raw_evidence,
                new_entity_id(TransformationId),
                DefinitionVersion("mt5-realized-execution-event-series-1"),
            ),
        )
        balances_outcome = transform_dataset(
            Mt5AccountBalanceEventSeriesTransformer(),
            TransformationRequest(
                execution_request.context,
                evidence,
                run.raw_evidence,
                new_entity_id(TransformationId),
                DefinitionVersion("mt5-account-balance-event-series-1"),
            ),
        )
        self.assertIsNone(
            summary_outcome.failure,
            repr(summary_outcome.failure.cause)
            if summary_outcome.failure
            else None,
        )
        self.assertIsNone(
            realized_outcome.failure,
            repr(realized_outcome.failure.cause)
            if realized_outcome.failure
            else None,
        )
        self.assertIsNone(
            balances_outcome.failure,
            repr(balances_outcome.failure.cause)
            if balances_outcome.failure
            else None,
        )
        summary = summary_outcome.dataset
        realized = realized_outcome.dataset
        balances = balances_outcome.dataset

        self.assertEqual(
            [event["realized_pnl"] for event in realized.content.payload.value["events"]],
            ["-0.04", "0.42"],
        )
        self.assertEqual(
            [
                observation["balance"]
                for observation in balances.content.payload.value["observations"]
            ],
            ["10000.00", "10000.00", "9999.96", "9999.96", "10000.38"],
        )
        for dataset in (summary, realized, balances):
            validate_document(_plain(dataset.content.payload.value))
            validate_document(_plain(dataset.manifest.value))
            self.assertEqual(
                dataset.provenance.input_manifests,
                (run.evidence_manifest_ref,),
            )

        analysis = analyze_execution_core(
            AnalysisRequest(
                execution_request.context,
                (summary, realized, balances),
                new_entity_id(AnalysisDefinitionId),
                DefinitionVersion("execution-core-analysis-1"),
                SchemaReferencedPayload(
                    _ref("execution-core-analysis-parameters"),
                    {
                        "schema_name": "execution-core-analysis-parameters",
                        "schema_version": "0.1.0",
                    },
                ),
                new_entity_id(EnvironmentConfigurationId),
            )
        )
        self.assertIsNone(
            analysis.failure,
            repr(analysis.failure.cause) if analysis.failure else None,
        )
        result = analysis.result
        self.assertIsNotNone(result)
        content = result.content.payload.value
        self.assertEqual(
            content["aggregate_metrics"],
            {
                "net_return": {"value": "0.000038000000"},
                "win_rate": {"value": "0.500000000000"},
                "loss_rate": {"value": "0.500000000000"},
                "expected_payoff": {"value": "0.190000000000"},
                "profit_factor": {"value": "10.500000000000"},
                "average_winning_result": {"value": "0.420000000000"},
                "average_losing_magnitude": {"value": "0.040000000000"},
                "payoff_ratio": {"value": "10.500000000000"},
                "gross_profit_return": {"value": "0.000042000000"},
                "gross_loss_return": {"value": "0.000004000000"},
            },
        )
        self.assertEqual(
            content["realized_execution_distribution"],
            {
                "count": 2,
                "minimum": {"value": "-0.040000000000"},
                "maximum": {"value": "0.420000000000"},
                "arithmetic_mean": {"value": "0.190000000000"},
                "median": {"value": "0.190000000000"},
                "mean_absolute_deviation": {"value": "0.230000000000"},
            },
        )
        self.assertEqual(
            content["realized_execution_sequence"],
            {
                "longest_positive_streak": 1,
                "longest_negative_streak": 1,
                "zero_result_count": 0,
            },
        )
        self.assertEqual(
            content["event_balance_analysis"]["event_balance_max_drawdown"],
            {
                "amount": {"value": "0.040000000000"},
                "rate": {"value": "0.000004000000"},
            },
        )
        self.assertEqual(
            content["input_content_digests"],
            {
                "execution_summary": str(summary.content.content_digest),
                "realized_execution_event_series": str(
                    realized.content.content_digest
                ),
                "account_balance_event_series": str(
                    balances.content.content_digest
                ),
            },
        )
        validate_document(_plain(content))
        validate_document(_plain(result.envelope.value))
        expected = {
            "build_id": str(build.build_record.value["build_record_id"]),
            "run_id": str(run.run_manifest.value["run_id"]),
            "analysis_id": str(result.provenance.analysis_result_id),
            "artifact_bytes": artifact.content,
            "artifact_digest": str(artifact.binary_digest),
            "evidence": tuple(
                (
                    item.content,
                    str(item.evidence_object.content_digest),
                )
                for item in run.raw_evidence
            ),
            "manifest_ref": (
                str(run.evidence_manifest_ref.manifest_id),
                str(run.evidence_manifest_ref.run_id),
                str(run.evidence_manifest_ref.content_digest),
            ),
            "dataset_ids": frozenset(
                str(dataset.provenance.dataset_id)
                for dataset in (summary, realized, balances)
            ),
            "datasets": frozenset(
                (
                    dataset.content.canonical_bytes,
                    str(dataset.content.content_digest),
                )
                for dataset in (summary, realized, balances)
            ),
            "analysis_bytes": result.content.canonical_bytes,
            "analysis_digest": str(result.content.content_digest),
        }
        with tempfile.TemporaryDirectory(
            prefix="earl-phase06-data-plane-"
        ) as data_name:
            database = Path(data_name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(DurableBuild.from_workflow_result(build))
                data_plane.publish_run(
                    DurableRun.from_execution_result(definition, run)
                )
                for dataset in (summary, realized, balances):
                    data_plane.publish_dataset(dataset)
                data_plane.publish_analysis(result)

            del build, artifact, run, evidence, summary, realized, balances
            del analysis, result, content, definition, execution_request
            del summary_outcome, realized_outcome, balances_outcome
            del build_request, terminal_configuration, metaeditor_configuration

            roots = CanonicalChainRequest(
                BuildRecordId.parse(expected["build_id"]),
                RunId.parse(expected["run_id"]),
                AnalysisResultId.parse(expected["analysis_id"]),
            )
            with (
                patch(
                    "ea_research_lab.application.build.execute_build",
                    side_effect=AssertionError("Build must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.execution.execute_run",
                    side_effect=AssertionError("Execution must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.dataset.transform_dataset",
                    side_effect=AssertionError("Transformation must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.analysis.analyze_execution_summaries",
                    side_effect=AssertionError("Analysis must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.analysis.analyze_execution_core",
                    side_effect=AssertionError("Analysis must not rerun."),
                ),
                SqliteDataPlane(database) as fresh_data_plane,
            ):
                chain = reconstruct_canonical_chain(fresh_data_plane, roots)

            loaded_artifact = chain.build.artifact_acceptance.artifact
            self.assertEqual(loaded_artifact.content, expected["artifact_bytes"])
            self.assertEqual(
                str(loaded_artifact.binary_digest), expected["artifact_digest"]
            )
            self.assertEqual(
                tuple(
                    (
                        item.content,
                        str(item.evidence_object.content_digest),
                    )
                    for revision in chain.run.evidence_history
                    for item in revision.raw_evidence
                ),
                expected["evidence"],
            )
            self.assertEqual(
                (
                    str(chain.run.evidence_history[-1].reference.manifest_id),
                    str(chain.run.evidence_history[-1].reference.run_id),
                    str(chain.run.evidence_history[-1].reference.content_digest),
                ),
                expected["manifest_ref"],
            )
            self.assertEqual(
                {str(item.provenance.dataset_id) for item in chain.datasets},
                expected["dataset_ids"],
            )
            self.assertEqual(
                {
                    (
                        item.content.canonical_bytes,
                        str(item.content.content_digest),
                    )
                    for item in chain.datasets
                },
                expected["datasets"],
            )
            self.assertEqual(
                chain.analysis.content.canonical_bytes,
                expected["analysis_bytes"],
            )
            self.assertEqual(
                str(chain.analysis.content.content_digest),
                expected["analysis_digest"],
            )
        self.assertFalse(self._related_processes_present())


if __name__ == "__main__":
    unittest.main()
