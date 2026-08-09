# Target State

The target state is intentionally broader than the first implementation phase.

Request/dependency topology and the research data lifecycle are separate views. Neither diagram implies that all capabilities must be implemented in an early phase.

## Target request and dependency topology

```text
 Visual Analytics   CLI   CI/CD                 Codex / Agents
        |             |      |                        |
        +-------------+------+                   MCP Adapter
                      |                                |
                      +---------------+----------------+
                                      |
                                      v
                             +------------------+
                             |   Platform API   |
                             | Command | Query  |
                             +----+--------+----+
                                  |        |
                                  v        v
                         Application command  Application query
                              services           services
                               |   |                |  |
                               |   +--> Analysis    |  +-- Semantic contracts
                               v          Plane     |
                         Control Plane      |        |
                           |       |        |        |
                           v       v        |        |
                     BuildProvider ExecutionProvider|
                           |       |        |        |
                      MetaEditor  MetaTrader 5       |
                                                    |
       Control, Analysis, and application services use Data Plane ports.
       MCP has no path around the Platform API.
```

## Target research data lifecycle

```text
Source revision
  -> Build record
  -> Immutable artifact
  -> Test-definition revision + Environment/configuration
  -> Run
  -> Raw evidence collection
  -> Sealed raw evidence manifest
  -> Transformation version
  -> Dataset
  -> Analysis definition/version/parameters
  -> Result
```

## Target capabilities

### Build & artifact management

- compile through BuildProvider;
- hash;
- version;
- record source and build provenance;
- store immutable artifacts.

### Control & orchestration

- test definitions;
- run lifecycle;
- batching;
- reproducibility assessment;
- scheduling;
- status tracking;
- provenance coordination.

### Execution

- Strategy Tester automation through ExecutionProvider;
- environment and provider metadata capture;
- telemetry collection without interpreting SUT intent;
- report/log collection;
- provider-specific evidence isolation.

### Data

- immutable raw objects and sealed evidence manifests;
- storage/data integrity;
- normalized derived data;
- versioned datasets;
- persistence of versioned analytical outputs;
- schema-version and content-identity preservation.

### Analysis

- analytical/run integrity;
- provider-neutral metrics derived from execution evidence;
- timeseries;
- distributions;
- stability;
- comparisons;
- robustness;
- simulations/research analytics that do not require strategy intent.

### Semantic Layer

- stable vocabulary;
- semantic models;
- projections;
- contracts;
- provenance representation;
- comparison and timeline representations.

### Platform API

- one application boundary with Command and Query capabilities;
- bounded retrieval through application/query services;
- cross-client validation, authorization, request identity, and audit context;
- no leakage of storage or provider implementation details.

### Visual Analytics

- run explorer;
- deep drill-down;
- synchronized timeline;
- distributions;
- robustness;
- comparisons;
- simulations.

### MCP

- adapter over the Platform API only;
- read-only semantic exploration first;
- command operations later;
- progressive drill-down;
- bounded LLM context;
- propagation of caller/request context to application-owned audit controls.
