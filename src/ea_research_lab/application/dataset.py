"""Provider-neutral deterministic Dataset transformation boundary."""

from __future__ import annotations

import hashlib
import json
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.domain.errors import EvidenceInvariantError, InvalidValueError
from ea_research_lab.domain.identifiers import DatasetId, TransformationId
from ea_research_lab.domain.provenance import (
    DatasetProvenance,
    EvidenceProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)


_DATASET_MANIFEST_REF = SchemaRef(
    SchemaName("dataset-manifest"), SchemaVersion(0, 2, 0)
)


@dataclass(frozen=True, slots=True)
class TransformationRequest:
    """Exact sealed evidence and immutable transformation definition."""

    context: RequestContext
    evidence: EvidenceProvenance
    raw_evidence: tuple[CollectedRawEvidence, ...]
    transformation_id: TransformationId
    transformation_version: DefinitionVersion
    transformation_parameters: SchemaReferencedPayload | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, RequestContext)
            or not isinstance(self.evidence, EvidenceProvenance)
            or not isinstance(self.transformation_id, TransformationId)
            or not isinstance(self.transformation_version, DefinitionVersion)
            or (
                self.transformation_parameters is not None
                and not isinstance(
                    self.transformation_parameters, SchemaReferencedPayload
                )
            )
        ):
            raise InvalidValueError("Dataset transformation request is invalid.")
        try:
            supplied = tuple(self.raw_evidence)
        except TypeError as error:
            raise EvidenceInvariantError(
                "Dataset transformation requires exact Raw Evidence."
            ) from error
        if any(not isinstance(item, CollectedRawEvidence) for item in supplied):
            raise EvidenceInvariantError(
                "Dataset transformation contains invalid Raw Evidence."
            )
        supplied_ids = tuple(item.evidence_object.object_id for item in supplied)
        if len(set(supplied_ids)) != len(supplied_ids):
            raise EvidenceInvariantError(
                "Dataset transformation contains duplicate Raw Evidence identities."
            )
        declared = {
            item.object_id: item for item in self.evidence.manifest.objects
        }
        if set(supplied_ids) != set(declared):
            raise EvidenceInvariantError(
                "Dataset transformation evidence does not match its sealed manifest."
            )
        for item in supplied:
            descriptor = item.evidence_object
            if (
                descriptor != declared[descriptor.object_id]
                or len(item.content) != descriptor.byte_length
                or hashlib.sha256(item.content).hexdigest()
                != str(descriptor.content_digest)
            ):
                raise EvidenceInvariantError(
                    "Dataset transformation Raw Evidence identity is invalid."
                )
        object.__setattr__(
            self,
            "raw_evidence",
            tuple(
                sorted(
                    supplied,
                    key=lambda item: str(item.evidence_object.object_id),
                )
            ),
        )


class DatasetTransformer(Protocol):
    """One narrow transformation port for exact evidence."""

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload: ...


@dataclass(frozen=True, slots=True)
class DatasetTransformationOutcome:
    dataset: Dataset | None
    failure: ApplicationError | None

    def __post_init__(self) -> None:
        if (self.dataset is None) == (self.failure is None):
            raise InvalidValueError(
                "Dataset transformation outcome requires success or failure."
            )
        if self.dataset is not None and not isinstance(self.dataset, Dataset):
            raise InvalidValueError("Dataset transformation result is invalid.")
        if self.failure is not None and not isinstance(
            self.failure, ApplicationError
        ):
            raise InvalidValueError("Dataset transformation failure is invalid.")


def transform_dataset(
    transformer: DatasetTransformer,
    request: TransformationRequest,
) -> DatasetTransformationOutcome:
    """Transform one exact evidence set into an immutable in-memory Dataset."""

    if not isinstance(request, TransformationRequest):
        raise TypeError("Dataset transformation requires a TransformationRequest.")
    try:
        payload = transformer.transform(request)
        if not isinstance(payload, SchemaReferencedPayload):
            raise TypeError(
                "DatasetTransformer must return a SchemaReferencedPayload."
            )
        content = DatasetContent(payload)
    except Exception as error:
        return DatasetTransformationOutcome(
            None,
            ApplicationError(
                ApplicationErrorCode.DATASET_TRANSFORMATION_FAILED,
                "Dataset transformation failed.",
                request_id=request.context.request_id,
                cause=error,
            ),
        )

    dataset_id = new_entity_id(DatasetId)
    created_at = _now()
    provenance = DatasetProvenance(
        dataset_id,
        request.transformation_id,
        request.transformation_version,
        input_manifests=(request.evidence.manifest_ref,),
        transformation_parameters=request.transformation_parameters,
    )
    document = _dataset_manifest_document(
        provenance,
        created_at,
        payload.schema_ref,
        content.content_digest,
    )
    validate_document(document)
    return DatasetTransformationOutcome(
        Dataset(
            content,
            provenance,
            SchemaReferencedPayload(_DATASET_MANIFEST_REF, document),
            created_at,
        ),
        None,
    )


def _dataset_manifest_document(
    provenance: DatasetProvenance,
    created_at: UtcTimestamp,
    dataset_schema: SchemaRef,
    content_digest: Sha256Digest,
) -> dict[str, object]:
    document: dict[str, object] = {
        "schema_name": str(_DATASET_MANIFEST_REF.name),
        "schema_version": str(_DATASET_MANIFEST_REF.version),
        "dataset_id": str(provenance.dataset_id),
        "input_manifests": [
            {
                "manifest_id": str(reference.manifest_id),
                "run_id": str(reference.run_id),
                "content_digest": str(reference.content_digest),
            }
            for reference in provenance.input_manifests
        ],
        "input_datasets": [str(value) for value in provenance.input_datasets],
        "transformation_id": str(provenance.transformation_id),
        "transformation_version": str(provenance.transformation_version),
        "created_at": str(created_at),
        "dataset_schema": str(dataset_schema),
        "content_digest": str(content_digest),
    }
    if provenance.transformation_parameters is not None:
        document["transformation_parameters"] = {
            "schema_ref": str(provenance.transformation_parameters.schema_ref),
            "value": _plain_json(provenance.transformation_parameters.value),
        }
    return document


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _now() -> UtcTimestamp:
    return UtcTimestamp(datetime.now(timezone.utc))
