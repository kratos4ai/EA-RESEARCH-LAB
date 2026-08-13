from __future__ import annotations

import base64
import copy
import hashlib
import json
import sqlite3
from contextlib import closing
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock, patch

from ea_research_lab.application.data_plane import (
    DATASET_MANIFEST_REF,
    RAW_EVIDENCE_MANIFEST_REF,
    RUN_MANIFEST_REF,
    DataPlaneError,
    DurableEvidence,
    DurableRun,
    reconstruct_canonical_chain,
)
from ea_research_lab.application.platform_queries import (
    PlatformQueries,
    list_dataset_analyses,
    list_research_runs,
    list_run_datasets,
    _dataset_detail,
)
from ea_research_lab.application.research_query import (
    DEFAULT_PAGE_LIMIT,
    MAX_PAGE_LIMIT,
    PageRequest,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.analysis import AnalysisResult
from ea_research_lab.domain.dataset import Dataset, DatasetContent
from ea_research_lab.application.execution import CollectedRawEvidence
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifest,
    RawEvidenceManifestRef,
    RawEvidenceObject,
)
from ea_research_lab.domain.identifiers import (
    ArtifactId,
    BuildRecordId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
)
from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    AnalysisSummary,
    CanonicalChainProjection,
    DatasetDetail,
    DatasetSummary,
    ResearchRunDetail,
    ResearchRunSummary,
)
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from ea_research_lab.infrastructure.sqlite_research_query import (
    SqliteResearchQuery,
)
from tests.test_sqlite_data_plane_chain import (
    _analysis,
    _dataset,
    _payload,
    _plain,
    _run,
    _successful_build,
    _canonical,
)


def _run_at(run: DurableRun, timestamp: str) -> DurableRun:
    document = copy.deepcopy(_plain(run.run_manifest.value))
    document["created_at"] = timestamp
    return DurableRun(
        run.test_definition,
        _payload(RUN_MANIFEST_REF, document),
        run.evidence_history,
    )


def _dataset_at(dataset: Dataset, timestamp: str) -> Dataset:
    created_at = UtcTimestamp.parse(timestamp)
    document = copy.deepcopy(_plain(dataset.manifest.value))
    document["created_at"] = timestamp
    return Dataset(
        dataset.content,
        dataset.provenance,
        _payload(DATASET_MANIFEST_REF, document),
        created_at,
    )


def _analysis_at(result: AnalysisResult, timestamp: str) -> AnalysisResult:
    created_at = UtcTimestamp.parse(timestamp)
    document = copy.deepcopy(_plain(result.envelope.value))
    document["created_at"] = timestamp
    return AnalysisResult(
        result.content,
        result.provenance,
        result.input_datasets,
        _payload(result.envelope.schema_ref, document),
        created_at,
    )


def _run_with_evidence_objects(count: int) -> DurableRun:
    original = _run()
    collected = tuple(
        CollectedRawEvidence(
            RawEvidenceObject(
                new_entity_id(RawEvidenceObjectId),
                "application/octet-stream",
                len(content := f"bounded-evidence-{index}".encode()),
                Sha256Digest(hashlib.sha256(content).hexdigest()),
                provider_namespace="portable.fake",
            ),
            content,
        )
        for index in range(count)
    )
    manifest = RawEvidenceManifest(
        new_entity_id(RawEvidenceManifestId),
        original.run_id,
        tuple(item.evidence_object for item in collected),
        UtcTimestamp.parse("2026-08-12T12:00:00Z"),
        EvidenceCollectionOutcome.COMPLETED,
    )
    document = {
        "schema_name": "raw-evidence-manifest",
        "schema_version": "0.1.0",
        "manifest_id": str(manifest.manifest_id),
        "run_id": str(manifest.run_id),
        "objects": [
            {
                "object_id": str(item.evidence_object.object_id),
                "media_type": item.evidence_object.media_type,
                "byte_length": item.evidence_object.byte_length,
                "content_digest": str(item.evidence_object.content_digest),
                "provider_namespace": item.evidence_object.provider_namespace,
            }
            for item in collected
        ],
        "sealed_at": str(manifest.sealed_at),
        "outcome": manifest.outcome.value,
    }
    reference = RawEvidenceManifestRef(
        manifest.manifest_id,
        manifest.run_id,
        Sha256Digest(hashlib.sha256(_canonical(document)).hexdigest()),
    )
    evidence = DurableEvidence(
        manifest,
        _payload(RAW_EVIDENCE_MANIFEST_REF, document),
        reference,
        collected,
    )
    run_document = copy.deepcopy(_plain(original.run_manifest.value))
    run_document["raw_evidence_manifest"] = {
        "manifest_id": str(reference.manifest_id),
        "run_id": str(reference.run_id),
        "content_digest": str(reference.content_digest),
    }
    return DurableRun(
        original.test_definition,
        _payload(RUN_MANIFEST_REF, run_document),
        (evidence,),
    )


def _seed(database: Path):
    build = _successful_build()
    runs = (
        _run_at(_run(), "2026-08-11T13:58:00Z"),
        _run_at(_run(), "2026-08-11T13:58:00Z"),
        _run_at(_run(), "2026-08-11T13:58:00.500000Z"),
    )
    datasets = (
        _dataset_at(_dataset(runs[0]), "2026-08-11T14:01:00Z"),
        _dataset_at(_dataset(runs[0]), "2026-08-11T14:01:00Z"),
        _dataset_at(_dataset(runs[0]), "2026-08-11T14:01:00.500000Z"),
    )
    unrelated_dataset = _dataset_at(
        _dataset(runs[1]), "2026-08-11T14:00:00Z"
    )
    with patch(
        "ea_research_lab.application.analysis._now",
        return_value=UtcTimestamp.parse("2026-08-11T14:03:00Z"),
    ):
        analyses = (
            _analysis(datasets[0]),
            _analysis(datasets[0]),
        )
        unrelated_analysis = _analysis(unrelated_dataset)
    with patch(
        "ea_research_lab.application.analysis._now",
        return_value=UtcTimestamp.parse("2026-08-11T14:03:00.500000Z"),
    ):
        analyses += (_analysis(datasets[0]),)

    with SqliteDataPlane(database) as data_plane:
        data_plane.publish_build(build)
        for run in runs:
            data_plane.publish_run(run)
        for dataset in (*datasets, unrelated_dataset):
            data_plane.publish_dataset(dataset)
        for analysis in (*analyses, unrelated_analysis):
            data_plane.publish_analysis(analysis)
    return runs, datasets, analyses


def _all_pages(fetch):
    items = []
    cursor = None
    while True:
        page = fetch(PageRequest(2, cursor))
        items.extend(page.items)
        if page.next_cursor is None:
            return tuple(items)
        cursor = page.next_cursor


class ResearchQueryTests(unittest.TestCase):
    def setUp(self) -> None:
        self.temporary = tempfile.TemporaryDirectory()
        self.addCleanup(self.temporary.cleanup)
        self.database = Path(self.temporary.name) / "research.sqlite3"
        self.runs, self.datasets, self.analyses = _seed(self.database)

    def test_keyset_pages_are_ordered_complete_and_repeatable(self) -> None:
        same_time = sorted(self.runs[:2], key=lambda item: str(item.run_id))
        expected_runs = tuple(item.run_id for item in (self.runs[2], *same_time))
        expected_datasets = tuple(
            item.provenance.dataset_id
            for item in (
                *sorted(
                    self.datasets[:2],
                    key=lambda item: str(item.provenance.dataset_id),
                ),
                self.datasets[2],
            )
        )
        expected_analyses = tuple(
            item.provenance.analysis_result_id
            for item in (
                self.analyses[2],
                *sorted(
                    self.analyses[:2],
                    key=lambda item: str(item.provenance.analysis_result_id),
                ),
            )
        )
        with SqliteResearchQuery(self.database) as query:
            runs = _all_pages(query.list_research_runs)
            datasets = _all_pages(
                lambda page: query.list_run_datasets(self.runs[0].run_id, page)
            )
            analyses = _all_pages(
                lambda page: query.list_dataset_analyses(
                    self.datasets[0].provenance.dataset_id, page
                )
            )
            self.assertEqual(runs, expected_runs)
            self.assertEqual(datasets, expected_datasets)
            self.assertEqual(analyses, expected_analyses)
            self.assertEqual(_all_pages(query.list_research_runs), runs)
            self.assertEqual(len(set(runs)), len(runs))
            self.assertEqual(len(set(datasets)), len(datasets))
            self.assertEqual(len(set(analyses)), len(analyses))

    def test_page_limits_and_final_page_are_explicit(self) -> None:
        self.assertEqual(PageRequest().limit, DEFAULT_PAGE_LIMIT)
        self.assertEqual(PageRequest(MAX_PAGE_LIMIT).limit, MAX_PAGE_LIMIT)
        for invalid in (0, MAX_PAGE_LIMIT + 1, True):
            with self.subTest(limit=invalid):
                with self.assertRaises(InvalidValueError):
                    PageRequest(invalid)
        with SqliteResearchQuery(self.database) as query:
            first = query.list_research_runs(PageRequest(2))
            final = query.list_research_runs(PageRequest(2, first.next_cursor))
            self.assertEqual(len(first.items), 2)
            self.assertIsNotNone(first.next_cursor)
            self.assertEqual(len(final.items), 1)
            self.assertIsNone(final.next_cursor)

    def test_cursor_is_bound_to_query_and_parent(self) -> None:
        with SqliteResearchQuery(self.database) as query:
            run_cursor = query.list_research_runs(PageRequest(1)).next_cursor
            dataset_cursor = query.list_run_datasets(
                self.runs[0].run_id, PageRequest(1)
            ).next_cursor
            self.assertIsNotNone(run_cursor)
            self.assertIsNotNone(dataset_cursor)
            with self.assertRaises(InvalidValueError):
                query.list_research_runs(PageRequest(1, "not-a-cursor"))
            with self.assertRaises(InvalidValueError):
                query.list_run_datasets(
                    self.runs[0].run_id, PageRequest(1, run_cursor)
                )
            with self.assertRaises(InvalidValueError):
                query.list_run_datasets(
                    self.runs[1].run_id, PageRequest(1, dataset_cursor)
                )
            padding = "=" * (-len(run_cursor) % 4)
            document = json.loads(
                base64.urlsafe_b64decode(f"{run_cursor}{padding}")
            )
            document["version"] = 2
            incompatible = base64.urlsafe_b64encode(
                json.dumps(document).encode("utf-8")
            ).decode("ascii")
            with self.assertRaises(InvalidValueError):
                query.list_research_runs(PageRequest(1, incompatible))

    def test_semantic_lists_use_integrity_checked_data_plane_loads(self) -> None:
        with (
            SqliteDataPlane(self.database) as data_plane,
            SqliteResearchQuery(self.database) as query,
        ):
            tracked = Mock(wraps=data_plane)
            run_page = list_research_runs(tracked, query, PageRequest(1))
            dataset_page = list_run_datasets(
                tracked, query, self.runs[0].run_id, PageRequest(1)
            )
            analysis_page = list_dataset_analyses(
                tracked,
                query,
                self.datasets[0].provenance.dataset_id,
                PageRequest(1),
            )
            self.assertIsInstance(run_page.items[0], ResearchRunSummary)
            self.assertIsInstance(dataset_page.items[0], DatasetSummary)
            self.assertIsInstance(analysis_page.items[0], AnalysisSummary)
            self.assertGreaterEqual(tracked.load_run.call_count, 2)
            tracked.load_dataset.assert_called()
            tracked.load_analysis.assert_called_once()

            run = next(
                item
                for item in self.runs
                if item.run_id == run_page.items[0].run_id
            )
            self.assertEqual(
                run_page.items[0].manifest_schema,
                run.run_manifest.schema_ref,
            )
            self.assertEqual(
                run_page.items[0].status,
                run.run_manifest.value["status"],
            )
            self.assertEqual(
                run_page.items[0].evidence_manifest,
                run.evidence_history[-1].reference,
            )
            self.assertEqual(
                run_page.items[0].evidence_outcome,
                run.evidence_history[-1].manifest.outcome,
            )
            dataset = next(
                item
                for item in self.datasets
                if item.provenance.dataset_id == dataset_page.items[0].dataset_id
            )
            self.assertEqual(
                dataset_page.items[0].content_digest,
                dataset.content.content_digest,
            )
            self.assertEqual(
                dataset_page.items[0].content_schema,
                dataset.content.payload.schema_ref,
            )
            self.assertEqual(
                dataset_page.items[0].transformation_id,
                dataset.provenance.transformation_id,
            )
            analysis = next(
                item
                for item in self.analyses
                if item.provenance.analysis_result_id
                == analysis_page.items[0].analysis_result_id
            )
            self.assertEqual(
                analysis_page.items[0].result_schema,
                analysis.content.payload.schema_ref,
            )
            self.assertEqual(
                analysis_page.items[0].result_digest,
                analysis.content.content_digest,
            )
            self.assertEqual(
                analysis_page.items[0].analysis_definition_id,
                analysis.provenance.analysis_definition_id,
            )

    def test_closed_or_missing_query_store_fails_safely(self) -> None:
        missing = Path(self.temporary.name) / "missing.sqlite3"
        with self.assertRaises(DataPlaneError):
            SqliteResearchQuery(missing)
        query = SqliteResearchQuery(self.database)
        query.close()
        with self.assertRaises(DataPlaneError):
            query.list_research_runs(PageRequest())

    def test_artifact_to_build_discovery_is_exact_and_fails_closed(self) -> None:
        build = _successful_build()
        artifact_id = build.artifact_acceptance.artifact.artifact_id
        with SqliteResearchQuery(self.database) as query:
            self.assertEqual(
                query.find_build_record_for_artifact(artifact_id),
                build.build_record_id,
            )
            with self.assertRaises(DataPlaneError):
                query.find_build_record_for_artifact(new_entity_id(ArtifactId))

        duplicate = copy.deepcopy(_plain(build.build_record.value))
        duplicate_id = new_entity_id(BuildRecordId)
        duplicate["build_record_id"] = str(duplicate_id)
        content = json.dumps(
            duplicate,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        digest = hashlib.sha256(content).hexdigest()
        with closing(sqlite3.connect(self.database)) as connection:
            connection.execute(
                "INSERT INTO content_objects VALUES (?, ?, ?)",
                (digest, len(content), content),
            )
            connection.execute(
                "INSERT INTO published_records VALUES (?, ?, ?, ?)",
                ("build-record", str(duplicate_id), str(build.build_record.schema_ref), digest),
            )
            connection.commit()
        with SqliteResearchQuery(self.database) as query:
            with self.assertRaises(DataPlaneError):
                query.find_build_record_for_artifact(artifact_id)

    def test_execution_summary_projection_rejects_another_schema_version(self) -> None:
        dataset = self.datasets[0]
        incompatible = Dataset(
            DatasetContent(
                _payload(
                    SchemaRef(
                        SchemaName("execution-summary"), SchemaVersion(0, 2, 0)
                    ),
                    _plain(dataset.content.payload.value),
                )
            ),
            dataset.provenance,
            dataset.manifest,
            dataset.created_at,
        )
        with self.assertRaises(DataPlaneError):
            _dataset_detail(incompatible)

    def test_platform_queries_return_bounded_details_and_verified_chain(self) -> None:
        context = RequestContext(new_entity_id(RequestId), "query-client")
        with (
            SqliteDataPlane(self.database) as data_plane,
            SqliteResearchQuery(self.database) as discovery,
        ):
            tracked = Mock(wraps=data_plane)
            queries = PlatformQueries(tracked, discovery)
            run = queries.get_research_run(context, self.runs[0].run_id)
            dataset = queries.get_dataset(
                context, self.datasets[0].provenance.dataset_id
            )
            analysis = queries.get_analysis(
                context, self.analyses[0].provenance.analysis_result_id
            )
            with patch(
                "ea_research_lab.application.platform_queries.reconstruct_canonical_chain",
                wraps=reconstruct_canonical_chain,
            ) as reconstruction:
                chain = queries.get_canonical_chain(
                    context,
                    _successful_build().build_record_id,
                    self.runs[0].run_id,
                    self.analyses[0].provenance.analysis_result_id,
                )

        self.assertIsInstance(run, ResearchRunDetail)
        self.assertEqual(run.summary.run_id, self.runs[0].run_id)
        self.assertEqual(run.build_record_id, _successful_build().build_record_id)
        self.assertEqual(
            run.evidence_history,
            tuple(item.reference for item in self.runs[0].evidence_history),
        )
        self.assertFalse(hasattr(run, "raw_evidence"))
        self.assertIsInstance(dataset, DatasetDetail)
        self.assertEqual(dataset.execution_summary.total_trades, 10)
        self.assertEqual(str(dataset.execution_summary.net_profit), "100.00")
        self.assertEqual(dataset.execution_summary.currency, "USD")
        self.assertEqual(str(dataset.execution_summary.initial_deposit), "1000.00")
        self.assertEqual(
            dataset.input_manifests,
            self.datasets[0].provenance.input_manifests,
        )
        self.assertFalse(hasattr(dataset, "content"))
        self.assertIsInstance(analysis, AnalysisDetail)
        self.assertIsNone(analysis.bounded_result)
        self.assertEqual(
            tuple(item.content_digest for item in analysis.input_datasets),
            tuple(item.content.content_digest for item in self.analyses[0].input_datasets),
        )
        self.assertIsInstance(chain, CanonicalChainProjection)
        reconstruction.assert_called_once()
        self.assertEqual(chain.provenance.run_id, self.runs[0].run_id)
        self.assertEqual(
            chain.provenance.analysis_result_id,
            self.analyses[0].provenance.analysis_result_id,
        )
        tracked.load_run.assert_called()
        tracked.load_build.assert_called()
        tracked.load_dataset.assert_called()
        tracked.load_analysis.assert_called()

    def test_platform_query_lists_preserve_m1_continuation(self) -> None:
        context = RequestContext(new_entity_id(RequestId), "query-client")
        with (
            SqliteDataPlane(self.database) as data_plane,
            SqliteResearchQuery(self.database) as discovery,
        ):
            queries = PlatformQueries(data_plane, discovery)
            first = queries.list_research_runs(context, PageRequest(2))
            second = queries.list_research_runs(
                context, PageRequest(2, first.next_cursor)
            )

        self.assertEqual(len(first.items), 2)
        self.assertIsNotNone(first.next_cursor)
        self.assertEqual(len(second.items), 1)
        self.assertIsNone(second.next_cursor)

    def test_evidence_metadata_is_bounded_and_cursor_bound_to_manifest(self) -> None:
        run = _run_with_evidence_objects(257)
        other = _run_with_evidence_objects(1)
        expected = tuple(
            item.evidence_object.object_id
            for item in run.evidence_history[-1].raw_evidence
        )
        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "bounded-evidence.sqlite3"
            with SqliteDataPlane(database) as data_plane:
                data_plane.publish_build(_successful_build())
                data_plane.publish_run(run)
                data_plane.publish_run(other)
            with SqliteResearchQuery(database) as discovery:
                statements: list[str] = []
                discovery._connection.set_trace_callback(statements.append)
                data_plane = Mock()
                data_plane.load_run.side_effect = AssertionError(
                    "Evidence listing must not load a DurableRun or Evidence bytes."
                )
                queries = PlatformQueries(data_plane, discovery)
                context = RequestContext(new_entity_id(RequestId), "query-client")
                cursor = None
                observed = []
                page_sizes = []
                while True:
                    page = queries.list_run_evidence_objects(
                        context,
                        run.run_id,
                        run.evidence_history[-1].reference.manifest_id,
                        PageRequest(17, cursor),
                    )
                    observed.extend(item.object_id for item in page.items)
                    page_sizes.append(len(page.items))
                    if page.next_cursor is None:
                        break
                    cursor = page.next_cursor

                first_cursor = queries.list_run_evidence_objects(
                    context,
                    run.run_id,
                    run.evidence_history[-1].reference.manifest_id,
                    PageRequest(1),
                ).next_cursor
                with self.assertRaises(InvalidValueError):
                    queries.list_run_evidence_objects(
                        context,
                        other.run_id,
                        run.evidence_history[-1].reference.manifest_id,
                        PageRequest(1, first_cursor),
                    )
                with self.assertRaises(InvalidValueError):
                    queries.list_run_evidence_objects(
                        context,
                        run.run_id,
                        other.evidence_history[-1].reference.manifest_id,
                        PageRequest(1, first_cursor),
                    )

        self.assertEqual(tuple(observed), expected)
        self.assertEqual(len(set(observed)), len(expected))
        self.assertTrue(all(1 <= size <= 17 for size in page_sizes))
        self.assertFalse(hasattr(page.items[0], "content"))
        data_plane.load_run.assert_not_called()
        evidence_queries = [
            statement
            for statement in statements
            if "json_each" in statement and "raw-evidence-object" in statement
        ]
        self.assertTrue(evidence_queries)
        self.assertTrue(any("LIMIT 18" in statement for statement in evidence_queries))
        self.assertTrue(all("LIMIT " in statement for statement in evidence_queries))


if __name__ == "__main__":
    unittest.main()
