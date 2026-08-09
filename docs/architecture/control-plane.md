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

Initial lifecycle proposal:

```text
CREATED
  ↓
VALIDATING
  ↓
READY
  ↓
RUNNING
  ↓
COLLECTING
  ↓
COMPLETED
```

Failure states may include:

```text
INVALID
FAILED
CANCELLED
COLLECTION_FAILED
```

## Boundary

The Control Plane receives commands through the Platform API/application boundary and invokes external technologies only through BuildProvider and ExecutionProvider ports. It accesses persisted state only through Data Plane ports.

The Control Plane does not interpret trading logic, implement provider automation, own storage formats, or calculate analytical results.
