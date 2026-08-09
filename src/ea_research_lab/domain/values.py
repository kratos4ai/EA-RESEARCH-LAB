"""Immutable provider- and storage-neutral domain values."""

import re
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Self

from ea_research_lab.domain.errors import InvalidValueError


_SHA256_PATTERN = re.compile(r"[0-9a-f]{64}")
_UTC_TIMESTAMP_PATTERN = re.compile(
    r"[0-9]{4}-[0-9]{2}-[0-9]{2}T[0-9]{2}:[0-9]{2}:[0-9]{2}"
    r"(?:\.[0-9]{1,6})?Z"
)
_SCHEMA_NAME_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:-[a-z0-9]+)*")
_SCHEMA_VERSION_PATTERN = re.compile(
    r"(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)\.(0|[1-9][0-9]*)"
)
_SCHEMA_URN_PREFIX = "urn:ea-research-lab:schema:"


def _require_clean_text(value: object, label: str) -> str:
    if not isinstance(value, str) or not value or value.strip() != value:
        raise InvalidValueError(f"{label} must be a non-empty trimmed string.")
    return value


@dataclass(frozen=True, slots=True)
class Sha256Digest:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SHA256_PATTERN.fullmatch(
            self.value
        ):
            raise InvalidValueError(
                "SHA-256 digest must contain 64 lowercase hexadecimal characters."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class UtcTimestamp:
    value: datetime

    def __post_init__(self) -> None:
        if (
            not isinstance(self.value, datetime)
            or self.value.tzinfo is None
            or self.value.utcoffset() != timedelta(0)
        ):
            raise InvalidValueError("Timestamp must be timezone-aware UTC.")
        object.__setattr__(self, "value", self.value.astimezone(timezone.utc))

    @classmethod
    def parse(cls, value: str) -> Self:
        if not isinstance(value, str) or not _UTC_TIMESTAMP_PATTERN.fullmatch(value):
            raise InvalidValueError(
                "Timestamp must use RFC 3339 UTC form with at most microsecond precision."
            )
        try:
            parsed = datetime.fromisoformat(f"{value[:-1]}+00:00")
        except ValueError as error:
            raise InvalidValueError("Timestamp is not valid RFC 3339 UTC.") from error
        return cls(parsed)

    def __str__(self) -> str:
        return self.value.isoformat().replace("+00:00", "Z")


@dataclass(frozen=True, slots=True)
class SchemaName:
    value: str

    def __post_init__(self) -> None:
        if not isinstance(self.value, str) or not _SCHEMA_NAME_PATTERN.fullmatch(
            self.value
        ):
            raise InvalidValueError(
                "Schema name must use lowercase kebab-case and start with a letter."
            )

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SchemaVersion:
    major: int
    minor: int
    patch: int

    def __post_init__(self) -> None:
        if any(type(part) is not int or part < 0 for part in self.parts):
            raise InvalidValueError(
                "Schema version parts must be non-negative integers."
            )

    @property
    def parts(self) -> tuple[int, int, int]:
        return self.major, self.minor, self.patch

    @classmethod
    def parse(cls, value: str) -> Self:
        if not isinstance(value, str):
            raise InvalidValueError("Schema version must be a string.")
        match = _SCHEMA_VERSION_PATTERN.fullmatch(value)
        if match is None:
            raise InvalidValueError(
                "Schema version must use exact MAJOR.MINOR.PATCH form."
            )
        return cls(*(int(part) for part in match.groups()))

    def __str__(self) -> str:
        return f"{self.major}.{self.minor}.{self.patch}"


@dataclass(frozen=True, slots=True)
class SchemaRef:
    name: SchemaName
    version: SchemaVersion

    def __post_init__(self) -> None:
        if not isinstance(self.name, SchemaName) or not isinstance(
            self.version, SchemaVersion
        ):
            raise InvalidValueError(
                "Schema reference requires a SchemaName and SchemaVersion."
            )

    @classmethod
    def parse(cls, value: str) -> Self:
        if not isinstance(value, str) or not value.startswith(_SCHEMA_URN_PREFIX):
            raise InvalidValueError(
                "Schema reference must use the repository-owned schema URN."
            )
        components = value[len(_SCHEMA_URN_PREFIX) :].split(":")
        if len(components) != 2:
            raise InvalidValueError("Schema reference URN is invalid.")
        return cls(SchemaName(components[0]), SchemaVersion.parse(components[1]))

    def __str__(self) -> str:
        return f"{_SCHEMA_URN_PREFIX}{self.name}:{self.version}"


@dataclass(frozen=True, slots=True)
class DefinitionVersion:
    value: str

    def __post_init__(self) -> None:
        _require_clean_text(self.value, "Definition version")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True, slots=True)
class SourceRevision:
    vcs_kind: str
    repository: str
    revision: str
    is_dirty: bool

    def __post_init__(self) -> None:
        _require_clean_text(self.vcs_kind, "VCS kind")
        _require_clean_text(self.repository, "Repository identity")
        _require_clean_text(self.revision, "Source revision")
        if type(self.is_dirty) is not bool:
            raise InvalidValueError("Source dirty state must be a boolean.")
