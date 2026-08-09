"""Opaque typed entity identifiers."""

from dataclasses import dataclass
from typing import ClassVar, Self
from uuid import RFC_4122, UUID

from ea_research_lab.domain.errors import InvalidIdentifierError


@dataclass(frozen=True, slots=True)
class EntityId:
    """Validated serialized identity; use a concrete typed subclass."""

    value: str
    prefix: ClassVar[str] = ""

    def __post_init__(self) -> None:
        if not self.prefix:
            raise TypeError("EntityId must be constructed through a typed subclass.")
        if not isinstance(self.value, str):
            raise InvalidIdentifierError("Identifier must be a string.")

        expected_prefix = f"{self.prefix}_"
        if not self.value.startswith(expected_prefix):
            raise InvalidIdentifierError(
                f"Identifier must use the '{self.prefix}' prefix."
            )

        uuid_text = self.value[len(expected_prefix) :]
        try:
            parsed = UUID(uuid_text)
        except (ValueError, AttributeError) as error:
            raise InvalidIdentifierError("Identifier UUID is invalid.") from error

        if str(parsed) != uuid_text:
            raise InvalidIdentifierError(
                "Identifier UUID must use canonical lowercase hyphenated form."
            )
        if parsed.version != 7 or parsed.variant != RFC_4122:
            raise InvalidIdentifierError(
                "Identifier UUID must be an RFC 9562 UUID version 7."
            )

    @classmethod
    def parse(cls, value: str) -> Self:
        return cls(value)

    @classmethod
    def from_uuid(cls, value: UUID) -> Self:
        if not isinstance(value, UUID):
            raise InvalidIdentifierError("Identifier UUID must be a UUID value.")
        return cls(f"{cls.prefix}_{value}")

    def __str__(self) -> str:
        return self.value


class BuildRecordId(EntityId):
    __slots__ = ()
    prefix = "build"


class ArtifactId(EntityId):
    __slots__ = ()
    prefix = "artifact"


class TestDefinitionId(EntityId):
    __slots__ = ()
    prefix = "testdef"


class TestDefinitionRevisionId(EntityId):
    __slots__ = ()
    prefix = "testrev"


class EnvironmentConfigurationId(EntityId):
    __slots__ = ()
    prefix = "envcfg"


class RunId(EntityId):
    __slots__ = ()
    prefix = "run"


class RawEvidenceObjectId(EntityId):
    __slots__ = ()
    prefix = "rawobj"


class RawEvidenceManifestId(EntityId):
    __slots__ = ()
    prefix = "rawmanifest"


class TransformationId(EntityId):
    __slots__ = ()
    prefix = "transformation"


class DatasetId(EntityId):
    __slots__ = ()
    prefix = "dataset"


class AnalysisDefinitionId(EntityId):
    __slots__ = ()
    prefix = "analysisdef"


class AnalysisResultId(EntityId):
    __slots__ = ()
    prefix = "analysisresult"


class RequestId(EntityId):
    __slots__ = ()
    prefix = "request"
