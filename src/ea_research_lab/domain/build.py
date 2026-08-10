"""Provider-neutral build values."""

import hashlib
from dataclasses import dataclass
from enum import StrEnum

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import ArtifactId, BuildRecordId
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import Sha256Digest


class BuildOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BuildInputScope(StrEnum):
    WORKSPACE = "workspace"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class BuildProviderObservation:
    """Opaque provider evidence that is not a final platform outcome."""

    provider_evidence: SchemaReferencedPayload
    candidate_available: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_evidence, SchemaReferencedPayload):
            raise InvalidValueError(
                "Build provider observation requires schema-referenced evidence."
            )
        if type(self.candidate_available) is not bool:
            raise InvalidValueError(
                "Build provider candidate availability must be a boolean."
            )


@dataclass(frozen=True, slots=True)
class AcceptedArtifact:
    """Accepted immutable bytes with separate entity and content identities."""

    artifact_id: ArtifactId
    build_record_id: BuildRecordId
    binary_digest: Sha256Digest
    content: bytes

    def __post_init__(self) -> None:
        required = (
            (self.artifact_id, ArtifactId, "ArtifactId"),
            (self.build_record_id, BuildRecordId, "BuildRecordId"),
            (self.binary_digest, Sha256Digest, "binary digest"),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise InvalidValueError(f"Accepted Artifact requires {label}.")
        if not isinstance(self.content, bytes):
            raise InvalidValueError("Accepted Artifact content must be immutable bytes.")
        if hashlib.sha256(self.content).hexdigest() != str(self.binary_digest):
            raise InvalidValueError(
                "Accepted Artifact digest must identify its exact content."
            )
