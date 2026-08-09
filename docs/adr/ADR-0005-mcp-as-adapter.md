# ADR-0005 — MCP as an adapter over the Platform API

- Status: Accepted

## Context

Codex and other agents should be able to investigate platform results fluently.

## Decision

MCP is an agent-facing adapter over the Platform API.

MCP must not directly access MetaTrader, storage engines, Parquet files, databases, or internal repositories.

MCP must not invoke analytical engines directly or expose application capabilities that bypass the Platform API. It maps agent-facing tools to Platform API Command or Query capabilities.

MCP propagates caller identity, request identity, tool context, and available protocol metadata. The Platform API/application boundary owns authorization, validation, audit policy, and the cross-client audit record.

## Consequences

Positive:

- protocol changes are isolated;
- Codex and UI share semantics;
- bounded context can be enforced;
- audit and authorization behavior remain consistent across clients.

Negative:

- an additional adapter layer is required;
- adapter context must be mapped into the application request/audit contract.
