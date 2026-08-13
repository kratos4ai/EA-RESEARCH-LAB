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

## Implemented Phase 07 and Phase 08 read boundary

The implemented Semantic Layer consists of immutable, provider-neutral summary,
detail, and canonical provenance projections. These values are derived on demand
and have no independent identity or persisted representation.

`ResearchQueryPort` performs bounded read-side discovery through five
operations: Runs, a Run's directly evidenced Datasets, Analyses that consume an
exact Dataset identity/digest, the single cardinality-one relation from an
accepted Artifact to its Build Record, and one manifest-scoped bounded Evidence
metadata listing. The Artifact relation returns only a
`BuildRecordId`; the application loads the Build through `DataPlane`, verifies
the accepted Artifact, and fails closed on missing or ambiguous relationships.
Keyset pagination uses opaque cursors and returns only `items` and
`next_cursor`; it has no counts, offsets, arbitrary filters, or caller-defined
sorting. Every discovered identity is subsequently loaded and
integrity-validated through `DataPlane` before projection.

The in-process, typed `PlatformApi` is the single application boundary. Its
four explicit Commands publish finalized durable facts before returning normal
success. Phase 08 M3 extends its seven Phase 07 Queries with one capability-
specific Evidence metadata Query. The eight Queries provide bounded discovery, detail, and
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

Phase 08 M1 adds two non-persistent semantic read values without changing the
seven-query Platform surface. `DatasetDetail.execution_summary` exposes only
the explicitly reviewed `execution-summary/0.1.0` fields needed by clients; it
is not generic Dataset-content access. `ResearchRunDetail` includes the verified
Build Record identity and an optional provider-neutral experiment context.
Provider adapters may translate exact configuration contracts into that
context; unsupported configurations remain unavailable. The MT5 projection
currently supports instrument, timeframe, interval, requested initial capital,
currency, and leverage. Its numeric provider model has no approved neutral
meaning and is therefore not projected.

Phase 08 M3 adds a bounded `list_run_evidence_objects` Query over membership in
one known sealed manifest. `ResearchQueryPort` implements the durable bounded
read with a Run/manifest/query-bound keyset cursor and SQLite `LIMIT`; neither
`DataPlane.load_run` nor Raw Evidence bytes participate. It returns only object and manifest identities,
media type, byte length, digest, optional payload schema, and provider
namespace. The cursor is bound to the Run and manifest; Evidence bytes,
previews, search, parsing, and download remain absent. Dataset and Analysis
drill-down continue to expose metadata plus only the explicitly bounded
`execution-core-analysis-result/0.1.0` result.

Historical Build-provider runtime facts are projected by an exact adapter from
canonical MetaEditor Build evidence into a provider-neutral role, namespace,
version, and executable digest. Historical execution-runtime version is not
retained in canonical Run facts and therefore remains unavailable; clients
must not inspect the current workstation to fill that gap.

A small local composition root owns read-only SQLite adapter lifetimes and
returns `PlatformApi`. Its Commands deterministically report unavailability
before invoking workflows; read-only safety does not depend on presentation
controls.
