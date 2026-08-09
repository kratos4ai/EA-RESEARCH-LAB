# System Context

## Actors

### User

Defines work, reviews results, investigates evidence, and remains the final decision authority.

### Codex / Agent

Acts as an external client for software development and research exploration. It is not required for platform runtime.

### CI/CD

May build, test, package, or trigger approved platform operations.

## External systems

### MetaEditor

Compilation provider for MQL5 source code.

### MetaTrader 5 Strategy Tester

Execution provider for compiled Expert Advisors.

## Internal platform responsibilities

- build coordination;
- artifact registry;
- test/run orchestration;
- execution adapters;
- immutable data collection;
- analysis;
- semantic vocabulary, models, projections, and contracts;
- one Platform API with Command and Query capabilities;
- bounded retrieval through application/query services;
- cross-client request identity and audit context;
- visual analytics support;
- MCP agent interface.

## Context boundary

No external client is allowed to bypass the Platform API/application boundary to query or mutate platform state directly. MCP is an adapter over that same boundary and only propagates caller/request context for application-owned authorization and auditability.
