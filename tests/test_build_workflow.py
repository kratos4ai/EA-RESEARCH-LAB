from __future__ import annotations

import hashlib
import tempfile
import unittest
from collections.abc import Mapping
from datetime import timedelta
from pathlib import Path
from unittest.mock import patch

from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
    execute_build,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import (
    BuildInputScope,
    BuildOutcome,
    BuildProviderObservation,
)
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    SourceRevision,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.build_workspace import load_source_input
from ea_research_lab.infrastructure.metaeditor import (
    MetaEditorConfiguration,
    execute_metaeditor_build_attempt,
)


def _observation(*, available: bool, timed_out: bool = False):
    value = {
        "schema_name": "metaeditor-build-evidence",
        "schema_version": "0.1.0",
        "provider": "metaeditor",
        "executable_digest": "a" * 64,
        "executable_version": "5.0.0.6104",
        "process_started": True,
        "timed_out": timed_out,
        "exit_code": -1 if timed_out else (1 if available else 0),
        "duration_ms": 10,
        "log_encoding": None if timed_out else "utf-16le",
        "log_digest": None if timed_out else "b" * 64,
        "compiler_verdict": "unavailable" if timed_out else (
            "succeeded" if available else "failed"
        ),
        "error_count": None if timed_out else (0 if available else 1),
        "warning_count": None if timed_out else 0,
        "candidate_observed": available,
        "declared_inputs_only": None if timed_out else True,
    }
    return BuildProviderObservation(
        SchemaReferencedPayload(
            SchemaRef(
                SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
            ),
            value,
        ),
        available,
    )


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class _FakeProvider:
    def __init__(
        self,
        workspace,
        observation: BuildProviderObservation,
        captured_inputs: list[bytes] | None = None,
    ) -> None:
        self.workspace = workspace
        self.observation = observation
        self.captured_inputs = captured_inputs

    def build(self, request: BuildRequest) -> BuildProviderObservation:
        primary = self.workspace.members[0].physical_path
        if self.captured_inputs is not None:
            self.captured_inputs.append(primary.read_bytes())
        if self.observation.candidate_available:
            primary.with_suffix(".ex5").write_bytes(b"accepted candidate")
        return self.observation


class BuildWorkflowTests(unittest.TestCase):
    def _configuration(self, parent: Path) -> MetaEditorConfiguration:
        executable = parent / "MetaEditor64.exe"
        executable.write_bytes(b"fake executable")
        return MetaEditorConfiguration(
            executable,
            Sha256Digest(hashlib.sha256(executable.read_bytes()).hexdigest()),
            {},
        )

    def _request(
        self,
        configuration: MetaEditorConfiguration,
        primary: BuildSourceInput | None = None,
    ) -> BuildRequest:
        return BuildRequest(
            RequestContext(new_entity_id(RequestId), "test-client"),
            new_entity_id(BuildRecordId),
            SourceRevision("git", "repository", "revision", True),
            BuildSourceSpecification(
                primary
                or BuildSourceInput(
                    BuildInputScope.WORKSPACE,
                    "Experts/Main.mq5",
                    b"snapshot source",
                )
            ),
            new_entity_id(EnvironmentConfigurationId),
            configuration.payload,
            timedelta(seconds=30),
        )

    def _execute(
        self,
        request: BuildRequest,
        configuration: MetaEditorConfiguration,
        workspace_parent: Path,
        observation: BuildProviderObservation,
        *,
        captured_inputs: list[bytes] | None = None,
    ):
        def provider_factory(configuration, workspace, logger=None):
            return _FakeProvider(workspace, observation, captured_inputs)

        with patch(
            "ea_research_lab.infrastructure.metaeditor.MetaEditorBuildProvider",
            side_effect=provider_factory,
        ):
            return execute_build(
                request,
                lambda active_request: execute_metaeditor_build_attempt(
                    active_request,
                    configuration=configuration,
                    workspace_parent=workspace_parent,
                    logical_name="example-sut",
                    artifact_version="build-1",
                    built_at=UtcTimestamp.parse("2026-08-09T12:00:00Z"),
                ),
            )

    def test_success_finalizes_valid_build_record_with_accepted_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            configuration = self._configuration(parent)
            request = self._request(configuration)
            result = self._execute(
                request, configuration, parent, _observation(available=True)
            )

        record = _plain(result.build_record.value)
        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)
        self.assertIsNone(result.failure)
        self.assertIsNotNone(result.artifact_acceptance)
        self.assertEqual(
            record["artifact_id"],
            str(result.artifact_acceptance.artifact.artifact_id),
        )
        self.assertEqual(record["status"], "succeeded")
        self.assertEqual(
            record["build_input"]["build_input_identity"],
            result.build_input_manifest.value["build_input_identity"],
        )
        self.assertEqual(
            record["provider_evidence"]["schema_ref"],
            str(result.provider_observation.provider_evidence.schema_ref),
        )
        validate_document(record)

    def test_provider_failure_and_timeout_preserve_input_and_evidence(self) -> None:
        for observation in (
            _observation(available=False),
            _observation(available=False, timed_out=True),
        ):
            with self.subTest(timed_out=observation.provider_evidence.value["timed_out"]):
                with tempfile.TemporaryDirectory() as parent_name:
                    parent = Path(parent_name)
                    configuration = self._configuration(parent)
                    request = self._request(configuration)
                    result = self._execute(
                        request, configuration, parent, observation
                    )

                record = _plain(result.build_record.value)
                self.assertIs(result.outcome, BuildOutcome.FAILED)
                self.assertIsNotNone(result.build_input_manifest)
                self.assertIs(result.provider_observation, observation)
                self.assertIsNone(result.artifact_acceptance)
                self.assertEqual(
                    result.failure.code.value, "build_provider_failed"
                )
                self.assertNotIn("artifact_id", record)
                self.assertIn("build_input", record)
                self.assertIn("provider_evidence", record)
                validate_document(record)

    def test_candidate_acceptance_is_required_for_success(self) -> None:
        observation = _observation(available=True)

        class NoCandidateProvider(_FakeProvider):
            def build(self, request):
                return self.observation

        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            configuration = self._configuration(parent)
            request = self._request(configuration)

            def factory(configuration, workspace, logger=None):
                return NoCandidateProvider(workspace, observation)

            with patch(
                "ea_research_lab.infrastructure.metaeditor.MetaEditorBuildProvider",
                side_effect=factory,
            ):
                result = execute_build(
                    request,
                    lambda active_request: execute_metaeditor_build_attempt(
                        active_request,
                        configuration=configuration,
                        workspace_parent=parent,
                        logical_name="example-sut",
                        artifact_version="build-1",
                        built_at=UtcTimestamp.parse("2026-08-09T12:00:00Z"),
                    ),
                )

        self.assertIs(result.outcome, BuildOutcome.FAILED)
        self.assertIsNone(result.artifact_acceptance)
        self.assertNotIn("artifact_id", result.build_record.value)
        self.assertIsNotNone(result.provider_observation)
        validate_document(_plain(result.build_record.value))

    def test_pre_materialization_failure_omits_input_and_provider_evidence(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            configuration = self._configuration(parent)
            request = self._request(configuration)
            unavailable_parent = parent / "missing"
            result = self._execute(
                request,
                configuration,
                unavailable_parent,
                _observation(available=True),
            )

        record = _plain(result.build_record.value)
        self.assertIs(result.outcome, BuildOutcome.FAILED)
        self.assertNotIn("build_input", record)
        self.assertNotIn("provider_evidence", record)
        self.assertNotIn("artifact_id", record)
        self.assertEqual(result.failure.code.value, "build_input_invalid")
        validate_document(record)

    def test_mutated_development_source_does_not_change_compiled_snapshot(self) -> None:
        with tempfile.TemporaryDirectory() as parent_name:
            parent = Path(parent_name)
            development_source = parent / "development.mq5"
            development_source.write_bytes(b"captured source")
            primary = load_source_input(
                scope=BuildInputScope.WORKSPACE,
                path="Experts/Main.mq5",
                source_path=development_source,
            )
            configuration = self._configuration(parent)
            request = self._request(configuration, primary)
            development_source.write_bytes(b"changed after capture")
            captured_inputs: list[bytes] = []
            result = self._execute(
                request,
                configuration,
                parent,
                _observation(available=True),
                captured_inputs=captured_inputs,
            )

        self.assertIs(result.outcome, BuildOutcome.SUCCEEDED)
        self.assertEqual(captured_inputs, [b"captured source"])
        primary_manifest = result.build_input_manifest.value["primary"]
        self.assertEqual(
            primary_manifest["content_digest"],
            hashlib.sha256(b"captured source").hexdigest(),
        )


if __name__ == "__main__":
    unittest.main()
