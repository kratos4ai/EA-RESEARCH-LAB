from __future__ import annotations

import hashlib
import os
import tempfile
import unittest
from contextlib import contextmanager
from dataclasses import FrozenInstanceError, replace
from datetime import timedelta
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

from ea_research_lab.application.build import (
    ArtifactAcceptance,
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import (
    AcceptedArtifact,
    BuildInputScope,
    BuildProviderObservation,
)
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    ArtifactId,
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
from ea_research_lab.infrastructure.artifact import (
    ArtifactAcceptanceError,
    accept_candidate,
)
from ea_research_lab.infrastructure.build_workspace import materialize_build_workspace


_FIXED_ARTIFACT_ID = ArtifactId.parse(
    "artifact_0195395c-7c9e-7b12-9d3c-7e5f9a2b3c4d"
)


def _provider_observation(*, candidate_available: bool = True):
    value = {
        "schema_name": "metaeditor-build-evidence",
        "schema_version": "0.1.0",
        "provider": "metaeditor",
        "executable_digest": "a" * 64,
        "executable_version": "5.0.0.6104",
        "process_started": True,
        "timed_out": False,
        "exit_code": 1,
        "duration_ms": 10,
        "log_encoding": "utf-16le",
        "log_digest": "b" * 64,
        "compiler_verdict": "succeeded",
        "error_count": 0,
        "warning_count": 0,
        "candidate_observed": True,
        "declared_inputs_only": True,
    }
    return BuildProviderObservation(
        SchemaReferencedPayload(
            SchemaRef(
                SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
            ),
            value,
        ),
        candidate_available,
    )


def _opaque_payload(name: str) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(
        SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0)),
        {"opaque": True},
    )


def _request() -> BuildRequest:
    return BuildRequest(
        RequestContext(new_entity_id(RequestId), "test-client"),
        new_entity_id(BuildRecordId),
        SourceRevision("git", "repository", "revision", True),
        BuildSourceSpecification(
            BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "Experts/Main.mq5",
                b"primary\n",
            )
        ),
        new_entity_id(EnvironmentConfigurationId),
        _opaque_payload("build-configuration"),
        timedelta(seconds=30),
    )


def _plain(value: object) -> object:
    if hasattr(value, "items"):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class ArtifactAcceptanceTests(unittest.TestCase):
    @contextmanager
    def _workspace(self, content: bytes | None = b"candidate bytes"):
        with tempfile.TemporaryDirectory() as parent_name:
            request = _request()
            with materialize_build_workspace(
                request, Path(parent_name)
            ) as workspace:
                candidate = workspace.members[0].physical_path.with_suffix(".ex5")
                if content is not None:
                    candidate.write_bytes(content)
                yield request, workspace, candidate

    def _accept(self, request, workspace, observation=None):
        return accept_candidate(
            workspace=workspace,
            request=request,
            observation=observation or _provider_observation(),
            logical_name="example-sut",
            artifact_version="build-1",
            built_at=UtcTimestamp.parse("2026-08-09T12:00:00Z"),
        )

    def test_valid_candidate_becomes_exact_immutable_artifact_and_manifest(self) -> None:
        content = b"\x00exact EX5 bytes\xff"
        with self._workspace(content) as (request, workspace, _):
            accepted = self._accept(request, workspace)

        artifact = accepted.artifact
        manifest = _plain(accepted.artifact_manifest.value)
        self.assertTrue(str(artifact.artifact_id).startswith("artifact_"))
        self.assertEqual(artifact.build_record_id, request.build_record_id)
        self.assertEqual(artifact.content, content)
        self.assertEqual(
            str(artifact.binary_digest), hashlib.sha256(content).hexdigest()
        )
        self.assertEqual(manifest["binary_digest"], str(artifact.binary_digest))
        self.assertEqual(manifest["artifact_id"], str(artifact.artifact_id))
        self.assertEqual(manifest["build_record_id"], str(request.build_record_id))
        self.assertNotIn("build_input", manifest)
        self.assertNotIn("status", manifest)
        validate_document(manifest)
        with self.assertRaises(FrozenInstanceError):
            artifact.content = b"replacement"
        with self.assertRaises(TypeError):
            accepted.artifact_manifest.value["binary_digest"] = "0" * 64

        with self.assertRaises(InvalidValueError):
            AcceptedArtifact(
                artifact.artifact_id,
                artifact.build_record_id,
                Sha256Digest("0" * 64),
                artifact.content,
            )
        mismatched = dict(manifest)
        mismatched["binary_digest"] = "0" * 64
        with self.assertRaises(InvalidValueError):
            ArtifactAcceptance(
                artifact,
                SchemaReferencedPayload(
                    accepted.artifact_manifest.schema_ref, mismatched
                ),
            )

    def test_artifact_id_is_allocated_only_after_candidate_checks_and_digest(self) -> None:
        with self._workspace(None) as (request, workspace, _):
            with patch(
                "ea_research_lab.infrastructure.artifact.new_entity_id"
            ) as identity:
                with self.assertRaises(ArtifactAcceptanceError):
                    self._accept(request, workspace)
                identity.assert_not_called()

        with self._workspace(b"accepted") as (request, workspace, _):
            with patch(
                "ea_research_lab.infrastructure.artifact.new_entity_id",
                return_value=_FIXED_ARTIFACT_ID,
            ) as identity:
                accepted = self._accept(request, workspace)
                identity.assert_called_once_with(ArtifactId)
                self.assertEqual(accepted.artifact.artifact_id, _FIXED_ARTIFACT_ID)

    def test_provider_must_support_a_current_unambiguous_candidate(self) -> None:
        with self._workspace() as (request, workspace, _):
            with patch(
                "ea_research_lab.infrastructure.artifact.new_entity_id"
            ) as identity:
                with self.assertRaises(ArtifactAcceptanceError) as caught:
                    self._accept(
                        request,
                        workspace,
                        _provider_observation(candidate_available=False),
                    )
                identity.assert_not_called()
        self.assertEqual(
            caught.exception.code,
            ApplicationErrorCode.ARTIFACT_REJECTED.value,
        )

    def test_ambiguous_and_non_regular_candidates_are_rejected(self) -> None:
        with self._workspace() as (request, workspace, _):
            (workspace.root / "other.ex5").write_bytes(b"ambiguous")
            with self.assertRaises(ArtifactAcceptanceError):
                self._accept(request, workspace)

        with self._workspace(None) as (request, workspace, candidate):
            candidate.mkdir()
            with self.assertRaises(ArtifactAcceptanceError):
                self._accept(request, workspace)

    def test_candidate_outside_workspace_and_link_escape_are_rejected(self) -> None:
        with self._workspace() as (request, workspace, _):
            outside_source = workspace.root.parent / "outside.mq5"
            outside_source.write_bytes(b"primary\n")
            outside_source.with_suffix(".ex5").write_bytes(b"outside")
            escaped = replace(
                workspace,
                members=(
                    replace(
                        workspace.members[0], physical_path=outside_source
                    ),
                ),
            )
            with self.assertRaises(ArtifactAcceptanceError) as caught:
                self._accept(request, escaped)
            self.assertNotIn(str(outside_source), str(caught.exception))

        if hasattr(os, "symlink"):
            with self._workspace(None) as (request, workspace, candidate):
                outside = workspace.root.parent / "outside.ex5"
                outside.write_bytes(b"outside")
                try:
                    candidate.symlink_to(outside)
                except OSError:
                    return
                with self.assertRaises(ArtifactAcceptanceError):
                    self._accept(request, workspace)

    def test_detectable_candidate_change_during_read_is_rejected(self) -> None:
        with self._workspace() as (request, workspace, candidate):
            metadata = candidate.stat()
            changed = SimpleNamespace(
                st_dev=metadata.st_dev,
                st_ino=metadata.st_ino,
                st_size=metadata.st_size + 1,
                st_mtime_ns=metadata.st_mtime_ns,
            )
            with (
                patch(
                    "ea_research_lab.infrastructure.artifact.os.fstat",
                    side_effect=(metadata, changed),
                ),
                patch(
                    "ea_research_lab.infrastructure.artifact.new_entity_id"
                ) as identity,
            ):
                with self.assertRaises(ArtifactAcceptanceError):
                    self._accept(request, workspace)
                identity.assert_not_called()

    def test_one_byte_change_produces_a_different_content_identity(self) -> None:
        digests = []
        for content in (b"candidate-A", b"candidate-B"):
            with self._workspace(content) as (request, workspace, _):
                digests.append(
                    str(self._accept(request, workspace).artifact.binary_digest)
                )
        self.assertNotEqual(*digests)


if __name__ == "__main__":
    unittest.main()
