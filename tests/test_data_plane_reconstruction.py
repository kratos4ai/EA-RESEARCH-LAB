from __future__ import annotations

import copy
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from ea_research_lab.application.build import ArtifactAcceptance
from ea_research_lab.application.data_plane import (
    ARTIFACT_MANIFEST_REF,
    BUILD_RECORD_REF,
    CanonicalChainRequest,
    DataPlaneError,
    DurableBuild,
    reconstruct_canonical_chain,
)
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    RunId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from tests.test_sqlite_data_plane import _replace_record_document, _successful_build
from tests.test_sqlite_data_plane_chain import (
    _analysis,
    _canonical,
    _dataset,
    _plain,
    _replace_evidence_and_run,
    _run,
)


def _clone_build(build: DurableBuild) -> DurableBuild:
    build_id = BuildRecordId.parse(
        "build_0195395c-7c9e-7a91-8c2b-6d4f8e1a2b3c"
    )
    artifact_id = ArtifactId.parse(
        "artifact_0195395c-7c9e-7a12-9d3c-7e5f9a2b3c4d"
    )
    record = copy.deepcopy(_plain(build.build_record.value))
    record["build_record_id"] = str(build_id)
    record["artifact_id"] = str(artifact_id)
    manifest = copy.deepcopy(
        _plain(build.artifact_acceptance.artifact_manifest.value)
    )
    manifest["build_record_id"] = str(build_id)
    manifest["artifact_id"] = str(artifact_id)
    artifact = AcceptedArtifact(
        artifact_id,
        build_id,
        build.artifact_acceptance.artifact.binary_digest,
        build.artifact_acceptance.artifact.content,
    )
    return DurableBuild(
        SchemaReferencedPayload(BUILD_RECORD_REF, record),
        build.build_input_manifest,
        ArtifactAcceptance(
            artifact,
            SchemaReferencedPayload(ARTIFACT_MANIFEST_REF, manifest),
        ),
    )


def _seed_fresh_state(database: Path) -> dict[str, object]:
    build = _successful_build()
    run = _run(revisions=2)
    datasets = (
        _dataset(run, net_profit="100.00"),
        _dataset(run, net_profit="110.00"),
        _dataset(run, net_profit="90.00"),
    )
    analysis = _analysis(*datasets)
    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(build)
        data_plane.publish_run(run)
        for dataset in datasets:
            data_plane.publish_dataset(dataset)
        data_plane.publish_analysis(analysis)
    return {
        "build_id": str(build.build_record_id),
        "run_id": str(run.run_id),
        "analysis_id": str(analysis.provenance.analysis_result_id),
        "artifact_bytes": build.artifact_acceptance.artifact.content,
        "artifact_digest": str(build.artifact_acceptance.artifact.binary_digest),
        "evidence_bytes": tuple(
            item.content
            for revision in run.evidence_history
            for item in revision.raw_evidence
        ),
        "evidence_refs": tuple(
            (
                str(revision.reference.manifest_id),
                str(revision.reference.content_digest),
            )
            for revision in run.evidence_history
        ),
        "dataset_ids": frozenset(
            str(dataset.provenance.dataset_id) for dataset in datasets
        ),
        "dataset_bytes": frozenset(
            dataset.content.canonical_bytes for dataset in datasets
        ),
        "dataset_digests": frozenset(
            str(dataset.content.content_digest) for dataset in datasets
        ),
        "analysis_bytes": analysis.content.canonical_bytes,
        "analysis_digest": str(analysis.content.content_digest),
    }


def _request(expected: dict[str, object]) -> CanonicalChainRequest:
    return CanonicalChainRequest(
        BuildRecordId.parse(expected["build_id"]),
        RunId.parse(expected["run_id"]),
        AnalysisResultId.parse(expected["analysis_id"]),
    )


class CanonicalChainReconstructionTests(unittest.TestCase):
    def test_fresh_state_reconstructs_all_exact_facts_without_computation(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            with (
                patch(
                    "ea_research_lab.application.build.execute_build",
                    side_effect=AssertionError("Build must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.execution.execute_run",
                    side_effect=AssertionError("Execution must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.dataset.transform_dataset",
                    side_effect=AssertionError("Transformation must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.analysis.analyze_execution_summaries",
                    side_effect=AssertionError("Analysis must not rerun."),
                ),
                patch(
                    "ea_research_lab.application.analysis.analyze_execution_core",
                    side_effect=AssertionError("Analysis must not rerun."),
                ),
                SqliteDataPlane(database) as fresh,
            ):
                chain = reconstruct_canonical_chain(fresh, _request(expected))

        artifact = chain.build.artifact_acceptance.artifact
        self.assertEqual(artifact.content, expected["artifact_bytes"])
        self.assertEqual(str(artifact.binary_digest), expected["artifact_digest"])
        self.assertEqual(
            tuple(
                item.content
                for revision in chain.run.evidence_history
                for item in revision.raw_evidence
            ),
            expected["evidence_bytes"],
        )
        self.assertEqual(
            tuple(
                (
                    str(revision.reference.manifest_id),
                    str(revision.reference.content_digest),
                )
                for revision in chain.run.evidence_history
            ),
            expected["evidence_refs"],
        )
        self.assertEqual(
            {str(dataset.provenance.dataset_id) for dataset in chain.datasets},
            expected["dataset_ids"],
        )
        self.assertEqual(
            {dataset.content.canonical_bytes for dataset in chain.datasets},
            expected["dataset_bytes"],
        )
        self.assertEqual(
            {str(dataset.content.content_digest) for dataset in chain.datasets},
            expected["dataset_digests"],
        )
        self.assertEqual(
            chain.analysis.content.canonical_bytes,
            expected["analysis_bytes"],
        )
        self.assertEqual(
            str(chain.analysis.content.content_digest),
            expected["analysis_digest"],
        )

    def test_run_cannot_substitute_another_valid_artifact(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            first = _successful_build()
            second = _clone_build(first)
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(second)
                run = data_plane.load_run(RunId.parse(expected["run_id"]))
            run_document = copy.deepcopy(_plain(run.run_manifest.value))
            test_document = copy.deepcopy(_plain(run.test_definition.value))
            run_document["artifact_id"] = str(
                second.artifact_acceptance.artifact.artifact_id
            )
            test_document["artifact_id"] = run_document["artifact_id"]
            _replace_record_document(
                database,
                "run-manifest",
                expected["run_id"],
                _canonical(run_document),
            )
            _replace_record_document(
                database,
                "test-definition",
                test_document["test_definition_revision_id"],
                _canonical(test_document),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_dataset_cannot_substitute_another_valid_evidence_revision(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            other_run = _run()
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_run(other_run)
                analysis = data_plane.load_analysis(
                    AnalysisResultId.parse(expected["analysis_id"])
                )
            dataset = analysis.input_datasets[0]
            document = copy.deepcopy(_plain(dataset.manifest.value))
            reference = other_run.evidence_history[-1].reference
            document["input_manifests"] = [
                {
                    "manifest_id": str(reference.manifest_id),
                    "run_id": str(reference.run_id),
                    "content_digest": str(reference.content_digest),
                }
            ]
            _replace_record_document(
                database,
                "dataset-manifest",
                str(dataset.provenance.dataset_id),
                _canonical(document),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_one_of_multiple_analysis_datasets_cannot_be_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            other_run = _run()
            unrelated = _dataset(other_run, net_profit="200.00")
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_run(other_run)
                data_plane.publish_dataset(unrelated)
                analysis = data_plane.load_analysis(
                    AnalysisResultId.parse(expected["analysis_id"])
                )
            document = copy.deepcopy(_plain(analysis.envelope.value))
            document["provenance"]["input_datasets"][1] = {
                "dataset_id": str(unrelated.provenance.dataset_id),
                "content_digest": str(unrelated.content.content_digest),
            }
            _replace_record_document(
                database,
                "analysis-result",
                expected["analysis_id"],
                _canonical(document),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_analysis_dataset_digest_cannot_be_substituted(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            with SqliteDataPlane(database) as data_plane:
                analysis = data_plane.load_analysis(
                    AnalysisResultId.parse(expected["analysis_id"])
                )
            document = copy.deepcopy(_plain(analysis.envelope.value))
            document["provenance"]["input_datasets"][0]["content_digest"] = (
                document["provenance"]["input_datasets"][1]["content_digest"]
            )
            _replace_record_document(
                database,
                "analysis-result",
                expected["analysis_id"],
                _canonical(document),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_dataset_entity_cannot_adopt_another_valid_content(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            with SqliteDataPlane(database) as data_plane:
                analysis = data_plane.load_analysis(
                    AnalysisResultId.parse(expected["analysis_id"])
                )
            first, second = analysis.input_datasets[:2]
            document = copy.deepcopy(_plain(first.manifest.value))
            document["content_digest"] = str(second.content.content_digest)
            _replace_record_document(
                database,
                "dataset-manifest",
                str(first.provenance.dataset_id),
                _canonical(document),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_raw_evidence_prior_revision_cannot_cross_runs(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            other_run = _run()
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_run(other_run)
                run = data_plane.load_run(RunId.parse(expected["run_id"]))
            current = run.evidence_history[-1]
            document = copy.deepcopy(_plain(current.payload.value))
            other = other_run.evidence_history[-1].reference
            document["prior_manifest"] = {
                "manifest_id": str(other.manifest_id),
                "run_id": str(other.run_id),
                "content_digest": str(other.content_digest),
            }
            _replace_evidence_and_run(database, run, document)
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))

    def test_schema_valid_build_artifact_lineage_break_fails_closed(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "lab.sqlite3"
            expected = _seed_fresh_state(database)
            first = _successful_build()
            second = _clone_build(first)
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(second)
            manifest = copy.deepcopy(
                _plain(first.artifact_acceptance.artifact_manifest.value)
            )
            manifest["build_record_id"] = str(second.build_record_id)
            _replace_record_document(
                database,
                "artifact-manifest",
                str(first.artifact_acceptance.artifact.artifact_id),
                _canonical(manifest),
            )
            with SqliteDataPlane(database) as fresh, self.assertRaises(DataPlaneError):
                reconstruct_canonical_chain(fresh, _request(expected))


if __name__ == "__main__":
    unittest.main()
