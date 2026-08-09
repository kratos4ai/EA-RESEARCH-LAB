import unittest
from dataclasses import FrozenInstanceError

from ea_research_lab.application.identity import new_entity_id
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
    RunId,
)
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)


def _raw_object(digest_character: str = "a") -> RawEvidenceObject:
    return RawEvidenceObject(
        object_id=new_entity_id(RawEvidenceObjectId),
        media_type="application/json",
        byte_length=128,
        content_digest=Sha256Digest(digest_character * 64),
        payload_schema=SchemaRef(
            SchemaName("telemetry-envelope"),
            SchemaVersion(0, 1, 0),
        ),
        provider_namespace="example.provider",
    )


def _sealed_manifest(
    run_id: RunId,
    objects: tuple[RawEvidenceObject, ...],
    outcome: EvidenceCollectionOutcome = EvidenceCollectionOutcome.COMPLETED,
    prior_manifest: RawEvidenceManifestRef | None = None,
) -> RawEvidenceManifest:
    return RawEvidenceManifest(
        manifest_id=new_entity_id(RawEvidenceManifestId),
        run_id=run_id,
        objects=objects,
        sealed_at=UtcTimestamp.parse("2026-08-09T15:00:00Z"),
        outcome=outcome,
        prior_manifest=prior_manifest,
    )


class RawEvidenceTests(unittest.TestCase):
    def test_object_keeps_entity_and_content_identity_distinct(self) -> None:
        raw_object = _raw_object()

        self.assertTrue(str(raw_object.object_id).startswith("rawobj_"))
        self.assertEqual(str(raw_object.content_digest), "a" * 64)
        with self.assertRaises(FrozenInstanceError):
            raw_object.byte_length = 129

    def test_invalid_object_metadata_is_rejected(self) -> None:
        object_id = new_entity_id(RawEvidenceObjectId)
        digest = Sha256Digest("a" * 64)

        for media_type, byte_length in (("json", 1), ("application/json", -1)):
            with self.subTest(
                media_type=media_type,
                byte_length=byte_length,
            ), self.assertRaises(EvidenceInvariantError):
                RawEvidenceObject(object_id, media_type, byte_length, digest)

        with self.assertRaises(EvidenceInvariantError):
            RawEvidenceObject(
                object_id,
                "application/json",
                1,
                object_id,
            )

    def test_sealed_manifest_is_immutable_and_rejects_duplicate_ids(self) -> None:
        run_id = new_entity_id(RunId)
        raw_object = _raw_object()
        manifest = _sealed_manifest(run_id, (raw_object,))

        self.assertIsInstance(manifest.objects, tuple)
        with self.assertRaises(FrozenInstanceError):
            manifest.outcome = EvidenceCollectionOutcome.FAILED
        with self.assertRaises(EvidenceInvariantError):
            _sealed_manifest(run_id, (raw_object, raw_object))

    def test_terminal_outcomes_can_preserve_available_evidence(self) -> None:
        self.assertNotIn(
            "collecting",
            {outcome.value for outcome in EvidenceCollectionOutcome},
        )
        for outcome in EvidenceCollectionOutcome:
            with self.subTest(outcome=outcome):
                manifest = _sealed_manifest(
                    new_entity_id(RunId),
                    (_raw_object(),),
                    outcome,
                )
                self.assertEqual(manifest.outcome, outcome)
                self.assertEqual(len(manifest.objects), 1)

    def test_manifest_digest_is_external_to_sealed_manifest(self) -> None:
        manifest = _sealed_manifest(new_entity_id(RunId), (_raw_object(),))
        manifest_ref = RawEvidenceManifestRef(
            manifest_id=manifest.manifest_id,
            run_id=manifest.run_id,
            content_digest=Sha256Digest("b" * 64),
        )

        self.assertFalse(hasattr(manifest, "content_digest"))
        self.assertEqual(str(manifest_ref.content_digest), "b" * 64)

    def test_late_evidence_creates_a_linked_new_manifest(self) -> None:
        run_id = new_entity_id(RunId)
        first_object = _raw_object("a")
        first_manifest = _sealed_manifest(run_id, (first_object,))
        first_ref = RawEvidenceManifestRef(
            first_manifest.manifest_id,
            run_id,
            Sha256Digest("b" * 64),
        )

        late_object = _raw_object("c")
        revised_manifest = _sealed_manifest(
            run_id,
            (first_object, late_object),
            prior_manifest=first_ref,
        )

        self.assertNotEqual(first_manifest.manifest_id, revised_manifest.manifest_id)
        self.assertEqual(revised_manifest.prior_manifest, first_ref)
        self.assertEqual(first_manifest.objects, (first_object,))

    def test_prior_revision_must_reference_another_manifest_for_same_run(self) -> None:
        run_id = new_entity_id(RunId)
        other_run_id = new_entity_id(RunId)
        manifest_id = new_entity_id(RawEvidenceManifestId)
        wrong_run_ref = RawEvidenceManifestRef(
            new_entity_id(RawEvidenceManifestId),
            other_run_id,
            Sha256Digest("d" * 64),
        )

        with self.assertRaises(EvidenceInvariantError):
            RawEvidenceManifest(
                manifest_id,
                run_id,
                (_raw_object(),),
                UtcTimestamp.parse("2026-08-09T15:00:00Z"),
                EvidenceCollectionOutcome.COMPLETED,
                wrong_run_ref,
            )

        self_ref = RawEvidenceManifestRef(
            manifest_id,
            run_id,
            Sha256Digest("e" * 64),
        )
        with self.assertRaises(EvidenceInvariantError):
            RawEvidenceManifest(
                manifest_id,
                run_id,
                (_raw_object(),),
                UtcTimestamp.parse("2026-08-09T15:00:00Z"),
                EvidenceCollectionOutcome.COMPLETED,
                self_ref,
            )


if __name__ == "__main__":
    unittest.main()
