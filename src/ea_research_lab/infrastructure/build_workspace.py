"""Exclusive exact-byte build workspace materialization."""

from __future__ import annotations

import hashlib
import os
import tempfile
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from pathlib import Path, PurePosixPath
from types import MappingProxyType

from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
)
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.contracts import (
    ContractValidationError,
    calculate_build_input_identity,
    normalize_logical_path,
    validate_document,
)
from ea_research_lab.domain.build import BuildInputScope
from ea_research_lab.domain.values import Sha256Digest


_PLACEHOLDER_DIGEST = "0" * 64


class BuildWorkspaceError(ValueError):
    """Safe failure while establishing or verifying a build snapshot."""

    code = ApplicationErrorCode.BUILD_INPUT_INVALID.value


@dataclass(frozen=True, slots=True)
class MaterializedBuildInput:
    scope: BuildInputScope
    logical_path: str
    physical_path: Path
    content_digest: Sha256Digest
    root: str | None = None


@dataclass(frozen=True, slots=True)
class MaterializedBuildWorkspace:
    root: Path
    workspace_root: Path
    external_roots: Mapping[str, Path]
    members: tuple[MaterializedBuildInput, ...]
    manifest: Mapping[str, object]

    def verify_integrity(self) -> None:
        """Verify represented files and manifest without modifying either."""

        for member in self.members:
            _require_safe_file(self.root, member.physical_path)
            if _hash_file(member.physical_path) != member.content_digest:
                raise BuildWorkspaceError(
                    "Materialized build input no longer matches its manifest."
                )
        expected = _manifest_for(self.members)
        if self.manifest != expected:
            raise BuildWorkspaceError("Build Input Manifest was modified.")
        try:
            validate_document(expected)
        except ContractValidationError as error:
            raise BuildWorkspaceError("Build Input Manifest is invalid.") from error


def load_source_input(
    *,
    scope: BuildInputScope,
    path: str,
    source_path: Path,
    root: str | None = None,
) -> BuildSourceInput:
    """Read one explicitly declared physical source into immutable bytes."""

    if not isinstance(source_path, Path):
        raise BuildWorkspaceError("Declared source reference is invalid.")
    try:
        if _is_link_or_junction(source_path) or not source_path.is_file():
            raise BuildWorkspaceError("Declared source is unavailable or unsafe.")
        content = source_path.read_bytes()
    except OSError as error:
        raise BuildWorkspaceError("Declared source is unavailable or unsafe.") from error
    return BuildSourceInput(scope=scope, path=path, content=content, root=root)


@contextmanager
def materialize_build_workspace(
    request: BuildRequest, workspace_parent: Path
) -> Iterator[MaterializedBuildWorkspace]:
    """Create, populate, yield, and safely remove one exclusive workspace."""

    if not isinstance(request, BuildRequest) or not isinstance(workspace_parent, Path):
        raise BuildWorkspaceError("Build workspace request is invalid.")
    parent = _safe_workspace_parent(workspace_parent)
    try:
        temporary = tempfile.TemporaryDirectory(prefix="build-", dir=parent)
    except OSError as error:
        raise BuildWorkspaceError(
            "Exclusive build workspace could not be created."
        ) from error

    try:
        root = Path(temporary.name).resolve(strict=True)
        if root.parent != parent or _is_link_or_junction(root):
            raise BuildWorkspaceError("Exclusive build workspace is unsafe.")
        workspace = _populate(root, request.source_specification)
        yield workspace
    finally:
        try:
            temporary.cleanup()
        except OSError as error:
            raise BuildWorkspaceError(
                "Exclusive build workspace cleanup failed."
            ) from error


def _safe_workspace_parent(path: Path) -> Path:
    try:
        if _is_link_or_junction(path) or not path.is_dir():
            raise BuildWorkspaceError("Build workspace parent is unavailable or unsafe.")
        return path.resolve(strict=True)
    except OSError as error:
        raise BuildWorkspaceError(
            "Build workspace parent is unavailable or unsafe."
        ) from error


def _populate(
    root: Path, specification: BuildSourceSpecification
) -> MaterializedBuildWorkspace:
    sources = _validated_sources(specification)
    materialized: list[MaterializedBuildInput] = []
    for source, logical_path in sources:
        base = root / source.scope.value
        if source.root is not None:
            base /= source.root
        target = base.joinpath(*PurePosixPath(logical_path).parts)
        _write_exclusive(root, target, source.content)
        materialized.append(
            MaterializedBuildInput(
                scope=source.scope,
                logical_path=logical_path,
                physical_path=target,
                content_digest=_hash_file(target),
                root=source.root,
            )
        )

    members = tuple(materialized)
    manifest = _manifest_for(members)
    try:
        validate_document(manifest)
    except ContractValidationError as error:
        raise BuildWorkspaceError("Build Input Manifest is invalid.") from error
    external_roots = MappingProxyType(
        {
            member.root: root / BuildInputScope.EXTERNAL.value / member.root
            for member in members
            if member.root is not None
        }
    )
    return MaterializedBuildWorkspace(
        root=root,
        workspace_root=root / BuildInputScope.WORKSPACE.value,
        external_roots=external_roots,
        members=members,
        manifest=manifest,
    )


def _validated_sources(
    specification: BuildSourceSpecification,
) -> tuple[tuple[BuildSourceInput, str], ...]:
    sources = (specification.primary, *specification.dependencies)
    normalized: list[tuple[BuildSourceInput, str]] = []
    projected: list[dict[str, object]] = []
    try:
        for source in sources:
            logical_path = normalize_logical_path(source.path)
            location: dict[str, object] = {
                "scope": source.scope.value,
                "path": logical_path,
            }
            if source.root is not None:
                location["root"] = source.root
            projected.append(
                {
                    "logical_location": location,
                    "content_digest": _PLACEHOLDER_DIGEST,
                }
            )
            normalized.append((source, logical_path))
        calculate_build_input_identity(projected[0], projected[1:])
    except ContractValidationError as error:
        raise BuildWorkspaceError("Build source specification is invalid.") from error
    return tuple(normalized)


def _write_exclusive(root: Path, target: Path, content: bytes) -> None:
    _require_contained(root, target)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        _require_no_linked_parent(root, target.parent)
        with target.open("xb") as stream:
            stream.write(content)
    except (FileExistsError, OSError) as error:
        raise BuildWorkspaceError("Build input could not be materialized safely.") from error
    _require_safe_file(root, target)


def _require_contained(root: Path, target: Path) -> None:
    try:
        if not target.resolve(strict=False).is_relative_to(root):
            raise BuildWorkspaceError("Build input target escapes its workspace.")
    except OSError as error:
        raise BuildWorkspaceError("Build input containment could not be verified.") from error


def _require_no_linked_parent(root: Path, parent: Path) -> None:
    current = parent
    while current != root:
        if _is_link_or_junction(current):
            raise BuildWorkspaceError("Build input target uses an unsafe link.")
        current = current.parent


def _require_safe_file(root: Path, path: Path) -> None:
    _require_contained(root, path)
    if _is_link_or_junction(path) or not path.is_file():
        raise BuildWorkspaceError("Materialized build input is unavailable or unsafe.")


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(os.path, "isjunction", lambda candidate: False)(path)
    )


def _hash_file(path: Path) -> Sha256Digest:
    try:
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise BuildWorkspaceError("Build input could not be read safely.") from error
    return Sha256Digest(digest)


def _manifest_member(member: MaterializedBuildInput) -> dict[str, object]:
    location: dict[str, object] = {
        "scope": member.scope.value,
        "path": member.logical_path,
    }
    if member.root is not None:
        location["root"] = member.root
    return {
        "logical_location": location,
        "content_digest": str(member.content_digest),
    }


def _manifest_for(
    members: tuple[MaterializedBuildInput, ...],
) -> dict[str, object]:
    primary = _manifest_member(members[0])
    dependencies = [_manifest_member(member) for member in members[1:]]
    return {
        "schema_name": "build-input-manifest",
        "schema_version": "0.1.0",
        "build_input_identity": str(
            calculate_build_input_identity(primary, dependencies)
        ),
        "primary": primary,
        "dependencies": dependencies,
    }
