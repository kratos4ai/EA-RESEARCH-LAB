"""Safe transport-neutral application error envelopes."""

import math
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from types import MappingProxyType

from ea_research_lab.domain.identifiers import RequestId


class ApplicationErrorCode(StrEnum):
    INVALID_IDENTIFIER = "invalid_identifier"
    INVALID_VALUE = "invalid_value"
    INVALID_PROVENANCE = "invalid_provenance"
    INVALID_EVIDENCE_MANIFEST = "invalid_evidence_manifest"
    INVALID_CONFIGURATION = "invalid_configuration"
    UNSUPPORTED_SCHEMA = "unsupported_schema"
    SCHEMA_VALIDATION_FAILED = "schema_validation_failed"
    BUILD_INPUT_INVALID = "build_input_invalid"
    BUILD_PROVIDER_FAILED = "build_provider_failed"
    ARTIFACT_REJECTED = "artifact_rejected"
    EXECUTION_PROVIDER_FAILED = "execution_provider_failed"


def _freeze_json(value: object) -> object:
    if value is None or isinstance(value, (str, bool, int)):
        return value
    if isinstance(value, float):
        if not math.isfinite(value):
            raise TypeError("Application error details require finite numbers.")
        return value
    if isinstance(value, Mapping):
        frozen: dict[str, object] = {}
        for key, item in value.items():
            if not isinstance(key, str):
                raise TypeError("Application error detail keys must be strings.")
            frozen[key] = _freeze_json(item)
        return MappingProxyType(frozen)
    if isinstance(value, (list, tuple)):
        return tuple(_freeze_json(item) for item in value)
    raise TypeError("Application error details must contain only JSON values.")


def _thaw_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _thaw_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_thaw_json(item) for item in value]
    return value


@dataclass(frozen=True, slots=True)
class ApplicationError:
    code: ApplicationErrorCode
    message: str
    details: Mapping[str, object] | None = None
    request_id: RequestId | None = None
    cause: BaseException | None = field(default=None, repr=False, compare=False)

    def __post_init__(self) -> None:
        if not isinstance(self.code, ApplicationErrorCode):
            raise TypeError("Application error code must be an ApplicationErrorCode.")
        if (
            not isinstance(self.message, str)
            or not self.message
            or self.message.strip() != self.message
        ):
            raise TypeError("Application error message must be non-empty and trimmed.")
        if self.details is not None:
            if not isinstance(self.details, Mapping):
                raise TypeError("Application error details must be a mapping.")
            object.__setattr__(self, "details", _freeze_json(self.details))
        if self.request_id is not None and not isinstance(self.request_id, RequestId):
            raise TypeError("Application error request_id must be a RequestId.")
        if self.cause is not None and not isinstance(self.cause, BaseException):
            raise TypeError("Application error cause must be an exception.")

    def to_dict(self) -> dict[str, object]:
        serialized: dict[str, object] = {
            "code": self.code.value,
            "message": self.message,
        }
        if self.details is not None:
            serialized["details"] = _thaw_json(self.details)
        if self.request_id is not None:
            serialized["request_id"] = str(self.request_id)
        return serialized
