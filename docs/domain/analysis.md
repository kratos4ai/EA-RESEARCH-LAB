# Analysis

An Analysis is a versioned computation over one or more datasets.

Minimum metadata for an Analysis Result:

- result identity
- analysis definition identity
- analysis version
- analysis parameters
- input dataset(s)
- execution timestamp
- computation environment identity
- exact result-content schema reference
- exact input Dataset content identities
- SHA-256 of the exact canonical result-content bytes
- provenance

The analysis definition/version identifies the computation, including its algorithm or code revision according to that definition's own versioning policy. Parameters and result content remain schema-referenced; the core result contract does not define formulas or metric catalogs.

Changing an analysis algorithm creates a new analysis version; it must not rewrite historical raw evidence.

The implemented execution-summary analysis computes only:

- `net_return = net_profit / initial_deposit`;
- `win_rate = winning_trades / total_trades`;
- `loss_rate = losing_trades / total_trades`.

It uses `Decimal`, an explicit computation context, round-half-even, and
canonical strings with twelve fractional digits. Zero denominators produce
bounded unavailable reasons rather than zero, NaN, or infinity.

Multi-Dataset analysis requires a baseline selected by exact Dataset content
digest. Deltas are candidate minus baseline. Rate comparison requires the same
Dataset content schema and transformation identity/version. Absolute monetary
comparison additionally requires the same currency; no FX conversion is
inferred. Comparability is structural only and does not assert scientific,
experimental, statistical, or strategy equivalence. The implementation does
not rank or recommend results.

`analysis-result/0.2.0` binds each input Dataset ID to its exact content digest
and binds the exact canonical result content through `result_digest`.
`analysis-result/0.1.0` remains unchanged and supported.
