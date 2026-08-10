"""Safe acceptance of one current-workspace build candidate."""

from __future__ import annotations

import hashlib
import logging
import os
import stat
from collections.abc import Mapping
from pathlib import Path

from ea_research_lab.application.build import (
    ArtifactAcceptance,
    BuildRequest,
)
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.build import AcceptedArtifact, BuildProviderObservation
from ea_research_lab.domain.identifiers import ArtifactId
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.build_workspace import (
    BuildWorkspaceError,
    MaterializedBuildWorkspace,
)
from ea_research_lab.infrastructure.logging import log_event


_ARTIFACT_MANIFEST_REF = SchemaRef(
    SchemaName("artifact-manifest"), SchemaVersion(0, 1, 0)
)


class ArtifactAcceptanceError(ValueError):
    """Safe failure while validating a candidate Artifact."""

    code = ApplicationErrorCode.ARTIFACT_REJECTED.value


def accept_candidate(
    *,
    workspace: MaterializedBuildWorkspace,
    request: BuildRequest,
    observation: BuildProviderObservation,
    logical_name: str,
    artifact_version: str,
    built_at: UtcTimestamp,
    logger: logging.Logger | None = None,
) -> ArtifactAcceptance:
    """Validate, read, identify, and accept one immutable candidate."""

    _validate_inputs(
        workspace,
        request,
        observation,
        logical_name,
        artifact_version,
        built_at,
        logger,
    )
    if logger is not None:
        log_event(
            logger,
            logging.INFO,
            "build.artifact.acceptance.started",
            "Artifact acceptance started.",
            context=request.context,
            build_record_id=request.build_record_id,
        )

    try:
        workspace.verify_integrity()
    except BuildWorkspaceError as error:
        raise ArtifactAcceptanceError("Build workspace integrity failed.") from error

    candidate = _expected_candidate(workspace)
    content = _read_stable_candidate(candidate)
    _require_single_candidate(workspace, candidate)
    try:
        workspace.verify_integrity()
    except BuildWorkspaceError as error:
        raise ArtifactAcceptanceError("Build workspace integrity failed.") from error

    binary_digest = Sha256Digest(hashlib.sha256(content).hexdigest())
    artifact_id = new_entity_id(ArtifactId)
    manifest = _artifact_manifest(
        artifact_id=artifact_id,
        request=request,
        observation=observation,
        logical_name=logical_name,
        artifact_version=artifact_version,
        binary_digest=binary_digest,
        built_at=built_at,
    )
    try:
        validate_document(manifest)
    except ContractValidationError as error:
        raise ArtifactAcceptanceError("Artifact Manifest is invalid.") from error

    artifact = AcceptedArtifact(
        artifact_id=artifact_id,
        build_record_id=request.build_record_id,
        binary_digest=binary_digest,
        content=content,
    )
    accepted = ArtifactAcceptance(
        artifact,
        SchemaReferencedPayload(_ARTIFACT_MANIFEST_REF, manifest),
    )
    if logger is not None:
        log_event(
            logger,
            logging.INFO,
            "build.artifact.accepted",
            "Artifact accepted.",
            context=request.context,
            build_record_id=request.build_record_id,
            artifact_id=artifact_id,
        )
    return accepted


def _validate_inputs(
    workspace: object,
    request: object,
    observation: object,
    logical_name: object,
    artifact_version: object,
    built_at: object,
    logger: object,
) -> None:
    if not isinstance(workspace, MaterializedBuildWorkspace) or not isinstance(
        request, BuildRequest
    ):
        raise ArtifactAcceptanceError("Artifact acceptance request is invalid.")
    if not isinstance(observation, BuildProviderObservation):
        raise ArtifactAcceptanceError("Provider observation is invalid.")
    if not observation.candidate_available:
        raise ArtifactAcceptanceError(
            "Provider observation does not support candidate acceptance."
        )
    for value in (logical_name, artifact_version):
        if not isinstance(value, str) or not value or value.strip() != value:
            raise ArtifactAcceptanceError("Artifact metadata is invalid.")
    if not isinstance(built_at, UtcTimestamp):
        raise ArtifactAcceptanceError("Artifact timestamp is invalid.")
    if logger is not None and not isinstance(logger, logging.Logger):
        raise ArtifactAcceptanceError("Artifact logger is invalid.")
    evidence = _plain_json(observation.provider_evidence.value)
    if not isinstance(evidence, dict):
        raise ArtifactAcceptanceError("Provider evidence is invalid.")
    try:
        validate_document(evidence)
    except ContractValidationError as error:
        raise ArtifactAcceptanceError("Provider evidence is invalid.") from error
    namespace = evidence.get("provider")
    if not isinstance(namespace, str) or not namespace:
        raise ArtifactAcceptanceError("Provider namespace is unavailable.")


def _expected_candidate(workspace: MaterializedBuildWorkspace) -> Path:
    if not workspace.members:
        raise ArtifactAcceptanceError("Build workspace has no primary input.")
    try:
        root = workspace.root.resolve(strict=True)
        primary = workspace.members[0].physical_path.resolve(strict=True)
    except OSError as error:
        raise ArtifactAcceptanceError("Build candidate location is unavailable.") from error
    if not primary.is_relative_to(root):
        raise ArtifactAcceptanceError("Build candidate location is outside workspace.")
    candidate = primary.with_suffix(".ex5")
    _require_single_candidate(workspace, candidate)
    _require_safe_regular_file(root, candidate)
    return candidate


def _require_single_candidate(
    workspace: MaterializedBuildWorkspace, expected: Path
) -> None:
    try:
        candidates = [
            path
            for path in workspace.root.rglob("*")
            if path.suffix.lower() == ".ex5"
        ]
    except OSError as error:
        raise ArtifactAcceptanceError("Build candidates cannot be inspected.") from error
    if len(candidates) != 1 or candidates[0] != expected:
        raise ArtifactAcceptanceError("Build candidate is missing or ambiguous.")


def _require_safe_regular_file(root: Path, candidate: Path) -> None:
    try:
        if _is_link_or_junction(candidate):
            raise ArtifactAcceptanceError("Build candidate uses an unsafe link.")
        current = candidate.parent
        while current != root:
            if _is_link_or_junction(current):
                raise ArtifactAcceptanceError("Build candidate uses an unsafe link.")
            current = current.parent
        resolved = candidate.resolve(strict=True)
        metadata = candidate.stat(follow_symlinks=False)
    except OSError as error:
        raise ArtifactAcceptanceError("Build candidate is unavailable.") from error
    if not resolved.is_relative_to(root) or not stat.S_ISREG(metadata.st_mode):
        raise ArtifactAcceptanceError("Build candidate is not a safe regular file.")


def _read_stable_candidate(candidate: Path) -> bytes:
    # ponytail: metadata and handle identity detect ordinary concurrent changes;
    # use native no-follow handle controls if adversarial writers enter scope.
    try:
        with candidate.open("rb") as stream:
            before = os.fstat(stream.fileno())
            content = stream.read()
            after = os.fstat(stream.fileno())
        current = candidate.stat(follow_symlinks=False)
    except OSError as error:
        raise ArtifactAcceptanceError("Build candidate cannot be read.") from error
    before_identity = _file_identity(before)
    if (
        before_identity != _file_identity(after)
        or before_identity != _file_identity(current)
        or len(content) != after.st_size
        or _is_link_or_junction(candidate)
    ):
        raise ArtifactAcceptanceError("Build candidate changed during acceptance.")
    return content


def _file_identity(metadata: os.stat_result) -> tuple[int, int, int, int]:
    return (
        metadata.st_dev,
        metadata.st_ino,
        metadata.st_size,
        metadata.st_mtime_ns,
    )


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(os.path, "isjunction", lambda candidate: False)(path)
    )


def _artifact_manifest(
    *,
    artifact_id: ArtifactId,
    request: BuildRequest,
    observation: BuildProviderObservation,
    logical_name: str,
    artifact_version: str,
    binary_digest: Sha256Digest,
    built_at: UtcTimestamp,
) -> dict[str, object]:
    evidence = _plain_json(observation.provider_evidence.value)
    return {
        "schema_name": "artifact-manifest",
        "schema_version": "0.1.0",
        "artifact_id": str(artifact_id),
        "logical_name": logical_name,
        "artifact_version": artifact_version,
        "build_record_id": str(request.build_record_id),
        "source_revision": {
            "vcs_kind": request.source_revision.vcs_kind,
            "repository": request.source_revision.repository,
            "revision": request.source_revision.revision,
            "is_dirty": request.source_revision.is_dirty,
        },
        "binary_digest": str(binary_digest),
        "compiler": {
            "namespace": evidence["provider"],
            "schema_ref": str(observation.provider_evidence.schema_ref),
            "value": evidence,
        },
        "built_at": str(built_at),
    }


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value
