"""Explicit local composition for read-only Platform API clients."""

from __future__ import annotations

import logging
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

from ea_research_lab.application.build import BuildRequest
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.platform_api import PlatformApi
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
from ea_research_lab.infrastructure.mt5_semantic import (
    Mt5ExperimentContextProjector,
)
from ea_research_lab.infrastructure.metaeditor_semantic import (
    MetaEditorBuildRuntimeProjector,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from ea_research_lab.infrastructure.sqlite_research_query import SqliteResearchQuery


class _ReadOnlyCommands(PlatformCommands):
    def __init__(self, logger: logging.Logger) -> None:
        self._logger = logger

    def build_artifact(self, request: BuildRequest) -> BuildCommandResult:
        if not isinstance(request, BuildRequest):
            raise TypeError("Build command requires a BuildRequest.")
        return BuildCommandResult(
            request.context.request_id,
            request.build_record_id,
            None,
            None,
            False,
            self._unavailable("build_artifact", request.context),
        )

    def execute_run(self, request: ExecuteRunCommandRequest) -> RunCommandResult:
        if not isinstance(request, ExecuteRunCommandRequest):
            raise TypeError("Run command requires an ExecuteRunCommandRequest.")
        return RunCommandResult(
            request.context.request_id,
            request.run_id,
            None,
            None,
            None,
            False,
            self._unavailable("execute_run", request.context),
        )

    def transform_evidence(
        self, request: TransformEvidenceCommandRequest
    ) -> TransformEvidenceCommandResult:
        if not isinstance(request, TransformEvidenceCommandRequest):
            raise TypeError(
                "Transformation command requires a TransformEvidenceCommandRequest."
            )
        return TransformEvidenceCommandResult(
            request.context.request_id,
            request.run_id,
            (),
            self._unavailable("transform_evidence", request.context),
        )

    def analyze_datasets(
        self, request: AnalyzeDatasetsCommandRequest
    ) -> AnalysisCommandResult:
        if not isinstance(request, AnalyzeDatasetsCommandRequest):
            raise TypeError("Analysis command requires an AnalyzeDatasetsCommandRequest.")
        return AnalysisCommandResult(
            request.context.request_id,
            None,
            None,
            None,
            False,
            self._unavailable("analyze_datasets", request.context),
        )

    def _unavailable(
        self, capability: str, context: RequestContext
    ) -> ApplicationError:
        error = ApplicationError(
            ApplicationErrorCode.INVALID_CONFIGURATION,
            "Platform Commands are unavailable in read-only composition.",
            request_id=context.request_id,
        )
        extra = {
            "event_name": f"platform.command.{capability}.failed",
            "request_id": str(context.request_id),
            "error_code": error.code.value,
        }
        if context.caller_id is not None:
            extra["caller_id"] = context.caller_id
        self._logger.error("Platform command failed.", extra=extra)
        return error


@contextmanager
def compose_read_only_platform(
    database_path: Path, logger: logging.Logger
) -> Iterator[PlatformApi]:
    """Own read-only adapter lifetimes and expose only the Platform API."""

    with (
        SqliteDataPlane(database_path, read_only=True) as data_plane,
        SqliteResearchQuery(database_path) as research_query,
    ):
        yield PlatformApi(
            _ReadOnlyCommands(logger),
            PlatformQueries(
                data_plane,
                research_query,
                Mt5ExperimentContextProjector(),
                MetaEditorBuildRuntimeProjector(),
            ),
            logger,
        )
