from __future__ import annotations

import asyncio
import base64
import io
import json
import logging
import sys
import tempfile
import unittest
from dataclasses import replace
from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch

from mcp import Client, ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from apps.mcp_adapter.__main__ import main, parse_configuration
from apps.mcp_adapter.serialization import (
    serialize_date,
    serialize_decimal,
    serialize_digest,
    serialize_entity_id,
    serialize_enum,
    serialize_research_run_page,
    serialize_timestamp,
)
from ea_research_lab.application.build import BuildRequest
from ea_research_lab.application.errors import ApplicationError
from ea_research_lab.application.platform_commands import (
    AnalysisCommandResult,
    AnalyzeDatasetsCommandRequest,
    BuildCommandResult,
    ExecuteRunCommandRequest,
    RunCommandResult,
    TransformEvidenceCommandRequest,
    TransformEvidenceCommandResult,
)
from apps.mcp_adapter.server import MCP_CALLER_ID, ServerMode, create_server
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.application.research_query import Page
from ea_research_lab.domain.build import BuildOutcome
from ea_research_lab.domain.evidence import (
    EvidenceCollectionOutcome,
    RawEvidenceManifestRef,
)
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    AnalysisDefinitionId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    EnvironmentConfigurationId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RequestId,
    RunId,
    TestDefinitionRevisionId,
    TransformationId,
)
from ea_research_lab.domain.semantic import (
    CanonicalChainProjection,
    DatasetContentReference,
    EvidenceObjectSummary,
    ProvenanceSummary,
    ResearchRunSummary,
)
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
    UtcTimestamp,
)
from ea_research_lab.infrastructure.sqlite_data_plane import SqliteDataPlane
from tests.test_visual_analytics import (
    _analysis_detail,
    _dataset_detail,
    _run_detail,
    _summary,
)


ROOT = Path(__file__).resolve().parents[1]


class _RecordingApi:
    def __init__(
        self,
        results: dict[str, object] | None = None,
        error: Exception | None = None,
    ) -> None:
        self.results = {} if results is None else results
        self.error = error
        self.calls: list[tuple[str, tuple[object, ...]]] = []

    def list_research_runs(self, context: object, page: object) -> object:
        return self._call("list_research_runs", context, page)

    def get_research_run(self, context: object, run_id: object) -> object:
        return self._call("get_research_run", context, run_id)

    def list_run_evidence_objects(
        self, context: object, run_id: object, manifest_id: object, page: object
    ) -> object:
        return self._call(
            "list_run_evidence_objects", context, run_id, manifest_id, page
        )

    def list_run_datasets(
        self, context: object, run_id: object, page: object
    ) -> object:
        return self._call("list_run_datasets", context, run_id, page)

    def get_dataset(self, context: object, dataset_id: object) -> object:
        return self._call("get_dataset", context, dataset_id)

    def list_dataset_analyses(
        self, context: object, dataset_id: object, page: object
    ) -> object:
        return self._call("list_dataset_analyses", context, dataset_id, page)

    def get_analysis(self, context: object, analysis_result_id: object) -> object:
        return self._call("get_analysis", context, analysis_result_id)

    def get_canonical_chain(self, context: object, *identifiers: object) -> object:
        return self._call("get_canonical_chain", context, *identifiers)

    def build_artifact(self, request: BuildRequest) -> object:
        default = BuildCommandResult(
            request.context.request_id,
            request.build_record_id,
            BuildOutcome.FAILED,
            None,
            True,
        )
        return self._call("build_artifact", request, default=default)

    def execute_run(self, request: ExecuteRunCommandRequest) -> object:
        reference = RawEvidenceManifestRef(
            new_entity_id(RawEvidenceManifestId),
            request.run_id,
            Sha256Digest("b" * 64),
        )
        default = RunCommandResult(
            request.context.request_id,
            request.run_id,
            "cancelled",
            EvidenceCollectionOutcome.CANCELLED,
            reference,
            True,
        )
        return self._call("execute_run", request, default=default)

    def transform_evidence(self, request: TransformEvidenceCommandRequest) -> object:
        default = TransformEvidenceCommandResult(
            request.context.request_id, request.run_id, ()
        )
        return self._call("transform_evidence", request, default=default)

    def analyze_datasets(self, request: AnalyzeDatasetsCommandRequest) -> object:
        default = AnalysisCommandResult(
            request.context.request_id,
            new_entity_id(AnalysisResultId),
            Sha256Digest("c" * 64),
            SchemaRef(SchemaName("execution-core-analysis-result"), SchemaVersion(0, 1, 0)),
            True,
        )
        return self._call("analyze_datasets", request, default=default)

    def _call(self, name: str, *arguments: object, default: object | None = None) -> object:
        self.calls.append((name, arguments))
        if self.error is not None:
            raise self.error
        return self.results.get(name, Page(()) if default is None else default)


class _SafePlatformFailure(Exception):
    code = ApplicationErrorCode.DATA_INTEGRITY_FAILED


def _logger(stream: io.StringIO | None = None) -> logging.Logger:
    logger = logging.Logger("mcp-adapter-test")
    if stream is not None:
        logger.addHandler(logging.StreamHandler(stream))
    else:
        logger.addHandler(logging.NullHandler())
    return logger


def _call(
    api: _RecordingApi,
    arguments: dict[str, object] | None = None,
    tool: str = "list_research_runs",
    mode: ServerMode = ServerMode.READ_ONLY,
):
    async def invoke():
        async with Client(create_server(api, mode=mode, logger=_logger())) as client:
            return await client.call_tool(tool, arguments or {})

    return asyncio.run(invoke())


def _command_arguments() -> dict[str, dict[str, object]]:
    build_id = str(new_entity_id(BuildRecordId))
    run_id = str(new_entity_id(RunId))
    artifact_id = str(new_entity_id(ArtifactId))
    environment_id = str(new_entity_id(EnvironmentConfigurationId))
    manifest_id = str(new_entity_id(RawEvidenceManifestId))
    dataset_id = str(new_entity_id(DatasetId))
    payload = {
        "schema_ref": "urn:ea-research-lab:schema:controlled-empty-inputs:0.1.0",
        "value_json": "{}",
    }
    return {
        "build_artifact": {
            "build_record_id": build_id,
            "vcs_kind": "git",
            "repository": "ea-research-lab",
            "source_revision": "test-revision",
            "source_is_dirty": True,
            "primary_source": {
                "scope": "workspace",
                "path": "Main.mq5",
                "content_base64": base64.b64encode(b"void OnStart() {}").decode(),
            },
            "dependencies": [],
            "build_configuration_id": environment_id,
            "build_configuration": payload,
            "timeout_seconds": 30,
        },
        "execute_run": {
            "run_id": run_id,
            "build_record_id": build_id,
            "artifact_id": artifact_id,
            "test_definition": payload,
            "environment_configuration_id": environment_id,
            "environment_configuration": payload,
            "timeout_seconds": 60,
            "reproducibility_level": "exact",
            "reproducibility_reasons": [],
        },
        "transform_evidence": {
            "run_id": run_id,
            "evidence_manifest_id": manifest_id,
            "evidence_manifest_digest": "a" * 64,
            "transformations": [
                {
                    "transformation_id": str(new_entity_id(TransformationId)),
                    "version": "1",
                }
                for _ in range(3)
            ],
        },
        "analyze_datasets": {
            "datasets": [{"dataset_id": dataset_id, "content_digest": "d" * 64}],
            "analysis_definition_id": str(new_entity_id(AnalysisDefinitionId)),
            "analysis_version": "1",
            "analysis_parameters": payload,
            "computation_environment_id": environment_id,
        },
    }


def _command_cli(root: Path) -> list[str]:
    return [
        "--mode",
        "command-capable",
        "--database",
        str(root / "research.sqlite3"),
        "--build-workspace",
        str(root / "builds"),
        "--artifact-logical-name",
        "mcp-build",
        "--artifact-version",
        "test-1",
        "--metaeditor-executable",
        str(root / "metaeditor64.exe"),
        "--metaeditor-digest",
        "a" * 64,
        "--terminal-executable",
        str(root / "terminal64.exe"),
        "--terminal-digest",
        "b" * 64,
        "--mt5-data-root",
        str(root / "mt5-data"),
    ]


class McpAdapterTests(unittest.TestCase):
    def test_command_mode_discovers_exactly_eight_queries_and_four_commands(self) -> None:
        async def inspect_server():
            async with Client(
                create_server(
                    _RecordingApi(),
                    mode=ServerMode.COMMAND_CAPABLE,
                    logger=_logger(),
                )
            ) as client:
                return await client.list_tools()

        tools = asyncio.run(inspect_server()).tools
        names = [tool.name for tool in tools]

        self.assertEqual(len(names), 12)
        self.assertEqual(
            names[-4:],
            [
                "build_artifact",
                "execute_run",
                "transform_evidence",
                "analyze_datasets",
            ],
        )
        self.assertTrue(all(tool.annotations.read_only_hint for tool in tools[:8]))
        self.assertTrue(
            all(not tool.annotations.read_only_hint for tool in tools[8:])
        )
        self.assertTrue(
            all("publish" in tool.description.lower() for tool in tools[8:])
        )

    def test_each_command_maps_once_to_typed_request_without_queries(self) -> None:
        expected_types = {
            "build_artifact": BuildRequest,
            "execute_run": ExecuteRunCommandRequest,
            "transform_evidence": TransformEvidenceCommandRequest,
            "analyze_datasets": AnalyzeDatasetsCommandRequest,
        }
        contexts = []
        requests = {}

        for tool, arguments in _command_arguments().items():
            with self.subTest(tool=tool):
                api = _RecordingApi()
                result = _call(
                    api, arguments, tool, mode=ServerMode.COMMAND_CAPABLE
                )
                self.assertFalse(result.is_error, result)
                self.assertEqual(len(api.calls), 1)
                called_name, (request,) = api.calls[0]
                self.assertEqual(called_name, tool)
                self.assertIsInstance(request, expected_types[tool])
                self.assertEqual(request.context.caller_id, MCP_CALLER_ID)
                contexts.append(request.context)
                requests[tool] = request

        self.assertEqual(len({context.request_id for context in contexts}), 4)
        build_request = contexts[0]
        self.assertIsInstance(build_request.request_id, RequestId)
        self.assertIsInstance(
            requests["execute_run"].execution_reproducibility,
            ReproducibilityAssessment,
        )
        self.assertEqual(len(requests["transform_evidence"].transformations), 3)
        self.assertIsInstance(
            requests["analyze_datasets"].datasets[0].content_digest,
            Sha256Digest,
        )

    def test_build_translation_decodes_exact_bytes_and_external_inputs(self) -> None:
        api = _RecordingApi()
        arguments = _command_arguments()["build_artifact"]
        arguments["dependencies"] = [
            {
                "scope": "external",
                "path": "Library.mqh",
                "content_base64": base64.b64encode(b"#define VALUE 1").decode(),
                "root": "shared",
            }
        ]

        result = _call(
            api,
            arguments,
            "build_artifact",
            mode=ServerMode.COMMAND_CAPABLE,
        )

        self.assertFalse(result.is_error)
        request = api.calls[0][1][0]
        self.assertEqual(request.source_specification.primary.content, b"void OnStart() {}")
        dependency = request.source_specification.dependencies[0]
        self.assertEqual(dependency.content, b"#define VALUE 1")
        self.assertEqual(dependency.root, "shared")
        self.assertTrue(request.source_revision.is_dirty)

    def test_command_research_outcomes_are_results_not_tool_errors(self) -> None:
        arguments = _command_arguments()
        build_api = _RecordingApi()
        build = _call(
            build_api,
            arguments["build_artifact"],
            "build_artifact",
            mode=ServerMode.COMMAND_CAPABLE,
        )
        run_api = _RecordingApi()
        run = _call(
            run_api,
            arguments["execute_run"],
            "execute_run",
            mode=ServerMode.COMMAND_CAPABLE,
        )

        self.assertFalse(build.is_error)
        self.assertIn('"outcome":"failed"', build.content[0].text.replace(" ", "").replace("\n", ""))
        self.assertFalse(run.is_error)
        self.assertIn('"status":"cancelled"', run.content[0].text.replace(" ", "").replace("\n", ""))

    def test_command_operational_failure_is_safe_and_never_retried(self) -> None:
        arguments = _command_arguments()["build_artifact"]
        api = _RecordingApi()

        def failed(request: BuildRequest) -> BuildCommandResult:
            api.calls.append(("build_artifact", (request,)))
            return BuildCommandResult(
                request.context.request_id,
                request.build_record_id,
                None,
                None,
                False,
                ApplicationError(
                    ApplicationErrorCode.INVALID_CONFIGURATION,
                    "Build configuration is unavailable.",
                    request_id=request.context.request_id,
                ),
            )

        api.build_artifact = failed
        result = _call(
            api,
            arguments,
            "build_artifact",
            mode=ServerMode.COMMAND_CAPABLE,
        )

        self.assertTrue(result.is_error)
        self.assertEqual(len(api.calls), 1)
        self.assertIn("invalid_configuration", result.content[0].text)
        self.assertNotIn("Traceback", result.content[0].text)

    def test_unexpected_command_failure_is_sanitized_once_for_every_command(self) -> None:
        for tool, arguments in _command_arguments().items():
            with self.subTest(tool=tool):
                api = _RecordingApi(
                    error=RuntimeError("secret provider path C:/private")
                )
                result = _call(
                    api, arguments, tool, mode=ServerMode.COMMAND_CAPABLE
                )
                self.assertTrue(result.is_error)
                self.assertEqual(len(api.calls), 1)
                self.assertEqual(api.calls[0][0], tool)
                self.assertIn("MCP command execution failed.", result.content[0].text)
                self.assertNotIn("private", result.content[0].text)

    def test_malformed_command_input_fails_before_platform_call(self) -> None:
        api = _RecordingApi()
        arguments = _command_arguments()["build_artifact"]
        arguments["primary_source"]["content_base64"] = "not base64!"

        result = _call(
            api,
            arguments,
            "build_artifact",
            mode=ServerMode.COMMAND_CAPABLE,
        )

        self.assertTrue(result.is_error)
        self.assertEqual(api.calls, [])
        self.assertIn("invalid_value", result.content[0].text)

    def test_one_tool_call_uses_one_platform_page_and_fresh_context(self) -> None:
        api = _RecordingApi()

        first = _call(api, {"page_size": 7, "cursor": "opaque-cursor"})
        second = _call(api, {"page_size": 7, "cursor": "opaque-cursor"})

        self.assertFalse(first.is_error)
        self.assertFalse(second.is_error)
        self.assertEqual(len(api.calls), 2)
        _, (first_context, first_page) = api.calls[0]
        _, (second_context, second_page) = api.calls[1]
        self.assertIsInstance(first_context.request_id, RequestId)
        self.assertEqual(first_context.request_id.value.split("_", 1)[1][14], "7")
        self.assertNotEqual(first_context.request_id, second_context.request_id)
        self.assertEqual(first_context.caller_id, MCP_CALLER_ID)
        self.assertEqual(second_context.caller_id, MCP_CALLER_ID)
        self.assertEqual(first_page.limit, 7)
        self.assertEqual(first_page.cursor, "opaque-cursor")
        self.assertEqual(second_page.cursor, "opaque-cursor")

    def test_invalid_input_fails_before_platform_api_call(self) -> None:
        api = _RecordingApi()

        result = _call(api, {"page_size": 201})

        self.assertTrue(result.is_error)
        self.assertEqual(api.calls, [])
        self.assertIn("invalid_value", result.content[0].text)
        self.assertNotIn("Traceback", result.content[0].text)

    def test_safe_platform_failure_preserves_safe_category(self) -> None:
        api = _RecordingApi(error=_SafePlatformFailure("Integrity check failed."))

        result = _call(api)

        self.assertTrue(result.is_error)
        payload = json.loads(result.content[0].text.partition(": ")[2])
        self.assertEqual(payload["error"]["code"], "data_integrity_failed")
        self.assertEqual(payload["error"]["message"], "Integrity check failed.")

    def test_unexpected_failure_is_sanitized_and_logged(self) -> None:
        stream = io.StringIO()
        api = _RecordingApi(error=RuntimeError("secret SQL at C:/private.sqlite3"))

        async def invoke():
            async with Client(create_server(api, logger=_logger(stream))) as client:
                return await client.call_tool("list_research_runs", {})

        result = asyncio.run(invoke())

        self.assertTrue(result.is_error)
        self.assertIn("MCP tool execution failed.", result.content[0].text)
        self.assertNotIn("private.sqlite3", result.content[0].text)
        self.assertNotIn("Traceback", result.content[0].text)
        self.assertIn("MCP tool failed unexpectedly.", stream.getvalue())
        self.assertNotIn("private.sqlite3", stream.getvalue())

    def test_discovery_is_tools_only_and_has_no_command_tools(self) -> None:
        async def inspect_server():
            async with Client(create_server(_RecordingApi(), logger=_logger())) as client:
                tools = await client.list_tools()
                resources = await client.list_resources()
                prompts = await client.list_prompts()
                return tools, resources, prompts

        tools, resources, prompts = asyncio.run(inspect_server())

        self.assertEqual(
            [tool.name for tool in tools.tools],
            [
                "list_research_runs",
                "get_research_run",
                "list_run_evidence_objects",
                "list_run_datasets",
                "get_dataset",
                "list_dataset_analyses",
                "get_analysis",
                "get_canonical_chain",
            ],
        )
        self.assertEqual(resources.resources, [])
        self.assertEqual(prompts.prompts, [])
        self.assertTrue(all(tool.annotations.read_only_hint for tool in tools.tools))
        schemas = {tool.name: tool.input_schema for tool in tools.tools}
        self.assertEqual(
            schemas["get_canonical_chain"]["required"],
            ["build_record_id", "run_id", "analysis_result_id"],
        )
        self.assertEqual(
            schemas["list_run_evidence_objects"]["required"],
            ["run_id", "manifest_id"],
        )
        self.assertTrue(
            schemas["get_research_run"]["properties"]["run_id"]["pattern"].startswith(
                "^run_"
            )
        )
        self.assertTrue(
            schemas["get_dataset"]["properties"]["dataset_id"]["pattern"].startswith(
                "^dataset_"
            )
        )
        for name in (
            "list_research_runs",
            "list_run_evidence_objects",
            "list_run_datasets",
            "list_dataset_analyses",
        ):
            self.assertEqual(
                schemas[name]["properties"]["page_size"]["type"], "integer"
            )
            self.assertEqual(
                schemas[name]["properties"]["page_size"]["minimum"], 1
            )
            self.assertEqual(
                schemas[name]["properties"]["page_size"]["maximum"], 200
            )
            self.assertIn("cursor", schemas[name]["properties"])

    def test_each_query_tool_maps_once_to_its_typed_platform_api_method(self) -> None:
        run = _run_detail()
        dataset = replace(_dataset_detail(), execution_summary=_summary())
        analysis = replace(
            _analysis_detail(),
            input_datasets=(
                DatasetContentReference(
                    dataset.summary.dataset_id, dataset.summary.content_digest
                ),
            ),
        )
        evidence = EvidenceObjectSummary(
            run.evidence_history[-1].manifest_id,
            new_entity_id(RawEvidenceObjectId),
            "text/html",
            42,
            Sha256Digest("d" * 64),
            provider_namespace="metatrader5.strategy-tester.report",
        )
        chain = CanonicalChainProjection(
            ProvenanceSummary(
                run.build_record_id,
                run.summary.artifact_id,
                Sha256Digest("e" * 64),
                run.summary.test_definition_revision_id,
                run.summary.run_id,
                run.evidence_history,
                analysis.input_datasets,
                analysis.summary.analysis_result_id,
            ),
            run,
            (dataset.summary,),
            analysis,
        )
        results = {
            "list_research_runs": Page((run.summary,), "run-cursor"),
            "get_research_run": run,
            "list_run_evidence_objects": Page((evidence,), "evidence-cursor"),
            "list_run_datasets": Page((dataset.summary,), "dataset-cursor"),
            "get_dataset": dataset,
            "list_dataset_analyses": Page((analysis.summary,), "analysis-cursor"),
            "get_analysis": analysis,
            "get_canonical_chain": chain,
        }
        cases = (
            ("list_research_runs", {"page_size": 3, "cursor": "opaque"}),
            ("get_research_run", {"run_id": str(run.summary.run_id)}),
            (
                "list_run_evidence_objects",
                {
                    "run_id": str(run.summary.run_id),
                    "manifest_id": str(run.evidence_history[-1].manifest_id),
                    "page_size": 3,
                    "cursor": "opaque",
                },
            ),
            (
                "list_run_datasets",
                {
                    "run_id": str(run.summary.run_id),
                    "page_size": 3,
                    "cursor": "opaque",
                },
            ),
            ("get_dataset", {"dataset_id": str(dataset.summary.dataset_id)}),
            (
                "list_dataset_analyses",
                {
                    "dataset_id": str(dataset.summary.dataset_id),
                    "page_size": 3,
                    "cursor": "opaque",
                },
            ),
            (
                "get_analysis",
                {"analysis_result_id": str(analysis.summary.analysis_result_id)},
            ),
            (
                "get_canonical_chain",
                {
                    "build_record_id": str(run.build_record_id),
                    "run_id": str(run.summary.run_id),
                    "analysis_result_id": str(
                        analysis.summary.analysis_result_id
                    ),
                },
            ),
        )
        api = _RecordingApi(results)

        responses = [_call(api, arguments, tool) for tool, arguments in cases]

        self.assertTrue(all(not response.is_error for response in responses))
        self.assertEqual([name for name, _ in api.calls], list(results))
        contexts = [arguments[0] for _, arguments in api.calls]
        self.assertEqual(len({context.request_id for context in contexts}), 8)
        self.assertTrue(all(context.caller_id == MCP_CALLER_ID for context in contexts))
        self.assertIsInstance(api.calls[1][1][1], RunId)
        self.assertIsInstance(api.calls[2][1][1], RunId)
        self.assertIsInstance(api.calls[2][1][2], RawEvidenceManifestId)
        self.assertIsInstance(api.calls[4][1][1], DatasetId)
        self.assertIsInstance(api.calls[6][1][1], AnalysisResultId)
        self.assertIsInstance(api.calls[7][1][1], BuildRecordId)
        self.assertEqual(responses[0].structured_content["next_cursor"], "run-cursor")
        self.assertNotIn("content", responses[2].structured_content["items"][0])
        self.assertNotIn("payload", responses[4].structured_content)
        metrics = responses[6].structured_content["bounded_result"][
            "aggregate_metrics"
        ]
        self.assertEqual(metrics["net_return"]["value"], "0.000038000000")
        self.assertNotIsInstance(metrics["profit_factor"]["value"], float)

    def test_malformed_typed_identifier_fails_before_platform_call(self) -> None:
        api = _RecordingApi()

        result = _call(api, {"run_id": "not-a-run-id"}, "get_research_run")

        self.assertTrue(result.is_error)
        self.assertEqual(api.calls, [])
        self.assertIn("invalid_identifier", result.content[0].text)

    def test_mode_parsing_defaults_read_only_and_requires_explicit_command_mode(self) -> None:
        read_only = parse_configuration(["--database", "research.sqlite3"])
        with tempfile.TemporaryDirectory() as name:
            command = parse_configuration(_command_cli(Path(name)))

        self.assertIs(read_only.mode, ServerMode.READ_ONLY)
        self.assertIs(command.mode, ServerMode.COMMAND_CAPABLE)
        self.assertIsNotNone(command.command)

    def test_command_capable_entrypoint_uses_only_explicit_command_composition(self) -> None:
        with tempfile.TemporaryDirectory() as name:
            with (
                patch("apps.mcp_adapter.__main__.compose_command_platform") as compose,
                patch("apps.mcp_adapter.__main__.compose_read_only_platform") as read_only,
                patch("apps.mcp_adapter.__main__.create_server") as create,
            ):
                compose.return_value.__enter__.return_value = _RecordingApi()
                main(_command_cli(Path(name)))

        compose.assert_called_once()
        read_only.assert_not_called()
        create.assert_called_once()
        create.return_value.run.assert_called_once_with()

    def test_command_mode_rejects_missing_provider_configuration(self) -> None:
        with self.assertRaises(SystemExit):
            parse_configuration(
                ["--mode", "command-capable", "--database", "research.sqlite3"]
            )

    def test_explicit_serialization_preserves_foundational_values(self) -> None:
        identifier = new_entity_id(RunId)
        timestamp = UtcTimestamp(datetime(2026, 8, 12, 12, 30, tzinfo=UTC))
        digest = Sha256Digest("a" * 64)

        self.assertEqual(serialize_decimal(Decimal("0.002630000000")), "0.002630000000")
        self.assertEqual(serialize_timestamp(timestamp), "2026-08-12T12:30:00Z")
        self.assertEqual(serialize_date(date(2026, 8, 12)), "2026-08-12")
        self.assertEqual(serialize_entity_id(identifier), str(identifier))
        self.assertEqual(serialize_digest(digest), "a" * 64)
        self.assertEqual(
            serialize_enum(EvidenceCollectionOutcome.COMPLETED), "completed"
        )

    def test_run_page_serialization_preserves_null_and_opaque_cursor(self) -> None:
        summary = ResearchRunSummary(
            new_entity_id(RunId),
            new_entity_id(ArtifactId),
            new_entity_id(TestDefinitionRevisionId),
            "created",
            UtcTimestamp(datetime(2026, 8, 12, tzinfo=UTC)),
            SchemaRef(SchemaName("run-manifest"), SchemaVersion(0, 1, 0)),
            None,
            None,
        )

        serialized = serialize_research_run_page(Page((summary,), "opaque+/=cursor"))

        self.assertEqual(serialized["next_cursor"], "opaque+/=cursor")
        self.assertIsNone(serialized["items"][0]["started_at"])
        self.assertIsNone(serialized["items"][0]["evidence_manifest"])

    def test_real_stdio_handshake_call_and_clean_shutdown(self) -> None:
        async def run_stdio(database: Path):
            parameters = StdioServerParameters(
                command=sys.executable,
                args=[
                    "-m",
                    "apps.mcp_adapter",
                    "--mode",
                    "read-only",
                    "--database",
                    str(database),
                ],
                cwd=ROOT,
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool(
                        "list_research_runs", {"page_size": 1}
                    )
                    return tools, result

        with tempfile.TemporaryDirectory() as name:
            database = Path(name) / "mcp.sqlite3"
            with SqliteDataPlane(database):
                pass
            tools, result = asyncio.run(run_stdio(database))

        self.assertEqual(len(tools.tools), 8)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content, {"items": [], "next_cursor": None})

    def test_command_capable_stdio_discovery_and_fake_command(self) -> None:
        async def run_stdio():
            parameters = StdioServerParameters(
                command=sys.executable,
                args=["-m", "tests.fixtures.mcp_command_server"],
                cwd=ROOT,
            )
            async with stdio_client(parameters) as (read_stream, write_stream):
                async with ClientSession(read_stream, write_stream) as session:
                    await session.initialize()
                    tools = await session.list_tools()
                    result = await session.call_tool(
                        "build_artifact", _command_arguments()["build_artifact"]
                    )
                    return tools, result

        tools, result = asyncio.run(run_stdio())

        self.assertEqual(len(tools.tools), 12)
        self.assertFalse(result.is_error)
        self.assertEqual(result.structured_content["outcome"], "failed")


if __name__ == "__main__":
    unittest.main()
