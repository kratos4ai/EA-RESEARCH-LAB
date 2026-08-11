"""Immutable provider-neutral Analysis Result values."""

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass, field

from ea_research_lab.domain.dataset import Dataset
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.provenance import (
    AnalysisProvenance,
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
class AnalysisContent:
    """Schema-identified deterministic analytical content."""

    payload: SchemaReferencedPayload
    canonical_bytes: bytes = field(init=False, repr=False)
    content_digest: Sha256Digest = field(init=False)

    def __post_init__(self) -> None:
        if not isinstance(self.payload, SchemaReferencedPayload):
            raise InvalidValueError(
                "Analysis content requires a schema-referenced payload."
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
                "Analysis content cannot be serialized deterministically."
            ) from error
        object.__setattr__(self, "canonical_bytes", content)
        object.__setattr__(
            self,
            "content_digest",
            Sha256Digest(hashlib.sha256(content).hexdigest()),
        )


@dataclass(frozen=True, slots=True)
class AnalysisResult:
    """One immutable in-memory Analysis Result and its exact envelope."""

    content: AnalysisContent
    provenance: AnalysisProvenance
    input_datasets: tuple[Dataset, ...]
    envelope: SchemaReferencedPayload
    created_at: UtcTimestamp

    def __post_init__(self) -> None:
        if (
            not isinstance(self.content, AnalysisContent)
            or not isinstance(self.provenance, AnalysisProvenance)
            or not isinstance(self.envelope, SchemaReferencedPayload)
            or not isinstance(self.created_at, UtcTimestamp)
        ):
            raise InvalidValueError("Analysis Result is invalid.")
        try:
            datasets = tuple(self.input_datasets)
        except TypeError as error:
            raise InvalidValueError(
                "Analysis Result requires its input Datasets."
            ) from error
        if (
            not datasets
            or any(not isinstance(item, Dataset) for item in datasets)
            or tuple(item.provenance.dataset_id for item in datasets)
            != self.provenance.input_dataset_ids
        ):
            raise InvalidValueError("Analysis Result Dataset provenance is invalid.")
        object.__setattr__(self, "input_datasets", datasets)
