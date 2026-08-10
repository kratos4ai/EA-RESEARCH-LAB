# Schemas

This directory contains the exact, machine-readable boundary contracts. All schemas use JSON Schema Draft 2020-12 and repository-owned URN identities.

## Contract catalog

| Contract | Version | Maturity | Schema identity |
|---|---:|---|---|
| Common values | `1.0.0` | Stable | `urn:ea-research-lab:schema:common:1.0.0` |
| Build input manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:build-input-manifest:0.1.0` |
| Build record | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:build-record:0.1.0` |
| Build record | `0.2.0` | Pre-stable | `urn:ea-research-lab:schema:build-record:0.2.0` |
| Artifact manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:artifact-manifest:0.1.0` |
| Test definition | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:test-definition:0.1.0` |
| Run manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:run-manifest:0.1.0` |
| Raw evidence manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:raw-evidence-manifest:0.1.0` |
| Dataset manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:dataset-manifest:0.1.0` |
| Telemetry envelope | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:telemetry-envelope:0.1.0` |
| Analysis result | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:analysis-result:0.1.0` |
| MetaEditor build configuration | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:metaeditor-build-configuration:0.1.0` |
| MetaEditor build configuration | `0.2.0` | Pre-stable | `urn:ea-research-lab:schema:metaeditor-build-configuration:0.2.0` |
| MetaEditor build evidence | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:metaeditor-build-evidence:0.1.0` |

`common/1.0.0` contains reusable provider-independent value definitions and is not an instance contract. Boundary contracts remain pre-stable until representative producers and consumers exercise them. Passing validation does not promote a contract to stable.

Reproducibility enum members serialize using the domain values `exact`, `equivalent`, `best_effort`, and `unavailable`; the uppercase Python enum member names are not wire values.

## Identity and local resolution

Schema files use `schemas/<schema-name>/v<major>.<minor>.<patch>.schema.json`. Every boundary instance declares the exact `schema_name` and `schema_version` used to select its schema.

`ea_research_lab.contracts.catalog` is the closed support declaration. It loads only the fourteen exact paths listed above and builds a local reference registry without a retrieval callback. Runtime network resolution is forbidden.

Schema references carried inside opaque extension envelopes identify the extension contract. They do not cause network retrieval or imply that the Phase 01 catalog supports that extension schema. A consumer validates such payload content only when it separately supports the referenced extension contract.

## Validation

`ea_research_lab.contracts.validation` selects an exact local boundary schema and uses `Draft202012Validator` with an explicit `FormatChecker`. Validation performs no default insertion, type coercion, migration, or domain interpretation.

Contract tests cover:

- Draft 2020-12 schema self-validation;
- local `$ref` resolution and closed-catalog behavior;
- explicit date-time and URI format checking;
- representative linked provenance fixtures;
- invalid identifiers, digests, formats, references, provenance shapes, and exact versions;
- missing and unexpected properties;
- opaque provider and SUT payloads confined to schema-referenced envelopes.

JSON Schema enforces serialized structure. The contracts validator additionally enforces the small Build Input Manifest invariants that JSON Schema cannot safely express: normalized logical locations, unique logical keys, and aggregate identity verification. Other deeper semantic invariants, such as cross-record equality and raw-evidence revision rules, remain in the domain model or application workflow.

## Build Input Identity v1

`build-input-manifest/0.1.0` identifies the exact declared source input set. The primary source is a workspace member. Dependencies are workspace or external members and form a semantic set; their serialized input order is not identity.

Logical paths are Unicode NFC relative identifiers using `/`. They reject leading or trailing `/`, empty segments, `.` and `..`, backslashes, control characters, Windows drive paths, UNC paths, and file URIs. Workspace locations have no root. External locations require a lowercase kebab-case logical root alias supplied by effective build configuration or orchestration. A provider may map that alias to a physical root, but the physical path does not enter Build Input Identity.

Each `content_digest` is SHA-256 over the member's exact file bytes. Source encoding, BOM, newlines, whitespace, and every other byte remain significant.

Build Input Identity v1 is calculated from this semantic projection only:

```json
{
  "primary": {
    "scope": "workspace",
    "root": null,
    "path": "Experts/Main.mq5",
    "content_digest": "<sha256>"
  },
  "dependencies": []
}
```

Before serialization, dependency members are sorted by the tuple of UTF-8 bytes for `scope`, `root` or the empty string, and normalized `path`. Duplicate normalized logical locations are rejected. The projection is serialized exactly as:

```python
json.dumps(
    projection,
    ensure_ascii=False,
    sort_keys=True,
    separators=(",", ":"),
    allow_nan=False,
).encode("utf-8")
```

The lowercase textual SHA-256 of those bytes is `build_input_identity`. Schema discriminators, the resulting identity, `SourceRevision`, physical paths, Build Environment, provider evidence, storage, retention, and arbitrary metadata are excluded. A future incompatible identity calculation requires a new exact Build Input Manifest schema version; historical identities are never silently recomputed.

`build-record/0.2.0` references the exact manifest schema and Build Input Identity. A succeeded record requires both that reference and an accepted `artifact_id`; a failed record rejects `artifact_id` and may retain Build Input Identity when it was established before failure. Optional provider evidence remains opaque and schema-referenced. Reproducibility assessment remains separate from immutable Build Record facts.

## Evolution rules

- Never edit an accepted schema version in place.
- Pre-stable breaking changes create a new minor version; compatible corrections or additions create a new patch version.
- Stable breaking changes create a new major version; compatible additions create a new minor version; compatible corrections create a new patch version.
- Readers support explicitly declared exact identities and reject unsupported versions.
- Historical raw evidence is never rewritten or silently migrated to a newer schema.
- Provider- or SUT-specific data remains opaque and schema-referenced; it does not become core vocabulary.

These rules implement ADR-0008. Maturity is a compatibility commitment, not a consequence of file existence or test success.
