"""Transport-neutral Platform Command boundary over existing workflows."""

from __future__ import annotations

import logging
from collections.abc import Callable
from dataclasses import dataclass, replace
from datetime import timedelta

from ea_research_lab.application.analysis import AnalysisOutcome, AnalysisRequest
from ea_research_lab.application.build import BuildRequest, BuildWorkflowResult
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.data_plane import (
    DataPlane,
    DataPlaneError,
    DurableBuild,
    DurableEvidence,
    DurableRun,
)
from ea_research_lab.application.dataset import (
    DatasetTransformationOutcome,
)
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.execution import ExecutionRequest, RunExecutionResult
from ea_research_lab.domain.build import BuildOutcome
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
    RequestId,
    RunId,
    TransformationId,
)
from ea_research_lab.domain.provenance import (
    SchemaReferencedPayload,
)
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)


_DATASET_SCHEMAS = (
    SchemaRef(SchemaName("execution-summary"), SchemaVersion(0, 1, 0)),
    SchemaRef(
        SchemaName("realized-execution-event-series"), SchemaVersion(0, 1, 0)
    ),
    SchemaRef(
        SchemaName("account-balance-event-series"), SchemaVersion(0, 1, 0)
    ),
)

BuildWorkflow = Callable[[BuildRequest], BuildWorkflowResult]
RunWorkflow = Callable[
    [ExecutionRequest, ReproducibilityAssessment], RunExecutionResult
]
AnalysisWorkflow = Callable[[AnalysisRequest], AnalysisOutcome]
TransformationWorkflow = Callable[
    [
        RequestContext,
        DurableEvidence,
        tuple[
            "TransformationDefinition",
            "TransformationDefinition",
            "TransformationDefinition",
        ],
    ],
    tuple[DatasetTransformationOutcome, ...],
]


@dataclass(frozen=True, slots=True)
class ExecuteRunCommandRequest:
    context: RequestContext
    run_id: RunId
    build_record_id: BuildRecordId
    artifact_id: ArtifactId
    test_definition: SchemaReferencedPayload
    environment_configuration_id: EnvironmentConfigurationId
    environment_configuration: SchemaReferencedPayload
    timeout: timedelta
    execution_reproducibility: ReproducibilityAssessment

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext),
            (self.run_id, RunId),
            (self.build_record_id, BuildRecordId),
            (self.artifact_id, ArtifactId),
            (self.test_definition, SchemaReferencedPayload),
            (self.environment_configuration_id, EnvironmentConfigurationId),
            (self.environment_configuration, SchemaReferencedPayload),
            (self.execution_reproducibility, ReproducibilityAssessment),
        )
        if any(not isinstance(value, kind) for value, kind in required) or (
            not isinstance(self.timeout, timedelta) or self.timeout <= timedelta(0)
        ):
            raise InvalidValueError("Run command request is invalid.")


@dataclass(frozen=True, slots=True)
class TransformationDefinition:
    transformation_id: TransformationId
    version: DefinitionVersion
    parameters: SchemaReferencedPayload | None = None

    def __post_init__(self) -> None:
        if (
            not isinstance(self.transformation_id, TransformationId)
            or not isinstance(self.version, DefinitionVersion)
            or (
                self.parameters is not None
                and not isinstance(self.parameters, SchemaReferencedPayload)
            )
        ):
            raise InvalidValueError("Transformation definition is invalid.")


@dataclass(frozen=True, slots=True)
class TransformEvidenceCommandRequest:
    context: RequestContext
    run_id: RunId
    evidence_manifest: RawEvidenceManifestRef
    transformations: tuple[
        TransformationDefinition,
        TransformationDefinition,
        TransformationDefinition,
    ]

    def __post_init__(self) -> None:
        if (
            not isinstance(self.context, RequestContext)
            or not isinstance(self.run_id, RunId)
            or not isinstance(self.evidence_manifest, RawEvidenceManifestRef)
        ):
            raise InvalidValueError("Evidence transformation command is invalid.")
        try:
            transformations = tuple(self.transformations)
        except TypeError as error:
            raise InvalidValueError(
                "Evidence transformation command requires three definitions."
            ) from error
        if len(transformations) != 3 or any(
            not isinstance(item, TransformationDefinition)
            for item in transformations
        ):
            raise InvalidValueError(
                "Evidence transformation command requires three definitions."
            )
        if self.evidence_manifest.run_id != self.run_id:
            raise InvalidValueError("Evidence reference belongs to another Run.")
        object.__setattr__(self, "transformations", transformations)


@dataclass(frozen=True, slots=True)
class DatasetInputReference:
    dataset_id: DatasetId
    content_digest: Sha256Digest

    def __post_init__(self) -> None:
        if not isinstance(self.dataset_id, DatasetId) or not isinstance(
            self.content_digest, Sha256Digest
        ):
            raise InvalidValueError("Dataset input reference is invalid.")


@dataclass(frozen=True, slots=True)
class AnalyzeDatasetsCommandRequest:
    context: RequestContext
    datasets: tuple[DatasetInputReference, ...]
    analysis_definition_id: AnalysisDefinitionId
    analysis_version: DefinitionVersion
    analysis_parameters: SchemaReferencedPayload
    computation_environment_id: EnvironmentConfigurationId

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext),
            (self.analysis_definition_id, AnalysisDefinitionId),
            (self.analysis_version, DefinitionVersion),
            (self.analysis_parameters, SchemaReferencedPayload),
            (self.computation_environment_id, EnvironmentConfigurationId),
        )
        if any(not isinstance(value, kind) for value, kind in required):
            raise InvalidValueError("Analysis command request is invalid.")
        try:
            datasets = tuple(self.datasets)
        except TypeError as error:
            raise InvalidValueError("Analysis command inputs are invalid.") from error
        if not datasets or any(
            not isinstance(item, DatasetInputReference) for item in datasets
        ):
            raise InvalidValueError("Analysis command inputs are invalid.")
        object.__setattr__(self, "datasets", datasets)


@dataclass(frozen=True, slots=True)
class BuildCommandResult:
    request_id: RequestId
    build_record_id: BuildRecordId
    outcome: BuildOutcome | None
    artifact_id: ArtifactId | None
    published: bool
    failure: ApplicationError | None = None


@dataclass(frozen=True, slots=True)
class RunCommandResult:
    request_id: RequestId
    run_id: RunId
    status: str | None
    evidence_outcome: EvidenceCollectionOutcome | None
    evidence_manifest: RawEvidenceManifestRef | None
    published: bool
    failure: ApplicationError | None = None


@dataclass(frozen=True, slots=True)
class DatasetCommandReference:
    dataset_id: DatasetId
    content_digest: Sha256Digest
    content_schema: SchemaRef
    published: bool


@dataclass(frozen=True, slots=True)
class TransformEvidenceCommandResult:
    request_id: RequestId
    run_id: RunId
    datasets: tuple[DatasetCommandReference, ...]
    failure: ApplicationError | None = None


@dataclass(frozen=True, slots=True)
class AnalysisCommandResult:
    request_id: RequestId
    analysis_result_id: AnalysisResultId | None
    result_digest: Sha256Digest | None
    result_schema: SchemaRef | None
    published: bool
    failure: ApplicationError | None = None


class PlatformCommands:
    """Four explicit Commands; durable publication is part of success."""

    def __init__(
        self,
        data_plane: DataPlane,
        build_workflow: BuildWorkflow,
        run_workflow: RunWorkflow,
        transformation_workflow: TransformationWorkflow,
        analysis_workflow: AnalysisWorkflow,
        logger: logging.Logger,
    ) -> None:
        if not all(
            (
                callable(build_workflow),
                callable(run_workflow),
                callable(transformation_workflow),
                callable(analysis_workflow),
                isinstance(logger, logging.Logger),
            )
        ):
            raise TypeError("Platform Command dependencies are invalid.")
        self._data_plane = data_plane
        self._build_workflow = build_workflow
        self._run_workflow = run_workflow
        self._transformation_workflow = transformation_workflow
        self._analysis_workflow = analysis_workflow
        self._logger = logger

    def build_artifact(self, request: BuildRequest) -> BuildCommandResult:
        """Run the existing Build workflow and publish its finalized facts."""

        if not isinstance(request, BuildRequest):
            raise TypeError("Build command requires a BuildRequest.")
        context = request.context
        self._audit("build_artifact", "started", context, request.build_record_id)
        durable = None
        try:
            workflow = self._build_workflow(request)
            if not isinstance(workflow, BuildWorkflowResult):
                raise TypeError("Build workflow returned an invalid result.")
            durable = DurableBuild.from_workflow_result(workflow)
            if durable.build_record_id != request.build_record_id:
                raise InvalidValueError("Build workflow returned another Build.")
            self._data_plane.publish_build(durable)
        except Exception as error:
            failure = self._safe_failure(
                error,
                context,
                ApplicationErrorCode.BUILD_PROVIDER_FAILED,
                "Build command failed.",
            )
            self._audit(
                "build_artifact", "failed", context, request.build_record_id, failure
            )
            return BuildCommandResult(
                context.request_id,
                request.build_record_id,
                None if durable is None else durable.outcome,
                (
                    None
                    if durable is None or durable.artifact_acceptance is None
                    else durable.artifact_acceptance.artifact.artifact_id
                ),
                False,
                failure,
            )
        artifact_id = (
            None
            if durable.artifact_acceptance is None
            else durable.artifact_acceptance.artifact.artifact_id
        )
        self._audit(
            "build_artifact", "completed", context, request.build_record_id
        )
        return BuildCommandResult(
            context.request_id,
            durable.build_record_id,
            durable.outcome,
            artifact_id,
            True,
        )

    def execute_run(self, request: ExecuteRunCommandRequest) -> RunCommandResult:
        """Run the existing execution workflow and publish its finalized facts."""

        if not isinstance(request, ExecuteRunCommandRequest):
            raise TypeError("Run command requires an ExecuteRunCommandRequest.")
        context = request.context
        self._audit("execute_run", "started", context, request.run_id)
        workflow = None
        try:
            build = self._data_plane.load_build(request.build_record_id)
            acceptance = build.artifact_acceptance
            if (
                acceptance is None
                or acceptance.artifact.artifact_id != request.artifact_id
            ):
                raise InvalidValueError("Run command Artifact is not accepted.")
            execution_request = ExecutionRequest(
                context,
                request.run_id,
                acceptance.artifact,
                request.test_definition,
                request.environment_configuration_id,
                request.environment_configuration,
                request.timeout,
            )
            workflow = self._run_workflow(
                execution_request, request.execution_reproducibility
            )
            if not isinstance(workflow, RunExecutionResult):
                raise TypeError("Run workflow returned an invalid result.")
            durable = DurableRun.from_execution_result(
                request.test_definition, workflow
            )
            if durable.run_id != request.run_id:
                raise InvalidValueError("Run workflow returned another Run.")
            self._data_plane.publish_run(durable)
        except Exception as error:
            failure = self._safe_failure(
                error,
                context,
                ApplicationErrorCode.EXECUTION_PROVIDER_FAILED,
                "Run command failed.",
            )
            self._audit("execute_run", "failed", context, request.run_id, failure)
            return RunCommandResult(
                context.request_id,
                request.run_id,
                (
                    None
                    if workflow is None
                    else str(workflow.run_manifest.value["status"])
                ),
                None if workflow is None else workflow.evidence_manifest.outcome,
                None if workflow is None else workflow.evidence_manifest_ref,
                False,
                failure,
            )
        self._audit("execute_run", "completed", context, request.run_id)
        return RunCommandResult(
            context.request_id,
            durable.run_id,
            str(workflow.run_manifest.value["status"]),
            workflow.evidence_manifest.outcome,
            workflow.evidence_manifest_ref,
            True,
        )

    def transform_evidence(
        self, request: TransformEvidenceCommandRequest
    ) -> TransformEvidenceCommandResult:
        """Produce and publish the three currently supported Dataset products."""

        if not isinstance(request, TransformEvidenceCommandRequest):
            raise TypeError(
                "Transformation command requires a TransformEvidenceCommandRequest."
            )
        context = request.context
        self._audit("transform_evidence", "started", context, request.run_id)
        references: list[DatasetCommandReference] = []
        failure = None
        try:
            run = self._data_plane.load_run(request.run_id)
            evidence = self._exact_evidence(run, request.evidence_manifest)
            outcomes = tuple(
                self._transformation_workflow(
                    context, evidence, request.transformations
                )
            )
            products = {}
            for outcome in outcomes:
                if not isinstance(outcome, DatasetTransformationOutcome):
                    raise TypeError("Dataset workflow returned an invalid outcome.")
                if outcome.failure is not None:
                    failure = failure or outcome.failure
                    continue
                dataset = outcome.dataset
                schema = dataset.content.payload.schema_ref
                if schema not in _DATASET_SCHEMAS or schema in products:
                    raise InvalidValueError(
                        "Dataset workflow returned an unsupported product set."
                    )
                products[schema] = dataset
            for schema in _DATASET_SCHEMAS:
                dataset = products.get(schema)
                if dataset is None:
                    continue
                references.append(
                    DatasetCommandReference(
                        dataset.provenance.dataset_id,
                        dataset.content.content_digest,
                        schema,
                        False,
                    )
                )
            for index, reference in enumerate(references):
                dataset = products[reference.content_schema]
                self._data_plane.publish_dataset(dataset)
                references[index] = replace(references[index], published=True)
            if len(products) != 3 and failure is None:
                raise InvalidValueError(
                    "Dataset workflow did not produce its three products."
                )
        except Exception as error:
            failure = self._safe_failure(
                error,
                context,
                ApplicationErrorCode.DATASET_TRANSFORMATION_FAILED,
                "Dataset transformation command failed.",
            )
        result = TransformEvidenceCommandResult(
            context.request_id, request.run_id, tuple(references), failure
        )
        self._audit(
            "transform_evidence",
            "completed" if failure is None else "failed",
            context,
            request.run_id,
            failure,
        )
        return result

    def analyze_datasets(
        self, request: AnalyzeDatasetsCommandRequest
    ) -> AnalysisCommandResult:
        """Run the current Analysis Core operation and publish its result."""

        if not isinstance(request, AnalyzeDatasetsCommandRequest):
            raise TypeError("Analysis command requires an AnalyzeDatasetsCommandRequest.")
        context = request.context
        self._audit("analyze_datasets", "started", context)
        result = None
        try:
            datasets = tuple(
                self._data_plane.load_dataset(reference.dataset_id)
                for reference in request.datasets
            )
            if any(
                dataset.content.content_digest != reference.content_digest
                for dataset, reference in zip(
                    datasets, request.datasets, strict=True
                )
            ):
                raise InvalidValueError("Analysis Dataset digest does not match.")
            outcome = self._analysis_workflow(
                AnalysisRequest(
                    context,
                    datasets,
                    request.analysis_definition_id,
                    request.analysis_version,
                    request.analysis_parameters,
                    request.computation_environment_id,
                )
            )
            if not isinstance(outcome, AnalysisOutcome):
                raise TypeError("Analysis workflow returned an invalid outcome.")
            if outcome.failure is not None:
                failure = outcome.failure
                self._audit("analyze_datasets", "failed", context, error=failure)
                return AnalysisCommandResult(
                    context.request_id, None, None, None, False, failure
                )
            result = outcome.result
            self._data_plane.publish_analysis(result)
        except Exception as error:
            failure = self._safe_failure(
                error,
                context,
                ApplicationErrorCode.ANALYSIS_FAILED,
                "Analysis command failed.",
            )
            self._audit("analyze_datasets", "failed", context, error=failure)
            return AnalysisCommandResult(
                context.request_id,
                None if result is None else result.provenance.analysis_result_id,
                None if result is None else result.content.content_digest,
                None if result is None else result.content.payload.schema_ref,
                False,
                failure,
            )
        result_id = result.provenance.analysis_result_id
        self._audit("analyze_datasets", "completed", context, result_id)
        return AnalysisCommandResult(
            context.request_id,
            result_id,
            result.content.content_digest,
            result.content.payload.schema_ref,
            True,
        )

    @staticmethod
    def _exact_evidence(
        run: DurableRun, reference: RawEvidenceManifestRef
    ) -> DurableEvidence:
        if reference.run_id != run.run_id:
            raise InvalidValueError("Evidence reference belongs to another Run.")
        evidence = next(
            (item for item in run.evidence_history if item.reference == reference),
            None,
        )
        if evidence is None:
            raise InvalidValueError("Evidence revision was not found.")
        return evidence

    @staticmethod
    def _safe_failure(
        error: Exception,
        context: RequestContext,
        default_code: ApplicationErrorCode,
        message: str,
    ) -> ApplicationError:
        if isinstance(error, DataPlaneError):
            return ApplicationError(
                error.code, str(error), request_id=context.request_id, cause=error
            )
        if isinstance(error, InvalidValueError):
            return ApplicationError(
                ApplicationErrorCode.INVALID_PROVENANCE,
                "Command input provenance is invalid.",
                request_id=context.request_id,
                cause=error,
            )
        return ApplicationError(
            default_code, message, request_id=context.request_id, cause=error
        )

    def _audit(
        self,
        capability: str,
        outcome: str,
        context: RequestContext,
        target: BuildRecordId | RunId | AnalysisResultId | None = None,
        error: ApplicationError | None = None,
    ) -> None:
        extra = {
            "event_name": f"platform.command.{capability}.{outcome}",
            "request_id": str(context.request_id),
        }
        if context.caller_id is not None:
            extra["caller_id"] = context.caller_id
        if isinstance(target, BuildRecordId):
            extra["build_record_id"] = str(target)
        elif isinstance(target, RunId):
            extra["run_id"] = str(target)
        elif isinstance(target, AnalysisResultId):
            extra["analysis_result_id"] = str(target)
        if error is not None:
            extra["error_code"] = error.code.value
        level = logging.ERROR if error is not None else logging.INFO
        self._logger.log(level, f"Platform command {outcome}.", extra=extra)
