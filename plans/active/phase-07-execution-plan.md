# Phase 07 — Semantic Layer & Platform API Execution Plan

- Status: Completed; M1-M4 completed on 2026-08-12
- Scope: Phase 07 only
- Baseline: completed Phase 06 at
  `c903b3673a8caf214271b1facd6c6dfb553ac093`
- Runtime: Python `>=3.14,<3.15`
- Git policy: no milestone commits; one consolidated Phase 07 commit only after
  M1–M4 are completed and approved

## Objective

Expose the implemented research capabilities through one provider-neutral,
transport-neutral Platform API with explicit Command and Query operations.
Semantic projections describe durable facts for clients without becoming new
entities or sources of truth.

```text
client
  -> Platform API
       -> Commands -> existing workflows -> DataPlane publication/load
       -> Queries  -> application query services
                        -> ResearchQueryPort discovery
                        -> DataPlane identity loads and integrity checks
                        -> semantic projections
```

The existing `DataPlane` remains the canonical publication and known-identity
load boundary with exactly eight operations. Discovery is a separate read-side
capability. Both SQLite adapters may use the same database, but SQL and physical
storage details remain infrastructure-only.

Phase 07 does not add a network transport. It does not implement Visual
Analytics or MCP; it establishes the single boundary those future adapters must
consume.

## Settled boundaries

### Data Plane and queryability

`DataPlane` remains unchanged:

```text
publish_build     load_build
publish_run       load_run
publish_dataset   load_dataset
publish_analysis  load_analysis
```

`ResearchQueryPort` provides only bounded discovery of identifiers. It is not a
repository, SQL abstraction, generic search interface, or alternative load
path. Application query services load each discovered entity through
`DataPlane` before projecting it, preserving Phase 06 integrity checks.

### Semantic Layer

Semantic projections are frozen, provider-neutral values derived on demand
from canonical records. They:

- have no independent entity identity;
- are not persisted;
- do not duplicate Artifact, Raw Evidence, or Dataset bytes;
- retain direct provenance references;
- contain no provider implementation or SUT strategy semantics;
- are independent of any transport serialization.

Semantic values live in `ea_research_lab.domain.semantic`, preserving the
existing top-level `domain`, `application`, `contracts`, and `infrastructure`
package boundary. They may depend on other domain identifiers and values but
must not import application workflows, infrastructure, SQLite, providers, or
transports. Application projection builders depend on the semantic values, not
the reverse.

### Platform API

One concrete typed `PlatformApi` facade exposes direct methods for the approved
Commands and Queries. It delegates to explicit application command/query
services. It has no generic `invoke`, command/query bus, handler registry,
controller hierarchy, endpoint router, or provider selection behavior.

The facade is an in-process application boundary. HTTP, REST, GraphQL, gRPC,
sockets, authentication, and authorization are outside Phase 07.

## Minimum semantic vocabulary

All collections below are immutable tuples. Optional timestamps reflect the
existing Run contract; they do not introduce lifecycle states.

### `ResearchRunSummary`

Source: one integrity-checked `DurableRun`.

Required fields:

- `run_id`;
- `artifact_id`;
- `test_definition_revision_id`;
- execution lifecycle `status`;
- `created_at`;
- collection outcome of the sealed evidence manifest explicitly referenced by
  the Run Manifest, when present.

Optional fields:

- `started_at`;
- `finished_at`.

The summary does not contain Dataset/Analysis counts because they require
unbounded reverse counting. Their availability is discovered through bounded
queries.

### `ResearchRunDetail`

Extends the summary with:

- `environment_configuration_id`;
- execution reproducibility assessment;
- ordered evidence manifest references, including revision relationships;
- direct Artifact and Test Definition references.

It excludes environment payloads, Raw Evidence descriptors/bytes, provider
logs, Dataset content, and inferred strategy meaning.

### `DatasetSummary`

Source: one integrity-checked `Dataset`.

Fields:

- `dataset_id`;
- `created_at`;
- Dataset content schema/version;
- content SHA-256;
- transformation identity/version.

### `DatasetDetail`

Extends the summary with direct input evidence manifest references, input
Dataset identities, and the transformation-parameter schema reference when
present. Dataset content is excluded because the implemented event-series
Datasets are not bounded client responses.

### `AnalysisSummary`

Source: one integrity-checked `AnalysisResult`.

Fields:

- `analysis_result_id`;
- `created_at`;
- result schema/version;
- result SHA-256;
- analysis definition identity/version.

### `AnalysisDetail`

Extends the summary with exact input Dataset identity/digest pairs, computation
environment identity, analysis-parameter schema reference, and an optional
bounded result payload. Direct inclusion is limited to
`execution-core-analysis-result/0.1.0`, whose structure has fixed bounds. The
potentially growing execution-summary comparison result is represented only by
schema and digest. A future result schema requires an explicit boundedness
review before direct inclusion; Phase 07 does not invent streaming or download
semantics.

### `ProvenanceSummary` and canonical chain projection

`ProvenanceSummary` contains only typed references needed to navigate the
validated chain: Build Record, Artifact, Test Definition revision, Run, sealed
evidence manifest revisions, Datasets with digests, and Analysis Result. The
canonical chain projection combines this summary with the relevant semantic
summaries. It is derived from `reconstruct_canonical_chain()` and is not a graph
engine or persisted lineage entity.

## Bounded discovery contract

### Exact `ResearchQueryPort` operations

```python
list_research_runs(page: PageRequest) -> DiscoveryPage[RunId]
list_run_datasets(run_id: RunId, page: PageRequest) -> DiscoveryPage[DatasetId]
list_dataset_analyses(
    dataset_id: DatasetId,
    page: PageRequest,
) -> DiscoveryPage[AnalysisResultId]
```

There are no get-by-ID methods in this port. Known-identity reads continue
through `DataPlane`.

For Phase 07, `list_run_datasets` means Datasets whose manifests directly
reference a sealed evidence manifest explicitly retained by that Run. Recursive
discovery of arbitrary downstream Dataset lineage is not part of the first
query surface. `list_dataset_analyses` means Analysis Results that directly
declare the exact Dataset identity/digest as an input.

### Pagination policy

- valid limits are `1..200`;
- omitted limit uses `50`;
- implementations fetch at most `limit + 1` rows to determine continuation;
- a final page returns `next_cursor=None`;
- total counts, page numbers, arbitrary sorting, and arbitrary filters do not
  exist;
- cursors are opaque URL-safe base64 encodings of canonical JSON;
- cursor version `1` binds the cursor to the query kind, parent identity where
  applicable, last `created_at`, and last typed entity ID;
- malformed, unsupported, or cross-query/cross-parent cursor reuse fails with
  a safe invalid-value error;
- cursors are continuity tokens, not authentication or integrity credentials.

Deterministic keyset order is:

- Runs: `created_at DESC`, then `run_id ASC`;
- Datasets for a Run: `created_at ASC`, then `dataset_id ASC`;
- Analyses for a Dataset: `created_at DESC`, then
  `analysis_result_id ASC`.

Typed IDs are used only as opaque deterministic tie-breakers; no domain
metadata is decoded from UUIDv7 values.

The first implementation queries the existing immutable record/content tables
using keyset predicates and a bounded SQL result. It does not add a persisted
semantic projection or migration framework. A private SQLite index/storage
support change is allowed only if a portable M1 test proves it necessary for
correct deterministic pagination, not for hypothetical scale.

## Command boundary and publication semantics

The four methods are:

```text
build_artifact
execute_run
transform_evidence
analyze_datasets
```

The command service receives explicitly composed workflow callables and the
`DataPlane`; it never imports or selects MetaEditor, MT5, or MT5 transformers.
The composition root/test supplies those dependencies without a DI container or
registry framework.

### Requests

- `build_artifact` accepts the existing provider-neutral `BuildRequest`.
- `execute_run` accepts context, exact Build Record/Artifact identities, Test
  Definition, environment configuration, timeout, and reproducibility
  assessment. It loads the accepted Artifact and constructs the existing
  `ExecutionRequest`.
- `transform_evidence` accepts context, Run identity, exact sealed evidence
  manifest reference, and transformation identity/version/parameters. It loads
  exact captured evidence and constructs the existing `TransformationRequest`;
  there is no implicit "latest" evidence selection.
- `analyze_datasets` accepts context, ordered Dataset identity/digest pairs,
  analysis definition/version/parameters, and computation environment identity.
  It loads and verifies the Datasets before constructing `AnalysisRequest`.

New command request values are immutable application-boundary values. They do
not replace existing workflow requests or persisted contracts.

### Results and failure semantics

Each command returns one bounded immutable, command-specific result containing
the request ID, capability outcome, produced identity/reference when available,
durable publication outcome, and an optional safe `ApplicationError`. It never
returns Artifact bytes, Raw Evidence bytes, provider output, paths, SQL, or
internal causes.

- every completed Build record, including a provider-reported failed Build, is
  published before the command returns its final result;
- every post-admission terminal Run, including failed/cancelled execution and
  collection failure, is published with preserved evidence before return;
- a failed Dataset transformation or Analysis with no product has nothing to
  publish;
- a produced Dataset or Analysis is published before command success;
- exact duplicate publication remains a successful idempotent publication;
- publication failure makes the command fail closed with
  `DATA_PLANE_FAILED`/`DATA_INTEGRITY_FAILED` as applicable;
- publication failure does not delete, overwrite, or fabricate workflow output;
- execution completion and durable publication success remain separate facts.

There is no distributed transaction claim across MetaEditor, MT5, and SQLite.
For the controlled research vertical, `transform_evidence` executes exactly the
execution-summary, realized-execution-event-series, and
account-balance-event-series transformations in that order. Each successful
Dataset is published in the same order. A later failure does not roll back or
misrepresent an earlier successful publication.

The command boundary emits bounded operational started/completed/failed events
with request/caller correlation and safe identifiers/error codes. These events
are not canonical research facts or a persistent audit subsystem.

## Query surface

Application query services accept `RequestContext`, use
`ResearchQueryPort` only for discovery, use `DataPlane` for all loads, and build
semantic projections:

| Query | Input | Output | Source |
|---|---|---|---|
| `list_research_runs` | page request | page of `ResearchRunSummary` | discovery IDs + `load_run` |
| `get_research_run` | `RunId` | `ResearchRunDetail` | `load_run` |
| `list_run_datasets` | `RunId`, page request | page of `DatasetSummary` | discovery IDs + `load_dataset` |
| `get_dataset` | `DatasetId` | `DatasetDetail` | `load_dataset` |
| `list_dataset_analyses` | `DatasetId`, page request | page of `AnalysisSummary` | discovery IDs + `load_analysis` |
| `get_analysis` | `AnalysisResultId` | `AnalysisDetail` | `load_analysis` |
| `get_canonical_chain` | explicit Build Record, Run, Analysis IDs | canonical semantic projection | `reconstruct_canonical_chain` |

List operations preserve the discovery page order after integrity-checked
loads. Missing, corrupt, or cross-linked records fail the whole query safely;
they are not silently skipped. Query errors contain no SQLite or provider
details.

## Auditability and errors

The Platform API/application boundary owns consistent request identity,
validation, safe errors, and operational audit facts. Every operation accepts
an explicit `RequestContext`; there is no thread-local/global context.

Commands emit paired structured events through the existing logging facility:

```text
platform.command.<capability>.started
platform.command.<capability>.completed
platform.command.<capability>.failed
```

The event timestamp plus `request_id`, optional `caller_id`, capability encoded
in the event name, available target identity, and safe outcome/error code form
the minimum Phase 07 audit facts. Query events may record capability,
correlation, completion/failure, page size, and returned item count, but never
arguments containing payload bytes or cursor contents.

These are non-durable application audit/operational events, not Raw Evidence,
canonical records, or an audit database. Existing `ApplicationError` envelopes
are reused; `cause` is never serialized or logged.

## Minimum expected structure

```text
src/ea_research_lab/
  domain/
    semantic.py
  application/
    research_query.py
    platform_commands.py
    platform_queries.py
    platform_api.py
  infrastructure/
    sqlite_research_query.py

# no semantic transport schemas until a serialization boundary exists

tests/
  test_semantic_projections.py
  test_sqlite_research_query.py
  test_platform_commands.py
  test_platform_queries.py
  test_platform_api.py
  architecture/
  integration/test_mt5_strategy_tester.py
```

The exact number of schema families may be reduced if one implemented public
shape covers multiple projections without optional-field ambiguity. Do not
create serialized command schemas in Phase 07 unless the in-process facade
actually serializes command requests/results. Historical schemas are never
modified for API convenience. Any newly exercised semantic contract starts at
pre-stable `0.1.0` and evolves under ADR-0008; existence alone does not justify
`1.0.0` stability.

## M1 — Semantic Vocabulary and Query Boundary

- Status: Completed

### Objective

Implement immutable semantic projections, the exact three-operation
`ResearchQueryPort`, deterministic cursor values, and SQLite discovery over the
existing Phase 06 database.

### Implementation sequence

1. Add a portable characterization test that publishes same-timestamp Runs,
   related Datasets, and related Analyses through `SqliteDataPlane`, then states
   the expected first/next-page identity order for all three discovery paths.
2. Add the three frozen semantic summary values in `domain/semantic.py` and
   dependency-boundary tests.
3. Add `PageRequest`, opaque cursor codec, `DiscoveryPage`, and the three-method
   Protocol.
4. Implement `SqliteResearchQuery` against existing private tables with
   `limit + 1` keyset queries.
5. Add the three list composition functions in `platform_queries.py`; each
   loads discovered identities through `DataPlane` before projection.
6. Test empty/final pages, tie-breaks, parent binding, malformed cursors,
   invalid limits, close/reopen, missing/corrupt rows, and independence from
   `DataPlane`'s eight-operation surface.

### Acceptance criteria

- all projection fields have the sources and exclusions defined above;
- the port contains exactly three discovery methods and returns identities;
- every list is bounded and deterministically repeatable;
- SQLite/SQL remain infrastructure-only;
- no persisted projections or new source-of-truth entity exists;
- `DataPlane` remains exactly eight operations;
- no Commands or Platform API facade exist yet.

### Out of scope

Platform Commands, detail/get queries, public schemas, API facade, network
transport, total counts, arbitrary filters, and storage redesign.

## M2 — Platform Commands

- Status: Completed

### Objective

Add four explicit command operations that reuse existing workflows and make
required durable publication part of command success semantics.

### Implementation sequence

1. Add immutable ID-based command requests/results where existing workflow
   requests are insufficient at the external application boundary.
2. Implement one concrete command service with four direct methods and
   explicitly supplied workflow dependencies.
3. Resolve Build/Run/Evidence/Dataset inputs through `DataPlane`; invoke
   existing workflows without duplicating their provider, evidence,
   transformation, or analysis logic.
4. Publish completed durable facts and map failures to safe existing errors.
5. Emit the minimum structured boundary events through explicit logger/context
   dependencies.

### Tests and acceptance criteria

- each command delegates once to the expected workflow;
- failed Builds and terminal failed/cancelled Runs are durably published;
- successful Dataset/Analysis results are published before success;
- publication failure returns failure and preserves produced in-memory facts;
- duplicate publication is idempotent;
- request/caller correlation and safe error behavior are preserved;
- logs expose no provider payload, evidence bytes, paths, SQL, or causes;
- no CommandBus, registry, provider selection, query facade, or transport is
  introduced.

### Out of scope

Queries, public serialization, durable audit records, distributed transaction
semantics, cancellation redesign, authentication, and authorization.

## M3 — Platform Queries and Transport-Neutral API

- Status: Completed

### Objective

Implement the seven approved bounded queries and expose all four Commands plus
seven Queries through one concrete transport-neutral `PlatformApi` facade.

### Implementation sequence

1. Extend the M1 projection builders with the approved detail shapes.
2. Implement exact-ID query services through `DataPlane`; retain the M1 list
   composition path through `ResearchQueryPort` followed by `DataPlane` loads.
3. Reuse `reconstruct_canonical_chain()` for the chain query.
4. Add the direct-method `PlatformApi` facade that delegates only to command
   and query services.
5. Keep semantic/page values as typed Python contracts; no serialized schema is
   introduced because M3 exercises no transport serialization boundary.
6. Test bounded response policy: no Artifact/Raw Evidence/Dataset bulk bytes,
   and direct Analysis result content only for approved bounded schemas.

### Acceptance criteria

- all seven Queries return provider-neutral immutable projections;
- ordering and cursors survive SQLite close/reopen;
- discovered objects are integrity-loaded, never projected directly from SQL;
- one Platform API exposes explicit Command and Query capabilities;
- no client-facing code imports SQLite, providers, transformers, or Analysis
  implementation details;
- projections remain on-demand and non-persistent;
- no public serialization contract or historical schema changes are introduced;
- no network or serialization framework dependency exists.

### Out of scope

Large-content retrieval, streaming/download APIs, arbitrary filters,
comparison/timeseries capabilities not already implemented, HTTP, UI, and MCP.

## M4 — Enforcement and Closure

- Status: Completed

### Objective

Machine-enforce the Phase 07 boundary, prove portable and controlled real
verticals through the Platform API, align relevant documentation, and close the
phase without adding Phase 08/09 capability.

### Enforcement and tests

- enforce exactly eight `DataPlane` methods and exactly three
  `ResearchQueryPort` discovery methods;
- enforce SQL/SQLite confinement to infrastructure;
- prevent Platform API imports of infrastructure providers/SQLite;
- reject generic CRUD/query/command buses and network frameworks;
- enforce semantic package neutrality and non-persistence;
- scan semantic/API contracts for provider or SUT strategy vocabulary;
- prove portably:

  ```text
  Platform Command -> existing workflow -> publication
  -> Platform Query -> semantic projection
  ```

- extend the single controlled MT5 vertical only enough to prove Build, Run,
  three Dataset transformations, Analysis, durable SQLite state, bounded
  discovery/detail queries, and validated canonical provenance through
  `PlatformApi`;
- confirm no unrelated provider process remains.

### Documentation and acceptance criteria

- update only Semantic Layer, Platform API/system context, development, roadmap
  status, and this plan as required by implemented behavior;
- document cursor rules, large-content exclusion, audit ownership, and absence
  of network transport;
- prove a future Visual Analytics client can enumerate/open Runs, discover and
  inspect Dataset/Analysis summaries, and follow provenance only through the
  Platform API;
- prove by dependency tests that a future MCP adapter has no path to DataPlane,
  SQLite, providers, or Analysis internals;
- run the authoritative portable gate, full portable discovery, controlled real
  integration, `compileall`, `pip check`, and `git diff --check`;
- confirm no dependency, transport, UI, MCP, or future-phase capability was
  added.

### Out of scope

New runtime behavior, UI, MCP, frontend fields, network protocol, auth system,
optimizer, ranking, experiments, Test Matrix, telemetry, or Phase 08/09 plans.

## Quality gates

Every milestone runs its focused tests plus the authoritative portable gate.
M4 runs:

```powershell
python tools/check.py
python -m unittest discover -s tests -p "test*.py"
python -m compileall -q src tests tools
python -m pip check
git diff --check
```

The existing controlled MetaEditor/MT5 integration remains opt-in and is run
only with all current safety variables explicitly configured.

## Major risks

- reverse discovery may accidentally bypass Phase 06 integrity loads;
- cursor ordering can become unstable if timestamps/tie-breakers are handled
  inconsistently;
- command success may be reported before durable publication;
- provider selection or physical storage details may leak into the facade;
- semantic details may accidentally return unbounded Dataset/evidence content;
- projections may drift into duplicated persisted truth;
- a generic repository, bus, or transport framework may appear under a neutral
  name;
- boundary logs may leak request payloads or internal causes;
- SQLite discovery may require measured indexing later, but hypothetical scale
  must not trigger a persistence redesign now.

## Dependencies

No new dependency is planned. Frozen dataclasses, Protocol, JSON, base64,
logging, and SQLite keyset queries are covered by the Python standard library
and existing project facilities. A web framework is unnecessary because Phase
07 has no network transport.

The existing non-blocking follow-ups remain unchanged:

- wheel/distribution packaging of external schemas;
- direct use of the transitively installed `referencing` package.

## Objective completion criteria

Phase 07 is complete only when:

- the three discovery operations and seven Platform Queries are bounded and
  deterministic;
- the four Platform Commands reuse existing workflows and publish required
  durable facts before reporting success;
- semantic projections are provider-neutral, immutable, traceable, and
  non-persistent;
- `DataPlane` still has exactly eight operations;
- one transport-neutral `PlatformApi` is the only intended client boundary;
- safe errors, request correlation, and application-owned audit facts are
  consistent across Commands and Queries;
- portable and controlled real verticals pass;
- no network, UI, MCP, generic CRUD/search, strategy semantics, new dependency,
  or Phase 08/09 implementation exists;
- the complete Phase 07 diff is approved before its single consolidated commit.

## First implementation action

Start M1 with one failing portable characterization test over a disposable
Phase 06 SQLite database. Publish at least three same-timestamp Runs, their
evidence-linked Datasets, and Dataset-linked Analyses; assert the exact first
and continuation pages for all three approved discovery paths. This fixes the
ordering/cursor invariant before adding `ResearchQueryPort` or changing
production modules.
