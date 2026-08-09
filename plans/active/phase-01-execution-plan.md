# Phase 01 — Foundation Execution Plan

- Status: In progress — M0 through M4 closed; M5 not started
- Scope: Phase 01 only
- Implementation authorization: Not granted by this document

## 1. Objective

Establish the smallest implementation foundation that makes the accepted architectural boundaries executable and testable without implementing build automation, external execution, persistence, analytics, an API runtime, visual analytics, or MCP.

Phase 01 produces domain primitives, stable identifier and value conventions, canonical provenance contracts, versioned schemas, local schema validation, configuration and logging conventions, a minimal Python package structure, and automated quality gates.

## 2. Non-negotiable constraints

- The core remains strategy-agnostic. SUT inputs and telemetry payloads are opaque to the core.
- No MetaTrader-, MetaEditor-, provider-, storage-, database-, filesystem-layout-, MCP-, UI-, or transport-specific types enter domain or semantic contracts.
- Raw evidence collection and sealed immutable evidence remain distinct concepts.
- Storage/data integrity contracts belong to the Data Plane boundary; analytical/run integrity belongs to the future Analysis Plane. Phase 01 may validate serialized structure and provenance invariants but must not implement analytical/run integrity logic.
- The complete canonical provenance chain remains representable.
- Schema identity, versioning, compatibility, and explicit unsupported-version failure follow ADR-0008.
- Reproducibility is assessed as Exact, Equivalent, Best effort, or Unavailable; no external provider guarantee is upgraded.
- External technologies remain behind future adapters.
- Analytical computation remains outside presentation and is not implemented in this phase.
- Platform API remains the future application boundary; no API server or transport is created.
- MCP remains a future adapter over Platform API and is not scaffolded in this phase.
- No empty packages, interfaces, factories, repositories, services, or adapters are created solely for later phases.
- Repository artifacts, identifiers, errors, schemas, tests, and documentation remain in English.

## 3. Observed repository state

The workspace contains Git metadata, but the repository has no commits. The current branch is `master`, and all current files are untracked.

Therefore:

- `git init` is already satisfied in this workspace and must not be repeated;
- the initial baseline commit is still required before Phase 01 implementation;
- a portable implementation checklist may retain `git init -b main` as a conditional step for a fresh checkout with no `.git` directory;
- no Git initialization, branch rename, staging, or commit is performed while this plan is being prepared.

## 4. Minimal technical baseline

### 4.1 Language

Use Python 3.14. Python 3.14 provides the required standard-library facilities: frozen dataclasses, enums, `uuid.uuid7()` generation, UTC-aware datetimes, JSON parsing, logging, environment access, `unittest`, `ast`, `compileall`, `venv`, and hashing.

Python 3.14 is not currently installed in the observed workspace, which exposes Python 3.12.10. Installing and verifying Python 3.14 is an M1 toolchain prerequisite and must not occur before M0 authorization and completion.

Do not introduce an asynchronous runtime, web framework, ORM, dataframe library, dependency-injection framework, or plugin framework in Phase 01.

### 4.2 Proposed third-party dependencies

Direct dependencies are limited to:

1. `jsonschema[format]`
   - Purpose: validate JSON Schema Draft 2020-12 contracts, local references, and declared date/date-time formats.
   - Why the standard library is insufficient: `json` parses JSON but does not validate JSON Schema, `$ref`, required fields, compatibility constraints, or formats.
   - Scope: contract-validation boundary only; it must not be imported by the domain package.
   - Installing the `format` extra only provides format-checker dependencies. It does not activate format validation. The validator must receive an explicit `FormatChecker` instance, and negative format fixtures must prove that checking is active.

Build-only dependency:

2. `setuptools`
   - Purpose: provide the standard Python packaging build backend for an installable `src` layout and editable development installation.
   - Why the standard library is insufficient: Python defines packaging standards but does not include a build backend capable of installing the project package.

Do not add `pytest`, a DI container, Pydantic, a logging framework, a configuration framework, a SemVer package, a UUID/ULID package, a schema-code-generation tool, or a task runner. `unittest` and small standard-library checks are sufficient for the Phase 01 code volume.

Use a clean `.venv`, record direct requirements separately from an exact resolved lock file, and approve resolved versions during implementation. Do not claim a reproducible toolchain from unpinned transitive dependencies.

## 5. Minimal repository structure

Only directories with Phase 01 behavior or tests are created:

```text
.
├── pyproject.toml
├── requirements.in
├── requirements.lock
├── src/
│   └── ea_research_lab/
│       ├── __init__.py
│       ├── domain/
│       │   ├── __init__.py
│       │   ├── identifiers.py
│       │   ├── values.py
│       │   ├── errors.py
│       │   ├── evidence.py
│       │   └── provenance.py
│       ├── application/
│       │   ├── __init__.py
│       │   ├── context.py
│       │   ├── identity.py
│       │   └── errors.py
│       ├── contracts/
│       │   ├── __init__.py
│       │   ├── catalog.py
│       │   └── validation.py
│       └── infrastructure/
│           ├── __init__.py
│           ├── config.py
│           └── logging.py
├── schemas/
│   ├── README.md
│   ├── common/
│   ├── build-record/
│   ├── artifact-manifest/
│   ├── test-definition/
│   ├── run-manifest/
│   ├── raw-evidence-manifest/
│   ├── dataset-manifest/
│   ├── telemetry-envelope/
│   └── analysis-result/
├── tests/
│   ├── unit/
│   ├── contracts/
│   ├── architecture/
│   └── fixtures/
│       └── schemas/
├── tools/
│   └── check.py
└── docs/
    └── development.md
```

Do not create `adapters`, `api`, `analysis`, `data`, `semantic`, `mcp`, `ui`, `metatrader`, or persistence implementation packages in Phase 01. Their architectural boundaries are documented, but they do not yet contain Phase 01 behavior.

## 6. Module responsibilities and dependency direction

### `ea_research_lab.domain`

Owns immutable identifiers, value objects, domain validation errors, raw-evidence sealing concepts, provenance relationships, and reproducibility assessment.

- Depends only on the Python standard library and other domain modules.
- Does not parse environment variables, configure logging, validate JSON Schema, access Git, open files, invoke providers, or know transport/storage types.

### `ea_research_lab.application`

Owns transport-neutral request context and application error envelopes needed by future Platform API capabilities.

It also owns the small standard-library UUIDv7 generation function used to create typed IDs without making domain entities depend on a clock or generator service.

- May depend on `domain`.
- Does not expose HTTP, CLI, MCP, database, or provider types.
- Does not contain command/query services in Phase 01 because no application use case is implemented yet.

### `ea_research_lab.contracts`

Owns the local schema catalog and validation of serialized documents at trust boundaries.

- May depend on `domain` error/value types and `jsonschema`.
- Resolves only repository-controlled schema identifiers; network schema resolution is forbidden.
- Does not contain persistence or domain business logic.

### `ea_research_lab.infrastructure`

Owns standard-library configuration loading and logging setup.

- May depend on `application` and `domain` identifiers for structured context.
- Does not define domain concepts or hide future external providers behind premature abstractions.

### `schemas`

Contains language-neutral serialized contracts. Schema property names must remain provider-neutral and strategy-agnostic. Provider or SUT extensions are admitted only through explicit schema-referenced opaque values/payload extension points.

### Allowed dependency direction

```text
infrastructure ---> application ---> domain
       |                                ^
       +----------> contracts ----------+

domain -X-> application / contracts / infrastructure
```

No package in Phase 01 depends on future adapters, API transports, storage engines, analysis engines, UI, or MCP.

## 7. Domain primitives

### 7.1 Opaque identifiers

Create distinct immutable types for:

- `BuildRecordId`
- `ArtifactId`
- `TestDefinitionId`
- `TestDefinitionRevisionId`
- `EnvironmentConfigurationId`
- `RunId`
- `RawEvidenceObjectId`
- `RawEvidenceManifestId`
- `TransformationId`
- `DatasetId`
- `AnalysisDefinitionId`
- `AnalysisResultId`
- `RequestId`

Do not add identifiers for future-only concepts such as MCP tools, visualizations, simulations, optimizers, schedules, databases, or provider jobs.

### 7.2 Identifier convention

Accepted convention from ADR-0009:

```text
<type-prefix>_<lowercase canonical UUIDv7>
```

Examples:

```text
run_0195395c-7c9e-7a91-8c2b-6d4f8e1a2b3c
artifact_0195395c-7c9e-7b12-9d3c-7e5f9a2b3c4d
dataset_0195395c-7c9e-7c23-ae4d-8f6a0b3c4d5e
```

Rules:

- IDs are opaque outside their owning type.
- IDs do not encode timestamps, storage locations, provider names, strategy meaning, or mutable metadata.
- UUIDv7 is generated with Python 3.14 standard-library `uuid.uuid7()`; no UUID/ULID dependency is justified.
- Prefixes make logs and serialized-contract errors diagnosable but are validated and never used as a substitute for the typed identifier.
- Parsing rejects wrong prefixes, non-version-7 UUIDs, non-RFC variants, non-canonical UUID text, whitespace, and empty values.
- Consumers must not extract the UUIDv7 timestamp or rely on UUID ordering as domain meaning. Authoritative time and order come only from explicit timestamp and sequence fields.
- Content identity is represented separately by a digest, never by an entity ID.

### 7.3 Value objects

Create frozen, validated values for:

- `Sha256Digest`: lowercase 64-character hexadecimal digest.
- `UtcTimestamp`: timezone-aware UTC datetime; serialized as RFC 3339 with `Z`.
- `SchemaName`: lowercase kebab-case contract name.
- `SchemaVersion`: exact `MAJOR.MINOR.PATCH` numeric version.
- `SchemaRef`: schema name plus exact schema version.
- `DefinitionVersion`: opaque non-empty version for transformations and analyses; it must not be conflated with schema version.
- `SourceRevision`: VCS kind, repository identity, immutable revision, and dirty-state declaration.
- `ReproducibilityLevel`: `EXACT`, `EQUIVALENT`, `BEST_EFFORT`, or `UNAVAILABLE`.
- `ReproducibilityAssessment`: level plus ordered, non-empty reason codes/details where limitations exist.

Use small explicit validation functions. Do not introduce a general validation framework or generic entity base class.

## 8. Provenance model

Represent provenance as immutable references owned by the record produced at each stage, not as one mutable graph service.

### 8.1 Required links

1. `BuildProvenance`
   - `source_revision`
   - `build_record_id`
   - build configuration reference/snapshot identity
   - produced `artifact_id` when successful

2. `RunProvenance`
   - `artifact_id`
   - `test_definition_revision_id`
   - `environment_configuration_id` and its immutable schema-referenced snapshot
   - `run_id`
   - execution reproducibility assessment

3. `EvidenceProvenance`
   - `run_id`
   - `raw_evidence_manifest_id`
   - immutable raw object descriptors
   - optional prior manifest revision

4. `DatasetProvenance`
   - input sealed manifest IDs and/or prior dataset IDs
   - transformation ID and version
   - transformation parameters or their immutable reference
   - produced `dataset_id`

5. `AnalysisProvenance`
   - input dataset IDs
   - analysis definition ID and version
   - analysis parameters
   - computation environment identity
   - produced `analysis_result_id`

Together these records must traverse:

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

### 8.2 Raw evidence model

- `RawEvidenceObject` contains an object ID, logical media type, byte length, SHA-256 digest, optional payload schema reference, and provider namespace when the bytes remain provider-specific.
- It contains no filesystem path, object-store key, database identifier, or storage vendor type.
- `RawEvidenceManifest` is immutable, identifies one run and one collection outcome, and contains an ordered immutable tuple of raw object descriptors.
- `RawEvidenceManifestRef` carries the manifest ID and SHA-256 digest of the serialized manifest bytes. The digest is external to the bytes it identifies, avoiding a self-referential hash field. Phase 01 models this reference but does not serialize or hash persisted manifests.
- A late-evidence manifest references the preceding manifest ID. It never replaces or mutates the preceding manifest.
- Completed, failed, cancelled, and collection-failed outcomes may be sealed.
- Phase 01 models and tests these invariants but does not collect bytes, hash files, persist manifests, or implement a storage adapter.

### 8.3 Reproducibility

- Execution reproducibility and analysis reproducibility remain distinct.
- A level without its supporting reasons and captured references is invalid when the level is `BEST_EFFORT` or `UNAVAILABLE`.
- `EXACT` is representable but cannot be assigned merely because all platform fields are populated; a future provider must explicitly support that claim.
- Phase 01 does not probe an execution provider or implement replay.

## 9. Schema consolidation

The existing five `v1.schema.json` files are design drafts, not released `1.0.0` contracts. Phase 01 consolidates them without inheriting false compatibility obligations from their filenames. Contract maturity follows ADR-0008 and is never inferred from file existence, metaschema validity, or Phase 01 completion alone.

### 9.1 Naming and identity

- File path: `schemas/<schema-name>/v<major>.<minor>.<patch>.schema.json`.
- Schema document `$id`: stable repository-owned URN, for example `urn:ea-research-lab:schema:artifact-manifest:0.1.0`.
- Every serialized instance requires `schema_name` and `schema_version`.
- The validator selects an exact local schema by those two fields.
- Released schema files are never edited in place, including pre-stable `0.y.z` contracts.
- For pre-stable contracts, breaking changes increment the minor version and backward-compatible corrections/additions increment the patch version.
- For stable contracts, breaking changes increment the major version, backward-compatible additions increment the minor version, and backward-compatible corrections increment the patch version.
- No schema is resolved over the network.

### 9.2 Initial maturity review

Phase 01 assigns maturity contract by contract:

| Schema | Initial version | Maturity rationale |
|---|---:|---|
| `common` | `1.0.0` | Stable provider-independent primitives fixed by ADR-0007, ADR-0008, and ADR-0009 and directly exercised by domain and contract tests |
| `build-record` | `0.1.0` | Pre-stable until exercised by a real BuildProvider workflow |
| `artifact-manifest` | `0.1.0` | Pre-stable until real build artifacts and provider metadata exercise the envelope |
| `test-definition` | `0.1.0` | Pre-stable until a real ExecutionProvider configuration schema exercises the opaque boundary |
| `run-manifest` | `0.1.0` | Pre-stable until real run lifecycle and environment capture exercise the contract |
| `raw-evidence-manifest` | `0.1.0` | Pre-stable until real collection and Data Plane sealing exercise the contract |
| `dataset-manifest` | `0.1.0` | Pre-stable until ingestion/transformation creates real datasets |
| `telemetry-envelope` | `0.1.0` | Pre-stable until real producer/collector interoperability is demonstrated |
| `analysis-result` | `0.1.0` | Pre-stable until the Analysis Plane produces and a consumer reads real results |

Pre-stable schemas are released, exact, locally resolvable, and immutable. Their maturity permits deliberate evolution through new `0.y.z` files; it does not permit in-place edits or silent coercion.

Promotion to `1.0.0` occurs only in the phase that can demonstrate representative producer/consumer exercise, required provider evidence where applicable, complete fixtures, boundary review, and an explicit compatibility commitment. Promotion creates a new schema document and does not relabel earlier instances.

### 9.3 Shared definitions

Create `schemas/common/v1.0.0.schema.json` for stable reusable serialized forms only:

- typed opaque identifier patterns;
- SHA-256 digest;
- RFC 3339 UTC timestamp;
- schema reference;
- reproducibility assessment.

Do not put domain aggregates or provider configurations in the common schema.

### 9.4 Existing schemas to revise

1. `artifact-manifest`
   - Add `build_record_id` and structured `source_revision`.
   - Separate entity ID from binary SHA-256 content identity.
   - Keep compiler/provider details opaque or namespaced rather than defining MetaEditor fields in the core contract.
   - Remove unconstrained generic metadata unless it is represented by an explicit namespace and schema reference.

2. `run-manifest`
   - Replace `test_id` with `test_definition_revision_id`.
   - Require the artifact reference and an embedded immutable, identified, schema-referenced environment/configuration snapshot so the provenance node is reconstructible without a separate Phase 01 schema.
   - Add reproducibility assessment.
   - Permit an exact sealed raw-evidence-manifest reference when available.
   - Constrain lifecycle values without implementing lifecycle behavior.

3. `test-definition`
   - Add immutable definition and revision identities.
   - Replace core `symbol`, `timeframe`, date, deposit, leverage, and tester-specific fields with a schema-referenced opaque execution configuration.
   - Keep SUT inputs in a separately schema-referenced opaque object.
   - Do not interpret either object in core validation beyond its envelope contract.

4. `telemetry-envelope`
   - Require run ID, stream ID, sequence, UTC timestamp, producer namespace, event type, payload schema reference, and opaque payload.
   - Do not define strategy categories, signals, entries, exits, indicators, or provider-native event types in the core schema.

5. `analysis-result`
   - Require result ID, input dataset IDs, analysis definition ID/version, parameters, computation environment identity, creation timestamp, result schema reference, and provenance.
   - Keep result content schema-referenced rather than embedding analytical formulas or metric catalogs in Phase 01.

Across all core schemas, remove unconstrained generic `metadata` objects unless a concrete Phase 01 use exists. An allowed opaque extension must declare its namespace and exact payload schema; arbitrary fields do not become core vocabulary.

### 9.5 New schemas required by canonical provenance

Add only the missing serialized links required to complete the chain:

1. `build-record/v0.1.0.schema.json`
2. `raw-evidence-manifest/v0.1.0.schema.json`
3. `dataset-manifest/v0.1.0.schema.json`

Do not add comparison, simulation, API request/response, provider configuration, storage layout, MCP, or UI schemas in Phase 01.

### 9.6 Validation strategy

The contract validator must:

- load a closed local catalog keyed by exact `SchemaRef`;
- call Draft 2020-12 schema self-validation during tests;
- instantiate `Draft202012Validator` with the closed local registry and an explicit, non-null `FormatChecker`;
- validate every declared format used by Phase 01 contracts, including date/date-time and URI/UUID formats where declared;
- verify through negative fixtures that structurally valid strings with invalid declared formats are rejected;
- fail tests if a required declared format has no active checker;
- reject unknown schema names or versions explicitly;
- resolve `$ref` only from the in-repository catalog;
- return deterministic contract errors with JSON paths;
- avoid automatic default insertion, coercion, migration, or semantic interpretation;
- keep serialized validation separate from domain invariant validation.

Each schema receives:

- at least one minimal valid fixture;
- a representative complete valid fixture where materially different;
- invalid fixtures for missing discriminator, wrong ID type/prefix, invalid digest, unsupported version, unexpected core property, and broken provenance reference shape.

Installing `jsonschema[format]` is not evidence that format validation is active. The validator wiring and negative fixture tests are both required acceptance evidence.

Compatibility fixtures begin with each schema's actual released version: stable `common/1.0.0` and pre-stable `0.1.0` for the other Phase 01 contracts. Later versions must preserve every historical fixture covered by the declared support policy and validate it against its exact schema.

## 10. Error model

### 10.1 Domain errors

Use a small explicit hierarchy rooted at `DomainError`:

- `InvalidIdentifierError`
- `InvalidValueError`
- `ProvenanceInvariantError`
- `EvidenceInvariantError`

### 10.2 Boundary/application errors

Use a transport-neutral `ApplicationError` containing:

- stable machine-readable `code`;
- safe human-readable `message`;
- optional structured `details`;
- optional request ID;
- original exception only as internal cause, never serialized by default.

Initial codes are limited to:

- `invalid_identifier`
- `invalid_value`
- `invalid_provenance`
- `invalid_evidence_manifest`
- `invalid_configuration`
- `unsupported_schema`
- `schema_validation_failed`

Do not add HTTP status codes, CLI exit-code policy, provider error codes, retry classes, or persistence exceptions in Phase 01. Later adapters map their failures into the application model without changing domain exceptions.

## 11. Configuration conventions

- Use an immutable `Settings` dataclass.
- Use the `EA_RESEARCH_LAB_` environment-variable prefix.
- Precedence is explicit arguments over environment variables over documented defaults.
- Phase 01 defines only settings it consumes, initially logging level and logging format. Do not add database, storage, MetaTrader, API, MCP, scheduler, or analytics settings.
- Parsing is strict; invalid values raise `invalid_configuration` rather than silently falling back.
- Configuration loading has no side effect at import time.
- Secrets are never logged or represented by a generic metadata dump.
- Do not add `.env`, YAML, or configuration-framework dependencies. A local developer may set environment variables through the shell or IDE.

## 12. Logging conventions

- Use the standard-library `logging` and `json` modules.
- Emit one structured JSON object per line to stderr by default.
- Required fields: UTC timestamp, level, logger, event name, and message.
- Optional correlation fields: request ID, run ID, artifact ID, dataset ID, analysis result ID, and error code.
- Use stable event names; prose belongs in `message`.
- Logging configuration is explicit and idempotent; importing a module must not configure global logging.
- Never log raw telemetry payloads, SUT inputs, secrets, complete environment dumps, or arbitrary exception locals.
- Operational logs are not raw evidence, provenance records, or audit records.
- Cross-client audit persistence remains out of scope; Phase 01 defines only request context that later Platform API services can propagate.

## 13. Test architecture

Use `unittest` from the standard library.

### Unit tests

- identifier creation, parsing, prefix isolation, and rejection cases;
- digest, timestamp, schema reference, definition version, and reproducibility values;
- domain/application error shape;
- immutable provenance links;
- raw evidence manifest sealing and late-revision invariants;
- configuration precedence and strict failure;
- structured logging fields and redaction exclusions.

### Contract tests

- every schema parses and passes Draft 2020-12 self-validation;
- every `$id` and instance discriminator is unique;
- every `$ref` resolves locally without network access;
- the actual `Draft202012Validator` instance receives an explicit `FormatChecker`;
- invalid values for every declared required format fail validation, proving the checker is active;
- all valid fixtures pass;
- all invalid fixtures fail with expected stable error codes and paths;
- the complete canonical provenance chain can be represented by linked valid fixtures;
- released historical fixtures remain readable by their exact declared schemas.

### Architecture enforcement tests

Use the standard-library `ast` module to enforce only high-value dependency rules:

- `domain` imports only standard-library or `ea_research_lab.domain` modules;
- `application` does not import infrastructure, contracts, provider, storage, UI, or MCP modules;
- no Phase 01 core module imports MetaTrader, MetaEditor, database, object-storage, dataframe, web, UI, or MCP libraries;
- schemas contain no storage paths/table names and do not define provider- or SUT-specific fields outside explicit opaque/namespaced extension points;
- no future-phase package exists accidentally.

Avoid brittle keyword scans over prose or payload examples. Architecture tests enforce import direction and contract structure; semantic neutrality also requires final human review.

## 14. Quality gates

`python tools/check.py` is the single local entry point and must fail fast with a non-zero exit status. It performs, in order:

1. Python version check for the approved 3.14 baseline, including availability of standard-library `uuid.uuid7()`.
2. `compileall` over `src`, `tests`, and `tools`.
3. `unittest` discovery.
4. Schema self-validation and fixture tests through the test suite.
5. Architecture enforcement tests through the test suite.

Additional repository gates:

- clean virtual-environment installation from the exact dependency lock;
- editable project installation through the declared build backend;
- `git diff --check` before commit;
- final `git status --short` review for unintended artifacts;
- manual ADR/architecture checklist confirming no later-phase capability or forbidden semantic coupling.

Do not add a hosted CI workflow in Phase 01. The local gate must be deterministic and callable unchanged by a later CI system.

## 15. Milestone sequence

| Order | Milestone | Outcome |
|---|---|---|
| M0 | Git initialization verification and baseline | First immutable source revision exists |
| M1 | Repository and test foundation | Installable minimal package and one local quality command |
| M2 | Identifier, value, and error contracts | Stable domain kernel conventions |
| M3 | Provenance, evidence, and reproducibility model | Complete canonical chain is representable in memory |
| M4 | Schema consolidation and validation | Stable common primitives and pre-stable boundary contracts are locally validated |
| M5 | Configuration, request context, and logging | Minimal operational conventions are executable |
| M6 | Architecture enforcement and Phase 01 closure | Boundaries and completion criteria are verified |

## 16. Milestone details

### M0 — Git initialization verification and baseline

#### Objective

Create the first immutable source revision before implementation so subsequent build and result provenance can reference a real committed baseline.

#### Inputs and relevant documents

- `AGENTS.md`
- ADR-0007
- this approved execution plan
- current `git status` and staged-file review

#### Expected files or modules

- `.gitignore` containing only known Phase 01 generated artifacts such as `.venv/`, Python caches, build output, and local test caches.
- `schemas/README.md` explicitly identifies the current `v1.schema.json` files as unreleased design drafts before they enter the Git baseline; this changes no schema contract content.
- Existing repository documentation, schemas, and Codex project configuration included in the baseline unless an explicit review excludes a file.
- No source modules yet.

#### Contracts involved

- `SourceRevision`
- canonical provenance root

#### Tests/checks

- Verify the Git repository root.
- If `.git` is absent in another workspace, initialize it; skip initialization here because it already exists.
- Review staged paths and check for secrets or generated artifacts.
- Run `git diff --cached --check`.
- After the approved baseline commit, verify `git log -1`, `git status --short`, and `git fsck`.

#### Acceptance criteria

- The approved primary branch name is set.
- Exactly one reviewed baseline commit exists before implementation commits.
- The worktree is clean after the baseline commit.
- The commit contains the approved architecture and Phase 01 plan.

#### Out of scope

- Git remote creation;
- hosted repository setup;
- CI workflow;
- release tags;
- signed commits;
- complex branching policy.

### M1 — Repository and test foundation

#### Objective

Create the minimum installable Python structure and a deterministic local test entry point.

#### Inputs and relevant documents

- Phase 01 scope in `docs/roadmap/phases.md`
- `plans/active/phase-01-foundation.md`
- architecture overview dependency rules
- approved Python/dependency decisions

#### Expected files or modules

- `pyproject.toml`
- `requirements.in`
- `requirements.lock`
- `src/ea_research_lab/__init__.py`
- Phase 01 package directories listed in Section 5
- `tests/` directories
- `tools/check.py`
- `docs/development.md`

`pyproject.toml` declares `requires-python = ">=3.14,<3.15"`. The exact Python patch version used by a reproducible environment is captured by the development/toolchain record rather than inferred from entity identifiers.

#### Contracts involved

- Python version baseline
- dependency lock convention
- package dependency direction

#### Tests necessary

- Python 3.14 runtime and `uuid.uuid7()` availability check.
- Clean `.venv` installation from the lock.
- Editable installation smoke test.
- Package import smoke test.
- `tools/check.py` self-test for correct exit propagation.
- Empty test discovery succeeds without hiding import failures.

#### Acceptance criteria

- A new developer can create `.venv`, install the locked environment, and run one documented check command.
- No future-phase package or interface exists.
- Direct and transitive dependencies are visible and pinned in the lock.

#### Out of scope

- Runtime process or daemon;
- API server;
- adapter interfaces;
- provider SDKs;
- persistence;
- hosted CI.

### M2 — Identifier, value, and error contracts

#### Objective

Implement the minimal immutable domain kernel used by provenance and serialized contracts.

#### Inputs and relevant documents

- ADR-0001
- ADR-0002
- ADR-0007
- ADR-0008
- domain documents for Artifact, Test Definition, Run, Dataset, and Analysis
- accepted ADR-0009

#### Expected files or modules

- `domain/identifiers.py`
- `domain/values.py`
- `domain/errors.py`
- `application/context.py`
- `application/identity.py`
- `application/errors.py`
- corresponding unit tests

#### Contracts involved

- typed opaque IDs and prefixes;
- SHA-256 digest;
- UTC timestamp;
- schema name/version/reference;
- definition version;
- source revision;
- request context;
- domain and application error conventions.

#### Tests necessary

- Valid construction and round-trip string serialization.
- Wrong-prefix and cross-type rejection.
- Non-UUIDv7, wrong-variant, and non-canonical UUID rejection.
- Python 3.14 `uuid.uuid7()` generation produces the accepted typed representation.
- Identifier APIs do not expose inferred creation time or semantic ordering; explicit timestamps remain separate values.
- Invalid digest, timestamp, schema name, and version rejection.
- Frozen-value mutation attempts fail.
- Error serialization excludes internal causes and unsafe arbitrary objects.

#### Acceptance criteria

- Every Phase 01 entity reference has one unambiguous typed ID.
- Entity identity and content identity cannot be confused.
- No domain behavior derives timestamps or ordering from UUIDv7.
- All domain values are immutable and provider/storage neutral.
- Error codes are stable and transport neutral.

#### Out of scope

- Aggregate repositories;
- API error responses;
- provider failures;
- retry policy;
- entity lifecycle services;
- comparison and simulation IDs.

### M3 — Provenance, evidence, and reproducibility model

#### Objective

Represent every canonical provenance link and raw-evidence immutability rule as small immutable domain structures.

#### Inputs and relevant documents

- ADR-0003
- ADR-0007
- architecture overview provenance and raw evidence sections
- relevant domain documents

#### Expected files or modules

- `domain/evidence.py`
- `domain/provenance.py`
- unit tests and representative in-memory examples
- domain documentation corrections discovered while implementing the approved model

#### Contracts involved

- Build, run, evidence, dataset, and analysis provenance records;
- raw evidence object descriptor;
- sealed raw evidence manifest;
- sealed raw evidence manifest reference with external content digest;
- prior-manifest revision link;
- reproducibility assessment.

#### Tests necessary

- Complete provenance chain can be assembled from typed references.
- Missing mandatory links fail at construction.
- Raw object and manifest instances are immutable.
- Duplicate raw object IDs in a manifest are rejected.
- Late manifest revision must identify a prior manifest for the same run.
- `BEST_EFFORT` and `UNAVAILABLE` require limitation reasons.
- An `EXACT` value remains a recorded assertion, not an inferred provider capability.

#### Acceptance criteria

- A result can be traced in memory to source revision without storage or provider types.
- Collection state is not confused with a sealed evidence set.
- Failed and partial collection outcomes can be represented without mutating evidence.
- No graph database, repository, traversal service, or file hashing implementation exists.

#### Out of scope

- Reading Git metadata in application code;
- build execution;
- evidence collection;
- file or object storage;
- provider capability probing;
- replay;
- analytical computation.

### M4 — Schema consolidation and validation

- Milestone status: Completed and approved

#### Objective

Release the first internally consistent, machine-validated schema set with maturity assigned per contract: stable common primitives and pre-stable unexercised boundary contracts.

#### Inputs and relevant documents

- ADR-0001, ADR-0003, ADR-0007, and ADR-0008
- `schemas/README.md`
- all existing draft schemas
- M2 and M3 conventions

#### Expected files or modules

- Exact schema files listed in Section 9
- `contracts/catalog.py`
- `contracts/validation.py`
- valid and invalid fixtures
- contract tests
- updated `schemas/README.md`
- updated domain documents where contract names or provenance references changed

#### Contracts involved

- common serialized values;
- build record;
- artifact manifest;
- test-definition revision;
- run manifest;
- raw-evidence manifest;
- dataset manifest;
- telemetry envelope;
- analysis result.

#### Tests necessary

- Schema self-validation.
- Closed local `$ref` resolution.
- Exact discriminator lookup.
- Positive and negative fixture validation.
- Explicit `FormatChecker` wiring test.
- Invalid date/date-time and every other declared-format fixture must fail specifically because of format validation.
- Unsupported-version error behavior.
- Full linked provenance fixture validation.
- Explicit tests that execution configuration and telemetry payload remain opaque and schema-referenced.

#### Acceptance criteria

- `common/1.0.0` is released as stable only after its provider-independent primitives pass ADR and contract tests.
- The eight unexercised boundary contracts are released as exact pre-stable `0.1.0` schemas and remain immutable after milestone acceptance.
- No pre-stable contract is presented as stable merely because it exists or passes metaschema validation.
- Existing draft inconsistencies (`test_id`, incomplete provenance, unconstrained identity, provider-shaped test configuration, and empty provenance objects) are removed.
- Validation explicitly activates `FormatChecker`, never accesses the network, and never silently coerces/migrates input.
- No storage location or provider-native type appears in a core schema.

#### Out of scope

- Provider-specific execution schemas;
- storage layout schemas;
- schema migration engine;
- generated domain classes;
- API, MCP, UI, comparison, or simulation schemas;
- ingestion runtime.

### M5 — Configuration, request context, and logging

#### Objective

Make the Phase 01 package operable and diagnosable without introducing a runtime service or external observability technology.

#### Inputs and relevant documents

- ADR-0002 cross-client context ownership
- architecture principles P12 and P19
- approved configuration and logging conventions

#### Expected files or modules

- `infrastructure/config.py`
- `infrastructure/logging.py`
- additions to `application/context.py` only if required
- unit tests
- development documentation

#### Contracts involved

- immutable settings;
- request context;
- structured operational log record;
- safe error fields.

#### Tests necessary

- Configuration precedence and invalid-value failure.
- No configuration or logging side effects on import.
- UTC timestamp and required structured log fields.
- Optional typed correlation IDs serialize correctly.
- Raw payloads, SUT inputs, and internal exception causes are not emitted by default.
- Repeated logging configuration is idempotent.

#### Acceptance criteria

- Phase 01 consumes only declared settings.
- Logging is structured, deterministic enough for tests, and storage/provider neutral.
- Operational logging is explicitly distinct from raw evidence and future audit persistence.
- No configuration or logging dependency is added.

#### Out of scope

- Secret manager integration;
- `.env` loading;
- file logging;
- telemetry backend;
- tracing system;
- audit database;
- Platform API runtime.

### M6 — Architecture enforcement and Phase 01 closure

#### Objective

Verify that Phase 01 establishes stable boundaries and nothing from a later phase has been implemented accidentally.

#### Inputs and relevant documents

- all accepted ADRs;
- architecture overview and principles;
- Phase 01 plan and acceptance criteria;
- final implementation diff.

#### Expected files or modules

- `tests/architecture/test_dependencies.py`
- `tests/architecture/test_contract_neutrality.py`
- final `tools/check.py`
- finalized `docs/development.md`
- aligned `README.md`, `schemas/README.md`, and affected domain documents
- Phase 01 plan status update only after acceptance

#### Contracts involved

- package dependency direction;
- strategy/provider/storage neutrality;
- schema release policy;
- local quality-gate contract.

#### Tests necessary

- All quality gates in Section 14.
- Architecture import scan.
- Contract-neutrality assertions.
- Clean-environment installation and check run.
- Manual final review against every accepted ADR.

#### Acceptance criteria

- All automated checks pass from a clean environment.
- Domain imports only standard-library/domain modules.
- The complete canonical provenance fixture validates.
- No MetaTrader-, storage-, API transport-, UI-, analysis-engine-, or MCP-specific implementation exists.
- No strategy-specific property appears in a core contract.
- All dependencies are approved, justified, and locked.
- Documentation describes actual Phase 01 behavior without claiming later-phase capabilities.

#### Out of scope

- Any Phase 02 or later implementation;
- hosted CI/CD;
- performance optimization;
- production deployment;
- provider, storage, API, analysis, UI, or MCP integration.

## 17. Objective Phase 01 completion criteria

Phase 01 is complete only when all of the following are true:

1. A reviewed Git baseline predates implementation and every Phase 01 change is committed with a clean worktree.
2. Python 3.14 and all dependencies are declared; the environment is reproducible from the lock and exposes standard-library `uuid.uuid7()`.
3. The minimal package structure exists without empty future-phase scaffolding.
4. Typed opaque identifiers and value objects enforce their invariants.
5. The complete canonical provenance chain is representable without provider or storage types.
6. Raw evidence objects and sealed manifests have tested immutability and revision semantics.
7. Reproducibility levels and limitations are represented without promising provider determinism.
8. Stable `common/1.0.0` and the eight pre-stable `0.1.0` contracts are self-validating, locally resolvable, fixture-tested, correctly labeled by maturity, and immutable after release.
9. Unsupported schema versions fail explicitly and no silent migration/coercion occurs.
10. JSON Schema format validation is explicitly activated with `FormatChecker`, and invalid-format fixtures prove it is effective.
11. Domain and application errors are stable, safe, and transport neutral.
12. Configuration and logging use only approved standard-library mechanisms and declared settings.
13. Architecture tests enforce domain dependency direction and detect accidental provider/storage/future-phase coupling.
14. The single local quality command passes in a clean environment.
15. Documentation and implemented contracts agree.
16. No Phase 02 or later runtime capability is present.

## 18. Risks and mitigations

### Incorrect schema maturity

Risk: provider-, data-, or analysis-facing schemas may be labeled stable before their real producers and consumers exercise them.

Mitigation: begin unexercised boundary contracts at immutable pre-stable `0.1.0`, retain exact historical versions, and promote only after the ADR-0008 evidence criteria. Keep provider configuration and payloads schema-referenced and opaque.

### Opaque extension points becoming ungoverned dumping grounds

Risk: arbitrary objects could bypass validation or leak strategy semantics into shared vocabulary.

Mitigation: require a schema reference and namespace for opaque content; core validates the envelope but does not promote payload fields into core contracts.

### Identifier convention lock-in

Risk: ID prefixes and UUID representation enter every schema and are expensive to change.

Mitigation: enforce accepted ADR-0009, keep UUIDv7 timestamps semantically opaque, and separate SHA-256 content hashes from entity identity.

### Incomplete dependency reproducibility

Risk: pinning only direct dependencies allows transitive drift.

Mitigation: create the lock from a clean virtual environment and verify installation from that lock.

### Python 3.14 is not installed in the current workspace

Risk: M1 cannot create or validate the approved environment until the Python 3.14 toolchain is available.

Mitigation: after M0, install an approved Python 3.14 distribution, verify `python --version` and `uuid.uuid7()`, declare `>=3.14,<3.15`, and capture the exact patch version used. Do not fall back silently to the currently installed Python 3.12.

### Schema validator dependency surface

Risk: `jsonschema[format]` introduces transitive dependencies.

Mitigation: isolate it in `contracts`, lock all resolved versions, do not expose library types outside that module, and test explicit `FormatChecker` activation rather than assuming the extra enables validation.

### No third-party formatter, linter, type checker, or test framework

Risk: some style or typing issues will rely on tests and review.

Mitigation: keep Phase 01 code small, immutable, and fully exercised; use `compileall`, `unittest`, strict constructors, and AST boundary tests. Add a tool only when code volume or observed defects justify it.

### Git baseline contains pre-release draft schemas

Risk: the initial commit records schemas that M4 later replaces.

Mitigation: label the existing files as drafts without released identity. M4 creates the first compatibility baseline using stable `common/1.0.0` and exact pre-stable `0.1.0` versions for unexercised boundary contracts.

### Operational logs confused with evidence or audit records

Risk: future work may treat logs as authoritative research evidence or cross-client audit history.

Mitigation: document and test the distinction; evidence and audit persistence remain separate later responsibilities.

## 19. Approved decisions and execution authorization

The owner has approved:

1. Python 3.14 as the Phase 01 language baseline.
2. Package name `ea_research_lab` and the minimal `src` layout.
3. Primary Git branch name `main` and creation of the initial baseline commit from the currently untracked repository.
4. Typed-prefix UUIDv7 entity identifiers, with UUIDv7 semantics opaque to consumers.
5. Strict separation of entity identity from SHA-256 content identity.
6. Exact semantic schema versions, repository-owned URN schema IDs, closed local resolution, and maturity assigned per contract.
7. `jsonschema[format]` as the only direct functional third-party dependency and `setuptools` as the build backend.
8. Explicit `FormatChecker` activation and negative format tests.
9. Standard-library `unittest`, configuration, logging, and architecture checks instead of additional developer frameworks.
10. No pytest, Pydantic, Ruff, mypy, ORM, DI container, or task runner in Phase 01.
11. Frozen dataclasses and immutable provenance records.

These decisions approve the plan but do not authorize execution. M0 begins only after the owner gives final explicit authorization.

## 20. Accepted ADR-0009

ADR-0009 — Entity identity and content identity is accepted and required by M2 and all serialized identifier schemas. It establishes:

- typed opaque entity IDs;
- typed prefix plus canonical UUIDv7 representation;
- explicit prohibition on consuming the UUIDv7 timestamp or ordering as domain data;
- entity identity versus SHA-256 content identity;
- canonical parsing/serialization;
- exact schema identity as a separate URN plus semantic version;
- prohibition on provider, storage, strategy, lifecycle, and mutable metadata inside IDs.

No other new ADR is required by this adjusted plan. If implementation later requires a new boundary, persistence decision, provider contract, or public API decision, work must stop and propose that ADR rather than expanding Phase 01 silently.

## 21. Explicit deferrals

The following remain entirely deferred to their roadmap phases:

- BuildProvider and MetaEditor integration;
- ExecutionProvider and MetaTrader integration;
- provider-specific execution configuration schemas;
- artifact or evidence storage adapters;
- run orchestration and lifecycle execution;
- telemetry ingestion;
- normalization and derived-data computation;
- analytical/run integrity algorithms;
- metrics, timeseries, distributions, comparisons, robustness, and simulations;
- Semantic Layer runtime models beyond the neutral contracts required by Phase 01 provenance;
- Platform API command/query services and transports;
- visual analytics;
- MCP;
- scheduling, distributed execution, and deployment.
