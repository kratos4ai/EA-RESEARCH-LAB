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
