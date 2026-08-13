"""Single transport-neutral application facade for Commands and Queries."""

from __future__ import annotations

import logging
from collections.abc import Callable
from typing import TypeVar

from ea_research_lab.application.build import BuildRequest
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.data_plane import DataPlaneError
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.platform_commands import (
    AnalysisCommandResult,
    AnalyzeDatasetsCommandRequest,
    BuildCommandResult,
    ExecuteRunCommandRequest,
    PlatformCommands,
    RunCommandResult,
    TransformEvidenceCommandRequest,
    TransformEvidenceCommandResult,
)
from ea_research_lab.application.platform_queries import PlatformQueries
from ea_research_lab.application.research_query import Page, PageRequest
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    BuildRecordId,
    DatasetId,
    RawEvidenceManifestId,
    RunId,
)
from ea_research_lab.domain.semantic import (
    AnalysisDetail,
    AnalysisSummary,
    CanonicalChainProjection,
    DatasetDetail,
    DatasetSummary,
    EvidenceObjectSummary,
    ResearchRunDetail,
    ResearchRunSummary,
)


QueryResultT = TypeVar("QueryResultT")


class PlatformApi:
    """Twelve direct capabilities with no transport or provider selection."""

    def __init__(
        self,
        commands: PlatformCommands,
        queries: PlatformQueries,
        logger: logging.Logger,
    ) -> None:
        if (
            not isinstance(commands, PlatformCommands)
            or not isinstance(queries, PlatformQueries)
            or not isinstance(logger, logging.Logger)
        ):
            raise TypeError("Platform API dependencies are invalid.")
        self._commands = commands
        self._queries = queries
        self._logger = logger

    def build_artifact(self, request: BuildRequest) -> BuildCommandResult:
        return self._commands.build_artifact(request)

    def execute_run(self, request: ExecuteRunCommandRequest) -> RunCommandResult:
        return self._commands.execute_run(request)

    def transform_evidence(
        self, request: TransformEvidenceCommandRequest
    ) -> TransformEvidenceCommandResult:
        return self._commands.transform_evidence(request)

    def analyze_datasets(
        self, request: AnalyzeDatasetsCommandRequest
    ) -> AnalysisCommandResult:
        return self._commands.analyze_datasets(request)

    def list_research_runs(
        self, context: RequestContext, page: PageRequest = PageRequest()
    ) -> Page[ResearchRunSummary]:
        return self._query(
            "list_research_runs",
            context,
            lambda: self._queries.list_research_runs(context, page),
        )

    def get_research_run(
        self, context: RequestContext, run_id: RunId
    ) -> ResearchRunDetail:
        return self._query(
            "get_research_run",
            context,
            lambda: self._queries.get_research_run(context, run_id),
            run_id,
        )

    def list_run_evidence_objects(
        self,
        context: RequestContext,
        run_id: RunId,
        manifest_id: RawEvidenceManifestId,
        page: PageRequest = PageRequest(),
    ) -> Page[EvidenceObjectSummary]:
        return self._query(
            "list_run_evidence_objects",
            context,
            lambda: self._queries.list_run_evidence_objects(
                context, run_id, manifest_id, page
            ),
            run_id,
        )

    def list_run_datasets(
        self,
        context: RequestContext,
        run_id: RunId,
        page: PageRequest = PageRequest(),
    ) -> Page[DatasetSummary]:
        return self._query(
            "list_run_datasets",
            context,
            lambda: self._queries.list_run_datasets(context, run_id, page),
            run_id,
        )

    def get_dataset(
        self, context: RequestContext, dataset_id: DatasetId
    ) -> DatasetDetail:
        return self._query(
            "get_dataset",
            context,
            lambda: self._queries.get_dataset(context, dataset_id),
            dataset_id,
        )

    def list_dataset_analyses(
        self,
        context: RequestContext,
        dataset_id: DatasetId,
        page: PageRequest = PageRequest(),
    ) -> Page[AnalysisSummary]:
        return self._query(
            "list_dataset_analyses",
            context,
            lambda: self._queries.list_dataset_analyses(
                context, dataset_id, page
            ),
            dataset_id,
        )

    def get_analysis(
        self, context: RequestContext, analysis_result_id: AnalysisResultId
    ) -> AnalysisDetail:
        return self._query(
            "get_analysis",
            context,
            lambda: self._queries.get_analysis(context, analysis_result_id),
            analysis_result_id,
        )

    def get_canonical_chain(
        self,
        context: RequestContext,
        build_record_id: BuildRecordId,
        run_id: RunId,
        analysis_result_id: AnalysisResultId,
    ) -> CanonicalChainProjection:
        return self._query(
            "get_canonical_chain",
            context,
            lambda: self._queries.get_canonical_chain(
                context, build_record_id, run_id, analysis_result_id
            ),
            run_id,
        )

    def _query(
        self,
        capability: str,
        context: RequestContext,
        operation: Callable[[], QueryResultT],
        target: BuildRecordId | RunId | DatasetId | AnalysisResultId | None = None,
    ) -> QueryResultT:
        if not isinstance(context, RequestContext):
            raise TypeError("Platform Query requires RequestContext.")
        self._audit(capability, "started", context, target)
        try:
            result = operation()
        except DataPlaneError as error:
            failure = ApplicationError(
                error.code, str(error), request_id=context.request_id
            )
            self._audit(capability, "failed", context, target, failure)
            raise error from None
        except (InvalidValueError, TypeError) as error:
            failure = ApplicationError(
                ApplicationErrorCode.INVALID_VALUE,
                "Platform query request is invalid.",
                request_id=context.request_id,
            )
            self._audit(capability, "failed", context, target, failure)
            raise InvalidValueError(failure.message) from None
        except Exception:
            failure = ApplicationError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Platform query failed.",
                request_id=context.request_id,
            )
            self._audit(capability, "failed", context, target, failure)
            raise DataPlaneError(failure.code, failure.message) from None
        self._audit(capability, "completed", context, target)
        return result

    def _audit(
        self,
        capability: str,
        outcome: str,
        context: RequestContext,
        target: BuildRecordId | RunId | DatasetId | AnalysisResultId | None,
        error: ApplicationError | None = None,
    ) -> None:
        extra = {
            "event_name": f"platform.query.{capability}.{outcome}",
            "request_id": str(context.request_id),
        }
        if context.caller_id is not None:
            extra["caller_id"] = context.caller_id
        for name, kind in (
            ("build_record_id", BuildRecordId),
            ("run_id", RunId),
            ("dataset_id", DatasetId),
            ("analysis_result_id", AnalysisResultId),
        ):
            if isinstance(target, kind):
                extra[name] = str(target)
                break
        if error is not None:
            extra["error_code"] = error.code.value
        self._logger.log(
            logging.ERROR if error is not None else logging.INFO,
            f"Platform query {outcome}.",
            extra=extra,
        )
