"""Local tools-only MCP adapter over the transport-neutral Platform API."""

from __future__ import annotations

import json
import logging
from base64 import b64decode
from binascii import Error as Base64Error
from dataclasses import dataclass
from datetime import timedelta
from enum import StrEnum
from typing import Annotated, Any, Literal, NoReturn, TypeVar

from mcp.server import MCPServer
from mcp.server.mcpserver.exceptions import ToolError
from mcp.types import ToolAnnotations

from apps.mcp_adapter.serialization import (
    serialize_analysis_command_result,
    serialize_analysis_detail,
    serialize_analysis_page,
    serialize_build_command_result,
    serialize_canonical_chain,
    serialize_dataset_detail,
    serialize_dataset_page,
    serialize_evidence_object_page,
    serialize_error,
    serialize_research_run_detail,
    serialize_research_run_page,
    serialize_run_command_result,
    serialize_transform_command_result,
)
from ea_research_lab.application.build import (
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError, ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.platform_api import PlatformApi
from ea_research_lab.application.platform_commands import (
    AnalyzeDatasetsCommandRequest,
    DatasetInputReference,
    ExecuteRunCommandRequest,
    TransformEvidenceCommandRequest,
    TransformationDefinition,
)
from ea_research_lab.application.research_query import PageRequest
from ea_research_lab.domain.build import BuildInputScope
from ea_research_lab.domain.errors import DomainError, InvalidValueError
from ea_research_lab.domain.evidence import RawEvidenceManifestRef
from ea_research_lab.domain.identifiers import (
    AnalysisDefinitionId,
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EntityId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RequestId,
    RunId,
    TransformationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    DefinitionVersion,
    ReproducibilityAssessment,
    ReproducibilityLevel,
    ReproducibilityReason,
    SchemaRef,
    Sha256Digest,
    SourceRevision,
)


MCP_CALLER_ID = "mcp:local"
EntityIdT = TypeVar("EntityIdT", bound=EntityId)
_READ_ONLY = ToolAnnotations(
    readOnlyHint=True,
    destructiveHint=False,
    idempotentHint=True,
    openWorldHint=False,
)


class _PageBounds:
    def __get_pydantic_json_schema__(
        self, core_schema: object, handler: Any
    ) -> dict[str, object]:
        schema = handler(core_schema)
        schema.update(minimum=1, maximum=200)
        return schema


PageSize = Annotated[int, _PageBounds()]


class _TypedIdSchema:
    def __init__(self, prefix: str) -> None:
        self._prefix = prefix

    def __get_pydantic_json_schema__(
        self, core_schema: object, handler: Any
    ) -> dict[str, object]:
        schema = handler(core_schema)
        schema["pattern"] = (
            rf"^{self._prefix}_[0-9a-f]{{8}}-[0-9a-f]{{4}}-7[0-9a-f]{{3}}-"
            r"[89ab][0-9a-f]{3}-[0-9a-f]{12}$"
        )
        return schema


RunIdText = Annotated[str, _TypedIdSchema("run")]
ManifestIdText = Annotated[str, _TypedIdSchema("rawmanifest")]
DatasetIdText = Annotated[str, _TypedIdSchema("dataset")]
AnalysisResultIdText = Annotated[str, _TypedIdSchema("analysisresult")]
BuildRecordIdText = Annotated[str, _TypedIdSchema("build")]
ArtifactIdText = Annotated[str, _TypedIdSchema("artifact")]
EnvironmentConfigurationIdText = Annotated[str, _TypedIdSchema("envcfg")]
TransformationIdText = Annotated[str, _TypedIdSchema("transformation")]
AnalysisDefinitionIdText = Annotated[str, _TypedIdSchema("analysisdef")]


class _PositiveSeconds:
    def __get_pydantic_json_schema__(
        self, core_schema: object, handler: Any
    ) -> dict[str, object]:
        schema = handler(core_schema)
        schema.update(exclusiveMinimum=0)
        return schema


PositiveSeconds = Annotated[float, _PositiveSeconds()]


@dataclass(frozen=True, slots=True)
class BuildSourceTransport:
    scope: Literal["workspace", "external"]
    path: str
    content_base64: str
    root: str | None = None


@dataclass(frozen=True, slots=True)
class SchemaPayloadTransport:
    schema_ref: str
    value_json: str


@dataclass(frozen=True, slots=True)
class ReproducibilityReasonTransport:
    code: str
    detail: str


@dataclass(frozen=True, slots=True)
class TransformationTransport:
    transformation_id: TransformationIdText
    version: str
    parameters: SchemaPayloadTransport | None = None


@dataclass(frozen=True, slots=True)
class DatasetReferenceTransport:
    dataset_id: DatasetIdText
    content_digest: str


class ServerMode(StrEnum):
    READ_ONLY = "read-only"
    COMMAND_CAPABLE = "command-capable"


def create_server(
    platform_api: PlatformApi,
    *,
    mode: ServerMode = ServerMode.READ_ONLY,
    logger: logging.Logger,
) -> MCPServer:
    """Register bounded Platform API tools for the explicitly selected mode."""

    if not isinstance(mode, ServerMode) or not isinstance(logger, logging.Logger):
        raise TypeError("MCP server configuration is invalid.")

    server = MCPServer(
        "EA Research Lab",
        instructions=(
            "Tools expose bounded EA Research Lab Platform API capabilities. "
            "Cursors are opaque and each list call returns one page."
        ),
    )

    @server.tool(
        name="list_research_runs",
        description="List one bounded page of provider-neutral research Run summaries.",
        annotations=_READ_ONLY,
    )
    async def list_research_runs(
        page_size: PageSize = 50, cursor: str | None = None
    ) -> dict[str, object]:
        """Return exactly one Platform API page without following its cursor."""

        context = _new_context()
        page = _page_request(page_size, cursor, context)

        try:
            return serialize_research_run_page(
                platform_api.list_research_runs(context, page)
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "list_research_runs")

    @server.tool(
        name="get_research_run",
        description="Get one bounded provider-neutral research Run detail.",
        annotations=_READ_ONLY,
    )
    async def get_research_run(run_id: RunIdText) -> dict[str, object]:
        context = _new_context()
        typed_run_id = _identifier(RunId, run_id, context)
        try:
            return serialize_research_run_detail(
                platform_api.get_research_run(context, typed_run_id)
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "get_research_run")

    @server.tool(
        name="list_run_evidence_objects",
        description="List one bounded page of Raw Evidence metadata; never content.",
        annotations=_READ_ONLY,
    )
    async def list_run_evidence_objects(
        run_id: RunIdText,
        manifest_id: ManifestIdText,
        page_size: PageSize = 50,
        cursor: str | None = None,
    ) -> dict[str, object]:
        context = _new_context()
        typed_run_id = _identifier(RunId, run_id, context)
        typed_manifest_id = _identifier(
            RawEvidenceManifestId, manifest_id, context
        )
        page = _page_request(page_size, cursor, context)
        try:
            return serialize_evidence_object_page(
                platform_api.list_run_evidence_objects(
                    context, typed_run_id, typed_manifest_id, page
                )
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "list_run_evidence_objects")

    @server.tool(
        name="list_run_datasets",
        description="List one bounded page of Dataset summaries for one Run.",
        annotations=_READ_ONLY,
    )
    async def list_run_datasets(
        run_id: RunIdText, page_size: PageSize = 50, cursor: str | None = None
    ) -> dict[str, object]:
        context = _new_context()
        typed_run_id = _identifier(RunId, run_id, context)
        page = _page_request(page_size, cursor, context)
        try:
            return serialize_dataset_page(
                platform_api.list_run_datasets(context, typed_run_id, page)
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "list_run_datasets")

    @server.tool(
        name="get_dataset",
        description="Get bounded Dataset metadata and supported semantic projection.",
        annotations=_READ_ONLY,
    )
    async def get_dataset(dataset_id: DatasetIdText) -> dict[str, object]:
        context = _new_context()
        typed_dataset_id = _identifier(DatasetId, dataset_id, context)
        try:
            return serialize_dataset_detail(
                platform_api.get_dataset(context, typed_dataset_id)
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "get_dataset")

    @server.tool(
        name="list_dataset_analyses",
        description="List one bounded page of Analysis summaries for one Dataset.",
        annotations=_READ_ONLY,
    )
    async def list_dataset_analyses(
        dataset_id: DatasetIdText,
        page_size: PageSize = 50,
        cursor: str | None = None,
    ) -> dict[str, object]:
        context = _new_context()
        typed_dataset_id = _identifier(DatasetId, dataset_id, context)
        page = _page_request(page_size, cursor, context)
        try:
            return serialize_analysis_page(
                platform_api.list_dataset_analyses(
                    context, typed_dataset_id, page
                )
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "list_dataset_analyses")

    @server.tool(
        name="get_analysis",
        description="Get bounded Analysis metadata and allow-listed result content.",
        annotations=_READ_ONLY,
    )
    async def get_analysis(
        analysis_result_id: AnalysisResultIdText,
    ) -> dict[str, object]:
        context = _new_context()
        typed_analysis_id = _identifier(
            AnalysisResultId, analysis_result_id, context
        )
        try:
            return serialize_analysis_detail(
                platform_api.get_analysis(context, typed_analysis_id)
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "get_analysis")

    @server.tool(
        name="get_canonical_chain",
        description="Get the existing integrity-verified canonical provenance chain.",
        annotations=_READ_ONLY,
    )
    async def get_canonical_chain(
        build_record_id: BuildRecordIdText,
        run_id: RunIdText,
        analysis_result_id: AnalysisResultIdText,
    ) -> dict[str, object]:
        context = _new_context()
        typed_build_id = _identifier(BuildRecordId, build_record_id, context)
        typed_run_id = _identifier(RunId, run_id, context)
        typed_analysis_id = _identifier(
            AnalysisResultId, analysis_result_id, context
        )
        try:
            return serialize_canonical_chain(
                platform_api.get_canonical_chain(
                    context, typed_build_id, typed_run_id, typed_analysis_id
                )
            )
        except Exception as error:
            _raise_query_error(error, context, logger, "get_canonical_chain")

    if mode is ServerMode.COMMAND_CAPABLE:
        _register_commands(server, platform_api, logger)

    return server


def _register_commands(
    server: MCPServer, platform_api: PlatformApi, logger: logging.Logger
) -> None:
    annotations = ToolAnnotations(
        readOnlyHint=False,
        destructiveHint=False,
        idempotentHint=False,
        openWorldHint=False,
    )

    @server.tool(
        name="build_artifact",
        description=(
            "Compile one explicit source set and publish durable Build state; "
            "may launch MetaEditor and create an Artifact."
        ),
        annotations=annotations,
    )
    async def build_artifact(
        build_record_id: BuildRecordIdText,
        vcs_kind: str,
        repository: str,
        source_revision: str,
        source_is_dirty: bool,
        primary_source: BuildSourceTransport,
        dependencies: list[BuildSourceTransport],
        build_configuration_id: EnvironmentConfigurationIdText,
        build_configuration: SchemaPayloadTransport,
        timeout_seconds: PositiveSeconds,
    ) -> dict[str, object]:
        context = _new_context()
        try:
            request = BuildRequest(
                context,
                _identifier(BuildRecordId, build_record_id, context),
                SourceRevision(
                    vcs_kind, repository, source_revision, source_is_dirty
                ),
                BuildSourceSpecification(
                    _build_source(primary_source),
                    tuple(_build_source(item) for item in dependencies),
                ),
                _identifier(
                    EnvironmentConfigurationId,
                    build_configuration_id,
                    context,
                ),
                _schema_payload(build_configuration),
                timedelta(seconds=timeout_seconds),
            )
            result = platform_api.build_artifact(request)
            _raise_result_failure(result.failure, context)
            return serialize_build_command_result(result)
        except Exception as error:
            _raise_command_error(error, context, logger, "build_artifact")

    @server.tool(
        name="execute_run",
        description=(
            "Execute one controlled research Run and publish durable Run/Evidence "
            "state; may launch MT5 Strategy Tester."
        ),
        annotations=annotations,
    )
    async def execute_run(
        run_id: RunIdText,
        build_record_id: BuildRecordIdText,
        artifact_id: ArtifactIdText,
        test_definition: SchemaPayloadTransport,
        environment_configuration_id: EnvironmentConfigurationIdText,
        environment_configuration: SchemaPayloadTransport,
        timeout_seconds: PositiveSeconds,
        reproducibility_level: Literal[
            "exact", "equivalent", "best_effort", "unavailable"
        ],
        reproducibility_reasons: list[ReproducibilityReasonTransport],
    ) -> dict[str, object]:
        context = _new_context()
        try:
            request = ExecuteRunCommandRequest(
                context,
                _identifier(RunId, run_id, context),
                _identifier(BuildRecordId, build_record_id, context),
                _identifier(ArtifactId, artifact_id, context),
                _schema_payload(test_definition),
                _identifier(
                    EnvironmentConfigurationId,
                    environment_configuration_id,
                    context,
                ),
                _schema_payload(environment_configuration),
                timedelta(seconds=timeout_seconds),
                ReproducibilityAssessment(
                    ReproducibilityLevel(reproducibility_level),
                    tuple(
                        ReproducibilityReason(item.code, item.detail)
                        for item in reproducibility_reasons
                    ),
                ),
            )
            result = platform_api.execute_run(request)
            _raise_result_failure(result.failure, context)
            return serialize_run_command_result(result)
        except Exception as error:
            _raise_command_error(error, context, logger, "execute_run")

    @server.tool(
        name="transform_evidence",
        description=(
            "Transform one sealed Evidence revision and publish the three "
            "supported deterministic Datasets."
        ),
        annotations=annotations,
    )
    async def transform_evidence(
        run_id: RunIdText,
        evidence_manifest_id: ManifestIdText,
        evidence_manifest_digest: str,
        transformations: list[TransformationTransport],
    ) -> dict[str, object]:
        context = _new_context()
        try:
            typed_run_id = _identifier(RunId, run_id, context)
            request = TransformEvidenceCommandRequest(
                context,
                typed_run_id,
                RawEvidenceManifestRef(
                    _identifier(
                        RawEvidenceManifestId, evidence_manifest_id, context
                    ),
                    typed_run_id,
                    Sha256Digest(evidence_manifest_digest),
                ),
                tuple(
                    TransformationDefinition(
                        _identifier(
                            TransformationId, item.transformation_id, context
                        ),
                        DefinitionVersion(item.version),
                        (
                            None
                            if item.parameters is None
                            else _schema_payload(item.parameters)
                        ),
                    )
                    for item in transformations
                ),
            )
            result = platform_api.transform_evidence(request)
            _raise_result_failure(result.failure, context)
            return serialize_transform_command_result(result)
        except Exception as error:
            _raise_command_error(error, context, logger, "transform_evidence")

    @server.tool(
        name="analyze_datasets",
        description=(
            "Analyze explicit Dataset identities and publish one deterministic "
            "Analysis result."
        ),
        annotations=annotations,
    )
    async def analyze_datasets(
        datasets: list[DatasetReferenceTransport],
        analysis_definition_id: AnalysisDefinitionIdText,
        analysis_version: str,
        analysis_parameters: SchemaPayloadTransport,
        computation_environment_id: EnvironmentConfigurationIdText,
    ) -> dict[str, object]:
        context = _new_context()
        try:
            request = AnalyzeDatasetsCommandRequest(
                context,
                tuple(
                    DatasetInputReference(
                        _identifier(DatasetId, item.dataset_id, context),
                        Sha256Digest(item.content_digest),
                    )
                    for item in datasets
                ),
                _identifier(
                    AnalysisDefinitionId, analysis_definition_id, context
                ),
                DefinitionVersion(analysis_version),
                _schema_payload(analysis_parameters),
                _identifier(
                    EnvironmentConfigurationId,
                    computation_environment_id,
                    context,
                ),
            )
            result = platform_api.analyze_datasets(request)
            _raise_result_failure(result.failure, context)
            return serialize_analysis_command_result(result)
        except Exception as error:
            _raise_command_error(error, context, logger, "analyze_datasets")


def _build_source(value: BuildSourceTransport) -> BuildSourceInput:
    try:
        content = b64decode(value.content_base64, validate=True)
    except (Base64Error, ValueError) as error:
        raise InvalidValueError("Build source content is not valid base64.") from error
    return BuildSourceInput(
        BuildInputScope(value.scope), value.path, content, value.root
    )


def _schema_payload(value: SchemaPayloadTransport) -> SchemaReferencedPayload:
    try:
        document = json.loads(value.value_json)
    except (json.JSONDecodeError, TypeError) as error:
        raise InvalidValueError("Schema-referenced value is not valid JSON.") from error
    if not isinstance(document, dict):
        raise InvalidValueError("Schema-referenced value must be a JSON object.")
    return SchemaReferencedPayload(SchemaRef.parse(value.schema_ref), document)


def _raise_result_failure(
    failure: ApplicationError | None, context: RequestContext
) -> None:
    if failure is not None:
        _raise_tool_error(failure.code.value, failure.message, context)


def _raise_command_error(
    error: Exception,
    context: RequestContext,
    logger: logging.Logger,
    tool_name: str,
) -> NoReturn:
    if isinstance(error, ToolError):
        raise error
    if isinstance(error, DomainError):
        _raise_tool_error(
            ApplicationErrorCode.INVALID_VALUE.value,
            "Platform command request is invalid.",
            context,
        )
    logger.error(
        "MCP command failed unexpectedly.",
        extra={
            "event_name": "mcp.tool.failed",
            "request_id": str(context.request_id),
            "caller_id": MCP_CALLER_ID,
            "tool_name": tool_name,
            "error_code": ApplicationErrorCode.INVALID_CONFIGURATION.value,
        },
    )
    _raise_tool_error(
        ApplicationErrorCode.INVALID_CONFIGURATION.value,
        "MCP command execution failed.",
        context,
    )


def _new_context() -> RequestContext:
    return RequestContext(new_entity_id(RequestId), MCP_CALLER_ID)


def _page_request(
    page_size: int, cursor: str | None, context: RequestContext
) -> PageRequest:
    try:
        return PageRequest(page_size, cursor)
    except InvalidValueError:
        _raise_tool_error(
            ApplicationErrorCode.INVALID_VALUE.value,
            "Page size or cursor is invalid.",
            context,
        )


def _identifier(
    identifier_type: type[EntityIdT], value: str, context: RequestContext
) -> EntityIdT:
    try:
        return identifier_type.parse(value)
    except DomainError:
        _raise_tool_error(
            ApplicationErrorCode.INVALID_IDENTIFIER.value,
            "Typed identifier is invalid.",
            context,
        )


def _raise_query_error(
    error: Exception,
    context: RequestContext,
    logger: logging.Logger,
    tool_name: str,
) -> NoReturn:
    if isinstance(error, InvalidValueError):
        _raise_tool_error(
            ApplicationErrorCode.INVALID_VALUE.value,
            "Platform query request is invalid.",
            context,
        )
    safe_code = getattr(error, "code", None)
    if safe_code in {
        ApplicationErrorCode.DATA_PLANE_FAILED,
        ApplicationErrorCode.DATA_INTEGRITY_FAILED,
    }:
        _raise_tool_error(safe_code.value, str(error), context)
    logger.error(
        "MCP tool failed unexpectedly.",
        extra={
            "event_name": "mcp.tool.failed",
            "request_id": str(context.request_id),
            "caller_id": MCP_CALLER_ID,
            "error_code": ApplicationErrorCode.DATA_PLANE_FAILED.value,
        },
    )
    _raise_tool_error(
        ApplicationErrorCode.DATA_PLANE_FAILED.value,
        "MCP tool execution failed.",
        context,
    )


def _raise_tool_error(
    code: str, message: str, context: RequestContext
) -> NoReturn:
    payload = serialize_error(code, message, context.request_id)
    raise ToolError(json.dumps(payload, separators=(",", ":"), sort_keys=True))
