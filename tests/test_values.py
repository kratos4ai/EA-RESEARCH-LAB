import unittest
from dataclasses import FrozenInstanceError
from datetime import datetime, timedelta, timezone

from ea_research_lab.domain.errors import InvalidIdentifierError, InvalidValueError
from ea_research_lab.domain.identifiers import RunId
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    SourceRevision,
    UtcTimestamp,
)


class DomainValueTests(unittest.TestCase):
    def test_sha256_digest_is_distinct_from_entity_identity(self) -> None:
        digest = Sha256Digest("a" * 64)

        self.assertEqual(str(digest), "a" * 64)
        with self.assertRaises(InvalidValueError):
            Sha256Digest("A" * 64)
        with self.assertRaises(InvalidValueError):
            Sha256Digest("run_" + "a" * 64)
        with self.assertRaises(InvalidIdentifierError):
            RunId("a" * 64)

    def test_utc_timestamp_round_trips_with_z(self) -> None:
        timestamp = UtcTimestamp.parse("2026-08-09T12:34:56.123456Z")

        self.assertEqual(str(timestamp), "2026-08-09T12:34:56.123456Z")
        self.assertEqual(timestamp.value.tzinfo, timezone.utc)

    def test_timestamp_rejects_naive_non_utc_and_non_z_values(self) -> None:
        invalid_datetimes = (
            datetime(2026, 8, 9, 12, 0),
            datetime(2026, 8, 9, 12, 0, tzinfo=timezone(timedelta(hours=1))),
        )
        for value in invalid_datetimes:
            with self.subTest(value=value), self.assertRaises(InvalidValueError):
                UtcTimestamp(value)

        for value in (
            "2026-08-09T12:00:00+00:00",
            "2026-08-09 12:00:00Z",
            "2026-08-09T12:00:00.1234567Z",
        ):
            with self.subTest(value=value), self.assertRaises(InvalidValueError):
                UtcTimestamp.parse(value)

    def test_schema_values_and_urn_round_trip(self) -> None:
        schema_ref = SchemaRef(
            SchemaName("run-manifest"),
            SchemaVersion.parse("0.1.0"),
        )
        serialized = "urn:ea-research-lab:schema:run-manifest:0.1.0"

        self.assertEqual(str(schema_ref), serialized)
        self.assertEqual(SchemaRef.parse(serialized), schema_ref)

    def test_invalid_schema_names_and_versions_are_rejected(self) -> None:
        for name in ("RunManifest", "run_manifest", "-run", "run-", ""):
            with self.subTest(name=name), self.assertRaises(InvalidValueError):
                SchemaName(name)

        for version in ("1", "1.0", "01.0.0", "1.0.0-alpha", ""):
            with self.subTest(version=version), self.assertRaises(
                InvalidValueError
            ):
                SchemaVersion.parse(version)

        with self.assertRaises(InvalidValueError):
            SchemaRef.parse("https://example.test/run-manifest/1.0.0")

    def test_definition_version_is_opaque_but_nonempty(self) -> None:
        self.assertEqual(str(DefinitionVersion("git:abc123")), "git:abc123")
        for value in ("", " untrimmed", "untrimmed "):
            with self.subTest(value=value), self.assertRaises(InvalidValueError):
                DefinitionVersion(value)

    def test_source_revision_is_validated_and_frozen(self) -> None:
        revision = SourceRevision(
            vcs_kind="git",
            repository="ea-research-lab",
            revision="fcf494972267b2b0bd8bf197fbda0dcf11e537f9",
            is_dirty=False,
        )

        with self.assertRaises(FrozenInstanceError):
            revision.revision = "other"
        with self.assertRaises(InvalidValueError):
            SourceRevision("", "repository", "revision", False)
        with self.assertRaises(InvalidValueError):
            SourceRevision("git", "repository", "revision", 0)


if __name__ == "__main__":
    unittest.main()
