# Data Plane

## Purpose

Preserve immutable evidence, versioned datasets, and versioned analytical outputs while enforcing storage/data integrity.

The Data Plane persists analytical outputs computed elsewhere; it does not calculate them or determine whether a run is analytically trustworthy.

## Logical storage tiers

```text
RAW
  |
  v
DERIVED
  |
  v
ANALYSIS OUTPUTS
```

The arrows describe lineage between stored tiers, not computation ownership.

### Raw

Immutable evidence objects may include:

- telemetry;
- tester reports;
- logs;
- execution metadata;
- runtime artifacts;
- provider-namespaced evidence.

Raw objects may be appended during active collection, but each object is immutable once written. A sealed raw evidence manifest identifies and content-hashes the complete evidence set for a collection outcome. Failed, cancelled, and incomplete runs preserve the evidence they produced.

Late evidence creates a new manifest revision linked to the prior revision. No sealed manifest or raw object is overwritten.

### Derived

Versioned datasets computed by deterministic transformations may include:

- normalized events;
- normalized executions/deals;
- reconstructed timeseries;
- enriched datasets;
- aggregations.

Every dataset identifies its input evidence manifest, transformation identity/version, parameters where applicable, and schema version.

### Analysis outputs

Versioned outputs computed by the Analysis Plane may include:

- integrity assessments;
- metrics;
- distributions;
- comparisons;
- robustness results;
- simulation results;
- reports.

Persistence in this tier does not transfer formula or interpretation ownership to the Data Plane.

## Storage/data integrity

The Data Plane owns validation of:

- content hashes and object identity;
- declared schema identity and version;
- manifest consistency;
- completeness of the objects declared by a manifest;
- missing, duplicate, or corrupted persisted objects;
- lineage references between stored tiers.

Storage/data integrity does not determine history quality, telemetry sufficiency, runtime trustworthiness, or suitability for analysis. Those are analytical/run integrity concerns owned by the Analysis Plane.

## Run layout — conceptual

```text
runs/{RUN_ID}/
├── manifest.json
├── definition.json
├── artifact.json
├── environment.json
├── raw/
├── derived/
└── analysis/
```

This layout is illustrative and not a contract for physical storage. Filesystem, object storage, relational metadata, columnar formats, or combinations may be selected later behind Data Plane ports.

## Schema evolution

Persisted objects retain the schema identity and version under which they were created. Raw evidence is never migrated in place. Readers must support an explicitly declared historical version or fail visibly. Breaking changes produce a new major schema version; derived data and analysis outputs are regenerated as new versions rather than overwritten.

## Boundary

Physical storage types, paths, tables, and vendor APIs must not leak into semantic or Platform API contracts. Other planes access persisted state only through explicit Data Plane ports.

## Implemented Phase 06 boundary

Phase 06 M1 introduced durable Build publication and loading. M2 extends the
same storage-neutral `DataPlane` application port with capability-specific
publication/loading for finalized Runs and sealed Raw Evidence, Datasets, and
Analysis Results. No listing, search, traversal, or semantic query capability
is part of this boundary.

The initial infrastructure adapter uses one local SQLite database through the
Python standard library. It retains canonical contract documents separately
from content-addressed binary objects, validates exact local schema versions,
and verifies identities, hashes, lengths, and Build provenance on publication
and load. One Build publication is one transaction. Published records and
content are immutable; exact duplicate publication is idempotent and conflicts
fail closed. Downstream publication requires its upstream durable references:
Run requires its Artifact, Dataset requires its evidence or input Datasets,
and Analysis requires exact Dataset identities and content digests.

Raw Evidence bytes remain exact BLOBs and evidence revisions remain separate
immutable manifests linked only through their existing `prior_manifest`
references. Dataset and Analysis canonical JSON bytes are retained under their
declared SHA-256 identities; persistence neither reruns transformations nor
recomputes analysis semantics.

SQLite paths, tables, SQL, transactions, and exceptions remain private to the
adapter. The supported concurrency model is local SQLite writer serialization:
an overlapping writer may fail safely because M1 adds neither retries nor
distributed coordination. Source snapshot bytes are not retained; the Build
Input Manifest preserves historical content identity according to ADR-0010.

Fresh-state canonical reconstruction accepts explicit Build, Run, and Analysis
Result identities and follows only references already present in their durable
records. It cross-validates the Build/Artifact, Run/Test Definition/Evidence,
Dataset/Evidence, and Analysis/Dataset relationships through the `DataPlane`
port. This is an integrity operation for one known chain, not a listing,
search, reverse lookup, lineage projection, or semantic query capability.

Reconstruction verifies persisted identities, exact bytes, schemas, digests,
and provenance links. It does not rerun a build or execution, reproduce a
Dataset transformation, or recompute analytical results. Those computations
retain their existing plane ownership; Data Plane integrity only establishes
that the persisted outputs form the same explicit canonical chain.

Malformed documents, changed bytes, conflicting identities, broken references,
and cross-capability substitutions fail closed. The adapter does not repair,
migrate, relink, or choose replacement content.

The current adapter remains intentionally local: it has SQLite locking but no
retry/concurrency framework, migrations, repair, backup, retention, garbage
collection, distributed storage, or privileged-write authenticity mechanism.
It does not archive source snapshot bytes. Schema wheel packaging and the
direct use of transitively installed `referencing` remain deferred follow-ups.
