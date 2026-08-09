# MCP Integration

## Decision

The platform is **API-first** and **MCP-ready**, but is not built on MCP.

```text
Codex / Agent
     ↓
MCP Adapter
     ↓
Platform API
     ↓
Application / Domain
```

The MCP Adapter must not directly access:

- MetaTrader;
- MetaEditor;
- filesystem storage;
- Postgres;
- Parquet;
- object storage.

It must also not bypass application/query services, invoke analytical engines directly, or define capabilities that do not exist in the Platform API.

## Initial MCP posture

Start read-only.

Candidate semantic tools:

- `search_runs`
- `get_run`
- `get_artifact`
- `get_analysis`
- `get_metrics`
- `get_timeseries`
- `get_distribution`
- `compare_runs`
- `get_timeline`

Later command tools may include:

- `create_run`
- `start_run`
- `cancel_run`
- `reanalyze_run`

Commands require stronger authorization and validation at the Platform API/application boundary. MCP propagates caller and request context but does not own a separate authorization or audit policy.

## Progressive investigation

Agent access should be optimized for bounded context:

```text
search
  ↓
summary
  ↓
comparison
  ↓
focused drill-down
  ↓
raw evidence only if required
```

## Response provenance

MCP responses should return analytical data together with provenance metadata.

Example:

```json
{
  "data": {
    "profit_factor": 1.53
  },
  "provenance": {
    "run_id": "RUN-231",
    "artifact_id": "ART-72",
    "dataset_id": "DATA-812",
    "analysis_version": "1.3.0"
  }
}
```

## Audit context

The Platform API/application boundary owns cross-client auditability. The MCP Adapter propagates available context such as:

- request ID;
- client;
- tool;
- arguments;
- timestamp;
- duration;
- user/agent identity where available;
- side effects for command tools.

The same application audit contract applies to UI, CLI, CI/CD, MCP, and future clients. MCP-specific protocol details may be added as context but do not create a separate audit record model.
