"""Provider-neutral application boundary for requesting execution."""

from collections.abc import Mapping
from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.build import AcceptedArtifact
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.execution import ExecutionProviderObservation
from ea_research_lab.domain.identifiers import EnvironmentConfigurationId, RunId
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaName, SchemaRef, SchemaVersion


_TEST_DEFINITION_REF = SchemaRef(
    SchemaName("test-definition"), SchemaVersion(0, 1, 0)
)


@dataclass(frozen=True, slots=True)
class ExecutionRequest:
    """Execution intent before any external provider interaction."""

    context: RequestContext
    run_id: RunId
    artifact: AcceptedArtifact
    test_definition: SchemaReferencedPayload
    environment_configuration_id: EnvironmentConfigurationId
    environment_configuration: SchemaReferencedPayload
    timeout: timedelta

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext, "RequestContext"),
            (self.run_id, RunId, "RunId"),
            (self.artifact, AcceptedArtifact, "accepted Artifact"),
            (
                self.environment_configuration_id,
                EnvironmentConfigurationId,
                "EnvironmentConfigurationId",
            ),
            (
                self.environment_configuration,
                SchemaReferencedPayload,
                "environment configuration",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise InvalidValueError(f"Execution request requires {label}.")
        if (
            not isinstance(self.test_definition, SchemaReferencedPayload)
            or self.test_definition.schema_ref != _TEST_DEFINITION_REF
        ):
            raise InvalidValueError(
                "Execution request requires Test Definition 0.1.0."
            )
        try:
            validate_document(_plain_json(self.test_definition.value))
        except ContractValidationError as error:
            raise InvalidValueError(
                "Execution request requires a valid Test Definition."
            ) from error
        if self.test_definition.value.get("artifact_id") != str(
            self.artifact.artifact_id
        ):
            raise InvalidValueError(
                "Test Definition must reference the accepted Artifact."
            )
        if not isinstance(self.timeout, timedelta) or self.timeout <= timedelta(0):
            raise InvalidValueError("Execution timeout must be a positive duration.")


class ExecutionProvider(Protocol):
    """Port implemented by one external execution technology adapter."""

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation: ...


def request_execution(
    provider: ExecutionProvider, request: ExecutionRequest
) -> ExecutionProviderObservation:
    """Invoke the provider without interpreting its observation as Run outcome."""

    if not isinstance(request, ExecutionRequest):
        raise TypeError("Execution operation requires an ExecutionRequest.")
    observation = provider.execute(request)
    if not isinstance(observation, ExecutionProviderObservation):
        raise TypeError(
            "ExecutionProvider must return an ExecutionProviderObservation."
        )
    return observation


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value
