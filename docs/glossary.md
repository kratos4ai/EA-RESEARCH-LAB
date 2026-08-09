# Glossary

## Artifact

An immutable compiled executable produced from a known source revision and build environment.

## Build Record

Immutable provenance for one build attempt, including source revision, build configuration, toolchain/environment identity, outcome, and produced Artifact when successful.

## Artifact ID

Stable identifier assigned to a compiled artifact.

## System Under Test (SUT)

The EA executable being evaluated. Its internal strategy is opaque to the platform.

## Test Definition

Declarative description of what should be executed: artifact, environment, symbol, period, tester configuration, and arbitrary EA input parameters.

## Test Definition Revision

Immutable revision of a Test Definition referenced by a Run. Later edits create a new revision.

## Run

One concrete execution of one Test Definition using one immutable Artifact.

## Run ID

Unique identifier for a concrete execution.

## Raw Evidence Object

An immutable object or chunk generated or collected during execution.

## Raw Evidence Manifest

Content-identified manifest that seals the complete raw evidence set for one collection outcome. Late evidence creates a new linked manifest revision.

## Derived Data

Deterministic transformations of Raw Data.

## Dataset

A versioned collection produced from sealed raw evidence manifests and/or prior datasets by an identified transformation version.

## Analysis

A versioned computation performed over one or more identified Datasets.

## Analysis Version

Identifier of the code/algorithm used to generate an analytical result.

## Metric

Named numerical or categorical analytical result.

## Timeseries

Timestamped ordered sequence of values associated with a run, dataset, or analysis.

## Distribution

Structured representation of observed values and their statistics/quantiles.

## Comparison

Versioned analytical result relating two or more runs, artifacts, configurations, or datasets.

## Provenance

Traceable relationship from source revision, build record, artifact, test-definition revision, environment/configuration, run, and sealed raw evidence manifest through transformation version, dataset, analysis definition/version/parameters, and result.

## Reproducibility Level

Recorded assessment of whether execution reproduction is Exact, Equivalent, Best effort, or Unavailable, including reasons and provider limitations.

## Control Plane

Coordinates tests, runs, artifacts, orchestration, status, and scheduling.

## Execution Plane

Runs the SUT using an external execution provider such as MetaTrader 5 Strategy Tester.

## Data Plane

Persists immutable evidence, derived datasets, metadata, and analytical outputs, and owns storage/data integrity.

## Analysis Plane

Performs deterministic transformation, analytical/run integrity assessment, statistics, robustness analysis, comparison, and reporting.

## Semantic Layer

Stable vocabulary, models, projections, and contracts used by the Platform API, UI, MCP, and analytical consumers. It does not retrieve or compute data.

## Visual Analytics Plane

Human-facing exploratory interface over the Query capability of the Platform API and its semantic contracts.

## MCP Adapter

Agent-facing adapter that exposes semantic platform capabilities through Model Context Protocol without bypassing the Platform API.
