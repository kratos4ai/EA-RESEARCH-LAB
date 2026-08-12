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

Extend the Phase 04 vertical slice with provider-neutral realized execution
events, event-indexed balances, deterministic aggregate metrics, a bounded
realized-event distribution, simple ordered-event sequences, and observed
event-balance drawdown. Broader timeseries, stability, and comparison remain
later work when their required evidence semantics exist.

## Phase 06 — Data Plane & Persistence

Persist the implemented canonical research chain behind Data Plane ports while
preserving immutable content, exact schema versions, storage integrity, and
provenance across process restarts.

## Phase 07 — Semantic Layer & Platform API

Define stable semantic contracts for Run, Artifact, Dataset, Metric, Timeseries,
Distribution, Analysis, and Comparison, and expose bounded retrieval through
the Query capability of the Platform API.

## Phase 08 — Visual Analytics

Build the research workbench over the Query capability of the Platform API and its semantic contracts.

## Phase 09 — MCP Adapter

Expose read-only semantic exploration to Codex/agents.

Later add controlled command tools.

## Phase 10 — Advanced Research Analytics

Bootstrap, Monte Carlo, sensitivity, confidence intervals, clustering, regime/time segmentation, and large experiment matrices.

## Rule

Later-phase concerns may influence contracts and boundaries, but must not be implemented prematurely.
