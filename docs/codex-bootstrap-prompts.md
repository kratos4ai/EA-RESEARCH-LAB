# Codex Bootstrap Prompts

## Prompt 1 — Architectural review

Use this before implementation:

> We are starting EA Research Lab.
>
> Read `AGENTS.md`, `docs/vision.md`, `docs/architecture/overview.md`,
> `docs/architecture/principles.md`, all accepted ADRs, and
> `docs/roadmap/target-state.md`.
>
> Do not implement code.
>
> Critically review the architecture for contradictions, hidden coupling,
> missing responsibilities, weak boundaries, or decisions that would make
> phased evolution difficult.
>
> Preserve as an absolute requirement that the platform remains agnostic to
> the internal trading logic of the EA.
>
> At the end, propose only architectural changes that are genuinely necessary.
> Do not expand scope.

## Prompt 2 — Phase 01 planning

After architectural review is accepted:

> Read `plans/active/phase-01-foundation.md` and every document it references.
>
> Do not implement yet.
>
> Produce a detailed execution plan for Phase 01 including:
> dependencies, module/package structure, files to create, contracts,
> implementation order, tests, risks, and completion criteria.
>
> Do not implement concerns from later phases.
> If you believe a new durable architectural decision is required, propose an ADR.

## Prompt 3 — Phase 01 implementation

After the execution plan is approved:

> Execute the approved Phase 01 plan.
>
> Work incrementally and run relevant tests after each meaningful milestone.
> Do not introduce undocumented architectural decisions.
> If a new durable structural decision is required, stop and propose an ADR first.
>
> At the end:
> - run all quality gates;
> - review the complete diff;
> - update affected documentation;
> - update the active plan with completion status;
> - report remaining risks or intentional deferrals.
