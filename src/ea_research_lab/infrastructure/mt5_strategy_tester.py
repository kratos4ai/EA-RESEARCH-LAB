"""Controlled MetaTrader 5 Strategy Tester execution adapter."""

from __future__ import annotations

import ctypes
import hashlib
import os
import subprocess
import tempfile
import time
from collections.abc import Mapping
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from types import MappingProxyType

from ea_research_lab.application.errors import ApplicationErrorCode
from ea_research_lab.application.execution import ExecutionRequest
from ea_research_lab.contracts import ContractValidationError, validate_document
from ea_research_lab.domain.execution import (
    CapturedExecutionOutput,
    ExecutionProviderObservation,
    ExecutionProviderVerdict,
)
from ea_research_lab.domain.provenance import SchemaReferencedPayload
from ea_research_lab.domain.values import (
    SchemaName,
    SchemaRef,
    SchemaVersion,
    Sha256Digest,
)


_CONFIGURATION_REF = SchemaRef(
    SchemaName("mt5-strategy-tester-configuration"), SchemaVersion(0, 2, 0)
)
_EXECUTION_REF = SchemaRef(
    SchemaName("mt5-strategy-tester-execution"), SchemaVersion(0, 1, 0)
)
_EVIDENCE_REF = SchemaRef(
    SchemaName("mt5-strategy-tester-evidence"), SchemaVersion(0, 1, 0)
)
_PROVIDER_NAMESPACE = "metatrader5.strategy-tester"
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
_TERMINATION_GRACE_SECONDS = 2.0


class Mt5StrategyTesterAdapterError(ValueError):
    """Safe rejection at the external Strategy Tester boundary."""

    code = ApplicationErrorCode.EXECUTION_PROVIDER_FAILED.value


@dataclass(frozen=True, slots=True)
class Mt5StrategyTesterConfiguration:
    """Explicit settings for the validated main-mode provider environment."""

    terminal_executable: Path
    terminal_digest: Sha256Digest
    data_root: Path
    environment: Mapping[str, str]
    terminal_mode: str
    expected_account_context: str
    max_output_bytes: int = 4_194_304

    def __post_init__(self) -> None:
        if (
            not isinstance(self.terminal_executable, Path)
            or not isinstance(self.data_root, Path)
            or not isinstance(self.terminal_digest, Sha256Digest)
            or not self.terminal_executable.is_absolute()
            or not self.data_root.is_absolute()
        ):
            raise Mt5StrategyTesterAdapterError("MT5 configuration is invalid.")
        if self.terminal_mode != "main" or self.expected_account_context != "demo":
            raise Mt5StrategyTesterAdapterError(
                "MT5 main-mode Demo context must be explicit."
            )
        if not isinstance(self.environment, Mapping):
            raise Mt5StrategyTesterAdapterError("MT5 environment is invalid.")
        environment = dict(self.environment)
        if any(
            key not in _ENVIRONMENT_KEYS
            or not isinstance(value, str)
            or not value
            for key, value in environment.items()
        ):
            raise Mt5StrategyTesterAdapterError("MT5 environment is invalid.")
        if type(self.max_output_bytes) is not int or self.max_output_bytes < 2:
            raise Mt5StrategyTesterAdapterError("MT5 output limit is invalid.")
        object.__setattr__(self, "environment", MappingProxyType(environment))
        _validate_provider_document(_plain_json(self.payload.value))

    @property
    def payload(self) -> SchemaReferencedPayload:
        return SchemaReferencedPayload(
            _CONFIGURATION_REF,
            {
                "schema_name": str(_CONFIGURATION_REF.name),
                "schema_version": str(_CONFIGURATION_REF.version),
                "provider": "metatrader5-strategy-tester",
                "terminal_executable": str(self.terminal_executable),
                "terminal_digest": str(self.terminal_digest),
                "terminal_mode": self.terminal_mode,
                "data_root": str(self.data_root),
                "expected_account_context": self.expected_account_context,
                "environment": dict(self.environment),
                "max_output_bytes": self.max_output_bytes,
            },
        )


@dataclass(frozen=True, slots=True)
class _ProcessObservation:
    started: bool
    timed_out: bool
    exit_code: int | None
    duration_ms: int
    ownership_established: bool
    owned_processes_stopped: bool | None


class Mt5StrategyTesterProvider:
    """Execute one request without deciding the final Run outcome."""

    def __init__(self, configuration: Mt5StrategyTesterConfiguration) -> None:
        if not isinstance(configuration, Mt5StrategyTesterConfiguration):
            raise Mt5StrategyTesterAdapterError("MT5 configuration is invalid.")
        self._configuration = configuration

    def execute(self, request: ExecutionRequest) -> ExecutionProviderObservation:
        if not isinstance(request, ExecutionRequest):
            raise Mt5StrategyTesterAdapterError("MT5 execution request is invalid.")
        configuration = self._configuration
        _verify_provider_environment(configuration)
        if request.environment_configuration != configuration.payload:
            raise Mt5StrategyTesterAdapterError(
                "Execution environment does not match the MT5 configuration."
            )
        execution = _execution_document(request)
        if _related_mt5_processes_present():
            raise Mt5StrategyTesterAdapterError(
                "Existing MT5 processes make execution ownership ambiguous."
            )
        parent = _workspace_parent(configuration.data_root)

        try:
            temporary = tempfile.TemporaryDirectory(
                prefix=f"{request.run_id}-", dir=parent
            )
        except OSError as error:
            raise Mt5StrategyTesterAdapterError(
                "Exclusive MT5 execution workspace could not be created."
            ) from error

        try:
            workspace = Path(temporary.name).resolve(strict=True)
            if workspace.parent != parent or _is_link_or_junction(workspace):
                raise Mt5StrategyTesterAdapterError(
                    "Exclusive MT5 execution workspace is unsafe."
                )
            artifact = workspace / "sut.ex5"
            _write_exact_artifact(artifact, request)
            report = workspace / "tester-report.htm"
            start_config = workspace / "tester.ini"
            _write_start_config(
                start_config,
                configuration.data_root,
                artifact,
                report,
                execution,
            )
            before = _snapshot_logs(configuration.data_root)
            process = _invoke_terminal(configuration, start_config, request)
            log_outputs, log_text, log_encoding = _capture_log_deltas(
                configuration.data_root,
                before,
                configuration.max_output_bytes,
            )
            report_output = _capture_file(
                report,
                configuration.max_output_bytes,
                "text/html",
            )
            outputs = (
                (() if report_output is None else (report_output,)) + log_outputs
            )
            report_observed = report_output is not None
            lowered = log_text.lower()
            config_loaded = (
                "successfully initialized from start config" in lowered
                if log_text
                else None
            )
            terminal_log_observed = any(
                output.provider_namespace == f"{_PROVIDER_NAMESPACE}.terminal-log"
                for output in log_outputs
            )
            tester_log_observed = any(
                output.provider_namespace == f"{_PROVIDER_NAMESPACE}.tester-log"
                for output in log_outputs
            )
            tester_completion_observed = any(
                marker in lowered
                for marker in (
                    "test passed",
                    "testing finished",
                    "test completed",
                    "final balance",
                )
            )
            if process.timed_out:
                verdict = ExecutionProviderVerdict.CANCELLED
                completion = "timeout"
            elif (
                report_observed
                and config_loaded is True
                and terminal_log_observed
                and tester_log_observed
                and tester_completion_observed
                and process.ownership_established
            ):
                verdict = ExecutionProviderVerdict.COMPLETED
                completion = "completed"
            elif "tester didn't start" in lowered or "test failed" in lowered:
                verdict = ExecutionProviderVerdict.FAILED
                completion = "failed"
            else:
                verdict = ExecutionProviderVerdict.INCONCLUSIVE
                completion = "ambiguous"

            evidence = {
                "schema_name": str(_EVIDENCE_REF.name),
                "schema_version": str(_EVIDENCE_REF.version),
                "provider": "metatrader5-strategy-tester",
                "terminal_digest": str(configuration.terminal_digest),
                "terminal_version": _read_windows_file_version(
                    configuration.terminal_executable
                ),
                "process_started": process.started,
                "timed_out": process.timed_out,
                "exit_code": process.exit_code,
                "duration_ms": process.duration_ms,
                "ownership_established": process.ownership_established,
                "owned_processes_stopped": process.owned_processes_stopped,
                "config_loaded": config_loaded,
                "report_observed": report_observed,
                "terminal_log_observed": terminal_log_observed,
                "tester_log_observed": tester_log_observed,
                "log_encoding": log_encoding,
                "completion": completion,
            }
            _validate_provider_document(evidence)
            return ExecutionProviderObservation(
                verdict,
                SchemaReferencedPayload(_EVIDENCE_REF, evidence),
                outputs,
            )
        finally:
            try:
                temporary.cleanup()
            except OSError as error:
                raise Mt5StrategyTesterAdapterError(
                    "Exclusive MT5 execution workspace cleanup failed."
                ) from error


def _execution_document(request: ExecutionRequest) -> Mapping[str, object]:
    definition = request.test_definition.value
    envelope = definition["execution_configuration"]
    try:
        schema_ref = SchemaRef.parse(envelope["schema_ref"])
        document = dict(envelope["value"])
    except (KeyError, TypeError, ValueError) as error:
        raise Mt5StrategyTesterAdapterError(
            "Test Definition execution configuration is invalid."
        ) from error
    if schema_ref != _EXECUTION_REF:
        raise Mt5StrategyTesterAdapterError(
            "Test Definition requires MT5 Strategy Tester execution 0.1.0."
        )
    _validate_provider_document(document)
    try:
        if date.fromisoformat(document["from_date"]) >= date.fromisoformat(
            document["to_date"]
        ):
            raise Mt5StrategyTesterAdapterError(
                "MT5 test date range must be increasing."
            )
    except (KeyError, TypeError, ValueError) as error:
        raise Mt5StrategyTesterAdapterError(
            "MT5 test date range is invalid."
        ) from error
    sut_inputs = definition["sut_inputs"]["value"]
    if not isinstance(sut_inputs, Mapping) or sut_inputs:
        raise Mt5StrategyTesterAdapterError(
            "The initial MT5 adapter supports only an empty SUT input payload."
        )
    return document


def _verify_provider_environment(
    configuration: Mt5StrategyTesterConfiguration,
) -> None:
    root = configuration.data_root
    executable = configuration.terminal_executable
    origin = root / "origin.txt"
    common = root / "config" / "common.ini"
    try:
        if (
            _is_link_or_junction(root)
            or not root.is_dir()
            or _is_link_or_junction(executable)
            or not executable.is_file()
            or _is_link_or_junction(origin)
            or not origin.is_file()
            or _is_link_or_junction(common)
            or not common.is_file()
        ):
            raise Mt5StrategyTesterAdapterError(
                "MT5 main-mode provider environment could not be verified."
            )
        expected_installation = executable.parent.resolve(strict=True)
        recorded_installation = Path(
            origin.read_bytes().removeprefix(b"\xff\xfe").decode("utf-16le").strip()
        ).resolve(strict=True)
        if os.path.normcase(str(recorded_installation)) != os.path.normcase(
            str(expected_installation)
        ):
            raise Mt5StrategyTesterAdapterError(
                "MT5 terminal and data root do not match."
            )
        common_text = common.read_bytes().removeprefix(b"\xff\xfe").decode(
            "utf-16le"
        )
        servers = [
            line.partition("=")[2].strip()
            for line in common_text.splitlines()
            if line.partition("=")[0].strip().casefold() == "server"
        ]
        if not servers or any("demo" not in server.casefold() for server in servers):
            raise Mt5StrategyTesterAdapterError(
                "MT5 Demo account context is unavailable."
            )
        with executable.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except (OSError, UnicodeError) as error:
        raise Mt5StrategyTesterAdapterError(
            "MT5 main-mode provider environment could not be verified."
        ) from error
    if digest != str(configuration.terminal_digest):
        raise Mt5StrategyTesterAdapterError("MT5 terminal identity changed.")


def _related_mt5_processes_present() -> bool:
    try:
        return any(
            image.casefold()
            in subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {image}", "/FO", "CSV", "/NH"],
                check=False,
                capture_output=True,
                text=True,
                errors="replace",
            ).stdout.casefold()
            for image in ("terminal64.exe", "metatester64.exe")
        )
    except OSError as error:
        raise Mt5StrategyTesterAdapterError(
            "MT5 process ownership preflight failed."
        ) from error


def _workspace_parent(root: Path) -> Path:
    parent = root / "MQL5" / "Experts" / "EAResearchLab"
    try:
        parent.mkdir(parents=True, exist_ok=True)
        if not parent.resolve(strict=True).is_relative_to(root.resolve(strict=True)):
            raise Mt5StrategyTesterAdapterError("MT5 workspace escapes its root.")
        _require_no_links(root, parent)
    except OSError as error:
        raise Mt5StrategyTesterAdapterError("MT5 workspace is unavailable.") from error
    return parent.resolve(strict=True)


def _write_exact_artifact(path: Path, request: ExecutionRequest) -> None:
    try:
        with path.open("xb") as stream:
            stream.write(request.artifact.content)
        with path.open("rb") as stream:
            digest = hashlib.file_digest(stream, "sha256").hexdigest()
    except OSError as error:
        raise Mt5StrategyTesterAdapterError("Artifact staging failed.") from error
    if digest != str(request.artifact.binary_digest):
        raise Mt5StrategyTesterAdapterError("Staged Artifact identity changed.")


def _write_start_config(
    path: Path,
    root: Path,
    artifact: Path,
    report: Path,
    execution: Mapping[str, object],
) -> None:
    expert = artifact.relative_to(root / "MQL5" / "Experts").with_suffix("")
    report_relative = report.relative_to(root)
    values = {
        "Expert": str(expert).replace("/", "\\"),
        "Symbol": execution["symbol"],
        "Period": execution["period"],
        "Model": execution["model"],
        "ExecutionMode": execution["execution_mode"],
        "FromDate": execution["from_date"].replace("-", "."),
        "ToDate": execution["to_date"].replace("-", "."),
        "Deposit": execution["deposit"],
        "Currency": execution["currency"],
        "Leverage": execution["leverage"],
        "Report": str(report_relative).replace("/", "\\"),
    }
    lines = [
        "[Common]",
        "ProxyEnable=0",
        "KeepPrivate=0",
        "NewsEnable=0",
        "CertInstall=0",
        "",
        "[Experts]",
        "AllowLiveTrading=0",
        "AllowDllImport=0",
        "Enabled=0",
        "",
        "[Tester]",
        *(f"{key}={value}" for key, value in values.items()),
        "Optimization=0",
        "ForwardMode=0",
        "ReplaceReport=0",
        "ShutdownTerminal=1",
        "UseLocal=1",
        "UseRemote=0",
        "UseCloud=0",
        "Visual=0",
        "",
    ]
    try:
        with path.open("x", encoding="utf-8", newline="") as stream:
            stream.write("\r\n".join(lines))
    except OSError as error:
        raise Mt5StrategyTesterAdapterError(
            "MT5 start configuration could not be created."
        ) from error


def _invoke_terminal(
    configuration: Mt5StrategyTesterConfiguration,
    start_config: Path,
    request: ExecutionRequest,
) -> _ProcessObservation:
    executable = configuration.terminal_executable
    if any('"' in str(path) for path in (executable, start_config)):
        raise Mt5StrategyTesterAdapterError("MT5 command path is invalid.")
    argv = (str(executable), f'/config:"{start_config}"')
    command_line = " ".join((f'"{argv[0]}"', *argv[1:]))
    started = time.monotonic()
    job = _WindowsOwnedJob()
    try:
        process = subprocess.Popen(
            command_line,
            cwd=configuration.terminal_executable.parent,
            env=dict(configuration.environment),
            shell=False,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            creationflags=subprocess.CREATE_NEW_PROCESS_GROUP,
        )
    except OSError:
        job.close()
        return _ProcessObservation(False, False, None, _duration_ms(started), False, None)

    try:
        try:
            job.assign(process.pid)
        except OSError as error:
            process.terminate()
            try:
                process.wait(timeout=_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=_TERMINATION_GRACE_SECONDS)
            raise Mt5StrategyTesterAdapterError(
                "MT5 process ownership could not be established."
            ) from error
        try:
            process.wait(timeout=request.timeout.total_seconds())
            return _ProcessObservation(
                True,
                False,
                process.returncode,
                _duration_ms(started),
                True,
                True,
            )
        except subprocess.TimeoutExpired:
            job.close()
            try:
                process.wait(timeout=_TERMINATION_GRACE_SECONDS)
            except subprocess.TimeoutExpired as error:
                raise Mt5StrategyTesterAdapterError(
                    "Owned MT5 process tree could not be stopped."
                ) from error
            return _ProcessObservation(
                True,
                True,
                process.returncode,
                _duration_ms(started),
                True,
                True,
            )
    finally:
        job.close()


def _snapshot_logs(root: Path) -> Mapping[Path, int]:
    paths = [root / "logs", root / "Tester"]
    snapshot: dict[Path, int] = {}
    try:
        for directory in paths:
            if not directory.exists():
                continue
            for path in directory.rglob("*.log"):
                if path.is_file() and not _is_link_or_junction(path):
                    snapshot[path.resolve(strict=True)] = path.stat().st_size
    except OSError as error:
        raise Mt5StrategyTesterAdapterError("MT5 log state is unsafe.") from error
    return snapshot


def _capture_log_deltas(
    root: Path,
    before: Mapping[Path, int],
    limit: int,
) -> tuple[tuple[CapturedExecutionOutput, ...], str, str | None]:
    after = _snapshot_logs(root)
    outputs: list[CapturedExecutionOutput] = []
    decoded: list[str] = []
    for path in sorted(after, key=str):
        offset = before.get(path, 0)
        if after[path] <= offset or after[path] - offset > limit:
            continue
        try:
            with path.open("rb") as stream:
                stream.seek(offset)
                content = stream.read(limit + 1)
        except OSError:
            continue
        if len(content) > limit or len(content) % 2:
            continue
        try:
            text = content.removeprefix(b"\xff\xfe").decode("utf-16le")
        except UnicodeDecodeError:
            continue
        namespace = (
            f"{_PROVIDER_NAMESPACE}.terminal-log"
            if path.is_relative_to(root / "logs")
            else f"{_PROVIDER_NAMESPACE}.tester-log"
        )
        outputs.append(
            CapturedExecutionOutput(content, "text/plain", provider_namespace=namespace)
        )
        decoded.append(text)
    return tuple(outputs), "\n".join(decoded), "utf-16le" if outputs else None


def _capture_file(
    path: Path, limit: int, media_type: str
) -> CapturedExecutionOutput | None:
    try:
        if (
            _is_link_or_junction(path)
            or not path.is_file()
            or path.stat().st_size > limit
        ):
            return None
        content = path.read_bytes()
    except OSError:
        return None
    if len(content) > limit:
        return None
    return CapturedExecutionOutput(
        content,
        media_type,
        provider_namespace=f"{_PROVIDER_NAMESPACE}.report",
    )


def _require_no_links(root: Path, path: Path) -> None:
    current = path
    while current != root:
        if _is_link_or_junction(current):
            raise Mt5StrategyTesterAdapterError("MT5 workspace uses an unsafe link.")
        current = current.parent


def _is_link_or_junction(path: Path) -> bool:
    return path.is_symlink() or bool(
        getattr(os.path, "isjunction", lambda candidate: False)(path)
    )


def _plain_json(value: object) -> object:
    if isinstance(value, Mapping):
        return {key: _plain_json(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_plain_json(item) for item in value]
    return value


def _validate_provider_document(document: dict[str, object]) -> None:
    try:
        validate_document(document)
    except ContractValidationError as error:
        raise Mt5StrategyTesterAdapterError(
            "MT5 provider document is invalid."
        ) from error


def _duration_ms(started: float) -> int:
    return max(0, int((time.monotonic() - started) * 1000))


def _read_windows_file_version(path: Path) -> str | None:
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
        size = ctypes.windll.version.GetFileVersionInfoSizeW(str(path), None)
        if not size:
            return None
        buffer = ctypes.create_string_buffer(size)
        if not ctypes.windll.version.GetFileVersionInfoW(str(path), 0, size, buffer):
            return None
        pointer = ctypes.c_void_p()
        length = ctypes.c_uint()
        if not ctypes.windll.version.VerQueryValueW(
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


class _WindowsOwnedJob:
    """Private kill-on-close ownership for this adapter's process tree."""

    _JOB_OBJECT_EXTENDED_LIMIT_INFORMATION = 9
    _JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE = 0x2000
    _PROCESS_TERMINATE = 0x0001
    _PROCESS_SET_QUOTA = 0x0100

    class _BasicLimit(ctypes.Structure):
        _fields_ = [
            ("PerProcessUserTimeLimit", ctypes.c_int64),
            ("PerJobUserTimeLimit", ctypes.c_int64),
            ("LimitFlags", ctypes.c_uint32),
            ("MinimumWorkingSetSize", ctypes.c_size_t),
            ("MaximumWorkingSetSize", ctypes.c_size_t),
            ("ActiveProcessLimit", ctypes.c_uint32),
            ("Affinity", ctypes.c_size_t),
            ("PriorityClass", ctypes.c_uint32),
            ("SchedulingClass", ctypes.c_uint32),
        ]

    class _IoCounters(ctypes.Structure):
        _fields_ = [(name, ctypes.c_uint64) for name in (
            "ReadOperationCount", "WriteOperationCount", "OtherOperationCount",
            "ReadTransferCount", "WriteTransferCount", "OtherTransferCount",
        )]

    class _ExtendedLimit(ctypes.Structure):
        pass

    _ExtendedLimit._fields_ = [
        ("BasicLimitInformation", _BasicLimit),
        ("IoInfo", _IoCounters),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]

    def __init__(self) -> None:
        if os.name != "nt":
            raise Mt5StrategyTesterAdapterError("MT5 execution requires Windows.")
        kernel32 = ctypes.windll.kernel32
        kernel32.CreateJobObjectW.restype = ctypes.c_void_p
        kernel32.OpenProcess.restype = ctypes.c_void_p
        self._kernel32 = kernel32
        self._handle = kernel32.CreateJobObjectW(None, None)
        if not self._handle:
            raise Mt5StrategyTesterAdapterError("MT5 process ownership failed.")
        limits = self._ExtendedLimit()
        limits.BasicLimitInformation.LimitFlags = self._JOB_OBJECT_LIMIT_KILL_ON_JOB_CLOSE
        if not kernel32.SetInformationJobObject(
            self._handle,
            self._JOB_OBJECT_EXTENDED_LIMIT_INFORMATION,
            ctypes.byref(limits),
            ctypes.sizeof(limits),
        ):
            self.close()
            raise Mt5StrategyTesterAdapterError("MT5 process ownership failed.")

    def assign(self, pid: int) -> None:
        process = self._kernel32.OpenProcess(
            self._PROCESS_TERMINATE | self._PROCESS_SET_QUOTA, False, pid
        )
        if not process:
            raise OSError("owned process could not be opened")
        try:
            if not self._kernel32.AssignProcessToJobObject(self._handle, process):
                raise OSError("owned process could not be assigned")
        finally:
            self._kernel32.CloseHandle(process)

    def close(self) -> None:
        handle = getattr(self, "_handle", None)
        if handle:
            self._kernel32.CloseHandle(handle)
            self._handle = None
