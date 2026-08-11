# Development

## Toolchain

EA Research Lab requires Python `>=3.14,<3.15`. The M1 environment and dependency lock were verified with Python 3.14.7.

The only functional third-party dependency remains `jsonschema[format]`. `setuptools` is used only as the package build backend. The Python standard library provides the test runner, local quality-check orchestration, filesystem isolation, hashing, and direct process invocation used by the Phase 02 build pipeline.

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

The command verifies the Python 3.14 baseline and `uuid.uuid7()` availability, compiles the Python sources, and runs complete `unittest` discovery. The discovered suite includes schema/catalog validation and standard-library AST architecture checks. A failing check returns a non-zero exit status.

Installing the `jsonschema[format]` extra does not activate format validation by itself. Schema validators must pass an explicit `FormatChecker`; negative contract tests verify this behavior.

The portable gate does not require or invoke MetaEditor. The controlled provider gate is opt-in and separate:

```powershell
$env:EA_RESEARCH_LAB_METAEDITOR = '<absolute-path-to-MetaEditor64.exe>'
$env:EA_RESEARCH_LAB_METAEDITOR_INTEGRATION = '1'
python -m unittest discover -s tests\integration -p test_*.py -v
```

The provider gate requires an explicit executable path, stops when another MetaEditor process makes ownership ambiguous, and uses disposable strategy-neutral fixtures. It must never compile project EA/SUT source.

The controlled Strategy Tester integration is also opt-in and separate. The
currently supported provider environment is explicit main mode with a
separately supplied, known no-trading EX5 fixture and an already provisioned
Demo account context:

```powershell
$env:EA_RESEARCH_LAB_MT5_TERMINAL = '<installation>\terminal64.exe'
$env:EA_RESEARCH_LAB_MT5_DATA_ROOT = '<expected-main-mode-data-root>'
$env:EA_RESEARCH_LAB_MT5_ARTIFACT = '<controlled-fixture>\fixture.ex5'
$env:EA_RESEARCH_LAB_MT5_CONTROLLED_ARTIFACT = '1'
$env:EA_RESEARCH_LAB_MT5_INTEGRATION = '1'
python -m unittest tests.integration.test_mt5_strategy_tester -v
```

The adapter invokes `terminal64.exe /config:"<tester.ini>"` without `/portable`.
It verifies the configured executable digest, checks the data root's
`origin.txt` association with that installation, and requires an existing Demo
server context in provider configuration. It never discovers an installation,
copies account databases, or handles credentials. Portable-mode successful
execution remains unsupported until a portable tester account is deliberately
provisioned and observed.

The main-mode data root is provider-owned mutable state. MT5 may update its
account, agent, server, settings, and terminal files during normal operation;
the Lab neither snapshots nor restores them. The adapter creates only an
exclusive per-Run directory below `MQL5/Experts/EAResearchLab`, stages the exact
accepted Artifact bytes as `sut.ex5`, verifies its SHA-256, captures bounded
report/log deltas, and removes only that owned directory. Live Expert trading
and DLL imports, optimization, visual mode, and remote/cloud agents are disabled
in the generated tester configuration.

On terminal build `5.0.0.6104`, the Windows list-to-command-line conversion was
observed to add a trailing quote to a spaced `/config:` path. The adapter
therefore emits the fixed MetaTrader command-line grammar directly while still
using `shell=False`; callers cannot add arguments. Terminal and tester logs
were observed as UTF-16LE. A controlled main-mode Demo execution completed in
12.5 seconds with process exit code `0`, produced a 22,952-byte report, preserved
the staged Artifact digest, and left no terminal or tester process. Provider
success nevertheless requires report, terminal and tester logs, a loaded start
configuration, a tester completion marker, and established process ownership;
the exit code alone is not success. Provider observation is not a final Run
outcome.

## Configuration

Platform configuration is immutable and currently limited to settings the foundation consumes:

| Setting | Environment variable | Default | Accepted values |
|---|---|---|---|
| Log level | `EA_RESEARCH_LAB_LOG_LEVEL` | `INFO` | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL` |
| Log format | `EA_RESEARCH_LAB_LOG_FORMAT` | `json` | `json`, `text` |

Call `load_settings()` explicitly. Precedence is explicit arguments over environment variables over defaults. Parsing is strict and raises `ConfigurationError` with code `invalid_configuration`; rejected values are not repeated in the error message. Supplying an environment mapping makes tests deterministic without mutating process environment. Importing the configuration module reads no environment and causes no side effects.

The foundation does not load `.env`, YAML, TOML, remote configuration, or storage/API settings. Phase 02 MetaEditor configuration is a separate explicit, immutable provider value containing the executable identity, approved environment subset, bounded log size, and optional logical external-root mappings. No machine-specific provider path is a committed default.

## Request context

`RequestContext` contains a typed request ID and an optional opaque caller/client identity. It is immutable, transport-neutral, and propagated explicitly. It does not define authentication, authorization, users, sessions, tenants, or audit policy, and it is never stored in thread-local or global context.

## Operational logging

Call `configure_logging()` explicitly to configure the `ea_research_lab` package logger. Configuration is idempotent, emits to stderr by default, uses JSON by default, and adds no handler during import. The optional text format remains structured as ordered `key=<JSON value>` pairs.

Operational events are emitted through `log_event()` with a controlled field set:

- required: UTC timestamp, level, logger, event, and message;
- optional: request ID, caller ID, Build Record ID, run ID, artifact ID, dataset ID, analysis result ID, and application error code.

Event names use lowercase dot-separated segments. Correlation identifiers retain their typed domain representations. Application error details and internal causes are not logged automatically. The formatter ignores arbitrary record fields and does not automatically serialize configuration values, exception tracebacks, SUT inputs, opaque payloads, or raw evidence.

Operational logs describe platform operation and debugging. They are not Raw Evidence and are not future Audit Records. Phase 02 introduces neither audit persistence nor an audit lifecycle and does not log source bytes, Artifact bytes, compiler logs, provider payloads, or physical paths automatically.

The current runtime contains the Phase 01 foundation, the Phase 02 Build and
Artifact pipeline, and the Phase 03 in-memory Run and Evidence workflow over the
controlled MT5 Strategy Tester adapter. The application finalizes a Run and
seals bounded captured outputs as immutable Raw Evidence without persistence.
It contains no Data Plane runtime, Platform API, analysis, UI, or MCP
implementation or scaffolding.

Phase 03 is complete. Its controlled provider validation is limited to the
currently tested MT5 version in explicit main mode with a previously provisioned
Demo context. Portable-mode tester success is not proven, EX5 recompilation is
not assumed byte-deterministic, execution and evidence remain in memory, and no
deterministic replay guarantee or durable persistence is claimed. Phase 02
dependency-discovery and build follow-ups, wheel packaging of external schemas,
and direct use of the transitively installed `referencing` package remain
non-blocking follow-ups.
