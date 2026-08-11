# Phase 04 — Dataset & Analysis Execution Plan

- Status: Completed
- Scope: Phase 04 only
- Baseline: completed Phase 03 at `09ed6004c141b45df90f941370a9221cf7351aea`
- Runtime: Python `>=3.14,<3.15`
- Git policy: one consolidated Phase 04 commit after complete phase approval

## Objective and boundaries

Deliver the smallest deterministic analytical slice:

```text
sealed Raw Evidence
-> deterministic transformation
-> execution-summary Dataset
-> deterministic summary/comparison analysis
-> comparable Analysis Result
```

Raw Evidence remains immutable execution fact. A Dataset is a derived,
schema-identified representation. An Analysis Result is a deterministic
computation over identified Dataset content. MT5 parsing remains infrastructure;
dataset and analysis contracts remain provider-neutral and strategy-agnostic.

Determinism applies to canonical content bytes and their SHA-256 identity. New
UUIDv7 entity IDs and creation timestamps are intentionally not deterministic.
Tests compare content and digests, not independently allocated entity IDs or
envelope timestamps.

No milestone may add persistence, repositories, a Data Plane runtime, generic
ETL/analytics frameworks, optimization, ranking, API, Semantic Layer runtime,
MCP, UI, queues, or distributed processing. No dependency is planned: `html.parser`,
`decimal`, `hashlib`, `json`, and `unittest` cover the presently known need.
Stop before adding a dependency.

## Initial vertical slice

The first Dataset is one provider-neutral execution summary per sealed evidence
manifest. It is derived only from the captured MT5 tester report identified by
its provider namespace and `text/html` media type. Its initial content is:

- account currency, with Run identity retained through provenance;
- initial deposit;
- total net profit, gross profit, and gross loss;
- total, profitable, and losing trade counts.

Only fields observed and unambiguously mapped from the controlled report enter
the contract. Decimal quantities use canonical decimal strings; counts use
integers. Logs are not transformation input for this Dataset, and no trade
intent, signal, entry/exit rationale, or SUT-specific meaning is inferred.

The first analysis definition accepts one or more execution-summary Datasets
and computes, per Run:

- net return (`net_profit / initial_deposit`);
- win rate (`winning_trades / total_trades`);
- loss rate (`losing_trades / total_trades`).

For two or more inputs it also reports deterministic deltas from an explicitly
declared baseline Dataset and whether the inputs are structurally directly
comparable. Direct comparability requires the same exact Dataset content schema,
transformation identity/version, and account currency. It does not claim that
different experiments are scientifically equivalent and does not rank Runs.
Zero denominators produce an explicit unavailable value/reason, never NaN or
infinity.

## M1 — Dataset Transformation Boundary

- Status: Completed

### Expected files

```text
src/ea_research_lab/domain/dataset.py
src/ea_research_lab/application/dataset.py
tests/test_dataset_application.py
tests/architecture/test_dependencies.py
```

### Scope

- Add immutable provider-neutral Dataset content/result values and one narrow
  transformation port or callable boundary; do not create an ETL framework or
  transformer registry.
- Accept a sealed `RawEvidenceManifest`, its exact reference, and matching
  immutable evidence bytes. Reject missing, duplicate, extra, digest-mismatched,
  or wrong-Run objects before transformation.
- Reuse `DatasetId`, `DatasetProvenance`, `TransformationId`,
  `DefinitionVersion`, `SchemaReferencedPayload`, `Sha256Digest`, and UTC values.
- Define canonical JSON content bytes with UTF-8, sorted keys, compact separators,
  finite values only, and semantic array ordering. Hash those exact bytes.
- Keep Dataset content/digest separate from entity identity and from the Dataset
  Manifest envelope.
- Produce and locally validate `dataset-manifest/0.1.0` while its current shape
  remains sufficient.

### Acceptance criteria

- identical inputs, transformation version, and parameters produce identical
  content bytes and SHA-256 across repeated calls;
- Dataset IDs and timestamps may differ without weakening content determinism;
- the manifest references the exact sealed input and transformation metadata;
- raw bytes and sealed manifests are not mutated;
- a fake transformer proves boundary substitution without provider vocabulary;
- no filesystem, MT5, persistence, analysis, or later-phase capability exists.

## M2 — MT5 Evidence Transformer

- Status: Completed

### Expected files

```text
src/ea_research_lab/infrastructure/mt5_report.py
tests/test_mt5_report.py
tests/integration/test_mt5_strategy_tester.py
schemas/execution-summary/v0.1.0.schema.json               # proven content shape
schemas/dataset-manifest/v0.2.0.schema.json                # only if required below
schemas/README.md                                           # only for released schemas
```

### Scope

- Inspect the smallest controlled real report needed to confirm encoding, table
  structure, labels, decimal conventions, and the initial field set.
- Parse only the explicitly captured report with standard-library HTML parsing;
  fail visibly on unsupported layout, localization, ambiguity, or duplicates.
- Keep HTML labels, encoding, and MT5 structure inside the adapter. Return only
  the proven provider-neutral execution-summary content.
- Use `Decimal`; never parse financial quantities through binary floating point.
- Validate the Dataset content against its exact local pre-stable schema and
  prove the controlled Phase 03 Run transforms end to end.
- Treat the absence of a Dataset content digest in
  `dataset-manifest/0.1.0` as a contract checkpoint. If the real product cannot
  bind its exact content identity through the manifest, add immutable
  `dataset-manifest/0.2.0` with the minimum digest reference and retain 0.1.0
  unchanged. Do not alter any released schema in place.

### Acceptance criteria

- the controlled report produces the declared execution-summary Dataset;
- report bytes and locale/layout errors fail explicitly rather than guessing;
- exact repeated report bytes produce identical canonical Dataset bytes/digest;
- non-report evidence and operational logs are not silently ingested;
- provider-specific terms do not enter domain/application contracts;
- any schema evolution is justified by the observed producer/consumer and keeps
  historical versions locally resolvable.

## M3 — Analysis Boundary and Comparable Result

- Status: Completed

### Expected files

```text
src/ea_research_lab/domain/analysis.py
src/ea_research_lab/application/analysis.py
tests/test_analysis_application.py
schemas/execution-summary-analysis-parameters/v0.1.0.schema.json
schemas/execution-summary-analysis-result/v0.1.0.schema.json
schemas/README.md
```

The two content schemas are released only after the implemented parameter and
result shapes are exercised. Existing `analysis-result/0.1.0` is reused and is
not edited in place.

### Scope

- Add one direct analysis operation, not an engine, registry, plug-in system, or
  formula catalog.
- Reuse `AnalysisProvenance`, `AnalysisDefinitionId`, `AnalysisResultId`,
  `DefinitionVersion`, computation-environment identity,
  `SchemaReferencedPayload`, timestamps, and the existing Analysis Result
  contract.
- Compute the declared ratios and optional baseline deltas with `Decimal`,
  explicit precision/rounding, deterministic Dataset ordering, and explicit
  zero-denominator outcomes.
- Allocate result identity and timestamp outside deterministic result content.
- Validate the exact parameter, result-content, and Analysis Result documents
  through local URN resolution only.
- Return an immutable in-memory result with the Analysis Result envelope,
  canonical result bytes/digest, and enough linked Dataset products to traverse
  provenance. Add no persistence or query surface.

### Acceptance criteria

- repeated computation over identical Dataset bytes, definition version,
  parameters, and computation environment produces identical result bytes/digest;
- one Run produces the three declared metrics; two or more Runs produce ordered
  baseline deltas and an explicit comparability decision/reasons;
- comparison never becomes ranking or strategy evaluation;
- the Analysis Result references exact input Dataset IDs, analysis definition,
  content digests, version, parameters, and computation environment and
  validates locally;
- the complete Run-to-result provenance chain is reconstructible in memory;
- no provider names, filesystem/process types, or presentation logic enter core
  analysis.

## M4 — Enforcement and Closure

- Status: Completed

### Expected files

```text
tests/architecture/test_dependencies.py
tests/architecture/test_contract_neutrality.py
tools/check.py                                      # only if current discovery misses work
docs/architecture/analysis-plane.md                 # behavior alignment only
docs/domain/dataset.md
docs/domain/analysis.md
docs/development.md
plans/active/phase-04-execution-plan.md
```

### Scope and acceptance criteria

- Machine-enforce provider parsing isolation, provider-neutral Dataset/analysis
  vocabulary, local exact contract resolution, deterministic content checks,
  and absence of excluded capabilities without a new enforcement framework.
- Verify the chain: Run -> sealed Raw Evidence Manifest -> exact Raw Evidence
  Objects -> transformation identity/version -> Dataset content identity ->
  analysis definition/version/parameters -> Analysis Result.
- Run the authoritative portable gate, full unittest discovery, the existing
  controlled MT5 vertical integration extended only through this slice,
  `compileall`, `pip check`, and `git diff --check`.
- Confirm no dependency, persistence, API, UI, MCP, optimization, ranking,
  workflow engine, or strategy semantics were introduced.
- Mark M1-M4 and Phase 04 completed only after all checks and owner approval.
  Keep every milestone change uncommitted until then; create exactly one
  consolidated Phase 04 commit only when separately authorized.

## Major risks

| Risk | Required treatment |
|---|---|
| MT5 report layout, encoding, or localization varies | Validate the controlled observed shape; fail unsupported variants explicitly and make no universal provider claim. |
| Dataset Manifest 0.1.0 does not bind content digest | Prove the need with the first real Dataset, then add 0.2.0 only if exact content identity cannot otherwise be represented. |
| Decimal normalization changes bytes or arithmetic | Define one canonical decimal representation and explicit analysis precision/rounding; prohibit floats, NaN, and infinity. |
| “Comparable” is mistaken for experimental equivalence | Limit the result to declared structural compatibility and deterministic metric deltas; emit reasons and make no research-validity claim. |
| Partial/failed evidence is treated as complete | Validate exact manifest membership and required report presence; fail visibly when the transformation's evidence requirements are unmet. |

## Completion record

M1 through M4 and Phase 04 are complete and approved for the single
consolidated Phase 04 checkpoint. No Phase 05 planning or implementation has
started.
