"""Provider-neutral execution observation values."""

import re
from dataclasses import dataclass
from enum import StrEnum

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import SchemaRef


_MEDIA_TYPE_PATTERN = re.compile(r"[^/\s]+/[^/\s]+")


class ExecutionProviderVerdict(StrEnum):
    """Terminal provider classification, not a final Run outcome."""

    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"
    INCONCLUSIVE = "inconclusive"


@dataclass(frozen=True, slots=True)
class CapturedExecutionOutput:
    """Immutable captured bytes before Raw Evidence identity or sealing."""

    content: bytes
    media_type: str
    payload_schema: SchemaRef | None = None
    provider_namespace: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.content, bytes):
            raise InvalidValueError("Captured execution output must use bytes.")
        if not isinstance(self.media_type, str) or _MEDIA_TYPE_PATTERN.fullmatch(
            self.media_type
        ) is None:
            raise InvalidValueError(
                "Captured execution output media type must use type/subtype form."
            )
        if self.payload_schema is not None and not isinstance(
            self.payload_schema, SchemaRef
        ):
            raise InvalidValueError(
                "Captured execution output schema must be a SchemaRef."
            )
        if self.provider_namespace is not None and (
            not isinstance(self.provider_namespace, str)
            or not self.provider_namespace
            or self.provider_namespace.strip() != self.provider_namespace
        ):
            raise InvalidValueError(
                "Captured execution output provider namespace is invalid."
            )


@dataclass(frozen=True, slots=True)
class ExecutionProviderObservation:
    """Provider facts that cannot finalize a Run or seal Raw Evidence."""

    verdict: ExecutionProviderVerdict
    provider_evidence: SchemaReferencedPayload
    captured_outputs: tuple[CapturedExecutionOutput, ...] = ()

    def __post_init__(self) -> None:
        if not isinstance(self.verdict, ExecutionProviderVerdict):
            raise InvalidValueError("Execution provider verdict is invalid.")
        if not isinstance(self.provider_evidence, SchemaReferencedPayload):
            raise InvalidValueError(
                "Execution observation requires schema-referenced evidence."
            )
        try:
            outputs = tuple(self.captured_outputs)
        except TypeError as error:
            raise InvalidValueError(
                "Captured execution outputs must be an ordered collection."
            ) from error
        if any(not isinstance(output, CapturedExecutionOutput) for output in outputs):
            raise InvalidValueError(
                "Execution observation contains an invalid captured output."
            )
        object.__setattr__(self, "captured_outputs", outputs)
