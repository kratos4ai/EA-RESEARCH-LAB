"""SQLite adapter for bounded research identity discovery."""

from __future__ import annotations

import base64
import binascii
import hashlib
import json
import sqlite3
from collections.abc import Callable
from pathlib import Path
from typing import TypeVar

from ea_research_lab.application.data_plane import DataPlaneError
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.research_query import Page, PageRequest
from ea_research_lab.domain.errors import InvalidValueError
from ea_research_lab.domain.evidence import RawEvidenceObject
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    RawEvidenceManifestId,
    RawEvidenceObjectId,
    RunId,
)
from ea_research_lab.domain.semantic import EvidenceObjectSummary
from ea_research_lab.domain.values import SchemaRef, Sha256Digest, UtcTimestamp


_CURSOR_VERSION = 1
_RUNS_QUERY = "research-runs"
_RUN_DATASETS_QUERY = "run-datasets"
_DATASET_ANALYSES_QUERY = "dataset-analyses"
_RUN_EVIDENCE_QUERY = "run-evidence-objects"
_RUN_KIND = "run-manifest"
_DATASET_KIND = "dataset-manifest"
_ANALYSIS_KIND = "analysis-result"
_BUILD_KIND = "build-record"
_EVIDENCE_MANIFEST_KIND = "raw-evidence-manifest"
_EVIDENCE_OBJECT_KIND = "raw-evidence-object"
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

    def list_run_evidence_objects(
        self,
        run_id: RunId,
        manifest_id: RawEvidenceManifestId,
        page: PageRequest,
    ) -> Page[EvidenceObjectSummary]:
        if not isinstance(run_id, RunId) or not isinstance(
            manifest_id, RawEvidenceManifestId
        ):
            raise TypeError("Run Evidence discovery requires typed identities.")
        if not isinstance(page, PageRequest):
            raise TypeError("Run Evidence discovery requires a PageRequest.")
        cursor_ordinal = _decode_evidence_cursor(page.cursor, run_id, manifest_id)
        parameters = (
            _RUN_KIND,
            str(run_id),
            _EVIDENCE_MANIFEST_KIND,
            str(manifest_id),
            str(manifest_id),
            str(run_id),
            str(run_id),
            str(manifest_id),
            _EVIDENCE_OBJECT_KIND,
            cursor_ordinal,
            page.limit + 1,
        )
        try:
            rows = self._require_connection().execute(
                """
                WITH manifest AS (
                    SELECT manifest_content.content AS document
                    FROM published_records AS manifest_record
                    JOIN content_objects AS manifest_content
                      ON manifest_content.digest = manifest_record.document_digest
                    JOIN published_records AS run_record
                      ON run_record.record_kind = ?
                     AND run_record.record_key = ?
                    JOIN content_objects AS run_content
                      ON run_content.digest = run_record.document_digest
                    WHERE manifest_record.record_kind = ?
                      AND manifest_record.record_key = ?
                      AND json_extract(
                          CAST(manifest_content.content AS TEXT), '$.manifest_id'
                      ) = ?
                      AND json_extract(
                          CAST(manifest_content.content AS TEXT), '$.run_id'
                      ) = ?
                      AND json_extract(
                          CAST(run_content.content AS TEXT), '$.run_id'
                      ) = ?
                      AND json_extract(
                          CAST(run_content.content AS TEXT),
                          '$.raw_evidence_manifest.manifest_id'
                      ) = ?
                      AND json_extract(
                          CAST(run_content.content AS TEXT),
                          '$.raw_evidence_manifest.content_digest'
                      ) = manifest_record.document_digest
                    LIMIT 1
                )
                SELECT
                    CAST(member.key AS INTEGER) AS ordinal,
                    object_record.record_key,
                    object_record.document_digest,
                    object_content.byte_length,
                    object_content.content
                FROM manifest
                JOIN json_each(
                    CAST(manifest.document AS TEXT), '$.objects'
                ) AS member
                JOIN published_records AS object_record
                  ON object_record.record_kind = ?
                 AND object_record.record_key = json_extract(
                     member.value, '$.object_id'
                 )
                JOIN content_objects AS object_content
                  ON object_content.digest = object_record.document_digest
                WHERE CAST(member.key AS INTEGER) > ?
                  AND json(CAST(object_content.content AS TEXT)) = json(member.value)
                ORDER BY ordinal ASC
                LIMIT ?
                """,
                parameters,
            ).fetchall()
            if not rows:
                self._require_evidence_binding(run_id, manifest_id)
                if page.cursor is not None:
                    raise InvalidValueError(
                        "Page cursor is invalid for this query."
                    )
            parsed = tuple(
                (
                    row[0],
                    _evidence_summary(
                        manifest_id,
                        row[1],
                        row[2],
                        row[3],
                        row[4],
                    ),
                )
                for row in rows
            )
        except InvalidValueError:
            raise
        except (sqlite3.Error, KeyError, TypeError, ValueError) as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_INTEGRITY_FAILED,
                "Run Evidence discovery failed integrity checks.",
            ) from error
        visible = parsed[: page.limit]
        next_cursor = (
            _encode_evidence_cursor(run_id, manifest_id, visible[-1][0])
            if len(parsed) > page.limit
            else None
        )
        return Page(tuple(item[1] for item in visible), next_cursor)

    def _require_evidence_binding(
        self, run_id: RunId, manifest_id: RawEvidenceManifestId
    ) -> None:
        row = self._require_connection().execute(
            """
            SELECT 1
            FROM published_records AS manifest_record
            JOIN content_objects AS manifest_content
              ON manifest_content.digest = manifest_record.document_digest
            JOIN published_records AS run_record
              ON run_record.record_kind = ?
             AND run_record.record_key = ?
            JOIN content_objects AS run_content
              ON run_content.digest = run_record.document_digest
            WHERE manifest_record.record_kind = ?
              AND manifest_record.record_key = ?
              AND json_extract(
                  CAST(manifest_content.content AS TEXT), '$.run_id'
              ) = ?
              AND json_extract(
                  CAST(run_content.content AS TEXT),
                  '$.raw_evidence_manifest.manifest_id'
              ) = ?
              AND json_extract(
                  CAST(run_content.content AS TEXT),
                  '$.raw_evidence_manifest.content_digest'
              ) = manifest_record.document_digest
            LIMIT 1
            """,
            (
                _RUN_KIND,
                str(run_id),
                _EVIDENCE_MANIFEST_KIND,
                str(manifest_id),
                str(run_id),
                str(manifest_id),
            ),
        ).fetchone()
        if row is None:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_INTEGRITY_FAILED,
                "Run Evidence discovery failed integrity checks.",
            )

    def find_build_record_for_artifact(
        self, artifact_id: ArtifactId
    ) -> BuildRecordId:
        if not isinstance(artifact_id, ArtifactId):
            raise TypeError("Build discovery requires an ArtifactId.")
        try:
            rows = self._require_connection().execute(
                """
                SELECT pr.record_key
                FROM published_records AS pr
                JOIN content_objects AS co
                  ON co.digest = pr.document_digest
                WHERE pr.record_kind = ?
                  AND json_extract(
                      CAST(co.content AS TEXT), '$.artifact_id'
                  ) = ?
                ORDER BY pr.record_key ASC
                LIMIT 2
                """,
                (_BUILD_KIND, str(artifact_id)),
            ).fetchall()
            if len(rows) != 1:
                raise ValueError
            return BuildRecordId.parse(rows[0][0])
        except (sqlite3.Error, TypeError, ValueError) as error:
            raise DataPlaneError(
                ApplicationErrorCode.DATA_INTEGRITY_FAILED,
                "Artifact-to-Build discovery failed integrity checks.",
            ) from error

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


def _encode_evidence_cursor(
    run_id: RunId, manifest_id: RawEvidenceManifestId, ordinal: int
) -> str:
    document = {
        "manifest_id": str(manifest_id),
        "ordinal": ordinal,
        "query": _RUN_EVIDENCE_QUERY,
        "run_id": str(run_id),
        "version": _CURSOR_VERSION,
    }
    content = json.dumps(
        document, sort_keys=True, separators=(",", ":"), allow_nan=False
    ).encode("utf-8")
    return base64.urlsafe_b64encode(content).decode("ascii").rstrip("=")


def _decode_evidence_cursor(
    cursor: str | None, run_id: RunId, manifest_id: RawEvidenceManifestId
) -> int:
    if cursor is None:
        return -1
    try:
        padding = "=" * (-len(cursor) % 4)
        content = base64.b64decode(
            f"{cursor}{padding}", altchars=b"-_", validate=True
        )
        document = json.loads(content.decode("utf-8"))
        if (
            not isinstance(document, dict)
            or set(document)
            != {"manifest_id", "ordinal", "query", "run_id", "version"}
            or document["manifest_id"] != str(manifest_id)
            or document["run_id"] != str(run_id)
            or document["query"] != _RUN_EVIDENCE_QUERY
            or document["version"] != _CURSOR_VERSION
            or type(document["ordinal"]) is not int
            or document["ordinal"] < 0
        ):
            raise ValueError
        return document["ordinal"]
    except (
        binascii.Error,
        json.JSONDecodeError,
        UnicodeDecodeError,
        KeyError,
        TypeError,
        ValueError,
    ) as error:
        raise InvalidValueError("Page cursor is invalid for this query.") from error


def _evidence_summary(
    manifest_id: RawEvidenceManifestId,
    object_id: str,
    document_digest: str,
    stored_length: int,
    content: bytes,
) -> EvidenceObjectSummary:
    if (
        not isinstance(content, bytes)
        or type(stored_length) is not int
        or len(content) != stored_length
        or hashlib.sha256(content).hexdigest() != document_digest
    ):
        raise ValueError("Evidence descriptor content is invalid.")
    document = json.loads(content.decode("utf-8"))
    if not isinstance(document, dict) or document.get("object_id") != object_id:
        raise ValueError("Evidence descriptor identity is invalid.")
    evidence = RawEvidenceObject(
        RawEvidenceObjectId.parse(document["object_id"]),
        document["media_type"],
        document["byte_length"],
        Sha256Digest(document["content_digest"]),
        (
            None
            if "payload_schema" not in document
            else SchemaRef.parse(document["payload_schema"])
        ),
        document.get("provider_namespace"),
    )
    return EvidenceObjectSummary(
        manifest_id,
        evidence.object_id,
        evidence.media_type,
        evidence.byte_length,
        evidence.content_digest,
        evidence.payload_schema,
        evidence.provider_namespace,
    )
