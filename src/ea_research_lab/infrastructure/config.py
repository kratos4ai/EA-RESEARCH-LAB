"""Explicit, immutable Phase 01 configuration loading."""

from __future__ import annotations

import os
from collections.abc import Mapping
from dataclasses import dataclass
from typing import ClassVar

from ea_research_lab.application.errors import ApplicationErrorCode


_LOG_LEVEL_ENV = "EA_RESEARCH_LAB_LOG_LEVEL"
_LOG_FORMAT_ENV = "EA_RESEARCH_LAB_LOG_FORMAT"
_LOG_LEVELS = frozenset({"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"})
_LOG_FORMATS = frozenset({"json", "text"})


class ConfigurationError(ValueError):
    """Rejected configuration without exposing the rejected value."""

    code: ClassVar[str] = ApplicationErrorCode.INVALID_CONFIGURATION.value


@dataclass(frozen=True, slots=True)
class Settings:
    log_level: str = "INFO"
    log_format: str = "json"

    def __post_init__(self) -> None:
        if self.log_level not in _LOG_LEVELS:
            raise ConfigurationError(
                f"{_LOG_LEVEL_ENV} must be a supported logging level."
            )
        if self.log_format not in _LOG_FORMATS:
            raise ConfigurationError(
                f"{_LOG_FORMAT_ENV} must be 'json' or 'text'."
            )


def load_settings(
    *,
    log_level: str | None = None,
    log_format: str | None = None,
    environ: Mapping[str, str] | None = None,
) -> Settings:
    """Load explicit arguments over environment values over defaults."""

    source = os.environ if environ is None else environ
    return Settings(
        log_level=(
            log_level
            if log_level is not None
            else source.get(_LOG_LEVEL_ENV, "INFO")
        ),
        log_format=(
            log_format
            if log_format is not None
            else source.get(_LOG_FORMAT_ENV, "json")
        ),
    )
