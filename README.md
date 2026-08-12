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

The repository currently contains the implemented Phase 01–06 vertical:
typed foundations, real controlled MetaEditor/MT5 adapters, immutable Build and
Run evidence, deterministic Dataset/Analysis products, and a local SQLite Data
Plane that persists and reconstructs the complete canonical chain with exact
schema, identity, digest, and provenance verification.

The Semantic Layer, Platform API, visual analytics, UI, and MCP remain future
phases. Phase 06 is implemented and awaiting final review/approval; Phase 07
has not started.

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
6. `plans/active/phase-06-execution-plan.md`
7. `docs/development.md`
