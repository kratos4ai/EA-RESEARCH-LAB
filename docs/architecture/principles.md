# Architectural Principles

## P01 — Strategy agnostic

Every EA is an opaque System Under Test. Core components must not depend on strategy-specific concepts. SUT-specific inputs and telemetry may be stored under declared schemas, but their trading meaning remains opaque to the platform core.

## P02 — One API, two capability surfaces

The Platform API is the single application contract. Command and Query are capabilities of that API, not independent architectural APIs. UI, CLI, automation, and MCP consume the same application boundary.

## P03 — Immutable artifacts

Compiled artifacts are immutable and identified by version, source revision, build record, build metadata, and cryptographic hash.

## P04 — Explicit reproducibility levels

A run records sufficient provenance to classify reproduction as Exact, Equivalent, Best effort, or Unavailable. The platform must not promise deterministic replay when an execution provider cannot guarantee it, and must record the reasons for any limitation.

## P05 — Immutable raw evidence

Raw evidence may be collected incrementally, but every persisted raw object is immutable once written. A sealed, content-identified manifest defines the evidence set for a collection outcome. Late evidence creates a new manifest revision; corrections create new derived data or analysis versions.

## P06 — Deterministic analysis

Analytical calculations should be deterministic whenever practical and must identify their analysis definition, version, parameters, input datasets, and computation environment.

## P07 — Schema first and explicit evolution

Serialized contracts are versioned and machine-validated. Compatible additions are preferred; breaking changes require a new major version. Readers must support declared historical versions or fail explicitly, and immutable raw evidence is never rewritten to migrate schemas.

## P08 — Provenance everywhere

Every result must preserve the canonical chain from source revision, build record, artifact, test-definition revision, environment/configuration, run, and sealed raw evidence manifest through transformation version, dataset, analysis definition/version/parameters, and result.

## P09 — Adapter isolation and semantic neutrality

MetaTrader, MetaEditor, filesystem, databases, object storage, and MCP remain behind explicit boundaries. Provider-specific observations are translated into provider-neutral contracts when possible and otherwise remain provider-namespaced. They must not define core semantics.

## P10 — Analysis outside presentation

UI components visualize and query analytical results; they do not implement statistical or analytical business logic.

## P11 — Shared semantic contracts

The Semantic Layer defines the vocabulary, models, projections, and contracts shared by humans, APIs, visual analytics, and agents. It does not retrieve data or perform analytical computation.

## P12 — MCP as adapter

MCP exposes Platform API capabilities but does not access storage, repositories, analytical engines, MetaEditor, or MetaTrader directly. It propagates caller and request context; the Platform API/application boundary owns authorization and auditability.

## P13 — Progressive investigation

Application/query services should return summaries first and support bounded drill-down only when necessary.

## P14 — Bounded LLM context

Large raw telemetry, ticks, logs, and datasets must not enter LLM context by default.

## P15 — Comparison ownership

The Analysis Plane computes versioned run comparisons. The Semantic Layer defines their models and contracts, and application/query services retrieve them. Neither UI nor agents compute authoritative comparisons ad hoc.

## P16 — Time series are first-class data

Time-oriented analytical data must preserve timestamps, ordering, run identity, resolution, dataset identity, and analysis provenance.

## P17 — Architecture evolves through ADRs

Durable changes in architecture are documented explicitly before or together with implementation.

## P18 — Integrity responsibilities are distinct

The Data Plane owns storage/data integrity. The Analysis Plane owns analytical/run integrity. Successful storage validation does not imply analytical validity.

## P19 — Cross-client auditability

The Platform API/application boundary owns consistent request identity and audit context for all clients. Adapters propagate caller and request metadata but do not define independent audit policy.
