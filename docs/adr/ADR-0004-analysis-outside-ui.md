# ADR-0004 — Analysis outside the UI

- Status: Accepted

## Context

Visual analytics will become a major user interface, but statistical logic embedded in frontend components would create divergence and weak reproducibility.

## Decision

All analytical computation belongs to the Analysis Plane.

The UI may filter, navigate, request, and visualize analytical data but must not own analytical formulas.

The Data Plane owns persistence and storage/data integrity, including hashes, schema validity, manifest consistency, and detection of missing or corrupted stored objects. It may store analytical outputs but does not compute them.

The Analysis Plane owns analytical/run integrity, deterministic transformations, metrics, comparisons, and other analytical calculations.

The Semantic Layer defines vocabulary, models, projections, and contracts for analytical results. It does not compute results or retrieve them. Bounded retrieval belongs to application/query services exposed through the Platform API Query capability.

## Consequences

- a single analytical truth serves UI, API, and agents;
- frontend remains simpler;
- storage validation and analytical validity remain distinct;
- backend analysis, semantic, and query responsibilities must remain explicit.
