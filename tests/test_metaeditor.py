from __future__ import annotations

import hashlib
import json
import logging
import tempfile
import unittest
from contextlib import contextmanager
from datetime import timedelta
from io import StringIO
from pathlib import Path
from unittest.mock import patch

from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.build import BuildInputScope
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
)
from ea_research_lab.domain.values import Sha256Digest, SourceRevision
from ea_research_lab.infrastructure.build_workspace import materialize_build_workspace
from ea_research_lab.infrastructure.config import Settings
from ea_research_lab.infrastructure.logging import configure_logging
from ea_research_lab.infrastructure.metaeditor import (
    MetaEditorAdapterError,
    MetaEditorBuildProvider,
    MetaEditorConfiguration,
)


def _utf16_log(errors: int = 0, warnings: int = 0, *includes: Path) -> bytes:
    lines = [
        *(f"source.mq5 : information: including {path}" for path in includes),
        f"Result: {errors} errors, {warnings} warnings, 10 ms elapsed",
    ]
    return b"\xff\xfe" + "\r\n".join(lines).encode("utf-16le")


class _FakeProcess:
    def __init__(self, exit_code: int, *, times_out: bool = False) -> None:
        self.returncode: int | None = None
        self._exit_code = exit_code
        self._times_out = times_out
        self.terminated = False
        self.killed = False

    def wait(self, timeout: float | None = None) -> int:
        if self._times_out and not self.terminated and not self.killed:
            import subprocess

            raise subprocess.TimeoutExpired("MetaEditor64.exe", timeout)
        self.returncode = -1 if self.terminated or self.killed else self._exit_code
        return self.returncode

    def terminate(self) -> None:
        self.terminated = True

    def kill(self) -> None:
        self.killed = True


class _PopenScenario:
    def __init__(
        self,
        *,
        exit_code: int = 1,
        log: bytes | None = None,
        candidate: bool = False,
        extra_candidate: bool = False,
        times_out: bool = False,
        start_error: bool = False,
    ) -> None:
        self.exit_code = exit_code
        self.log = log
        self.candidate = candidate
        self.extra_candidate = extra_candidate
        self.times_out = times_out
        self.start_error = start_error
        self.calls: list[tuple[object, dict[str, object]]] = []
        self.process: _FakeProcess | None = None

    def __call__(self, command: object, **kwargs: object) -> _FakeProcess:
        self.calls.append((command, kwargs))
        if self.start_error:
            raise OSError("private process detail")
        directory = Path(str(kwargs["cwd"]))
        primary = next(directory.glob("*.mq5"))
        if self.log is not None:
            primary.with_suffix(".log").write_bytes(self.log)
        if self.candidate:
            primary.with_suffix(".ex5").write_bytes(b"candidate bytes")
        if self.extra_candidate:
            (directory / "unexpected.ex5").write_bytes(b"other candidate")
        self.process = _FakeProcess(self.exit_code, times_out=self.times_out)
        return self.process


class MetaEditorAdapterTests(unittest.TestCase):
    @contextmanager
    def _build_setup(
        self,
        *,
        dependencies: tuple[BuildSourceInput, ...] = (),
        logical_primary: str = "Probe Main.mq5",
        max_log_bytes: int = 1_048_576,
        logger: logging.Logger | None = None,
    ):
        with tempfile.TemporaryDirectory(prefix="metaeditor test café ") as parent_name:
            parent = Path(parent_name)
            executable = parent / "MetaEditor64.exe"
            executable.write_bytes(b"fake executable identity")
            configuration = MetaEditorConfiguration(
                executable,
                Sha256Digest(hashlib.sha256(executable.read_bytes()).hexdigest()),
                {},
                max_log_bytes=max_log_bytes,
            )
            specification = BuildSourceSpecification(
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    logical_primary,
                    b"void OnStart() {}\n",
                ),
                dependencies,
            )
            request = BuildRequest(
                RequestContext(new_entity_id(RequestId), "test-client"),
                new_entity_id(BuildRecordId),
                SourceRevision("git", "repository", "revision", True),
                specification,
                new_entity_id(EnvironmentConfigurationId),
                configuration.payload,
                timedelta(seconds=2),
            )
            with materialize_build_workspace(request, parent) as workspace:
                yield (
                    MetaEditorBuildProvider(
                        configuration, workspace, logger=logger
                    ),
                    request,
                    workspace,
                    configuration,
                    executable,
                )

    def _invoke(self, provider, request, scenario: _PopenScenario):
        with (
            patch(
                "ea_research_lab.infrastructure.metaeditor.subprocess.Popen",
                side_effect=scenario,
            ),
            patch(
                "ea_research_lab.infrastructure.metaeditor._read_windows_file_version",
                return_value="5.0.0.6104",
            ),
        ):
            return provider.build(request)

    def test_uses_fixed_argv_grammar_shell_false_and_safe_environment(self) -> None:
        scenario = _PopenScenario(log=_utf16_log(), candidate=True)
        with self._build_setup(logical_primary="Probe ç 測試.mq5") as setup:
            provider, request, workspace, _, executable = setup
            observation = self._invoke(provider, request, scenario)
            command, options = scenario.calls[0]
            primary = workspace.members[0].physical_path.resolve()

            self.assertEqual(
                command,
                f'"{executable.resolve()}" /compile:"{primary}" /log',
            )
            self.assertIs(options["shell"], False)
            self.assertEqual(options["executable"], str(executable.resolve()))
            self.assertEqual(options["cwd"], str(primary.parent))
            self.assertNotIn("private", options["env"])
            self.assertTrue(observation.candidate_available)

    def test_configuration_is_explicit_frozen_and_rejects_unapproved_values(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            executable = Path(parent_name) / "MetaEditor64.exe"
            executable.write_bytes(b"identity")
            digest = Sha256Digest(hashlib.sha256(b"identity").hexdigest())
            configuration = MetaEditorConfiguration(
                executable,
                digest,
                {"SystemRoot": "C:\\Windows"},
                max_log_bytes=512,
            )

            self.assertEqual(
                configuration.payload.value["executable_path"], str(executable)
            )
            with self.assertRaises(TypeError):
                configuration.environment["PATH"] = "changed"
            with self.assertRaises(MetaEditorAdapterError):
                MetaEditorConfiguration(Path("relative.exe"), digest, {})
            with self.assertRaises(MetaEditorAdapterError):
                MetaEditorConfiguration(
                    executable, digest, {"UNAPPROVED": "value"}
                )
            with self.assertRaises(MetaEditorAdapterError):
                MetaEditorConfiguration(executable, digest, {}, max_log_bytes=1)

    def test_log_verdict_not_exit_code_controls_candidate_availability(self) -> None:
        cases = (
            (23, _utf16_log(0, 0), True, True, "succeeded"),
            (0, _utf16_log(3, 1), False, False, "failed"),
            (1, _utf16_log(2, 0), True, False, "failed"),
        )
        for exit_code, log, candidate, available, verdict in cases:
            with self.subTest(exit_code=exit_code, verdict=verdict):
                scenario = _PopenScenario(
                    exit_code=exit_code, log=log, candidate=candidate
                )
                with self._build_setup() as setup:
                    observation = self._invoke(setup[0], setup[1], scenario)
                    self.assertEqual(
                        observation.provider_evidence.value["exit_code"], exit_code
                    )
                    self.assertEqual(
                        observation.provider_evidence.value["compiler_verdict"],
                        verdict,
                    )
                    self.assertEqual(observation.candidate_available, available)

    def test_timeout_terminates_only_owned_process_and_rejects_candidate(self) -> None:
        scenario = _PopenScenario(
            log=_utf16_log(), candidate=True, times_out=True
        )
        with self._build_setup() as setup:
            observation = self._invoke(setup[0], setup[1], scenario)

        self.assertTrue(scenario.process.terminated)
        self.assertFalse(scenario.process.killed)
        self.assertTrue(observation.provider_evidence.value["timed_out"])
        self.assertTrue(
            observation.provider_evidence.value["candidate_observed"]
        )
        self.assertFalse(observation.candidate_available)

    def test_missing_malformed_wrong_encoding_and_oversized_logs_fail_closed(self) -> None:
        cases = (
            (None, 1_048_576),
            (b"not utf16", 1_048_576),
            (b"\xff\xfe" + "no result".encode("utf-16le"), 1_048_576),
            (_utf16_log(), 4),
        )
        for log, limit in cases:
            with self.subTest(log=log, limit=limit):
                scenario = _PopenScenario(log=log, candidate=True)
                with self._build_setup(max_log_bytes=limit) as setup:
                    observation = self._invoke(setup[0], setup[1], scenario)
                self.assertEqual(
                    observation.provider_evidence.value["compiler_verdict"],
                    "unavailable",
                )
                self.assertFalse(observation.candidate_available)

    def test_undeclared_include_and_ambiguous_candidate_fail_closed(self) -> None:
        with self._build_setup() as setup:
            outside = setup[2].root.parent / "undeclared.mqh"
            scenario = _PopenScenario(
                log=_utf16_log(0, 0, outside),
                candidate=True,
                extra_candidate=True,
            )
            observation = self._invoke(setup[0], setup[1], scenario)

        self.assertFalse(
            observation.provider_evidence.value["declared_inputs_only"]
        )
        self.assertFalse(observation.candidate_available)

    def test_process_start_failure_returns_bounded_opaque_evidence(self) -> None:
        scenario = _PopenScenario(start_error=True)
        with self._build_setup() as setup:
            observation = self._invoke(setup[0], setup[1], scenario)

        evidence = observation.provider_evidence
        self.assertEqual(
            str(evidence.schema_ref),
            "urn:ea-research-lab:schema:metaeditor-build-evidence:0.1.0",
        )
        self.assertFalse(evidence.value["process_started"])
        self.assertFalse(observation.candidate_available)
        serialized = repr(evidence.value)
        self.assertNotIn("private process detail", serialized)
        self.assertNotIn("MetaEditor64.exe", serialized)

    def test_executable_stale_output_and_external_inputs_are_rejected_safely(self) -> None:
        with self._build_setup() as setup:
            provider, request, workspace, _, executable = setup
            executable.write_bytes(b"changed executable")
            with self.assertRaises(MetaEditorAdapterError) as caught:
                provider.build(request)
            self.assertEqual(
                caught.exception.code,
                ApplicationErrorCode.BUILD_PROVIDER_FAILED.value,
            )
            self.assertNotIn(str(executable), str(caught.exception))

        external = BuildSourceInput(
            BuildInputScope.EXTERNAL,
            "Arrays/Array.mqh",
            b"external\n",
            root="mql5-standard",
        )
        with self._build_setup(dependencies=(external,)) as setup:
            with self.assertRaises(MetaEditorAdapterError):
                setup[0].build(setup[1])

        with self._build_setup() as setup:
            setup[2].members[0].physical_path.with_suffix(".ex5").write_bytes(
                b"stale"
            )
            with self.assertRaises(MetaEditorAdapterError):
                setup[0].build(setup[1])

    def test_operational_logs_contain_only_safe_correlations(self) -> None:
        stream = StringIO()
        package_logger = logging.getLogger("ea_research_lab")
        original = (
            package_logger.handlers[:],
            package_logger.level,
            package_logger.propagate,
        )
        package_logger.handlers = []
        try:
            logger = configure_logging(Settings(), stream=stream)
            scenario = _PopenScenario(log=_utf16_log(), candidate=True)
            with self._build_setup(logger=logger) as setup:
                primary = str(setup[2].members[0].physical_path)
                observation = self._invoke(setup[0], setup[1], scenario)

            records = [json.loads(line) for line in stream.getvalue().splitlines()]
            self.assertEqual(
                [record["event"] for record in records],
                ["build.provider.started", "build.provider.completed"],
            )
            self.assertTrue(
                all("build_record_id" in record for record in records)
            )
            self.assertNotIn(primary, stream.getvalue())
            self.assertNotIn(
                repr(observation.provider_evidence.value), stream.getvalue()
            )
        finally:
            for handler in package_logger.handlers:
                handler.close()
            package_logger.handlers = original[0]
            package_logger.setLevel(original[1])
            package_logger.propagate = original[2]


if __name__ == "__main__":
    unittest.main()
