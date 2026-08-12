"""SQLite adapter for bounded research identity discovery."""

from __future__ import annotations

import base64
import binascii
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from ea_research_lab.application.data_plane import DataPlaneError
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.research_query import Page, PageRequest
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.identifiers import AnalysisResultId, DatasetId, RunId
from ea_research_lab.domain.values import UtcTimestamp


_CURSOR_VERSION = 1
_RUNS_QUERY = "research-runs"
_RUN_DATASETS_QUERY = "run-datasets"
_DATASET_ANALYSES_QUERY = "dataset-analyses"
_RUN_KIND = "run-manifest"
_DATASET_KIND = "dataset-manifest"
_ANALYSIS_KIND = "analysis-result"
EntityIdT = TypeVar("EntityIdT", RunId, DatasetId, AnalysisResultId)


class SqliteResearchQuery:
    def __init__(self, database_path: Path) -> None:
        if not isinstance(database_path, Path):
            raise TypeError("SQLite research query requires a Path.")
        if not database_path.is_file():
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Research query store does not exist.",
            )
        connection: sqlite3.Connection | None = None
        try:
            connection = sqlite3.connect(
                f"{database_path.resolve().as_uri()}?mode=ro",
                uri=True,
                timeout=0,
                isolation_level=None,
            )
            connection.create_function(
                "erlab_utc_key", 1, _utc_key, deterministic=True
            )
        except sqlite3.Error as error:
            if connection is not None:
                connection.close()
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Research query store could not be opened.",
            ) from error
        self._connection: sqlite3.Connection | None = connection

    def __enter__(self) -> SqliteResearchQuery:
        self._require_connection()
        return self

    def __exit__(self, *exc_info: object) -> None:
        self.close()

    def close(self) -> None:
        if self._connection is not None:
            self._connection.close()
            self._connection = None

    def list_research_runs(self, page: PageRequest) -> Page[RunId]:
        return self._page(
            _RUNS_QUERY,
            _RUN_KIND,
            None,
            page,
            RunId.parse,
            descending=True,
        )

    def list_run_datasets(
        self, run_id: RunId, page: PageRequest
    ) -> Page[DatasetId]:
        if not isinstance(run_id, RunId):
            raise TypeError("Run Dataset discovery requires a RunId.")
        return self._page(
            _RUN_DATASETS_QUERY,
            _DATASET_KIND,
            str(run_id),
            page,
            DatasetId.parse,
            descending=False,
            relation=(
                "AND EXISTS ("
                "SELECT 1 FROM json_each(CAST(co.content AS TEXT), "
                "'$.input_manifests') AS item "
                "WHERE json_extract(item.value, '$.run_id') = ?"
                ")"
            ),
        )

    def list_dataset_analyses(
        self, dataset_id: DatasetId, page: PageRequest
    ) -> Page[AnalysisResultId]:
        if not isinstance(dataset_id, DatasetId):
            raise TypeError("Dataset Analysis discovery requires a DatasetId.")
        return self._page(
            _DATASET_ANALYSES_QUERY,
            _ANALYSIS_KIND,
            str(dataset_id),
            page,
            AnalysisResultId.parse,
            descending=True,
            relation=(
                "AND EXISTS ("
                "SELECT 1 FROM json_each(CAST(co.content AS TEXT), "
                "'$.provenance.input_datasets') AS item "
                "WHERE json_extract(item.value, '$.dataset_id') = ?"
                ")"
            ),
        )

    def _page(
        self,
        query: str,
        record_kind: str,
        parent: str | None,
        page: PageRequest,
        parse_id: Callable[[str], EntityIdT],
        *,
        descending: bool,
        relation: str = "",
    ) -> Page[EntityIdT]:
        if not isinstance(page, PageRequest):
            raise TypeError("Research discovery requires a PageRequest.")
        cursor_key, cursor_id = _decode_cursor(
            page.cursor, query, parent, parse_id
        )
        comparison = "<" if descending else ">"
        direction = "DESC" if descending else "ASC"
        sql = f"""
            WITH candidates AS (
                SELECT
                    pr.record_key AS entity_id,
                    json_extract(
                        CAST(co.content AS TEXT), '$.created_at'
                    ) AS created_at,
                    erlab_utc_key(json_extract(
                        CAST(co.content AS TEXT), '$.created_at'
                    )) AS order_key
                FROM published_records AS pr
                JOIN content_objects AS co
                  ON co.digest = pr.document_digest
                WHERE pr.record_kind = ?
                  {relation}
            )
            SELECT entity_id, created_at, order_key
            FROM candidates
            WHERE (
                ? IS NULL
                OR order_key {comparison} ?
                OR (order_key = ? AND entity_id > ?)
            )
            ORDER BY order_key {direction}, entity_id ASC
            LIMIT ?
        """
        parameters: list[object] = [record_kind]
        if relation:
            parameters.append(parent)
        parameters.extend(
            (cursor_key, cursor_key, cursor_key, cursor_id, page.limit + 1)
        )
        try:
            rows = self._require_connection().execute(sql, parameters).fetchall()
            parsed = tuple(
                (parse_id(row[0]), UtcTimestamp.parse(row[1])) for row in rows
            )
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_INTEGRITY_FAILED,
                "Research discovery failed integrity checks.",
            ) from error
        visible = parsed[: page.limit]
        next_cursor = (
            _encode_cursor(query, parent, visible[-1][1], visible[-1][0])
            if len(parsed) > page.limit
            else None
        )
        return Page(tuple(item[0] for item in visible), next_cursor)

    def _require_connection(self) -> sqlite3.Connection:
        if self._connection is None:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_PLANE_FAILED,
                "Research query store is closed.",
            )
        return self._connection


def _utc_key(value: object) -> str:
    if not isinstance(value, str):
        raise ValueError("Research ordering timestamp is invalid.")
    timestamp = UtcTimestamp.parse(value)
    return timestamp.value.isoformat(timespec="microseconds").replace(
        "+00:00", "Z"
    )


def _encode_cursor(
    query: str,
    parent: str | None,
    created_at: UtcTimestamp,
    entity_id: object,
) -> str:
    document = {
        "created_at": str(created_at),
        "entity_id": str(entity_id),
        "parent": parent,
        "query": query,
        "version": _CURSOR_VERSION,
    }
    content = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return base64.urlsafe_b64encode(content).decode("ascii").rstrip("=")


def _decode_cursor(
    cursor: str | None,
    query: str,
    parent: str | None,
    parse_id: Callable[[str], EntityIdT],
) -> tuple[str | None, str | None]:
    if cursor is None:
        return None, None
    try:
        padding = "=" * (-len(cursor) % 4)
        content = base64.b64decode(
            f"{cursor}{padding}", altchars=b"-_", validate=True
        )
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or set(document)
            != {"created_at", "entity_id", "parent", "query", "version"}
            or type(document["version"]) is not int
            or document["version"] != _CURSOR_VERSION
            or document["query"] != query
            or document["parent"] != parent
            or not isinstance(document["created_at"], str)
            or not isinstance(document["entity_id"], str)
        ):
            raise ValueError
        timestamp = UtcTimestamp.parse(document["created_at"])
        entity_id = parse_id(document["entity_id"])
    except (
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidValueError("Page cursor is invalid for this query.") from error
    return _utc_key(str(timestamp)), str(entity_id)
