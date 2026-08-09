"""Cross-client request context owned by the application boundary."""

from dataclasses import dataclass

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import RequestId


@dataclass(frozen=True, slots=True)
class RequestContext:
    request_id: RequestId
    caller_id: str | None = None

    def __post_init__(self) -> None:
        if not isinstance(self.request_id, RequestId):
            raise InvalidValueError("Request context requires a RequestId.")
        if self.caller_id is not None and (
            not isinstance(self.caller_id, str)
            or not self.caller_id
            or self.caller_id.strip() != self.caller_id
        ):
            raise InvalidValueError(
                "Caller identity must be a non-empty trimmed string when provided."
            )
