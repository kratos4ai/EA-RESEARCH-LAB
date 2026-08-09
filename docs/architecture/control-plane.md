# Control Plane

## Responsibilities

The Control Plane coordinates **what** should run and tracks **what happened**.

Core responsibilities:

- Test Definition registry;
- build coordination through BuildProvider;
- Artifact selection;
- Run creation and lifecycle;
- Run ID generation;
- orchestration;
- status tracking;
- execution scheduling;
- configuration validation;
- provenance coordination;
- reproducibility assessment coordination.

## Core entities

- BuildRecord
- Artifact
- TestDefinitionRevision
- EnvironmentConfiguration
- Run

## Run lifecycle

Run status describes execution lifecycle only:

The pre-stable Run contract exposes `CREATED`, `RUNNING`, `COMPLETED`, `FAILED`, and `CANCELLED`. Transition rules remain deferred until execution-provider behavior exercises the lifecycle.

Evidence collection, persistence, and analysis have independent lifecycles. In particular, `COLLECTION_FAILED` is an evidence collection outcome, not a Run state. Additional orchestration stages must not become Run states without evidence for a new version of the pre-stable Run contract.

## Boundary

The Control Plane receives commands through the Platform API/application boundary and invokes external technologies only through BuildProvider and ExecutionProvider ports. It accesses persisted state only through Data Plane ports.

The Control Plane does not interpret trading logic, implement provider automation, own storage formats, or calculate analytical results.
