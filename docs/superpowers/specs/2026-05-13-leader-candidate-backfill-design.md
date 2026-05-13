# Leader Candidate Backfill Design

**Date**: 2026-05-13
**Status**: Proposed

## Summary

This design adds historical and forward-fill support for `leader_candidate_snapshots`, a runtime table that records ranked market leaders over time. The table exists to support opportunity diagnostics: when a symbol produces a large right-tail move, we need to know whether the strategy saw it, entered it, entered late, skipped it, or missed it because of data, timing, or execution constraints.

The key product rule is that the diagnostic grain is an opportunity, not a trade. `leader_candidate_snapshots` is the market-fact layer that later opportunity diagnostics will join against `signal_decisions`, `broker_orders`, `trade_fills`, and `trade_round_trips`.

## Goals

- Persist enough historical leader candidate data to evaluate whether large leader moves were captured.
- Support a fast replay path from existing `position_snapshots` for immediate partial coverage.
- Support a full-market historical rebuild path from Binance kline data for accurate missed-opportunity analysis.
- Keep the first version bounded by storing top N ranked candidates per timestamp, not every symbol at every timestamp.
- Make the backfill idempotent, resumable, and safe to rerun.

## Non-Goals

- This design does not create the final opportunity diagnostics table.
- This design does not change entry, add-on, or stop behavior.
- This design does not add a dashboard view yet.
- This design does not require storing all raw klines permanently.

## Existing Context

Current runtime storage already has useful but incomplete data:

- `position_snapshots` can store `payload_json.market_context.candidates`, but the current payload keeps only the top 5 candidates.
- `signal_decisions` stores strategy behavior such as `base_entry`, `add_on`, `add_on_skipped`, `stop_update`, and `no_action`.
- `trade_round_trips` stores closed trade analytics, including leg count, add-on count, risk, and leg payloads.
- `BinanceRestClient.fetch_klines()` already supports public kline requests with interval, start time, end time, and limit.

This is enough for a two-stage rollout:

1. Replay existing stored top candidates into the new table.
2. Rebuild full-market leader candidates from historical klines.

## Data Model

Add a new table to the runtime schema:

```sql
CREATE TABLE IF NOT EXISTS leader_candidate_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT NOT NULL,
    symbol TEXT NOT NULL,
    rank INTEGER NOT NULL,
    daily_open_price TEXT,
    latest_price TEXT,
    daily_change_pct TEXT,
    previous_hour_low TEXT,
    current_hour_low TEXT,
    leader_gap_pct TEXT,
    payload_json TEXT NOT NULL
);

CREATE UNIQUE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_unique
    ON leader_candidate_snapshots(timestamp, symbol);

CREATE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_rank_time
    ON leader_candidate_snapshots(rank, timestamp DESC);

CREATE INDEX IF NOT EXISTS idx_leader_candidate_snapshots_symbol_time
    ON leader_candidate_snapshots(symbol, timestamp DESC);
```

Store numeric fields as text to match the existing runtime pattern for decimal values.

## Replay Existing Position Snapshots

Add a backfill path that expands `position_snapshots.payload_json.market_context.candidates` into `leader_candidate_snapshots`.

Behavior:

- Read `position_snapshots` in ascending timestamp order.
- Parse `payload_json.market_context.candidates`.
- Preserve candidate order as rank, starting at 1.
- Insert one row per candidate.
- Use `source = "position-snapshot-replay"`.
- Skip malformed candidates but keep processing the rest of the snapshot.
- Use an idempotent insert strategy keyed by `(timestamp, symbol)`.

Limitations:

- This only replays the top candidates that the system already persisted.
- It cannot recover symbols that were outside the persisted top 5.
- It cannot recover periods where the poll worker was not running.

## Historical Kline Backfill

Add a full-market backfill path that reconstructs ranked leader candidates from Binance klines.

Command shape:

```bash
python3 -m momentum_alpha.main backfill-leader-candidates \
  --runtime-db-file ./var/runtime.db \
  --start-time 2026-04-01T00:00:00+00:00 \
  --end-time 2026-05-01T00:00:00+00:00 \
  --interval 5m \
  --top-n 50
```

Optional arguments:

- `--symbols`: restrict backfill to an explicit symbol list.
- `--testnet`: reuse existing environment behavior.
- `--replay-position-snapshots`: run the local replay path instead of Binance kline fetches.

### Kline Reconstruction Rules

For each UTC day and symbol:

- Fetch klines for the requested interval.
- Determine `daily_open_price` from the first available candle at or after UTC midnight.
- Use candle close as `latest_price` at that timestamp.
- Compute `daily_change_pct = (latest_price - daily_open_price) / daily_open_price`.
- Compute `previous_hour_low` from the most recent fully closed UTC hour.
- Compute `current_hour_low` from the current UTC hour up to the candidate timestamp.

At each timestamp:

- Rank all available symbols by `daily_change_pct` descending.
- Break ties by symbol ascending for deterministic output.
- Persist only the top N candidates.
- Set `leader_gap_pct` only for rank 1 when rank 2 exists.
- Use `source = "kline-backfill"`.

The first implementation can derive hourly lows from the same interval data. If `interval = 5m`, the lows are approximate at 5-minute resolution. A later precision pass can rerun important windows at `1m`.

## Symbol Selection

Default symbol set:

- Use current exchange info to resolve tradable USD-M perpetual symbols, matching the existing live scan behavior.

Known limitation:

- Current exchange info will not include delisted symbols. The backfill should log missing or unavailable symbols but should not fail the entire run.

## Idempotency And Resume

The backfill must be safe to rerun.

Rules:

- Use `(timestamp, symbol)` as the uniqueness key.
- Prefer `INSERT OR REPLACE` for deterministic rebuilds of the same source and timestamp.
- If replay data and kline data overlap, `kline-backfill` is allowed to replace `position-snapshot-replay` because it is reconstructed from the full symbol universe.
- Emit per-day and per-symbol progress logs.
- Continue after a symbol fetch failure, and include failures in a final audit event.
- Keep each UTC day as the natural processing unit to limit memory and make reruns easy.

## Live Poll Persistence

After the table exists, the live poll path should write fresh leader candidate rows on every audited poll tick.

Behavior:

- Reuse the ranked `market_payloads` built during live telemetry.
- Persist the top N candidates to `leader_candidate_snapshots`.
- Default live top N should be 50, matching backfill.
- Use `source = "poll"`.
- Keep `position_snapshots.payload_json.market_context.candidates` unchanged for dashboard compatibility.

This prevents a new data gap after historical backfill is complete. The existing dashboard payload can stay top 5 while the diagnostic table stores top 50.

## Runtime Integration

Add focused modules:

- `runtime_writes_history_candidates.py`
  - `insert_leader_candidate_snapshot()`
  - `insert_leader_candidate_snapshots_bulk()`
- `runtime_reads_history_candidates.py`
  - `fetch_leader_candidate_snapshots_for_window()`
  - `fetch_top_leader_candidates_for_window()`
- `cli_backfill_candidates.py`
  - replay from existing position snapshots
  - kline-based full-market reconstruction
- `telemetry.py`
  - live poll persistence for top N leader candidates

Expose the public functions through `runtime_store.py` compatibility exports, following the existing runtime split pattern.

Add CLI support in:

- `cli_parser.py`
- `cli_commands_ops.py` or a focused backfill command module, matching existing command dispatch patterns.

## Testing

Add tests for:

- schema bootstrap creates `leader_candidate_snapshots` and indexes
- replay expands `position_snapshots` candidates with correct rank
- replay is idempotent on rerun
- kline reconstruction computes daily open, latest price, daily change, previous-hour low, current-hour low, rank, and leader gap
- overlapping kline rows replace replay rows for the same timestamp and symbol
- live poll persistence writes top N candidates without changing the existing position snapshot payload shape
- `--top-n` limits persisted rows per timestamp
- malformed candidates or failed symbol fetches do not abort the whole run
- CLI dispatch calls the backfill function with parsed arguments

## Rollout

1. Add schema and persistence functions.
2. Add replay from existing `position_snapshots`.
3. Add kline reconstruction for explicit symbols and a short time window.
4. Add auto symbol resolution from exchange info.
5. Add live poll writes for top 50 candidates.
6. Run replay on the existing runtime database.
7. Run kline backfill first with `interval=5m` and `top-n=50`.
8. Use the resulting table to design the opportunity diagnostics table.

## Open Implementation Choice

Default interval should be `5m` for cost control. The CLI must allow `1m` so high-value windows can be rebuilt precisely.
