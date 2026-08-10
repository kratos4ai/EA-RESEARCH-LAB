from __future__ import annotations

import hashlib
import os
import subprocess
import tempfile
import unittest
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path

from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
    execute_build,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import BuildInputScope, BuildOutcome
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
)
from ea_research_lab.domain.values import Sha256Digest, SourceRevision, UtcTimestamp
from ea_research_lab.infrastructure.build_workspace import load_source_input
from ea_research_lab.infrastructure.metaeditor import (
    MetaEditorConfiguration,
    execute_metaeditor_build_attempt,
)


ROOT = Path(__file__).resolve().parents[2]
_METAEDITOR_PATH = os.environ.get("EA_RESEARCH_LAB_METAEDITOR")
METAEDITOR = Path(_METAEDITOR_PATH) if _METAEDITOR_PATH else None
MQL5_INCLUDE = ROOT.parent.parent / "Include"
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


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


@unittest.skipUnless(
    os.environ.get("EA_RESEARCH_LAB_METAEDITOR_INTEGRATION") == "1",
    "controlled MetaEditor integration is not enabled",
)
class MetaEditorBuildIntegrationTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        if METAEDITOR is None or not METAEDITOR.is_file():
            raise unittest.SkipTest("approved MetaEditor executable is not configured")
        processes = subprocess.run(
            [
                "tasklist",
                "/FI",
                "IMAGENAME eq MetaEditor64.exe",
                "/FO",
                "CSV",
                "/NH",
            ],
            check=False,
            capture_output=True,
            text=True,
            errors="replace",
        )
        if "MetaEditor64.exe" in processes.stdout:
            raise unittest.SkipTest(
                "an existing MetaEditor process makes ownership ambiguous"
            )

    def _configuration(
        self, *, external: bool = False
    ) -> MetaEditorConfiguration:
        with METAEDITOR.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
        environment = {
            key: os.environ[key]
            for key in _ENVIRONMENT_KEYS
            if os.environ.get(key)
        }
        return MetaEditorConfiguration(
            METAEDITOR,
            Sha256Digest(digest),
            environment,
            external_roots=(
                {"mql5-standard": MQL5_INCLUDE} if external else {}
            ),
        )

    def _request(
        self,
        configuration: MetaEditorConfiguration,
        primary: BuildSourceInput,
        dependencies: tuple[BuildSourceInput, ...] = (),
        *,
        timeout_seconds: float = 10,
    ) -> BuildRequest:
        return BuildRequest(
            RequestContext(new_entity_id(RequestId), "metaeditor-integration"),
            new_entity_id(BuildRecordId),
            SourceRevision("git", "integration-fixtures", "disposable", True),
            BuildSourceSpecification(primary, dependencies),
            new_entity_id(EnvironmentConfigurationId),
            configuration.payload,
            timedelta(seconds=timeout_seconds),
        )

    def _execute(
        self,
        parent: Path,
        request: BuildRequest,
        configuration: MetaEditorConfiguration,
    ):
        return execute_build(
            request,
            lambda active_request: execute_metaeditor_build_attempt(
                active_request,
                configuration=configuration,
                workspace_parent=parent,
                logical_name="integration-sut",
                artifact_version="probe-1",
                built_at=UtcTimestamp(datetime.now(UTC)),
            ),
        )

    def test_valid_minimal_compile(self) -> None:
        with tempfile.TemporaryDirectory(prefix="earl-m5-valid-") as name:
            parent = Path(name)
            configuration = self._configuration()
            request = self._request(
                configuration,
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Main.mq5",
                    b"void OnStart() {}\n",
                ),
            )
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)
        validate_document(_plain(result.build_record.value))

    def test_compiler_failure(self) -> None:
        with tempfile.TemporaryDirectory(prefix="earl-m5-failure-") as name:
            parent = Path(name)
            configuration = self._configuration()
            request = self._request(
                configuration,
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Main.mq5",
                    b"void OnStart( {\n",
                ),
            )
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.FAILED)
        self.assertIsNone(result.artifact_acceptance)
        self.assertIsNotNone(result.provider_observation)
        validate_document(_plain(result.build_record.value))

    def test_owned_process_timeout(self) -> None:
        with tempfile.TemporaryDirectory(prefix="earl-m5-timeout-") as name:
            parent = Path(name)
            configuration = self._configuration()
            request = self._request(
                configuration,
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Main.mq5",
                    b"void OnStart() {}\n",
                ),
                timeout_seconds=0.01,
            )
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.FAILED)
        self.assertTrue(result.provider_observation.provider_evidence.value["timed_out"])
        self.assertIsNone(result.artifact_acceptance)

    def test_mutated_development_source_compiles_captured_snapshot(self) -> None:
        with tempfile.TemporaryDirectory(prefix="earl-m5-dirty-") as name:
            parent = Path(name)
            development = parent / "development.mq5"
            captured = b"void OnStart() {}\n"
            development.write_bytes(captured)
            primary = load_source_input(
                scope=BuildInputScope.WORKSPACE,
                path="Main.mq5",
                source_path=development,
            )
            development.write_bytes(b"void OnStart( {\n")
            configuration = self._configuration()
            request = self._request(configuration, primary)
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)
        self.assertEqual(
            result.build_input_manifest.value["primary"]["content_digest"],
            hashlib.sha256(captured).hexdigest(),
        )

    def test_declared_local_include(self) -> None:
        with tempfile.TemporaryDirectory(prefix="earl-m5-local-") as name:
            parent = Path(name)
            configuration = self._configuration()
            primary = BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "case/Main.mq5",
                b'#include "local.mqh"\nvoid OnStart() {}\n',
            )
            local = BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "case/local.mqh",
                b"int local_value = 1;\n",
            )
            request = self._request(configuration, primary, (local,))
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)

    def test_declared_standard_external_include(self) -> None:
        required = (
            "Arrays/Array.mqh",
            "Object.mqh",
            "StdLibErr.mqh",
        )
        if any(not (MQL5_INCLUDE / path).is_file() for path in required):
            self.skipTest("probed standard include set is unavailable")
        with tempfile.TemporaryDirectory(prefix="earl-m5-external-") as name:
            parent = Path(name)
            configuration = self._configuration(external=True)
            dependencies = tuple(
                load_source_input(
                    scope=BuildInputScope.EXTERNAL,
                    root="mql5-standard",
                    path=path,
                    source_path=MQL5_INCLUDE / path,
                )
                for path in required
            )
            request = self._request(
                configuration,
                BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Main.mq5",
                    b"#include <Arrays\\Array.mqh>\nvoid OnStart() {}\n",
                ),
                dependencies,
            )
            result = self._execute(parent, request, configuration)

        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)
        self.assertEqual(
            {
                member["logical_location"]["root"]
                for member in result.build_input_manifest.value["dependencies"]
            },
            {"mql5-standard"},
        )
        self.assertNotIn(
            str(MQL5_INCLUDE), repr(result.build_input_manifest.value)
        )


if __name__ == "__main__":
    unittest.main()
