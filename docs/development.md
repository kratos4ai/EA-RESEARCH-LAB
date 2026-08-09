# Development

## Toolchain

EA Research Lab requires Python `>=3.14,<3.15`. The M1 environment and dependency lock were verified with Python 3.14.7.

The only functional third-party dependency in Phase 01 is `jsonschema[format]`. `setuptools` is used only as the package build backend. The Python standard library provides the test runner and local quality-check orchestration.

## Environment setup

Create and activate a project-local virtual environment:

```powershell
py -3.14 -m venv .venv
.\.venv\Scripts\Activate.ps1
```

On Command Prompt, activate it with:

```bat
.venv\Scripts\activate.bat
```

Install the exact locked environment, then install the project in editable mode without resolving dependencies again:

```text
python -m pip install -r requirements.lock
python -m pip install --no-build-isolation --no-deps --editable .
```

If PowerShell script execution prevents activation, invoke `.venv\Scripts\python.exe` explicitly for each command instead of changing the machine execution policy.

## Local quality gate

Run the complete local check with the project virtual environment active:

```text
python tools/check.py
```

The command verifies the Python 3.14 baseline and `uuid.uuid7()` availability, compiles the Python sources, and runs `unittest` discovery. A failing check returns a non-zero exit status.

Installing the `jsonschema[format]` extra does not activate format validation by itself. Schema validators must pass an explicit `FormatChecker`; the M1 negative test verifies this behavior.

## Configuration

Phase 01 configuration is immutable and limited to settings the foundation currently consumes:

| Setting | Environment variable | Default | Accepted values |
|---|---|---|---|
| Log level | `EA_RESEARCH_LAB_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| Log format | `EA_RESEARCH_LAB_LOG_FORMAT` | `json` | `json`, `text` |

Call `load_settings()` explicitly. Precedence is explicit arguments over environment variables over defaults. Parsing is strict and raises `ConfigurationError` with code `invalid_configuration`; rejected values are not repeated in the error message. Supplying an environment mapping makes tests deterministic without mutating process environment. Importing the configuration module reads no environment and causes no side effects.

The foundation does not load `.env`, YAML, TOML, remote configuration, or future provider/storage/API settings.

## Request context

`RequestContext` contains a typed request ID and an optional opaque caller/client identity. It is immutable, transport-neutral, and propagated explicitly. It does not define authentication, authorization, users, sessions, tenants, or audit policy, and it is never stored in thread-local or global context.

## Operational logging

Call `configure_logging()` explicitly to configure the `ea_research_lab` package logger. Configuration is idempotent, emits to stderr by default, uses JSON by default, and adds no handler during import. The optional text format remains structured as ordered `key=<JSON value>` pairs.

Operational events are emitted through `log_event()` with a controlled field set:

- required: UTC timestamp, level, logger, event, and message;
- optional: request ID, caller ID, run ID, artifact ID, dataset ID, analysis result ID, and application error code.

Event names use lowercase dot-separated segments. Correlation identifiers retain their typed domain representations. Application error details and internal causes are not logged automatically. The formatter ignores arbitrary record fields and does not automatically serialize configuration values, exception tracebacks, SUT inputs, opaque payloads, or raw evidence.

Operational logs describe platform operation and debugging. They are not Raw Evidence and are not future Audit Records. M5 introduces neither audit persistence nor an audit lifecycle.

The current Phase 01 foundation contains no provider, storage, API, analysis, UI, or MCP runtime implementation or scaffolding.
