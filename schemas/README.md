# Schemas

This directory contains the exact, machine-readable Phase 01 boundary contracts. All schemas use JSON Schema Draft 2020-12 and repository-owned URN identities.

## Contract catalog

| Contract | Version | Maturity | Schema identity |
|---|---:|---|---|
| Common values | `1.0.0` | Stable | `urn:ea-research-lab:schema:common:1.0.0` |
| Build record | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:build-record:0.1.0` |
| Artifact manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:artifact-manifest:0.1.0` |
| Test definition | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:test-definition:0.1.0` |
| Run manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:run-manifest:0.1.0` |
| Raw evidence manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:raw-evidence-manifest:0.1.0` |
| Dataset manifest | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:dataset-manifest:0.1.0` |
| Telemetry envelope | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:telemetry-envelope:0.1.0` |
| Analysis result | `0.1.0` | Pre-stable | `urn:ea-research-lab:schema:analysis-result:0.1.0` |

`common/1.0.0` contains reusable provider-independent value definitions and is not an instance contract. The eight boundary contracts remain pre-stable until representative producers and consumers exercise them. Passing validation does not promote a contract to stable.

Reproducibility enum members serialize using the domain values `exact`, `equivalent`, `best_effort`, and `unavailable`; the uppercase Python enum member names are not wire values.

## Identity and local resolution

Schema files use `schemas/<schema-name>/v<major>.<minor>.<patch>.schema.json`. Every boundary instance declares the exact `schema_name` and `schema_version` used to select its schema.

`ea_research_lab.contracts.catalog` is the closed Phase 01 support declaration. It loads only the nine paths listed above and builds a local reference registry without a retrieval callback. Runtime network resolution is forbidden.

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

JSON Schema enforces serialized structure. Deeper semantic invariants, such as cross-record equality and raw-evidence revision rules, remain in the domain model or application workflow.

## Evolution rules

- Never edit an accepted schema version in place.
- Pre-stable breaking changes create a new minor version; compatible corrections or additions create a new patch version.
- Stable breaking changes create a new major version; compatible additions create a new minor version; compatible corrections create a new patch version.
- Readers support explicitly declared exact identities and reject unsupported versions.
- Historical raw evidence is never rewritten or silently migrated to a newer schema.
- Provider- or SUT-specific data remains opaque and schema-referenced; it does not become core vocabulary.

These rules implement ADR-0008. Maturity is a compatibility commitment, not a consequence of file existence or test success.
