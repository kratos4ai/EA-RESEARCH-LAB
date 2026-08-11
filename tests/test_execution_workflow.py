from __future__ import annotations

import hashlib
import json
import unittest
from collections.abc import Mapping
from dataclasses import FrozenInstanceError
from datetime import timedelta
from unittest.mock import patch

import ea_research_lab.application.execution as execution_application
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.execution import ExecutionRequest, execute_run
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.contracts import validate_document
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.errors import EvidenceInvariantError, InvalidValueError
from ea_research_lab.domain.evidence import EvidenceCollectionOutcome
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderObservation,
    ExecutionProviderVerdict,
)
from ea_research_lab.domain.identifiers import (
    ArtifactId,
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
    RunId,
    TestDefinitionId,
    TestDefinitionRevisionId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    ReproducibilityAssessment,
    ReproducibilityLevel,
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)


def _ref(name: str) -> SchemaRef:
    return SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0))


def _payload(name: str, value: dict[str, object]) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(_ref(name), value)


def _request() -> ExecutionRequest:
    content = b"accepted artifact bytes"
    artifact = AcceptedArtifact(
        new_entity_id(ArtifactId),
        new_entity_id(BuildRecordId),
        Sha256Digest(hashlib.sha256(content).hexdigest()),
        content,
    )
    definition = _payload(
        "test-definition",
        {
            "schema_name": "test-definition",
            "schema_version": "0.1.0",
            "test_definition_id": str(new_entity_id(TestDefinitionId)),
            "test_definition_revision_id": str(
                new_entity_id(TestDefinitionRevisionId)
            ),
            "artifact_id": str(artifact.artifact_id),
            "execution_configuration": {
                "schema_ref": str(_ref("example-execution")),
                "value": {"opaque": True},
            },
            "sut_inputs": {
                "schema_ref": str(_ref("example-inputs")),
                "value": {},
            },
        },
    )
    return ExecutionRequest(
        RequestContext(new_entity_id(RequestId), "workflow-test"),
        new_entity_id(RunId),
        artifact,
        definition,
        new_entity_id(EnvironmentConfigurationId),
        _payload("execution-environment", {"captured": True}),
        timedelta(seconds=30),
    )


def _observation(
    verdict: ExecutionProviderVerdict,
    outputs: tuple[CapturedExecutionOutput, ...],
) -> ExecutionProviderObservation:
    return ExecutionProviderObservation(
        verdict,
        _payload("execution-provider-evidence", {"bounded": True}),
        outputs,
    )


class _Provider:
    def __init__(self, observation: ExecutionProviderObservation) -> None:
        self.observation = observation
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation:
        self.requests.append(request)
        return self.observation


class _RaisingProvider:
    def __init__(self, error: Exception) -> None:
        self.error = error
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation:
        self.requests.append(request)
        raise self.error


def _plain(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain(item) for item in value]
    return value


class ExecutionWorkflowTests(unittest.TestCase):
    def test_success_seals_exact_evidence_and_validates_final_run(self) -> None:
        request = _request()
        outputs = (
            CapturedExecutionOutput(
                b"<html>controlled report</html>",
                "text/html",
                provider_namespace="example.report",
            ),
            CapturedExecutionOutput(
                b"\xff\xfec\x00o\x00m\x00p\x00l\x00e\x00t\x00e\x00d\x00",
                "text/plain",
                provider_namespace="example.log",
            ),
        )
        observation = _observation(ExecutionProviderVerdict.COMPLETED, outputs)

        result = execute_run(
            _Provider(observation),
            request,
            ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
        )

        run_document = _plain(result.run_manifest.value)
        evidence_document = _plain(result.evidence_manifest_payload.value)
        validate_document(run_document)
        validate_document(evidence_document)
        self.assertEqual(run_document["status"], "completed")
        self.assertEqual(
            result.evidence_manifest.outcome,
            EvidenceCollectionOutcome.COMPLETED,
        )
        self.assertEqual(result.provider_observation, observation)
        self.assertIsNone(result.failure)
        self.assertEqual(len(result.raw_evidence), len(outputs))
        for collected, output in zip(result.raw_evidence, outputs):
            self.assertEqual(collected.content, output.content)
            self.assertEqual(
                str(collected.evidence_object.content_digest),
                hashlib.sha256(output.content).hexdigest(),
            )
            self.assertEqual(
                collected.evidence_object.byte_length,
                len(output.content),
            )
        manifest_bytes = json.dumps(
            evidence_document,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            allow_nan=False,
        ).encode("utf-8")
        self.assertEqual(
            str(result.evidence_manifest_ref.content_digest),
            hashlib.sha256(manifest_bytes).hexdigest(),
        )
        self.assertEqual(result.evidence_manifest.run_id, request.run_id)
        self.assertEqual(
            run_document["raw_evidence_manifest"]["manifest_id"],
            str(result.evidence_manifest.manifest_id),
        )
        self.assertEqual(
            run_document["test_definition_revision_id"],
            request.test_definition.value["test_definition_revision_id"],
        )
        with self.assertRaises(FrozenInstanceError):
            result.evidence_manifest.outcome = EvidenceCollectionOutcome.FAILED
        with self.assertRaises(FrozenInstanceError):
            result.raw_evidence[0].content = b"changed"

    def test_failed_and_cancelled_runs_preserve_available_evidence(self) -> None:
        mappings = (
            (
                ExecutionProviderVerdict.FAILED,
                "failed",
                EvidenceCollectionOutcome.FAILED,
            ),
            (
                ExecutionProviderVerdict.CANCELLED,
                "cancelled",
                EvidenceCollectionOutcome.CANCELLED,
            ),
            (
                ExecutionProviderVerdict.INCONCLUSIVE,
                "failed",
                EvidenceCollectionOutcome.FAILED,
            ),
        )
        for verdict, status, outcome in mappings:
            with self.subTest(verdict=verdict):
                output = CapturedExecutionOutput(
                    f"available {verdict.value} evidence".encode(),
                    "text/plain",
                    provider_namespace="example.failure",
                )
                result = execute_run(
                    _Provider(_observation(verdict, (output,))),
                    _request(),
                    ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
                )
                self.assertEqual(result.run_manifest.value["status"], status)
                self.assertEqual(result.evidence_manifest.outcome, outcome)
                self.assertEqual(result.raw_evidence[0].content, output.content)

    def test_collection_failure_is_independent_and_keeps_prior_bytes(self) -> None:
        request = _request()
        outputs = (
            CapturedExecutionOutput(b"first", "text/plain"),
            CapturedExecutionOutput(b"second", "text/plain"),
        )
        original = execution_application._collect_output
        calls = 0

        def fail_second(output: CapturedExecutionOutput):
            nonlocal calls
            calls += 1
            if calls == 2:
                raise EvidenceInvariantError("controlled collection failure")
            return original(output)

        with patch.object(
            execution_application,
            "_collect_output",
            fail_second,
        ):
            result = execute_run(
                _Provider(_observation(ExecutionProviderVerdict.COMPLETED, outputs)),
                request,
                ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
            )

        self.assertEqual(result.run_manifest.value["status"], "completed")
        self.assertEqual(
            result.evidence_manifest.outcome,
            EvidenceCollectionOutcome.COLLECTION_FAILED,
        )
        self.assertEqual(tuple(item.content for item in result.raw_evidence), (b"first",))
        self.assertEqual(len(result.provider_observation.captured_outputs), 2)
        self.assertEqual(result.evidence_manifest.run_id, request.run_id)

    def test_provider_exception_after_admission_finalizes_without_observation(self) -> None:
        for error, expected_status in (
            (RuntimeError("controlled provider failure"), "failed"),
            (TimeoutError("controlled provider timeout"), "cancelled"),
        ):
            with self.subTest(error=type(error).__name__):
                request = _request()
                provider = _RaisingProvider(error)

                result = execute_run(
                    provider,
                    request,
                    ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
                )

                self.assertEqual(provider.requests, [request])
                self.assertEqual(result.run_manifest.value["status"], expected_status)
                self.assertIsNone(result.provider_observation)
                self.assertIs(result.failure.cause, error)
                self.assertEqual(
                    result.failure.code.value,
                    "execution_provider_failed",
                )
                self.assertEqual(
                    result.evidence_manifest.outcome,
                    EvidenceCollectionOutcome.COLLECTION_FAILED,
                )
                self.assertEqual(result.raw_evidence, ())
                self.assertNotIn("provider_evidence", result.run_manifest.value)
                validate_document(_plain(result.evidence_manifest_payload.value))
                validate_document(_plain(result.run_manifest.value))

    def test_provider_start_failure_uses_actual_observation(self) -> None:
        request = _request()
        observation = ExecutionProviderObservation(
            ExecutionProviderVerdict.INCONCLUSIVE,
            _payload("execution-provider-evidence", {"process_started": False}),
        )

        result = execute_run(
            _Provider(observation),
            request,
            ReproducibilityAssessment(ReproducibilityLevel.EQUIVALENT),
        )

        self.assertEqual(result.run_manifest.value["status"], "failed")
        self.assertIs(result.provider_observation, observation)
        self.assertIsNone(result.failure)
        self.assertEqual(
            result.evidence_manifest.outcome,
            EvidenceCollectionOutcome.FAILED,
        )
        self.assertEqual(result.raw_evidence, ())

    def test_invalid_request_fails_before_admission_without_a_final_run(self) -> None:
        provider = _Provider(
            _observation(ExecutionProviderVerdict.COMPLETED, ())
        )
        with self.assertRaises(TypeError):
            execute_run(
                provider,
                object(),
                ReproducibilityAssessment(ReproducibilityLevel.EXACT),
            )
        with self.assertRaises(TypeError):
            execute_run(provider, _request(), object())
        valid = _request()
        incompatible = dict(valid.test_definition.value)
        incompatible["artifact_id"] = str(new_entity_id(ArtifactId))
        with self.assertRaises(InvalidValueError):
            ExecutionRequest(
                valid.context,
                valid.run_id,
                valid.artifact,
                _payload("test-definition", incompatible),
                valid.environment_configuration_id,
                valid.environment_configuration,
                valid.timeout,
            )
        self.assertEqual(provider.requests, [])


if __name__ == "__main__":
    unittest.main()
