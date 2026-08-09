# ADR-0008 — Schema evolution, maturity, and backward compatibility

- Status: Accepted

## Context

Raw evidence is immutable, while platform contracts and analytical models will evolve across phases. Rewriting historical evidence would break auditability, but silently coercing old data would make interpretation non-reproducible.

Early schemas may exist before their contracts have been exercised by a real producer and consumer, including an external provider where the contract touches provider behavior. File existence, successful metaschema validation, or Phase 01 completion alone does not make such a contract stable.

## Decision

Every persisted or externally exchanged serialized contract carries a schema identity and exact semantic version.

Schema documents use repository-owned URN identifiers and are resolved through a closed local catalog. Runtime network resolution is prohibited.

### Maturity levels

Schemas have one of three maturity levels:

1. **Draft**
   - Design material that has not been released for persisted or external instances.
   - Drafts do not create backward-compatibility obligations.
   - Draft status must be explicit; a draft must not use a released contract identity.

2. **Pre-stable (`0.y.z`)**
   - A released, exact, machine-validatable contract whose semantics or boundary fit still require operational evidence.
   - Appropriate for contracts not yet exercised by their real producer and consumer or, when applicable, by a real external provider.
   - Every released pre-stable file is immutable and remains identifiable. Pre-stable does not mean mutable in place.
   - Breaking structural or semantic changes increment the minor version (`0.y.z` to `0.(y+1).0`). Backward-compatible corrections or additions increment the patch version.

3. **Stable (`1.0.0` and later)**
   - A contract promoted after representative producer/consumer exercise, fixture coverage, boundary review, and an explicit compatibility commitment.
   - Backward-compatible additions increment the minor version. Backward-compatible corrections increment the patch version. Breaking structural or semantic changes increment the major version.

Provider-independent schemas may become stable without a real execution provider only when their complete semantics are fixed by accepted ADRs and exercised by implementation and contract tests. Provider-facing or provider-shaped contracts must not become stable before representative provider evidence has tested the boundary.

### Immutability and compatibility

Any change to a released schema creates a new exact version and a new schema document. Released schema files are never edited in place, including `0.y.z` files.

Readers must either:

- support the object's declared historical schema version through an explicit reader or adapter; or
- fail visibly with an unsupported-version error.

Silent coercion is prohibited. Raw evidence is never rewritten in place to adopt a newer schema. Derived datasets and analytical results are regenerated under new transformation or analysis versions and coexist with prior versions.

Backward compatibility means that declared supported historical versions remain readable; it does not require every future implementation to support every version forever. Any retirement policy must be explicit and must preserve the ability to identify and export the original immutable evidence and its schema.

Promotion from pre-stable to stable creates a new stable schema version. It does not relabel, overwrite, or erase pre-stable contracts or instances.

### Validation conformance

Schema validation must enforce every declared format used as a contract constraint. Merely installing optional format-validation dependencies does not activate format checking and is not acceptance evidence.

Each validator implementation must explicitly enable its format-checking mechanism, fail if a required declared format has no active checker, and include negative fixtures proving that invalid formatted values are rejected.

## Consequences

Positive:

- phased evolution does not invalidate historical evidence;
- schema maturity reflects operational evidence rather than file existence;
- early provider assumptions can change without falsely promising stable compatibility;
- compatibility behavior is explicit and testable;
- declared formats are enforced rather than treated as unchecked annotations;
- derived interpretations remain versioned and reproducible.

Negative:

- readers and adapters may need to support multiple schema versions and maturity levels;
- promotion requires explicit evidence and review;
- breaking changes require deliberate version and support decisions even before `1.0.0`.
