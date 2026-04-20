# Dashboard Daily Review Design

**Date**: 2026-04-21
**Status**: Proposed

## Overview

Add a daily review section to the existing `复盘室` and pair it with a scheduled daily report job that runs at **08:30 Asia/Shanghai (UTC+8)**.

This feature is not a new top-level room. It is a time-bounded trading review surface inside `复盘室` that summarizes the previous 24 hours from **yesterday 08:30 to today 08:30** in local display time.

The daily review must answer two questions at the same time:

1. What did the strategy actually realize in the last 24 hours?
2. What would the result have been if the strategy had **not filtered out hourly add-on entries** for non-leader positions, and had instead replayed the unconditional hourly add-on rule?

The second question is a counterfactual replay, not a simple subtraction.

## Confirmed User Requirement

The user confirmed the following requirement:

- The current `复盘室` already covers all closed trades overall.
- The new feature should add a daily review block.
- The daily review window is `UTC+8 08:30` to the next `UTC+8 08:30`.
- The report should list:
  - how many trades occurred in the window
  - each trade's `symbol`
  - each trade's `opened_at`
  - each trade's realized PnL
  - the PnL under a strategy that does **not** filter out hourly add-ons
  - total realized PnL
  - total counterfactual PnL under the unconditional hourly add-on replay

The user also clarified that the counterfactual should **replay the skipped add-on positions** rather than simply dropping add-ons from the real trades.

## Problem Statement

The existing review room is useful for whole-sample closed-trade analysis, but it does not answer a daily operating question:

- What happened in the last trading day?
- How much of the result came from the real strategy?
- How much would have changed if every eligible hourly add-on had been taken, even when the symbol was not the leader?

The current data pipeline already records:

- closed trade round trips
- leg-level trade payloads
- skipped add-on decisions
- position and account snapshots with market context

That is enough to build the daily report, but only if the report is treated as a deterministic replay job with its own persisted output.

## Goals

The daily review feature should:

1. Show the number of closed trades in the last 24 hours using the `08:30 -> 08:30` local window.
2. Show one row per trade with `symbol`, `opened_at`, and realized PnL.
3. Show the counterfactual PnL for the same window after replaying skipped hourly add-ons.
4. Show the total realized PnL and total counterfactual PnL.
5. Keep the report visible inside `复盘室`, near the existing `Closed Trade Detail` surface.
6. Generate the report automatically every day at `08:30 Asia/Shanghai`.
7. Persist the report so the dashboard can render it quickly without recomputing the full replay on every page load.

## Non-Goals

This design does not include:

- a new top-level dashboard room
- a live intraday counterfactual simulator
- order recommendation logic
- a new strategy
- external exports such as CSV or Excel
- a rewrite of the existing `Closed Trade Detail` section

The daily report is a reporting and replay feature, not a trading engine change.

## Approaches Considered

### Approach A: Compute The Daily Report On Demand In The Dashboard

Pros:

- simplest data model
- no new scheduled job
- no persisted report table needed

Cons:

- the dashboard becomes more expensive to load
- replay cost moves into the user request path
- report results may vary if the underlying runtime data changes while the page is open

This is not recommended.

### Approach B: Materialize A Daily Report At 08:30 And Render The Latest Snapshot

Pros:

- matches the user's operational cadence
- keeps dashboard rendering fast
- produces a stable daily record
- allows the replay logic to be tested independently from the UI

Cons:

- requires a new report builder and persistence path
- requires one more scheduled job
- requires the replay input data to be complete enough for deterministic recomputation

This is the recommended approach.

### Approach C: Add A Separate Daily Review Page

Pros:

- isolates the daily report from the broader review room
- easier to evolve into a standalone analytics view later

Cons:

- adds a new navigation surface
- fragments the review experience
- is more structure than the user asked for right now

This is not recommended for the first implementation.

## Recommended Direction

Use **Approach B**.

The implementation should add:

1. a daily report builder that replays the previous day window
2. a persisted daily report record in `runtime.db`
3. a scheduled job that runs at `08:30 Asia/Shanghai`
4. a dashboard section inside `复盘室` that renders the latest daily report

The existing `Closed Trade Detail` section remains in place as the broader review surface. The new daily block is the time-bounded operational summary for the last 24 hours.

## Daily Review Window

The report window is defined in `Asia/Shanghai` time:

- `window_start = yesterday 08:30:00`
- `window_end = today 08:30:00`

The report should be labeled by the end date in local time. For example:

- a report generated at `2026-04-21 08:30:00 +08:00`
- covers `2026-04-20 08:30:00 +08:00` through `2026-04-21 08:30:00 +08:00`
- and is labeled as the `2026-04-21` daily review

Trade inclusion should be based on the round-trip close timestamp inside the window. If a trade opened before the window but closed inside it, it belongs in that day's report.

## Data Sources

The daily report should use the existing runtime database as its source of truth.

Required inputs:

- `trade_round_trips`
  - actual closed-trade result
  - actual `opened_at`, `closed_at`, `net_pnl`, and payload
- `signal_decisions`
  - especially `add_on_skipped`, `add_on`, `base_entry`, and `stop_update`
  - replay context for skipped add-ons
- `position_snapshots`
  - runtime market context and symbol-level payloads
- `account_snapshots`
  - window metadata and supporting operational context

The replay must not depend on live exchange data at report time.

## Counterfactual Replay Model

The counterfactual is:

- "What if the strategy had taken every hourly add-on that was filtered out because the symbol was not the current leader?"

This is not a simple subtraction of add-on legs from the actual trade.
It is a replay with the skipped add-on legs inserted as hypothetical fills.

The replay model should:

1. start with the actual base entry legs for the trade
2. insert any skipped hourly add-on legs that belong to the trade's lifetime
3. size each hypothetical add-on using the same sizing logic as the live strategy
4. keep the actual exit timing and actual exit fills for the day report
5. compute the counterfactual realized PnL from the replayed leg set

This keeps the report aligned with the existing strategy structure while answering the user's question about the unconditional hourly add-on rule.

### Replay Inputs That Must Be Available

To make the replay deterministic, the stored data for each skipped add-on must include enough sizing context to reconstruct the add-on quantity.

The report builder should have access to:

- the skipped add-on symbol
- the skipped add-on stop price
- the market snapshot for that tick
- the symbol filter values used for sizing at that tick

If the required sizing context is missing for a row, the report should mark the row as incomplete and surface a warning instead of silently inventing a quantity.

## Report Structure

The daily report should include two layers.

### Summary Layer

The top of the daily block should show:

- report date
- local window start and end
- trade count
- actual total PnL
- counterfactual total PnL
- delta between the two
- number of replayed skipped add-ons

### Trade Table Layer

One row per trade should show:

- `symbol`
- `opened_at`
- `closed_at`
- actual PnL
- counterfactual PnL
- PnL delta
- leg count
- replayed skipped add-on count

The table should be compact and scan-friendly. It should not expand into the full leg-level detail that belongs in `Closed Trade Detail`.

## UI Placement

The daily review block should live inside `复盘室`, above or adjacent to the broader `Closed Trade Detail` section.

Its purpose is to answer:

- "What did the last day look like?"

The existing `Closed Trade Detail` section continues to answer:

- "What happened across the whole review sample?"

The two sections should not compete for the same job.

## Persistence Model

Add a persisted daily report record in `runtime.db`.

Recommended shape:

- report date
- window start
- window end
- generated at
- status
- warning list
- actual summary totals
- counterfactual summary totals
- trade rows as JSON

The dashboard should render the latest successful daily report for the active window.
If no stored report exists yet, the dashboard may fall back to an on-demand build, but the scheduled path is the primary one.

## Scheduler And CLI

Add a dedicated CLI command for generating the daily report, for example:

- `daily-review-report`

The command should:

1. read `runtime.db`
2. determine the current `08:30 Asia/Shanghai` window
3. build the daily report
4. persist the result back into `runtime.db`
5. print a short summary for logs and operators

Add a matching shell script in `scripts/` following the pattern used by `audit_report.sh` and `run_rebuild_trade_analytics.sh`.

Add a systemd timer and service pair for the 08:30 schedule.

The schedule should be evaluated in `Asia/Shanghai` local time, not by a naive UTC midnight boundary.

## Error Handling

The report generator should fail loudly enough for operators to notice, but it should not prevent the dashboard from starting.

Expected failure cases:

- no runtime DB exists yet
- the report window has no closed trades
- replay inputs are incomplete for one or more trades
- a trade row cannot be reconstructed deterministically

In these cases, the report should:

- mark the row or report as warning/degraded
- preserve the usable actual trade results if possible
- surface a clear message in the report metadata

The dashboard should show the latest available report and indicate when the report is partial.

## Testing Strategy

Add tests for the following:

1. window calculation from `08:30 Asia/Shanghai`
2. inclusion rules for trades closed inside the window
3. actual total PnL aggregation
4. counterfactual replay aggregation with skipped add-ons
5. dashboard rendering of the daily summary block
6. scheduler command wiring for the daily report job
7. warning behavior when replay inputs are incomplete

The tests should use existing runtime-store fixtures and should not depend on live exchange access.

## Implementation Notes

The implementation should reuse existing building blocks where possible:

- `trade_round_trips` for actual results
- `signal_decisions` for `add_on_skipped` replay inputs
- `position_snapshots` and stored market payloads for replay context
- the same sizing logic used by live execution

The design should avoid introducing a second analytics pipeline just for the daily report.
The daily report is a specialization of the existing runtime data model.

## Success Criteria

The feature is complete when all of the following are true:

- `复盘室` shows a daily review block for the previous 24-hour local window
- the block lists every trade in that window
- the block shows actual and counterfactual PnL side by side
- the counterfactual includes the skipped hourly add-ons
- a scheduled job runs at `08:30 Asia/Shanghai`
- the generated report is persisted and can be rendered without recomputing everything on page load
- tests cover the window boundary and the replay totals

