"""Immutable raw evidence descriptors and sealed manifest records."""

import re
from dataclasses import dataclass
from enum import StrEnum

from ea_research_lab.domain.errors import EvidenceInvariantError
from ea_research_lab.domain.identifiers import (
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RunId,
)
from ea_research_lab.domain.values import Sha256Digest, SchemaRef, UtcTimestamp


_MEDIA_TYPE_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")


class EvidenceCollectionOutcome(StrEnum):
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    COLLECTION_FAILED = "collection_failed"


@dataclass(frozen=True, slots=True)
class RawEvidenceObject:
    object_id: RawEvidenceObjectId
    media_type: str
    byte_length: int
    content_digest: Sha256Digest
    payload_schema: SchemaRef | None = None
    provider_namespace: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.object_id, RawEvidenceObjectId):
            raise EvidenceInvariantError(
                "Raw evidence object requires a RawEvidenceObjectId."
            )
        if not isinstance(self.media_type, str) or not _MEDIA_TYPE_PATTERN.fullmatch(
            self.media_type
        ):
            raise EvidenceInvariantError(
                "Raw evidence media type must use type/subtype form."
            )
        if type(self.byte_length) is not int or self.byte_length < 0:
            raise EvidenceInvariantError(
                "Raw evidence byte length must be a non-negative integer."
            )
        if not isinstance(self.content_digest, Sha256Digest):
            raise EvidenceInvariantError(
                "Raw evidence content requires a SHA-256 digest."
            )
        if self.payload_schema is not None and not isinstance(
            self.payload_schema, SchemaRef
        ):
            raise EvidenceInvariantError(
                "Raw evidence payload schema must be a SchemaRef."
            )
        if self.provider_namespace is not None and (
            not isinstance(self.provider_namespace, str)
            or not self.provider_namespace
            or self.provider_namespace.strip() != self.provider_namespace
        ):
            raise EvidenceInvariantError(
                "Provider namespace must be non-empty and trimmed when provided."
            )


@dataclass(frozen=True, slots=True)
class RawEvidenceManifestRef:
    """Exact manifest reference with a digest external to manifest bytes."""

    manifest_id: RawEvidenceManifestId
    run_id: RunId
    content_digest: Sha256Digest

    def __post_init__(self) -> None:
        if not isinstance(self.manifest_id, RawEvidenceManifestId):
            raise EvidenceInvariantError(
                "Manifest reference requires a RawEvidenceManifestId."
            )
        if not isinstance(self.run_id, RunId):
            raise EvidenceInvariantError("Manifest reference requires a RunId.")
        if not isinstance(self.content_digest, Sha256Digest):
            raise EvidenceInvariantError(
                "Manifest reference requires an external SHA-256 digest."
            )


@dataclass(frozen=True, slots=True)
class RawEvidenceManifest:
    manifest_id: RawEvidenceManifestId
    run_id: RunId
    objects: tuple[RawEvidenceObject, ...]
    sealed_at: UtcTimestamp
    outcome: EvidenceCollectionOutcome
    prior_manifest: RawEvidenceManifestRef | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.manifest_id, RawEvidenceManifestId):
            raise EvidenceInvariantError(
                "Sealed manifest requires a RawEvidenceManifestId."
            )
        if not isinstance(self.run_id, RunId):
            raise EvidenceInvariantError("Sealed manifest requires a RunId.")
        try:
            objects = tuple(self.objects)
        except TypeError as error:
            raise EvidenceInvariantError(
                "Sealed manifest objects must be an ordered collection."
            ) from error
        if any(not isinstance(item, RawEvidenceObject) for item in objects):
            raise EvidenceInvariantError(
                "Sealed manifest members must be RawEvidenceObject values."
            )
        object_ids = tuple(item.object_id for item in objects)
        if len(set(object_ids)) != len(object_ids):
            raise EvidenceInvariantError(
                "Sealed manifest cannot contain duplicate raw evidence object IDs."
            )
        if not isinstance(self.sealed_at, UtcTimestamp):
            raise EvidenceInvariantError(
                "Sealed manifest requires an explicit UTC sealing timestamp."
            )
        if not isinstance(self.outcome, EvidenceCollectionOutcome):
            raise EvidenceInvariantError(
                "Sealed manifest requires a terminal evidence collection outcome."
            )
        if self.prior_manifest is not None:
            if not isinstance(self.prior_manifest, RawEvidenceManifestRef):
                raise EvidenceInvariantError(
                    "Prior manifest revision must be a RawEvidenceManifestRef."
                )
            if self.prior_manifest.run_id != self.run_id:
                raise EvidenceInvariantError(
                    "Prior manifest revision must belong to the same run."
                )
            if self.prior_manifest.manifest_id == self.manifest_id:
                raise EvidenceInvariantError(
                    "A sealed manifest cannot reference itself as its prior revision."
                )
        object.__setattr__(self, "objects", objects)
