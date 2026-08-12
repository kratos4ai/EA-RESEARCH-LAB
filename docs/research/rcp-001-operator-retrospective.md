# RCP-001 Operator Retrospective

- Status: Completed
- Iteration: Pre-Phase-08 Research Operator Readiness
- Source: the already persisted RCP-001 checkpoint
- Scope: inspection only; no Build, Run, transformation, or Analysis execution

## Inspection method

`tools/inspect_research_checkpoint.py` was run against an automatic disposable
copy of `data/rcp-001/lab.sqlite3`. The canonical database SHA-256 was identical
before and after inspection. After infrastructure composition, the operator
workflow used only `PlatformApi`:

```text
list_research_runs
-> get_research_run
-> list_run_datasets
-> get_dataset
-> list_dataset_analyses
-> get_analysis
-> get_canonical_chain
```

The Run, three Datasets, and single Analysis were discovered without prior
knowledge of their identities. `get_canonical_chain` requires a Build Record ID
that the current query surface cannot discover, so RCP-001's Build Record ID had
to be supplied explicitly.

Example:

```text
python tools/inspect_research_checkpoint.py data/rcp-001/lab.sqlite3 --build-record-id build_019ff630-0cd2-7191-b26d-37ee22e7a6f9
```

## Available to the operator

The current Platform API exposed:

- Run identity, lifecycle status, timestamps, Artifact identity, and Test
  Definition revision identity;
- evidence collection outcome and sealed manifest identity/digest/history;
- execution reproducibility level and reasons;
- Dataset identities, schemas, content digests, transformation identities and
  versions, and direct provenance references;
- Analysis identity, definition/version, result schema/digest, parameter schema,
  computation environment identity, and exact Dataset inputs;
- the bounded Execution Core Analysis result;
- canonical Build-to-Analysis provenance once the Build Record ID was supplied.

The bounded Analysis result exposed 19 of the 23 requested research metrics:

- net return, win rate, loss rate, expected payoff, and profit factor;
- average winner, average losing magnitude, and payoff ratio;
- realized PnL minimum, maximum, mean, median, and mean absolute deviation;
- longest positive streak, longest negative streak, and zero-result count;
- event-balance maximum drawdown amount and rate.

## Unavailable through the current Platform API

The operator could not obtain:

- total, winning, or losing trade counts, or net profit;
- symbol, timeframe, date range, initial deposit, modeling mode, or leverage;
- MetaTrader or MetaEditor version and provider build/execution evidence;
- Raw Evidence object descriptors, bytes, logs, or bounded event drill-down;
- `MA_CROSS`, `POSITION_OPEN`, `POSITION_CLOSE`, `POSITION_REVERSE`, or
  `TRADE_ERROR` observations;
- Dataset payloads;
- a discoverable Build Record ID for canonical-chain navigation.

These were not recovered through SQLite, Data Plane, ResearchQueryPort, or
hardcoded RCP-001 knowledge. Their absence is an observed Platform API result.

## Operator friction

- Query-only composition still requires a `PlatformCommands` instance; the tool
  supplies command callables that always reject execution.
- The Build Record ID must be supplied even though the Run, Datasets, and
  Analysis can be discovered.
- Four elementary execution-summary values are absent while more advanced
  derived metrics are available inline.
- Environment configuration is represented only by identity, which prevents an
  operator from understanding the actual experiment configuration.
- Evidence presence and sealing are visible, but its research-relevant contents
  are not inspectable.

## Phase 08 input

### MUST

- Expose a bounded, provider-neutral research outcome projection containing the
  four missing execution-summary values alongside the existing Analysis Core
  metrics.
- Expose the bounded experiment configuration needed to interpret a Run:
  instrument, timeframe, date range, initial deposit, modeling mode, and
  leverage, without leaking provider mechanics into core vocabulary.
- Allow the canonical chain for a discovered Run/Analysis to be reached without
  an out-of-band Build Record ID.
- Preserve the existing identity, digest, lifecycle, reproducibility, Dataset,
  Analysis, and provenance information in the first Visual Analytics vertical
  slice.

### SHOULD

- Provide bounded evidence metadata and focused text/event drill-down sufficient
  to inspect failures and representative SUT-emitted observations without
  exposing an unrestricted evidence download.
- Expose provider/runtime version context relevant to interpreting and
  reproducing a Run, while keeping provider-specific evidence behind the
  adapter boundary.
- Provide a reusable read-only operator composition entry point so clients do
  not need disabled Command callables for query-only use.

### DEFER

- unrestricted Raw Evidence download;
- complete Dataset-content APIs;
- generic search, graph navigation, or ad hoc query languages;
- dashboards beyond the first evidence-backed research vertical;
- comparisons, optimization, ranking, and strategy-specific interpretation;
- MCP and other agent transports.

## Concerns outside Phase 08

| Candidate gap | Classification | Rationale |
|---|---|---|
| Easier checkpoint composition | Platform concern outside Phase 08 | Useful to operators and future clients, but not a visual semantic requirement. |
| Execution-summary metric exposure | Phase 08 concern | Four basic values are required to understand the existing result. |
| Bounded Raw Evidence drill-down | Phase 08 concern | Useful for research audit; SHOULD rather than required for the first metrics/provenance view. |
| Execution environment/version exposure | Phase 08 concern | Experiment configuration is MUST; provider versions are SHOULD. |
| Transitive include discovery | Build/reproducibility follow-up | It concerns Build Input completeness, not visual inspection. |
| Source snapshot byte retention | Build/reproducibility follow-up | It affects future reconstruction and retention policy, not the first visual slice. |

No Platform API capability, schema, dependency, persistence behavior, Analysis,
or provider integration was changed during this iteration. Phase 08 planning and
implementation have not started.
