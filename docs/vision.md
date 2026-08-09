# Vision

## Purpose

Build a reproducible research environment for MetaTrader 5 Expert Advisors without assumptions about their internal trading logic.

The platform must make it possible to answer, with evidence:

- Which source produced this binary?
- Which binary produced this run?
- Which configuration produced this run?
- Which raw evidence was collected?
- Which analysis version produced this metric?
- Can the execution and the analysis be reproduced later?
- How does this run compare with other runs?

## Target capabilities

The long-term platform must support:

1. **Build**
2. **Version**
3. **Execute**
4. **Collect**
5. **Reproduce**
6. **Analyze**
7. **Compare**
8. **Query**
9. **Explore visually**
10. **Expose agent-oriented access through MCP**

## System Under Test

An EA is treated as an opaque System Under Test.

The platform may know its inputs, binary identity, runtime outputs, and telemetry contracts, but it must not require knowledge of what the EA is attempting to do.

## Out of domain

The platform core must not encode:

- trading strategies;
- market interpretation;
- signal generation rules;
- entry/exit semantics;
- position management semantics;
- optimization objectives tied to a specific strategy;
- assumptions about indicators or market structure.

These may exist inside an EA or in external research code, but not as core platform assumptions.
