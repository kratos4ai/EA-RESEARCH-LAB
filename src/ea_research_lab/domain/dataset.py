"""Immutable provider-neutral Dataset values."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.provenance import (
    DatasetProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import Sha256Digest, UtcTimestamp


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class DatasetContent:
    """Schema-identified content with deterministic canonical byte identity."""

    payload: SchemaReferencedPayload
    canonical_bytes: bytes = field(init=False, repr=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.payload, SchemaReferencedPayload):
            raise InvalidValueError(
                "Dataset content requires a schema-referenced payload."
            )
        try:
            content = json.dumps(
                _plain_json(self.payload.value),
                ensure_ascii=False,
                sort_keys=True,
                separators=(",", ":"),
                allow_nan=False,
            ).encode("utf-8")
        except (TypeError, ValueError) as error:
            raise InvalidValueError(
                "Dataset content cannot be serialized deterministically."
            ) from error
        object.__setattr__(self, "canonical_bytes", content)
        object.__setattr__(
            self,
            "content_digest",
            Sha256Digest(hashlib.sha256(content).hexdigest()),
        )


@dataclass(frozen=True, slots=True)
class Dataset:
    """One immutable in-memory Dataset and its content-identified manifest."""

    content: DatasetContent
    provenance: DatasetProvenance
    manifest: SchemaReferencedPayload
    created_at: UtcTimestamp

    def __post_init__(self) -> None:
        if (
            not isinstance(self.content, DatasetContent)
            or not isinstance(self.provenance, DatasetProvenance)
            or not isinstance(self.manifest, SchemaReferencedPayload)
            or not isinstance(self.created_at, UtcTimestamp)
        ):
            raise InvalidValueError("Dataset is invalid.")
