"""SQLite Data Plane adapter for immutable durable Build facts."""

from __future__ import annotations

import hashlib
import json
import sqlite3
from collections.abc import Mapping
from pathlib import Path

from ea_research_lab.application.build import ArtifactAcceptance
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.application.data_plane import (
    ANALYSIS_RESULT_REF,
    ARTIFACT_MANIFEST_REF,
    BUILD_INPUT_MANIFEST_REF,
    BUILD_RECORD_REF,
    DATASET_MANIFEST_REF,
    RAW_EVIDENCE_MANIFEST_REF,
    RUN_MANIFEST_REF,
    TEST_DEFINITION_REF,
    DataPlaneError,
    DurableBuild,
    DurableEvidence,
    DurableRun,
    validate_analysis,
    validate_dataset,
)
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.analysis import AnalysisContent, AnalysisResult
from ea_research_lab.domain.build import AcceptedArtifact, BuildOutcome
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.domain.errors import DomainError
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RunId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
    AnalysisProvenance,
    DatasetProvenance,
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    SchemaRef,
    Sha256Digest,
    UtcTimestamp,
)


_BUILD_RECORD_KIND = "build-record"
_BUILD_INPUT_KIND = "build-input-manifest"
_ARTIFACT_MANIFEST_KIND = "artifact-manifest"
_TEST_DEFINITION_KIND = "test-definition"
_RUN_MANIFEST_KIND = "run-manifest"
_RAW_EVIDENCE_MANIFEST_KIND = "raw-evidence-manifest"
_RAW_EVIDENCE_OBJECT_KIND = "raw-evidence-object"
_DATASET_MANIFEST_KIND = "dataset-manifest"
_ANALYSIS_RESULT_KIND = "analysis-result"


class SqliteDataPlane:
    """One local SQLite connection; concurrent writers rely on SQLite locking."""

    def __init__(self, database_path: Path, *, read_only: bool = False) -> None:
        if not isinstance(database_path, Path):
            raise TypeError("SQLite Data Plane requires a Path.")
        if type(read_only) is not bool:
            raise TypeError("SQLite Data Plane read-only mode must be boolean.")
        connection: sqlite3.Connection | None = None
        try:
            connection = (
                sqlite3.connect(
                    f"{database_path.resolve().as_uri()}?mode=ro",
                    uri=True,
                    timeout=0,
                    isolation_level=None,
                )
                if read_only
                else sqlite3.connect(
                    database_path,
                    timeout=0,
                    isolation_level=None,
                )
            )
            connection.execute("PRAGMA foreign_keys = ON")
            if read_only:
                connection.execute("PRAGMA query_only = ON")
            else:
                connection.executescript(
                    """
                    CREATE TABLE IF NOT EXISTS content_objects (
                        digest TEXT PRIMARY KEY,
                        byte_length INTEGER NOT NULL CHECK (byte_length >= 0),
                        content BLOB NOT NULL
                    );
                    CREATE TABLE IF NOT EXISTS published_records (
                        record_kind TEXT NOT NULL,
                        record_key TEXT NOT NULL,
                        schema_ref TEXT NOT NULL,
                        document_digest TEXT NOT NULL,
                        PRIMARY KEY (record_kind, record_key),
                        FOREIGN KEY (document_digest)
                            REFERENCES content_objects(digest)
                    );
                    """
                )
        except sqlite3.Error as error:
            if connection is not None:
                connection.close()
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Data Plane could not be opened.",
            ) from error
        self._connection: sqlite3.Connection | None = connection

    def __enter__(self) -> SqliteDataPlane:
        self._require_connection()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def publish_build(self, build: DurableBuild) -> None:
        if not isinstance(build, DurableBuild):
            raise TypeError("Build publication requires DurableBuild facts.")
        try:
            build = DurableBuild(
                build.build_record,
                build.build_input_manifest,
                build.artifact_acceptance,
            )
        except (
            DomainError,
            ContractValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise _integrity_error(
                "Build publication failed integrity checks."
            ) from error

        connection = self._require_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            if build.build_input_manifest is not None:
                self._store_document(
                    _BUILD_INPUT_KIND,
                    build.build_input_manifest.value["build_input_identity"],
                    build.build_input_manifest,
                )
            if build.artifact_acceptance is not None:
                accepted = build.artifact_acceptance
                self._store_content(
                    accepted.artifact.binary_digest,
                    accepted.artifact.content,
                )
                self._store_document(
                    _ARTIFACT_MANIFEST_KIND,
                    str(accepted.artifact.artifact_id),
                    accepted.artifact_manifest,
                )
            self._store_document(
                _BUILD_RECORD_KIND,
                str(build.build_record_id),
                build.build_record,
            )
            connection.execute("COMMIT")
        except DataPlaneError:
            _rollback(connection)
            raise
        except sqlite3.Error as error:
            _rollback(connection)
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Build publication failed.",
            ) from error

    def load_build(self, build_record_id: BuildRecordId) -> DurableBuild:
        if not isinstance(build_record_id, BuildRecordId):
            raise TypeError("Build load requires a BuildRecordId.")
        self._require_connection()
        try:
            record = self._load_document(
                _BUILD_RECORD_KIND,
                str(build_record_id),
                BUILD_RECORD_REF,
                missing_is_integrity=False,
            )
            document = _plain(record.value)
            if document["build_record_id"] != str(build_record_id):
                raise _integrity_error("Durable Build identity is inconsistent.")

            build_input = None
            if "build_input" in document:
                reference = document["build_input"]
                build_input = self._load_document(
                    _BUILD_INPUT_KIND,
                    reference["build_input_identity"],
                    BUILD_INPUT_MANIFEST_REF,
                )

            artifact_acceptance = None
            if document["status"] == BuildOutcome.SUCCEEDED.value:
                artifact_id = ArtifactId.parse(document["artifact_id"])
                artifact_manifest = self._load_document(
                    _ARTIFACT_MANIFEST_KIND,
                    str(artifact_id),
                    ARTIFACT_MANIFEST_REF,
                )
                manifest = _plain(artifact_manifest.value)
                binary_digest = Sha256Digest(manifest["binary_digest"])
                content = self._load_content(binary_digest)
                artifact_acceptance = ArtifactAcceptance(
                    AcceptedArtifact(
                        artifact_id,
                        build_record_id,
                        binary_digest,
                        content,
                    ),
                    artifact_manifest,
                )
            return DurableBuild(record, build_input, artifact_acceptance)
        except DataPlaneError:
            raise
        except (
            ContractValidationError,
            DomainError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            raise _integrity_error("Durable Build failed integrity checks.") from error
        except sqlite3.Error as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable Build could not be loaded.",
            ) from error

    def publish_run(self, run: DurableRun) -> None:
        if not isinstance(run, DurableRun):
            raise TypeError("Run publication requires DurableRun facts.")
        try:
            run = DurableRun(
                run.test_definition,
                run.run_manifest,
                run.evidence_history,
            )
        except (
            DomainError,
            ContractValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise _integrity_error(
                "Run publication failed integrity checks."
            ) from error

        connection = self._require_connection()
        try:
            connection.execute("BEGIN IMMEDIATE")
            run_document = _plain(run.run_manifest.value)
            self._require_artifact(run_document["artifact_id"])
            self._store_document(
                _TEST_DEFINITION_KIND,
                str(run.test_definition_revision_id),
                run.test_definition,
            )
            for evidence in run.evidence_history:
                self._store_evidence(evidence)
            self._store_document(
                _RUN_MANIFEST_KIND,
                str(run.run_id),
                run.run_manifest,
            )
            connection.execute("COMMIT")
        except DataPlaneError:
            _rollback(connection)
            raise
        except sqlite3.Error as error:
            _rollback(connection)
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Run publication failed.",
            ) from error

    def load_run(self, run_id: RunId) -> DurableRun:
        if not isinstance(run_id, RunId):
            raise TypeError("Run load requires a RunId.")
        try:
            run_manifest = self._load_document(
                _RUN_MANIFEST_KIND,
                str(run_id),
                RUN_MANIFEST_REF,
                missing_is_integrity=False,
            )
            run = _plain(run_manifest.value)
            if run["run_id"] != str(run_id):
                raise _integrity_error("Durable Run identity is inconsistent.")
            self._require_artifact(run["artifact_id"])
            test_revision = TestDefinitionRevisionId.parse(
                run["test_definition_revision_id"]
            )
            test_definition = self._load_document(
                _TEST_DEFINITION_KIND,
                str(test_revision),
                TEST_DEFINITION_REF,
            )
            reference = _evidence_reference(run["raw_evidence_manifest"])
            history = self._load_evidence_history(reference, set())
            return DurableRun(test_definition, run_manifest, history)
        except DataPlaneError:
            raise
        except (
            ContractValidationError,
            DomainError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            raise _integrity_error("Durable Run failed integrity checks.") from error
        except sqlite3.Error as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable Run could not be loaded.",
            ) from error

    def publish_dataset(self, dataset: Dataset) -> None:
        try:
            validate_dataset(dataset)
        except (
            DomainError,
            ContractValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise _integrity_error(
                "Dataset publication failed integrity checks."
            ) from error
        connection = self._require_connection()
        document = _plain(dataset.manifest.value)
        try:
            connection.execute("BEGIN IMMEDIATE")
            for reference in document["input_manifests"]:
                self._require_evidence_reference(_evidence_reference(reference))
            for input_id in document["input_datasets"]:
                self._load_document(
                    _DATASET_MANIFEST_KIND,
                    input_id,
                    DATASET_MANIFEST_REF,
                )
            self._store_content(
                dataset.content.content_digest,
                dataset.content.canonical_bytes,
            )
            self._store_document(
                _DATASET_MANIFEST_KIND,
                str(dataset.provenance.dataset_id),
                dataset.manifest,
            )
            connection.execute("COMMIT")
        except DataPlaneError:
            _rollback(connection)
            raise
        except sqlite3.Error as error:
            _rollback(connection)
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Dataset publication failed.",
            ) from error

    def load_dataset(self, dataset_id: DatasetId) -> Dataset:
        if not isinstance(dataset_id, DatasetId):
            raise TypeError("Dataset load requires a DatasetId.")
        try:
            manifest = self._load_document(
                _DATASET_MANIFEST_KIND,
                str(dataset_id),
                DATASET_MANIFEST_REF,
                missing_is_integrity=False,
            )
            document = _plain(manifest.value)
            if document["dataset_id"] != str(dataset_id):
                raise _integrity_error("Durable Dataset identity is inconsistent.")
            for reference in document["input_manifests"]:
                self._require_evidence_reference(_evidence_reference(reference))
            for input_id in document["input_datasets"]:
                self._load_document(
                    _DATASET_MANIFEST_KIND,
                    input_id,
                    DATASET_MANIFEST_REF,
                )
            content_ref = SchemaRef.parse(document["dataset_schema"])
            digest = Sha256Digest(document["content_digest"])
            content_payload = self._load_json_content(digest, content_ref)
            dataset = Dataset(
                DatasetContent(content_payload),
                _dataset_provenance(document),
                manifest,
                UtcTimestamp.parse(document["created_at"]),
            )
            validate_dataset(dataset)
            return dataset
        except DataPlaneError:
            raise
        except (
            ContractValidationError,
            DomainError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            raise _integrity_error(
                "Durable Dataset failed integrity checks."
            ) from error
        except sqlite3.Error as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable Dataset could not be loaded.",
            ) from error

    def publish_analysis(self, result: AnalysisResult) -> None:
        try:
            validate_analysis(result)
        except (
            DomainError,
            ContractValidationError,
            KeyError,
            TypeError,
            ValueError,
        ) as error:
            raise _integrity_error(
                "Analysis publication failed integrity checks."
            ) from error
        connection = self._require_connection()
        document = _plain(result.envelope.value)
        try:
            connection.execute("BEGIN IMMEDIATE")
            self._require_analysis_inputs(document["provenance"]["input_datasets"])
            self._store_content(
                result.content.content_digest,
                result.content.canonical_bytes,
            )
            self._store_document(
                _ANALYSIS_RESULT_KIND,
                str(result.provenance.analysis_result_id),
                result.envelope,
            )
            connection.execute("COMMIT")
        except DataPlaneError:
            _rollback(connection)
            raise
        except sqlite3.Error as error:
            _rollback(connection)
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Analysis publication failed.",
            ) from error

    def load_analysis(self, result_id: AnalysisResultId) -> AnalysisResult:
        if not isinstance(result_id, AnalysisResultId):
            raise TypeError("Analysis load requires an AnalysisResultId.")
        try:
            envelope = self._load_document(
                _ANALYSIS_RESULT_KIND,
                str(result_id),
                ANALYSIS_RESULT_REF,
                missing_is_integrity=False,
            )
            document = _plain(envelope.value)
            if document["analysis_result_id"] != str(result_id):
                raise _integrity_error("Durable Analysis identity is inconsistent.")
            inputs = tuple(
                self.load_dataset(DatasetId.parse(item["dataset_id"]))
                for item in document["provenance"]["input_datasets"]
            )
            self._require_analysis_inputs(document["provenance"]["input_datasets"])
            content_ref = SchemaRef.parse(document["result_schema"])
            digest = Sha256Digest(document["result_digest"])
            content_payload = self._load_json_content(digest, content_ref)
            if _plain(content_payload.value) != document["result"]:
                raise _integrity_error("Durable Analysis content is inconsistent.")
            result = AnalysisResult(
                AnalysisContent(content_payload),
                _analysis_provenance(result_id, document),
                inputs,
                envelope,
                UtcTimestamp.parse(document["created_at"]),
            )
            validate_analysis(result)
            return result
        except DataPlaneError:
            raise
        except (
            ContractValidationError,
            DomainError,
            KeyError,
            TypeError,
            ValueError,
            json.JSONDecodeError,
            UnicodeDecodeError,
        ) as error:
            raise _integrity_error(
                "Durable Analysis failed integrity checks."
            ) from error
        except sqlite3.Error as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable Analysis could not be loaded.",
            ) from error

    def _store_evidence(self, evidence: DurableEvidence) -> None:
        if evidence.manifest.prior_manifest is not None:
            self._require_evidence_reference(evidence.manifest.prior_manifest)
        document = _plain(evidence.payload.value)
        descriptors = document["objects"]
        for collected, descriptor in zip(
            evidence.raw_evidence, descriptors, strict=True
        ):
            self._store_content(
                collected.evidence_object.content_digest,
                collected.content,
            )
            self._store_record_bytes(
                _RAW_EVIDENCE_OBJECT_KIND,
                str(collected.evidence_object.object_id),
                str(RAW_EVIDENCE_MANIFEST_REF),
                _canonical_json_bytes(descriptor),
            )
        self._store_document(
            _RAW_EVIDENCE_MANIFEST_KIND,
            str(evidence.manifest.manifest_id),
            evidence.payload,
        )

    def _load_evidence_history(
        self,
        reference: RawEvidenceManifestRef,
        seen: set[RawEvidenceManifestId],
    ) -> tuple[DurableEvidence, ...]:
        if reference.manifest_id in seen:
            raise _integrity_error("Raw Evidence revision chain contains a cycle.")
        seen.add(reference.manifest_id)
        payload = self._load_document(
            _RAW_EVIDENCE_MANIFEST_KIND,
            str(reference.manifest_id),
            RAW_EVIDENCE_MANIFEST_REF,
        )
        document = _plain(payload.value)
        if (
            document["manifest_id"] != str(reference.manifest_id)
            or document["run_id"] != str(reference.run_id)
            or hashlib.sha256(_canonical_json_bytes(document)).hexdigest()
            != str(reference.content_digest)
        ):
            raise _integrity_error("Raw Evidence Manifest reference is inconsistent.")
        prior = (
            _evidence_reference(document["prior_manifest"])
            if "prior_manifest" in document
            else None
        )
        history = self._load_evidence_history(prior, seen) if prior else ()
        collected = []
        objects = []
        for descriptor in document["objects"]:
            descriptor_bytes = _canonical_json_bytes(descriptor)
            self._require_record_bytes(
                _RAW_EVIDENCE_OBJECT_KIND,
                descriptor["object_id"],
                str(RAW_EVIDENCE_MANIFEST_REF),
                descriptor_bytes,
            )
            evidence_object = _evidence_object(descriptor)
            content = self._load_content(evidence_object.content_digest)
            if len(content) != evidence_object.byte_length:
                raise _integrity_error("Raw Evidence byte length is inconsistent.")
            objects.append(evidence_object)
            collected.append(CollectedRawEvidence(evidence_object, content))
        manifest = RawEvidenceManifest(
            reference.manifest_id,
            reference.run_id,
            tuple(objects),
            UtcTimestamp.parse(document["sealed_at"]),
            EvidenceCollectionOutcome(document["outcome"]),
            prior,
        )
        return (
            *history,
            DurableEvidence(manifest, payload, reference, tuple(collected)),
        )

    def _require_evidence_reference(
        self, reference: RawEvidenceManifestRef
    ) -> None:
        self._load_evidence_history(reference, set())

    def _require_artifact(self, artifact_id: str) -> None:
        manifest = self._load_document(
            _ARTIFACT_MANIFEST_KIND,
            artifact_id,
            ARTIFACT_MANIFEST_REF,
        )
        build = self.load_build(
            BuildRecordId.parse(manifest.value["build_record_id"])
        )
        if (
            build.artifact_acceptance is None
            or str(build.artifact_acceptance.artifact.artifact_id) != artifact_id
        ):
            raise _integrity_error("Run Artifact reference is inconsistent.")

    def _require_analysis_inputs(self, inputs: list[object]) -> None:
        for item in inputs:
            dataset = self.load_dataset(DatasetId.parse(item["dataset_id"]))
            if str(dataset.content.content_digest) != item["content_digest"]:
                raise _integrity_error("Analysis Dataset reference is inconsistent.")

    def _load_json_content(
        self, digest: Sha256Digest, schema_ref: SchemaRef
    ) -> SchemaReferencedPayload:
        content = self._load_content(digest)
        document = json.loads(content.decode("utf-8"))
        if not isinstance(document, dict) or _canonical_json_bytes(document) != content:
            raise _integrity_error("Durable content representation is invalid.")
        validate_document(document)
        expected_ref = SchemaRef.parse(
            f"urn:ea-research-lab:schema:"
            f"{document['schema_name']}:{document['schema_version']}"
        )
        if expected_ref != schema_ref:
            raise _integrity_error("Durable content schema is inconsistent.")
        return SchemaReferencedPayload(schema_ref, document)

    def _store_record_bytes(
        self,
        record_kind: str,
        record_key: str,
        schema_ref: str,
        content: bytes,
    ) -> None:
        digest = Sha256Digest(hashlib.sha256(content).hexdigest())
        self._store_content(digest, content)
        self._store_record_identity(record_kind, record_key, schema_ref, digest)

    def _require_record_bytes(
        self,
        record_kind: str,
        record_key: str,
        schema_ref: str,
        content: bytes,
    ) -> None:
        digest = Sha256Digest(hashlib.sha256(content).hexdigest())
        connection = self._require_connection()
        row = connection.execute(
            """
            SELECT schema_ref, document_digest
            FROM published_records
            WHERE record_kind = ? AND record_key = ?
            """,
            (record_kind, record_key),
        ).fetchone()
        if row != (schema_ref, str(digest)):
            raise _integrity_error("Immutable entity identity is inconsistent.")
        self._load_content(digest)

    def _store_document(
        self,
        record_kind: str,
        record_key: str,
        payload: SchemaReferencedPayload,
    ) -> None:
        document = _plain(payload.value)
        try:
            validate_document(document)
        except ContractValidationError as error:
            raise _integrity_error("Durable document is invalid.") from error
        expected_ref = SchemaRef.parse(
            f"urn:ea-research-lab:schema:"
            f"{document['schema_name']}:{document['schema_version']}"
        )
        if payload.schema_ref != expected_ref:
            raise _integrity_error("Durable document schema is inconsistent.")
        content = _canonical_json_bytes(document)
        digest = Sha256Digest(hashlib.sha256(content).hexdigest())
        self._store_content(digest, content)

        self._store_record_identity(
            record_kind,
            record_key,
            str(payload.schema_ref),
            digest,
        )

    def _store_record_identity(
        self,
        record_kind: str,
        record_key: str,
        schema_ref: str,
        digest: Sha256Digest,
    ) -> None:
        connection = self._require_connection()
        existing = connection.execute(
            """
            SELECT schema_ref, document_digest
            FROM published_records
            WHERE record_kind = ? AND record_key = ?
            """,
            (record_kind, record_key),
        ).fetchone()
        durable_identity = (schema_ref, str(digest))
        if existing is None:
            connection.execute(
                """
                INSERT INTO published_records
                    (record_kind, record_key, schema_ref, document_digest)
                VALUES (?, ?, ?, ?)
                """,
                (record_kind, record_key, *durable_identity),
            )
        elif existing != durable_identity:
            raise _integrity_error("Published record conflicts with durable data.")

    def _store_content(self, digest: Sha256Digest, content: bytes) -> None:
        if not isinstance(digest, Sha256Digest) or not isinstance(content, bytes):
            raise _integrity_error("Immutable content identity is invalid.")
        if hashlib.sha256(content).hexdigest() != str(digest):
            raise _integrity_error("Immutable content digest is invalid.")
        connection = self._require_connection()
        existing = connection.execute(
            "SELECT byte_length, content FROM content_objects WHERE digest = ?",
            (str(digest),),
        ).fetchone()
        durable_content = (len(content), content)
        if existing is None:
            connection.execute(
                """
                INSERT INTO content_objects (digest, byte_length, content)
                VALUES (?, ?, ?)
                """,
                (str(digest), len(content), sqlite3.Binary(content)),
            )
        elif (existing[0], bytes(existing[1])) != durable_content:
            raise _integrity_error("Immutable content conflicts with durable data.")

    def _load_document(
        self,
        record_kind: str,
        record_key: str,
        expected_ref: SchemaRef,
        *,
        missing_is_integrity: bool = True,
    ) -> SchemaReferencedPayload:
        connection = self._require_connection()
        row = connection.execute(
            """
            SELECT schema_ref, document_digest
            FROM published_records
            WHERE record_kind = ? AND record_key = ?
            """,
            (record_kind, record_key),
        ).fetchone()
        if row is None:
            if missing_is_integrity:
                raise _integrity_error("Referenced durable record is missing.")
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Durable Build is unavailable.",
            )
        if row[0] != str(expected_ref):
            raise _integrity_error("Durable record schema is inconsistent.")
        content = self._load_content(Sha256Digest(row[1]))
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or _canonical_json_bytes(document) != content
            or document.get("schema_name") != str(expected_ref.name)
            or document.get("schema_version") != str(expected_ref.version)
        ):
            raise _integrity_error("Durable document representation is invalid.")
        try:
            validate_document(document)
        except ContractValidationError as error:
            raise _integrity_error(
                "Durable document schema validation failed."
            ) from error
        return SchemaReferencedPayload(expected_ref, document)

    def _load_content(self, digest: Sha256Digest) -> bytes:
        connection = self._require_connection()
        row = connection.execute(
            "SELECT byte_length, content FROM content_objects WHERE digest = ?",
            (str(digest),),
        ).fetchone()
        if row is None:
            raise _integrity_error("Referenced immutable content is missing.")
        content = bytes(row[1])
        if row[0] != len(content) or hashlib.sha256(content).hexdigest() != str(
            digest
        ):
            raise _integrity_error("Immutable content failed integrity checks.")
        return content

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Data Plane is closed.",
            )
        return self._connection


def _canonical_json_bytes(document: Mapping[str, object]) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _evidence_reference(document: object) -> RawEvidenceManifestRef:
    if not isinstance(document, Mapping):
        raise _integrity_error("Raw Evidence Manifest reference is invalid.")
    return RawEvidenceManifestRef(
        RawEvidenceManifestId.parse(document["manifest_id"]),
        RunId.parse(document["run_id"]),
        Sha256Digest(document["content_digest"]),
    )


def _evidence_object(document: Mapping[str, object]) -> RawEvidenceObject:
    return RawEvidenceObject(
        RawEvidenceObjectId.parse(document["object_id"]),
        document["media_type"],
        document["byte_length"],
        Sha256Digest(document["content_digest"]),
        (
            SchemaRef.parse(document["payload_schema"])
            if "payload_schema" in document
            else None
        ),
        document.get("provider_namespace"),
    )


def _embedded_payload(document: Mapping[str, object]) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(
        SchemaRef.parse(document["schema_ref"]),
        document["value"],
    )


def _dataset_provenance(document: Mapping[str, object]) -> DatasetProvenance:
    return DatasetProvenance(
        DatasetId.parse(document["dataset_id"]),
        TransformationId.parse(document["transformation_id"]),
        DefinitionVersion(document["transformation_version"]),
        tuple(
            _evidence_reference(item) for item in document["input_manifests"]
        ),
        tuple(DatasetId.parse(item) for item in document["input_datasets"]),
        (
            _embedded_payload(document["transformation_parameters"])
            if "transformation_parameters" in document
            else None
        ),
    )


def _analysis_provenance(
    result_id: AnalysisResultId,
    document: Mapping[str, object],
) -> AnalysisProvenance:
    provenance = document["provenance"]
    return AnalysisProvenance(
        result_id,
        AnalysisDefinitionId.parse(provenance["analysis_definition_id"]),
        DefinitionVersion(provenance["analysis_version"]),
        _embedded_payload(provenance["analysis_parameters"]),
        EnvironmentConfigurationId.parse(
            provenance["computation_environment_id"]
        ),
        tuple(
            DatasetId.parse(item["dataset_id"])
            for item in provenance["input_datasets"]
        ),
    )


def _rollback(connection: sqlite3.Connection) -> None:
    try:
        connection.execute("ROLLBACK")
    except sqlite3.Error:
        pass


def _integrity_error(message: str) -> DataPlaneError:
    return DataPlaneError(ApplicationErrorCode.DATA_INTEGRITY_FAILED, message)
