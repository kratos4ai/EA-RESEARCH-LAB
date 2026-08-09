# ADR-0006 — MetaTrader behind an Execution Provider

- Status: Accepted

## Context

Direct coupling of orchestration/business logic to MetaTrader would leak platform-specific behavior into the core.

## Decision

MetaTrader 5 Strategy Tester is accessed through an ExecutionProvider abstraction.

MetaEditor compilation is accessed through a BuildProvider abstraction.

The Control Plane coordinates builds and runs through these provider ports and never calls MetaEditor or MetaTrader directly.

Adapters translate provider-specific observations into provider-neutral execution contracts only when the mapping preserves meaning. Unmapped observations remain provider-namespaced raw evidence and do not define core domain or semantic contracts.

Providers report available environment metadata and explicit limitations. The platform records reproducibility levels and must not infer deterministic replay guarantees from the abstraction itself.

## Consequences

- platform core remains testable;
- external technology is replaceable/mockable;
- adapter translation code is required;
- some provider evidence remains namespaced;
- provider limitations remain visible in reproducibility provenance.
