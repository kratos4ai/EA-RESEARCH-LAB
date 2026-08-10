from __future__ import annotations

import unittest
from dataclasses import FrozenInstanceError, fields
from datetime import timedelta

from ea_research_lab.application.build import (
    BuildProvider,
    BuildRequest,
    BuildSourceInput,
    BuildSourceSpecification,
    request_build,
)
from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.identity import new_entity_id
from ea_research_lab.domain.build import (
    BuildInputScope,
    BuildOutcome,
    BuildProviderObservation,
)
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
    RequestId,
    RunId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    SourceRevision,
)


def _payload(name: str) -> SchemaReferencedPayload:
    return SchemaReferencedPayload(
        schema_ref=SchemaRef(SchemaName(name), SchemaVersion(0, 1, 0)),
        value={"opaque": {"key": "value"}},
    )


def _request() -> BuildRequest:
    return BuildRequest(
        context=RequestContext(new_entity_id(RequestId), "test-client"),
        build_record_id=new_entity_id(BuildRecordId),
        source_revision=SourceRevision("git", "repository", "revision", True),
        source_specification=BuildSourceSpecification(
            primary=BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "Experts/Main.mq5",
                b"primary\n",
            )
        ),
        build_configuration_id=new_entity_id(EnvironmentConfigurationId),
        build_configuration=_payload("build-configuration"),
        timeout=timedelta(seconds=30),
    )


class _FakeBuildProvider:
    def __init__(self, observation: BuildProviderObservation) -> None:
        self.observation = observation
        self.requests: list[BuildRequest] = []

    def build(self, request: BuildRequest) -> BuildProviderObservation:
        self.requests.append(request)
        return self.observation


class BuildBoundaryTests(unittest.TestCase):
    def test_request_and_nested_payloads_are_immutable(self) -> None:
        request = _request()

        self.assertEqual(
            tuple(field.name for field in fields(request)),
            (
                "context",
                "build_record_id",
                "source_revision",
                "source_specification",
                "build_configuration_id",
                "build_configuration",
                "timeout",
            ),
        )
        with self.assertRaises(FrozenInstanceError):
            request.timeout = timedelta(seconds=1)
        with self.assertRaises(TypeError):
            request.build_configuration.value["new"] = "value"
        with self.assertRaises(FrozenInstanceError):
            request.source_specification.primary.content += b"changed"

    def test_request_validates_required_types_and_positive_timeout(self) -> None:
        valid = _request()
        invalid_values = (
            ("context", object()),
            ("build_record_id", new_entity_id(RunId)),
            ("source_revision", object()),
            ("source_specification", object()),
            ("build_configuration_id", new_entity_id(RunId)),
            ("build_configuration", object()),
            ("timeout", timedelta(0)),
            ("timeout", timedelta(seconds=-1)),
        )

        for field_name, value in invalid_values:
            values = {
                field.name: getattr(valid, field.name) for field in fields(valid)
            }
            values[field_name] = value
            with self.subTest(field=field_name), self.assertRaises(
                InvalidValueError
            ):
                BuildRequest(**values)

    def test_source_specification_is_provider_neutral_and_immutable(self) -> None:
        dependency = BuildSourceInput(
            BuildInputScope.EXTERNAL,
            "Include/Dependency.mqh",
            b"dependency\n",
            root="stable-root",
        )
        specification = BuildSourceSpecification(
            primary=BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "Experts/Main.mq5",
                b"primary\n",
            ),
            dependencies=[dependency],
        )

        self.assertEqual(specification.dependencies, (dependency,))
        with self.assertRaises(FrozenInstanceError):
            specification.dependencies = ()
        with self.assertRaises(InvalidValueError):
            BuildSourceInput(
                BuildInputScope.WORKSPACE,
                "Experts/Main.mq5",
                b"primary\n",
                root="not-allowed",
            )
        with self.assertRaises(InvalidValueError):
            BuildSourceInput(
                BuildInputScope.EXTERNAL,
                "Include/Dependency.mqh",
                b"dependency\n",
            )
        with self.assertRaises(InvalidValueError):
            BuildSourceSpecification(primary=dependency)

    def test_fake_provider_is_substitutable_without_infrastructure(self) -> None:
        request = _request()
        observation = BuildProviderObservation(_payload("build-provider-evidence"))
        provider: BuildProvider = _FakeBuildProvider(observation)

        actual = request_build(provider, request)

        self.assertIs(actual, observation)
        self.assertEqual(provider.requests, [request])

    def test_provider_observation_is_not_an_artifact_or_final_outcome(self) -> None:
        observation = BuildProviderObservation(_payload("build-provider-evidence"))

        self.assertEqual(
            tuple(field.name for field in fields(observation)),
            ("provider_evidence",),
        )
        self.assertFalse(hasattr(observation, "artifact_id"))
        self.assertFalse(hasattr(observation, "candidate"))
        self.assertFalse(hasattr(observation, "outcome"))
        self.assertFalse(hasattr(observation, "status"))
        self.assertEqual(
            {outcome.value for outcome in BuildOutcome},
            {"succeeded", "failed"},
        )
        with self.assertRaises(FrozenInstanceError):
            observation.provider_evidence = _payload("replacement-evidence")

    def test_boundary_rejects_invalid_requests_and_provider_results(self) -> None:
        observation = BuildProviderObservation(_payload("build-provider-evidence"))
        provider = _FakeBuildProvider(observation)

        with self.assertRaises(TypeError):
            request_build(provider, object())

        class InvalidProvider:
            def build(self, request: BuildRequest) -> object:
                return object()

        with self.assertRaises(TypeError):
            request_build(InvalidProvider(), _request())

    def test_observation_requires_schema_referenced_evidence(self) -> None:
        with self.assertRaises(InvalidValueError):
            BuildProviderObservation(object())


if __name__ == "__main__":
    unittest.main()
