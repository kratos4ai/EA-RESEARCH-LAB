# Execution Plane

## Purpose

Execute an immutable System Under Test under a declared configuration.

## Provider abstraction

The platform depends on one narrow application port:

```text
ExecutionProvider
  execute(ExecutionRequest) -> ExecutionProviderObservation
```

Initial provider:

```text
MetaTrader5ExecutionProvider
```

Preparation, process lifecycle, bounded output capture, and cleanup are adapter
implementation concerns within that single call. The provider reports observed
facts and captured bytes; the application owns Run admission, terminal status,
Raw Evidence identity, evidence sealing, and Run Manifest finalization.

## Build abstraction

Compilation must also be isolated:

```text
BuildProvider
  build(BuildRequest) -> BuildProviderObservation
```

Initial provider:

```text
MetaEditorBuildProvider
```

The provider reports bounded observed facts and provider-namespaced evidence. It does not determine the platform Build outcome, allocate an Artifact identity, or create a Build Record. Application orchestration declares success only after the candidate from the current exclusive workspace passes Artifact acceptance and exact-byte hashing.

The implemented MetaEditor adapter compiles only captured inputs materialized in an exclusive workspace. External inputs use stable logical root aliases; the provider-specific include view is derived from workspace-owned materialized bytes. Physical mappings, Windows invocation grammar, exit codes, UTF-16LE logs, diagnostics, and candidate paths remain adapter concerns.

This support is limited to the direct-compile behavior observed for MetaEditor `5.0.0.6104`. Dependency discovery is not claimed complete, and interactive/reused instances, output redirection, deterministic EX5 output, and larger/project-mode process trees remain unverified.

## Execution outputs

The execution provider may produce:

- tester reports;
- logs;
- telemetry;
- orders/deals;
- runtime metadata;
- environment metadata;
- failure diagnostics.

The execution provider does not define analytical or strategy meaning. It translates provider data into provider-neutral execution contracts when a valid neutral mapping exists. Provider-specific observations that cannot be mapped without losing meaning remain explicitly provider-namespaced raw evidence.

SUT-specific telemetry is captured under a declared schema and envelope but remains opaque to the platform core.

## Required metadata

A run should capture, when available:

- terminal version;
- compiler/build version;
- symbol specification;
- tester model;
- history quality;
- bars/ticks processed;
- deposit;
- currency;
- leverage;
- spread/commission/swap configuration;
- start/end timestamps;
- host/environment identity.

Unavailable or provider-controlled metadata must be recorded as an explicit reproducibility limitation rather than silently omitted. The Execution Plane captures provider facts; the platform does not claim deterministic replay beyond provider guarantees.

## Collection boundary

Execution may emit raw objects incrementally while a run is active. The
application boundary owns the terminal collection outcome and seals the
manifest after execution reaches a terminal state. Once persisted, each raw
object and sealed manifest is immutable; the Data Plane owns storage validation
and must not redefine or rewrite the sealed evidence set.
