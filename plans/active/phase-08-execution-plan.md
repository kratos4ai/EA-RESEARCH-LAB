# Phase 08 — Visual Analytics Execution Plan

- Status: Completed
- Scope: Phase 08 only
- Baseline: completed Phase 07 plus the approved Research Operator Readiness
  iteration at `927ffd8`
- Acceptance data: immutable persisted RCP-001 checkpoint at
  `data/rcp-001/lab.sqlite3`
- Runtime: Python `>=3.14,<3.15`
- Git policy: no milestone commits; one consolidated Phase 08 commit only after
  M1–M4 are implemented, reviewed, and approved

## 1. Objective

Deliver the smallest useful, read-only Visual Analytics experience over the
completed research lifecycle. A researcher must be able to discover a Run,
understand its execution context and outcomes, inspect the current bounded
Analysis Core result, navigate Dataset/Analysis metadata, assess
reproducibility, and inspect canonical provenance without direct database
access or copied internal identifiers.

```text
Researcher
  -> local browser presentation
       -> PlatformApi Query capabilities
            -> application query services
                 -> bounded discovery
                 -> DataPlane integrity-verified loads
                 -> immutable semantic projections
```

Phase 08 is inspection/exploration only. It exposes no Build or Run controls,
performs no analysis in presentation code, and does not implement a public
network Platform API.

## 2. Evidence from RCP-001 and the operator retrospective

RCP-001 proved the complete durable lifecycle through Build, Run, sealed Raw
Evidence, three deterministic Datasets, Analysis, reload, semantic queries, and
canonical provenance. The subsequent operator workflow used all seven current
Platform API Queries against a disposable database copy.

That inspection established the following facts:

- Run lifecycle, timestamps, Artifact/Test Definition references, evidence
  outcome/history, reproducibility, Dataset metadata, Analysis metadata, 19
  Analysis Core metrics, and canonical provenance are already available;
- `total_trades`, `winning_trades`, `losing_trades`, and `net_profit` exist in
  the bounded execution-summary Dataset but are not exposed semantically;
- experiment configuration exists in the persisted Test Definition and Run
  environment payload but is represented semantically only by identities;
- canonical reconstruction works, but `BuildRecordId` is not discoverable from
  the Run/Artifact relationship;
- Raw Evidence sealing is visible, but Evidence Object metadata/content is not;
- the query-only bootstrap still constructs disabled Commands.

RCP-001 is acceptance data, not a strategy model. No EMA-specific concept may
enter semantic or presentation code.

## 3. Current capability gaps

| Gap | Durable source | Minimum Phase 08 response |
|---|---|---|
| Four basic execution facts | `execution-summary/0.1.0` Dataset content | Permit only this explicitly reviewed fixed-bound Dataset contract as immutable bounded content in `DatasetDetail`. |
| Interpretable experiment context | Test Definition execution configuration; Run environment configuration | Project supported fields through a one-operation provider adapter into one provider-neutral immutable semantic value. |
| Build Record navigation | Accepted Artifact manifest/Build relationship | Add exactly one capability-specific `ResearchQueryPort` lookup from `ArtifactId` to `BuildRecordId`, verify the returned Build through `DataPlane`, and include the identity in `ResearchRunDetail`. |
| Query-only composition | Existing SQLite Data Plane/query adapters and `PlatformApi` | Add one explicit local read-only composition root; no container, registry, or framework. |
| Evidence metadata | Sealed `DurableEvidence` objects | M3 adds one bounded Platform API metadata query; content remains excluded. |

No new persisted contract is required. Historical schemas remain unchanged.

## 4. Technology recommendation

### Selected: local browser application with Streamlit

Use one local Streamlit application, bound explicitly to `127.0.0.1`, with
built-in tables, metric elements, navigation widgets, and charts. Streamlit is
the only new direct dependency. Its exact version will be selected and locked
at M2 implementation after verifying Python 3.14 and the repository gate.

Reasons:

- it consumes Python `PlatformApi` objects in-process, so no serialized/public
  Platform API or duplicated data-access client is needed;
- it supplies browser rendering, widgets, tables, charts, session state, and a
  headless `AppTest` surface rather than requiring the Lab to own those pieces;
- current official installation documentation supports Python 3.10–3.14;
- the app remains local and read-only; its internal localhost presentation
  transport is not an independently supported application contract;
- view-model logic remains pure Python and portable-testable with `unittest`.

The application must not use Streamlit caching as a source of truth. Queries
remain bounded and integrity-verified. Canonical decimal strings remain intact
in view models; conversion is allowed only at the final chart/formatting edge.

Official evidence reviewed during planning:

- https://docs.streamlit.io/get-started/installation/command-line
- https://docs.streamlit.io/develop/concepts/architecture/architecture
- https://docs.streamlit.io/develop/api-reference/app-testing

### Rejected for Phase 08

**Lightweight native Python desktop (`tkinter`)** requires custom charting,
layout, navigation, and interaction testing. It saves a dependency but creates
more presentation code and a weaker visual research experience.

**Static/generated HTML** is useful for export and the operator script already
proves that model, but it cannot naturally provide live bounded pagination and
progressive Run/Dataset/Analysis navigation without regeneration or a second
client data model.

**Hand-written standard-library local HTTP application** avoids a dependency
but requires the Lab to own routing, HTML templating, browser state, chart SVG,
and security-sensitive request handling. Python documents its simple HTTP
server as unsuitable for production. That ownership is not justified for a
local research vertical.

No separate plotting library, JavaScript framework, CSS framework, web API
framework, browser automation dependency, or template engine is planned.

## 5. Target Visual Analytics boundary

```text
apps/visual_analytics/
  app.py          Streamlit rendering and user interaction only
  view_model.py   pure formatting and explicit visual states

src/ea_research_lab/infrastructure/
  composition.py  explicit local read-only PlatformApi lifecycle
  mt5_semantic.py MT5 extension contract -> neutral experiment context

Visual code -> PlatformApi only
PlatformApi -> PlatformQueries -> ResearchQueryPort + DataPlane
```

Visual modules may import `PlatformApi`, application request context/page
values, semantic projections, and presentation dependencies. They must not
import Data Plane ports/adapters, SQLite, providers, transformations, Analysis
operations, or provider extension contracts.

The first product is one compact navigable experience, not a multi-page
workbench:

- a bounded Research Runs selector/list with next/previous cursor state;
- one selected Run overview;
- Performance and justified charts in the main view;
- Dataset, Analysis, reproducibility, provenance, and evidence-metadata
  drill-down in sections/tabs below the overview.

Above the fold for a selected Run:

- Run identity and execution/evidence status;
- symbol, timeframe, interval, and requested initial capital when available;
- total/winning/losing counts and net profit;
- net return, win rate, profit factor, payoff ratio, and event-balance maximum
  drawdown rate;
- reproducibility level with unavailable/best-effort state visible.

Canonical values and availability remain separate from display strings. For
example, canonical `0.002630000000` may display as `0.263%`; Decimal-based
formatting must not alter analytical content or identities.

## 6. M1 — Visual Read Model Readiness

- Status: Completed

### Objective

Close only the confirmed semantic/query gaps required by the first visual
vertical, before implementing UI code.

### Contracts and responsibilities

1. Add immutable provider-neutral semantic values:
   - `ExecutionSummaryProjection`: currency, observed initial deposit, net
     profit, and total/winning/losing counts;
   - `ExperimentContextProjection`: instrument, timeframe, start/end dates,
     requested initial capital/currency, and leverage;
   - add verified `build_record_id` and experiment context to
     `ResearchRunDetail`;
   - add optional explicit `execution_summary` to `DatasetDetail`, populated
     only for `execution-summary/0.1.0`. This is not a generic Dataset-content
     query, and clients never interpret Dataset JSON.
2. Add one application port, `ExperimentContextProjector`, with one operation
   from an exact Test Definition/environment payload to
   `ExperimentContextProjection`. Its MT5 adapter translates
   `mt5-strategy-tester-execution/0.1.0`; Platform Queries do not import MT5
   vocabulary.
3. Grow `ResearchQueryPort` from three to exactly four operations with:

   ```python
   find_build_record_for_artifact(artifact_id: ArtifactId) -> BuildRecordId
   ```

   This is a single cardinality-one canonical relationship, not generic reverse
   lookup. The SQLite query adapter returns the identity; `PlatformQueries`
   loads the Build through `DataPlane` and verifies that its accepted Artifact
   matches before projecting the ID.
4. Keep `get_canonical_chain` as the existing operation. Clients obtain its
   Build Record argument from `ResearchRunDetail`; no out-of-band/script-copied
   identity is required and no graph engine is introduced.
5. Add one explicit context-managed read-only composition function that creates
   SQLite adapters, the MT5 experiment projector, and `PlatformApi`, while
   Commands fail closed. It is infrastructure bootstrap, not a service
   container or visual business logic.

The durable MT5 execution contract also contains numeric `model` and
`execution_mode` fields. M1 does not project either: the repository has no
approved provider-neutral modeling-mode vocabulary, so exposing a label would
invent semantics. They remain provider-specific configuration facts rather
than visual read-model fields.

No new Platform API operation is required in M1. Counts remain:

- `DataPlane`: 8;
- `ResearchQueryPort`: 4;
- `PlatformCommands`: 4;
- `PlatformQueries`: 7;
- `PlatformApi`: 11.

### Expected files

- modify `src/ea_research_lab/domain/semantic.py`;
- add `src/ea_research_lab/application/experiment_context.py`;
- modify `src/ea_research_lab/application/research_query.py`;
- modify `src/ea_research_lab/application/platform_queries.py`;
- add `src/ea_research_lab/infrastructure/mt5_semantic.py`;
- modify `src/ea_research_lab/infrastructure/sqlite_research_query.py`;
- add `src/ea_research_lab/infrastructure/composition.py`;
- focused semantic/query/composition tests and architecture enforcement updates.

### Tests and acceptance

- exact execution-summary projection from integrity-verified bounded content;
- no other Dataset schema exposes inline content;
- MT5 extension values map to neutral context without MT5 types/field names in
  domain values;
- missing/unsupported/malformed context fails safely or reports unavailable as
  explicitly designed; it is never inferred;
- Artifact-to-Build discovery is cardinality-one and fails closed on missing,
  conflicting, or mismatched lineage;
- canonical-chain navigation begins from a discovered Run and needs no manually
  copied Build Record identity;
- read-only composition invokes no Command and closes owned adapters;
- no visual source, dependency, schema, or persistence redesign enters M1.

## 7. M2 — Research Overview

- Status: Completed

### Objective

Implement the first useful local, read-only visual view over M1 projections and
the existing bounded Analysis result.

### Experience

- bounded/keyset Run list with deterministic order and cursor-aware next/back
  navigation; back navigation retains previously issued cursors rather than
  inventing offset/page semantics;
- Run selection and one overview view;
- above-the-fold execution context, lifecycle/evidence status, basic outcomes,
  Analysis Core headline metrics, and reproducibility badge;
- exact unavailable states rather than zeros or fabricated defaults;
- safe user messages for Platform API failures with no internal exception,
  paths, SQL, or provider payload.

### Justified charts

1. **Winning versus losing executions** — two categorical bars using canonical
   execution-summary counts. It is not a trade reconstruction or strategy
   score.
2. **Realized PnL summary statistics** — a compact min/median/mean/max marker or
   bar view using existing Analysis Core results. It must not be labeled a
   histogram or full distribution.

Event-balance maximum drawdown is a metric card only. No event-balance path is
planned because the current Platform API exposes no bounded series. It must be
labeled **event-balance maximum drawdown**, never equity drawdown. No equity,
continuous-balance, holding-time, trade, MAE, or MFE chart is permitted.

### Expected files

- add `apps/visual_analytics/view_model.py`;
- add `apps/visual_analytics/app.py`;
- document the direct Streamlit invocation; no launcher wrapper is needed;
- add exact Streamlit direct dependency to `requirements.in` and regenerate the
  lock through the existing dependency workflow;
- pure view-model and minimal Streamlit `AppTest` tests.

### States and acceptance

- no Runs: clear empty state with no fake sample data;
- completed Run without Analysis: context/status/Datasets remain visible and
  Analysis/metric section says unavailable;
- failed/cancelled Run: lifecycle is prominent; success metrics are not implied;
- evidence collection failed/partial: independent warning without changing Run
  status;
- best-effort/unavailable reproducibility: reasons visible and not downgraded to
  generic success;
- unavailable metric: explicit `Unavailable`, not zero/blank;
- Run list never fetches beyond the requested bounded page;
- no Build/Run/transform/analyze control exists;
- charts consume semantic metric values and perform formatting only.

## 8. M3 — Research Drill-down and Provenance

- Status: Completed

### Objective

Complete focused research navigation without becoming a generic explorer.

### Capabilities

- Dataset section: identity, content schema/digest, transformation identity and
  version, and direct provenance references; no payload browser;
- Analysis section: identity, definition/version, result schema/digest,
  parameters schema, computation environment, inputs, and bounded result;
- reproducibility section: level and recorded reasons;
- canonical provenance section: readable Build → Artifact → Test Definition →
  Run → Evidence → Datasets → Analysis chain with useful identities/digests;
- Evidence Level 1 only: bounded Evidence Object metadata containing typed
  object identity, manifest identity, media type, byte length, digest, optional
  payload schema, and provider namespace.

Evidence metadata adds exactly one capability:

```python
list_run_evidence_objects(
    context: RequestContext,
    run_id: RunId,
    manifest_id: RawEvidenceManifestId,
    page: PageRequest,
) -> Page[EvidenceObjectSummary]
```

It belongs to `PlatformQueries`/`PlatformApi` and one capability-specific
`ResearchQueryPort` durable read. Loading the Run through `DataPlane` would
materialize the complete manifest and Raw Evidence bytes before pagination, so
the SQLite adapter instead applies the page bound with keyset/`LIMIT` over
immutable manifest order. Raw bytes, previews, search, parsing, and downloads
remain excluded.

After M3 the exact counts are:

- `DataPlane`: 8;
- `ResearchQueryPort`: 5;
- `PlatformCommands`: 4;
- `PlatformQueries`: 8;
- `PlatformApi`: 12.

### Tests and acceptance

- all drill-down loads originate from Platform API Queries;
- evidence pages obey `1..200`, deterministic immutable-manifest order, opaque
  cursor binding, and safe cross-Run/manifest rejection;
- no Evidence content enters semantic/view values or logs;
- provenance uses the existing reconstruction capability, not UI joins or a
  graph abstraction;
- no strategy/event-specific vocabulary such as `MA_CROSS`, BUY, SELL, EMA, or
  strategy score exists in visual/domain/application modules;
- Level 2 content preview and Level 3 interpretation remain deferred.

### Implemented decisions

- Dataset and Analysis navigation use the existing bounded keyset discovery
  and detail Queries, with separate cursor history and identity-only selection
  state.
- Evidence descriptors could not be embedded unboundedly in Run detail because
  `raw-evidence-manifest/0.1.0` does not cap object cardinality. The approved
  manifest-specific metadata Query and one exact `ResearchQueryPort` operation
  were therefore required. The durable adapter applies keyset/`LIMIT` before
  returning descriptors and never loads Raw Evidence bytes; no Evidence content
  capability was added.
- Canonical MetaEditor Build evidence supports historical Build provider,
  version, and executable digest projection through an exact infrastructure
  adapter. The execution runtime version is not retained in canonical Run facts
  and remains explicitly unavailable. No current-machine inspection is used.
- Provenance display delegates verification to `get_canonical_chain`; failures
  produce a safe unverified state rather than a partial trusted chain.

## 9. M4 — RCP-001 Validation and Closure

- Status: Completed

### Objective

Enforce the final boundary and validate usability against the immutable real
checkpoint without adding capability.

### Validation

- run semantic/query, view-model, and Streamlit integration suites;
- inspect an automatic disposable copy of `data/rcp-001/lab.sqlite3` through the
  read-only composition and `PlatformApi` only;
- record and compare the canonical database digest before/after validation;
- assert that Build, Run, transformation, and Analysis Commands are never
  invoked and that MetaEditor/MT5 are not started;
- verify RCP-001 shows EURUSD/H1, the persisted interval, completed status,
  135/43/92 counts, USD 2.63 net profit, 0.263% net return, 31.85% win rate,
  1.0143 profit factor, 2.17 payoff ratio, and 3.65% event-balance maximum
  drawdown from Platform API projections rather than hardcoded runtime data;
- verify Dataset/Analysis identities, reproducibility, and full provenance;
- perform a short keyboard/navigation/readability check locally;
- update only affected architecture, roadmap, development, and Phase 08 status
  documentation.

### Closure gates

- authoritative portable gate and complete `unittest` discovery;
- Streamlit headless/AppTest suite;
- `compileall`, `pip check`, and `git diff --check`;
- dependency/license and locked-environment verification;
- complete cumulative Phase 08 diff review;
- one consolidated commit only after owner approval;
- no MT5/MetaEditor integration run is required or permitted for visual
  acceptance.

M4 introduces no major runtime capability, schema, analytical formula, or
future-phase scaffold.

### Implemented validation

- one automated validation copies `data/rcp-001/lab.sqlite3` into a disposable
  workspace and uses read-only composition, Platform API, pure view models, and
  the real Streamlit entrypoint;
- the canonical and disposable-copy SHA-256 remained
  `f95b223be6351dd51272a921d4ec0841bc2b29d710b2ebb04ef0fcbd6926c495`
  before and after validation;
- the Run was discovered without supplied identities and the persisted
  EURUSD/H1 context, lifecycle, execution summary, bounded Analysis metrics,
  three Dataset products, three Evidence descriptors, best-effort reasons,
  historical MetaEditor facts, unavailable execution-runtime version, and
  verified canonical chain were observed;
- provider methods were guarded and received zero calls; the existing
  read-only-composition tests also prove all four Commands fail before workflow
  side effects;
- a short usability review found the selected-Run tab workspace understandable
  without SQLite/Data Plane knowledge, with IDs/digests available but secondary
  to semantic labels. Event-Balance wording and explicit unavailable states are
  clear. The bounded Analysis detail was expanded to present all already
  computed Phase 05 metrics; no metric was added or recomputed.

## 10. Testing strategy

### Semantic/query tests

- immutable projections and exact type/value validation;
- execution-summary boundedness;
- provider-neutral experiment-context mapping at the adapter boundary;
- Artifact-to-Build relation integrity and failure classification;
- evidence metadata pagination and manifest/run binding;
- canonical navigation with only identities discovered through the normal API
  workflow.

### Presentation/view-model tests

Pure `unittest` tests cover:

- Decimal-string currency, percentage, count, and unavailable formatting;
- canonical values retained separately from display values;
- lifecycle/evidence/reproducibility state mapping;
- no Runs, no Analysis, failed, cancelled, partial collection, unavailable
  metric, and safe-error views;
- next/back cursor state without offset pagination;
- chart inputs produced only from already-computed semantic metrics.

### Visual integration tests

Use Streamlit `AppTest` at the smallest practical level with a fake
`PlatformApi` to verify Run selection, state rendering, sections, and chart
presence. Keep `unittest`; do not add pytest or browser automation.

M4 adds one real read-only validation using a disposable copy of RCP-001. No
test reads SQLite directly to assert operator-visible facts; setup may copy the
file and compose infrastructure, after which assertions use Platform API/view
models only.

## 11. Architecture enforcement

Extend the existing standard-library AST tests to enforce:

- `ea_research_lab.visual` imports no `infrastructure`, Data Plane,
  `ResearchQueryPort`, SQLite, provider, transformer, or Analysis operation;
- the visual client receives/uses `PlatformApi` as its only research-data
  application boundary;
- visual code contains no analytical formulas or Dataset/Raw Evidence parsing;
- semantic projections import no presentation or infrastructure modules and
  remain frozen/non-persistent;
- application/domain files contain no Streamlit, HTML, CSS, chart, or MT5
  adapter dependency;
- no EMA/crossover/BUY/SELL strategy vocabulary enters visual, semantic, or
  application modules;
- no MCP, generic search/filter/graph, public HTTP API, or command UI appears;
- DataPlane and command operation counts remain unchanged; final query counts
  match the explicit M3 boundary.

No new architecture-test framework is required.

## 12. Files/modules expected

| Area | Expected change |
|---|---|
| Semantic | Extend `domain/semantic.py` with execution summary, experiment context, evidence metadata, and verified Build reference values. |
| Application | Add one experiment-context projector port; extend research discovery and Platform Queries/API only as specified. |
| Infrastructure | Add MT5 context projector, Artifact-to-Build SQLite lookup, and explicit read-only composition. |
| Visual | Add `visual/view_model.py`, `visual/app.py`, package marker, and one local launcher. |
| Tests | Focused semantic/query, adapter, composition, view-model, Streamlit, RCP-001 read-only, and architecture tests. |
| Documentation | Update `docs/architecture/visual-analytics.md`, `docs/roadmap/phases.md`, this plan's status, and minimal local run instructions in `docs/development.md`. |
| Dependencies | Add only Streamlit as a direct dependency and regenerate the exact lock. |

No schema file, migration, frontend project, Node toolchain, package manager,
asset pipeline, public endpoint contract, or separate service is expected.

## 13. Dependency impact

The standard library and current project capabilities are insufficient for the
selected browser interaction, accessible widgets, tabular layout, chart
rendering, session navigation, and headless visual integration testing without
substantial custom presentation infrastructure.

Add exactly one direct dependency in M2:

- `streamlit` — local browser presentation, built-in chart/table/widget
  primitives, session state, and `AppTest`.

Its transitive set must be captured in `requirements.lock`; no transitive
package may be promoted to direct use without separate justification. No direct
Plotly, Altair, pandas, NumPy, browser driver, pytest, or web framework
dependency is planned.

The app binds to loopback and assumes a trusted single-user local workstation.
Authentication/authorization and external hosting are not introduced. A future
external/multi-user deployment would require a separate security and production
serving decision.

## 14. Explicit out of scope

- Phase 09 MCP or any agent adapter;
- public HTTP/REST/GraphQL/gRPC Platform API;
- unrestricted Raw Evidence download or content preview;
- arbitrary Dataset payload access, search, filtering, or sorting;
- graph engine or generic reverse lookup;
- strategy-specific interpretation, telemetry protocol, trade/position
  reconstruction, equity reconstruction, MAE/MFE, or holding-time analysis;
- experiment comparison, ranking, optimization, Test Matrix, Monte Carlo, or
  other Phase 10 advanced analytics;
- execution controls, scheduling, or command UI;
- vector SUT implementation or any SUT modification;
- source snapshot retention, transitive MQL include discovery, or build changes;
- distributed deployment, cloud hosting, authentication, or authorization;
- new schemas, database migrations, or persisted semantic projections.

## 15. Risks

| Risk | Planned control |
|---|---|
| UI bypasses Platform API for convenient chart data | M1 closes required read gaps first; AST enforcement forbids storage/provider imports. |
| Provider-specific experiment fields leak into core | One provider adapter maps an exact extension contract into a neutral semantic projection. |
| Basic facts are duplicated or recomputed | Project the existing fixed execution-summary Dataset; do not create Analysis or UI formulas. |
| Visual labels overclaim available evidence | Permit only two justified charts; explicitly prohibit equity/distribution/path claims not supported by current results. |
| Streamlit reruns trigger unbounded/repeated work | Keep calls read-only and paged; explicitly manage cursors; no command access or analytical recomputation. |
| Streamlit dependency footprint grows | One direct dependency, exact lock, built-in components only, no competing UI/chart library. |
| Local server is exposed beyond the workstation | Bind `127.0.0.1`; document trusted local single-user scope and no production/public support. |
| RCP-001 is accidentally changed or rerun | Disposable database copy, before/after digest, command-denying composition, and no provider gate in M4. |
| Successful RCP-001 hides failure states | Portable fakes cover empty, incomplete, failed, cancelled, partial-evidence, unavailable, and safe-error paths. |
| Evidence Level 1 becomes a content browser | Explicit metadata fields, bounded pages, no bytes/preview/search/download. |

## 16. Acceptance criteria

Phase 08 is complete only when:

1. a local researcher can discover and select Runs through bounded Platform API
   pagination;
2. a selected Run shows its actual execution/evidence lifecycle and supported
   experiment context without provider types in semantic values;
3. the four execution-summary facts and all current bounded Analysis Core
   metrics come from integrity-verified canonical facts;
4. canonical Decimal/string values remain distinct from display formatting;
5. the first view contains the two justified charts and makes no unsupported
   equity, trade reconstruction, or full-distribution claim;
6. Dataset and Analysis drill-down remains metadata/bounded-result only;
7. canonical provenance is navigable without an out-of-band Build Record ID;
8. Evidence Level 1 metadata is bounded and no Evidence bytes/content are
   exposed;
9. empty, incomplete, failed, cancelled, partial-evidence, best-effort,
   unavailable, and safe-error states are explicit;
10. Visual Analytics imports only the Platform API/application-semantic boundary
    for research information and contains no analytical computation;
11. RCP-001 renders the approved acceptance facts through a disposable copy,
    with its canonical database digest unchanged and no lifecycle command or
    provider process executed;
12. strategy neutrality is machine-enforced and a future opaque SUT can use the
    same Run/configuration/metrics/Dataset/Analysis/provenance surface;
13. all portable, Streamlit, architecture, compile, dependency, and diff gates
    pass;
14. no Phase 09, Phase 10 capability, public API, schema, or persistence change
    is introduced;
15. the complete phase receives exactly one consolidated commit only after
    explicit owner approval.

## Settled answers to required planning questions

1. M1 adds bounded execution-summary content, neutral experiment context,
   verified Build identity on Run detail, one Artifact-to-Build discovery
   relation, and explicit read-only composition.
2. The four metrics come from the existing `execution-summary/0.1.0` Dataset via
   an explicitly bounded semantic projection; no new Analysis is created.
3. One infrastructure projector translates the exact MT5 extension contract
   into provider-neutral experiment fields.
4. Run detail resolves Artifact → Build Record through one query-port relation
   and verifies the Build through DataPlane.
5. `ResearchQueryPort` gains exactly
   `find_build_record_for_artifact(ArtifactId) -> BuildRecordId`.
6. The first visual view is a bounded Run selector plus one Run Overview.
7. Above the fold: lifecycle/evidence status, experiment context, core outcome
   cards, headline Analysis metrics, and reproducibility.
8. Charts: winning-versus-losing counts and realized-PnL summary statistics.
9. Drawdown is labeled event-balance maximum drawdown; no equity claim exists.
10. Phase 08 is read-only.
11. Technology: Streamlit local browser application.
12. It requires one direct dependency, Streamlit.
13. It serves presentation on loopback localhost.
14. The localhost transport renders UI and calls in-process PlatformApi; it is
    not a public or independently supported Platform API transport.
15. Phase 08 adds only bounded Evidence Object metadata (Level 1) in M3.
16. Unavailable values retain explicit availability state and display
    `Unavailable`, never zero or inferred data.
17. Failed/cancelled/partial Runs retain independent lifecycle, evidence, and
    reproducibility states; Analysis may be absent.
18. The UI preserves existing keyset cursors and page limits, with a cursor
    history for back navigation.
19. M4 copies RCP-001, validates through PlatformApi, hashes before/after, and
    denies all Commands; it never reruns research.
20. The UI consumes only neutral Run/configuration/outcome/Analysis/provenance
    values, so future opaque SUTs use the same surface without strategy concepts.
