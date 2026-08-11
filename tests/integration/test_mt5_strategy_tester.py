from __future__ import annotations

import hashlib
import os
import subprocess
import unittest
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

import ea_research_lab.infrastructure.mt5_strategy_tester as mt5_adapter
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.execution import ExecutionRequest, execute_run
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.evidence import EvidenceCollectionOutcome
from ea_research_lab.domain.execution import ExecutionProviderVerdict
from ea_research_lab.domain.identifiers import (
    ArtifactId,
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)
from ea_research_lab.infrastructure.mt5_strategy_tester import (
    Mt5StrategyTesterConfiguration,
    Mt5StrategyTesterProvider,
)


_TERMINAL = os.environ.get("EA_RESEARCH_LAB_MT5_TERMINAL")
_DATA_ROOT = os.environ.get("EA_RESEARCH_LAB_MT5_DATA_ROOT")
_ARTIFACT = os.environ.get("EA_RESEARCH_LAB_MT5_ARTIFACT")
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


if __name__ == "__main__":
    unittest.main()
