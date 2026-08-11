# Phase 05 M1 — MT5 Evidence Observation

- Status: Completed observation
- Recorded: `2026-08-11T01:37:44-03:00`
- Purpose: determine which detailed analytical facts the Lab can prove from
  Raw Evidence captured by its normal Build and Run workflows
- Scope: one controlled Demo Strategy Tester environment and one disposable
  test-only fixture; no general claim about other providers, account modes,
  report languages, or report versions

## Safety and environment

No related MetaEditor, terminal, or tester process existed before either
attempt, and none remained afterward. The existing adapters established process
ownership. The Run used main mode with the controlled Demo context, local tester
agents only, live trading disabled, DLL import disabled, optimization disabled,
and no SUT inputs.

| Component | Observed identity |
|---|---|
| Terminal | Ava Trade MT5 `5.0.0.6104`; SHA-256 `3b8dfb92f9e1bb3f5950189e4fedfe4deb454d3ae054643b8a1ffacc9ae37df8` |
| MetaEditor | `5.0.0.6104`; SHA-256 `50f47217c681e022924e905a2296144a7712dcf07f27bcfc108bf972aa20214c` |
| Terminal mode | `main` |
| Account context | controlled Demo environment |
| Data-root identity | `9B101088254A9C260A9790D5079A7B11`, linked to `C:\Program Files\Ava Trade MT5 Terminal` |
| Test interval | `EURUSD`, M1, every-tick model, `2026-08-03` through `2026-08-04` |

## Fixture and workflow

`tests/fixtures/mt5/phase05-known-activity.mq5` is research infrastructure,
not a trading strategy. It uses no indicator, signal model, market hypothesis,
or configurable SUT input. It performs this finite sequence:

1. open one minimum-volume buy exposure;
2. close it on the next tick;
3. open one minimum-volume sell exposure immediately;
4. close it on the next tick; then perform no further action.

The final fixture source SHA-256 was
`45a01f14fd7b9ddfbb842fbac2552172b3a291a1b59564e47dc2d6340eb2e8ea`.
It was compiled through the existing Build workflow; the accepted EX5 SHA-256
was `afa26906e78a2f1055b1f169be39376182582d45cce4331806bac3bf1230afc7`.
The existing Execution workflow completed normally and sealed its Raw Evidence
with outcome `completed`.

The first calibration attempt produced two negative outcomes. The final attempt
changed only the timing of the second opening and produced the intended bounded
sample: one realized loss (`-0.04`) and one realized gain (`0.42`). No realistic
strategy behavior was added.

## Raw Evidence inspected

Only the immutable bytes returned in the final Run result were inspected. No
original report or log path under the MT5 data root was used as analytical
input.

| Object | Media type / namespace | Bytes | SHA-256 |
|---|---|---:|---|
| `rawobj_019fef1c-0789-727c-b7e2-95b7d01fa042` | `text/html`; `metatrader5.strategy-tester.report` | 26,712 | `72cabf2f5b8feae30b9dd428de55753cf63dd034d8a64dfaeea34b39fb65899e` |
| `rawobj_019fef1c-078a-7331-9482-8af549467e62` | `text/plain`; `metatrader5.strategy-tester.tester-log` | 9,760 | `5bfcea6e7c8c612a1213c884ea426edfc5577fda6d46851cac56e7cc530e83b2` |
| `rawobj_019fef1c-078a-7331-9482-8af61c1b4821` | `text/plain`; `metatrader5.strategy-tester.terminal-log` | 4,142 | `46c20b1f4690e55bab060da02ef383331ac5d16607ab75960ee0e115e615d989` |

The report is UTF-16LE with a BOM. Logs were not used as analytical sources.

## Observed report structure

The captured HTML contains Settings, aggregate Results, Orders, and Deals
sections. The Orders section contains four rows with opening/completion local
times, opaque numeric identifiers, instrument, buy/sell type, requested/filled
volume, and state. Its price values were `0.00000`, so it did not establish
execution price.

The Deals section contains an initial balance row followed by four execution
event rows. Each execution row contains source-local time, opaque numeric record
identifier, instrument, buy/sell side, source `in`/`out` direction, volume,
price, related order identifier, commission, swap, reported profit, and balance
after the event. Two different event pairs share timestamps, so timestamp alone
does not establish total order.

The HTML references four external images:

- `tester-report.png`;
- `tester-report-hst.png`;
- `tester-report-mfemae.png`;
- `tester-report-holding.png`.

Those files were not part of captured Raw Evidence. The tabular facts used by
the approved Dataset contracts are present in the captured HTML itself; chart
content is not available to the Lab.

## Classification

### Confirmed

| Candidate fact | Direct observation and consequence |
|---|---|
| Record granularity | Separate order records, execution-event records, and one initial balance event exist. They must not be collapsed into a generic trade row. |
| Identifiers and relationships | Opaque order and execution-event identifiers exist; each observed execution event references one order identifier. No platform entity meaning is assigned to them. |
| Time and ordering | Local wall-clock values to seconds exist without offset. Source table order exists and must be represented by an explicit sequence because timestamps repeat. |
| Price and volume | Execution-event rows contain decimal price and volume. Order-row price did not establish execution price. |
| Side | Buy and sell execution sides are directly present. |
| Realized PnL | Source `out` events reported `-0.04` and `0.42`, confirming signed event-level realized PnL. |
| Commission and swap | Separate decimal columns exist and reported `0.00` for all observed events. They remain separate from realized PnL. |
| Balance | An initial balance and balance after every execution event are present in deterministic source order. |
| Aggregate results | Existing summary facts plus aggregate drawdown and holding-time values are present, but aggregates do not establish point series or record relationships. |

### Unsupported

- position identity or a position-record section;
- UTC, timezone offset, or a mapping from provider-local time to UTC;
- equity observations or a sampled equity series;
- continuously sampled balance observations;
- drawdown point data or the bytes behind report charts;
- per-event MAE/MFE, market-data series, requested price, slippage, or costs
  beyond the observed commission and swap columns;
- a provider-neutral holding duration derived from explicit paired lifecycle
  records;
- external image assets as Raw Evidence.

### Ambiguous

- whether source `in`/`out` direction has the same lifecycle meaning under
  netting, hedging, partial execution, reversal, or other account behavior;
- a universal open/close pairing: the fixture makes its two pairs known, but the
  report contains no position identifier and the observation covers one account
  context only;
- whether reported profit includes or excludes commission and swap; the three
  amounts therefore remain separate and are not combined;
- non-zero commission/swap representation and semantics, because only zero was
  observed;
- stability of source record identifiers across replay; they are retained only
  as opaque source identifiers;
- localization and layout outside this English build 6104 report.

## Dataset contract decision

### Approved: `realized-execution-event-series/0.1.0`

One row represents one source execution event for which captured evidence
reports realized PnL. It is deliberately not named or defined as a trade,
position, or completed lifecycle. Required fields are deterministic sequence,
opaque source record ID, source-local time without offset, instrument, side,
volume, execution price, realized PnL, commission, and swap. Currency and time
basis apply to the series. No open/close relationship or combined net amount is
asserted.

### Approved: `account-balance-event-series/0.1.0`

One observation represents the balance reported after one ordered source event,
including the initial balance event. Required fields are deterministic sequence,
opaque source record ID, source-local time without offset, and balance. Currency
and time basis apply to the series. This is event-indexed and is neither an
equity series nor a continuously sampled balance series.

Both products can be derived deterministically from the captured report bytes
and reuse `dataset-manifest/0.2.0`. Their financial fields are canonical decimal
strings; JSON numbers and floating-point values are rejected.

## Contracts deliberately not created

- no generic trade, order, deal, or position Dataset, because their cross-account
  lifecycle semantics were not established;
- no account-value or equity series, because no equity points were captured;
- no drawdown or return series, because aggregate values and uncaptured images
  do not establish ordered points;
- no holding-duration series, because universal event pairing is ambiguous;
- no combined net-execution amount, because the relationship between reported
  profit, commission, and swap was not established;
- no external-asset contract, because referenced images were not captured.

## Analytical consequences

The realized-event product supports deterministic realized-PnL distributions
and source-order sequence analysis without claiming trade semantics. The balance
product supports event-indexed balance-path analysis and balance drawdown under
an explicit future Analysis definition. Equity drawdown, equity path, general
holding duration, and periodic return analysis remain unavailable in Phase 05.

M1 does not implement either production transformation. Parsing and canonical
Dataset production remain M2 work.
