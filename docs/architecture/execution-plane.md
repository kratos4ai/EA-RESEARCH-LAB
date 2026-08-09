# Execution Plane

## Purpose

Execute an immutable System Under Test under a declared configuration.

## Provider abstraction

The platform must depend on an abstraction similar to:

```text
ExecutionProvider
  prepare(run)
  execute(run)
  wait(run)
  collect(run)
  cleanup(run)
```

Initial provider:

```text
MetaTrader5ExecutionProvider
```

## Build abstraction

Compilation must also be isolated:

```text
BuildProvider
  build(source_revision, configuration)
  collect_artifact()
```

Initial provider:

```text
MetaEditorBuildProvider
```

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

Execution may emit raw objects incrementally while a run is active. Once persisted, each raw object is immutable. The Data Plane owns storage validation and sealing the manifest that identifies a collection outcome; the Execution Plane does not rewrite sealed evidence.
