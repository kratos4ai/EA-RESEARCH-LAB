# ADR-0001 — Strategy-agnostic platform

- Status: Accepted

## Context

The platform must support heterogeneous Expert Advisors without coupling infrastructure to a particular research hypothesis or trading model.

## Decision

Every EA is treated as an opaque System Under Test.

The platform may understand inputs, execution metadata, outputs, telemetry envelopes, and analytical results, but must not encode strategy semantics in the core domain.

Core contracts may preserve typed SUT inputs and schema-versioned telemetry payloads without interpreting their trading meaning. SUT-specific payloads remain opaque to the core.

Provider-specific observations must either:

- be translated by an adapter into a genuinely provider-neutral execution fact; or
- remain explicitly provider-namespaced evidence.

Provider or SUT field names do not become shared core vocabulary merely because they are available in a report or telemetry stream. A core concept must remain meaningful without knowing the SUT's strategy intent, signals, entry/exit rationale, market thesis, indicator assumptions, or strategy-specific optimization objective.

## Consequences

Positive:

- reusable execution/research infrastructure;
- lower coupling;
- easier evolution of EAs;
- analytical capabilities remain generic.

Negative:

- strategy-specific interpretation must live outside the core platform;
- some provider and SUT payloads remain opaque or namespaced rather than normalized into shared contracts.
