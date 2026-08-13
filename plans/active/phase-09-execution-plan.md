# Phase 09 — MCP Adapter Execution Plan

- Status: Completed
- Scope: Completed Phase 09 implementation through M4 only
- Baseline: completed Phase 08 at `049c161d8b36c5e3feb6afc4620f8b1aaf3c35a3`
- Runtime: Python `>=3.14,<3.15`
- Git policy: no milestone commits; one consolidated Phase 09 commit only after
  M1–M4 are implemented, reviewed, and approved

## 1. Objective

Add the smallest local MCP protocol adapter over the existing `PlatformApi`.
The adapter translates MCP calls into the existing typed Query or Command and
serializes the existing result or safe error. It owns no research, analytical,
provider, persistence, provenance, or strategy semantics.

```text
MCP client
    -> local stdio MCP adapter
    -> PlatformApi
    -> existing application/domain/infrastructure
```

The phase adds no research capability and does not change an existing
application operation count.

## 2. Current PlatformApi Boundary

The source-of-truth surfaces at the Phase 08 baseline are:

| Surface | Operations |
|---|---:|
| `DataPlane` | 8 |
| `ResearchQueryPort` | 5 |
| `PlatformCommands` | 4 |
| `PlatformQueries` | 8 |
| `PlatformApi` | 12 |

After composition, MCP code may import and invoke `PlatformApi` and the typed
request/result values needed at that boundary. It must not access
`DataPlane`, `ResearchQueryPort`, `PlatformQueries`, `PlatformCommands`,
SQLite, providers, transformers, Analysis functions, or evidence storage.

The existing eight Queries are sufficient for progressive read-only research.
The four Commands are sufficient for explicit command exposure. A missing use
case must remain blocked or deferred rather than be implemented behind the API.

Known limitation: `ApplicationErrorCode` currently has no dedicated
`not_found` member. Phase 09 must preserve the exact application error emitted
by `PlatformApi`; it must not infer a new error category in the adapter. A
future change to that taxonomy requires separate approval if evidence shows it
is essential.

## 3. MCP Technology Recommendation

Use the official Python SDK package `mcp`, its stable 2.x `MCPServer` API, and
no unofficial MCP framework. The standard library cannot implement MCP
protocol negotiation, schemas, framing, lifecycle, and client interoperability
without creating a second protocol implementation that the Lab would have to
maintain.

The implementation baseline should pin `mcp==2.0.0` in `requirements.in` and
the resolved lock. This is the current stable release, requires Python 3.10 or
newer, and publishes Python 3.14 support. M1 must install the proposed pin in a
disposable environment first and run a Python 3.14 import/stdio/in-memory-client
smoke test before modifying the project dependency files. A failed probe blocks
implementation and triggers dependency review; it does not justify choosing a
second framework.

Install plain `mcp`, not the `cli` extra: the adapter can run its own module and
the SDK client can test it. The optional developer CLI and MCP Inspector are not
required by the authoritative gate. The lock review must record all transitives;
the SDK has a materially larger footprint than the standard library and brings
protocol types, validation, async/transport, HTTP-stack, telemetry, and Windows
support dependencies even though Phase 09 uses only stdio. No additional test
framework is proposed; retain `unittest`.

## 4. Transport Decision

Phase 09 uses local stdio only.

| Criterion | stdio | Streamable HTTP |
|---|---|---|
| Local Codex use | Direct child process support | Requires a listening service |
| Exposure | No network listener | Local network endpoint and HTTP policy |
| Lifecycle | Client owns one child process | Separate server lifecycle |
| Configuration | Executable plus argv/environment | URL, host, port, server lifecycle |
| Security | Existing local process/filesystem permissions | Adds network/auth concerns |
| Testing | SDK in-memory client plus stdio subprocess | Adds HTTP integration surface |

No current requirement warrants HTTP, so no public/local HTTP server,
authentication service, TLS, reverse proxy, or cloud deployment enters the
phase. Protocol messages use stdin/stdout exclusively; operational logging uses
stderr so it cannot corrupt the MCP stream. The client owns start, stop, and
termination of the child server process.

## 5. MCP Capability Mapping

### Tools versus Resources

Represent all twelve Phase 09 capabilities as MCP tools. The Query surface is
parameterized, paginated, model-invoked, and already returns bounded semantic
projections. Tools provide one consistent validation, error, RequestContext,
and structured-result path. Resources would duplicate stable-identity lookup,
would not simplify paginated discovery, and would add a second public mapping.

Phase 09 exposes no Resources and no duplicate Tool/Resource capability.
Prompts, model sampling, subscriptions, and progress notifications are also not
required.

Names use lowercase snake case with explicit research nouns. Query tools carry
read-only annotations; Command tools carry mutating/destructive semantics where
the SDK supports standard annotations. Annotations are descriptive and never
replace server-side mode enforcement.

### Eight Query tools

| MCP tool | Exact PlatformApi call | Inputs | Bounded output |
|---|---|---|---|
| `list_research_runs` | `list_research_runs` | `limit`, optional opaque `cursor` | Run summaries and `next_cursor` |
| `get_research_run` | `get_research_run` | `run_id` | Run detail, experiment context, lifecycle, reproducibility, runtime metadata |
| `list_run_evidence_objects` | `list_run_evidence_objects` | `run_id`, `manifest_id`, `limit`, optional cursor | Evidence metadata only and `next_cursor` |
| `list_run_datasets` | `list_run_datasets` | `run_id`, `limit`, optional cursor | Dataset summaries and `next_cursor` |
| `get_dataset` | `get_dataset` | `dataset_id` | Semantic detail only; no generic payload |
| `list_dataset_analyses` | `list_dataset_analyses` | `dataset_id`, `limit`, optional cursor | Analysis summaries and `next_cursor` |
| `get_analysis` | `get_analysis` | `analysis_result_id` | Existing bounded supported result only |
| `get_canonical_chain` | `get_canonical_chain` | `build_record_id`, `run_id`, `analysis_result_id` | Existing verified canonical projection |

List inputs construct the existing `PageRequest`, retaining its `1..200`
validation. The adapter forwards a cursor unchanged, never decodes it, never
uses OFFSET, never fetches a second page implicitly, and never computes totals.

### Four Command tools

| MCP tool | Exact PlatformApi call | Existing request |
|---|---|---|
| `build_artifact` | `build_artifact` | `BuildRequest` |
| `execute_run` | `execute_run` | `ExecuteRunCommandRequest` |
| `transform_evidence` | `transform_evidence` | `TransformEvidenceCommandRequest` |
| `analyze_datasets` | `analyze_datasets` | `AnalyzeDatasetsCommandRequest` |

The protocol input is an explicit field-for-field representation from which the
existing typed request is constructed. It is not a second domain model. A
Command handler performs exactly one corresponding `PlatformApi` call. It does
not retry, chain Commands, poll, compensate, or call a provider. In particular,
there is no complete-pipeline tool.

Build source paths remain fields accepted by the existing `BuildRequest`. The
adapter passes them through typed construction and performs no independent
file read, directory listing, write, or shell execution.

## 6. Serialization and Error Model

Keep explicit allow-listed serializer functions in the adapter, covered by
tests for every result type exposed by the current milestone. They convert only
already-returned PlatformApi values into JSON-compatible structured content:

- typed entity IDs and SHA-256 digests: their exact strings;
- `Decimal`: canonical decimal string, never binary float;
- `UtcTimestamp`: its existing UTC string representation;
- dates: ISO `YYYY-MM-DD` strings;
- enums: their stable string values;
- schema references and definition versions: exact strings;
- tuples/mappings: JSON arrays/objects while preserving order;
- unavailable optional values: JSON `null`;
- opaque cursors: unchanged strings.

Do not serialize arbitrary objects with `__dict__`, `repr`, or generic JSON
fallbacks. Do not expose exception causes, tracebacks, SQL, local paths,
credentials, provider diagnostics, or raw content.

Malformed MCP inputs remain protocol/input-validation errors. A safe
`ApplicationError` returned by a Command is emitted as a tool execution error
with its existing `code`, safe `message`, safe `details`, and `request_id`.
Safe exceptions raised by Queries are mapped thinly from the existing
application/Data Plane error code and sanitized message. Unknown exceptions
become one generic internal tool error and are logged only through existing
operational logging. The adapter adds no independent error taxonomy.

## 7. RequestContext and Audit Model

Each tool call creates exactly one `RequestContext`:

- `request_id`: a new typed UUIDv7 `RequestId` generated by the existing
  identity helper;
- `caller_id`: a bounded, trimmed opaque local label supplied by server
  composition, defaulting to `mcp:local` and configurable as a non-secret
  local value when the host provides a stable client label.

Do not treat MCP session IDs, transport request IDs, or protocol metadata as
authenticated identity. Do not place tool arguments in `caller_id`. Command
request context is server-owned; client-supplied serialized command input must
not override it. Existing PlatformApi/application audit events remain
authoritative. MCP may log safe protocol operation/lifecycle events to stderr,
but creates no separate audit model or persistence.

## 8. Read-only and Command-capable Operation

The server requires two explicit local inputs: an existing database path and
mode (`read-only` by default, or `command-capable`). No database discovery or
RCP-001 default is allowed.

Read-only composition reuses `compose_read_only_platform`. Only the eight Query
tools are registered/advertised. Defense in depth retains the existing
`_ReadOnlyCommands`, and tests invoke all four Command paths against read-only
composition to prove failure before side effects. Hidden descriptions alone are
not a security boundary.

Command-capable mode must be selected explicitly at launch and uses an explicit
composition root built from the same concrete workflows already proven by
PlatformApi integration. Required MetaEditor/MT5/provider configuration remains
existing explicit local configuration; no discovery, credentials model, DI
container, registry, or command enablement by default is added. If a coherent
production composition cannot be formed from current concrete values without
inventing policy, M3 stops and reports the missing composition decision rather
than bypassing PlatformApi.

Command descriptions must state their side effects. Client consent/approval is
also configured in Codex, with query tools read-only and command tools requiring
an appropriate prompt policy. Host approval is defense in depth; server mode is
the authoritative availability boundary. Automatic retries are absent from
both handler code and server instructions.

## 9. M1 — MCP Contract and Transport Design

- Status: Completed

### Objective

Establish and verify the protocol boundary without exposing the complete
research surface.

### Inputs

- ADR-0002 and ADR-0005;
- architecture principles P02, P12, P13, P14, and P19;
- current `PlatformApi`, typed request/results, error model, RequestContext,
  composition, configuration, and logging;
- official MCP 2.x specification and Python SDK documentation;
- official Codex MCP configuration documentation.

### Expected files/modules

- `apps/mcp_adapter/__main__.py`: guarded stdio entry point and minimal
  database/mode parsing;
- `apps/mcp_adapter/server.py`: `MCPServer` construction, the single bounded
  `list_research_runs` tool, RequestContext creation, and safe error mapping;
- `apps/mcp_adapter/serialization.py`: explicit allow-listed result/error
  serialization;
- `tests/test_mcp_adapter.py`;
- `tests/architecture/test_mcp_adapter.py`;
- dependency and lock updates for exactly one direct MCP dependency;
- affected architecture/development documentation.

Exact file separation may be reduced if implementation remains clearer in
fewer files; no generic framework or reusable core MCP helper is expected.

### Implementation sequence

1. Probe exact `mcp==2.0.0` installation and minimal SDK API on Python 3.14 in
   a disposable environment.
2. Add the exact dependency and lock only after the probe passes.
3. Implement explicit JSON-safe serialization and safe error mapping.
4. Implement minimal config and composition selection.
5. Construct a stdio `MCPServer` with instructions that state boundedness,
   read-only default, no retries, and no autonomous research.
6. Add one representative no-side-effect contract tool only if needed to prove
   the boundary; complete Query exposure belongs to M2.

### Tests and acceptance

- Python 3.14 import and stdio smoke test succeeds;
- SDK in-memory `Client(server)` test proves initialization, discovery, schema,
  invocation, and safe failure without Codex or MT5;
- mapping tests preserve Decimal, timestamp, ID, digest, enum, null, and cursor;
- stdout contains protocol traffic only and operational logs use stderr;
- read-only and command-capable modes are explicit and immutable;
- architecture tests prove the adapter is outside core and imports no forbidden
  boundary;
- no PlatformApi operation or schema changes.

### Out of scope

Complete Query/Command exposure, Resources, Prompts, HTTP, authentication,
sampling, notifications, and provider execution.

### M1 implementation record

The disposable Python 3.14.7 probe installed `mcp==2.0.0`, imported the
stable `MCPServer`, `ClientSession`, and stdio client APIs, completed a real
child-process handshake, discovered and called one probe tool, and shut down
cleanly before the repository dependency files changed. The implemented
adapter uses that same `MCPServer` API and local stdio transport.

M1 exposes only `list_research_runs`. Each call creates a new UUIDv7
`RequestId` with caller ID `mcp:local`, constructs one `PageRequest`, invokes
one `PlatformApi` operation, and returns one page without following the opaque
cursor. Read-only is the default mode. `command-capable` must be selected
explicitly but is rejected by the M1 entry point because M3 has not supplied a
command-capable composition or registered Command tools.

## 10. M2 — Read-only MCP Queries

- Status: Completed

### Objective

Expose all eight existing Queries as bounded tools through read-only
`PlatformApi` composition.

### Expected work

- register the eight Query tools listed in section 5;
- construct one RequestContext per invocation;
- serialize only existing semantic projections;
- preserve keyset cursors and page bounds;
- map safe errors without internal diagnostics;
- add portable in-memory SDK and disposable SQLite integration tests.

### Tests and acceptance

- discovery exposes exactly eight tools in read-only mode and no Commands;
- each tool invokes exactly one matching PlatformApi Query;
- first/continuation pages remain bounded and deterministic;
- cursors remain opaque and wrong-bound cursors fail closed;
- Evidence is metadata-only, Dataset payload is unavailable, and Analysis is
  limited to the current bounded result;
- canonical provenance delegates to `get_canonical_chain`;
- empty, failed, cancelled, partial-evidence, unsupported-result, integrity,
  invalid-input, and safe-error cases remain bounded and intelligible;
- portable end-to-end tests use only disposable deterministic data.

### Out of scope

Commands, RCP recomputation, Evidence content, arbitrary Dataset/Analysis JSON,
Resources, Prompts, and research calculations.

### M2 implementation record

Read-only discovery now exposes exactly the eight Query tools defined in
section 5. Each handler creates a fresh UUIDv7 `RequestId`, validates typed
identifiers and pagination, makes exactly one corresponding `PlatformApi`
call, and invokes one explicit result serializer. List tools return one page
and preserve `next_cursor` unchanged. The discovered schemas declare integer
page size bounds `1..200`; the existing `PageRequest` enforces the same rule at
runtime.

The Dataset mapping contains only metadata and the existing optional
execution-summary projection. Evidence contains metadata only. Analysis
content is inline only for the existing allow-listed
`execution-core-analysis-result/0.1.0`; every output field is copied
explicitly and decimal strings remain exact. Canonical provenance is a direct
serialization of one `PlatformApi.get_canonical_chain` result.

An official SDK `ClientSession` navigated from no known research identities
through the local stdio server against a disposable read-only copy of RCP-001.
It discovered the Run, experiment context, three Datasets, one Analysis,
three Evidence descriptors, and the verified canonical chain. The canonical
database SHA-256 remained
`f95b223be6351dd51272a921d4ec0841bc2b29d710b2ebb04ef0fcbd6926c495`
before and after. No Build, execution, transformation, Analysis computation,
MetaEditor, or MT5 operation ran.

## 11. M3 — MCP Commands

- Status: Completed

### Objective

Expose exactly the four existing Commands only in explicit command-capable
mode, without new orchestration.

### Expected work

- register the four Command tools listed in section 5 only for
  command-capable composition;
- translate field-for-field inputs into existing typed requests with the
  server-created RequestContext;
- retain existing durable-publication success semantics and safe errors;
- document and annotate side effects and required client approval;
- build the explicit normal PlatformApi composition from existing workflows
  and provider configuration.

### Tests and acceptance

- command-capable discovery exposes exactly twelve tools;
- read-only discovery still exposes exactly eight;
- spies prove one tool call invokes exactly one corresponding PlatformApi
  Command, with no retry or implicit sibling Command;
- invalid input fails before the PlatformApi call;
- Command failure is not reported as success;
- read-only composition blocks all four Commands before provider, filesystem,
  or persistence side effects;
- portable tests use deterministic fakes/disposable data and require no MT5;
- existing controlled PlatformApi provider integration remains the evidence for
  real MetaEditor/MT5 mechanics.

### Out of scope

Pipeline commands, cancellation/job APIs not already present, background
workers, provider CLI inputs, optimizer tools, and uncontrolled real research.

### M3 implementation record

Command-capable mode registers exactly the existing four Commands in addition
to the eight Queries. Each handler creates a fresh `RequestContext`, translates
explicit transport values into the existing typed application request, invokes
exactly one matching `PlatformApi` operation, performs no Query enrichment or
retry, and serializes only the bounded Command result. Failed or cancelled
research outcomes remain normal results when durable publication succeeds; an
application `failure` remains a sanitized Tool error.

The explicit `compose_command_platform` root joins the already-qualified
MetaEditor, MT5, Dataset, Analysis, SQLite, and semantic components behind one
`PlatformApi`. Launch configuration supplies the existing database, workspace,
provider executable paths and digests, artifact labels, MT5 data root, and
optional external-root aliases. No machine discovery or hard-coded path was
added. Portable in-memory and real-stdio SDK tests use a fake `PlatformApi`;
M3 ran no MetaEditor, MT5, RCP-001, or Codex integration.

## 12. M4 — Codex Integration Validation and Closure

- Status: Completed

### Objective

Validate the actual local stdio server with an MCP client and Codex-compatible
configuration, then close Phase 09 without adding capability.

### Expected work

- use the SDK's real stdio client to launch the server as a subprocess and test
  discovery, invocation, pagination, errors, shutdown, and stderr logging;
- configure a local Codex MCP server with an absolute project `.venv` Python
  path, `-m apps.mcp_adapter`, explicit database-copy path/mode environment,
  working directory, startup/tool timeouts, and tool approval policy;
- validate actual Codex discovery and read navigation where the local client is
  available;
- validate RCP-001 through a disposable read-only database copy;
- update documentation/status and run the authoritative portable gate,
  `compileall`, `pip check`, lock checks, `git diff --check`, and the dedicated
  MCP/RCP acceptance.

Codex supports local stdio servers through shared `config.toml` configuration
and `codex mcp add`. Prefer project-scoped `.codex/config.toml` only when the
repository is trusted; do not commit machine-specific absolute paths. Verify
with `codex mcp list` and the client's MCP capability list.

M4 does not require a new real MetaEditor/MT5 execution. Existing controlled
PlatformApi integration already proves provider workflows; mapping/spy tests
prove MCP-to-Command correspondence. If an optional command smoke test is
explicitly approved later, it must use a disposable controlled fixture and may
not mutate or rerun RCP-001.

### Acceptance

- an actual stdio client discovers and calls the expected tools;
- Codex can discover RCP-001 and progressively inspect Run, Datasets, Analysis,
  Evidence metadata, reproducibility, and canonical provenance without prior
  internal IDs;
- the canonical RCP-001 SHA-256 is identical before and after validation;
- no Build, execution, transformation, or Analysis recomputation occurs;
- child-process shutdown leaves no adapter process;
- Phase 09 documentation and architecture enforcement reflect implemented
  behavior; no Phase 10 work appears.

### M4 implementation record

Codex CLI `0.147.0-alpha.6.5` validated the adapter through real local stdio
sessions. Both sessions used `codex exec --ephemeral --ignore-user-config`,
per-invocation `mcp_servers` configuration overrides, the absolute project
`.venv` Python executable, and the repository root as `cwd`; no global or
repository Codex configuration was written.

The read-only session began without research identities, discovered exactly
eight Query Tools, and progressively navigated a disposable RCP-001 copy. It
retrieved the persisted experiment context, execution summary, three Dataset
products, bounded Analysis result, three Evidence descriptors,
`best_effort` reproducibility, recorded MetaEditor runtime, and canonical
provenance. A malformed Run ID returned a bounded `invalid_identifier` error.
List results exposed `next_cursor` and no auto-pagination occurred.

The command-capable session discovered exactly twelve Tools after one harmless
read-only query. Codex correctly distinguished eight Queries from four
Commands and found every Command description explicit about its controlled
side effects. It invoked no Command. Its provider paths deliberately referenced
nonexistent disposable placeholders, so MetaEditor and MT5 could not be
started. Both disposable databases and the canonical RCP-001 database retained
the expected SHA-256. No research state was created. Phase 09 is completed and
Phase 10 has not started.

## 13. Testing Strategy

### A. Pure mapping

Standard-library unit tests cover every supported input/result/error mapping,
including exact Decimal strings, timestamps, IDs, digests, enums, nulls,
cursors, invalid inputs, and sanitized failures.

### B. MCP server contract

Use the official SDK's in-memory client against the server object. Verify tool
discovery, generated input/output schemas, annotations, output shape,
validation, safe errors, tool counts, and mode-dependent availability. No
separate MCP testing dependency is required.

### C. Portable PlatformApi integration

Compose the adapter over deterministic/disposable PlatformApi data. Exercise
all Query tools and Command mapping without MetaEditor or MT5. Verify one-call
mapping, audit context, pagination, bounded content, and command denial.

### D. Real local integration

Use an official SDK stdio client as the repeatable automated proof and an
actual Codex configuration as the local acceptance proof. Use RCP-001 only for
read operations. Codex is not required by the portable gate, so CI remains
independent of an installed host application.

## 14. RCP-001 Acceptance Strategy

1. Hash `data/rcp-001/lab.sqlite3` without opening it writable.
2. Copy it to a disposable workspace.
3. Start the adapter in read-only mode against the copy.
4. Discover the Run; derive subsequent IDs from bounded responses.
5. Verify the persisted EURUSD/H1 context, 135/43/92 execution facts, USD 2.63
   net profit, supported Analysis metrics, three Datasets, three Evidence
   descriptors, `best_effort` reasons, and verified canonical provenance.
6. Assert all provider/Command paths remain unused.
7. Close the server, remove the copy, and verify the canonical digest again.

Acceptance expectations live in integration tests, never MCP runtime code.

## 15. Architecture Enforcement

At closure, AST/contract tests must prove:

- core remains exactly `domain`, `application`, `contracts`, and
  `infrastructure`;
- `apps/mcp_adapter` remains outside core;
- adapter runtime depends on `PlatformApi`, typed boundary values, SDK, and
  explicit composition only;
- no MCP module imports SQLite adapters, `DataPlane`, `ResearchQueryPort`,
  `PlatformQueries`, `PlatformCommands`, providers, transformers, or Analysis
  functions after composition;
- tool counts are 8 read-only and 12 command-capable;
- DataPlane/ResearchQueryPort/Commands/Queries/API counts remain 8/5/4/8/12;
- every handler maps to exactly one approved PlatformApi operation;
- no generic file, directory, shell, Python, Evidence-content, Dataset-content,
  graph, optimizer, or strategy-specific tool exists;
- no HTTP listener, MCP Resource, Prompt, sampling, subscription, or autonomous
  loop exists;
- read-only mode blocks Commands before side effects;
- serialization never turns Decimal into float;
- list calls retain explicit bounded `PageRequest` inputs and opaque cursors;
- stdout logging cannot corrupt stdio.

## 16. Expected Files and Modules

Minimum expected additions/changes during implementation:

```text
apps/mcp_adapter/__main__.py
apps/mcp_adapter/server.py
apps/mcp_adapter/mapping.py
apps/mcp_adapter/config.py                 # only if server.py cannot stay cohesive
tests/test_mcp_mapping.py
tests/test_mcp_server.py
tests/integration/test_mcp_rcp001.py
docs/architecture/mcp-integration.md
docs/development.md
docs/roadmap/phases.md
plans/active/phase-09-execution-plan.md
pyproject.toml
requirements.in
requirements.lock
tests/architecture/test_dependencies.py
tools/check.py
```

No `src/ea_research_lab/mcp` package, schema, database, service, DI container,
plugin framework, task runner, or HTTP application is expected. A normal
command composition change under infrastructure is allowed only if M3 proves
it is the minimum explicit way to obtain the already-existing `PlatformApi`;
it must not add a PlatformApi capability.

## 17. Dependency Impact

- Proposed direct dependency: exactly `mcp==2.0.0`.
- Version strategy: exact direct pin plus fully resolved `requirements.lock`;
  review upgrades deliberately because MCP major revisions change protocol/API.
- Python: official metadata requires `>=3.10`, classifies Python 3.14, and has
  Python-3.14-specific dependency constraints.
- Optional SDK `cli`/`rich` extras: not installed unless M1 proves a required
  capability cannot be tested or launched without them.
- Test dependencies: none; use `unittest` plus the SDK's client/in-memory
  transport.
- Transitives: expected to include async, validation, HTTP/ASGI, telemetry,
  schema, JWT/crypto, and Windows support packages. M1 must record the exact
  resolved set and run `pip check`; unused transports do not justify declaring
  their transitives as direct project capabilities.

## 18. Security and Local-runtime Assumptions

Phase 09 assumes one trusted local workstation, trusted repository, explicit
server launch, stdio child-process ownership, and existing OS filesystem/process
permissions. It adds no OAuth, JWT policy, API keys, TLS, RBAC, user database,
or remote multi-user service.

The database path and mode are explicit. Command mode is opt-in. Inputs are
strictly typed and bounded; source paths pass only to the existing Build
request. No secrets, credentials, unrestricted paths, evidence bytes, provider
diagnostics, SQL, or tracebacks enter tool results. Host approval settings are
recommended for Commands, but do not replace application validation or server
mode enforcement.

## 19. Explicit Out of Scope

- new PlatformApi or research capabilities;
- advanced analytics, comparison, ranking, optimization, Test Matrix, and
  vector-strategy work;
- strategy-specific tools or semantic interpretation;
- arbitrary files, directories, shell, Python, SQL, or provider access;
- Raw Evidence content/preview/download and generic Dataset/Analysis payloads;
- Resources, Prompts, sampling, elicitation, autonomous loops, background jobs,
  subscriptions, and progress streaming;
- public/local HTTP MCP deployment, public HTTP Platform API, cloud hosting,
  authentication platform, and distributed execution;
- Phase 10 implementation.

## 20. Risks

| Risk | Required response |
|---|---|
| MCP 2.x/API churn | Exact pin, lock, official API tests, deliberate upgrades |
| Large transitive footprint | Plain package only, inspect lock, no second framework |
| Python 3.14 incompatibility despite metadata | Disposable M1 install/import/transport probe before project change |
| stdout corruption | Protocol-only stdout; structured operational logs to stderr |
| Context explosion | Existing bounded Queries, one page per call, no raw content or auto-pagination |
| Decimal precision loss | Serialize Decimal as string and test exact values |
| Unsafe error leakage | Explicit allow-listed serializer and thin safe mapping |
| Caller identity mistaken for authentication | Opaque local label only; document trust assumption |
| Commands invoked accidentally or retried | Read-only default, separate registration, explicit mode, annotations, client prompt policy, no retry code |
| MCP bypasses PlatformApi | AST boundary tests and one-call spies |
| Source path becomes file API | Field-for-field BuildRequest translation only; no adapter filesystem operations |
| Command composition duplicates application logic | Reuse existing workflows; stop for approval if composition requires new policy |
| RCP-001 mutation/recomputation | Hash, disposable copy, read-only composition, provider guards |
| Codex-specific behavior weakens portability | Official SDK client is authoritative automated proof; Codex is a local acceptance client |
| Current errors cannot express dedicated not-found | Preserve existing code/message; record as follow-up, do not invent MCP taxonomy |

## 21. Acceptance Criteria

Phase 09 is complete only when:

1. the adapter is a local stdio process under `apps/mcp_adapter`;
2. it uses one official direct MCP dependency verified on Python 3.14;
3. read-only mode is the default and advertises exactly eight Query tools;
4. explicit command-capable mode advertises those Queries plus exactly four
   Command tools;
5. every tool performs exactly one corresponding PlatformApi call;
6. all results and errors use explicit safe serialization;
7. Decimal, timestamps, IDs, digests, enums, nulls, and cursors preserve their
   exact semantics;
8. pagination remains bounded/keyset and cursors remain opaque;
9. Evidence remains metadata-only and Dataset/Analysis content remains bounded
   by PlatformApi;
10. provenance delegates only to `get_canonical_chain`;
11. RequestContext is explicit and application audit ownership is unchanged;
12. Commands cannot be invoked in read-only mode and are never retried or
    chained implicitly;
13. portable tests require neither Codex, MetaEditor, nor MT5;
14. real stdio/Codex read validation succeeds against a disposable RCP-001 copy
    without recomputation or canonical mutation;
15. no real MetaEditor/MT5 execution is required solely for MCP validation;
16. core remains four packages and all forbidden imports/capabilities are
    machine-rejected;
17. existing operation counts remain 8/5/4/8/12;
18. no schema or historical contract changes;
19. documentation states the actual local setup, trust model, modes, bounds,
    and limitations;
20. no Phase 10 capability is planned or implemented as part of Phase 09.
