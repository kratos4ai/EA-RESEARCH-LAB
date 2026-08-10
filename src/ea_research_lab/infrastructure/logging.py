"""Structured operational logging with an explicit safe field set."""

from __future__ import annotations

import json
import logging
import re
import sys
from datetime import UTC, datetime
from typing import TextIO

from ea_research_lab.application.context import RequestContext
from ea_research_lab.application.errors import ApplicationError
from ea_research_lab.domain.identifiers import (
    AnalysisResultId,
    ArtifactId,
    BuildRecordId,
    DatasetId,
    RunId,
)
from ea_research_lab.infrastructure.config import Settings


LOGGER_NAME = "ea_research_lab"
_EVENT_PATTERN = re.compile(r"[a-z][a-z0-9]*(?:\.[a-z0-9]+)*")
_OPTIONAL_FIELDS = (
    "request_id",
    "caller_id",
    "build_record_id",
    "run_id",
    "artifact_id",
    "dataset_id",
    "analysis_result_id",
    "error_code",
)
_LOG_LEVELS = frozenset(
    {logging.DEBUG, logging.INFO, logging.WARNING, logging.ERROR, logging.CRITICAL}
)


class _OperationalHandler(logging.StreamHandler):
    pass


class _OperationalFormatter(logging.Formatter):
    def fields(self, record: logging.LogRecord) -> dict[str, str]:
        event = getattr(record, "event_name", None)
        if not isinstance(event, str) or _EVENT_PATTERN.fullmatch(event) is None:
            event = "operational.message"
        fields = {
            "timestamp": _utc_timestamp(record.created),
            "level": record.levelname,
            "logger": record.name,
            "event": event,
            "message": record.getMessage(),
        }
        for name in _OPTIONAL_FIELDS:
            value = getattr(record, name, None)
            if isinstance(value, str):
                fields[name] = value
        return fields


class _JsonFormatter(_OperationalFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return json.dumps(
            self.fields(record),
            ensure_ascii=False,
            allow_nan=False,
            separators=(",", ":"),
        )


class _TextFormatter(_OperationalFormatter):
    def format(self, record: logging.LogRecord) -> str:
        return " ".join(
            f"{name}={json.dumps(value, ensure_ascii=False)}"
            for name, value in self.fields(record).items()
        )


def configure_logging(
    settings: Settings, *, stream: TextIO | None = None
) -> logging.Logger:
    """Explicitly configure one idempotent package log handler."""

    if not isinstance(settings, Settings):
        raise TypeError("Logging configuration requires Settings.")

    logger = logging.getLogger(LOGGER_NAME)
    target_stream = sys.stderr if stream is None else stream
    handler = next(
        (
            candidate
            for candidate in logger.handlers
            if isinstance(candidate, _OperationalHandler)
        ),
        None,
    )
    if handler is None:
        handler = _OperationalHandler(target_stream)
        logger.addHandler(handler)
    elif handler.stream is not target_stream:
        handler.setStream(target_stream)

    formatter = _JsonFormatter() if settings.log_format == "json" else _TextFormatter()
    handler.setFormatter(formatter)
    logger.setLevel(settings.log_level)
    logger.propagate = False
    return logger


def log_event(
    logger: logging.Logger,
    level: int,
    event: str,
    message: str,
    *,
    context: RequestContext | None = None,
    build_record_id: BuildRecordId | None = None,
    run_id: RunId | None = None,
    artifact_id: ArtifactId | None = None,
    dataset_id: DatasetId | None = None,
    analysis_result_id: AnalysisResultId | None = None,
    error: ApplicationError | None = None,
) -> None:
    """Emit one operational event without arbitrary payload serialization."""

    if not isinstance(logger, logging.Logger):
        raise TypeError("Operational logging requires a Logger.")
    if type(level) is not int or level not in _LOG_LEVELS:
        raise ValueError("Operational log level is invalid.")
    if not isinstance(event, str) or _EVENT_PATTERN.fullmatch(event) is None:
        raise ValueError("Event name must use lowercase dot-separated segments.")
    if (
        not isinstance(message, str)
        or not message
        or message.strip() != message
    ):
        raise ValueError("Operational log message must be non-empty and trimmed.")
    if context is not None and not isinstance(context, RequestContext):
        raise TypeError("Operational log context must be a RequestContext.")
    if error is not None and not isinstance(error, ApplicationError):
        raise TypeError("Operational log error must be an ApplicationError.")

    extra: dict[str, str] = {"event_name": event}
    if context is not None:
        extra["request_id"] = str(context.request_id)
        if context.caller_id is not None:
            extra["caller_id"] = context.caller_id
    elif error is not None and error.request_id is not None:
        extra["request_id"] = str(error.request_id)

    if (
        context is not None
        and error is not None
        and error.request_id is not None
        and error.request_id != context.request_id
    ):
        raise ValueError("Request context and application error IDs do not match.")

    correlations = (
        ("build_record_id", build_record_id, BuildRecordId),
        ("run_id", run_id, RunId),
        ("artifact_id", artifact_id, ArtifactId),
        ("dataset_id", dataset_id, DatasetId),
        ("analysis_result_id", analysis_result_id, AnalysisResultId),
    )
    for name, value, expected_type in correlations:
        if value is not None:
            if not isinstance(value, expected_type):
                raise TypeError(f"{name} has an invalid identifier type.")
            extra[name] = str(value)
    if error is not None:
        extra["error_code"] = error.code.value

    logger.log(level, message, extra=extra)


def _utc_timestamp(created: float) -> str:
    return (
        datetime.fromtimestamp(created, UTC)
        .isoformat(timespec="milliseconds")
        .replace("+00:00", "Z")
    )
