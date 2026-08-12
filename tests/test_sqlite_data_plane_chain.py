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

from ea_research_lab.application.analysis import (
    AnalysisRequest,
    analyze_execution_summaries,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.data_plane import (
    DATASET_MANIFEST_REF,
    RAW_EVIDENCE_MANIFEST_REF,
    RUN_MANIFEST_REF,
    TEST_DEFINITION_REF,
    DataPlaneError,
    DurableEvidence,
    DurableRun,
)
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.analysis import AnalysisContent, AnalysisResult
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
    TestDefinitionId,
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
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from tests.test_sqlite_data_plane import (
    _database_counts,
    _replace_record_document,
    _successful_build,
)


SUMMARY_REF = SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0))
PARAMETERS_REF = SchemaRef(
    SchemaName("execution-summary-analysis-parameters"), SchemaVersion(0, 1, 0)
)
EVIDENCE_BYTES = b"\xffexact raw evidence\x00"


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


def _canonical(document: object) -> bytes:
    return json.dumps(
        document,
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
        allow_nan=False,
    ).encode("utf-8")


def _payload(reference: SchemaRef, value: dict[str, object]):
    return SchemaReferencedPayload(reference, value)


def _evidence(
    run_id: RunId,
    *,
    content: bytes | None = EVIDENCE_BYTES,
    object_id: RawEvidenceObjectId | None = None,
    prior: DurableEvidence | None = None,
    outcome: EvidenceCollectionOutcome = EvidenceCollectionOutcome.COMPLETED,
) -> DurableEvidence:
    evidence_object = (
        RawEvidenceObject(
            object_id or new_entity_id(RawEvidenceObjectId),
            "application/octet-stream",
            len(content),
            Sha256Digest(hashlib.sha256(content).hexdigest()),
            provider_namespace="portable.fake",
        )
        if content is not None
        else None
    )
    collected = (
        (CollectedRawEvidence(evidence_object, content),)
        if evidence_object is not None and content is not None
        else ()
    )
    manifest = RawEvidenceManifest(
        new_entity_id(RawEvidenceManifestId),
        run_id,
        tuple(item.evidence_object for item in collected),
        UtcTimestamp.parse("2026-08-11T14:00:00Z"),
        outcome,
        prior.reference if prior else None,
    )
    document: dict[str, object] = {
        "schema_name": "raw-evidence-manifest",
        "schema_version": "0.1.0",
        "manifest_id": str(manifest.manifest_id),
        "run_id": str(run_id),
        "objects": (
            [
                {
                    "object_id": str(evidence_object.object_id),
                    "media_type": evidence_object.media_type,
                    "byte_length": evidence_object.byte_length,
                    "content_digest": str(evidence_object.content_digest),
                    "provider_namespace": evidence_object.provider_namespace,
                }
            ]
            if evidence_object is not None
            else []
        ),
        "sealed_at": str(manifest.sealed_at),
        "outcome": manifest.outcome.value,
    }
    if prior:
        document["prior_manifest"] = {
            "manifest_id": str(prior.reference.manifest_id),
            "run_id": str(prior.reference.run_id),
            "content_digest": str(prior.reference.content_digest),
        }
    reference = RawEvidenceManifestRef(
        manifest.manifest_id,
        run_id,
        Sha256Digest(hashlib.sha256(_canonical(document)).hexdigest()),
    )
    return DurableEvidence(
        manifest,
        _payload(RAW_EVIDENCE_MANIFEST_REF, document),
        reference,
        collected,
    )


def _run(
    *,
    revisions: int = 1,
    status: str = "completed",
    evidence_content: bytes | None = EVIDENCE_BYTES,
    evidence_outcome: EvidenceCollectionOutcome = EvidenceCollectionOutcome.COMPLETED,
) -> DurableRun:
    build = _successful_build()
    artifact_id = build.artifact_acceptance.artifact.artifact_id
    run_id = new_entity_id(RunId)
    history = []
    for index in range(revisions):
        history.append(
            _evidence(
                run_id,
                content=(
                    f"evidence-{index}".encode()
                    if evidence_content is not None
                    else None
                ),
                prior=history[-1] if history else None,
                outcome=evidence_outcome,
            )
        )
    test_revision = new_entity_id(TestDefinitionRevisionId)
    test_definition = {
        "schema_name": "test-definition",
        "schema_version": "0.1.0",
        "test_definition_id": str(new_entity_id(TestDefinitionId)),
        "test_definition_revision_id": str(test_revision),
        "artifact_id": str(artifact_id),
        "execution_configuration": {
            "schema_ref": "urn:ea-research-lab:schema:example-config:0.1.0",
            "value": {"mode": "portable"},
        },
        "sut_inputs": {
            "schema_ref": "urn:ea-research-lab:schema:example-inputs:0.1.0",
            "value": {"opaque": True},
        },
    }
    current = history[-1].reference
    run_manifest = {
        "schema_name": "run-manifest",
        "schema_version": "0.1.0",
        "run_id": str(run_id),
        "test_definition_revision_id": str(test_revision),
        "artifact_id": str(artifact_id),
        "environment_configuration_id": str(
            new_entity_id(EnvironmentConfigurationId)
        ),
        "environment_configuration": {
            "schema_ref": "urn:ea-research-lab:schema:example-environment:0.1.0",
            "value": {"provider": "portable.fake"},
        },
        "status": status,
        "created_at": "2026-08-11T13:58:00Z",
        "started_at": "2026-08-11T13:59:00Z",
        "finished_at": "2026-08-11T14:00:00Z",
        "execution_reproducibility": {"level": "equivalent", "reasons": []},
        "raw_evidence_manifest": {
            "manifest_id": str(current.manifest_id),
            "run_id": str(current.run_id),
            "content_digest": str(current.content_digest),
        },
    }
    return DurableRun(
        _payload(TEST_DEFINITION_REF, test_definition),
        _payload(RUN_MANIFEST_REF, run_manifest),
        tuple(history),
    )


def _dataset(
    run: DurableRun,
    *,
    dataset_id: DatasetId | None = None,
    net_profit: str = "100.00",
) -> Dataset:
    evidence = run.evidence_history[-1].reference
    content = DatasetContent(
        _payload(
            SUMMARY_REF,
            {
                "schema_name": "execution-summary",
                "schema_version": "0.1.0",
                "currency": "USD",
                "initial_deposit": "1000.00",
                "net_profit": net_profit,
                "gross_profit": "120.00",
                "gross_loss": "-20.00",
                "total_trades": 10,
                "winning_trades": 6,
                "losing_trades": 4,
            },
        )
    )
    provenance = DatasetProvenance(
        dataset_id or new_entity_id(DatasetId),
        new_entity_id(TransformationId),
        DefinitionVersion("portable-transform-1"),
        input_manifests=(evidence,),
    )
    created_at = UtcTimestamp.parse("2026-08-11T14:01:00Z")
    manifest = {
        "schema_name": "dataset-manifest",
        "schema_version": "0.2.0",
        "dataset_id": str(provenance.dataset_id),
        "input_manifests": [
            {
                "manifest_id": str(evidence.manifest_id),
                "run_id": str(evidence.run_id),
                "content_digest": str(evidence.content_digest),
            }
        ],
        "input_datasets": [],
        "transformation_id": str(provenance.transformation_id),
        "transformation_version": str(provenance.transformation_version),
        "created_at": str(created_at),
        "dataset_schema": str(content.payload.schema_ref),
        "content_digest": str(content.content_digest),
    }
    return Dataset(
        content,
        provenance,
        _payload(DATASET_MANIFEST_REF, manifest),
        created_at,
    )


def _analysis(*datasets: Dataset) -> AnalysisResult:
    parameters: dict[str, object] = {
        "schema_name": "execution-summary-analysis-parameters",
        "schema_version": "0.1.0",
    }
    if len(datasets) > 1:
        parameters["baseline_content_digest"] = str(
            datasets[0].content.content_digest
        )
    outcome = analyze_execution_summaries(
        AnalysisRequest(
            RequestContext(new_entity_id(RequestId), "persistence-test"),
            datasets,
            new_entity_id(AnalysisDefinitionId),
            DefinitionVersion("portable-analysis-1"),
            _payload(
                PARAMETERS_REF,
                parameters,
            ),
            new_entity_id(EnvironmentConfigurationId),
        )
    )
    assert outcome.result is not None
    return outcome.result


def _conflicting_dataset(dataset: Dataset) -> Dataset:
    content_document = copy.deepcopy(_plain(dataset.content.payload.value))
    content_document["net_profit"] = "101.00"
    content = DatasetContent(
        _payload(dataset.content.payload.schema_ref, content_document)
    )
    manifest = copy.deepcopy(_plain(dataset.manifest.value))
    manifest["content_digest"] = str(content.content_digest)
    return Dataset(
        content,
        dataset.provenance,
        _payload(DATASET_MANIFEST_REF, manifest),
        dataset.created_at,
    )


def _conflicting_analysis(result: AnalysisResult) -> AnalysisResult:
    content_document = copy.deepcopy(_plain(result.content.payload.value))
    content_document["metrics"][0]["net_return"]["value"] = "0.200000000000"
    content = AnalysisContent(
        _payload(result.content.payload.schema_ref, content_document)
    )
    envelope = copy.deepcopy(_plain(result.envelope.value))
    envelope["result"] = content_document
    envelope["result_digest"] = str(content.content_digest)
    return AnalysisResult(
        content,
        result.provenance,
        result.input_datasets,
        _payload(result.envelope.schema_ref, envelope),
        result.created_at,
    )


def _seed_chain(database: Path):
    build = _successful_build()
    run = _run(revisions=2)
    dataset = _dataset(run)
    analysis = _analysis(dataset)
    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(build)
        data_plane.publish_run(run)
        data_plane.publish_dataset(dataset)
        data_plane.publish_analysis(analysis)
    return build, run, dataset, analysis


def _mutate_content(database: Path, digest: Sha256Digest) -> None:
    with closing(sqlite3.connect(database, isolation_level=None)) as connection:
        connection.execute(
            "UPDATE content_objects SET content = ? WHERE digest = ?",
            (b"corrupted", str(digest)),
        )


def _replace_evidence_and_run(
    database: Path,
    run: DurableRun,
    evidence_document: dict[str, object],
) -> None:
    evidence = run.evidence_history[-1]
    digest = hashlib.sha256(_canonical(evidence_document)).hexdigest()
    _replace_record_document(
        database,
        "raw-evidence-manifest",
        str(evidence.reference.manifest_id),
        _canonical(evidence_document),
    )
    run_document = copy.deepcopy(_plain(run.run_manifest.value))
    run_document["raw_evidence_manifest"]["content_digest"] = digest
    _replace_record_document(
        database,
        "run-manifest",
        str(run.run_id),
        _canonical(run_document),
    )


class SqliteCanonicalChainTests(unittest.TestCase):
    def test_complete_chain_survives_close_and_reopen(self) -> None:
        build = _successful_build()
        run = _run(revisions=2)
        dataset = _dataset(run)
        analysis = _analysis(dataset)
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                data_plane.publish_run(run)
                data_plane.publish_dataset(dataset)
                data_plane.publish_analysis(analysis)
            with SqliteDataPlane(database) as fresh:
                loaded_build = fresh.load_build(build.build_record_id)
                loaded_run = fresh.load_run(run.run_id)
                loaded_dataset = fresh.load_dataset(dataset.provenance.dataset_id)
                loaded_analysis = fresh.load_analysis(
                    analysis.provenance.analysis_result_id
                )

        self.assertEqual(loaded_build, build)
        self.assertEqual(loaded_run, run)
        self.assertEqual(loaded_dataset, dataset)
        self.assertEqual(loaded_analysis, analysis)

    def test_publications_are_idempotent_and_content_is_deduplicated(self) -> None:
        build = _successful_build()
        run = _run(revisions=2)
        first = _dataset(run)
        second = _dataset(run)
        analysis = _analysis(first)
        object.__setattr__(second, "content", first.content)
        second_document = copy.deepcopy(_plain(second.manifest.value))
        second_document["content_digest"] = str(first.content.content_digest)
        object.__setattr__(
            second,
            "manifest",
            _payload(DATASET_MANIFEST_REF, second_document),
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                data_plane.publish_run(run)
                data_plane.publish_run(run)
                data_plane.publish_dataset(first)
                before = _database_counts(database)
                data_plane.publish_dataset(first)
                self.assertEqual(_database_counts(database), before)
                data_plane.publish_analysis(analysis)
                before_analysis = _database_counts(database)
                data_plane.publish_analysis(analysis)
                self.assertEqual(_database_counts(database), before_analysis)
                data_plane.publish_dataset(second)
            with closing(sqlite3.connect(database)) as connection:
                count = connection.execute(
                    "SELECT count(*) FROM content_objects WHERE digest = ?",
                    (str(first.content.content_digest),),
                ).fetchone()[0]
        self.assertEqual(count, 1)

    def test_missing_upstream_facts_fail_closed(self) -> None:
        run = _run()
        dataset = _dataset(run)
        analysis = _analysis(dataset)
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                for operation, value in (
                    (data_plane.publish_run, run),
                    (data_plane.publish_dataset, dataset),
                    (data_plane.publish_analysis, analysis),
                ):
                    with self.subTest(operation=operation.__name__), self.assertRaises(
                        DataPlaneError
                    ):
                        operation(value)

    def test_raw_evidence_entity_conflict_fails_without_overwrite(self) -> None:
        build = _successful_build()
        first = _run()
        second = _run()
        shared_id = first.evidence_history[-1].raw_evidence[0].evidence_object.object_id
        conflicting_evidence = _evidence(
            second.run_id,
            content=b"different exact bytes",
            object_id=shared_id,
        )
        second_document = copy.deepcopy(_plain(second.run_manifest.value))
        second_document["raw_evidence_manifest"] = {
            "manifest_id": str(conflicting_evidence.reference.manifest_id),
            "run_id": str(conflicting_evidence.reference.run_id),
            "content_digest": str(conflicting_evidence.reference.content_digest),
        }
        conflict = DurableRun(
            second.test_definition,
            _payload(RUN_MANIFEST_REF, second_document),
            (conflicting_evidence,),
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                data_plane.publish_run(first)
                before = _database_counts(database)
                with self.assertRaises(DataPlaneError):
                    data_plane.publish_run(conflict)
                self.assertEqual(_database_counts(database), before)
                self.assertEqual(data_plane.load_run(first.run_id), first)

    def test_run_lifecycle_and_empty_evidence_are_not_reinterpreted(self) -> None:
        build = _successful_build()
        cases = (
            ("completed", EvidenceCollectionOutcome.COLLECTION_FAILED),
            ("failed", EvidenceCollectionOutcome.FAILED),
            ("cancelled", EvidenceCollectionOutcome.CANCELLED),
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                runs = []
                for status, outcome in cases:
                    run = _run(
                        status=status,
                        evidence_content=None,
                        evidence_outcome=outcome,
                    )
                    data_plane.publish_run(run)
                    runs.append(run)
            with SqliteDataPlane(database) as fresh:
                loaded = tuple(fresh.load_run(run.run_id) for run in runs)

        self.assertEqual(loaded, tuple(runs))

    def test_late_conflicts_roll_back_each_capability(self) -> None:
        build = _successful_build()
        run = _run()
        dataset = _dataset(run)
        analysis = _analysis(dataset)
        conflicting_run_document = copy.deepcopy(_plain(run.run_manifest.value))
        conflicting_run_document["status"] = "failed"
        conflicting_run = DurableRun(
            run.test_definition,
            _payload(RUN_MANIFEST_REF, conflicting_run_document),
            run.evidence_history,
        )
        conflicts = (
            ("run", conflicting_run),
            ("dataset", _conflicting_dataset(dataset)),
            ("analysis", _conflicting_analysis(analysis)),
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(build)
                data_plane.publish_run(run)
                data_plane.publish_dataset(dataset)
                data_plane.publish_analysis(analysis)
                for capability, conflict in conflicts:
                    before = _database_counts(database)
                    with self.subTest(capability=capability), self.assertRaises(
                        DataPlaneError
                    ):
                        getattr(data_plane, f"publish_{capability}")(conflict)
                    self.assertEqual(_database_counts(database), before)

    def test_run_corruption_fails_closed(self) -> None:
        mutations = (
            self._mutate_raw_bytes,
            self._mismatch_raw_digest,
            self._break_raw_object_reference,
            self._malform_run_manifest,
            self._break_test_definition_reference,
        )
        for mutation in mutations:
            with self.subTest(
                case=mutation.__name__
            ), tempfile.TemporaryDirectory() as name:
                database = Path(name) / "lab.sqlite3"
                _, run, _, _ = _seed_chain(database)
                mutation(database, run)
                with SqliteDataPlane(database) as fresh:
                    with self.assertRaises(DataPlaneError):
                        fresh.load_run(run.run_id)

    def test_dataset_corruption_fails_closed(self) -> None:
        mutations = (
            self._mutate_dataset_content,
            self._mismatch_dataset_digest,
            self._malform_dataset_manifest,
            self._break_dataset_evidence_reference,
        )
        for mutation in mutations:
            with self.subTest(
                case=mutation.__name__
            ), tempfile.TemporaryDirectory() as name:
                database = Path(name) / "lab.sqlite3"
                _, _, dataset, _ = _seed_chain(database)
                mutation(database, dataset)
                with SqliteDataPlane(database) as fresh:
                    with self.assertRaises(DataPlaneError):
                        fresh.load_dataset(dataset.provenance.dataset_id)

    def test_analysis_corruption_fails_closed(self) -> None:
        mutations = (
            self._mutate_analysis_content,
            self._mismatch_analysis_digest,
            self._malform_analysis_result,
            self._break_analysis_dataset_reference,
        )
        for mutation in mutations:
            with self.subTest(
                case=mutation.__name__
            ), tempfile.TemporaryDirectory() as name:
                database = Path(name) / "lab.sqlite3"
                _, _, _, analysis = _seed_chain(database)
                mutation(database, analysis)
                with SqliteDataPlane(database) as fresh:
                    with self.assertRaises(DataPlaneError):
                        fresh.load_analysis(analysis.provenance.analysis_result_id)

    @staticmethod
    def _mutate_raw_bytes(database: Path, run: DurableRun) -> None:
        _mutate_content(
            database,
            run.evidence_history[-1].raw_evidence[0].evidence_object.content_digest,
        )

    @staticmethod
    def _mismatch_raw_digest(database: Path, run: DurableRun) -> None:
        evidence = run.evidence_history[-1]
        document = copy.deepcopy(_plain(evidence.payload.value))
        document["objects"][0]["content_digest"] = "f" * 64
        _replace_evidence_and_run(database, run, document)

    @staticmethod
    def _break_raw_object_reference(database: Path, run: DurableRun) -> None:
        evidence = run.evidence_history[-1]
        document = copy.deepcopy(_plain(evidence.payload.value))
        document["objects"][0]["object_id"] = str(
            new_entity_id(RawEvidenceObjectId)
        )
        _replace_evidence_and_run(database, run, document)

    @staticmethod
    def _malform_run_manifest(database: Path, run: DurableRun) -> None:
        _replace_record_document(
            database,
            "run-manifest",
            str(run.run_id),
            b"{malformed",
        )

    @staticmethod
    def _break_test_definition_reference(database: Path, run: DurableRun) -> None:
        document = copy.deepcopy(_plain(run.run_manifest.value))
        document["test_definition_revision_id"] = str(
            new_entity_id(TestDefinitionRevisionId)
        )
        _replace_record_document(
            database,
            "run-manifest",
            str(run.run_id),
            _canonical(document),
        )

    @staticmethod
    def _mutate_dataset_content(database: Path, dataset: Dataset) -> None:
        _mutate_content(database, dataset.content.content_digest)

    @staticmethod
    def _mismatch_dataset_digest(database: Path, dataset: Dataset) -> None:
        document = copy.deepcopy(_plain(dataset.manifest.value))
        document["content_digest"] = "f" * 64
        _replace_record_document(
            database,
            "dataset-manifest",
            str(dataset.provenance.dataset_id),
            _canonical(document),
        )

    @staticmethod
    def _malform_dataset_manifest(database: Path, dataset: Dataset) -> None:
        _replace_record_document(
            database,
            "dataset-manifest",
            str(dataset.provenance.dataset_id),
            b"{malformed",
        )

    @staticmethod
    def _break_dataset_evidence_reference(database: Path, dataset: Dataset) -> None:
        document = copy.deepcopy(_plain(dataset.manifest.value))
        document["input_manifests"][0]["manifest_id"] = str(
            new_entity_id(RawEvidenceManifestId)
        )
        _replace_record_document(
            database,
            "dataset-manifest",
            str(dataset.provenance.dataset_id),
            _canonical(document),
        )

    @staticmethod
    def _mutate_analysis_content(database: Path, result: AnalysisResult) -> None:
        _mutate_content(database, result.content.content_digest)

    @staticmethod
    def _mismatch_analysis_digest(database: Path, result: AnalysisResult) -> None:
        document = copy.deepcopy(_plain(result.envelope.value))
        document["result_digest"] = "f" * 64
        _replace_record_document(
            database,
            "analysis-result",
            str(result.provenance.analysis_result_id),
            _canonical(document),
        )

    @staticmethod
    def _malform_analysis_result(database: Path, result: AnalysisResult) -> None:
        _replace_record_document(
            database,
            "analysis-result",
            str(result.provenance.analysis_result_id),
            b"{malformed",
        )

    @staticmethod
    def _break_analysis_dataset_reference(
        database: Path, result: AnalysisResult
    ) -> None:
        document = copy.deepcopy(_plain(result.envelope.value))
        document["provenance"]["input_datasets"][0]["content_digest"] = "f" * 64
        _replace_record_document(
            database,
            "analysis-result",
            str(result.provenance.analysis_result_id),
            _canonical(document),
        )


if __name__ == "__main__":
    unittest.main()
