# Base Entry False-Breakout Filter Research Design

## Objective

Find a conservative base-entry filter that reduces losses from non-target moves
without materially damaging the strategy's long-tail winners or their add-on
sequence.

The filter is an opportunity veto, not a requirement that every accepted trade
must exhibit a perfect trend.

## Acceptance Criteria

Candidate rules must satisfy all of the following on the available live data:

- Preserve every closed trade with original net PnL of at least 100 USDT.
- Preserve at least 98% of aggregate original PnL from trades with net PnL of
  at least 50 USDT.
- Report the effect on original add-on count and add-on PnL.
- Use only information available before the base-entry decision.
- Improve total PnL after fees under the counterfactual replay.

Rules that pass these constraints are ranked by:

1. Total PnL improvement.
2. Recent-period improvement from 2026-05-29 UTC onward.
3. Weekly stability.
4. Number of avoided losing trades.
5. Simplicity and live implementation cost.

## Data

- Strategy decisions, fills, round trips, and leader history:
  `var/runtime.db`.
- Binance USD-M futures 1-minute and 15-minute klines:
  existing local caches, supplemented through the configured HTTP proxy when
  required.
- Analysis universe:
  the 692 closed round trips that match an original base-entry decision.
- The seven unmatched legacy or reconstructed round trips remain unchanged in
  portfolio totals.

All feature values use completed candles only. The signal minute's incomplete
candle is excluded.

## Feature Families

### Price Path Quality

- Returns over 5, 15, 30, and 60 completed minutes.
- Kaufman-style efficiency ratio over 15, 30, and 60 minutes:
  absolute net move divided by the sum of absolute one-minute moves.
- Fraction of positive one-minute returns.
- Maximum pullback from the rolling high.
- Current distance from the UTC-day high.
- Short-horizon return acceleration.

### Breakout Acceptance

- Previous completed candle close location within its high-low range.
- Upper-wick fraction.
- Close above or below recent rolling highs.
- Breakout amount relative to recent realized range.
- Pullback after the most recent rolling-high break.

### Market Participation

- Quote-volume ratio relative to the same symbol's recent baseline.
- Trade-count ratio relative to the recent baseline.
- Taker-buy quote-volume share.
- Taker-buy imbalance relative to total quote volume.
- Agreement between positive return and expanding participation.

### Volatility And Entry Cost

- Existing stop distance.
- Realized range and ATR-normalized short-term move.
- Short-term range expansion.
- Return relative to realized volatility.

EMA conditions and the current 1-hour candle direction are included only as
comparison baselines.

## Research Process

### Phase 1: Feature Audit

Compute every feature at each original base signal and compare distributions
for:

- losing trades;
- profitable but non-tail trades;
- trades with net PnL at least 50 USDT;
- trades with net PnL at least 100 USDT.

Discard features with excessive missingness, unstable definitions, or no
meaningful separation.

### Phase 2: Conservative Veto Search

Evaluate:

- individual weak-state conditions;
- pairs of weak-state conditions;
- three-condition vetoes drawn from different feature families.

A trade is filtered only when every condition in the veto is true. Thresholds
come from coarse, predeclared grids or empirical quantiles, not symbol-specific
manual tuning.

The preferred shape is:

`poor path quality AND failed breakout acceptance AND weak participation`

This structure is intended to reject broadly weak setups while allowing a
long-tail candidate to pass when any important trend dimension is strong.

### Phase 3: Counterfactual Replay

For each candidate:

- Original entries that pass remain unchanged.
- Filtered entries contribute zero PnL unless the existing strategy later
  creates an independent valid base opportunity.
- Add-ons attached to a filtered base are removed.
- Later independent entries for the same symbol are retained.
- Portfolio totals include the seven unmatched trades unchanged.

Probe-sizing variants may be reported separately, but they must not be mixed
with hard-filter results.

### Phase 4: Stability Checks

For every passing candidate, report:

- total and recent-period PnL deltas;
- weekly PnL deltas;
- accepted and filtered trade counts;
- filtered losers and filtered winners;
- long-tail trade count and PnL retention;
- add-on count and PnL retention;
- largest positive and negative per-trade effects.

Reject candidates whose improvement is dominated by one week or one avoided
loss, even if the aggregate acceptance criteria pass.

## Outputs

Write analysis artifacts under:

`var/analysis/base_filter_research_20260610/`

Required files:

- `feature_table.csv`
- `single_condition_results.csv`
- `combined_veto_results.csv`
- `passing_candidates.csv`
- `candidate_trade_detail.csv`
- `summary.md`

The final recommendation must include one preferred rule, one simpler fallback,
and an explicit statement when no hard filter is robust enough to deploy.

## Limitations

- The sample contains only eight trades with net PnL of at least 100 USDT, so
  long-tail preservation is a hard historical constraint rather than proof of
  future recall.
- The analysis cannot recreate fills for hypothetical signals that were never
  generated by the live strategy.
- Funding, additional slippage, and market impact beyond recorded fills are not
  newly estimated.
- Results are research evidence, not a guarantee of future performance.
