# Development

## Toolchain

EA Research Lab requires Python `>=3.14,<3.15`. The M1 environment and dependency lock were verified with Python 3.14.7.

The functional third-party dependencies are `jsonschema[format]`, the local
Visual Analytics client dependency `streamlit==1.60.0`, and the official local
protocol adapter SDK `mcp==2.0.0`. `setuptools` is used
only as the package build backend. Streamlit's transitive dependencies remain
locked but are not separately selected as project capabilities. The Python
standard library provides the test runner, local quality-check orchestration,
filesystem isolation, hashing, and direct process invocation used by the Phase
02 build pipeline.

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

## Local Visual Analytics

Launch the read-only Research workspace with an explicit existing database:

```powershell
python -m streamlit run apps/visual_analytics/app.py --server.address 127.0.0.1 -- --database '<path-to-lab.sqlite3>'
```

For controlled automation, `EA_RESEARCH_LAB_DATABASE` supplies the same
explicit local path when `--database` is absent. The application does not
discover databases and never defaults to RCP-001. It uses the read-only
`PlatformApi` composition; there are no Build, Run, transformation, or Analysis
controls. Streamlit session state retains only selected Run/Dataset/Analysis
identities and keyset cursor state. Dataset and Evidence content are not
exposed. The local server is a presentation transport for a trusted single-user
workstation, not a public Platform API and not a supported remote deployment.

## Local MCP adapter

M3 provides two explicit tools-only modes over `PlatformApi`. Launch
the local stdio server with an explicit existing database path:

```powershell
python -m apps.mcp_adapter --mode read-only --database '<path-to-lab.sqlite3>'
```

Command-capable mode exposes the same eight Queries plus exactly four
side-effecting Commands and requires explicit operational configuration:

```powershell
python -m apps.mcp_adapter --mode command-capable --database '<path-to-lab.sqlite3>' --build-workspace '<absolute-build-workspace>' --artifact-logical-name '<logical-name>' --artifact-version '<version>' --metaeditor-executable '<absolute-metaeditor64.exe>' --metaeditor-digest '<sha256>' --terminal-executable '<absolute-terminal64.exe>' --terminal-digest '<sha256>' --mt5-data-root '<absolute-mt5-data-root>'
```

Repeat `--metaeditor-external-root 'ALIAS=<absolute-path>'` only for explicitly
declared external build roots. Command execution is synchronous. Each Command
Tool invokes exactly one matching Platform API Command, performs no automatic
Query, chaining, retry, progress service, or background job, and may compile,
launch controlled Strategy Tester execution, or publish durable research state
as stated by its Tool description.

For a disposable Codex validation without changing global configuration, use
the current CLI's per-invocation MCP overrides. The following read-only pattern
was validated in Phase 09 M4; paths must be absolute and the database must be a
disposable copy when validating RCP-001:

```powershell
$python = '<absolute-project-.venv-python>'
$repository = '<absolute-repository-root>'
$database = '<absolute-disposable-database>'
codex exec --ephemeral --ignore-user-config --sandbox read-only -C $repository `
  -c "mcp_servers.ea_research_lab.command='$python'" `
  -c "mcp_servers.ea_research_lab.args=['-m','apps.mcp_adapter','--mode','read-only','--database','$database']" `
  -c "mcp_servers.ea_research_lab.cwd='$repository'" `
  '<read-only research request>'
```

Command-capable Codex configuration uses the same override mechanism and the
explicit command-capable server arguments documented above. Phase 09 M4
validated discovery only: it invoked no Command and used nonexistent
disposable provider paths so MetaEditor and MT5 could not start. Persistent
daily-use registration remains an operator choice; M4 wrote no global or
repository Codex configuration.

The protocol owns stdout; operational logs use stderr. The server does not
discover a database and does not default to RCP-001. Each tool invocation uses
a fresh UUIDv7 Request ID with caller label `mcp:local`. Read-only mode is the
default and composes the existing read-only Platform API. The explicit
`command-capable` mode uses the explicit operational Platform API composition.
The eight read tools map directly to the eight
existing Platform API Queries. Each list call returns one page, declares and
enforces page size `1..200`, and preserves its opaque cursor. Evidence is
metadata-only, Dataset payloads are absent, and inline Analysis content is
restricted to the existing bounded execution-core result. Resources, Prompts,
sampling, HTTP, and Codex configuration are absent. M3 portable validation
uses fake Platform API behavior and does not invoke MetaEditor or MT5.

Run the RCP-001 read-only MCP acceptance separately:

```powershell
python -m unittest tests.integration.test_mcp_rcp001 -v
```

This test calculates the canonical database SHA-256, copies the checkpoint to
a disposable directory, launches the real stdio server with the official MCP
SDK client, and progressively discovers all identities through the eight
Tools. It verifies the persisted Run context, execution summary, Datasets,
bounded Analysis, Evidence metadata, reproducibility, provider history, and
canonical provenance. It then proves the canonical database and disposable
copy remained byte-identical. Provider integration is disabled and no Build,
Run, transformation, or Analysis computation occurs.

Run the RCP-001 read-only Visual Analytics acceptance separately:

```powershell
python -m unittest discover -s tests/integration -p 'test_visual_analytics_rcp001.py' -v
```

This test hashes the canonical database, copies it to a disposable directory,
drives the normal Streamlit application and Platform API read flow, verifies
provider methods are not invoked, and confirms the canonical and copied files
remain byte-identical. It does not rerun Build, MT5 execution, transformation,
or Analysis.

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

The current runtime contains the Phase 01 foundation through the Phase 07
transport-neutral Platform API. Its four Commands build, execute, transform,
analyze, and publish through the existing application/Data Plane boundaries.
Its eight Queries provide bounded Run, Dataset, Analysis, and canonical
provenance projections after integrity-checked loads. SQLite remains behind the
Data Plane and bounded discovery adapters. Phase 08 adds only the local,
read-only Streamlit Research Overview client. There is no public Platform API,
arbitrary search, or persisted semantic projection. Phase 09 M1-M3 add the
local stdio MCP boundary, eight bounded Query Tools, and four explicitly
enabled Command Tools. The adapter adds no orchestration or research capability
beyond the existing Platform API.

Phase 04 report parsing is intentionally limited to the observed English
UTF-16LE-with-BOM Strategy Tester HTML shape and exact required labels.
Unsupported encoding, layout, localization, missing or duplicate fields,
malformed decimals/counts, and contradictory trade counts fail closed. The
parser consumes captured Raw Evidence bytes and never reopens the provider
filesystem.

The controlled persisted Platform API vertical remains limited to MetaEditor/MT5
`5.0.0.6104`, explicit main mode, an already provisioned Demo context, and the
disposable known-activity fixture. Enable exactly that opt-in proof with:

```powershell
$env:EA_RESEARCH_LAB_METAEDITOR = '<installation>\MetaEditor64.exe'
$env:EA_RESEARCH_LAB_METAEDITOR_INTEGRATION = '1'
$env:EA_RESEARCH_LAB_MT5_TERMINAL = '<installation>\terminal64.exe'
$env:EA_RESEARCH_LAB_MT5_DATA_ROOT = '<expected-main-mode-data-root>'
$env:EA_RESEARCH_LAB_MT5_CONTROLLED_ACTIVITY_FIXTURE = '1'
$env:EA_RESEARCH_LAB_MT5_INTEGRATION = '1'
python -m unittest tests.integration.test_mt5_strategy_tester.PlatformApiMt5IntegrationTests -v
```

The test uses disposable Build and SQLite workspaces and invokes the complete
real lifecycle through `PlatformApi`. It closes persistence, discards the
original runtime objects, constructs a fresh `PlatformApi`, and verifies all
eight Queries and canonical provenance without rerunning Build, execution,
Dataset transformations, or Analysis. It also confirms that no related provider
process remains.

Portable-mode tester success is not proven, EX5 recompilation is not assumed
byte-deterministic, and no deterministic provider replay guarantee is claimed.
Phase 02 dependency-discovery and build follow-ups, wheel packaging of external
schemas, and direct use of the transitively installed `referencing` package
remain non-blocking follow-ups.
