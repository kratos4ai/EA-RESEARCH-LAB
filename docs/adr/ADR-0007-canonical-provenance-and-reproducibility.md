# ADR-0007 — Canonical provenance and reproducibility levels

- Status: Accepted

## Context

Research results are not reproducible or auditable unless build, execution, evidence, transformation, and analysis identities form one traceable contract. External execution providers may also be unable to guarantee deterministic replay.

## Decision

The canonical provenance chain is:

```text
source revision
-> build record
-> artifact
-> test-definition revision
-> environment/configuration
-> run
-> sealed raw evidence manifest
-> transformation version
-> dataset
-> analysis definition/version/parameters
-> result
```

The implementation may represent this as a graph. Every result must retain stable references sufficient to traverse the complete chain. Serialized nodes carry schema identity/version, and immutable artifacts and evidence use content identity where practical.

Execution reproducibility is assessed as one of:

- **Exact**: all identified inputs and environment dependencies are available and the provider declares the relevant execution reproducible under those conditions.
- **Equivalent**: the SUT, declared configuration, data dependencies, and materially relevant environment are available, but bit-for-bit replay is not guaranteed.
- **Best effort**: some non-critical or provider-controlled dependencies cannot be recreated and the gaps are recorded.
- **Unavailable**: required inputs or environment dependencies are missing, invalid, or inaccessible.

The level and its reasons are provenance metadata. The platform does not upgrade a provider's guarantee or equate external execution reproducibility with deterministic analysis reproducibility.

Exact analysis reproducibility requires the same dataset, analysis definition/version, parameters, and deterministic computation environment.

## Consequences

Positive:

- results can be explained across build, execution, data, and analysis boundaries;
- incomplete reproduction claims become explicit and testable;
- provider limitations remain visible rather than being hidden by abstractions.

Negative:

- more metadata and validation are required;
- exact external replay may remain unavailable even when platform provenance is complete.
