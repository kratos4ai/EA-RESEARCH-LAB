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

The direct Execution Core analysis consumes exactly one Dataset of each of
these schemas:

- `execution-summary/0.1.0`;
- `realized-execution-event-series/0.1.0`;
- `account-balance-event-series/0.1.0`.

It adds these aggregate formulas without changing the existing definitions:

- `expected_payoff = net_profit / total_trades`;
- `profit_factor = gross_profit / abs(gross_loss)`;
- `average_winning_result = gross_profit / winning_trades`;
- `average_losing_magnitude = abs(gross_loss) / losing_trades`;
- `payoff_ratio = average_winning_result / average_losing_magnitude`;
- `gross_profit_return = gross_profit / initial_deposit`;
- `gross_loss_return = abs(gross_loss) / initial_deposit`.

Every zero denominator has a bounded unavailable reason. The realized
execution outcome distribution contains count, minimum, maximum, arithmetic
mean, median, and mean absolute deviation around the arithmetic mean:
`sum(abs(value - arithmetic_mean)) / count`. Sequence facts follow Dataset
source order; zero outcomes count separately and break both positive and
negative realized-event streaks.

Event-balance drawdown is calculated only over the observed balance sequence.
For each observation, the running peak is the greatest balance observed so
far, drawdown amount is `running_peak - balance`, and drawdown rate is that
amount divided by the non-zero running peak. The reported maximum amount and
rate are maxima over those observations. This is neither a continuous-path nor
an equity measure, and it has no duration semantics.

Execution Core fails closed unless all three Dataset documents, exact
canonical content digests, currencies, and sealed evidence-manifest provenance
agree. It does not infer composition relationships among provider facts. Its
pre-stable parameter and content schemas are
`execution-core-analysis-parameters/0.1.0` and
`execution-core-analysis-result/0.1.0`; the envelope remains
`analysis-result/0.2.0`.
