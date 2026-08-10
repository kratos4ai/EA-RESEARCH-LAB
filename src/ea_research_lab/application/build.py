"""Provider-neutral application boundary for requesting a build."""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import (
    AcceptedArtifact,
    BuildInputScope,
    BuildOutcome,
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
_BUILD_INPUT_MANIFEST_REF = SchemaRef(
    SchemaName("build-input-manifest"), SchemaVersion(0, 1, 0)
)
_BUILD_RECORD_REF = SchemaRef(
    SchemaName("build-record"), SchemaVersion(0, 2, 0)
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
class BuildAttempt:
    """Established facts from one infrastructure build attempt."""

    build_input_manifest: SchemaReferencedPayload | None
    provider_observation: BuildProviderObservation | None
    artifact_acceptance: ArtifactAcceptance | None
    failure: ApplicationError | None

    def __post_init__(self) -> None:
        if self.build_input_manifest is not None and (
            not isinstance(self.build_input_manifest, SchemaReferencedPayload)
            or self.build_input_manifest.schema_ref != _BUILD_INPUT_MANIFEST_REF
        ):
            raise InvalidValueError("Build attempt input manifest is invalid.")
        if self.provider_observation is not None and not isinstance(
            self.provider_observation, BuildProviderObservation
        ):
            raise InvalidValueError("Build attempt provider observation is invalid.")
        if self.artifact_acceptance is not None and not isinstance(
            self.artifact_acceptance, ArtifactAcceptance
        ):
            raise InvalidValueError("Build attempt Artifact acceptance is invalid.")
        if self.failure is not None and not isinstance(self.failure, ApplicationError):
            raise InvalidValueError("Build attempt failure is invalid.")
        succeeded = self.artifact_acceptance is not None
        if succeeded and (
            self.build_input_manifest is None
            or self.provider_observation is None
            or self.failure is not None
        ):
            raise InvalidValueError("Successful build attempt facts are incomplete.")
        if not succeeded and self.failure is None:
            raise InvalidValueError("Failed build attempt requires a safe failure.")


@dataclass(frozen=True, slots=True)
class BuildWorkflowResult:
    """Final in-memory Build Record and the facts established by its workflow."""

    outcome: BuildOutcome
    build_record: SchemaReferencedPayload
    build_input_manifest: SchemaReferencedPayload | None
    provider_observation: BuildProviderObservation | None
    artifact_acceptance: ArtifactAcceptance | None
    failure: ApplicationError | None

    def __post_init__(self) -> None:
        if not isinstance(self.outcome, BuildOutcome) or (
            not isinstance(self.build_record, SchemaReferencedPayload)
            or self.build_record.schema_ref != _BUILD_RECORD_REF
        ):
            raise InvalidValueError("Build workflow result is invalid.")
        record = self.build_record.value
        if record.get("status") != self.outcome.value:
            raise InvalidValueError("Build workflow outcome does not match its record.")
        if self.outcome is BuildOutcome.SUCCEEDED:
            if self.artifact_acceptance is None or self.failure is not None:
                raise InvalidValueError("Successful Build result is incomplete.")
            if record.get("artifact_id") != str(
                self.artifact_acceptance.artifact.artifact_id
            ):
                raise InvalidValueError("Build Record does not reference its Artifact.")
        elif self.artifact_acceptance is not None or self.failure is None:
            raise InvalidValueError("Failed Build result is invalid.")


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


def execute_build(
    request: BuildRequest,
    attempt_executor: Callable[[BuildRequest], BuildAttempt],
) -> BuildWorkflowResult:
    """Execute one explicit build attempt and own its final platform outcome."""

    if not isinstance(request, BuildRequest) or not callable(attempt_executor):
        raise TypeError("Build workflow requires a request and attempt executor.")
    try:
        attempt = attempt_executor(request)
    except Exception as error:
        attempt = BuildAttempt(
            None,
            None,
            None,
            ApplicationError(
                ApplicationErrorCode.BUILD_PROVIDER_FAILED,
                "Build attempt failed.",
                request_id=request.context.request_id,
                cause=error,
            ),
        )
    if not isinstance(attempt, BuildAttempt):
        raise TypeError("Build attempt executor must return BuildAttempt.")
    if attempt.build_input_manifest is not None:
        validate_document(_plain_json(attempt.build_input_manifest.value))

    outcome = (
        BuildOutcome.SUCCEEDED
        if attempt.artifact_acceptance is not None
        else BuildOutcome.FAILED
    )
    record = _build_record(request, attempt, outcome)
    validate_document(record)
    return BuildWorkflowResult(
        outcome=outcome,
        build_record=SchemaReferencedPayload(_BUILD_RECORD_REF, record),
        build_input_manifest=attempt.build_input_manifest,
        provider_observation=attempt.provider_observation,
        artifact_acceptance=attempt.artifact_acceptance,
        failure=attempt.failure,
    )


def _build_record(
    request: BuildRequest, attempt: BuildAttempt, outcome: BuildOutcome
) -> dict[str, object]:
    record: dict[str, object] = {
        "schema_name": "build-record",
        "schema_version": "0.2.0",
        "build_record_id": str(request.build_record_id),
        "source_revision": {
            "vcs_kind": request.source_revision.vcs_kind,
            "repository": request.source_revision.repository,
            "revision": request.source_revision.revision,
            "is_dirty": request.source_revision.is_dirty,
        },
        "build_configuration_id": str(request.build_configuration_id),
        "build_configuration": _wire_payload(request.build_configuration),
        "status": outcome.value,
    }
    if attempt.build_input_manifest is not None:
        record["build_input"] = {
            "schema_ref": str(attempt.build_input_manifest.schema_ref),
            "build_input_identity": attempt.build_input_manifest.value[
                "build_input_identity"
            ],
        }
    if attempt.provider_observation is not None:
        record["provider_evidence"] = _wire_payload(
            attempt.provider_observation.provider_evidence
        )
    if attempt.artifact_acceptance is not None:
        record["artifact_id"] = str(
            attempt.artifact_acceptance.artifact.artifact_id
        )
    return record


def _wire_payload(payload: SchemaReferencedPayload) -> dict[str, object]:
    return {
        "schema_ref": str(payload.schema_ref),
        "value": _plain_json(payload.value),
    }


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value
