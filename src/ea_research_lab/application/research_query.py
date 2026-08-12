"""Bounded discovery port for durable research identities."""

from dataclasses import dataclass
from typing import Generic, Protocol, TypeVar

from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import AnalysisResultId, DatasetId, RunId


DEFAULT_PAGE_LIMIT = 50
MAX_PAGE_LIMIT = 200
PageItemT = TypeVar("PageItemT")


@dataclass(frozen=True, slots=True)
class PageRequest:
    limit: int = DEFAULT_PAGE_LIMIT
    cursor: str | None = None

    def __post_init__(self) -> None:
        if type(self.limit) is not int or not 1 <= self.limit <= MAX_PAGE_LIMIT:
            raise InvalidValueError("Page limit must be between 1 and 200.")
        if self.cursor is not None and (
            not isinstance(self.cursor, str)
            or not self.cursor
            or self.cursor.strip() != self.cursor
        ):
            raise InvalidValueError("Page cursor is invalid.")


@dataclass(frozen=True, slots=True)
class Page(Generic[PageItemT]):
    items: tuple[PageItemT, ...]
    next_cursor: str | None = None

    def __post_init__(self) -> None:
        try:
            items = tuple(self.items)
        except TypeError as error:
            raise InvalidValueError("Page items are invalid.") from error
        if self.next_cursor is not None and (
            not isinstance(self.next_cursor, str)
            or not self.next_cursor
            or self.next_cursor.strip() != self.next_cursor
        ):
            raise InvalidValueError("Next page cursor is invalid.")
        object.__setattr__(self, "items", items)


class ResearchQueryPort(Protocol):
    def list_research_runs(self, page: PageRequest) -> Page[RunId]: ...

    def list_run_datasets(
        self, run_id: RunId, page: PageRequest
    ) -> Page[DatasetId]: ...

    def list_dataset_analyses(
        self, dataset_id: DatasetId, page: PageRequest
    ) -> Page[AnalysisResultId]: ...
