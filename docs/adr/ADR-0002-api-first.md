# ADR-0002 — API-first application boundary

- Status: Accepted

## Context

The platform will eventually serve UI, CLI, CI/CD, Codex, and other agents.

## Decision

Define one Platform API as the stable application contract.

All external clients consume platform capabilities through this boundary or an adapter built over it.

Command and Query are capability surfaces of the Platform API, not architecturally independent APIs. Commands invoke application and Control Plane use cases. Queries use application/query services for bounded retrieval under Semantic Layer contracts.

The Platform API/application boundary owns consistent request identity, authorization policy, validation, and audit context across clients. Protocol adapters propagate caller/request context but do not create independent application or audit policy.

## Consequences

- UI and MCP can evolve independently;
- storage and execution technologies remain replaceable;
- application semantics remain centralized;
- command and query behavior cannot diverge through client-specific paths;
- the application boundary requires explicit long-running command and bounded-query contracts as later phases introduce them.
