"""Immutable provider-neutral semantic query values."""

from dataclasses import dataclass
from datetime import date
from decimal import Decimal

from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifestRef,
)
from ea_research_lab.domain.errors import InvalidValueError
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
    TestDefinitionId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    SchemaRef,
    Sha256Digest,
    UtcTimestamp,
)


_RUN_STATUSES = frozenset({"created", "running", "completed", "failed", "cancelled"})


@dataclass(frozen=True, slots=True)
class ResearchRunSummary:
    run_id: RunId
    artifact_id: ArtifactId
    test_definition_revision_id: TestDefinitionRevisionId
    status: str
    created_at: UtcTimestamp
    manifest_schema: SchemaRef
    evidence_manifest: RawEvidenceManifestRef | None
    evidence_outcome: EvidenceCollectionOutcome | None
    started_at: UtcTimestamp | None = None
    finished_at: UtcTimestamp | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.run_id, RunId)
            or not isinstance(self.artifact_id, ArtifactId)
            or not isinstance(
                self.test_definition_revision_id, TestDefinitionRevisionId
            )
            or not isinstance(self.status, str)
            or self.status not in _RUN_STATUSES
            or not isinstance(self.created_at, UtcTimestamp)
            or not isinstance(self.manifest_schema, SchemaRef)
            or (
                self.started_at is not None
                and not isinstance(self.started_at, UtcTimestamp)
            )
            or (
                self.finished_at is not None
                and not isinstance(self.finished_at, UtcTimestamp)
            )
            or (self.evidence_manifest is None) != (self.evidence_outcome is None)
            or (
                self.evidence_manifest is not None
                and not isinstance(self.evidence_manifest, RawEvidenceManifestRef)
            )
            or (
                self.evidence_outcome is not None
                and not isinstance(self.evidence_outcome, EvidenceCollectionOutcome)
            )
        ):
            raise InvalidValueError("Research Run summary is invalid.")


@dataclass(frozen=True, slots=True)
class DatasetSummary:
    dataset_id: DatasetId
    created_at: UtcTimestamp
    manifest_schema: SchemaRef
    content_schema: SchemaRef
    content_digest: Sha256Digest
    transformation_id: TransformationId
    transformation_version: DefinitionVersion

    def __post_init__(self) -> None:
        required = (
            (self.dataset_id, DatasetId),
            (self.created_at, UtcTimestamp),
            (self.manifest_schema, SchemaRef),
            (self.content_schema, SchemaRef),
            (self.content_digest, Sha256Digest),
            (self.transformation_id, TransformationId),
            (self.transformation_version, DefinitionVersion),
        )
        if any(not isinstance(value, expected) for value, expected in required):
            raise InvalidValueError("Dataset summary is invalid.")


@dataclass(frozen=True, slots=True)
class AnalysisSummary:
    analysis_result_id: AnalysisResultId
    created_at: UtcTimestamp
    envelope_schema: SchemaRef
    result_schema: SchemaRef
    result_digest: Sha256Digest
    analysis_definition_id: AnalysisDefinitionId
    analysis_version: DefinitionVersion

    def __post_init__(self) -> None:
        required = (
            (self.analysis_result_id, AnalysisResultId),
            (self.created_at, UtcTimestamp),
            (self.envelope_schema, SchemaRef),
            (self.result_schema, SchemaRef),
            (self.result_digest, Sha256Digest),
            (self.analysis_definition_id, AnalysisDefinitionId),
            (self.analysis_version, DefinitionVersion),
        )
        if any(not isinstance(value, expected) for value, expected in required):
            raise InvalidValueError("Analysis summary is invalid.")


@dataclass(frozen=True, slots=True)
class ExecutionSummaryProjection:
    total_trades: int
    winning_trades: int
    losing_trades: int
    net_profit: Decimal
    currency: str
    initial_deposit: Decimal

    def __post_init__(self) -> None:
        counts = (self.total_trades, self.winning_trades, self.losing_trades)
        if (
            any(type(value) is not int or value < 0 for value in counts)
            or not isinstance(self.net_profit, Decimal)
            or not self.net_profit.is_finite()
            or not isinstance(self.initial_deposit, Decimal)
            or not self.initial_deposit.is_finite()
            or not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isupper()
        ):
            raise InvalidValueError("Execution summary projection is invalid.")


@dataclass(frozen=True, slots=True)
class ExperimentContextProjection:
    instrument: str
    timeframe: str
    start_date: date
    end_date: date
    requested_initial_capital: Decimal
    currency: str
    leverage: str

    def __post_init__(self) -> None:
        if (
            not isinstance(self.instrument, str)
            or not self.instrument
            or self.instrument.strip() != self.instrument
            or not isinstance(self.timeframe, str)
            or not self.timeframe
            or self.timeframe.strip() != self.timeframe
            or not isinstance(self.start_date, date)
            or not isinstance(self.end_date, date)
            or self.start_date >= self.end_date
            or not isinstance(self.requested_initial_capital, Decimal)
            or not self.requested_initial_capital.is_finite()
            or self.requested_initial_capital <= 0
            or not isinstance(self.currency, str)
            or len(self.currency) != 3
            or not self.currency.isascii()
            or not self.currency.isupper()
            or not isinstance(self.leverage, str)
            or not self.leverage.startswith("1:")
            or not self.leverage[2:].isdigit()
            or int(self.leverage[2:]) <= 0
        ):
            raise InvalidValueError("Experiment context projection is invalid.")


@dataclass(frozen=True, slots=True)
class ProviderRuntimeProjection:
    role: str
    provider_namespace: str
    version: str | None
    executable_digest: Sha256Digest | None

    def __post_init__(self) -> None:
        if (
            self.role not in {"build", "execution"}
            or not isinstance(self.provider_namespace, str)
            or not self.provider_namespace
            or (
                self.version is not None
                and (not isinstance(self.version, str) or not self.version)
            )
            or (
                self.executable_digest is not None
                and not isinstance(self.executable_digest, Sha256Digest)
            )
        ):
            raise InvalidValueError("Provider runtime projection is invalid.")


@dataclass(frozen=True, slots=True)
class ResearchRunDetail:
    summary: ResearchRunSummary
    build_record_id: BuildRecordId
    test_definition_id: TestDefinitionId
    environment_configuration_id: EnvironmentConfigurationId
    execution_reproducibility: ReproducibilityAssessment
    evidence_history: tuple[RawEvidenceManifestRef, ...]
    experiment_context: ExperimentContextProjection | None = None
    provider_runtimes: tuple[ProviderRuntimeProjection, ...] = ()

    def __post_init__(self) -> None:
        required = (
            (self.summary, ResearchRunSummary),
            (self.build_record_id, BuildRecordId),
            (self.test_definition_id, TestDefinitionId),
            (self.environment_configuration_id, EnvironmentConfigurationId),
            (self.execution_reproducibility, ReproducibilityAssessment),
        )
        try:
            history = tuple(self.evidence_history)
            runtimes = tuple(self.provider_runtimes)
        except TypeError as error:
            raise InvalidValueError("Research Run detail is invalid.") from error
        if any(not isinstance(value, expected) for value, expected in required) or (
            not history
            or any(not isinstance(item, RawEvidenceManifestRef) for item in history)
            or (
                self.experiment_context is not None
                and not isinstance(
                    self.experiment_context, ExperimentContextProjection
                )
            )
            or any(not isinstance(item, ProviderRuntimeProjection) for item in runtimes)
        ):
            raise InvalidValueError("Research Run detail is invalid.")
        object.__setattr__(self, "evidence_history", history)
        object.__setattr__(self, "provider_runtimes", runtimes)


@dataclass(frozen=True, slots=True)
class EvidenceObjectSummary:
    manifest_id: RawEvidenceManifestId
    object_id: RawEvidenceObjectId
    media_type: str
    byte_length: int
    content_digest: Sha256Digest
    payload_schema: SchemaRef | None = None
    provider_namespace: str | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.manifest_id, RawEvidenceManifestId)
            or not isinstance(self.object_id, RawEvidenceObjectId)
            or not isinstance(self.media_type, str)
            or not self.media_type
            or type(self.byte_length) is not int
            or self.byte_length < 0
            or not isinstance(self.content_digest, Sha256Digest)
            or (
                self.payload_schema is not None
                and not isinstance(self.payload_schema, SchemaRef)
            )
            or (
                self.provider_namespace is not None
                and (
                    not isinstance(self.provider_namespace, str)
                    or not self.provider_namespace
                )
            )
        ):
            raise InvalidValueError("Evidence Object summary is invalid.")


@dataclass(frozen=True, slots=True)
class DatasetDetail:
    summary: DatasetSummary
    input_manifests: tuple[RawEvidenceManifestRef, ...]
    input_datasets: tuple[DatasetId, ...]
    transformation_parameters_schema: SchemaRef | None
    execution_summary: ExecutionSummaryProjection | None = None

    def __post_init__(self) -> None:
        try:
            manifests = tuple(self.input_manifests)
            datasets = tuple(self.input_datasets)
        except TypeError as error:
            raise InvalidValueError("Dataset detail is invalid.") from error
        if (
            not isinstance(self.summary, DatasetSummary)
            or any(not isinstance(item, RawEvidenceManifestRef) for item in manifests)
            or any(not isinstance(item, DatasetId) for item in datasets)
            or not manifests and not datasets
            or (
                self.transformation_parameters_schema is not None
                and not isinstance(self.transformation_parameters_schema, SchemaRef)
            )
            or (
                self.execution_summary is not None
                and not isinstance(
                    self.execution_summary, ExecutionSummaryProjection
                )
            )
        ):
            raise InvalidValueError("Dataset detail is invalid.")
        object.__setattr__(self, "input_manifests", manifests)
        object.__setattr__(self, "input_datasets", datasets)


@dataclass(frozen=True, slots=True)
class DatasetContentReference:
    dataset_id: DatasetId
    content_digest: Sha256Digest

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, DatasetId) or not isinstance(
            self.content_digest, Sha256Digest
        ):
            raise InvalidValueError("Dataset content reference is invalid.")


@dataclass(frozen=True, slots=True)
class AnalysisDetail:
    summary: AnalysisSummary
    input_datasets: tuple[DatasetContentReference, ...]
    analysis_parameters_schema: SchemaRef
    computation_environment_id: EnvironmentConfigurationId
    bounded_result: SchemaReferencedPayload | None = None

    def __post_init__(self) -> None:
        try:
            inputs = tuple(self.input_datasets)
        except TypeError as error:
            raise InvalidValueError("Analysis detail is invalid.") from error
        if (
            not isinstance(self.summary, AnalysisSummary)
            or not inputs
            or any(not isinstance(item, DatasetContentReference) for item in inputs)
            or not isinstance(self.analysis_parameters_schema, SchemaRef)
            or not isinstance(
                self.computation_environment_id, EnvironmentConfigurationId
            )
            or (
                self.bounded_result is not None
                and not isinstance(self.bounded_result, SchemaReferencedPayload)
            )
        ):
            raise InvalidValueError("Analysis detail is invalid.")
        object.__setattr__(self, "input_datasets", inputs)


@dataclass(frozen=True, slots=True)
class ProvenanceSummary:
    build_record_id: BuildRecordId
    artifact_id: ArtifactId
    artifact_digest: Sha256Digest
    test_definition_revision_id: TestDefinitionRevisionId
    run_id: RunId
    evidence_manifests: tuple[RawEvidenceManifestRef, ...]
    datasets: tuple[DatasetContentReference, ...]
    analysis_result_id: AnalysisResultId

    def __post_init__(self) -> None:
        required = (
            (self.build_record_id, BuildRecordId),
            (self.artifact_id, ArtifactId),
            (self.artifact_digest, Sha256Digest),
            (self.test_definition_revision_id, TestDefinitionRevisionId),
            (self.run_id, RunId),
            (self.analysis_result_id, AnalysisResultId),
        )
        try:
            evidence = tuple(self.evidence_manifests)
            datasets = tuple(self.datasets)
        except TypeError as error:
            raise InvalidValueError("Provenance summary is invalid.") from error
        if (
            any(not isinstance(value, expected) for value, expected in required)
            or not evidence
            or any(not isinstance(item, RawEvidenceManifestRef) for item in evidence)
            or not datasets
            or any(not isinstance(item, DatasetContentReference) for item in datasets)
        ):
            raise InvalidValueError("Provenance summary is invalid.")
        object.__setattr__(self, "evidence_manifests", evidence)
        object.__setattr__(self, "datasets", datasets)


@dataclass(frozen=True, slots=True)
class CanonicalChainProjection:
    provenance: ProvenanceSummary
    run: ResearchRunDetail
    datasets: tuple[DatasetSummary, ...]
    analysis: AnalysisDetail

    def __post_init__(self) -> None:
        try:
            datasets = tuple(self.datasets)
        except TypeError as error:
            raise InvalidValueError("Canonical chain projection is invalid.") from error
        if (
            not isinstance(self.provenance, ProvenanceSummary)
            or not isinstance(self.run, ResearchRunDetail)
            or not datasets
            or any(not isinstance(item, DatasetSummary) for item in datasets)
            or not isinstance(self.analysis, AnalysisDetail)
        ):
            raise InvalidValueError("Canonical chain projection is invalid.")
        object.__setattr__(self, "datasets", datasets)
