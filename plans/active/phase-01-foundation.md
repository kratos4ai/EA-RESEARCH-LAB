# Phase 01 — Foundation

## Objective

Create the minimum architectural foundation required for later build, execution, analytics, visual, and MCP capabilities without prematurely implementing those capabilities.

## Scope

Phase 01 includes:

- repository/module structure;
- domain primitives;
- identifier conventions;
- initial machine-readable schemas;
- configuration conventions;
- logging conventions;
- provenance model;
- error model;
- test infrastructure;
- architecture enforcement tests where practical;
- documentation baseline.

## Required domain primitives

At minimum:

- Artifact identity
- TestDefinition identity
- Run identity
- Dataset identity
- Analysis identity/version
- provenance references

These may begin as interfaces/data structures/contracts rather than complete services.

## Required schemas

Initial versioned schemas:

- Artifact Manifest
- Run Manifest
- Test Definition
- Telemetry Envelope
- Analysis Result

## Out of scope

Do not implement:

- MetaEditor compilation;
- Strategy Tester execution;
- actual telemetry emission from an EA;
- analytics algorithms;
- database persistence;
- web UI;
- MCP server;
- optimization engine;
- scheduling;
- distributed execution.

## Architectural constraints

- no strategy-specific concepts;
- no MetaTrader types in core domain contracts;
- no storage-specific types in semantic/domain contracts;
- schemas are versioned from the beginning;
- IDs are opaque to consumers;
- raw evidence is modeled as immutable;
- analysis outputs carry analysis version and provenance.

## Suggested milestones

### M1 — Repository skeleton

Create module/package boundaries and testing foundation.

### M2 — Core identifiers and value objects

Define opaque IDs and common metadata.

### M3 — Schema contracts

Implement initial schemas and validation tests.

### M4 — Provenance model

Define traceability relationships between source, artifact, run, dataset, and analysis.

### M5 — Quality gates

Automated checks for formatting, typing/linting where applicable, tests, and schema validation.

### M6 — Documentation review

Ensure implementation matches ADRs and architecture documentation.

## Acceptance criteria

Phase 01 is complete when:

- the repository has explicit architectural boundaries;
- the core model contains no strategy semantics;
- initial contracts are machine-validatable;
- schema tests pass;
- provenance is represented explicitly;
- future MetaTrader and MCP integrations can be implemented as adapters;
- no future-phase runtime capability was implemented accidentally.

## Codex instruction for this phase

Before implementation:

1. Read `AGENTS.md`.
2. Read `docs/vision.md`.
3. Read `docs/architecture/overview.md`.
4. Read `docs/architecture/principles.md`.
5. Read all accepted ADRs.
6. Inspect initial schemas.
7. Produce a detailed execution plan.

Do not implement until the execution plan has been reviewed.
