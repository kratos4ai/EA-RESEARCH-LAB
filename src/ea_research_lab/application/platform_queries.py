"""Semantic query composition over discovery and integrity-checked loads."""

from collections.abc import Mapping

from ea_research_lab.application.data_plane import (
    CanonicalChain,
    CanonicalChainRequest,
    DataPlane,
    DataPlaneError,
    DurableRun,
    reconstruct_canonical_chain,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.research_query import (
    Page,
    PageRequest,
    ResearchQueryPort,
)
from ea_research_lab.domain.analysis import AnalysisResult
from ea_research_lab.domain.dataset import Dataset
from ea_research_lab.domain.evidence import RawEvidenceManifestRef
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
)
from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    AnalysisSummary,
    CanonicalChainProjection,
    DatasetContentReference,
    DatasetDetail,
    DatasetSummary,
    ProvenanceSummary,
    ResearchRunDetail,
    ResearchRunSummary,
)
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)


_BOUNDED_ANALYSIS_RESULT = SchemaRef(
    SchemaName("execution-core-analysis-result"), SchemaVersion(0, 1, 0)
)


def list_research_runs(
    data_plane: DataPlane,
    research_query: ResearchQueryPort,
    page: PageRequest = PageRequest(),
) -> Page[ResearchRunSummary]:
    discovered = research_query.list_research_runs(page)
    return Page(
        tuple(_run_summary(data_plane.load_run(run_id)) for run_id in discovered.items),
        discovered.next_cursor,
    )


def list_run_datasets(
    data_plane: DataPlane,
    research_query: ResearchQueryPort,
    run_id: RunId,
    page: PageRequest = PageRequest(),
) -> Page[DatasetSummary]:
    if not isinstance(run_id, RunId):
        raise TypeError("Run Dataset query requires a RunId.")
    run = data_plane.load_run(run_id)
    run_evidence = {item.reference for item in run.evidence_history}
    discovered = research_query.list_run_datasets(run_id, page)
    datasets = tuple(data_plane.load_dataset(item) for item in discovered.items)
    if any(
        not any(
            reference in run_evidence
            for reference in item.provenance.input_manifests
        )
        for item in datasets
    ):
        raise _lineage_error()
    return Page(
        tuple(_dataset_summary(item) for item in datasets),
        discovered.next_cursor,
    )


def list_dataset_analyses(
    data_plane: DataPlane,
    research_query: ResearchQueryPort,
    dataset_id: DatasetId,
    page: PageRequest = PageRequest(),
) -> Page[AnalysisSummary]:
    if not isinstance(dataset_id, DatasetId):
        raise TypeError("Dataset Analysis query requires a DatasetId.")
    dataset = data_plane.load_dataset(dataset_id)
    discovered = research_query.list_dataset_analyses(dataset_id, page)
    analyses = tuple(data_plane.load_analysis(item) for item in discovered.items)
    if any(
        not any(
            input_dataset.provenance.dataset_id == dataset_id
            and input_dataset.content.content_digest
            == dataset.content.content_digest
            for input_dataset in item.input_datasets
        )
        for item in analyses
    ):
        raise _lineage_error()
    return Page(
        tuple(_analysis_summary(item) for item in analyses),
        discovered.next_cursor,
    )


class PlatformQueries:
    """Seven bounded queries over discovery and integrity-checked loads."""

    def __init__(
        self, data_plane: DataPlane, research_query: ResearchQueryPort
    ) -> None:
        self._data_plane = data_plane
        self._research_query = research_query

    def list_research_runs(
        self, context: RequestContext, page: PageRequest = PageRequest()
    ) -> Page[ResearchRunSummary]:
        _require_context(context)
        return list_research_runs(self._data_plane, self._research_query, page)

    def get_research_run(
        self, context: RequestContext, run_id: RunId
    ) -> ResearchRunDetail:
        _require_context(context)
        if not isinstance(run_id, RunId):
            raise TypeError("Research Run query requires a RunId.")
        return _run_detail(self._data_plane.load_run(run_id))

    def list_run_datasets(
        self,
        context: RequestContext,
        run_id: RunId,
        page: PageRequest = PageRequest(),
    ) -> Page[DatasetSummary]:
        _require_context(context)
        return list_run_datasets(
            self._data_plane, self._research_query, run_id, page
        )

    def get_dataset(
        self, context: RequestContext, dataset_id: DatasetId
    ) -> DatasetDetail:
        _require_context(context)
        if not isinstance(dataset_id, DatasetId):
            raise TypeError("Dataset query requires a DatasetId.")
        return _dataset_detail(self._data_plane.load_dataset(dataset_id))

    def list_dataset_analyses(
        self,
        context: RequestContext,
        dataset_id: DatasetId,
        page: PageRequest = PageRequest(),
    ) -> Page[AnalysisSummary]:
        _require_context(context)
        return list_dataset_analyses(
            self._data_plane, self._research_query, dataset_id, page
        )

    def get_analysis(
        self, context: RequestContext, analysis_result_id: AnalysisResultId
    ) -> AnalysisDetail:
        _require_context(context)
        if not isinstance(analysis_result_id, AnalysisResultId):
            raise TypeError("Analysis query requires an AnalysisResultId.")
        return _analysis_detail(
            self._data_plane.load_analysis(analysis_result_id)
        )

    def get_canonical_chain(
        self,
        context: RequestContext,
        build_record_id: BuildRecordId,
        run_id: RunId,
        analysis_result_id: AnalysisResultId,
    ) -> CanonicalChainProjection:
        _require_context(context)
        chain = reconstruct_canonical_chain(
            self._data_plane,
            CanonicalChainRequest(
                build_record_id, run_id, analysis_result_id
            ),
        )
        return _chain_projection(chain)


def _run_summary(run: DurableRun) -> ResearchRunSummary:
    document = run.run_manifest.value
    if not isinstance(document, Mapping):
        raise _lineage_error()
    evidence_document = document.get("raw_evidence_manifest")
    reference = _manifest_reference(evidence_document)
    evidence_outcome = None
    if reference is not None:
        evidence = next(
            (item for item in run.evidence_history if item.reference == reference),
            None,
        )
        if evidence is None:
            raise _lineage_error()
        evidence_outcome = evidence.manifest.outcome
    return ResearchRunSummary(
        RunId.parse(document["run_id"]),
        ArtifactId.parse(document["artifact_id"]),
        TestDefinitionRevisionId.parse(document["test_definition_revision_id"]),
        document["status"],
        UtcTimestamp.parse(document["created_at"]),
        run.run_manifest.schema_ref,
        reference,
        evidence_outcome,
        _optional_timestamp(document.get("started_at")),
        _optional_timestamp(document.get("finished_at")),
    )


def _dataset_summary(dataset: Dataset) -> DatasetSummary:
    return DatasetSummary(
        dataset.provenance.dataset_id,
        dataset.created_at,
        dataset.manifest.schema_ref,
        dataset.content.payload.schema_ref,
        dataset.content.content_digest,
        dataset.provenance.transformation_id,
        dataset.provenance.transformation_version,
    )


def _analysis_summary(result: AnalysisResult) -> AnalysisSummary:
    return AnalysisSummary(
        result.provenance.analysis_result_id,
        result.created_at,
        result.envelope.schema_ref,
        result.content.payload.schema_ref,
        result.content.content_digest,
        result.provenance.analysis_definition_id,
        result.provenance.analysis_version,
    )


def _run_detail(run: DurableRun) -> ResearchRunDetail:
    document = run.run_manifest.value
    definition = run.test_definition.value
    try:
        reproducibility = document["execution_reproducibility"]
        reasons = tuple(
            ReproducibilityReason(item["code"], item["detail"])
            for item in reproducibility["reasons"]
        )
        assessment = ReproducibilityAssessment(
            ReproducibilityLevel(reproducibility["level"]), reasons
        )
        return ResearchRunDetail(
            _run_summary(run),
            TestDefinitionId.parse(definition["test_definition_id"]),
            EnvironmentConfigurationId.parse(
                document["environment_configuration_id"]
            ),
            assessment,
            tuple(item.reference for item in run.evidence_history),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _lineage_error() from error


def _dataset_detail(dataset: Dataset) -> DatasetDetail:
    parameters = dataset.provenance.transformation_parameters
    return DatasetDetail(
        _dataset_summary(dataset),
        dataset.provenance.input_manifests,
        dataset.provenance.input_datasets,
        None if parameters is None else parameters.schema_ref,
    )


def _analysis_detail(result: AnalysisResult) -> AnalysisDetail:
    bounded_result = (
        result.content.payload
        if result.content.payload.schema_ref == _BOUNDED_ANALYSIS_RESULT
        else None
    )
    return AnalysisDetail(
        _analysis_summary(result),
        tuple(
            DatasetContentReference(
                dataset.provenance.dataset_id, dataset.content.content_digest
            )
            for dataset in result.input_datasets
        ),
        result.provenance.analysis_parameters.schema_ref,
        result.provenance.computation_environment_id,
        bounded_result,
    )


def _chain_projection(chain: CanonicalChain) -> CanonicalChainProjection:
    artifact = chain.build.artifact_acceptance
    if artifact is None:
        raise _lineage_error()
    datasets = tuple(_dataset_summary(item) for item in chain.datasets)
    analysis = _analysis_detail(chain.analysis)
    return CanonicalChainProjection(
        ProvenanceSummary(
            chain.build.build_record_id,
            artifact.artifact.artifact_id,
            chain.run.test_definition_revision_id,
            chain.run.run_id,
            tuple(item.reference for item in chain.run.evidence_history),
            tuple(
                DatasetContentReference(item.dataset_id, item.content_digest)
                for item in datasets
            ),
            chain.analysis.provenance.analysis_result_id,
        ),
        _run_detail(chain.run),
        datasets,
        analysis,
    )


def _require_context(context: RequestContext) -> None:
    if not isinstance(context, RequestContext):
        raise TypeError("Platform Query requires RequestContext.")


def _manifest_reference(value: object) -> RawEvidenceManifestRef | None:
    if value is None:
        return None
    if not isinstance(value, Mapping):
        raise _lineage_error()
    try:
        return RawEvidenceManifestRef(
            RawEvidenceManifestId.parse(value["manifest_id"]),
            RunId.parse(value["run_id"]),
            Sha256Digest(value["content_digest"]),
        )
    except (KeyError, TypeError, ValueError) as error:
        raise _lineage_error() from error


def _optional_timestamp(value: object) -> UtcTimestamp | None:
    if value is None:
        return None
    if not isinstance(value, str):
        raise _lineage_error()
    return UtcTimestamp.parse(value)


def _lineage_error() -> DataPlaneError:
    return DataPlaneError(
        ApplicationErrorCode.DATA_INTEGRITY_FAILED,
        "Research query lineage failed integrity checks.",
    )
