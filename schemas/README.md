# Schemas

This directory contains versioned machine-readable contracts.

Initial contracts are intentionally minimal and are expected to evolve through explicit versioning.

## Current status

The existing `v1.schema.json` files are unreleased design drafts. Their filenames do not grant stable `1.0.0` status and do not create backward-compatibility obligations.

Phase 01 M4 will consolidate them under the maturity and exact semantic-version rules defined by ADR-0008. Until then, they must not be treated as released contracts for persisted or external instances.

Rules:

- never silently change the meaning of an existing schema version;
- additive changes must still be evaluated for compatibility;
- breaking changes create a new version;
- schema validation belongs in automated tests;
- schemas describe transport/persistence contracts, not strategy semantics.
