# Dataset

A Dataset is a versioned collection of data produced from one or more runs.

Datasets may represent normalized, enriched, aggregated, or research-ready data.

Dataset identity must include:

- `dataset_id`
- input sealed evidence manifest(s) and/or dataset(s)
- transformation version
- transformation parameters where applicable
- creation timestamp
- exact dataset-content schema reference
- SHA-256 of the exact canonical dataset-content bytes
- provenance

Entity identity remains distinct from content identity. Dataset content uses
canonical UTF-8 JSON with sorted keys and compact separators; independently
allocated Dataset IDs and creation timestamps do not change those bytes.

`dataset-manifest/0.2.0` records the exact content digest together with the
input and transformation provenance. `dataset-manifest/0.1.0` remains an
unchanged supported historical contract but does not bind Dataset content.
Neither version defines storage layout or analytical formulas.

Phase 05 adds two pre-stable provider-neutral Dataset products derived directly
from sealed Raw Evidence:

- `realized-execution-event-series/0.1.0` contains ordered source execution
  events for which evidence reports realized PnL. Source IDs are opaque, times
  are source-local without an offset, and each row is an event rather than a
  complete trade, position, or round trip. Commission and swap remain separate
  observed facts.
- `account-balance-event-series/0.1.0` contains balances observed after ordered
  source events, including the initial balance event. It is event-indexed, not
  an equity series or continuously sampled balance path.

Both products use explicit sequence values to disambiguate repeated local
timestamps and canonical decimal strings for financial values. Their current
MT5 adapter is intentionally limited to the empirically observed English
Strategy Tester report layout and provider version recorded in the Phase 05
evidence observation. Unsupported layouts and ambiguous facts fail closed.
