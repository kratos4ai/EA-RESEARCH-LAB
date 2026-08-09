# ADR-0010 — Build input identity and source snapshot policy

- Status: Accepted

## Context

The platform must explain which source bytes produced an accepted Artifact. `SourceRevision` provides source-history context, including repository, revision, version-control system, and dirty-state declaration, but it does not prove which bytes a compiler consumed.

A clean Git working tree does not by itself prove the complete build input. Build inputs may include generated files, untracked files, local includes, transitive includes, provider-supplied includes, or other external dependencies. A dirty working tree can still be a legitimate research input when the exact claimed bytes can be materialized and identified.

Conflating source-history identity with byte identity would weaken the canonical provenance chain established by ADR-0007. Encoding content identity inside an entity identifier would violate ADR-0009.

Controlled probes P01–P16, recorded in `plans/active/phase-02-metaeditor-probe-results.md`, established that the observed MetaEditor version can compile a materialized primary/local/transitive source snapshot, writes its candidate EX5 beside the primary source, and exposes paths for the tested include categories in its provider log. The same probes also established important limits: no output-redirection mechanism was verified, and log-based dependency discovery was not proven complete for every possible compilation input.

## Decision

### Source-history context

`SourceRevision` remains the historical source-control reference. It records where source came from and whether the referenced working state was dirty. It is not authoritative evidence of the exact bytes compiled.

Git cleanliness must never be used as proof of exact build-input identity.

### Build Input and Build Environment

Build Input and Build Environment are separate provenance concepts.

Build Input identifies source material whose bytes the platform declares as participating in compilation. Where established for a build, this includes:

- the primary source;
- local includes;
- transitive includes;
- standard or external includes that participate in the declared input set.

Build Environment records facts that can affect compilation without becoming source members, including:

- provider and compiler identity;
- compiler version and executable SHA-256;
- materially relevant operating-system and environment facts;
- locale or code page when material;
- effective provider configuration.

Provider, compiler, host, and configuration identities do not belong inside the Build Input Manifest. They remain separately identified environment/configuration provenance associated with the Build Record.

### Build input identity

Every accepted build must identify the exact bytes of every source input that the platform declares as participating in that build.

The architecture will support a deterministic Build Input Manifest containing an exact-byte SHA-256 content identity for each declared input. Logical input identity must remain separate from machine-specific storage location. Absolute local paths, provider installation paths, and storage keys do not become core source identity.

Entity Identity and Content Identity remain distinct. A Build Input Manifest is content-addressed rather than identified by a typed UUIDv7 entity identifier.

The aggregate identity of the represented build-input set is also distinct from a digest of arbitrary serialized manifest bytes. Before publishing the Build Input Manifest contract, the platform must select and specify a deterministic canonical representation and the exact bytes covered by its aggregate SHA-256 identity. This ADR does not select or define the canonicalization algorithm.

### Dirty source and exclusive build workspace

A dirty working tree is not rejected merely because it is dirty. It may be built when the platform can materialize and content-identify the exact source input set it declares for the build independently from Git history.

The preferred isolation flow is:

```text
mutable development workspace
-> materialized exclusive build workspace
-> provider compilation
-> candidate output
```

Build execution should consume the materialized input represented by the manifest rather than the mutable development workspace whenever the provider supports that workflow.

For the observed MetaEditor version, the exclusive build workspace is the supported isolation boundary because P16 compiled the materialized snapshot and P06 observed the EX5 beside the primary source. No output-redirection mechanism was verified by P07. Output redirection is therefore not a platform requirement.

The exact workspace creation, path layout, lifecycle, and cleanup mechanism are infrastructure-specific and are not defined by this ADR.

### Candidate freshness and acceptance

An existing candidate EX5 is never sufficient evidence of current-build success.

The architecture prefers a newly materialized exclusive build workspace where the expected candidate does not exist before provider invocation. A candidate may be accepted only when it can be attributed to the current invocation and its content identity has been established.

The observed MetaEditor version replaced an existing candidate on a successful tested compile and removed an existing candidate on a failed tested compile. These are provider observations, not platform invariants. Candidate acceptance must not rely on either behavior.

A Build becomes `succeeded` only after candidate acceptance. The provider-neutral public Build outcome remains:

- `succeeded`;
- `failed`.

Timeout, cancellation, process outcome, and provider diagnostics are evidence used to determine that outcome; they do not add provider-specific public Build outcomes through this ADR.

### Dependency completeness and reproducibility

The tested MetaEditor logs exposed full paths for local, transitive, standard, and missing includes. This evidence can support a provider-specific discovery mechanism, but it does not prove that logs enumerate every possible compilation dependency.

The platform must not claim dependency completeness beyond what the provider-specific mechanism can establish. The claimed Build Input set, the discovery method and scope, and known completeness limitations must remain explicit.

A provider may successfully compile while the platform still has a reproducibility limitation. Successful build outcome and complete reproducibility are separate conclusions. Unknown or unavailable dependencies reduce the reproducibility level according to ADR-0007 and must not be silently omitted or upgraded into an exact reproduction claim.

The core does not parse MQL source or infer provider dependency semantics.

### Content identity and byte retention

Digest identity and durable byte retention are separate responsibilities.

A known SHA-256 identity remains valid historical content identity even when the referenced bytes are no longer retained. Missing retained bytes reduce the achievable reproducibility level and must be recorded as a limitation; they do not retroactively invalidate historical provenance.

This decision does not introduce snapshot persistence, source archives, registries, repositories, or Data Plane storage infrastructure. Retention policy and storage implementation remain separate later decisions.

### Provider observations and adapter boundary

For the tested MetaEditor `5.0.0.6104` installation, the probes observed:

- successful tested compilation exited with code `1`;
- tested compiler failure exited with code `0`;
- the terminated timeout probe exited with code `-1`;
- diagnostics were written to adjacent UTF-16LE provider logs rather than stdout or stderr;
- the tested direct process completed without an observed child, detach, or reuse;
- native Windows command-line quoting was material for paths containing spaces.

These facts are MetaEditor-adapter evidence. They must never become generic platform exit-code, process, path, encoding, or diagnostic semantics. Adapters translate provider observations into provider-neutral contracts only when meaning is preserved; otherwise evidence remains provider-namespaced, consistent with ADR-0006.

The provider-neutral Build outcome can become `succeeded` only after the adapter and application boundary establish acceptable provider evidence and accept the current invocation's candidate.

## Remaining provider uncertainties

The following are non-blocking adapter concerns and do not weaken the provider-neutral decision:

- output redirection remains unverified;
- interactive or reused MetaEditor behavior remains untested;
- dependency-log completeness remains unproven;
- byte-for-byte EX5 determinism remains untested;
- only MetaEditor `5.0.0.6104` in the observed installation was tested;
- process-tree behavior for larger or project-mode builds remains unverified.

Provider implementation and tests must preserve these limits until further evidence resolves them.

## Consequences

Positive:

- accepted Artifacts can be linked to byte-level build-input identity rather than Git state alone;
- dirty-source research remains possible when exact declared inputs can be materialized;
- source history, entity identity, content identity, and environment identity remain distinct;
- exclusive workspaces provide a supported freshness and isolation boundary without requiring output redirection;
- external inputs and provider limitations remain visible in provenance;
- reproducibility assessments distinguish successful compilation, known content identity, dependency completeness, and retained availability.

Negative:

- Phase 02 must define a versioned Build Input Manifest contract and its canonical aggregate identity before accepted builds use it;
- the released pre-stable Build Record contract requires a new exact version to reference Build Input Identity and the separated Build Environment evidence; ADR-0008 prohibits editing `0.1.0` in place;
- provider-specific discovery cannot promise completeness beyond its evidence;
- build workspace isolation and candidate attribution add adapter responsibilities;
- retaining enough bytes for future reconstruction remains unresolved.

## Alternatives considered

### Treat a clean Git revision as exact input identity

Rejected. Cleanliness does not prove the complete compiler input and does not cover external or provider-supplied dependencies.

### Reject every dirty-source build

Rejected as an architectural rule. It unnecessarily excludes valid research inputs that can be materialized and content-identified. A provider operation may still fail when it cannot establish the exact declared input set or an acceptable candidate.

### Hash only the primary source file

Rejected. The primary file does not represent local, nested, generated, or external includes.

### Require provider output redirection

Rejected. No output-redirection mechanism was verified, while compilation from an exclusive materialized workspace was empirically supported.

### Implement an MQL dependency parser in the platform core

Rejected. Dependency semantics are provider-specific and outside the strategy-agnostic core.

### Treat successful compilation as complete reproducibility

Rejected. A provider can produce a candidate even when dependency completeness, retained inputs, environment reconstruction, or deterministic output cannot be guaranteed.

## Evidence basis

The controlled probes satisfied this decision's acceptance conditions for the observed provider boundary:

- P16 demonstrated compilation from an isolated materialized snapshot;
- P09–P12 exposed the tested local, nested, standard, and missing include behavior while preserving completeness uncertainty;
- P03, P06, and P08 established the need for exclusive-workspace candidate attribution rather than stale-output assumptions;
- P01, P02, and P14 demonstrated that provider exit codes cannot define the platform Build outcome;
- P04, P05, P13, and P15 located Windows path, encoding, and process behavior behind the adapter boundary.

Acceptance does not claim universal MetaEditor behavior, dependency completeness, deterministic EX5 generation, or durable snapshot retention. It accepts the provider-neutral identity and isolation policy while preserving those limitations explicitly.
