# EA Research Lab — Codex Instructions

## Mission

EA Research Lab is a strategy-agnostic platform for building, versioning, executing, reproducing, collecting, analyzing, comparing, querying, and visually exploring MetaTrader 5 Expert Advisor executions.

Treat every EA as a **System Under Test (SUT)**. The platform must not infer, encode, or depend on the EA's internal trading strategy.

## Architectural invariants

1. The platform MUST remain strategy-agnostic.
2. MetaTrader 5 is an external execution provider, not the platform core.
3. Raw execution data is immutable.
4. Every artifact and run must be reproducible and traceable.
5. Analysis belongs to the Analysis Plane and must be deterministic whenever possible.
6. The UI must not contain analytical business logic.
7. The Platform API is the application contract.
8. MCP is an adapter over the Platform API, never a direct integration with storage or MetaTrader.
9. Codex is a client of the platform, not a runtime dependency.
10. Every analytical result must preserve provenance:
    source code → artifact → run → dataset → analysis.
11. External technologies must be isolated behind adapters.
12. Large raw datasets must not be sent to LLM context by default.
13. Prefer progressive investigation: summary → comparison → focused drill-down → raw evidence only when necessary.
14. Durable architectural decisions require an ADR.

## Repository navigation

Before architectural changes, read:

- `docs/vision.md`
- `docs/architecture/overview.md`
- `docs/architecture/principles.md`
- relevant files under `docs/adr/`

Before changing a specific area:

- Control plane: `docs/architecture/control-plane.md`
- MetaTrader execution: `docs/architecture/execution-plane.md`
- Persistence/data contracts: `docs/architecture/data-plane.md`
- Analytics/statistics: `docs/architecture/analysis-plane.md`
- Semantic/query model: `docs/architecture/semantic-layer.md`
- Visual analytics: `docs/architecture/visual-analytics.md`
- MCP: `docs/architecture/mcp-integration.md`

Before changing domain concepts, read the corresponding file under `docs/domain/`.

Before changing serialized contracts, inspect `schemas/`.

For current implementation scope, read `plans/active/`.

## Working method

For non-trivial work:

1. Investigate the relevant code and documentation.
2. Confirm the task belongs to the active phase.
3. Produce or update an execution plan before broad implementation.
4. Implement incrementally.
5. Add or update tests with each behavioral change.
6. Run relevant quality gates.
7. Review the final diff for architectural drift.
8. Update documentation when behavior or architecture changed.

Do not implement future phases merely because they appear in the target architecture.

Do not introduce architectural decisions silently. If implementation requires a durable new decision, propose an ADR first.

## Definition of done

Work is not complete until:

- code or documentation is consistent with architectural invariants;
- relevant tests pass;
- machine-readable contracts are updated when applicable;
- affected documentation is updated;
- no strategy-specific assumptions entered the platform core;
- provenance and reproducibility are preserved.
