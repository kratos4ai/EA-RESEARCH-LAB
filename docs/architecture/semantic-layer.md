# Semantic Layer

## Purpose

Define the stable vocabulary, models, projections, and contracts shared by analytics, the Platform API, UI, MCP, and agents.

The Semantic Layer does not retrieve data, orchestrate work, access storage, or perform analytical computation. Bounded retrieval is implemented by application/query services and exposed through the Query capability of the Platform API.

## Core semantic entities

- SourceRevision
- BuildRecord
- Artifact
- TestDefinitionRevision
- EnvironmentConfiguration
- Run
- RawEvidenceManifest
- Dataset
- AnalysisDefinition
- AnalysisResult
- Metric
- Timeseries
- Distribution
- Comparison
- Simulation
- Segment

These entities describe platform and research evidence without encoding the internal trading intent of a SUT.

## Example metric projection

```json
{
  "run_id": "RUN-001",
  "dataset_id": "DATASET-001",
  "analysis_definition": "execution-metrics",
  "analysis_version": "1.0.0",
  "metric": {
    "name": "profit_factor",
    "value": 1.51,
    "unit": "ratio"
  }
}
```

## Example timeseries projection

```json
{
  "run_id": "RUN-001",
  "dataset_id": "DATASET-002",
  "analysis_version": "1.0.0",
  "series": "equity",
  "timestamp": "2026-05-03T13:31:00Z",
  "value": 10831.71
}
```

## Contract philosophy

Semantic contracts express concepts rather than storage operations. Application/query services may expose operations such as:

```text
get run
get metrics
get timeseries
compare runs
get distribution
get timeline
```

They must not expose implementation operations such as:

```text
open parquet file X
read JSON line Y
query table implementation detail Z
```

## Provenance projections

Semantic result projections carry direct provenance references sufficient to locate the complete canonical chain:

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

Responses need not duplicate the entire graph, but no projection may make its result impossible to trace through it.

## Semantic neutrality

Provider-specific observations are either translated by an adapter into genuinely provider-neutral concepts or retained under an explicit provider namespace. SUT-specific payloads remain opaque and schema-identified. Neither becomes shared core vocabulary merely because it appears in telemetry or a provider report.

## Implemented Phase 07 boundary

The implemented Semantic Layer consists of immutable, provider-neutral summary,
detail, and canonical provenance projections. These values are derived on demand
and have no independent identity or persisted representation.

`ResearchQueryPort` performs only bounded identity discovery through three
operations: Runs, a Run's directly evidenced Datasets, and Analyses that consume
an exact Dataset identity/digest. Keyset pagination uses opaque cursors and
returns only `items` and `next_cursor`; it has no counts, offsets, arbitrary
filters, or caller-defined sorting. Every discovered identity is subsequently
loaded and integrity-validated through `DataPlane` before projection.

The in-process, typed `PlatformApi` is the single application boundary. Its
four explicit Commands publish finalized durable facts before returning normal
success. Its seven explicit Queries provide bounded discovery, detail, and
canonical-chain projections. Boundary audit events are operational logs with
request/caller correlation, safe identities, outcome, and safe error codes;
they are neither persisted semantic facts nor Raw Evidence.

Artifact and Raw Evidence bytes, provider logs, and complete Dataset payloads
are excluded. Inline Analysis content is currently allowed only for
`execution-core-analysis-result/0.1.0`, whose structure is explicitly bounded.
Other result contracts remain schema/digest references until separately
reviewed. Phase 07 introduces no network transport or serialized public schema.
Future Visual Analytics and MCP adapters must consume `PlatformApi`; they must
not access Data Plane, SQLite, providers, transformers, or Analysis internals.
