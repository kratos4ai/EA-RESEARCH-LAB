# Phase 01 — Foundation

- Status: Completed

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

Phase 01 versioned contracts:

- Common values
- Build Record
- Artifact Manifest
- Test Definition
- Run Manifest
- Raw Evidence Manifest
- Dataset Manifest
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

## Approved milestone execution

The authoritative milestone sequence, scope, and status are maintained in `plans/active/phase-01-execution-plan.md`. This foundation brief does not redefine that approved execution plan.

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
