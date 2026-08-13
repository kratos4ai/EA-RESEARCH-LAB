# Visual Analytics

## Principle

The visual layer explores analysis; it does not perform the analysis.

```text
Visual Analytics
  ↓
Platform API — Query capability
  ↓
Application / Query Services
  ↓
Semantic contracts and projections
```

This is a request path, not the research data lifecycle. Analytical results are computed by the Analysis Plane and persisted through Data Plane ports before they are queried.

## Target experience

Visual Analytics should evolve into a research workbench rather than a static KPI dashboard.

Target areas:

- run explorer;
- execution integrity;
- performance overview;
- equity/balance/drawdown timelines;
- distributions;
- run comparison;
- parameter matrices;
- stability/robustness;
- Monte Carlo;
- telemetry timeline;
- provenance drill-down.

## First-class drill-down

The architecture should support navigation like:

```text
Runs
  ↓
Run
  ↓
Metric / Period
  ↓
Timeline
  ↓
Events / Telemetry
  ↓
Raw evidence
```

## Requirements established from day one

- `run_id` on analytical data;
- consistent timestamps;
- sequence ordering for events;
- versioned analysis outputs;
- stable semantic names;
- Platform API Query capability and application/query services between UI and storage;
- comparison as a backend capability.

## Implemented local technology

Phase 08 M2 uses one local Streamlit `1.60.0` application under
`apps/visual_analytics/`. It is a client outside the four core packages and
binds only a local presentation server. It calls the in-process `PlatformApi`;
it does not introduce a public network Platform API.

The application entrypoint may import the explicit read-only composition root
to obtain `PlatformApi`. After composition, all research reads use that API.
The pure view model imports semantic values only and neither queries storage nor
computes research metrics. SQLite, Data Plane ports, bounded discovery ports,
providers, transformers, and Analysis operations remain inaccessible to the
visual client.

The implemented Research Overview is a single page with bounded Run discovery,
opaque cursor navigation, Run selection, experiment context, lifecycle,
evidence outcome, reproducibility, core metric cards, winning-versus-losing
counts, and realized PnL minimum/median/mean/maximum. The latter is labeled a
statistical summary, not a distribution. Event-balance drawdown is explicitly
described as based on observed balance events and never as equity drawdown.

Phase 08 M3 keeps the same selected-Run workspace and adds focused Dataset,
Analysis, Provenance, and Evidence tabs. Dataset views expose identity, exact
schema/digest, transformation metadata, and provenance references without
payloads. Exact known Dataset schemas receive approved researcher-facing
labels; unknown schemas remain a generic Dataset. Analysis views expose
identity, definition/version, inputs, result schema/digest, and only the
explicitly bounded `execution-core-analysis-result/0.1.0` metrics.

Canonical provenance is rendered only after the existing Platform API
reconstruction succeeds. Digests are shortened for scanning while complete
values remain available in expandable details. Reproducibility remains a level
plus recorded reasons, never a score. Evidence is Level 1 metadata only,
obtained through a bounded manifest-specific Platform Query; no bytes,
previews, downloads, or provider-log interpretation enter the client.

The Environment section distinguishes historical Build-provider facts from
generic experiment context. Canonically retained MetaEditor provider identity,
version, and executable digest may be shown. Execution runtime version remains
explicitly unavailable because it was not retained as a canonical Run fact.
The current installation is never used to describe a historical Run.

The client remains read-only. It exposes no Build, execution, transformation,
or Analysis command control. Session state contains only database identity,
selected Run/Dataset/Analysis identities, and bounded keyset cursors/history;
semantic objects and content are not authoritative session state.

## RCP-001 closure validation

Phase 08 M4 validates the real application against a disposable copy of the
persisted RCP-001 database. The automated path discovers the Run without prior
identities and proceeds through read-only composition and `PlatformApi` to the
Overview, three Dataset products, bounded execution-core Analysis, three
Evidence descriptors, reproducibility reasons, and verified canonical chain.
MetaEditor and MT5 provider methods are guarded and receive no calls. SHA-256
checks before and after prove both the canonical database and disposable copy
remain byte-identical.

The usability inspection found that a researcher can identify what was tested,
execution success, basic performance, Analysis inputs, and provenance without
knowing SQLite or Data Plane concepts. Semantic labels dominate the workspace;
opaque IDs and complete digests remain available for audit without dominating
the Overview. Event-Balance is consistently distinguished from equity, and
missing execution-runtime version is explicit. Evidence metadata is useful for
confirming captured report/log objects without exposing their content.
