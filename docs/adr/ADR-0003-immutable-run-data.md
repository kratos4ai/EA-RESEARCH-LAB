# ADR-0003 — Immutable raw run data

- Status: Accepted

## Context

Research results must remain reproducible and auditable.

## Decision

Raw evidence collection and sealed evidence are distinct states.

During active collection, new raw objects or chunks may be appended. Each object is immutable once persisted. A sealed, content-identified raw evidence manifest defines the evidence set for a collection outcome.

Completed, failed, cancelled, and collection-failed runs may each produce a sealed manifest. Late evidence creates a new manifest revision linked to the previous revision; it does not modify a sealed manifest or existing raw objects.

Corrections, enrichment, normalization, and alternative calculations create new Derived Data or new Analysis versions.

## Consequences

- historical evidence is preserved;
- analysis can be recomputed;
- storage usage may increase;
- versioning and manifest-sealing discipline are required;
- an actively collecting run does not yet have a final reproducible evidence boundary.
