# Phase 03 — Run & Evidence Pipeline Execution Plan

- Status: Completed; M1-M4 completed on 2026-08-10
- Scope: Phase 03 only
- Baseline: completed Phase 02 at `f63171092910adb4f885895f053172d09d46273b`
- Runtime: Python `>=3.14,<3.15`

## Objective and boundaries

Deliver the minimum controlled Strategy Tester path:

```text
accepted Artifact + Test Definition
-> ExecutionRequest
-> ExecutionProvider
-> MetaTrader 5 Strategy Tester
-> ExecutionProviderObservation
-> immutable Raw Evidence objects
-> sealed Raw Evidence Manifest 0.1.0
-> finalized Run Manifest 0.1.0
```

The application owns final Run outcome and evidence sealing. The provider only
reports observations and captured bytes. Preserve:

```text
OS process result
!= provider observation
!= final Run lifecycle outcome
!= evidence collection outcome
```

Reuse `AcceptedArtifact`, typed IDs, `RequestContext`,
`SchemaReferencedPayload`, UTC timestamps, SHA-256, reproducibility values,
application errors/logging, the local validator, and the existing evidence
domain model. Reuse `test-definition/0.1.0`, `run-manifest/0.1.0`,
`raw-evidence-manifest/0.1.0`, and `telemetry-envelope/0.1.0` where actually
applicable. Do not change them unless real execution proves an incompatibility.

Domain/application contain no filesystem, subprocess, Windows, MT5, tester,
report, log, or trading semantics. Provider facts remain in the adapter and
provider-namespaced payloads.

No dependency is planned: the Python standard library covers the current
process, filesystem, hashing, encoding, and test needs. Stop for an explicit
decision if safe process ownership proves otherwise.

Excluded from every milestone: persistence, Data Plane runtime, ingestion,
datasets, Analysis, metrics, optimization, ranking, Platform API, Semantic
Layer runtime, MCP, UI, live trading, queues, and distributed workers.

## M1 — Execution Boundary

- Status: Completed

### Objective and expected files

Add one fake-testable provider-neutral boundary. Do not invoke MT5, collect
bytes, seal evidence, or finalize a Run.

```text
src/ea_research_lab/domain/execution.py
src/ea_research_lab/application/execution.py
tests/test_execution_application.py
tests/architecture/test_dependencies.py
```

### Implementation and tests

- Add frozen neutral values only where existing provenance/evidence values are
  insufficient.
- Define `ExecutionRequest` with `RequestContext`, `RunId`, accepted Artifact,
  exact Test Definition payload, identified environment/configuration, and a
  positive timeout/deadline.
- Validate that Test Definition and Artifact references agree.
- Define one port:

  ```text
  ExecutionProvider.execute(ExecutionRequest) -> ExecutionProviderObservation
  ```

- Observation carries only neutral facts required later, opaque
  schema-referenced provider evidence, and zero or more immutable captured
  outputs represented as bytes plus media type and optional schema/provider
  namespace. It cannot finalize Run, create `RawEvidenceObject` identities, or
  seal evidence.
- Test frozen validation, invalid links/timeouts/payloads, fake-provider
  substitution, captured-output immutability, safe errors, and architecture
  vocabulary/import boundaries.

### Acceptance criteria

- the fake provider executes through one protocol method;
- no `Path`, subprocess type, MT5 state, tester configuration, or physical
  location crosses inward;
- no infrastructure module, provider schema, evidence identity/manifest, final
  Run, contract change, or dependency is introduced.

## M2 — MT5 Strategy Tester Adapter

- Status: Completed

### Objective and expected files

Reach one real controlled Strategy Tester execution behind M1. Resolve unknown
behavior with disposable observe → implement → test iterations inside M2, not a
separate probe phase.

```text
src/ea_research_lab/infrastructure/mt5_strategy_tester.py
tests/test_mt5_strategy_tester.py
tests/integration/test_mt5_strategy_tester.py
tests/architecture/test_dependencies.py
docs/development.md
schemas/mt5-strategy-tester-*/v0.x.schema.json # only if evidence requires it
```

### Implementation and tests

- Validate terminal executable identity and its explicitly configured main-mode
  data-root association. Treat that data root as provider-owned mutable state.
- Stage only accepted Artifact bytes and disposable tester inputs; never execute
  from or overwrite the project EA tree.
- Use adapter-owned argv, `shell=False`, bounded timeout/capture, and no arbitrary
  caller CLI arguments.
- Stop only the directly owned process; fail closed on detachment, reuse, agent,
  or child-process ambiguity.
- Keep paths, configuration files, process results, completion markers,
  encodings, logs, reports, diagnostics, and provider errors in the adapter.
- Return bounded observation plus immutable captured evidence bytes/metadata.
  Do not interpret trading or analytical meaning.
- Add a provider schema only when an observed serialized payload needs one; do
  not modify core schemas to carry MT5 facts.
- Portable tests cover invocation, paths, environment, ownership, timeout,
  ambiguity, bounded capture, safe logging/errors, and cleanup.
- Opt-in integration uses a known Phase 02 Artifact, disposable configuration,
  no live trading, and an externally provisioned Demo account precondition. It
  proves a conclusive execution; portable account provisioning and an expanded
  real-provider failure matrix remain unsupported until reproducible.

### Acceptance criteria

- a real Strategy Tester run is observed safely and separately from the portable
  gate;
- exit code alone cannot define provider success;
- observation contains sufficient bounded facts/bytes for M3;
- limitations are recorded without universal MT5 claims;
- no generic process runner, provider registry, workflow engine, persistence, or
  dependency is introduced.

## M3 — End-to-End Run and Evidence

- Status: Completed

### Objective and expected files

Compose Artifact, Test Definition, provider, immutable evidence, and existing
contracts into one in-memory application workflow.

```text
src/ea_research_lab/application/execution.py
src/ea_research_lab/domain/execution.py        # only proven neutral additions
tests/test_execution_workflow.py
tests/integration/test_mt5_strategy_tester.py
docs/domain/run.md                             # behavior clarification only
schemas/README.md                              # only if support changes
```

### Implementation and tests

- Use one explicit orchestration path; no manager, repository, collection
  framework, command bus, or pipeline engine.
- Map conclusive provider facts to the existing Run lifecycle; process completion
  alone is insufficient.
- For every captured byte sequence, allocate `RawEvidenceObjectId` and record
  exact byte length, media type, optional payload schema/provider namespace, and
  SHA-256 of those exact bytes. Return bytes immutably without physical paths.
- Explicitly seal one `RawEvidenceManifest` for each terminal collection outcome,
  including failed/cancelled and zero-object outcomes. Never mutate it; late
  evidence uses the existing prior-manifest revision.
- Define/document the exact deterministic UTF-8 JSON bytes hashed for the
  external `RawEvidenceManifestRef` digest.
- Finalize and locally validate Run Manifest 0.1.0 with Artifact, Test Definition
  revision, environment/configuration, final execution lifecycle status,
  reproducibility assessment/reasons, and matching sealed-manifest reference.
- Keep collection outcome in the evidence manifest, never as a new Run state.
- Test completed, failed, cancelled, timeout, partial/absent evidence,
  collection-failed, exact digests, sealing/immutability, late revision,
  provenance links, contract validation, cleanup, and safe logs.
- Real tests cover controlled completion and failure/timeout with disposable
  evidence.

### Acceptance criteria

- one call returns an immutable final Run Manifest, sealed evidence
  manifest/reference, captured bytes, and provider observation;
- all serialized documents validate and cross-references agree;
- failed/cancelled runs retain only evidence actually obtained;
- Run lifecycle and collection outcome remain independent;
- no replay guarantee exceeds provider evidence and no persistence or later-phase
  capability exists.

## M4 — Enforcement and Closure

- Status: Completed

### Objective and expected files

Prove provider isolation, contract validity, safety, and Phase 03 scope.

```text
tests/architecture/test_dependencies.py
tests/architecture/test_contract_neutrality.py
tools/check.py                                  # only if discovery misses a check
docs/architecture/execution-plane.md
docs/development.md
docs/domain/run.md
plans/active/phase-03-execution-plan.md
```

### Verification and acceptance criteria

- Enforce MT5/process/filesystem semantics only in the adapter/provider
  contracts; evolve the Phase 02 subprocess allowlist only for this adapter.
- Verify exact local contract resolution, supported historical versions, no
  network retrieval, immutable evidence, explicit sealing, cross-record
  provenance, safe logs/errors, workspace cleanup, and owned termination.
- Run authoritative portable and opt-in real MT5 gates separately, plus
  `compileall`, `pip check`, `git diff --check`, dependency/scope audit, and full
  diff review.
- Both gates pass; failures preserve available evidence; sealed evidence and Run
  documents remain immutable and valid; Artifact → Test Definition revision →
  Run → Evidence is reconstructable.
- No dependency or excluded/future capability exists. Mark Phase 03 completed
  only after owner approval and a clean checkpoint. Do not begin Phase 04.

## Provider risks tracked during execution

| Area | Question or required treatment |
|---|---|
| Tester-only safety | Which verified invocation guarantees Strategy Tester operation without live execution, account use, or shared terminal reconfiguration? |
| Isolation/staging | Which terminal/data layout safely owns the EX5, tester config, reports, logs, agents, and caches? |
| Process ownership | Does MT5 detach, reuse an instance, or spawn agents/children, and what can be terminated safely? |
| Completion | Which logs/reports/markers prove completion or failure when exit codes are inconclusive? |
| Evidence sealing | Where, when, and in what encoding are outputs complete; how are late writes, locks, truncation, and replacement detected? |
| Reproducibility | Which terminal, tester, history, symbol, model, range, input, and agent facts are available or provider-controlled? |
| Contract fit | Can current pre-stable contracts represent observations without leaking MT5 semantics into core fields? |

M2 and M3 resolved these risks sufficiently for the validated controlled
scenario without requiring another ADR or a provider-neutral boundary change.
The provider limitations recorded in `docs/development.md` remain in force.

## Closure outcome

The completed slice uses one `ExecutionProvider.execute()` port, one controlled
MT5 adapter, and one in-memory application orchestration path. Portable and
controlled real-provider gates verify provider isolation, exact-byte Raw
Evidence identity, immutable sealing, final Run validation, provenance links,
owned cleanup, and the absence of later-phase capabilities. Phase 04 was not
started.
