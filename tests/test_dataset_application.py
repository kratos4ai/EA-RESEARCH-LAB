from __future__ import annotations

import hashlib
import unittest
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from unittest.mock import patch

import ea_research_lab.application.dataset as dataset_application
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.dataset import (
    DatasetTransformer,
    TransformationRequest,
    transform_dataset,
)
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.errors import EvidenceInvariantError
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
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


def _ref(name: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0))


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _collected(content: bytes) -> CollectedRawEvidence:
    return CollectedRawEvidence(
        RawEvidenceObject(
            new_entity_id(RawEvidenceObjectId),
            "application/octet-stream",
            len(content),
            Sha256Digest(hashlib.sha256(content).hexdigest()),
        ),
        content,
    )


def _evidence(
    *contents: bytes,
) -> tuple[EvidenceProvenance, tuple[CollectedRawEvidence, ...]]:
    collected = tuple(_collected(content) for content in contents)
    manifest = RawEvidenceManifest(
        new_entity_id(RawEvidenceManifestId),
        new_entity_id(RunId),
        tuple(item.evidence_object for item in collected),
        UtcTimestamp.parse("2026-08-11T10:00:00Z"),
        EvidenceCollectionOutcome.COMPLETED,
    )
    reference = RawEvidenceManifestRef(
        manifest.manifest_id,
        manifest.run_id,
        Sha256Digest("a" * 64),
    )
    return EvidenceProvenance(manifest, reference), collected


def _request(
    evidence: EvidenceProvenance,
    collected: tuple[CollectedRawEvidence, ...],
) -> TransformationRequest:
    return TransformationRequest(
        RequestContext(new_entity_id(RequestId), "dataset-test"),
        evidence,
        collected,
        new_entity_id(TransformationId),
        DefinitionVersion("fake-1"),
        SchemaReferencedPayload(_ref("fake-transformation-parameters"), {"mode": "x"}),
    )


class _FakeTransformer:
    def __init__(self) -> None:
        self.requests: list[TransformationRequest] = []

    def transform(self, request: TransformationRequest) -> SchemaReferencedPayload:
        self.requests.append(request)
        return SchemaReferencedPayload(
            _ref("fake-dataset-content"),
            {
                "objects": [
                    {
                        "id": str(item.evidence_object.object_id),
                        "digest": str(item.evidence_object.content_digest),
                    }
                    for item in request.raw_evidence
                ],
                "mode": request.transformation_parameters.value["mode"],
            },
        )


class DatasetTransformationTests(unittest.TestCase):
    def test_identical_inputs_preserve_content_not_entity_identity(self) -> None:
        evidence, collected = _evidence(b"first", b"second")
        request = _request(evidence, collected)
        transformer: DatasetTransformer = _FakeTransformer()
        timestamps = (
            UtcTimestamp.parse("2026-08-11T10:01:00Z"),
            UtcTimestamp.parse("2026-08-11T10:02:00Z"),
        )

        with patch.object(dataset_application, "_now", side_effect=timestamps):
            first = transform_dataset(transformer, request).dataset
            second = transform_dataset(transformer, request).dataset

        self.assertNotEqual(first.provenance.dataset_id, second.provenance.dataset_id)
        self.assertNotEqual(first.created_at, second.created_at)
        self.assertEqual(first.content.canonical_bytes, second.content.canonical_bytes)
        self.assertEqual(first.content.content_digest, second.content.content_digest)
        self.assertEqual(
            str(first.content.content_digest),
            hashlib.sha256(first.content.canonical_bytes).hexdigest(),
        )

    def test_evidence_input_order_is_normalized_before_transformation(self) -> None:
        evidence, collected = _evidence(b"first", b"second")
        forward = _request(evidence, collected)
        reverse = _request(evidence, tuple(reversed(collected)))

        first = transform_dataset(_FakeTransformer(), forward).dataset
        second = transform_dataset(_FakeTransformer(), reverse).dataset

        self.assertEqual(first.content.canonical_bytes, second.content.canonical_bytes)
        self.assertEqual(first.content.content_digest, second.content.content_digest)

    def test_missing_extra_and_identity_mismatched_evidence_are_rejected(self) -> None:
        evidence, collected = _evidence(b"first", b"second")
        extra = _collected(b"extra")
        replacements = (
            collected[:-1],
            (*collected, extra),
            (collected[0], extra),
        )

        for supplied in replacements:
            with self.subTest(size=len(supplied)), self.assertRaises(
                EvidenceInvariantError
            ):
                _request(evidence, supplied)

    def test_duplicate_evidence_identity_is_rejected(self) -> None:
        evidence, collected = _evidence(b"first")

        with self.assertRaises(EvidenceInvariantError):
            _request(evidence, (collected[0], collected[0]))

    def test_tampered_evidence_length_and_digest_are_rejected(self) -> None:
        for tampered_content in (b"longer", b"xxxxx"):
            with self.subTest(content=tampered_content):
                evidence, collected = _evidence(b"first")
                object.__setattr__(collected[0], "content", tampered_content)
                with self.assertRaises(EvidenceInvariantError):
                    _request(evidence, collected)

    def test_raw_evidence_and_dataset_content_remain_immutable(self) -> None:
        evidence, collected = _evidence(b"first")
        before = (collected[0].evidence_object, collected[0].content)

        dataset = transform_dataset(
            _FakeTransformer(), _request(evidence, collected)
        ).dataset

        self.assertEqual(
            (collected[0].evidence_object, collected[0].content),
            before,
        )
        with self.assertRaises(FrozenInstanceError):
            dataset.content.canonical_bytes = b"changed"
        with self.assertRaises(TypeError):
            dataset.content.payload.value["new"] = "value"
        with self.assertRaises(TypeError):
            dataset.content.payload.value["objects"][0]["id"] = "changed"

    def test_manifest_validates_and_binds_content_provenance(self) -> None:
        evidence, collected = _evidence(b"first")
        request = _request(evidence, collected)

        outcome = transform_dataset(_FakeTransformer(), request)
        dataset = outcome.dataset
        document = dataset.manifest.value

        self.assertIsNone(outcome.failure)
        validate_document(_plain(document))
        self.assertEqual(
            str(dataset.manifest.schema_ref),
            "urn:ea-research-lab:schema:dataset-manifest:0.2.0",
        )
        self.assertEqual(document["schema_version"], "0.2.0")
        self.assertEqual(
            dataset.provenance.input_manifests,
            (evidence.manifest_ref,),
        )
        self.assertEqual(
            document["input_manifests"][0]["run_id"],
            str(evidence.manifest.run_id),
        )
        self.assertEqual(
            document["content_digest"],
            str(dataset.content.content_digest),
        )

    def test_fake_transformer_is_usable_and_failure_is_safe(self) -> None:
        evidence, collected = _evidence(b"secret evidence bytes")
        request = _request(evidence, collected)
        transformer = _FakeTransformer()

        success = transform_dataset(transformer, request)

        self.assertEqual(transformer.requests, [request])
        self.assertIsNotNone(success.dataset)

        class FailingTransformer:
            def transform(self, request: TransformationRequest) -> object:
                raise RuntimeError("secret provider log and payload")

        failure = transform_dataset(FailingTransformer(), request)
        serialized = failure.failure.to_dict()
        self.assertIsNone(failure.dataset)
        self.assertEqual(serialized["code"], "dataset_transformation_failed")
        self.assertNotIn("secret", str(serialized))


if __name__ == "__main__":
    unittest.main()
