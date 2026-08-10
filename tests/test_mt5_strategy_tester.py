from __future__ import annotations

import hashlib
import subprocess
import tempfile
import unittest
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.execution import ExecutionRequest, request_execution
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.build import AcceptedArtifact
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
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)
from ea_research_lab.infrastructure.mt5_strategy_tester import (
    Mt5StrategyTesterAdapterError,
    Mt5StrategyTesterConfiguration,
    Mt5StrategyTesterProvider,
)


def _ref(name: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0))


def _execution_document() -> dict[str, object]:
    return {
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


def _configuration(root: Path) -> Mt5StrategyTesterConfiguration:
    installation = root / "installation"
    data_root = root / "data"
    installation.mkdir()
    (data_root / "config").mkdir(parents=True)
    terminal = installation / "terminal64.exe"
    terminal.write_bytes(b"controlled terminal")
    (data_root / "origin.txt").write_bytes(
        b"\xff\xfe" + str(installation).encode("utf-16le")
    )
    (data_root / "config/common.ini").write_bytes(
        b"\xff\xfe" + "[Common]\r\nServer=Controlled-Demo\r\n".encode("utf-16le")
    )
    return Mt5StrategyTesterConfiguration(
        terminal,
        Sha256Digest(hashlib.sha256(terminal.read_bytes()).hexdigest()),
        data_root,
        {},
        "main",
        "demo",
        max_output_bytes=4096,
    )


def _request(
    configuration: Mt5StrategyTesterConfiguration,
    *,
    execution: dict[str, object] | None = None,
    sut_inputs: dict[str, object] | None = None,
    timeout: float = 10,
) -> ExecutionRequest:
    content = b"accepted ex5 bytes"
    artifact = AcceptedArtifact(
        new_entity_id(ArtifactId),
        new_entity_id(BuildRecordId),
        Sha256Digest(hashlib.sha256(content).hexdigest()),
        content,
    )
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
                "value": execution or _execution_document(),
            },
            "sut_inputs": {
                "schema_ref": "urn:ea-research-lab:schema:controlled-empty-inputs:0.1.0",
                "value": {} if sut_inputs is None else sut_inputs,
            },
        },
    )
    return ExecutionRequest(
        RequestContext(new_entity_id(RequestId), "controlled-test"),
        new_entity_id(RunId),
        artifact,
        definition,
        new_entity_id(EnvironmentConfigurationId),
        configuration.payload,
        timedelta(seconds=timeout),
    )


class _FakeJob:
    assignments: list[int] = []
    closes = 0

    def assign(self, pid: int) -> None:
        self.assignments.append(pid)

    def close(self) -> None:
        type(self).closes += 1


class _FailingJob(_FakeJob):
    def assign(self, pid: int) -> None:
        raise OSError("controlled assignment failure")


class _FakeProcess:
    behavior = "success"
    calls: list[tuple[object, dict[str, object]]] = []
    staged_bytes: bytes | None = None
    config_text: str | None = None
    terminations = 0
    data_root: Path | None = None
    workspaces: list[Path] = []

    def __init__(self, command: object, **kwargs: object) -> None:
        type(self).calls.append((command, kwargs))
        self.pid = 4321
        self.returncode = None
        self.root = type(self).data_root
        if self.root is None:
            raise AssertionError("controlled data root is not configured")
        workspace = next((self.root / "MQL5/Experts/EAResearchLab").iterdir())
        type(self).workspaces.append(workspace)
        type(self).staged_bytes = (workspace / "sut.ex5").read_bytes()
        type(self).config_text = (workspace / "tester.ini").read_text(
            encoding="utf-8"
        )
        self.workspace = workspace
        self.waits = 0

    def wait(self, timeout: float) -> int:
        self.waits += 1
        if self.behavior == "timeout" and self.waits == 1:
            raise subprocess.TimeoutExpired("terminal64.exe", timeout)
        if self.behavior == "success":
            (self.workspace / "tester-report.htm").write_bytes(b"<html>ok</html>")
            self._write_log(
                self.root / "logs/controlled.log",
                "successfully initialized from start config",
            )
            self._write_log(
                self.root / "Tester/logs/controlled.log",
                "test passed; final balance 10000",
            )
            self.returncode = 7
        elif self.behavior == "failed":
            self._write_log(self.root / "logs/controlled.log", "tester didn't start")
            self.returncode = 91
        elif self.behavior == "ambiguous":
            self._write_log(
                self.root / "logs/controlled.log",
                "provider emitted an unknown message",
            )
            self.returncode = 0
        else:
            self.returncode = -1
        return self.returncode

    def terminate(self) -> None:
        type(self).terminations += 1
        self.returncode = -15

    def kill(self) -> None:
        self.returncode = -9

    def _write_log(self, path: Path, message: str) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("ab") as stream:
            if path.stat().st_size == 0:
                stream.write(b"\xff\xfe")
            stream.write((message + "\r\n").encode("utf-16le"))


class Mt5StrategyTesterTests(unittest.TestCase):
    def setUp(self) -> None:
        _FakeJob.assignments = []
        _FakeJob.closes = 0
        _FakeProcess.calls = []
        _FakeProcess.staged_bytes = None
        _FakeProcess.config_text = None
        _FakeProcess.terminations = 0
        _FakeProcess.data_root = None
        _FakeProcess.workspaces = []
        _FakeProcess.behavior = "success"

    def _execute(self, root: Path, **request_options: object):
        configuration = _configuration(root)
        _FakeProcess.data_root = configuration.data_root
        request = _request(configuration, **request_options)
        with (
            patch(
                "ea_research_lab.infrastructure.mt5_strategy_tester._WindowsOwnedJob",
                _FakeJob,
            ),
            patch(
                "ea_research_lab.infrastructure.mt5_strategy_tester.subprocess.Popen",
                _FakeProcess,
            ),
            patch(
                "ea_research_lab.infrastructure.mt5_strategy_tester._related_mt5_processes_present",
                return_value=False,
            ),
        ):
            observation = request_execution(
                Mt5StrategyTesterProvider(configuration), request
            )
        return request, observation

    def test_configuration_requires_explicit_matching_main_environment(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            configuration = _configuration(root)
            request = _request(configuration)
            (configuration.data_root / "origin.txt").write_bytes(
                b"\xff\xfe" + str(root).encode("utf-16le")
            )
            with self.assertRaises(Mt5StrategyTesterAdapterError):
                Mt5StrategyTesterProvider(configuration).execute(request)

            (configuration.data_root / "origin.txt").write_bytes(
                b"\xff\xfe"
                + str(configuration.terminal_executable.parent).encode("utf-16le")
            )
            common = configuration.data_root / "config/common.ini"
            common.write_bytes(
                b"\xff\xfe"
                + "[Common]\r\nServer=Controlled-Real\r\n".encode("utf-16le")
            )
            with self.assertRaises(Mt5StrategyTesterAdapterError):
                Mt5StrategyTesterProvider(configuration).execute(request)

            common.write_bytes(
                b"\xff\xfe"
                + "[Common]\r\nServer=Controlled-Demo\r\n".encode("utf-16le")
            )
            configuration.terminal_executable.write_bytes(b"changed")
            with self.assertRaises(Mt5StrategyTesterAdapterError):
                Mt5StrategyTesterProvider(configuration).execute(request)

            with self.assertRaises(Mt5StrategyTesterAdapterError):
                Mt5StrategyTesterConfiguration(
                    configuration.terminal_executable,
                    configuration.terminal_digest,
                    configuration.data_root,
                    {},
                    "portable",
                    "demo",
                )

    def test_invocation_is_fixed_shell_free_and_artifact_isolated(self) -> None:
        with tempfile.TemporaryDirectory(prefix="mt5 adapter ") as name:
            root = Path(name)
            request, observation = self._execute(root)

            command, options = _FakeProcess.calls[0]
            self.assertIs(options["shell"], False)
            self.assertNotIn("/portable", command)
            self.assertIn('/config:"', command)
            self.assertEqual(
                options["cwd"],
                Path(request.environment_configuration.value["terminal_executable"]).parent,
            )
            self.assertNotIn(str(request.artifact.artifact_id), command)
            self.assertEqual(_FakeProcess.staged_bytes, request.artifact.content)
            self.assertEqual(_FakeJob.assignments, [4321])
            self.assertEqual(
                list((root / "data/MQL5/Experts/EAResearchLab").glob("*")), []
            )
            self.assertIs(observation.verdict, ExecutionProviderVerdict.COMPLETED)

    def test_staging_is_run_scoped_and_cleanup_preserves_provider_state(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            configuration = _configuration(root)
            provider_state = configuration.data_root / "config/accounts.dat"
            provider_state.write_bytes(b"provider-owned mutable state")
            state_before = provider_state.read_bytes()
            _FakeProcess.data_root = configuration.data_root
            requests = (_request(configuration), _request(configuration))
            provider = Mt5StrategyTesterProvider(configuration)
            with (
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester._WindowsOwnedJob",
                    _FakeJob,
                ),
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester.subprocess.Popen",
                    _FakeProcess,
                ),
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester._related_mt5_processes_present",
                    return_value=False,
                ),
            ):
                observations = tuple(provider.execute(request) for request in requests)

            self.assertEqual(len({path.name for path in _FakeProcess.workspaces}), 2)
            for workspace, request in zip(_FakeProcess.workspaces, requests):
                self.assertTrue(workspace.name.startswith(f"{request.run_id}-"))
            self.assertEqual(provider_state.read_bytes(), state_before)
            self.assertEqual(
                list((configuration.data_root / "MQL5/Experts/EAResearchLab").iterdir()),
                [],
            )
            self.assertTrue(
                all(
                    item.verdict is ExecutionProviderVerdict.COMPLETED
                    for item in observations
                )
            )

    def test_definition_translation_stays_inside_fixed_start_config(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            self._execute(Path(name))
        config = _FakeProcess.config_text
        self.assertIn("Symbol=EURUSD", config)
        self.assertIn("FromDate=2026.08.03", config)
        self.assertIn("AllowLiveTrading=0", config)
        self.assertIn("AllowDllImport=0", config)
        self.assertIn("UseRemote=0", config)
        self.assertIn("UseCloud=0", config)
        self.assertNotIn("caller_args", config)
        self.assertNotIn("Login=", config)
        self.assertNotIn("Password=", config)
        self.assertNotIn("Server=", config)

    def test_success_returns_bounded_opaque_provider_observation_only(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _, observation = self._execute(Path(name))
        evidence = observation.provider_evidence
        self.assertEqual(
            str(evidence.schema_ref),
            "urn:ea-research-lab:schema:mt5-strategy-tester-evidence:0.1.0",
        )
        self.assertEqual(evidence.value["completion"], "completed")
        self.assertEqual(evidence.value["exit_code"], 7)
        self.assertEqual(len(observation.captured_outputs), 3)
        self.assertEqual(observation.captured_outputs[0].content, b"<html>ok</html>")
        for field in ("run_status", "run_manifest", "raw_evidence_manifest"):
            self.assertFalse(hasattr(observation, field))

    def test_failure_and_ambiguous_completion_fail_closed(self) -> None:
        for behavior, verdict in (
            ("failed", ExecutionProviderVerdict.FAILED),
            ("ambiguous", ExecutionProviderVerdict.INCONCLUSIVE),
        ):
            with self.subTest(behavior=behavior), tempfile.TemporaryDirectory() as name:
                _FakeProcess.behavior = behavior
                _, observation = self._execute(Path(name))
                self.assertIs(observation.verdict, verdict)
                self.assertFalse(observation.provider_evidence.value["report_observed"])

    def test_timeout_closes_owned_job_and_returns_provider_cancellation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            _FakeProcess.behavior = "timeout"
            _, observation = self._execute(Path(name), timeout=0.001)
        self.assertIs(observation.verdict, ExecutionProviderVerdict.CANCELLED)
        self.assertTrue(observation.provider_evidence.value["timed_out"])
        self.assertTrue(observation.provider_evidence.value["ownership_established"])
        self.assertGreaterEqual(_FakeJob.closes, 1)

    def test_ownership_assignment_failure_stops_and_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            configuration = _configuration(root)
            _FakeProcess.data_root = configuration.data_root
            request = _request(configuration)
            with (
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester._WindowsOwnedJob",
                    _FailingJob,
                ),
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester.subprocess.Popen",
                    _FakeProcess,
                ),
                patch(
                    "ea_research_lab.infrastructure.mt5_strategy_tester._related_mt5_processes_present",
                    return_value=False,
                ),
                self.assertRaises(Mt5StrategyTesterAdapterError),
            ):
                Mt5StrategyTesterProvider(configuration).execute(request)
        self.assertEqual(_FakeProcess.calls[0][0].count("/config:"), 1)
        self.assertEqual(_FakeProcess.terminations, 1)

    def test_rejects_unknown_execution_contract_nonempty_inputs_and_date_order(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            root = Path(name)
            configuration = _configuration(root)
            provider = Mt5StrategyTesterProvider(configuration)
            invalid_date = _execution_document()
            invalid_date["from_date"] = invalid_date["to_date"]
            requests = (
                _request(configuration, sut_inputs={"strategy": "opaque"}),
                _request(configuration, execution=invalid_date),
            )
            for request in requests:
                with self.assertRaises(Mt5StrategyTesterAdapterError):
                    provider.execute(request)


if __name__ == "__main__":
    unittest.main()
