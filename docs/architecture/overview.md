# Architecture Overview

## Architectural style

EA Research Lab is an API-first, adapter-oriented platform with strict separation between orchestration, external execution, evidence persistence, analytical computation, semantic contracts, and presentation.

Request/dependency topology and the research data lifecycle are different architectural views. They must not be inferred from one combined linear diagram.

## Request and dependency topology

This view shows allowed application entry points and dependency direction. It does not describe the order in which research data is produced.

```text
 Web UI       CLI       CI/CD                 Codex / Agents
    |          |          |                         |
    +----------+----------+                    MCP Adapter
               |                                      |
               +------------------+-------------------+
                                  |
                                  v
                         +-------------------+
                         |   PLATFORM API    |
                         | Command | Query   |
                         +----+---------+----+
                              |         |
                              v         v
                    APPLICATION COMMAND  APPLICATION QUERY
                         SERVICES            SERVICES
                           |   |                 |  |
                           |   |                 |  +-- uses Semantic Layer
                           |   |                 |      contracts/projections
                           |   |                 |
                           |   +-------> ANALYSIS PLANE
                           v                   |
                    CONTROL PLANE              |
                      |       |                |
                      v       v                |
                BuildProvider ExecutionProvider
                      |       |                |
                      v       v                |
                 MetaEditor  MetaTrader 5      |
                                               |
        Control, Analysis, and application services access persisted state
        only through ---------------------> DATA PLANE PORTS
```

The Platform API is the single application boundary. Command and Query are capabilities of that API, not independent architectural APIs. The MCP Adapter is only an adapter over the Platform API and has no direct path to providers, storage, repositories, or analytical engines.

Application command and query services are responsibilities inside the application boundary, not new planes or independently exposed runtime APIs. Commands dispatch to the relevant use case; they do not require every command to traverse Control or Analysis. The Analysis Plane does not serve client requests directly.

The Semantic Layer defines shared vocabulary, models, projections, and contracts. Application/query services implement bounded retrieval under those contracts. The Semantic Layer does not perform retrieval or analytical computation.

## Research data lifecycle

This view shows how research evidence and analytical results are produced. It does not define client request routing or software dependency direction.

```text
SOURCE REVISION
      |
      v
BUILD RECORD ---------> IMMUTABLE ARTIFACT
                              |
TEST-DEFINITION REVISION -----+
ENVIRONMENT / CONFIGURATION --+
                              v
                             RUN
                              |
                              v
                    RAW EVIDENCE COLLECTION
                              |
                              v
                 SEALED RAW EVIDENCE MANIFEST
                              |
                 TRANSFORMATION VERSION
                              |
                              v
                            DATASET
                              |
       ANALYSIS DEFINITION / VERSION / PARAMETERS
                              |
                              v
                            RESULT
```

Every arrow represents a durable provenance relationship, not merely a processing step. A result must be traceable through the entire chain.

## Responsibility ownership

| Boundary | Owns | Does not own |
|---|---|---|
| Platform API / application boundary | Command and Query capabilities, application command/query services, application validation, bounded retrieval, cross-client authorization and audit context | Provider access, storage implementation, analytical formulas |
| Control Plane | Test definitions, build/run orchestration, lifecycle, status, scheduling, provenance coordination | Provider-specific automation, evidence persistence implementation, analytical computation |
| BuildProvider / ExecutionProvider adapters | Translation to external build and execution technologies, provider interaction, provider metadata capture | Platform lifecycle policy, shared semantic vocabulary, analytical interpretation |
| Data Plane | Persistence, immutable evidence, versioned datasets/outputs, storage integrity, schema and content integrity | Analytical/run trustworthiness, statistics, comparison logic, semantic presentation |
| Analysis Plane | Deterministic transformations, analytical/run integrity, metrics, timeseries, distributions, comparisons, robustness, simulations | Storage integrity, client retrieval, presentation |
| Semantic Layer | Vocabulary, semantic models, projections, and contracts shared by clients and application services | Data retrieval, orchestration, persistence, analytical computation |
| MCP Adapter | Agent protocol translation and propagation of caller/request context | Independent application capabilities, authorization policy, audit ownership, provider or storage access |
| Visual Analytics | Exploration and presentation through Platform API Query capabilities | Analytical business logic, storage access |

Build and artifact management are platform capabilities coordinated through the Control Plane and isolated from MetaEditor by BuildProvider. This assignment does not introduce a separate plane.

## Integrity boundaries

Storage/data integrity belongs to the Data Plane. It covers concerns such as content hashes, schema validity, completeness of declared objects, manifest consistency, and detection of missing or corrupted persisted data.

Analytical/run integrity belongs to the Analysis Plane. It determines whether available evidence is sufficient and trustworthy for a particular analysis, including history quality, telemetry gaps, runtime anomalies, and inconsistent analytical counts.

A storage-integrity success does not imply that a run is analytically valid.

## Canonical provenance

The canonical provenance chain is:

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

Implementations may store this as a graph rather than a literal linked list. The contract is that no link required to explain or reproduce a result may be lost. Identities must be stable, schema-versioned where serialized, and content-addressed where practical.

## Raw evidence lifecycle

Evidence may be appended while a run is actively collecting. Each persisted raw object or chunk is immutable once written. A run reaches a reproducible evidence boundary only when a manifest identifies and hashes the complete evidence set for that collection outcome.

Evidence collection may end as completed, failed, cancelled, or collection failed independently from the Run execution lifecycle. A completed Run may therefore have a collection-failed evidence outcome without acquiring another Run state. Every terminal evidence outcome may produce a sealed manifest. Late evidence never rewrites a sealed manifest or its objects; it creates a new manifest revision that references the prior revision and preserves both histories.

Corrections, enrichment, normalization, and alternative calculations produce new derived datasets or analytical results. They do not modify raw evidence.

## Reproducibility levels

The platform records a reproducibility assessment rather than promising deterministic replay that an execution provider cannot guarantee:

- **Exact**: all identified inputs and environment dependencies are available and the provider declares the relevant execution reproducible under those conditions.
- **Equivalent**: the SUT, declared configuration, data dependencies, and materially relevant environment are available, but bit-for-bit replay is not guaranteed.
- **Best effort**: some non-critical or provider-controlled dependencies cannot be recreated and the gaps are recorded.
- **Unavailable**: required inputs or environment dependencies are missing, invalid, or inaccessible.

The assessment and its reasons are provenance metadata. Exact reproducibility of analysis requires the same input dataset, analysis definition/version, parameters, and deterministic computation environment. This is distinct from reproducibility of external execution.

## Schema evolution

Every persisted or externally exchanged contract carries a schema identity and exact version. Under ADR-0008, breaking changes create a new minor version for pre-stable contracts and a new major version for stable contracts. Compatible changes create new exact versions under the corresponding maturity rules, and declared supported historical versions retain explicit readers or adapters.

Raw evidence is never rewritten to adopt a newer schema. Derived datasets and analytical results are regenerated as new versions. Readers must either interpret a declared supported version or fail explicitly; silent coercion is not permitted.

## Strategy-agnostic boundary

### The platform may know

- artifact and source identity;
- opaque, typed SUT inputs without interpreting their trading intent;
- execution configuration and runtime environment;
- run identity and lifecycle;
- provider-neutral execution facts;
- schema-versioned telemetry envelopes and opaque SUT-specific payloads;
- datasets, analysis definitions/versions, generic metrics, timeseries, distributions, comparisons, simulations, and provenance.

### The platform must not know

- strategy intent or market thesis;
- signal, entry, exit, or position-management meaning;
- indicator or market-structure assumptions;
- strategy-specific optimization objectives;
- semantics inferred from SUT-specific field names or payloads.

Provider-specific observations are translated at adapters into genuinely provider-neutral contracts when such a mapping exists. Otherwise they remain explicitly provider-namespaced evidence. SUT-specific telemetry remains opaque to the core and is interpreted only by external strategy-specific research code.

## External systems

MetaTrader 5 and MetaEditor are external technologies accessed only through ExecutionProvider and BuildProvider adapters.

Storage technologies are infrastructure concerns behind Data Plane ports and must not leak into semantic or application contracts.

MCP is an external adapter over the Platform API.
