"""Explicit local composition for Platform API clients."""

from __future__ import annotations

import logging
from collections.abc import Iterator, Mapping
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

from ea_research_lab.application.analysis import analyze_execution_core
from ea_research_lab.application.build import BuildRequest, execute_build
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.dataset import TransformationRequest, transform_dataset
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.execution import execute_run
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
from ea_research_lab.domain.provenance import EvidenceProvenance
from ea_research_lab.domain.values import Sha256Digest, UtcTimestamp
from ea_research_lab.infrastructure.metaeditor import (
    MetaEditorConfiguration,
    execute_metaeditor_build_attempt,
)
from ea_research_lab.infrastructure.mt5_semantic import (
    Mt5ExperimentContextProjector,
)
from ea_research_lab.infrastructure.mt5_report import (
    Mt5AccountBalanceEventSeriesTransformer,
    Mt5RealizedExecutionEventSeriesTransformer,
    Mt5ReportTransformer,
)
from ea_research_lab.infrastructure.mt5_strategy_tester import (
    Mt5StrategyTesterConfiguration,
    Mt5StrategyTesterProvider,
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


@dataclass(frozen=True, slots=True)
class CommandPlatformConfiguration:
    """Existing provider inputs required by command-capable composition."""

    build_workspace_parent: Path
    artifact_logical_name: str
    artifact_version: str
    metaeditor: MetaEditorConfiguration
    mt5: Mt5StrategyTesterConfiguration

    def __post_init__(self) -> None:
        if (
            not isinstance(self.build_workspace_parent, Path)
            or not self.build_workspace_parent.is_absolute()
            or not isinstance(self.artifact_logical_name, str)
            or not self.artifact_logical_name
            or self.artifact_logical_name.strip() != self.artifact_logical_name
            or not isinstance(self.artifact_version, str)
            or not self.artifact_version
            or self.artifact_version.strip() != self.artifact_version
            or not isinstance(self.metaeditor, MetaEditorConfiguration)
            or not isinstance(self.mt5, Mt5StrategyTesterConfiguration)
        ):
            raise ValueError("Command Platform configuration is invalid.")


def create_command_platform_configuration(
    *,
    build_workspace_parent: Path,
    artifact_logical_name: str,
    artifact_version: str,
    metaeditor_executable: Path,
    metaeditor_digest: str,
    terminal_executable: Path,
    terminal_digest: str,
    mt5_data_root: Path,
    environment: Mapping[str, str],
    external_roots: Mapping[str, Path],
) -> CommandPlatformConfiguration:
    """Translate explicit local settings into existing provider configuration."""

    return CommandPlatformConfiguration(
        build_workspace_parent,
        artifact_logical_name,
        artifact_version,
        MetaEditorConfiguration(
            metaeditor_executable,
            Sha256Digest(metaeditor_digest),
            environment,
            external_roots=external_roots,
        ),
        Mt5StrategyTesterConfiguration(
            terminal_executable,
            Sha256Digest(terminal_digest),
            mt5_data_root,
            environment,
            "main",
            "demo",
        ),
    )


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


@contextmanager
def compose_command_platform(
    database_path: Path,
    configuration: CommandPlatformConfiguration,
    logger: logging.Logger,
) -> Iterator[PlatformApi]:
    """Own the existing operational adapters behind one Platform API."""

    if not isinstance(configuration, CommandPlatformConfiguration):
        raise TypeError("Command Platform composition requires configuration.")

    def build_workflow(request: BuildRequest):
        return execute_build(
            request,
            lambda active: execute_metaeditor_build_attempt(
                active,
                configuration=configuration.metaeditor,
                workspace_parent=configuration.build_workspace_parent,
                logical_name=configuration.artifact_logical_name,
                artifact_version=configuration.artifact_version,
                built_at=UtcTimestamp(datetime.now(UTC)),
                logger=logger,
            ),
        )

    def run_workflow(request, reproducibility):
        return execute_run(
            Mt5StrategyTesterProvider(configuration.mt5), request, reproducibility
        )

    def transformation_workflow(context, evidence, definitions):
        transformers = (
            Mt5ReportTransformer(),
            Mt5RealizedExecutionEventSeriesTransformer(),
            Mt5AccountBalanceEventSeriesTransformer(),
        )
        return tuple(
            transform_dataset(
                transformer,
                TransformationRequest(
                    context,
                    EvidenceProvenance(evidence.manifest, evidence.reference),
                    evidence.raw_evidence,
                    definition.transformation_id,
                    definition.version,
                    definition.parameters,
                ),
            )
            for transformer, definition in zip(
                transformers, definitions, strict=True
            )
        )

    with (
        SqliteDataPlane(database_path) as data_plane,
        SqliteResearchQuery(database_path) as research_query,
    ):
        yield PlatformApi(
            PlatformCommands(
                data_plane,
                build_workflow,
                run_workflow,
                transformation_workflow,
                analyze_execution_core,
                logger,
            ),
            PlatformQueries(
                data_plane,
                research_query,
                Mt5ExperimentContextProjector(),
                MetaEditorBuildRuntimeProjector(),
            ),
            logger,
        )
