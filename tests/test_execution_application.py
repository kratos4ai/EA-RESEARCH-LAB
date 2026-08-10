from __future__ import annotations

import hashlib
import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.execution import (
    ExecutionProvider,
    ExecutionRequest,
    request_execution,
)
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.errors import InvalidValueError
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
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)


def _payload(name: str, value: dict[str, object] | None = None):
    return SchemaReferencedPayload(
        SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0)),
        value or {"opaque": {"key": "value"}},
    )


def _artifact() -> AcceptedArtifact:
    content = b"accepted artifact bytes"
    return AcceptedArtifact(
        new_entity_id(ArtifactId),
        new_entity_id(BuildRecordId),
        Sha256Digest(hashlib.sha256(content).hexdigest()),
        content,
    )


def _test_definition(artifact: AcceptedArtifact) -> SchemaReferencedPayload:
    return _payload(
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
                "schema_ref": (
                    "urn:ea-research-lab:schema:example-execution-config:0.1.0"
                ),
                "value": {"opaque": True},
            },
            "sut_inputs": {
                "schema_ref": "urn:ea-research-lab:schema:example-inputs:0.1.0",
                "value": {"opaque": True},
            },
        },
    )


def _request() -> ExecutionRequest:
    artifact = _artifact()
    return ExecutionRequest(
        context=RequestContext(new_entity_id(RequestId), "test-client"),
        run_id=new_entity_id(RunId),
        artifact=artifact,
        test_definition=_test_definition(artifact),
        environment_configuration_id=new_entity_id(EnvironmentConfigurationId),
        environment_configuration=_payload("execution-environment"),
        timeout=timedelta(seconds=30),
    )


class _FakeExecutionProvider:
    def __init__(self, observation: ExecutionProviderObservation) -> None:
        self.observation = observation
        self.requests: list[ExecutionRequest] = []

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation:
        self.requests.append(request)
        return self.observation


class ExecutionBoundaryTests(unittest.TestCase):
    def test_request_is_immutable_and_has_only_required_inputs(self) -> None:
        request = _request()

        self.assertEqual(
            tuple(field.name for field in fields(request)),
            (
                "context",
                "run_id",
                "artifact",
                "test_definition",
                "environment_configuration_id",
                "environment_configuration",
                "timeout",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            request.timeout = timedelta(seconds=1)
        with self.assertRaises(TypeError):
            request.environment_configuration.value["new"] = "value"

    def test_request_validates_types_environment_and_timeout(self) -> None:
        valid = _request()
        invalid_values = (
            ("context", object()),
            ("run_id", valid.artifact.artifact_id),
            ("artifact", object()),
            ("environment_configuration_id", valid.run_id),
            ("environment_configuration", object()),
            ("timeout", timedelta(0)),
            ("timeout", timedelta(seconds=-1)),
        )
        for field_name, value in invalid_values:
            values = {field.name: getattr(valid, field.name) for field in fields(valid)}
            values[field_name] = value
            with self.subTest(field=field_name), self.assertRaises(InvalidValueError):
                ExecutionRequest(**values)

    def test_request_requires_exact_linked_test_definition(self) -> None:
        valid = _request()
        wrong_ref = _payload("other-contract", dict(valid.test_definition.value))
        wrong_artifact = dict(valid.test_definition.value)
        wrong_artifact["artifact_id"] = str(new_entity_id(ArtifactId))
        invalid_document = dict(valid.test_definition.value)
        del invalid_document["test_definition_revision_id"]

        for test_definition in (
            wrong_ref,
            _payload("test-definition", wrong_artifact),
            _payload("test-definition", invalid_document),
        ):
            with self.subTest(schema=str(test_definition.schema_ref)), self.assertRaises(
                InvalidValueError
            ):
                ExecutionRequest(
                    valid.context,
                    valid.run_id,
                    valid.artifact,
                    test_definition,
                    valid.environment_configuration_id,
                    valid.environment_configuration,
                    valid.timeout,
                )

    def test_captured_outputs_and_observation_are_immutable_and_neutral(self) -> None:
        output = CapturedExecutionOutput(
            b"opaque provider bytes",
            "application/octet-stream",
            provider_namespace="example.provider",
        )
        observation = ExecutionProviderObservation(
            ExecutionProviderVerdict.COMPLETED,
            _payload("execution-provider-evidence"),
            [output],
        )

        self.assertEqual(observation.captured_outputs, (output,))
        with self.assertRaises(FrozenInstanceError):
            output.content = b"changed"
        with self.assertRaises(FrozenInstanceError):
            observation.verdict = ExecutionProviderVerdict.FAILED
        for name in (
            "run_manifest",
            "run_status",
            "raw_evidence_manifest",
            "manifest_id",
            "analysis_result",
        ):
            self.assertFalse(hasattr(observation, name))

    def test_fake_provider_is_substitutable_and_propagates_context(self) -> None:
        request = _request()
        observation = ExecutionProviderObservation(
            ExecutionProviderVerdict.INCONCLUSIVE,
            _payload("execution-provider-evidence"),
        )
        provider: ExecutionProvider = _FakeExecutionProvider(observation)

        actual = request_execution(provider, request)

        self.assertIs(actual, observation)
        self.assertEqual(provider.requests, [request])
        self.assertIs(provider.requests[0].context, request.context)

    def test_boundary_rejects_invalid_observation_and_output_values(self) -> None:
        with self.assertRaises(InvalidValueError):
            CapturedExecutionOutput("bytes", "application/octet-stream")
        with self.assertRaises(InvalidValueError):
            CapturedExecutionOutput(b"bytes", "invalid")
        with self.assertRaises(InvalidValueError):
            ExecutionProviderObservation("completed", _payload("evidence"))
        with self.assertRaises(InvalidValueError):
            ExecutionProviderObservation(
                ExecutionProviderVerdict.COMPLETED,
                object(),
            )
        with self.assertRaises(TypeError):
            request_execution(_FakeExecutionProvider(object()), _request())
        with self.assertRaises(TypeError):
            request_execution(_FakeExecutionProvider(object()), object())


if __name__ == "__main__":
    unittest.main()
