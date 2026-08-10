"""MetaEditor-specific build invocation and bounded provider evidence."""

from __future__ import annotations

import ctypes
import hashlib
import logging
import os
import re
import subprocess
import time
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from types import MappingProxyType

from ea_research_lab.application.build import BuildRequest
from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.build import BuildProviderObservation
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)
from ea_research_lab.infrastructure.build_workspace import (
    BuildWorkspaceError,
    MaterializedBuildWorkspace,
)
from ea_research_lab.infrastructure.logging import log_event


_CONFIGURATION_REF = SchemaRef(
    SchemaName("metaeditor-build-configuration"), SchemaVersion(0, 1, 0)
)
_EVIDENCE_REF = SchemaRef(
    SchemaName("metaeditor-build-evidence"), SchemaVersion(0, 1, 0)
)
_RESULT_PATTERN = re.compile(
    r"^Result:\s*(\d+)\s+errors?,\s*(\d+)\s+warnings?\b", re.MULTILINE
)
_INCLUDE_PATTERN = re.compile(r": information: including (.+)$", re.MULTILINE)
_ENVIRONMENT_KEYS = (
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
_TERMINATION_GRACE_SECONDS = 1.0


class MetaEditorAdapterError(ValueError):
    """Safe adapter precondition or owned-process failure."""

    code = ApplicationErrorCode.BUILD_PROVIDER_FAILED.value


@dataclass(frozen=True, slots=True)
class MetaEditorConfiguration:
    """Only MetaEditor settings consumed by the initial adapter."""

    executable: Path
    executable_digest: Sha256Digest
    environment: Mapping[str, str]
    max_log_bytes: int = 1_048_576

    def __post_init__(self) -> None:
        if not isinstance(self.executable, Path) or not isinstance(
            self.executable_digest, Sha256Digest
        ):
            raise MetaEditorAdapterError("MetaEditor configuration is invalid.")
        if not self.executable.is_absolute() or not isinstance(
            self.environment, Mapping
        ):
            raise MetaEditorAdapterError("MetaEditor configuration is invalid.")
        environment = dict(self.environment)
        if any(
            key not in _ENVIRONMENT_KEYS
            or not isinstance(value, str)
            or not value
            for key, value in environment.items()
        ):
            raise MetaEditorAdapterError("MetaEditor environment is invalid.")
        if type(self.max_log_bytes) is not int or self.max_log_bytes < 2:
            raise MetaEditorAdapterError("MetaEditor log limit is invalid.")
        object.__setattr__(
            self,
            "environment",
            MappingProxyType(dict(sorted(environment.items()))),
        )

    @property
    def payload(self) -> SchemaReferencedPayload:
        value = {
            "schema_name": "metaeditor-build-configuration",
            "schema_version": "0.1.0",
            "provider": "metaeditor",
            "executable_path": str(self.executable),
            "executable_digest": str(self.executable_digest),
            "environment": dict(self.environment),
            "max_log_bytes": self.max_log_bytes,
        }
        _validate_provider_document(value)
        return SchemaReferencedPayload(_CONFIGURATION_REF, value)


class MetaEditorBuildProvider:
    """BuildProvider adapter for the observed direct MetaEditor compile mode."""

    def __init__(
        self,
        configuration: MetaEditorConfiguration,
        workspace: MaterializedBuildWorkspace,
        *,
        logger: logging.Logger | None = None,
    ) -> None:
        if not isinstance(configuration, MetaEditorConfiguration) or not isinstance(
            workspace, MaterializedBuildWorkspace
        ):
            raise MetaEditorAdapterError("MetaEditor adapter setup is invalid.")
        if logger is not None and not isinstance(logger, logging.Logger):
            raise MetaEditorAdapterError("MetaEditor logger is invalid.")
        self._configuration = configuration
        self._workspace = workspace
        self._logger = logger

    def build(self, request: BuildRequest) -> BuildProviderObservation:
        if not isinstance(request, BuildRequest):
            raise TypeError("MetaEditor build requires a BuildRequest.")
        if request.build_configuration != self._configuration.payload:
            raise MetaEditorAdapterError("Build configuration does not match adapter.")

        executable = self._validated_executable()
        primary = self._validated_primary()
        if self._workspace.external_roots:
            raise MetaEditorAdapterError(
                "External input mapping is not verified for this adapter."
            )
        try:
            self._workspace.verify_integrity()
        except BuildWorkspaceError as error:
            raise MetaEditorAdapterError("Build workspace integrity failed.") from error

        log_path = primary.with_suffix(".log")
        candidate_path = primary.with_suffix(".ex5")
        if log_path.exists() or candidate_path.exists():
            raise MetaEditorAdapterError("Build workspace contains stale provider output.")

        executable_version = _read_windows_file_version(executable)
        argv = _metaeditor_argv(executable, primary)
        if self._logger is not None:
            log_event(
                self._logger,
                logging.INFO,
                "build.provider.started",
                "Build provider started.",
                context=request.context,
                build_record_id=request.build_record_id,
            )

        started = time.monotonic()
        try:
            process = subprocess.Popen(
                _windows_command_line(argv),
                executable=str(executable),
                cwd=str(primary.parent),
                env=dict(self._configuration.environment),
                shell=False,
                stdin=subprocess.DEVNULL,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
        except OSError:
            return self._observation(
                executable_version=executable_version,
                process_started=False,
                duration_ms=_duration_ms(started),
            )

        timed_out = False
        try:
            process.wait(timeout=request.timeout.total_seconds())
        except subprocess.TimeoutExpired:
            timed_out = True
            _terminate_owned_process(process)

        duration_ms = _duration_ms(started)
        exit_code = process.returncode
        candidate_observed, candidate_unambiguous = _candidate_state(
            primary.parent, candidate_path
        )

        log_bytes, log_text = _read_log(
            log_path, self._configuration.max_log_bytes
        )
        verdict = "unavailable"
        error_count: int | None = None
        warning_count: int | None = None
        declared_inputs_only: bool | None = None
        if not timed_out and log_text is not None:
            result = _parse_result(log_text)
            if result is not None:
                error_count, warning_count = result
                verdict = "succeeded" if error_count == 0 else "failed"
                declared_inputs_only = _uses_only_declared_inputs(
                    log_text, self._workspace
                )

        try:
            self._workspace.verify_integrity()
        except BuildWorkspaceError as error:
            raise MetaEditorAdapterError("Build workspace integrity failed.") from error

        candidate_available = bool(
            not timed_out
            and verdict == "succeeded"
            and declared_inputs_only
            and candidate_observed
            and candidate_unambiguous
        )
        observation = self._observation(
            executable_version=executable_version,
            process_started=True,
            timed_out=timed_out,
            exit_code=exit_code,
            duration_ms=duration_ms,
            log_bytes=log_bytes,
            compiler_verdict=verdict,
            error_count=error_count,
            warning_count=warning_count,
            candidate_observed=candidate_observed,
            declared_inputs_only=declared_inputs_only,
            candidate_available=candidate_available,
        )
        if self._logger is not None:
            log_event(
                self._logger,
                logging.INFO,
                "build.provider.completed",
                "Build provider completed.",
                context=request.context,
                build_record_id=request.build_record_id,
            )
        return observation

    def _validated_executable(self) -> Path:
        path = self._configuration.executable
        try:
            if (
                path.suffix.lower() != ".exe"
                or path.is_symlink()
                or not path.is_file()
            ):
                raise MetaEditorAdapterError("MetaEditor executable is unavailable.")
            resolved = path.resolve(strict=True)
            with resolved.open("rb") as stream:
                digest = Sha256Digest(
                    hashlib.file_digest(stream, "sha256").hexdigest()
                )
        except OSError as error:
            raise MetaEditorAdapterError("MetaEditor executable is unavailable.") from error
        if digest != self._configuration.executable_digest:
            raise MetaEditorAdapterError("MetaEditor executable identity changed.")
        return resolved

    def _validated_primary(self) -> Path:
        if not self._workspace.members:
            raise MetaEditorAdapterError("Build workspace has no primary input.")
        primary = self._workspace.members[0].physical_path
        try:
            resolved = primary.resolve(strict=True)
            workspace_root = self._workspace.workspace_root.resolve(strict=True)
        except OSError as error:
            raise MetaEditorAdapterError("Primary build input is unavailable.") from error
        if (
            not resolved.is_relative_to(workspace_root)
            or resolved.suffix.lower() != ".mq5"
            or resolved.is_symlink()
            or not resolved.is_file()
        ):
            raise MetaEditorAdapterError("Primary build input is invalid.")
        return resolved

    def _observation(
        self,
        *,
        executable_version: str | None,
        process_started: bool,
        timed_out: bool = False,
        exit_code: int | None = None,
        duration_ms: int = 0,
        log_bytes: bytes | None = None,
        compiler_verdict: str = "unavailable",
        error_count: int | None = None,
        warning_count: int | None = None,
        candidate_observed: bool = False,
        declared_inputs_only: bool | None = None,
        candidate_available: bool = False,
    ) -> BuildProviderObservation:
        value = {
            "schema_name": "metaeditor-build-evidence",
            "schema_version": "0.1.0",
            "provider": "metaeditor",
            "executable_digest": str(self._configuration.executable_digest),
            "executable_version": executable_version,
            "process_started": process_started,
            "timed_out": timed_out,
            "exit_code": exit_code,
            "duration_ms": duration_ms,
            "log_encoding": "utf-16le" if log_bytes is not None else None,
            "log_digest": (
                hashlib.sha256(log_bytes).hexdigest()
                if log_bytes is not None
                else None
            ),
            "compiler_verdict": compiler_verdict,
            "error_count": error_count,
            "warning_count": warning_count,
            "candidate_observed": candidate_observed,
            "declared_inputs_only": declared_inputs_only,
        }
        _validate_provider_document(value)
        return BuildProviderObservation(
            SchemaReferencedPayload(_EVIDENCE_REF, value), candidate_available
        )


def _metaeditor_argv(
    executable: Path, primary: Path
) -> tuple[str, str, str]:
    for path in (executable, primary):
        if '"' in str(path):
            raise MetaEditorAdapterError("MetaEditor command path is invalid.")
    return str(executable), f'/compile:"{primary}"', "/log"


def _windows_command_line(argv: tuple[str, ...]) -> str:
    # MetaEditor requires this exact CreateProcess grammar. The fixed argv is
    # never passed to a command shell and contains no caller-supplied options.
    executable, *arguments = argv
    return " ".join((f'"{executable}"', *arguments))


def _read_log(path: Path, limit: int) -> tuple[bytes | None, str | None]:
    try:
        if path.is_symlink() or not path.is_file() or path.stat().st_size > limit:
            return None, None
        data = path.read_bytes()
    except OSError:
        return None, None
    if len(data) > limit or not data.startswith(b"\xff\xfe"):
        return None, None
    try:
        return data, data[2:].decode("utf-16le")
    except UnicodeDecodeError:
        return None, None


def _parse_result(text: str) -> tuple[int, int] | None:
    matches = list(_RESULT_PATTERN.finditer(text))
    if len(matches) != 1:
        return None
    return int(matches[0].group(1)), int(matches[0].group(2))


def _uses_only_declared_inputs(
    text: str, workspace: MaterializedBuildWorkspace
) -> bool:
    declared = {_path_key(member.physical_path) for member in workspace.members}
    observed = {
        _path_key(Path(match.group(1).strip()))
        for match in _INCLUDE_PATTERN.finditer(text)
    }
    return observed <= declared


def _path_key(path: Path) -> str:
    try:
        resolved = path.resolve(strict=False)
    except OSError:
        resolved = path.absolute()
    return os.path.normcase(str(resolved))


def _candidate_state(directory: Path, expected: Path) -> tuple[bool, bool]:
    try:
        observed = expected.is_file() and not expected.is_symlink()
        candidates = [
            path
            for path in directory.glob("*.ex5")
            if path.is_file() and not path.is_symlink()
        ]
    except OSError:
        return False, False
    return observed, observed and len(candidates) == 1 and candidates[0] == expected


def _terminate_owned_process(process: subprocess.Popen) -> None:
    try:
        process.terminate()
        try:
            process.wait(timeout=_TERMINATION_GRACE_SECONDS)
        except subprocess.TimeoutExpired:
            process.kill()
            process.wait(timeout=_TERMINATION_GRACE_SECONDS)
    except (OSError, subprocess.TimeoutExpired) as error:
        raise MetaEditorAdapterError("Owned MetaEditor process could not be stopped.") from error


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _validate_provider_document(document: dict[str, object]) -> None:
    try:
        validate_document(document)
    except ContractValidationError as error:
        raise MetaEditorAdapterError("MetaEditor provider document is invalid.") from error


def _read_windows_file_version(path: Path) -> str | None:
    """Read the fixed Windows file version without invoking another process."""

    if os.name != "nt":
        return None

    class _FixedFileInfo(ctypes.Structure):
        _fields_ = [
            ("signature", ctypes.c_uint32),
            ("structure_version", ctypes.c_uint32),
            ("file_version_ms", ctypes.c_uint32),
            ("file_version_ls", ctypes.c_uint32),
            ("product_version_ms", ctypes.c_uint32),
            ("product_version_ls", ctypes.c_uint32),
            ("file_flags_mask", ctypes.c_uint32),
            ("file_flags", ctypes.c_uint32),
            ("file_os", ctypes.c_uint32),
            ("file_type", ctypes.c_uint32),
            ("file_subtype", ctypes.c_uint32),
            ("file_date_ms", ctypes.c_uint32),
            ("file_date_ls", ctypes.c_uint32),
        ]

    try:
        version = ctypes.windll.version
        size = version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not version.VerQueryValueW(
            buffer, "\\", ctypes.byref(pointer), ctypes.byref(length)
        ):
            return None
        info = ctypes.cast(pointer, ctypes.POINTER(_FixedFileInfo)).contents
    except (AttributeError, OSError, ValueError):
        return None
    return ".".join(
        str(part)
        for part in (
            info.file_version_ms >> 16,
            info.file_version_ms & 0xFFFF,
            info.file_version_ls >> 16,
            info.file_version_ls & 0xFFFF,
        )
    )
