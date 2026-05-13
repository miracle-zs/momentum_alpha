# Leader Opportunity Diagnostics Design

## Context

The project already has two data sources that matter for historical review:

- `var/runtime.db`, which contains runtime snapshots, signal decisions, trade fills, and trade round trips.
- `local_analytics/leader_candidates.db`, which stores the historical leader candidate stream reconstructed from runtime snapshots or Binance klines.

The current gap is a read-only replay tool that can answer, for each strong leader run, whether the strategy entered, how quickly it entered, what it captured, and why it missed when it did.

This design does not change trading behavior. It only adds an offline diagnostics command and a CSV artifact for review.

## Goal

Add a `diagnose-opportunities` CLI command that:

- reads the runtime DB and the sidecar leader candidate DB,
- groups rank-1 leader candidates into contiguous leader runs,
- joins those runs to runtime execution data,
- writes a CSV report under `local_analytics/`,
- prints a concise summary to the terminal.

The first version is focused on historical review of leader-driven opportunities, not on live trading or dashboard rendering.

## Non-Goals

This first version will not:

- modify any runtime trading tables,
- simulate alternate strategy rules,
- mark to market open positions,
- build a dashboard view,
- persist a new analytics database.

The report is deliberately coarse-grained. It works at the stored snapshot interval, not at tick level.

## Recommended Approach

### Option 1: CSV-only offline command

This is the recommended approach.

The command computes opportunity rows in memory, writes a CSV file, and prints a short terminal summary. It is easy to inspect in spreadsheets, easy to diff, and cheap to rerun.

### Option 2: SQLite diagnostics store

This would make repeated analysis queries easier, but it adds schema and read/write plumbing without much benefit for the first pass.

### Option 3: Dashboard integration

This is useful later, once the CSV analysis proves which questions matter most. It is too much surface area for the initial diagnostics pass.

## Data Model

### Opportunity definition

An opportunity is one contiguous run of rank-1 leader candidate snapshots for a single symbol.

Rules:

- sort `leader_candidate_snapshots` by timestamp,
- take only rank `1` rows,
- collapse consecutive rows with the same symbol into one run,
- treat the run end as the timestamp of the next leader change or the analysis window end.

This gives one row per leader run, which matches the actual question we want to answer: did the strategy catch the continuous push, and if not, why not?

### Runtime joins

For each leader run, the report may use:

- `trade_round_trips` to identify a closed trade that overlaps the run,
- `signal_decisions` to explain why the strategy did or did not enter,
- `position_snapshots` as a best-effort way to label a run as already-held or still-open when there is no closed round trip yet.

The first version does not attempt per-leg attribution. It treats the round trip as the execution unit when one exists.

## Output

### CSV file

Default output path:

```text
./local_analytics/opportunity_diagnostics.csv
```

The command should accept an explicit output path, but keep that default.

### CSV columns

The report should include at least these fields:

- `run_id`
- `symbol`
- `run_start`
- `run_end`
- `run_minutes`
- `snapshot_count`
- `start_daily_change_pct`
- `peak_daily_change_pct`
- `peak_timestamp`
- `leader_gap_pct_start`
- `trade_status`
- `signal_decision_id`
- `decision_type`
- `matched_round_trip_id`
- `entered_at`
- `exit_at`
- `entry_price`
- `exit_price`
- `realized_pnl`
- `net_pnl`
- `peak_return_pct`
- `realized_return_pct`
- `capture_rate`
- `miss_reason`
- `notes`

The important output is the opportunity row itself, not a giant dump of raw runtime tables.

### Summary lines

The command should print a short terminal summary with:

- total leader runs,
- captured run count,
- missed run count,
- open-at-cutoff count,
- median entry delay for captured runs,
- average capture rate for runs where it is calculable,
- total realized net PnL for matched runs,
- top miss reasons.

## Matching Rules

### Run grouping

Group rank-1 leader snapshots by contiguous symbol identity:

- if the next rank-1 row has the same symbol, it stays in the same run,
- if the symbol changes, the current run ends and a new one starts.

### Trade matching

Match runtime execution data to a run in this order:

1. Find a closed round trip for the same symbol whose open/close interval overlaps the run.
2. If no closed round trip exists, look for a position snapshot that indicates the symbol is still held near the run end.
3. If neither exists, classify the run as missed or unresolved.

The report should record the matching outcome in `trade_status`.

### Miss reason selection

When the run is not captured, derive `miss_reason` from the first matching signal decision if one exists.

Precedence:

1. `blocked_reason` from the signal decision payload.
2. `decision_type` when there is no explicit blocked reason.
3. `open_at_cutoff` when a position snapshot shows the symbol is still held but no closed round trip exists.
4. `no_matching_signal` when nothing else matches.

This keeps the report explainable without pretending it knows more than the data actually shows.

### Capture rate

When a closed round trip exists and both prices are available:

- `peak_return_pct = (peak_price - entry_price) / entry_price`
- `realized_return_pct = (exit_price - entry_price) / entry_price`
- `capture_rate = realized_return_pct / peak_return_pct`

If the run did not produce a valid denominator, leave `capture_rate` blank.

## CLI Surface

Add a new command:

```bash
python3 -m momentum_alpha.main diagnose-opportunities \
  --runtime-db-file ./var/runtime.db \
  --leader-candidates-db-file ./local_analytics/leader_candidates.db \
  --output-file ./local_analytics/opportunity_diagnostics.csv
```

Suggested arguments:

- `--runtime-db-file` required
- `--leader-candidates-db-file` default `./local_analytics/leader_candidates.db`
- `--output-file` default `./local_analytics/opportunity_diagnostics.csv`
- `--start-time` optional
- `--end-time` optional
- `--symbols` optional
- `--min-peak-change-pct` optional, default `0`

If `--start-time` or `--end-time` are omitted, the command should analyze the full available range in the leader candidate DB.

The command is read-only. It should not accept `--testnet`.

## Error Handling

- If the runtime DB is missing, fail fast with a clear error.
- If the leader candidate DB is missing or empty, print a short warning and exit with a non-zero status only if no rows can be produced.
- If a row contains malformed JSON or unusable numeric fields, skip the bad piece of data and keep the rest of the report.
- If a symbol has no matching runtime data, still emit the opportunity row with an unresolved status.

## Testing

The test coverage should prove:

- the command groups contiguous leader rows into one opportunity,
- the command matches a round trip and computes capture rate when the prices are usable,
- the command explains missed runs with a blocked reason when one is present,
- the CLI parser exposes `diagnose-opportunities`,
- the CLI dispatcher forwards the new command correctly,
- the command writes a CSV file to the requested output path.

Use temporary SQLite databases and synthetic rows for the tests. Keep them deterministic and small.

## Acceptance Criteria

The work is complete when:

- the new command can generate a CSV replay report from historical data,
- the terminal prints a compact summary that highlights captures and misses,
- the command reads only from the runtime DB and the leader candidate sidecar,
- the test suite covers the grouping, matching, and CLI wiring paths,
- no trading behavior or runtime schema is changed.

