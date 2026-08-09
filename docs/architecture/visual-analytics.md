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

## Technology

No frontend technology is mandated at this stage.

The architecture should permit a dedicated web application later without requiring analytical logic to be rewritten.
