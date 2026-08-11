"""Provider-neutral execution boundary and in-memory Run finalization."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import (
    ApplicationError,
    ApplicationErrorCode,
)
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.errors import DomainError, InvalidValueError
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderObservation,
    ExecutionProviderVerdict,
)
from ea_research_lab.domain.identifiers import (
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RunId,
    TestDefinitionRevisionId,
)
from ea_research_lab.domain.provenance import (
    EvidenceProvenance,
    RunProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)


_TEST_DEFINITION_REF = SchemaRef(
    SchemaName("test-definition"), SchemaVersion(0, 1, 0)
)
_RAW_EVIDENCE_MANIFEST_REF = SchemaRef(
    SchemaName("raw-evidence-manifest"), SchemaVersion(0, 1, 0)
)
_RUN_MANIFEST_REF = SchemaRef(
    SchemaName("run-manifest"), SchemaVersion(0, 1, 0)
)


@dataclass(frozen=True, slots=True)
class CollectedRawEvidence:
    """One immutable byte sequence and its exact evidence descriptor."""

    evidence_object: RawEvidenceObject
    content: bytes

    def __post_init__(self) -> None:
        if not isinstance(self.evidence_object, RawEvidenceObject) or not isinstance(
            self.content, bytes
        ):
            raise InvalidValueError("Collected Raw Evidence is invalid.")
        if (
            len(self.content) != self.evidence_object.byte_length
            or hashlib.sha256(self.content).hexdigest()
            != str(self.evidence_object.content_digest)
        ):
            raise InvalidValueError(
                "Collected Raw Evidence metadata must identify its exact bytes."
            )


@dataclass(frozen=True, slots=True)
class RunExecutionResult:
    """Final in-memory Run, sealed evidence, bytes, and provider observation."""

    run_manifest: SchemaReferencedPayload
    evidence_manifest: RawEvidenceManifest
    evidence_manifest_payload: SchemaReferencedPayload
    evidence_manifest_ref: RawEvidenceManifestRef
    raw_evidence: tuple[CollectedRawEvidence, ...]
    provider_observation: ExecutionProviderObservation | None
    failure: ApplicationError | None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_manifest, SchemaReferencedPayload)
            or self.run_manifest.schema_ref != _RUN_MANIFEST_REF
            or not isinstance(self.evidence_manifest, RawEvidenceManifest)
            or not isinstance(self.evidence_manifest_payload, SchemaReferencedPayload)
            or self.evidence_manifest_payload.schema_ref
            != _RAW_EVIDENCE_MANIFEST_REF
            or not isinstance(self.evidence_manifest_ref, RawEvidenceManifestRef)
            or (
                self.provider_observation is not None
                and not isinstance(
                    self.provider_observation, ExecutionProviderObservation
                )
            )
            or (
                self.failure is not None
                and not isinstance(self.failure, ApplicationError)
            )
        ):
            raise InvalidValueError("Final Run execution result is invalid.")
        try:
            evidence = tuple(self.raw_evidence)
        except TypeError as error:
            raise InvalidValueError(
                "Final Run Raw Evidence must be an ordered collection."
            ) from error
        if any(not isinstance(item, CollectedRawEvidence) for item in evidence):
            raise InvalidValueError("Final Run contains invalid Raw Evidence.")
        manifest_document = _plain_json(self.evidence_manifest_payload.value)
        expected_manifest_ref = {
            "manifest_id": str(self.evidence_manifest_ref.manifest_id),
            "run_id": str(self.evidence_manifest_ref.run_id),
            "content_digest": str(self.evidence_manifest_ref.content_digest),
        }
        if (
            self.evidence_manifest.manifest_id
            != self.evidence_manifest_ref.manifest_id
            or self.evidence_manifest.run_id != self.evidence_manifest_ref.run_id
            or self.evidence_manifest.objects
            != tuple(item.evidence_object for item in evidence)
            or manifest_document
            != _evidence_manifest_document(self.evidence_manifest)
            or hashlib.sha256(_canonical_json_bytes(manifest_document)).hexdigest()
            != str(self.evidence_manifest_ref.content_digest)
            or self.run_manifest.value.get("run_id")
            != str(self.evidence_manifest.run_id)
            or _plain_json(self.run_manifest.value).get("raw_evidence_manifest")
            != expected_manifest_ref
            or (self.provider_observation is None) != (self.failure is not None)
            or (
                self.provider_observation is None
                and (
                    evidence
                    or self.evidence_manifest.outcome
                    is not EvidenceCollectionOutcome.COLLECTION_FAILED
                    or self.run_manifest.value.get("status")
                    not in {"failed", "cancelled"}
                )
            )
        ):
            raise InvalidValueError("Final Run provenance links do not agree.")
        object.__setattr__(self, "raw_evidence", evidence)


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Execution intent before any external provider interaction."""

    context: RequestContext
    run_id: RunId
    artifact: AcceptedArtifact
    test_definition: SchemaReferencedPayload
    environment_configuration_id: EnvironmentConfigurationId
    environment_configuration: SchemaReferencedPayload
    timeout: timedelta

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext, "RequestContext"),
            (self.run_id, RunId, "RunId"),
            (self.artifact, AcceptedArtifact, "accepted Artifact"),
            (
                self.environment_configuration_id,
                EnvironmentConfigurationId,
                "EnvironmentConfigurationId",
            ),
            (
                self.environment_configuration,
                SchemaReferencedPayload,
                "environment configuration",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise InvalidValueError(f"Execution request requires {label}.")
        if (
            not isinstance(self.test_definition, SchemaReferencedPayload)
            or self.test_definition.schema_ref != _TEST_DEFINITION_REF
        ):
            raise InvalidValueError(
                "Execution request requires Test Definition 0.1.0."
            )
        try:
            validate_document(_plain_json(self.test_definition.value))
        except ContractValidationError as error:
            raise InvalidValueError(
                "Execution request requires a valid Test Definition."
            ) from error
        if self.test_definition.value.get("artifact_id") != str(
            self.artifact.artifact_id
        ):
            raise InvalidValueError(
                "Test Definition must reference the accepted Artifact."
            )
        if not isinstance(self.timeout, timedelta) or self.timeout <= timedelta(0):
            raise InvalidValueError("Execution timeout must be a positive duration.")


class ExecutionProvider(Protocol):
    """Port implemented by one external execution technology adapter."""

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation: ...


def request_execution(
    provider: ExecutionProvider, request: ExecutionRequest
) -> ExecutionProviderObservation:
    """Invoke the provider without interpreting its observation as Run outcome."""

    if not isinstance(request, ExecutionRequest):
        raise TypeError("Execution operation requires an ExecutionRequest.")
    observation = provider.execute(request)
    if not isinstance(observation, ExecutionProviderObservation):
        raise TypeError(
            "ExecutionProvider must return an ExecutionProviderObservation."
        )
    return observation


def execute_run(
    provider: ExecutionProvider,
    request: ExecutionRequest,
    execution_reproducibility: ReproducibilityAssessment,
) -> RunExecutionResult:
    """Execute, collect bounded outputs, seal evidence, and finalize one Run."""

    if not isinstance(request, ExecutionRequest):
        raise TypeError("Run execution requires an ExecutionRequest.")
    if not isinstance(execution_reproducibility, ReproducibilityAssessment):
        raise TypeError("Run execution requires a reproducibility assessment.")

    created_at = _now()
    started_at = _now()
    failure = None
    provider_exception = None
    try:
        observation = request_execution(provider, request)
    except Exception as error:
        observation = None
        provider_exception = error
        failure = ApplicationError(
            ApplicationErrorCode.EXECUTION_PROVIDER_FAILED,
            "Execution attempt failed.",
            request_id=request.context.request_id,
            cause=error,
        )
    finished_at = _now()

    collected: list[CollectedRawEvidence] = []
    if observation is None:
        run_status = (
            "cancelled" if isinstance(provider_exception, TimeoutError) else "failed"
        )
        evidence_outcome = EvidenceCollectionOutcome.COLLECTION_FAILED
    else:
        collection_failed = False
        for output in observation.captured_outputs:
            try:
                collected.append(_collect_output(output))
            except DomainError:
                collection_failed = True
                break
        run_status = _RUN_STATUS_BY_VERDICT[observation.verdict]
        evidence_outcome = (
            EvidenceCollectionOutcome.COLLECTION_FAILED
            if collection_failed
            else _EVIDENCE_OUTCOME_BY_VERDICT[observation.verdict]
        )
    manifest = RawEvidenceManifest(
        new_entity_id(RawEvidenceManifestId),
        request.run_id,
        tuple(item.evidence_object for item in collected),
        _now(),
        evidence_outcome,
    )
    manifest_document = _evidence_manifest_document(manifest)
    validate_document(manifest_document)
    manifest_payload = SchemaReferencedPayload(
        _RAW_EVIDENCE_MANIFEST_REF, manifest_document
    )
    manifest_digest = Sha256Digest(
        hashlib.sha256(_canonical_json_bytes(manifest_document)).hexdigest()
    )
    manifest_ref = RawEvidenceManifestRef(
        manifest.manifest_id,
        request.run_id,
        manifest_digest,
    )
    EvidenceProvenance(manifest, manifest_ref)

    run_provenance = RunProvenance(
        request.artifact.artifact_id,
        TestDefinitionRevisionId.parse(
            request.test_definition.value["test_definition_revision_id"]
        ),
        request.environment_configuration_id,
        request.environment_configuration,
        request.run_id,
        execution_reproducibility,
    )
    run_document = _run_manifest_document(
        run_provenance,
        run_status,
        created_at,
        started_at,
        finished_at,
        manifest_ref,
    )
    validate_document(run_document)
    return RunExecutionResult(
        SchemaReferencedPayload(_RUN_MANIFEST_REF, run_document),
        manifest,
        manifest_payload,
        manifest_ref,
        tuple(collected),
        observation,
        failure,
    )


_RUN_STATUS_BY_VERDICT = {
    ExecutionProviderVerdict.COMPLETED: "completed",
    ExecutionProviderVerdict.FAILED: "failed",
    ExecutionProviderVerdict.CANCELLED: "cancelled",
    ExecutionProviderVerdict.INCONCLUSIVE: "failed",
}
_EVIDENCE_OUTCOME_BY_VERDICT = {
    ExecutionProviderVerdict.COMPLETED: EvidenceCollectionOutcome.COMPLETED,
    ExecutionProviderVerdict.FAILED: EvidenceCollectionOutcome.FAILED,
    ExecutionProviderVerdict.CANCELLED: EvidenceCollectionOutcome.CANCELLED,
    ExecutionProviderVerdict.INCONCLUSIVE: EvidenceCollectionOutcome.FAILED,
}


def _collect_output(output: CapturedExecutionOutput) -> CollectedRawEvidence:
    digest = Sha256Digest(hashlib.sha256(output.content).hexdigest())
    return CollectedRawEvidence(
        RawEvidenceObject(
            new_entity_id(RawEvidenceObjectId),
            output.media_type,
            len(output.content),
            digest,
            output.payload_schema,
            output.provider_namespace,
        ),
        output.content,
    )


def _evidence_manifest_document(
    manifest: RawEvidenceManifest,
) -> dict[str, object]:
    objects = []
    for item in manifest.objects:
        document: dict[str, object] = {
            "object_id": str(item.object_id),
            "media_type": item.media_type,
            "byte_length": item.byte_length,
            "content_digest": str(item.content_digest),
        }
        if item.payload_schema is not None:
            document["payload_schema"] = str(item.payload_schema)
        if item.provider_namespace is not None:
            document["provider_namespace"] = item.provider_namespace
        objects.append(document)
    document = {
        "schema_name": str(_RAW_EVIDENCE_MANIFEST_REF.name),
        "schema_version": str(_RAW_EVIDENCE_MANIFEST_REF.version),
        "manifest_id": str(manifest.manifest_id),
        "run_id": str(manifest.run_id),
        "objects": objects,
        "sealed_at": str(manifest.sealed_at),
        "outcome": manifest.outcome.value,
    }
    if manifest.prior_manifest is not None:
        document["prior_manifest"] = {
            "manifest_id": str(manifest.prior_manifest.manifest_id),
            "run_id": str(manifest.prior_manifest.run_id),
            "content_digest": str(manifest.prior_manifest.content_digest),
        }
    return document


def _run_manifest_document(
    provenance: RunProvenance,
    status: str,
    created_at: UtcTimestamp,
    started_at: UtcTimestamp,
    finished_at: UtcTimestamp,
    manifest_ref: RawEvidenceManifestRef,
) -> dict[str, object]:
    return {
        "schema_name": str(_RUN_MANIFEST_REF.name),
        "schema_version": str(_RUN_MANIFEST_REF.version),
        "run_id": str(provenance.run_id),
        "test_definition_revision_id": str(
            provenance.test_definition_revision_id
        ),
        "artifact_id": str(provenance.artifact_id),
        "environment_configuration_id": str(
            provenance.environment_configuration_id
        ),
        "environment_configuration": {
            "schema_ref": str(provenance.environment_configuration.schema_ref),
            "value": _plain_json(provenance.environment_configuration.value),
        },
        "status": status,
        "created_at": str(created_at),
        "started_at": str(started_at),
        "finished_at": str(finished_at),
        "execution_reproducibility": {
            "level": provenance.execution_reproducibility.level.value,
            "reasons": [
                {"code": reason.code, "detail": reason.detail}
                for reason in provenance.execution_reproducibility.reasons
            ],
        },
        "raw_evidence_manifest": {
            "manifest_id": str(manifest_ref.manifest_id),
            "run_id": str(manifest_ref.run_id),
            "content_digest": str(manifest_ref.content_digest),
        },
    }


def _canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _now() -> UtcTimestamp:
    return UtcTimestamp(datetime.now(timezone.utc))


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value
