"""Entity identity generation at the application boundary."""

from typing import TypeVar
from uuid import uuid7

from ea_research_lab.domain.identifiers import EntityId


EntityIdT = TypeVar("EntityIdT", bound=EntityId)


def new_entity_id(identifier_type: type[EntityIdT]) -> EntityIdT:
    if identifier_type is EntityId or not issubclass(identifier_type, EntityId):
        raise TypeError("A concrete EntityId type is required.")
    return identifier_type.from_uuid(uuid7())
