# EA Research Lab

EA Research Lab is a **strategy-agnostic research and execution platform** for MetaTrader 5 Expert Advisors.

Its purpose is to provide a reproducible environment for:

- building and versioning EA artifacts;
- defining and executing test runs;
- collecting immutable evidence;
- reconstructing and analyzing results;
- comparing runs and datasets;
- exposing a semantic query API;
- enabling visual exploration;
- enabling agentic exploration through MCP.

The platform treats every Expert Advisor as a **System Under Test (SUT)**.

## Current implementation status

The repository currently contains the Phase 01 foundation: typed domain values, immutable provenance and evidence models, exact versioned schemas with local validation, transport-neutral request context, minimal configuration, structured operational logging, and automated architecture checks.

BuildProvider, ExecutionProvider, MetaTrader/MetaEditor integration, persistence, analytical computation, Platform API runtime, UI, and MCP remain later-phase work. Phase 01 is complete.

## Core principle

The platform understands:

`artifact / configuration / execution / telemetry / dataset / analysis / provenance`

The platform does **not** understand:

`strategy / signal / market thesis / entry logic / exit logic / trading intent`

## Start here

1. `docs/vision.md`
2. `docs/architecture/overview.md`
3. `docs/architecture/principles.md`
4. `docs/roadmap/target-state.md`
5. `docs/roadmap/phases.md`
6. `plans/active/phase-01-foundation.md`
7. `plans/active/phase-01-execution-plan.md`
8. `docs/development.md`
