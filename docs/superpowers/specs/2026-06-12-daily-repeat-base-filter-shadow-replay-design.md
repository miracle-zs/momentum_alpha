# Daily Repeat Base Filter And Shadow Replay Design

## Objective

Reduce repeated intraday base-entry losses by allowing each symbol only one
valid base signal per UTC day, while retaining enough structured evidence to
replay every filtered base and its hypothetical add-ons offline.

This change has two connected parts:

1. a live trading guard that filters repeated base signals; and
2. a read-only offline replay command that reconstructs the filtered strategy
   path from recorded signals and Binance one-minute klines.

## Confirmed Trading Rule

The daily limit uses UTC calendar days.

For each symbol:

- The first signal that satisfies all existing base-entry conditions is
  allowed.
- Producing that valid base `EntryIntent` consumes the symbol's daily
  opportunity immediately.
- Order submission, acknowledgement, and fill success do not affect whether
  the opportunity has been consumed.
- Any later signal on the same UTC day that would otherwise produce a valid
  base entry is filtered.
- Existing add-on, stop update, stop-loss cooldown, leader selection, and
  position rules remain unchanged.
- The daily tracking state resets when the UTC date changes.

This is signal-based accounting, not fill-based accounting.

## Live State Model

### Runtime strategy state

Extend `StrategyState` with:

- `daily_base_signal_times: dict[str, datetime]`
- `daily_base_signal_counts: dict[str, int]`

The first map stores the first valid base signal timestamp for each symbol on
the current UTC day. The second map counts every valid base opportunity,
including the allowed first signal and all later filtered signals.

The maps belong to `current_day`. When `now.date()` differs from
`state.current_day`, the runtime normalizes the state before strategy
evaluation:

- set `current_day` to `now.date()`;
- clear both daily base-signal maps;
- preserve positions, recent stop-loss exits, and previous leader state.

### Persisted strategy state

Extend `StoredStrategyState` with JSON-compatible equivalents:

- `daily_base_signal_times: dict[str, str]`
- `daily_base_signal_counts: dict[str, int]`

Serialization must remain backward compatible. Existing state rows without
these keys deserialize to empty maps.

Both poll and user-stream atomic state updates must preserve these poll-owned
fields. A process restart during the day must therefore continue filtering a
symbol whose first base signal occurred before the restart.

## Strategy Decision Model

Add a `SkippedBaseEntry` decision object containing:

- `symbol`
- `stop_price`
- `reason`
- `base_signal_sequence`
- `first_base_signal_at`
- `shadow_opportunity_id`

Extend `MinuteCloseDecision` and `TickDecision` with
`skipped_base_entries`.

The strategy evaluates all existing base conditions first. The daily-repeat
rule applies only when the signal would otherwise create a valid base
`EntryIntent`. Therefore:

- a signal blocked by the entry window, cooldown, existing position, missing
  candle, or invalid stop does not consume the daily opportunity;
- the first fully valid signal creates the normal base entry and updates the
  daily maps;
- a later fully valid signal creates no order, increments the signal count,
  and returns a `SkippedBaseEntry` with reason `daily_repeat_base`.

The skipped-base decision must coexist with add-on and stop-update decisions
on the same clock tick. It must not be collapsed into the generic
`blocked_reason` or lost when other signal records exist.

## Stable Opportunity Identity

Every filtered base receives a deterministic `shadow_opportunity_id` derived
from:

- UTC signal timestamp;
- symbol;
- daily base signal sequence.

The identifier must be stable across telemetry retries and unique within the
runtime database. It links the skipped signal to offline replay output without
creating a new live database table.

## Structured Telemetry

Record every filtered signal in `signal_decisions` with:

- `decision_type = base_entry_skipped`
- `symbol`
- the normal decision and leader linkage fields
- a payload containing:
  - `leg_type = base`
  - `blocked_reason = daily_repeat_base`
  - `base_signal_sequence`
  - `first_base_signal_at`
  - `shadow_opportunity_id`
  - `latest_price`
  - `stop_price`
  - `stop_budget_usdt`
  - `daily_open_price`
  - `daily_change_pct`
  - `previous_hour_low`
  - `current_hour_low`
  - `leader_gap_pct`
  - `step_size`
  - `min_qty`
  - `tick_size`

The tick audit payload and position snapshot payload should also include the
list of skipped-base symbols for operational visibility.

No virtual position is stored in live strategy state. Live execution and risk
management remain unaware of shadow opportunities.

## Offline Replay Command

Add a command with this surface:

```bash
python3 -m momentum_alpha.main replay-skipped-base \
  --runtime-db-file ./var/runtime.db \
  --output-dir ./local_analytics/skipped_base_replay \
  --proxy http://127.0.0.1:7897
```

Supported arguments:

- `--runtime-db-file`, required
- `--output-dir`, default
  `./local_analytics/skipped_base_replay`
- `--start-time`, optional UTC ISO timestamp
- `--end-time`, optional UTC ISO timestamp
- `--symbols`, optional comma-separated symbol list
- `--proxy`, optional and defaulting to `http://127.0.0.1:7897`
- `--taker-fee-rate`, default `0.0005`
- `--refresh-klines`, optional

The command is read-only with respect to `runtime.db`. It may maintain a local
JSON kline cache under the output directory.

## Replay Inputs

### Runtime data

Load:

- `base_entry_skipped` rows as replay seeds;
- `signal_decisions.next_leader_symbol` as the minute-level historical top-1
  leader series;
- the signal payload's sizing filters, stop price, signal price, and risk
  budget.

If several signal rows exist in a minute, use their recorded
`next_leader_symbol`. Conflicting non-null leaders for the same minute produce
a warning and use the latest database row.

### Market data

Fetch Binance USD-M futures one-minute klines through the configured proxy.
Use completed one-minute candles only.

Fetch enough history to cover:

- the base signal minute;
- every subsequent hour boundary;
- the eventual stop exit or analysis cutoff.

Cached data must be reusable so repeated reviews do not redownload unchanged
days.

## Shadow Position Simulation

### Base entry

At the skipped signal:

- use recorded `latest_price` as the shadow base entry price;
- use recorded `stop_price` as the initial stop;
- use recorded `stop_budget_usdt` and symbol filters with the production
  `size_from_stop_budget` function;
- charge entry taker fees.

If required replay inputs are absent or sizing returns no quantity, emit an
unresolved result with a precise warning.

### Add-ons and stop updates

At each later UTC hour boundary while the shadow position remains open:

1. calculate the completed previous hour's low;
2. update the entire shadow position stop to that low, matching the production
   hour-close behavior;
3. if the symbol is the recorded top-1 leader at that boundary, add one
   risk-sized add-on using:
   - the first completed minute close available at the boundary as entry
     price;
   - the completed previous hour's low as stop;
   - the recorded base signal's stop budget and symbol filters;
4. charge entry taker fees for every accepted add-on.

If the add-on stop is not below its entry price or sizing fails, record a
skipped shadow add-on with its reason.

### Stop execution

Replay candles chronologically.

- If a completed candle's low reaches or crosses the active stop, close the
  entire shadow position at the stop price.
- If an hour-boundary candle can both trigger the old stop and establish a new
  stop/add-on, process the candle against the previously active stop first.
  Only a surviving position receives the hour-boundary update.
- Charge exit taker fees.
- Do not invent slippage beyond the stop price.

This is a deterministic candle replay, not a claim about exact intraminute fill
ordering.

### Replay cutoff

By default, replay each seed until:

- its first simulated stop exit; or
- the last available leader and kline timestamp.

An unclosed shadow position is marked `open_at_cutoff`. Its realized net PnL is
left blank and its mark-to-market PnL at the cutoff is reported separately.

### Overlapping skipped signals

Only one shadow position per symbol may be open at a time.

If a later `base_entry_skipped` seed arrives while an earlier shadow position
for that symbol remains open:

- do not open another shadow position;
- classify the later seed as `overlap_existing_shadow`;
- link it to the active shadow opportunity.

After the shadow position exits, a later skipped seed may start a new replay
even on the same UTC day. This preserves a one-position-at-a-time
counterfactual while retaining every filtered signal in the detail output.

## Replay Outputs

Write the following files under the output directory.

### `skipped_base_replay_summary.csv`

One row per independent shadow opportunity:

- `shadow_opportunity_id`
- `symbol`
- `base_signal_at`
- `base_signal_sequence`
- `first_base_signal_at`
- `status`
- `base_entry_price`
- `initial_stop_price`
- `base_quantity`
- `add_on_count`
- `skipped_add_on_count`
- `exit_at`
- `exit_price`
- `duration_minutes`
- `gross_pnl`
- `entry_fees`
- `exit_fees`
- `net_pnl`
- `mark_price_at_cutoff`
- `mark_to_market_net_pnl`
- `warning_count`

### `skipped_base_replay_legs.csv`

One row per virtual base or add-on:

- opportunity identity
- leg type and sequence
- opened timestamp
- entry price
- stop at entry
- quantity
- risk budget
- entry fee
- closing timestamp and price when available
- gross and net contribution

### `skipped_base_replay_events.csv`

Chronological audit rows for:

- base seed accepted for replay;
- overlap suppression;
- stop updates;
- add-ons;
- skipped add-ons;
- stop exits;
- missing leader data;
- missing market data;
- open-at-cutoff outcomes.

### `summary.md`

Report:

- skipped base seed count;
- independent and overlapping opportunity counts;
- closed, open, and unresolved counts;
- total realized shadow net PnL;
- mark-to-market PnL for open positions;
- total base and add-on legs;
- win rate for closed shadows;
- largest winners and losers;
- PnL grouped by base signal sequence and UTC week;
- data-quality warnings.

## Error Handling

- Missing runtime DB: fail fast.
- No `base_entry_skipped` rows: write an empty summary and exit successfully.
- Binance request failure after retries: preserve cached results, mark affected
  opportunities unresolved, and return a non-zero exit status after writing
  available outputs.
- Missing leader minute at an hour boundary: do not create an add-on; record a
  warning and continue stop replay.
- Malformed signal payload: isolate the affected opportunity rather than
  aborting the full run.
- Duplicate `shadow_opportunity_id`: deduplicate identical seeds and warn on
  conflicting payloads.

## Testing

### Live filter tests

Cover:

- first valid base signal is allowed and consumes the daily opportunity;
- second valid signal for the same symbol is filtered;
- invalid or otherwise blocked signals do not consume the opportunity;
- different symbols each receive one daily opportunity;
- UTC day change clears the daily maps;
- state serialization is backward compatible;
- poll and user-stream state merges preserve the daily maps;
- restart restoration continues filtering;
- `base_entry_skipped` is recorded even when the same tick also records add-on
  or stop-update decisions;
- order submission failure still leaves the first signal consumed.

### Replay tests

Use deterministic synthetic signal rows and one-minute candles to cover:

- risk-sized base construction;
- hourly stop update;
- add-on only when the symbol is top-1;
- add-on sizing and fee calculation;
- stop exit before an hour-boundary update;
- multiple add-ons followed by one full-position stop;
- overlapping seed suppression;
- open-at-cutoff mark-to-market reporting;
- missing leader and market data warnings;
- CSV output and CLI dispatch.

## Acceptance Criteria

The change is complete when:

- live trading permits at most one valid base signal per symbol per UTC day;
- the consumed opportunity survives process restarts;
- repeated valid base signals create no broker orders;
- every repeated signal is persisted as `base_entry_skipped` with complete
  replay inputs;
- existing add-on behavior is unchanged;
- the offline command reconstructs virtual base, add-on, stop-update, and exit
  paths from the recorded seeds;
- replay artifacts make realized, open, overlapping, and unresolved cases
  explicit;
- targeted and full automated test suites pass.

## Limitations

- One-minute candles cannot determine exact intraminute ordering when both a
  stop and another price event occur in the same candle.
- Stop fills are modeled at the stop price without additional slippage.
- The replay depends on the completeness of historical leader records.
- Shadow results are counterfactual estimates and do not include portfolio
  margin interaction, funding, or market impact.
