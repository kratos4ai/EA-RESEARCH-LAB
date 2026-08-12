# Phase 06 — Data Plane & Persistence Execution Plan

- Status: Completed
- Scope: Phase 06 only
- Baseline: completed Phase 05 at `27f1c0c4d08ca5aaba07b10a360e86e403c7ce30`
- Runtime: Python `>=3.14,<3.15`
- Git policy: no milestone commits; one consolidated Phase 06 commit only after
  M1–M4 are completed and approved

## Objective

Make the implemented canonical research chain survive process termination:

```text
Source Revision
-> Build Record
-> Artifact
-> Run
-> sealed Raw Evidence
-> Dataset
-> Analysis Result
```

Phase 06 persists existing durable facts and exact bytes. It does not redesign
domain concepts around storage, add analytical meaning, or introduce client
query capabilities. Dependency direction remains:

```text
existing domain/application values
-> storage-neutral Data Plane application port
-> SQLite infrastructure adapter
```

Physical tables, database paths, SQL, transactions, and SQLite exceptions stay
inside infrastructure. Future Platform API application services must use
application capabilities and must never call the adapter directly.

## Scope boundaries

Phase 06 includes:

- immutable publication and integrity-checked loading of implemented records;
- exact byte retention for accepted Artifacts, Raw Evidence, Dataset content,
  and Analysis content;
- exact schema URN/version retention and validation;
- content-addressed deduplication by existing SHA-256 identity;
- restart-safe reconstruction of equivalent durable facts;
- end-to-end reconstruction of the existing provenance chain;
- explicit corruption and conflict detection;
- one local SQLite adapter using only the Python standard library.

Phase 06 excludes:

- Semantic Layer models or projections;
- Platform API Command or Query capabilities and bounded retrieval;
- persistence-oriented redesign of domain objects;
- ORM, generic repository, Unit of Work, registry, migration framework, or
  generic serialization framework;
- network/database servers, Docker, cloud/object storage, queues, distributed
  workers, or distributed concurrency;
- retention policies, TTL, garbage collection, archival tiers, compression, or
  recovery/repair automation;
- authentication, authorization, UI, MCP, telemetry, Test Matrix, experiment
  generation, optimizer, ranking, or SUT Descriptor;
- new analytical, provider, build, or execution behavior;
- silent schema migration or coercion;
- source dependency parsing or source snapshot archive infrastructure.

## Reused foundations

The implementation must reuse without redesign:

- typed UUIDv7 entity IDs and SHA-256 content identities;
- `SchemaReferencedPayload`, local schema catalog, Draft 2020-12 validation,
  and explicit `FormatChecker` behavior;
- `BuildWorkflowResult`, `ArtifactAcceptance`, `AcceptedArtifact`,
  `RunExecutionResult`, `CollectedRawEvidence`, `Dataset`, and
  `AnalysisResult` as sources of already validated facts;
- Build Input, Artifact, Build Record, Test Definition, Run, Raw Evidence,
  Dataset, and Analysis contracts at their exact existing versions;
- `RequestContext`, safe application errors, configuration conventions, and
  operational logging restrictions;
- canonical JSON conventions already used for Dataset and Analysis content;
- architecture tests enforcing `domain <- application <- infrastructure`.

No new serialized contract is planned. SQLite DDL is private adapter state, not
a platform schema. If an existing durable fact cannot be represented without a
new cross-boundary contract, implementation must stop and present the concrete
blocker before changing schemas or architecture.

## Storage backend decision

### Recommendation: one SQLite database

Use Python's standard-library `sqlite3` module for both immutable content BLOBs
and published record metadata. Do not add an ORM or another storage technology.

SQLite is the minimum reliable backend because it provides:

- atomic multi-row publication and rollback after process failure;
- uniqueness constraints for entity/content conflict detection;
- serialized local writes without a distributed locking design;
- exact BLOB retention;
- deterministic lookup by typed entity ID or digest;
- one portable database file with no server, network, Docker, or dependency;
- close/reopen tests that model fresh application state.

A filesystem-only store is not selected because safely publishing related
content and records would require a custom crash-consistency, no-overwrite, and
concurrent-writer protocol. A filesystem-plus-SQLite design adds a second
failure boundary without a current size or throughput requirement. PostgreSQL
or another server would violate the portable gate and current operational
needs.

Known ceiling: SQLite BLOB storage is appropriate for the Lab's currently
bounded artifacts and evidence. A future measured size or throughput limit may
justify a different adapter without changing application/domain semantics.

### Private logical storage model

The exact DDL belongs to the adapter, but it should remain no broader than:

```text
content_objects
  digest           SHA-256 primary key
  byte_length      exact length
  content          exact immutable BLOB

published_records
  record_kind      bounded adapter-owned kind
  record_key       typed entity ID or existing content identity
  schema_ref       exact schema URN/version
  document_digest  SHA-256 reference to canonical bytes in content_objects
  primary key (record_kind, record_key)
```

Published record JSON is itself stored once in `content_objects`; the record
row maps its durable identity to those canonical bytes. Artifact, Raw Evidence,
Dataset, and Analysis content use the same content table and deduplicate only
when their exact bytes share a digest. Record kinds and tables are
infrastructure details and must not appear in domain, semantic, or API
contracts.

Raw Evidence object descriptors remain in the sealed manifest. The adapter may
maintain a private uniqueness index from Raw Evidence Object ID to its exact
descriptor/content digest solely to reject conflicting ID reuse; this is not a
new persisted platform record or schema.

## Minimum durable facts

### Build publication

Persist:

- `build-record/0.2.0`, including Source Revision, build configuration, provider
  evidence when present, outcome, and references;
- `build-input-manifest/0.1.0` when the Build established one, keyed by its
  existing `build_input_identity`;
- `artifact-manifest/0.1.0` and exact accepted Artifact bytes for a successful
  Build;
- the Artifact byte length as private integrity metadata.

Failed Build Records remain durable without inventing an Artifact. Phase 06
does not archive build-source snapshot bytes: ADR-0010 separates historical
content identity from retained bytes, and the current Build result publishes a
Build Input Manifest rather than a source archive. This limitation must remain
visible and must not upgrade the execution reproducibility assessment.

### Execution publication

Persist:

- the exact `test-definition/0.1.0` document used by the Run, keyed by Test
  Definition Revision ID;
- `run-manifest/0.1.0`;
- every `raw-evidence-manifest/0.1.0` revision supplied for the Run, including
  its external canonical content digest and prior-manifest reference;
- exact bytes for every Raw Evidence Object declared by each persisted
  manifest, with declared byte length and content digest.

Environment/configuration and execution reproducibility remain represented
inside the existing Run Manifest. Provider observations are persisted only
where already represented by an accepted record or captured Raw Evidence; no
standalone provider-observation record is invented.

### Dataset publication

Persist:

- `dataset-manifest/0.2.0` keyed by Dataset ID;
- exact canonical Dataset content bytes keyed by the manifest's
  `content_digest`;
- the exact Dataset content schema reference already declared by the manifest;
- existing transformation identity, version, parameters, and input lineage
  from the manifest.

### Analysis publication

Persist:

- `analysis-result/0.2.0` keyed by Analysis Result ID;
- exact deterministic Analysis content bytes keyed by `result_digest`;
- existing input Dataset ID/digest references, Analysis Definition/version,
  parameters, and computation environment identity.

`analysis-result/0.2.0` embeds the result document for contract compatibility.
The adapter still stores the canonical Analysis content object separately and
verifies that the embedded value canonicalizes to the declared digest. Phase
06 does not evolve this historical envelope merely to change physical storage.

No separate record is created for an in-memory helper when the durable fact is
already embedded in one of these exact published documents.

## Application boundary

Create one narrow storage-neutral `DataPlane` port in
`application/data_plane.py`. It must expose explicit capabilities rather than
generic repositories:

```text
publish_build / load_build
publish_run / load_run
publish_dataset / load_dataset
publish_analysis / load_analysis
```

This is the final Phase 06 surface, not M1 scaffolding. M1 introduces and fully
implements only `publish_build / load_build`; M2 adds each remaining pair with
its real consumer and tests. Do not add placeholder methods or unsupported
branches.

Publication inputs and loaded results may be small frozen application values
composed from existing schema-referenced records, typed IDs, and exact bytes.
They are not persisted as Python object snapshots. They must not contain paths,
SQL connections, rows, table names, cursors, or SQLite exceptions.

The port may be split into read/write protocols only if tests demonstrate a
real dependency-direction need. Do not create `BaseRepository`,
`GenericRepository[T]`, factories, registries, sessions, or Unit of Work.

Application operations own orchestration and safe `ApplicationError` mapping.
The adapter owns transactions, physical storage, and verification of bytes read
from SQLite. Integrity failures must use a bounded transport-neutral error code
and must never expose database paths, SQL, raw bytes, provider payloads, or
credentials through logs/errors.

## Write invariants

Every publication must validate the complete proposed unit before commit and
must execute in one SQLite transaction.

### Content objects

- compute SHA-256 over the supplied exact bytes;
- require computed digest to equal the declared digest;
- require declared byte length where one exists;
- insert new bytes under their digest;
- treat exact existing bytes under the digest as an idempotent success;
- reject an existing digest with different bytes or length;
- never update accepted content in place.

### Published records

- canonicalize record JSON with the existing UTF-8, sorted-key, compact,
  no-NaN convention;
- validate the exact declared schema through the local catalog before write;
- verify record entity/content identity and all links owned by the publication;
- insert an unseen record identity;
- treat the exact same canonical record as an idempotent success;
- reject reuse of an entity ID or Build Input identity with different durable
  bytes, schema reference, or linked content;
- never update a published/sealed record in place;
- publish a new Raw Evidence Manifest ID for an allowed revision and validate
  its prior-manifest link.

The transaction commits only after all content and records in the publication
agree. Failure rolls back the complete publication. No broad retry or
distributed idempotency infrastructure is introduced.

## Load and integrity invariants

Loading is verification, not blind deserialization. Each load must:

- retrieve by the requested typed ID or existing content identity;
- require a known, locally supported exact schema URN/version;
- validate canonical document bytes against that schema;
- recompute and compare document/content SHA-256;
- compare byte length where declared;
- verify the requested entity identity against the loaded document;
- verify Artifact, Raw Evidence, Dataset, and Analysis content links;
- verify Raw Evidence manifest membership and prior revision links;
- verify Build -> Artifact, Run -> Test Definition/Artifact/Evidence,
  Dataset -> Evidence/Dataset inputs, and Analysis -> Dataset ID/digest links;
- reconstruct equivalent immutable durable facts using existing domain/value
  validation where applicable;
- fail explicitly on missing, malformed, unsupported, corrupted, duplicate, or
  conflicting data.

Load must not repair, migrate, coerce, or overwrite data. Tests may mutate the
private database directly to simulate corruption; production application code
must not expose such mutation capability.

## Provenance reconstruction after restart

No separate lineage graph or Semantic projection is required. Reconstruction
follows references already present in exact records:

```text
Analysis Result input Dataset IDs/digests
-> Dataset Manifest input Raw Evidence Manifest reference
-> Raw Evidence Manifest Run ID and object descriptors
-> Run Manifest Artifact ID and Test Definition Revision ID
-> Test Definition Artifact ID
-> Artifact Manifest Build Record ID
-> Build Record Source Revision and Build Input identity
```

The reconstructed chain must also retrieve and validate the exact Artifact,
Raw Evidence, Dataset, and Analysis bytes. M3 tests must discard all original
in-memory aggregates, close the database connection, create a new adapter and
application state, and reconstruct the chain only from durable identities.

## Schema and version handling

- persist exact schema URNs and canonical document bytes;
- validate only through the closed local schema catalog;
- support only versions explicitly listed by the catalog;
- retain historical bytes unchanged;
- fail visibly on unknown or mismatched versions;
- never resolve a schema over the network;
- add no migration table or migration runner in Phase 06;
- make private SQLite DDL initialization explicit and idempotent, but do not
  describe it as platform schema evolution.

No JSON Schema change is expected. A schema change is permitted only after an
actual representational blocker is demonstrated and separately approved.

## Configuration and operational behavior

- pass the database path explicitly when constructing the SQLite adapter;
- use no environment discovery, global connection, singleton, or import-time
  filesystem/database side effect;
- create/open the database only through an explicit operation;
- keep database paths and SQL out of domain values and safe error/log payloads;
- use bounded operational events and existing request context where an
  application publication operation already has it;
- never log Artifact, Raw Evidence, Dataset, Analysis, configuration, or SUT
  payload bytes;
- close connections deterministically in tests and application-owned lifetime;
- use SQLite's local transactions and uniqueness constraints; document that
  distributed/multi-host writers are unsupported.

## Minimal expected structure

```text
src/ea_research_lab/application/data_plane.py
src/ea_research_lab/infrastructure/sqlite_data_plane.py
tests/test_data_plane_application.py
tests/test_sqlite_data_plane.py
tests/integration/test_mt5_strategy_tester.py       # M4 extension only
tests/architecture/test_dependencies.py             # M4 if needed
tests/architecture/test_contract_neutrality.py      # M4 if needed
docs/architecture/data-plane.md
docs/development.md                                 # only actual usage/limits
plans/active/phase-06-execution-plan.md
```

Do not create a new package hierarchy unless these two cohesive modules become
unmanageably large during implementation. Do not add a `repositories`,
`storage`, `database`, or `migrations` framework directory speculatively.

## M1 — Data Plane Boundary and Durable Model

- Status: Completed

### Objective

Implement the smallest storage-neutral application port and SQLite adapter
foundation. Prove exact content and published-record immutability, idempotency,
conflict rejection, transaction rollback, and close/reopen behavior before
connecting any complete workflow.

### Inputs and contracts

- `docs/architecture/data-plane.md`;
- ADR-0003, ADR-0004, ADR-0007, ADR-0008, and ADR-0009;
- existing canonical JSON, schema catalog, identity, digest, and error values;
- all exact Build, Run, Evidence, Dataset, and Analysis contracts listed above.

### Expected files

- `src/ea_research_lab/application/data_plane.py`;
- `src/ea_research_lab/infrastructure/sqlite_data_plane.py`;
- `tests/test_data_plane_application.py`;
- `tests/test_sqlite_data_plane.py`.

### Implementation sequence

1. Define frozen publication/load values composed only of existing durable
   records, typed identities, schema references, and bytes.
2. Define one explicit `DataPlane` port with the fully implemented
   `publish_build / load_build` pair; do not add generic CRUD or placeholders
   for later milestone operations.
3. Add bounded application error outcomes for write, read, and integrity
   failures without exposing infrastructure details.
4. Implement explicit SQLite initialization with the two logical storage areas,
   no import-time side effects, and no migration framework.
5. Implement private content/record publication and verified loading primitives
   used only by the capability-specific adapter methods.

### Tests

- explicit path/open/close behavior and fresh connection reload;
- exact BLOB round trip including arbitrary binary bytes;
- declared digest and byte-length rejection;
- exact idempotent content/record publication;
- conflicting digest, entity ID, record bytes, or schema rejection;
- complete rollback when one member of a publication fails;
- concurrent local connection conflict fails safely or serializes through
  SQLite without overwriting;
- malformed/unsupported schema fails through a bounded safe error;
- database path, SQL, raw bytes, and internal causes are not serialized or
  logged automatically;
- no new dependency and no global/import-time connection.

### Acceptance criteria

- application/domain code imports no `sqlite3`, `pathlib`, SQL, or adapter type;
- all writes validate before an atomic commit;
- exact repeated publication succeeds without duplication;
- conflicting publication leaves durable state unchanged;
- a new adapter instance loads and verifies an accepted record/content object;
- the authoritative portable gate requires no external service or network.

### Out of scope

Complete canonical-chain publication, corruption matrix, real MT5 integration,
Semantic/API retrieval, migration, backup, recovery, and performance tuning.

## M2 — Canonical Chain Persistence

- Status: Completed

### Objective

Connect the explicit Data Plane capabilities to every implemented durable tier
and prove exact round trips for Build/Artifact, Run/Evidence, Dataset, and
Analysis independently.

### Inputs and contracts

- M1 port and adapter invariants;
- successful and failed `BuildWorkflowResult` facts;
- Test Definition and `RunExecutionResult` facts;
- `Dataset` and `AnalysisResult` immutable aggregates;
- exact existing manifests/envelopes and content schemas.

### Expected files

- `src/ea_research_lab/application/data_plane.py`;
- `src/ea_research_lab/infrastructure/sqlite_data_plane.py`;
- `tests/test_data_plane_application.py`;
- `tests/test_sqlite_data_plane.py`.

### Implementation sequence

1. Publish/load Build Record and optional Build Input; for success, atomically
   include Artifact Manifest and exact Artifact bytes.
2. Publish/load Test Definition, Run Manifest, sealed Raw Evidence Manifest,
   and all exact Raw Evidence bytes.
3. Publish/load Dataset Manifest 0.2.0 and canonical Dataset content.
4. Publish/load Analysis Result 0.2.0 and canonical Analysis content.
5. Validate references to already durable upstream records before accepting a
   downstream publication; never infer or synthesize a missing link.

### Tests

- failed Build persists without Artifact and successful Build requires it;
- Artifact bytes/digest and Build/Artifact/Build Input references round trip;
- completed, failed, cancelled, and collection-failed evidence outcomes retain
  all actually captured bytes and a sealed manifest;
- manifest revisions append through a valid prior reference without mutation;
- Dataset content/schema/digest/transformation lineage round trip;
- Analysis content/envelope/result digest/input Dataset references round trip;
- duplicate immutable content is stored once by digest;
- exact entity ID reuse is idempotent and conflicting reuse fails closed;
- no provider/storage type enters the domain or serialized contracts.

### Acceptance criteria

- every minimum durable fact listed by this plan can be published and loaded;
- exact bytes before and after reload are identical;
- all existing exact schemas validate on write and read;
- no standalone persisted helper or provider observation is invented;
- no existing runtime workflow is forced to depend on SQLite directly;
- no schema or dependency is added without a demonstrated blocker and approval.

### Out of scope

Cross-process full-chain reconstruction, deliberate physical corruption,
application query services, indexes for ad hoc queries, migration, retention,
and real provider expansion.

## M3 — Reload, Integrity and Provenance

- Status: Completed

### Objective

Prove that a fresh application state can reconstruct equivalent durable facts
and the complete canonical provenance chain, while detecting corruption rather
than trusting or repairing stored data.

### Inputs and contracts

- M2 persisted records/content and explicit load capabilities;
- accepted provenance and evidence revision rules;
- exact schema catalog and historical version policy.

### Expected files

- `src/ea_research_lab/application/data_plane.py`;
- `src/ea_research_lab/infrastructure/sqlite_data_plane.py`;
- `tests/test_sqlite_data_plane.py`;
- focused fixtures only if inline durable records make a test unclear.

### Tests

- persist complete synthetic chain, close all state, reopen, load, validate, and
  reconstruct equivalent durable facts;
- mutated Artifact bytes;
- mutated Raw Evidence bytes and byte length;
- mutated Dataset content;
- mutated Analysis content or embedded result;
- mismatched content/document digest;
- broken Build/Artifact, Run/Evidence/Test Definition, Dataset/Evidence, or
  Analysis/Dataset reference;
- conflicting entity identity;
- malformed persisted JSON;
- schema URN/version mismatch and unsupported historical version;
- missing referenced content/record;
- no automatic repair, migration, fallback, or network schema resolution.

### Acceptance criteria

- restart round trip preserves exact bytes, identities, schemas, and durable
  semantics without relying on original Python object identity;
- reconstruction traverses Source Revision through Analysis Result using only
  explicit durable references;
- every required corruption class produces an explicit bounded integrity
  failure;
- corruption of one object never causes another immutable object to be
  overwritten or silently substituted;
- storage/data integrity remains separate from Run and Analysis validity.

### Out of scope

Repair, backup/restore product features, migrations, lineage projections,
query optimization, distributed transactions, or Platform API behavior.

## M4 — Enforcement and Closure

- Status: Completed

### Objective

Machine-enforce the final boundary, prove the existing controlled real MT5
vertical through persistence and fresh reload, align documentation, and close
Phase 06 without introducing Phase 07 capability.

### Expected files

- `tests/architecture/test_dependencies.py`;
- `tests/architecture/test_contract_neutrality.py`;
- `tests/integration/test_mt5_strategy_tester.py`;
- `docs/architecture/data-plane.md`;
- `docs/development.md` only for implemented local usage and limitations;
- `plans/active/phase-06-execution-plan.md`.

### Architecture enforcement

- domain and application contain no SQLite, table, row, path, SQL, or BLOB
  semantics;
- only the infrastructure adapter imports `sqlite3`;
- the port exposes explicit Data Plane capabilities, not generic repositories;
- no Semantic Layer, Platform API, persistence-aware analysis, ORM, registry,
  migration framework, or future-phase module exists;
- operational logging cannot emit persisted bytes, payloads, SQL, or paths;
- historical contracts and the dependency lock remain unchanged unless an
  approved blocker required otherwise.

### Portable and real tests

- run the authoritative portable gate and full portable unittest discovery;
- run all SQLite tests in disposable temporary directories with closed/reopened
  connections and no network/service requirement;
- extend the existing controlled MT5 test only enough to persist the real
  Build, Artifact, Run, Raw Evidence, three Datasets, and Analysis Result;
- discard original application state, reopen the SQLite Data Plane, validate
  exact bytes/digests/contracts, and reconstruct the full provenance chain;
- retain the current known fixture facts and analytical outputs;
- confirm no related MetaEditor, terminal, or tester process remains;
- run `compileall`, `pip check`, and `git diff --check`.

### Acceptance criteria

- the real controlled chain survives state disposal and verified reload;
- every Phase 06 write, read, corruption, provenance, and boundary criterion is
  machine-enforced;
- all portable tests pass without MetaTrader, server, network, Docker, or cloud;
- no dependency, speculative schema, or Phase 07 capability was introduced;
- M1–M4 and Phase 06 documentation match the implemented state;
- the cumulative Phase 06 diff is reviewed and approved before its single
  consolidated commit.

### Out of scope

Any new provider behavior, Semantic Layer/API planning or implementation,
retention/GC, migration, repair, scalability work, or external storage backend.

## Quality gates

Every milestone must run focused tests plus the authoritative portable gate.
Before Phase 06 closure run:

```text
python tools/check.py
python -m unittest discover -s tests -p "test_*.py"
controlled real MT5 vertical integration (explicit opt-in environment)
python -m compileall -q src tests tools
python -m pip check
git diff --check
```

The portable suite must create isolated temporary SQLite databases and must not
depend on MetaTrader, an external database, network access, Docker, cloud
services, machine-global configuration, or persistent test order.

## Objective completion criteria

Phase 06 is complete only when:

- all minimum durable records and exact content bytes are persisted;
- immutable/idempotent/conflict and atomic publication rules are proven;
- a fresh application state reloads equivalent durable facts;
- corruption and broken provenance fail explicitly without repair;
- the complete canonical chain is reconstructible after restart;
- the controlled MT5 vertical survives persistence/reload;
- storage types remain behind the application port;
- historical contracts, strategy neutrality, and existing runtime semantics
  remain intact;
- no Phase 07 capability, schema migration, or retention system exists;
- M1–M4 are approved and one consolidated phase commit is separately
  authorized.

## Major risks

| Risk | Required treatment |
|---|---|
| Partial publication leaves a visible record without its bytes or references | Validate first and publish the complete capability-specific unit in one SQLite transaction. |
| Entity ID or digest reuse hides conflicting durable data | Unique keys plus exact byte/schema comparison; identical writes are idempotent and conflicts fail closed. |
| Reload trusts valid-looking but corrupted storage | Recompute hashes, lengths, schemas, identities, and references on every load used by the application. |
| Analysis Result embeds content while content is also addressable | Preserve the historical envelope, store canonical result content by digest, and verify equality; do not evolve the contract for storage convenience. |
| Build input identity is mistaken for retained source bytes | Persist the Build Input Manifest and retain the ADR-0010 reproducibility limitation; do not claim a source archive. |
| SQLite BLOB size or write contention eventually exceeds local needs | Document the local bounded ceiling; replace only the adapter after measured evidence, without leaking storage semantics inward. |
| Test corruption hooks become production mutation APIs | Mutate SQLite directly only in infrastructure tests; expose no repair or arbitrary update capability. |

## Existing infrastructure follow-ups

### External schema packaging in wheels

This is not a Phase 06 blocker. The approved scope runs from the repository and
the portable gate resolves the existing external schemas locally. Installed
wheel support remains unproven and must stay visible. Revisit it before claiming
that an installed distribution can validate persisted contracts independently
of the source tree; do not solve it during M1 without separate scope.

### Direct use of transitively installed `referencing`

This is not a Phase 06 blocker. The current locked environment contains the
package and existing validation already uses it directly. Phase 06 adds no
dependency and does not change schema resolution. Direct-dependency hygiene
must be revisited with the dependency/distribution strategy; do not alter the
lock merely for Phase 06 planning.

## First implementation action

After explicit authorization for M1, the first action is a contract-to-storage
mapping test in `tests/test_sqlite_data_plane.py` that creates a temporary
SQLite database, publishes one successful Build bundle containing an exact
Build Record, Build Input Manifest, Artifact Manifest, and Artifact bytes in
one transaction, closes the adapter, reopens it, and proves exact verified
bytes plus idempotent/conflicting-write behavior. Implement only the
`publish_build / load_build` port pair and minimum SQLite adapter code required
to make that test pass.
