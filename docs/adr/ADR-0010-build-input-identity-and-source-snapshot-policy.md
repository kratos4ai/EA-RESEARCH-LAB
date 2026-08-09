# ADR-0010 — Build input identity and source snapshot policy

- Status: Proposed

## Context

The platform must explain which source bytes produced an accepted Artifact. `SourceRevision` provides source-history context, including repository, revision, version-control system, and dirty-state declaration, but it does not prove which bytes a compiler consumed.

A clean Git working tree does not by itself prove the complete build input. Build inputs may include generated files, untracked files, local includes, transitive includes, provider-supplied includes, or other external dependencies. A dirty working tree can still be a legitimate research input when the exact claimed bytes can be materialized and identified.

Conflating source-history identity with byte identity would weaken the canonical provenance chain established by ADR-0007. Encoding content identity inside an entity identifier would violate ADR-0009.

## Decision

### Source-history context

`SourceRevision` remains the source-history reference. It records where the source came from and whether the referenced working state was dirty. It is not authoritative evidence of the bytes compiled.

Git cleanliness must never be used as proof of exact build-input bytes.

### Build input identity

Every accepted build must reference a content-addressed identity for the actual build input claimed by the platform.

The architecture will support a deterministic Build Input Manifest. The manifest describes the claimed input set and contains, at minimum, an exact-byte SHA-256 content identity for every included input. Its own content identity is the SHA-256 digest of a canonical serialized representation defined by its eventual versioned contract.

The manifest must distinguish logical input identity from machine-specific storage location. Absolute local paths, provider installation paths, and storage keys do not become core source identity.

Entity identity and content identity remain separate. The Build Input Manifest digest is content identity, not an entity identifier, and receives no typed UUIDv7 prefix.

### Dirty source and materialization

A dirty working tree is not rejected merely because it is dirty. It may be built when the exact claimed input can be materialized and content-identified before provider execution.

If the platform cannot materialize and content-identify the claimed input set, it must not accept the build as `succeeded`. Provider-controlled dependencies that cannot be identified must remain explicit limitations rather than being silently omitted; the probes must establish whether such limitations require revising the claimed input boundary before this ADR can be accepted.

Build execution should consume the materialized input represented by the manifest rather than relying on a mutable development working tree whenever the provider can support that workflow.

### External inputs and includes

External inputs that participate in the claimed build input must be represented explicitly. They may be identified as source-owned inputs or as provider/environment inputs, but they must not disappear behind `SourceRevision`.

The mechanism that discovers dependencies, resolves includes, and materializes the provider workspace is provider-specific. Completeness claims must reflect the provider evidence actually available. The core does not parse MQL source or infer dependency semantics.

### Identity versus retention

Digest identity and durable byte retention are separate responsibilities.

A manifest digest remains valid historical content identity even when the referenced bytes are no longer retained. Missing retained bytes reduce the achievable reproducibility level and must be recorded as a limitation; they do not retroactively invalidate the historical digest.

This decision does not introduce snapshot persistence, a source archive, a registry, or Data Plane infrastructure. Retention policy and storage implementation remain separate later decisions.

### Provider evidence

The exact dependency-discovery and snapshot-materialization mechanism remains subject to controlled MetaEditor probes. Provider-specific paths, observations, and limitations stay inside the MetaEditor adapter or namespaced provider evidence.

No source dependency parser is introduced by this decision.

## Consequences

Positive:

- accepted Artifacts can be linked to byte-level build-input identity rather than Git state alone;
- dirty-source research remains possible when exact inputs can be materialized;
- source history, entity identity, and content identity remain distinct;
- external inputs and provider limitations become visible in provenance;
- reproducibility assessments can distinguish known identity from retained availability.

Negative:

- Phase 02 must define a versioned Build Input Manifest contract before accepted builds use it;
- materialization and dependency completeness require provider evidence;
- external include behavior may prevent a complete input claim until additional environment facts are captured;
- retaining enough bytes for future reconstruction remains an unsolved responsibility;
- existing pre-stable Build Record and Artifact Manifest contracts may require new exact versions.

## Alternatives considered

### Treat a clean Git revision as exact input identity

Rejected. Cleanliness does not prove the complete compiler input and does not cover external or provider-supplied dependencies.

### Reject every dirty-source build

Rejected as an architectural rule. It unnecessarily excludes valid research inputs that can be materialized and content-identified. A strict operational mode may still reject inputs it cannot identify.

### Hash only the primary source file

Rejected. The primary file does not represent local, nested, generated, or external includes.

### Implement an MQL dependency parser in the platform core

Rejected. Dependency semantics are provider-specific, operationally unverified, and outside the strategy-agnostic core.

## Acceptance conditions

This ADR remains Proposed until controlled MetaEditor probes establish whether:

- compilation can operate on a materialized disposable snapshot;
- local, nested, and standard-location include behavior can be observed sufficiently to state a claimed input set;
- provider-controlled output or include resolution introduces material assumptions that would change this decision;
- the manifest can remain provider-neutral while provider-specific evidence stays namespaced.

Acceptance does not require implementing persistence or retaining source snapshots. It requires confidence that the identity contract accurately states what the platform can and cannot claim.
