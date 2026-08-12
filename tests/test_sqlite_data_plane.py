from __future__ import annotations

import copy
import hashlib
import json
import sqlite3
import tempfile
import unittest
from collections.abc import Mapping
from contextlib import closing
from pathlib import Path

from ea_research_lab.application.build import (
    ArtifactAcceptance,
    BuildWorkflowResult,
)
from ea_research_lab.application.data_plane import (
    ARTIFACT_MANIFEST_REF,
    BUILD_INPUT_MANIFEST_REF,
    BUILD_RECORD_REF,
    DataPlaneError,
    DurableBuild,
)
from ea_research_lab.application.errors import (
    ApplicationErrorCode,
)
from ea_research_lab.contracts import ContractValidationError
from ea_research_lab.domain.build import (
    AcceptedArtifact,
    BuildOutcome,
    BuildProviderObservation,
)
from ea_research_lab.domain.identifiers import ArtifactId, BuildRecordId
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane


FIXTURES = Path(__file__).parent / "fixtures" / "schemas" / "valid"
BUILD_ID = BuildRecordId.parse(
    "build_0195395c-7c9e-7d91-8c2b-6d4f8e1a2b3c"
)
ARTIFACT_ID = ArtifactId.parse(
    "artifact_0195395c-7c9e-7e12-9d3c-7e5f9a2b3c4d"
)
CONFIGURATION_REF = SchemaRef(
    SchemaName("metaeditor-build-configuration"), SchemaVersion(0, 2, 0)
)
EVIDENCE_REF = SchemaRef(
    SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
)
SOURCE_REVISION = {
    "vcs_kind": "git",
    "repository": "ea-research-lab",
    "revision": "27f1c0c4d08ca5aaba07b10a360e86e403c7ce30",
    "is_dirty": False,
}
ARTIFACT_BYTES = b"\x00exact accepted artifact bytes\xff"


def _fixture(name: str) -> dict[str, object]:
    return json.loads((FIXTURES / name).read_text(encoding="utf-8"))


def _canonical(document: dict[str, object]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _payload(reference: SchemaRef, value: dict[str, object]):
    return SchemaReferencedPayload(reference, value)


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _successful_build() -> DurableBuild:
    build_input = _fixture("build-input-manifest.json")
    configuration = _fixture("metaeditor-build-configuration-v0.2.0.json")
    evidence = _fixture("metaeditor-build-evidence.json")
    binary_digest = hashlib.sha256(ARTIFACT_BYTES).hexdigest()
    artifact_manifest = {
        "schema_name": "artifact-manifest",
        "schema_version": "0.1.0",
        "artifact_id": str(ARTIFACT_ID),
        "logical_name": "phase06-build",
        "artifact_version": "m1",
        "build_record_id": str(BUILD_ID),
        "source_revision": SOURCE_REVISION,
        "binary_digest": binary_digest,
        "compiler": {
            "namespace": "metaeditor",
            "schema_ref": str(EVIDENCE_REF),
            "value": evidence,
        },
        "built_at": "2026-08-11T12:00:00Z",
    }
    build_record = {
        "schema_name": "build-record",
        "schema_version": "0.2.0",
        "build_record_id": str(BUILD_ID),
        "source_revision": SOURCE_REVISION,
        "build_input": {
            "schema_ref": str(BUILD_INPUT_MANIFEST_REF),
            "build_input_identity": build_input["build_input_identity"],
        },
        "build_configuration_id": (
            "envcfg_0195395c-7c9e-7e45-8a6f-1b3c5d7e9f01"
        ),
        "build_configuration": {
            "schema_ref": str(CONFIGURATION_REF),
            "value": configuration,
        },
        "provider_evidence": {
            "schema_ref": str(EVIDENCE_REF),
            "value": evidence,
        },
        "status": "succeeded",
        "artifact_id": str(ARTIFACT_ID),
    }
    artifact = AcceptedArtifact(
        ARTIFACT_ID,
        BUILD_ID,
        Sha256Digest(binary_digest),
        ARTIFACT_BYTES,
    )
    return DurableBuild(
        _payload(BUILD_RECORD_REF, build_record),
        _payload(BUILD_INPUT_MANIFEST_REF, build_input),
        ArtifactAcceptance(
            artifact,
            _payload(ARTIFACT_MANIFEST_REF, artifact_manifest),
        ),
    )


def _failed_build(*, with_input: bool) -> DurableBuild:
    successful = _successful_build()
    record = copy.deepcopy(_plain(successful.build_record.value))
    record["status"] = "failed"
    record.pop("artifact_id")
    build_input = successful.build_input_manifest if with_input else None
    if not with_input:
        record.pop("build_input")
        record.pop("provider_evidence")
    return DurableBuild(_payload(BUILD_RECORD_REF, record), build_input)


def _database_counts(database: Path) -> tuple[int, int]:
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        return (
            connection.execute("SELECT count(*) FROM content_objects").fetchone()[0],
            connection.execute("SELECT count(*) FROM published_records").fetchone()[0],
        )


def _replace_record_document(
    database: Path,
    kind: str,
    key: str,
    content: bytes,
) -> None:
    digest = hashlib.sha256(content).hexdigest()
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute(
            "INSERT OR REPLACE INTO content_objects VALUES (?, ?, ?)",
            (digest, len(content), content),
        )
        connection.execute(
            """
            UPDATE published_records
            SET document_digest = ?
            WHERE record_kind = ? AND record_key = ?
            """,
            (digest, kind, key),
        )


class SqliteBuildDataPlaneTests(unittest.TestCase):
    def test_successful_build_round_trips_exactly_after_close_and_reopen(self) -> None:
        build = _successful_build()
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
            with SqliteDataPlane(database) as fresh_data_plane:
                loaded = fresh_data_plane.load_build(BUILD_ID)

        self.assertIs(loaded.outcome, BuildOutcome.SUCCEEDED)
        self.assertEqual(loaded.build_record, build.build_record)
        self.assertEqual(loaded.build_input_manifest, build.build_input_manifest)
        self.assertEqual(
            loaded.artifact_acceptance.artifact_manifest,
            build.artifact_acceptance.artifact_manifest,
        )
        self.assertEqual(
            loaded.artifact_acceptance.artifact.content,
            ARTIFACT_BYTES,
        )
        self.assertEqual(
            loaded.artifact_acceptance.artifact.binary_digest,
            build.artifact_acceptance.artifact.binary_digest,
        )

    def test_durable_build_can_be_derived_from_the_actual_workflow_result(self) -> None:
        build = _successful_build()
        observation = BuildProviderObservation(
            _payload(
                EVIDENCE_REF,
                copy.deepcopy(_plain(build.build_record.value))["provider_evidence"][
                    "value"
                ],
            ),
            True,
        )
        workflow = BuildWorkflowResult(
            BuildOutcome.SUCCEEDED,
            build.build_record,
            build.build_input_manifest,
            observation,
            build.artifact_acceptance,
            None,
        )

        self.assertEqual(DurableBuild.from_workflow_result(workflow), build)

    def test_invalid_contract_document_is_rejected_before_publication(self) -> None:
        document = copy.deepcopy(_plain(_successful_build().build_record.value))
        document.pop("source_revision")

        with self.assertRaises(ContractValidationError):
            DurableBuild(_payload(BUILD_RECORD_REF, document))

    def test_failed_build_round_trips_with_or_without_build_input(self) -> None:
        for with_input in (True, False):
            with self.subTest(with_input=with_input):
                build = _failed_build(with_input=with_input)
                with tempfile.TemporaryDirectory() as name:
                    database = Path(name) / "lab.sqlite3"
                    with SqliteDataPlane(database) as data_plane:
                        data_plane.publish_build(build)
                    with SqliteDataPlane(database) as fresh_data_plane:
                        loaded = fresh_data_plane.load_build(BUILD_ID)

                self.assertIs(loaded.outcome, BuildOutcome.FAILED)
                self.assertEqual(loaded.build_record, build.build_record)
                self.assertEqual(loaded.build_input_manifest, build.build_input_manifest)
                self.assertIsNone(loaded.artifact_acceptance)

    def test_exact_duplicate_is_idempotent_and_conflicting_entity_fails(self) -> None:
        build = _failed_build(with_input=False)
        conflict_record = copy.deepcopy(_plain(build.build_record.value))
        conflict_record["source_revision"]["repository"] = "conflicting-source"
        conflict = DurableBuild(_payload(BUILD_RECORD_REF, conflict_record))
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                before = _database_counts(database)
                data_plane.publish_build(build)
                self.assertEqual(_database_counts(database), before)
                with self.assertRaises(DataPlaneError) as caught:
                    data_plane.publish_build(conflict)

            self.assertEqual(_database_counts(database), before)
        self.assertIs(
            caught.exception.code,
            ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        )

    def test_artifact_manifest_is_immutable(self) -> None:
        build = _successful_build()
        changed_document = copy.deepcopy(
            _plain(build.artifact_acceptance.artifact_manifest.value)
        )
        changed_document["logical_name"] = "changed-name"
        conflict = DurableBuild(
            build.build_record,
            build.build_input_manifest,
            ArtifactAcceptance(
                build.artifact_acceptance.artifact,
                _payload(ARTIFACT_MANIFEST_REF, changed_document),
            ),
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                before = _database_counts(database)
                with self.assertRaises(DataPlaneError) as caught:
                    data_plane.publish_build(conflict)
                self.assertEqual(_database_counts(database), before)

        self.assertIs(
            caught.exception.code,
            ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        )

    def test_conflicting_content_under_existing_digest_fails_closed(self) -> None:
        build = _successful_build()
        digest = str(build.artifact_acceptance.artifact.binary_digest)
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                with closing(
                    sqlite3.connect(database, isolation_level=None)
                ) as connection:
                    connection.execute(
                        """
                        UPDATE content_objects
                        SET byte_length = ?, content = ?
                        WHERE digest = ?
                        """,
                        (7, b"changed", digest),
                    )
                with self.assertRaises(DataPlaneError) as caught:
                    data_plane.publish_build(build)

        self.assertIs(
            caught.exception.code,
            ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        )

    def test_late_record_conflict_rolls_back_the_complete_publication(self) -> None:
        failed = _failed_build(with_input=False)
        successful = _successful_build()
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(failed)
                before = _database_counts(database)
                with self.assertRaises(DataPlaneError):
                    data_plane.publish_build(successful)
                self.assertEqual(_database_counts(database), before)
                self.assertEqual(data_plane.load_build(BUILD_ID), failed)

    def test_build_corruption_is_detected_without_repair(self) -> None:
        cases = (
            self._mutate_artifact_blob,
            self._mismatch_artifact_length,
            self._mismatch_artifact_digest,
            self._malform_build_record,
            self._break_artifact_reference,
            self._break_build_input_reference,
            self._mismatch_record_schema,
        )
        for mutate in cases:
            with self.subTest(case=mutate.__name__), tempfile.TemporaryDirectory() as name:
                database = Path(name) / "lab.sqlite3"
                with SqliteDataPlane(database) as data_plane:
                    data_plane.publish_build(_successful_build())
                mutate(database)
                with SqliteDataPlane(database) as fresh_data_plane:
                    with self.assertRaises(DataPlaneError) as caught:
                        fresh_data_plane.load_build(BUILD_ID)
                self.assertIs(
                    caught.exception.code,
                    ApplicationErrorCode.DATA_INTEGRITY_FAILED,
                )
                message = str(caught.exception).lower()
                self.assertNotIn(str(database).lower(), message)
                self.assertNotIn("select ", message)
                self.assertNotIn(ARTIFACT_BYTES.hex(), message)

    def test_foreign_keys_and_local_writer_conflict_are_safe(self) -> None:
        build = _successful_build()
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                self.assertEqual(
                    data_plane._connection.execute(
                        "PRAGMA foreign_keys"
                    ).fetchone()[0],
                    1,
                )
                locker = sqlite3.connect(database, isolation_level=None)
                locker.execute("BEGIN IMMEDIATE")
                try:
                    with self.assertRaises(DataPlaneError) as caught:
                        data_plane.publish_build(build)
                finally:
                    locker.execute("ROLLBACK")
                    locker.close()
                self.assertIs(
                    caught.exception.code,
                    ApplicationErrorCode.DATA_PLANE_FAILED,
                )
                data_plane.publish_build(build)

    @staticmethod
    def _mutate_artifact_blob(database: Path) -> None:
        digest = hashlib.sha256(ARTIFACT_BYTES).hexdigest()
        with closing(
            sqlite3.connect(database, isolation_level=None)
        ) as connection:
            connection.execute(
                "UPDATE content_objects SET content = ? WHERE digest = ?",
                (b"mutated artifact", digest),
            )

    @staticmethod
    def _mismatch_artifact_length(database: Path) -> None:
        digest = hashlib.sha256(ARTIFACT_BYTES).hexdigest()
        with closing(
            sqlite3.connect(database, isolation_level=None)
        ) as connection:
            connection.execute(
                "UPDATE content_objects SET byte_length = ? WHERE digest = ?",
                (len(ARTIFACT_BYTES) + 1, digest),
            )

    @staticmethod
    def _mismatch_artifact_digest(database: Path) -> None:
        build = _successful_build()
        document = copy.deepcopy(
            _plain(build.artifact_acceptance.artifact_manifest.value)
        )
        document["binary_digest"] = "f" * 64
        _replace_record_document(
            database,
            "artifact-manifest",
            str(ARTIFACT_ID),
            _canonical(document),
        )

    @staticmethod
    def _malform_build_record(database: Path) -> None:
        _replace_record_document(
            database,
            "build-record",
            str(BUILD_ID),
            b"{malformed",
        )

    @staticmethod
    def _break_artifact_reference(database: Path) -> None:
        document = copy.deepcopy(_plain(_successful_build().build_record.value))
        document["artifact_id"] = (
            "artifact_0195395c-7c9e-7f12-9d3c-7e5f9a2b3c4d"
        )
        _replace_record_document(
            database,
            "build-record",
            str(BUILD_ID),
            _canonical(document),
        )

    @staticmethod
    def _break_build_input_reference(database: Path) -> None:
        document = copy.deepcopy(_plain(_successful_build().build_record.value))
        document["build_input"]["build_input_identity"] = "f" * 64
        _replace_record_document(
            database,
            "build-record",
            str(BUILD_ID),
            _canonical(document),
        )

    @staticmethod
    def _mismatch_record_schema(database: Path) -> None:
        with closing(sqlite3.connect(database, isolation_level=None)) as connection:
            connection.execute(
                """
                UPDATE published_records
                SET schema_ref = ?
                WHERE record_kind = ? AND record_key = ?
                """,
                (str(ARTIFACT_MANIFEST_REF), "build-record", str(BUILD_ID)),
            )


if __name__ == "__main__":
    unittest.main()
