"""Provider-neutral application boundary for requesting a build."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.domain.build import (
    AcceptedArtifact,
    BuildInputScope,
    BuildProviderObservation,
)
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    SourceRevision,
)


_ARTIFACT_MANIFEST_REF = SchemaRef(
    SchemaName("artifact-manifest"), SchemaVersion(0, 1, 0)
)


@dataclass(frozen=True, slots=True)
class ArtifactAcceptance:
    """Accepted in-memory Artifact and its exact validated manifest."""

    artifact: AcceptedArtifact
    artifact_manifest: SchemaReferencedPayload

    def __post_init__(self) -> None:
        if not isinstance(self.artifact, AcceptedArtifact):
            raise InvalidValueError("Artifact acceptance requires an Artifact.")
        if (
            not isinstance(self.artifact_manifest, SchemaReferencedPayload)
            or self.artifact_manifest.schema_ref != _ARTIFACT_MANIFEST_REF
        ):
            raise InvalidValueError(
                "Artifact acceptance requires Artifact Manifest 0.1.0."
            )
        manifest = self.artifact_manifest.value
        expected = {
            "artifact_id": str(self.artifact.artifact_id),
            "build_record_id": str(self.artifact.build_record_id),
            "binary_digest": str(self.artifact.binary_digest),
        }
        if any(manifest.get(name) != value for name, value in expected.items()):
            raise InvalidValueError(
                "Accepted Artifact does not match its Artifact Manifest."
            )


@dataclass(frozen=True, slots=True)
class BuildSourceInput:
    """Exact source bytes under one provider-neutral logical location."""

    scope: BuildInputScope
    path: str
    content: bytes
    root: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.scope, BuildInputScope):
            raise InvalidValueError("Build source scope is invalid.")
        if not isinstance(self.path, str) or not self.path:
            raise InvalidValueError("Build source path must be non-empty.")
        if not isinstance(self.content, bytes):
            raise InvalidValueError("Build source content must be immutable bytes.")
        if self.scope is BuildInputScope.WORKSPACE and self.root is not None:
            raise InvalidValueError("Workspace build source cannot declare a root.")
        if self.scope is BuildInputScope.EXTERNAL and (
            not isinstance(self.root, str)
            or not self.root
            or self.root.strip() != self.root
        ):
            raise InvalidValueError(
                "External build source requires a logical root alias."
            )


@dataclass(frozen=True, slots=True)
class BuildSourceSpecification:
    """One primary source and its explicitly declared dependency set."""

    primary: BuildSourceInput
    dependencies: tuple[BuildSourceInput, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.primary, BuildSourceInput) or (
            self.primary.scope is not BuildInputScope.WORKSPACE
        ):
            raise InvalidValueError("Primary build source must use workspace scope.")
        try:
            dependencies = tuple(self.dependencies)
        except TypeError as error:
            raise InvalidValueError(
                "Build dependencies must be an ordered collection."
            ) from error
        if any(
            not isinstance(dependency, BuildSourceInput)
            for dependency in dependencies
        ):
            raise InvalidValueError(
                "Build dependencies must contain BuildSourceInput values."
            )
        object.__setattr__(self, "dependencies", dependencies)


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Build intent before provider-specific materialization or invocation."""

    context: RequestContext
    build_record_id: BuildRecordId
    source_revision: SourceRevision
    source_specification: BuildSourceSpecification
    build_configuration_id: EnvironmentConfigurationId
    build_configuration: SchemaReferencedPayload
    timeout: timedelta

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext, "RequestContext"),
            (self.build_record_id, BuildRecordId, "BuildRecordId"),
            (self.source_revision, SourceRevision, "SourceRevision"),
            (
                self.source_specification,
                BuildSourceSpecification,
                "source specification",
            ),
            (
                self.build_configuration_id,
                EnvironmentConfigurationId,
                "EnvironmentConfigurationId",
            ),
            (
                self.build_configuration,
                SchemaReferencedPayload,
                "build configuration",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise InvalidValueError(f"Build request requires {label}.")
        if not isinstance(self.timeout, timedelta) or self.timeout <= timedelta(0):
            raise InvalidValueError("Build timeout must be a positive duration.")


class BuildProvider(Protocol):
    """Port implemented by one external build technology adapter."""

    def build(self, request: BuildRequest) -> BuildProviderObservation: ...


def request_build(
    provider: BuildProvider, request: BuildRequest
) -> BuildProviderObservation:
    """Invoke the provider port without interpreting its evidence as success."""

    if not isinstance(request, BuildRequest):
        raise TypeError("Build operation requires a BuildRequest.")
    observation = provider.build(request)
    if not isinstance(observation, BuildProviderObservation):
        raise TypeError("BuildProvider must return a BuildProviderObservation.")
    return observation
