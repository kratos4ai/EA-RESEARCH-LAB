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

Phase 09 planning maps the currently implemented Platform API Queries to
capability-specific MCP tools:

- `list_research_runs`
- `get_research_run`
- `list_run_evidence_objects`
- `list_run_datasets`
- `get_dataset`
- `list_dataset_analyses`
- `get_analysis`
- `get_canonical_chain`

The command-capable mode maps only the existing four Platform API
Commands:

- `build_artifact`
- `execute_run`
- `transform_evidence`
- `analyze_datasets`

Commands require stronger authorization and validation at the Platform API/application boundary. MCP propagates caller and request context but does not own a separate authorization or audit policy.

The implemented adapter is a local stdio process under `apps/mcp_adapter`.
It uses the official `mcp==2.0.0` SDK and registers exactly the eight bounded
read-only Query tools listed above. Every Tool constructs a fresh request
context, validates its typed identifiers and page request, calls exactly one
matching `PlatformApi` Query, and explicitly serializes that one result.
Explicit command-capable mode adds the four Commands above; every Command Tool
creates one typed request and invokes exactly one matching `PlatformApi`
Command without Query enrichment, chaining, retry, or background work.

Tool names follow the exact lowercase snake-case Platform API capability name,
such as `list_research_runs` and `get_research_run`; vague transport verbs and
provider-specific names are excluded. Results use explicit allow-listed
translation: Decimal values remain exact strings, UTC timestamps and dates
retain canonical strings, typed IDs/digests/enums retain their stable values,
optional absence is `null`, and keyset cursors pass through unchanged. The
adapter does not reflect arbitrary objects or recursively fetch more data.

Every invocation creates a fresh UUIDv7 `RequestId` in an application-owned
`RequestContext` and uses the bounded caller label `mcp:local`. This label is
correlation context, not authentication. Safe application errors retain their
existing category; unexpected exceptions become a sanitized tool failure and
are logged without their cause.

The stdio protocol exclusively owns stdout. Operational logging uses the
existing stderr configuration. Read-only is the default launch mode and uses
`compose_read_only_platform`; `command-capable` is explicitly selected and
uses the existing operational workflows through `compose_command_platform`.
The latter requires explicit database, workspace, artifact, MetaEditor, and
MT5 configuration and performs no provider discovery.

The Phase 09 surface remains Tools only.
All capabilities are tools: the existing surface is parameterized, paginated,
and model-invoked, while adding Resources would duplicate lookup semantics.
Read-only mode is the default and does not advertise Commands; command-capable
mode requires explicit local composition. MCP adds no Resources, Prompts, sampling,
subscriptions, HTTP service, autonomous orchestration, or automatic retries.

List tools preserve the Platform API's page limits and opaque keyset cursors.
Evidence remains metadata-only. Dataset payloads and arbitrary Analysis result
content remain unavailable. The adapter never auto-fetches continuation pages.
Dataset detail may include only the existing execution-summary projection.
Analysis detail may include only the existing allow-listed
`execution-core-analysis-result/0.1.0`; unsupported results remain
metadata-only. Canonical provenance delegates to the existing integrity-checked
Platform API capability and is not reconstructed in MCP.

## Codex integration validation

Phase 09 M4 validated the local stdio adapter with Codex CLI
`0.147.0-alpha.6.5`. Ephemeral per-invocation configuration used the absolute
project virtual-environment Python executable and a disposable RCP-001 copy;
it did not modify global or repository Codex configuration.

Codex began without research identifiers and used the eight Query Tools to
discover the Run, experiment context, Datasets, bounded Analysis, Evidence
metadata, reproducibility, provider history, and verified canonical chain. It
also received a sanitized error for a malformed identifier. A separate
command-capable connection discovered twelve Tools and correctly identified
the four Commands and their side effects without invoking them. No provider
execution or research-state publication occurred.

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
bounded evidence metadata
```

## Response provenance

MCP responses should return analytical data together with provenance metadata.

Illustrative shape (identifiers remain opaque typed IDs):

```json
{
  "data": {
    "profit_factor": 1.53
  },
  "provenance": {
    "run_id": "run_<uuidv7>",
    "artifact_id": "artifact_<uuidv7>",
    "dataset_id": "dataset_<uuidv7>",
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
