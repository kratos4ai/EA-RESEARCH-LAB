# ADR-0009 — Entity identity and content identity

- Status: Accepted

## Context

Platform entities need stable, type-safe identifiers across domain objects, logs, provenance records, schemas, and future Platform API contracts. Entity identifiers must remain distinct from the cryptographic digests used to identify immutable content.

Identifier representation is a durable serialized contract. It must not expose provider, storage, strategy, or other mutable domain metadata.

## Decision

### Entity identity

Every platform entity identifier uses:

```text
<typed-prefix>_<canonical-lowercase-UUIDv7>
```

UUIDv7 is generated with Python 3.14 standard-library `uuid.uuid7()` and validated as an RFC 9562 UUID version 7 in canonical lowercase hyphenated form.

The initial typed prefixes are:

| Entity | Prefix |
|---|---|
| Build record | `build` |
| Artifact | `artifact` |
| Test definition | `testdef` |
| Test-definition revision | `testrev` |
| Environment/configuration | `envcfg` |
| Run | `run` |
| Raw evidence object | `rawobj` |
| Raw evidence manifest | `rawmanifest` |
| Transformation | `transformation` |
| Dataset | `dataset` |
| Analysis definition | `analysisdef` |
| Analysis result | `analysisresult` |
| Application request | `request` |

Rules:

- Entity IDs are opaque outside their owning type.
- Consumers must not extract or depend on the UUIDv7 timestamp, sort order, counter, or random fields as domain data.
- Authoritative timestamps are explicit domain values and provenance fields, never values inferred from an ID.
- IDs do not encode provider names, storage locations, strategy meaning, lifecycle state, mutable metadata, or content hashes.
- The typed prefix identifies the entity type only. It carries no instance-specific domain metadata.
- Parsing rejects an incorrect prefix, a non-version-7 UUID, a non-RFC variant, non-canonical case or hyphenation, whitespace, and empty values.
- UUIDv7 generation belongs at an application boundary or an explicitly injected ID-generation function. Domain entities accept validated typed IDs and do not depend on a clock service.

The time-ordered representation is an operational property, not a semantic ordering contract. Consumers must use explicit timestamps and sequence fields when order matters.

### Content identity

Immutable content identity uses a cryptographic digest:

```text
SHA-256 = 64 lowercase hexadecimal characters
```

The contract that computes a digest must define the exact bytes covered. A content digest is not an entity ID and receives no entity prefix.

Entity identity and content identity may appear together. For example, an Artifact has an `ArtifactId` and a binary SHA-256 digest; a sealed raw evidence manifest has a `RawEvidenceManifestId` and a SHA-256 digest of the serialized manifest bytes held by its reference.

### Schema identity

Schema identity is separate from both entity and content identity. It uses the repository-owned URN plus exact semantic schema version defined by ADR-0008.

## Consequences

Positive:

- typed IDs prevent accidental cross-entity substitution;
- Python 3.14 provides UUIDv7 without another dependency;
- entity identity remains independent from content, provider, storage, and strategy semantics;
- explicit timestamps remain the only authoritative temporal contract.

Negative:

- Python 3.14 becomes the minimum runtime for the standard-library generator;
- every serialized contract must validate its exact typed prefix and UUID version;
- consumers may be tempted to infer time or ordering from UUIDv7, so tests and documentation must prohibit that coupling.
