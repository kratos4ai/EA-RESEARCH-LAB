# Analysis Plane

## Purpose

Convert execution evidence into reproducible analytical outputs without requiring knowledge of the EA's internal strategy.

## Current implemented boundary

Phase 05 implements an in-memory deterministic vertical slice from sealed Raw
Evidence through three provider-neutral Datasets to direct Analysis results.
The products are `execution-summary`, `realized-execution-event-series`, and
`account-balance-event-series`. The direct Execution Core operation computes
the approved aggregate ratios, a bounded realized-event PnL distribution,
source-order event streaks, and maximum drawdown over observed event balances.
Dataset and result content use exact canonical byte identities. MT5 report
parsing remains an infrastructure adapter.

Current comparability is structural: exact Dataset schema and transformation
identity/version for rates, plus matching currency for absolute monetary
deltas. It performs no currency conversion and makes no scientific,
experimental, statistical-superiority, or strategy-equivalence claim. There is
no generic analysis engine, registry, ranking, optimizer, persistence, or query
surface.

The detailed rows are realized execution events, not reconstructed trades or
positions. Their timestamps are provider-local without an offset. Balance is
event-indexed and does not establish equity or a continuous path. Consequently,
holding duration, equity/continuous drawdown, periodic returns, and other
unsupported analytics remain outside the implemented boundary. Zero
denominators produce explicit bounded unavailability rather than synthetic
zero values.

## Analysis depth

The target design supports layered analysis.

### L0 — Analytical/run integrity

Determine whether a run is analytically trustworthy.

Examples:

- history quality;
- missing data;
- telemetry gaps;
- runtime errors;
- invalid metadata;
- inconsistent counts.

This assessment assumes that the Data Plane has already verified storage/data integrity. A structurally complete and hash-valid evidence set may still be analytically suspect or invalid.

Possible run analytical status:

- VALID
- SUSPECT
- INVALID

### L1 — Execution metrics

Derive provider-neutral metrics from execution-provider evidence. Provider-native field names and types remain in adapters or explicitly provider-namespaced raw evidence; they do not define shared analytical contracts.

Examples:

- total net profit;
- gross profit/loss;
- profit factor;
- expected payoff;
- recovery factor;
- Sharpe ratio;
- balance/equity drawdown;
- total trades/deals;
- long/short counts;
- win/loss statistics.

### L2 — Time-series reconstruction

Examples:

- balance(t);
- equity(t);
- drawdown(t);
- exposure(t);
- activity(t);
- PnL(t).

Derived analysis may include:

- underwater periods;
- recovery duration;
- rolling metrics;
- capital stagnation.

### L3 — Distribution analysis

Examples:

- PnL;
- holding duration;
- MAE;
- MFE;
- commission;
- slippage;
- returns;
- drawdowns.

Prefer full distribution descriptors over averages alone.

### L4 — Stability and robustness

Examples:

- monthly/weekly consistency;
- rolling Sharpe;
- rolling drawdown;
- rolling profit factor;
- profit concentration;
- dispersion;
- regime/time segmentation.

### L5 — Run comparison

Versioned comparison between runs/configurations/artifacts.

Outputs may include:

- absolute difference;
- relative difference;
- rank;
- percentile;
- stability;
- distance from baseline.

### L6 — Research analytics

Long-term capabilities may include:

- bootstrap;
- Monte Carlo;
- confidence intervals;
- correlation;
- regression;
- clustering;
- parameter sensitivity;
- distribution drift;
- segmentation.

## Principle

Python or another deterministic analysis engine performs the computation.

LLMs reason over bounded analytical outputs; they are not the primary computation engine.

The Analysis Plane owns transformations, analytical/run integrity, formulas, and versioned comparison logic. The Data Plane stores its inputs and outputs, the Semantic Layer defines their shared representations, and application/query services retrieve them.

Analyses may operate on generic execution facts and opaque typed inputs, but must not infer or encode SUT strategy intent, signal meaning, entry/exit rationale, or strategy-specific objectives in core analytical contracts.
