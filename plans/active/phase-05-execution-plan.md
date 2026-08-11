# Phase 05 — Analysis Core Execution Plan

- Status: Completed; M1-M4 completed
- Scope: Phase 05 only
- Baseline: completed Phase 04 at `1eda4a326d50b8844c7456a6672bcb07f505bcd9`
- Runtime: Python `>=3.14,<3.15`
- Git policy: no milestone commits; one consolidated Phase 05 commit only after M1–M4 are completed and approved

## Objective and boundaries

Expand the existing deterministic in-memory analytical slice only as far as
facts observed in captured Raw Evidence permit:

```text
sealed Raw Evidence
-> deterministic richer Dataset(s)
-> direct Analysis operations
-> deterministic Analysis Results
```

Phase 05 analyzes observed execution facts without interpreting strategy intent.
Provider-shaped parsing remains in infrastructure; Dataset and Analysis content
remain provider-neutral. A metric is available only when all facts required by
its explicit definition exist. Otherwise the result carries a bounded
unavailable reason; zero, inferred values, and semantically related substitutes
must not conceal missing facts.

The phase remains in memory. It adds no persistence, repository, database, Data
Plane runtime, generic transformation or analytics engine, provider framework,
API, Semantic Layer runtime, MCP, UI, optimization, ranking, recommendation,
experiment/matrix orchestration, telemetry, or distributed execution. No new
dependency is planned: `decimal`, `statistics` where suitable, `datetime`,
`html.parser`, `hashlib`, `json`, and `unittest` cover the expected work. Stop
and report a blocker before adding any dependency.

## Reused foundations and contracts

Phase 05 reuses without redesign:

- immutable sealed Raw Evidence and its exact-byte SHA-256 identities;
- `TransformationRequest`, `DatasetTransformer`, `transform_dataset`,
  `Dataset`, and `DatasetProvenance`;
- `AnalysisRequest`, immutable Analysis content/result values, and direct
  application Analysis operations;
- typed UUIDv7 entity IDs, `SchemaReferencedPayload`, `DefinitionVersion`,
  `RequestContext`, application errors, and local schema validation;
- `dataset-manifest/0.2.0` and `analysis-result/0.2.0` envelopes;
- the separate `execution-summary/0.1.0` aggregate Dataset and current summary
  analysis contracts.

Released historical schemas remain unchanged. New content schemas begin
pre-stable and are released only after their producer, consumer, semantics, and
fixtures have been exercised. Dataset-to-Dataset transformation is excluded
unless direct Raw Evidence derivation is empirically impossible; such a blocker
must be reported before changing the existing provenance model.

## M1 — Evidence Observation and Dataset Contracts

- Status: Completed

### Objective

Use one disposable, controlled MT5 Strategy Tester Run with known closed
execution activity to determine exactly which analytical facts are present in
the Raw Evidence already captured by the normal Run pipeline. Convert only
confirmed, provider-neutral facts into the minimum separate Dataset content
contracts. This observation is the first activity of M1, not a separate probe
phase.

### Exact empirical observation

1. Start from a clean working tree and the existing explicitly configured Demo,
   non-live, opt-in MT5 integration environment. Abort if process ownership or
   environment identity cannot be established.
2. Create the smallest test-only disposable EA/fixture capable of producing a
   known finite set of closed execution outcomes over a bounded historical test
   interval. Keep it outside the platform core and do not reuse project SUT
   strategy code.
3. Build and run it through the existing Build and Execution workflows, with
   live trading, DLL import, remote agents, cloud agents, optimization, and
   visual mode disabled.
4. Inspect only the immutable bytes returned as captured Raw Evidence by the
   completed workflow. Do not reread the original MT5 report or log filesystem
   as an analytical input.
5. Record the evidence object identity/digest, media type, provider namespace,
   encoding, report structure, external asset references, and the exact source
   location for each candidate fact. Compare observed records with the fixture's
   known activity without inferring absent relationships.
6. Classify individual records and their granularity, timestamps, realized PnL,
   commission/costs, swap, quantity/volume, direction, open/close relationship,
   and any balance/equity observations as `confirmed`, `unsupported`, or
   `ambiguous`, with the observation that supports the classification.
7. Define schemas only for the smallest coherent products composed entirely of
   confirmed facts. If no richer product is confirmed, close M1 with that
   limitation and reduce M2/M3 accordingly rather than inventing a contract.

### Provisional Dataset products

These are hypotheses, not approved names or structures:

- `realized-execution-series`: only if the evidence exposes individually
  identifiable realized outcomes with a provider-neutral meaning and a
  deterministic order;
- `account-value-series`: only if the evidence contains actual ordered balance
  and/or equity observations, not values reconstructed from aggregates or
  execution outcomes.

The observed MT5 granularity may instead require a different provider-neutral
name or no normalized series at all. `execution-summary` remains a separate
aggregate Dataset and must not be expanded into one generic catch-all Dataset.

### Expected files

```text
plans/active/phase-05-evidence-observation.md                 # concise evidence record
tests/fixtures/mt5/<minimal-known-activity-fixture>           # test-only, if retained
schemas/<confirmed-dataset-product>/v0.1.0.schema.json        # only after observation
tests/fixtures/schemas/valid/<confirmed-product>.json         # only for released schema
tests/fixtures/schemas/invalid/cases.json                     # focused contract failures
tests/test_contract_schemas.py
schemas/README.md
```

No schema path or product name above is authorized until observation confirms
its semantics. Existing envelopes and historical content contracts are not
edited.

### Tests and acceptance criteria

- the controlled fixture produces known activity without live trading and all
  owned MT5 processes are stopped;
- the observation record distinguishes direct observation from interpretation
  and classifies every candidate fact as confirmed, unsupported, or ambiguous;
- external HTML assets and evidence sufficiency are explicitly recorded;
- each released Dataset schema contains confirmed facts only, has deterministic
  ordering/timestamp semantics, validates positive and negative fixtures through
  local Draft 2020-12 resolution with explicit format checking, and remains
  provider- and strategy-neutral;
- `dataset-manifest/0.2.0`, `analysis-result/0.2.0`, and all historical schemas
  remain unchanged;
- no production transformation or Analysis capability is added in M1.

### Out of scope

Parsing implementation, Dataset production, analytical formulas, persistence,
additional provider matrices, and universal claims about MT5 report variants.

## M2 — MT5 Evidence Transformation

- Status: Completed

### Objective

Implement the smallest deterministic MT5 report transformation(s) needed to
produce the M1-confirmed Dataset products directly from sealed Raw Evidence.

### Expected files

```text
src/ea_research_lab/infrastructure/mt5_report.py
tests/test_mt5_report.py
tests/test_dataset_application.py                         # only for boundary invariants
tests/integration/test_mt5_strategy_tester.py
```

Add no domain or application abstraction unless the existing single-result
transformation boundary has a demonstrated representational blocker. Multiple
products may be produced by separate direct transformations over the same exact
sealed evidence.

### Contracts and implementation rules

- consume captured Raw Evidence bytes only and require exact membership in the
  sealed manifest;
- select required evidence explicitly by provider namespace/media type and
  reject missing, duplicate, ambiguous, oversized, unsupported-encoding,
  unsupported-layout, or unsupported-localization input;
- keep MT5 labels, HTML shape, and record mechanics inside infrastructure;
- use `Decimal` for financial values and never round-trip them through `float`;
- preserve timestamp timezone/offset and record semantics exactly as confirmed;
- define a total deterministic record ordering with an explicit tie-breaker;
- serialize canonical UTF-8 JSON, calculate SHA-256 over the exact bytes, and
  produce a valid Dataset Manifest 0.2.0 linked to the Run's sealed Raw Evidence
  Manifest and the exact transformation identity/version;
- do not use terminal/tester logs unless M1 confirms a specific stable fact that
  is absent from the preferred Strategy Tester report.

### Tests and acceptance criteria

- a fixed captured report fixture produces the exact confirmed Dataset content;
- repeated transformation of identical evidence, parameters, and version
  produces identical canonical bytes and digest;
- record ordering, decimal normalization, timestamp preservation, exact evidence
  hashing, and provenance links are tested;
- unsupported/ambiguous report variants fail closed without partial Dataset
  output or guessed semantics;
- the controlled real Run completes the chain from sealed Raw Evidence to every
  M1-approved richer Dataset with repeatable content digests;
- Raw Evidence and existing `execution-summary` output remain unchanged;
- no Dataset-to-Dataset transformation, persistence, or Analysis capability is
  introduced.

### Out of scope

Generic HTML/report parsers, normalization of unconfirmed deals/orders/positions,
synthetic account-value paths, and support for unobserved locale/layout variants.

## M3 — Analysis Core

- Status: Completed

### Objective

Extend the existing direct Analysis boundary with only the formulas supported by
the current `execution-summary` and the richer Datasets actually produced by M2.
Keep formulas versioned, deterministic, in memory, and independent of provider
and SUT semantics.

### Target analyses

The current execution summary supports these aggregate definitions:

- expected payoff: `net_profit / total_trades`;
- profit factor: `gross_profit / abs(gross_loss)`;
- average winning result: `gross_profit / winning_trades`;
- average losing magnitude: `abs(gross_loss) / losing_trades`;
- payoff ratio: `average_winning_result / average_losing_magnitude`;
- gross profit relative to initial deposit:
  `gross_profit / initial_deposit`;
- gross loss magnitude relative to initial deposit:
  `abs(gross_loss) / initial_deposit`.

Every zero or unavailable denominator yields a bounded unavailable reason.
Existing net return, win/loss rates, baseline deltas, and structural
comparability remain supported and unchanged unless a new exact contract
version is required.

M2 evidence supports only these additional analyses:

- realized execution-outcome distribution: count, minimum, maximum, arithmetic
  mean, median, and mean absolute deviation around the arithmetic mean;
- longest positive and negative realized-event streaks in confirmed source
  order, with zero outcomes counted separately and breaking both streaks;
- maximum observed event-balance drawdown amount and rate over running peaks in
  the event-indexed balance sequence.

These facts do not establish complete trades, positions, continuous paths,
equity, holding duration, or periodic return sampling. No such analysis is
implemented.

Sharpe, Sortino, volatility, rolling statistics, and periodic returns remain
unavailable unless M1/M2 unexpectedly establish a rigorously timestamped return
series and sampling rule. They are not default Phase 05 targets.

### Expected files

```text
src/ea_research_lab/application/analysis.py
tests/test_analysis_core.py
schemas/execution-core-analysis-parameters/v0.1.0.schema.json
schemas/execution-core-analysis-result/v0.1.0.schema.json
tests/fixtures/schemas/valid/execution-core-analysis-parameters.json
tests/fixtures/schemas/valid/execution-core-analysis-result.json
tests/fixtures/schemas/invalid/cases.json
schemas/README.md
docs/domain/analysis.md                                     # implemented definitions only
```

Names and shapes for new Analysis content contracts remain provisional until M2
fixes the actual inputs. Reuse the existing immutable Analysis Result envelope,
content digest, provenance, and direct operation pattern; do not add an engine,
registry, plug-in system, formula catalog, or new dependency.

### Tests and acceptance criteria

- all implemented formulas have explicit definitions, Decimal precision and
  rounding, canonical output, and deterministic zero-denominator behavior;
- repeated analysis of identical Dataset bytes, definition/version, parameters,
  and computation environment produces identical result bytes/digest;
- each metric is represented as available with its value or unavailable with a
  bounded reason; missing facts never become zero, NaN, infinity, or inferred
  observations;
- conditional distribution, sequence, duration, bucket, and account-value tests
  exist only for capabilities justified by M1/M2 evidence;
- Analysis Results validate against their exact content schema and
  `analysis-result/0.2.0`, bind exact input Dataset IDs/digests, and preserve the
  full in-memory provenance chain;
- no ranking, recommendation, optimization, strategy interpretation,
  presentation, persistence, or future-phase capability exists.

### Out of scope

Generic statistics infrastructure, inferential statistics, stability scoring,
research recommendations, synthetic curves/returns, and multi-run orchestration.

## M4 — Enforcement and Closure

- Status: Completed

### Objective

Machine-enforce the Phase 05 boundaries, prove the controlled vertical slice,
align only affected documentation, and close the phase without adding runtime
capability.

### Expected files

```text
tests/architecture/test_dependencies.py
tests/architecture/test_contract_neutrality.py
tests/integration/test_mt5_strategy_tester.py
tools/check.py                                      # only if current discovery misses work
docs/architecture/analysis-plane.md
docs/domain/dataset.md
docs/domain/analysis.md
docs/development.md                                 # only for changed execution instructions
plans/active/phase-05-execution-plan.md
```

### Tests and acceptance criteria

- architecture tests enforce provider parsing isolation, provider-neutral
  Dataset/Analysis vocabulary, strategy neutrality, and absence of excluded
  capabilities without a new enforcement framework;
- fixtures and tests prove deterministic Dataset and Analysis bytes/digests,
  exact Decimal behavior, availability/unavailability rules, local exact schema
  resolution, immutable historical contracts, and reconstructible provenance;
- the smallest controlled opt-in real MT5 integration proves, for every
  evidence-supported product, `Run -> Raw Evidence -> Dataset -> Analysis
  Result`, repeatable content identity, and no unrelated MT5 processes left;
- `python tools/check.py`, full portable unittest discovery, controlled real MT5
  integration, `compileall`, `pip check`, and `git diff --check` all pass;
- the complete diff contains Phase 05 work only; no dependency, persistence,
  experiment/matrix capability, optimization, ranking, Platform API, Semantic
  Layer runtime, MCP, UI, telemetry, or later-phase scaffolding exists;
- M1–M4 and Phase 05 are marked Completed only after all acceptance criteria and
  owner approval; no commit is created until separately authorized, after which
  exactly one consolidated Phase 05 commit is permitted.

### Out of scope

Any new analytical capability, unresolved provider variant, or Phase 06 work.

## Major risks

| Risk | Required treatment |
|---|---|
| The report exposes provider records whose deal/order/position meanings cannot be normalized safely | Keep them provider-namespaced or mark them ambiguous; release no normalized Dataset for them. |
| The known-activity fixture does not produce representative closed outcomes | Adjust only the disposable fixture or bounded historical interval and repeat M1; do not weaken semantic proof. |
| HTML rows depend on external assets or omit needed facts | Record the limitation; capture no uncaptured asset implicitly and omit the unsupported Dataset/metric. |
| Ordering or timestamps are duplicated, localized, or timezone-ambiguous | Require an observed total ordering/tie-breaker and explicit timestamp semantics or mark sequence/time analyses unavailable. |
| Aggregate report values and detailed records disagree | Preserve both observed products, fail analytical integrity checks where required, and do not silently reconcile them. |
| Decimal scale or statistical context changes content identity | Fix formula version, precision, rounding, canonical strings, and population-versus-sample definition in contract tests. |
| Richer products tempt Dataset-to-Dataset provenance or one oversized schema | Derive each minimum product directly from Raw Evidence and retain `execution-summary` separately. |

## Roadmap follow-up

Durable Data Plane runtime and persistence ownership must be resolved explicitly
before Phase 06 Platform API planning. Phase 05 records this as a non-blocking
roadmap follow-up and does not implement or design the solution.

## Completion rule

Phase 05 completes only when M1 evidence justifies every released fact, M2 and
M3 prove deterministic content and explicit unavailability, M4 proves the real
vertical slice and portable gates, all historical contracts remain immutable,
and the owner approves the cumulative diff. No milestone commit is allowed;
exactly one consolidated Phase 05 commit may be created only after separate
authorization.
