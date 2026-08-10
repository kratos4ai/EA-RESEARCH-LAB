"""Provider-neutral build values."""

from dataclasses import dataclass
from enum import StrEnum

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.provenance import SchemaReferencedPayload


class BuildOutcome(StrEnum):
    SUCCEEDED = "succeeded"
    FAILED = "failed"


class BuildInputScope(StrEnum):
    WORKSPACE = "workspace"
    EXTERNAL = "external"


@dataclass(frozen=True, slots=True)
class BuildProviderObservation:
    """Opaque provider evidence that is not a final platform outcome."""

    provider_evidence: SchemaReferencedPayload
    candidate_available: bool = False

    def __post_init__(self) -> None:
        if not isinstance(self.provider_evidence, SchemaReferencedPayload):
            raise InvalidValueError(
                "Build provider observation requires schema-referenced evidence."
            )
        if type(self.candidate_available) is not bool:
            raise InvalidValueError(
                "Build provider candidate availability must be a boolean."
            )
