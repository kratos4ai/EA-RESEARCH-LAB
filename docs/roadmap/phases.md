# Roadmap Phases

The target architecture is intentionally implemented incrementally.

## Phase 01 — Foundation

Establish repository architecture, domain primitives, schemas, configuration, logging, test infrastructure, and provenance conventions.

No MetaTrader automation yet.

## Phase 02 — Build & Artifact Pipeline

Implement MetaEditor build adapter, artifact hashing, immutable artifact manifest, and build orchestration.

## Phase 03 — MetaTrader Execution

Implement Strategy Tester execution adapter, test definition execution, run lifecycle, and collection of tester outputs.

## Phase 04 — Dataset & Initial Analysis

Implement the in-memory deterministic path from sealed Raw Evidence to one
provider-neutral Dataset and the initial execution-summary metrics/comparison
result. Persistence and broader ingestion formats remain deferred.

## Phase 05 — Analysis Core

Extend the Analysis Plane beyond the Phase 04 vertical slice, beginning with:

- integrity;
- provider-neutral execution metrics;
- timeseries;
- distributions.

Then extend to stability and comparison.

## Phase 06 — Semantic Layer & Platform API Query Capability

Define stable semantic contracts for Run, Artifact, Dataset, Metric, Timeseries, Distribution, Analysis, and Comparison, and expose bounded retrieval through the Query capability of the Platform API.

## Phase 07 — Visual Analytics

Build the research workbench over the Query capability of the Platform API and its semantic contracts.

## Phase 08 — MCP Adapter

Expose read-only semantic exploration to Codex/agents.

Later add controlled command tools.

## Phase 09 — Advanced Research Analytics

Bootstrap, Monte Carlo, sensitivity, confidence intervals, clustering, regime/time segmentation, and large experiment matrices.

## Rule

Later-phase concerns may influence contracts and boundaries, but must not be implemented prematurely.
