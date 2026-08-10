"""Provider-neutral application boundary for requesting a build."""

from dataclasses import dataclass
from datetime import timedelta
from typing import Protocol

from ea_research_lab.application.context import RequestContext
from ea_research_lab.domain.build import BuildProviderObservation
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import (
    BuildRecordId,
    EnvironmentConfigurationId,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SourceRevision


@dataclass(frozen=True, slots=True)
class BuildRequest:
    """Build intent before provider-specific materialization or invocation."""

    context: RequestContext
    build_record_id: BuildRecordId
    source_revision: SourceRevision
    source_specification: SchemaReferencedPayload
    build_configuration_id: EnvironmentConfigurationId
    build_configuration: SchemaReferencedPayload
    timeout: timedelta

    def __post_init__(self) -> None:
        required = (
            (self.context, RequestContext, "RequestContext"),
            (self.build_record_id, BuildRecordId, "BuildRecordId"),
            (self.source_revision, SourceRevision, "SourceRevision"),
            (
                self.source_specification,
                SchemaReferencedPayload,
                "source specification",
            ),
            (
                self.build_configuration_id,
                EnvironmentConfigurationId,
                "EnvironmentConfigurationId",
            ),
            (
                self.build_configuration,
                SchemaReferencedPayload,
                "build configuration",
            ),
        )
        for value, expected_type, label in required:
            if not isinstance(value, expected_type):
                raise InvalidValueError(f"Build request requires {label}.")
        if not isinstance(self.timeout, timedelta) or self.timeout <= timedelta(0):
            raise InvalidValueError("Build timeout must be a positive duration.")


class BuildProvider(Protocol):
    """Port implemented by one external build technology adapter."""

    def build(self, request: BuildRequest) -> BuildProviderObservation: ...


def request_build(
    provider: BuildProvider, request: BuildRequest
) -> BuildProviderObservation:
    """Invoke the provider port without interpreting its evidence as success."""

    if not isinstance(request, BuildRequest):
        raise TypeError("Build operation requires a BuildRequest.")
    observation = provider.build(request)
    if not isinstance(observation, BuildProviderObservation):
        raise TypeError("BuildProvider must return a BuildProviderObservation.")
    return observation
