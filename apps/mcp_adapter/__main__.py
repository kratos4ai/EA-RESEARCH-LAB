"""Guarded local stdio entry point for the EA Research Lab MCP adapter."""

from __future__ import annotations

import argparse
import os
from collections.abc import Sequence
from dataclasses import dataclass
from pathlib import Path

from apps.mcp_adapter.server import ServerMode, create_server
from ea_research_lab.infrastructure.composition import (
    CommandPlatformConfiguration,
    compose_command_platform,
    compose_read_only_platform,
    create_command_platform_configuration,
)
from ea_research_lab.infrastructure.config import load_settings
from ea_research_lab.infrastructure.logging import configure_logging


_PROVIDER_ENVIRONMENT_KEYS = (
    "SystemRoot",
    "WINDIR",
    "PATH",
    "TEMP",
    "TMP",
    "USERPROFILE",
    "APPDATA",
    "LOCALAPPDATA",
    "PROGRAMDATA",
    "COMSPEC",
    "HOMEDRIVE",
    "HOMEPATH",
)


@dataclass(frozen=True, slots=True)
class ServerConfiguration:
    mode: ServerMode
    database: Path
    command: CommandPlatformConfiguration | None = None


def parse_configuration(argv: Sequence[str] | None = None) -> ServerConfiguration:
    parser = argparse.ArgumentParser(description="EA Research Lab local MCP adapter")
    parser.add_argument(
        "--mode",
        choices=tuple(mode.value for mode in ServerMode),
        default=ServerMode.READ_ONLY.value,
    )
    parser.add_argument("--database", type=Path, required=True)
    parser.add_argument("--build-workspace", type=Path)
    parser.add_argument("--artifact-logical-name")
    parser.add_argument("--artifact-version")
    parser.add_argument("--metaeditor-executable", type=Path)
    parser.add_argument("--metaeditor-digest")
    parser.add_argument("--metaeditor-external-root", action="append", default=[])
    parser.add_argument("--terminal-executable", type=Path)
    parser.add_argument("--terminal-digest")
    parser.add_argument("--mt5-data-root", type=Path)
    arguments = parser.parse_args(argv)
    mode = ServerMode(arguments.mode)
    if mode is ServerMode.READ_ONLY:
        return ServerConfiguration(mode, arguments.database)
    required = (
        arguments.build_workspace,
        arguments.artifact_logical_name,
        arguments.artifact_version,
        arguments.metaeditor_executable,
        arguments.metaeditor_digest,
        arguments.terminal_executable,
        arguments.terminal_digest,
        arguments.mt5_data_root,
    )
    if any(value is None for value in required):
        parser.error(
            "command-capable mode requires explicit build, MetaEditor, and MT5 configuration"
        )
    try:
        environment = {
            key: os.environ[key]
            for key in _PROVIDER_ENVIRONMENT_KEYS
            if os.environ.get(key)
        }
        command = create_command_platform_configuration(
            build_workspace_parent=arguments.build_workspace.resolve(),
            artifact_logical_name=arguments.artifact_logical_name,
            artifact_version=arguments.artifact_version,
            metaeditor_executable=arguments.metaeditor_executable.resolve(),
            metaeditor_digest=arguments.metaeditor_digest,
            terminal_executable=arguments.terminal_executable.resolve(),
            terminal_digest=arguments.terminal_digest,
            mt5_data_root=arguments.mt5_data_root.resolve(),
            environment=environment,
            external_roots=_external_roots(arguments.metaeditor_external_root),
        )
    except ValueError as error:
        parser.error(str(error))
    return ServerConfiguration(mode, arguments.database, command)


def _external_roots(values: list[str]) -> dict[str, Path]:
    roots: dict[str, Path] = {}
    for value in values:
        alias, separator, path = value.partition("=")
        if not separator or not alias or not path or alias in roots:
            raise ValueError(
                "--metaeditor-external-root must use unique ALIAS=ABSOLUTE_PATH values"
            )
        roots[alias] = Path(path).resolve()
    return roots


def main(argv: Sequence[str] | None = None) -> None:
    configuration = parse_configuration(argv)
    logger = configure_logging(load_settings())
    if configuration.mode is ServerMode.READ_ONLY:
        composition = compose_read_only_platform(configuration.database, logger)
    else:
        if configuration.command is None:
            raise SystemExit("Command-capable configuration is incomplete.")
        composition = compose_command_platform(
            configuration.database, configuration.command, logger
        )
    with composition as platform_api:
        create_server(platform_api, mode=configuration.mode, logger=logger).run()


if __name__ == "__main__":
    main()
