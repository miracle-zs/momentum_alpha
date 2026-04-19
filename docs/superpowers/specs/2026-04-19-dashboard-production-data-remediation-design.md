# Dashboard Production Data Remediation Design

**Date**: 2026-04-19
**Status**: Proposed

## Summary

This document consolidates the live production dashboard review performed against:

- `http://43.153.134.252/momentum-alpha/`

The review compared the rendered data in each dashboard tab with the current codebase. The result is a confirmed list of production bugs, their user-facing impact, and the remediation direction needed to make the dashboard reliable for discretionary trading analysis.

The key conclusion is that the current dashboard has two different classes of issues:

- rendering and state bugs in the deployed frontend
- incomplete analytics ingestion and backfill in the runtime data pipeline

Both classes must be fixed. Frontend cleanup alone will not restore missing stop-slippage and leg analytics.

## Confirmed User Requirements

The remediation is constrained by the already-confirmed product requirements:

- All analytics stay inside the existing dashboard
- Complete-trade analytics must include all fully closed trades, not only recent `1D` data
- One complete trade means the full lifecycle from base entry through all add-on legs until the net position returns to zero
- Stop-slippage analytics must reflect real production stop behavior, not placeholders
- The dashboard must help a trader evaluate capital pressure, risk accumulation, and trade quality from live data

## Review Method

The production review was grounded in both the live rendered page and the API payloads behind it.

Checked surfaces:

- `Overview`
- `Execution`
- `Performance`
- `System`
- `/momentum-alpha/api/dashboard/tables`
- `/momentum-alpha/api/dashboard/timeseries`

The review also compared the live behavior with the current implementation in:

- `src/momentum_alpha/dashboard.py`
- `src/momentum_alpha/runtime_store.py`
- `src/momentum_alpha/user_stream.py`
- `src/momentum_alpha/main.py`
- `src/momentum_alpha/health.py`

## Confirmed Live Findings By Tab

### Overview

`Overview` is the healthiest tab in production.

Confirmed working signals:

- top account metrics render with live values
- open positions render with current symbol, side, size, entry, stop, and PnL-related fields
- capital pressure section shows live values
- active signal and home-command sections are populated

This strongly suggests that:

- the runtime database is being updated
- position snapshots are present
- account snapshots are present
- the dashboard server itself is running

### Execution

`Execution` is partially populated but analytically incomplete.

Confirmed live issues:

- `Latest Broker Action` is present
- `Latest Fill` is present
- `Latest Stop Exit` shows exit data but not trigger price
- `Latest Stop Order` renders as `n/a`
- `Avg Slippage` and `Max Slippage` render as `n/a`
- `STOP SLIPPAGE ANALYSIS` renders rows, but every `STOP` and `SLIP %` value is `n/a`

Confirmed backend evidence:

- `recent_stop_exit_summaries` exists, so stop exits are being reconstructed
- every stop-exit row has `trigger_price = null`
- every stop-exit row has `slippage_pct = null`
- `recent_algo_orders` is empty in production

This means the table is not merely rendering incorrectly. The production pipeline is failing to persist the stop-trigger metadata required to calculate slippage.

### Performance

`Performance` is currently the most misleading tab for strategy review.

Confirmed live issues:

- default `Performance` view can show `No closed trades`
- `?tab=performance&range=ALL` reveals many historical closed trades
- the top `Complete Trade Summary` still reports only a small recent sample even when the detail table shows many rows
- every visible trade row shows `Legs 0`
- `Peak Risk` is `n/a`
- expanded trade detail shows `No leg detail available`
- `By Total Leg Count` and `By Leg Index` are empty

This creates a false impression that either:

- there is no historical trade history
- the strategy has no leg-level information

Neither is true. Historical round trips do exist in production. The dashboard is loading them inconsistently, and historical leg analytics were not backfilled.

### System

`System` appears healthy, but its scope is too narrow.

Confirmed live behavior:

- `strategy_state`, `poll_log`, `user_stream_log`, and `runtime_db` all report `OK`
- recent runtime events are visible
- warning count is zero

Confirmed problem:

- the health model does not check analytics completeness
- it does not detect missing `algo_orders`
- it does not detect null stop-trigger coverage
- it does not detect stale or empty `trade_round_trips` analytics payloads

This is why the system tab can be green while the trader-facing analytical tabs remain broken.

## Confirmed Root Causes In Code

### 1. Subpath Deployment Is Not Handled Correctly

The dashboard is deployed under `/momentum-alpha/`, but the account-range fetch uses an absolute root path:

- `src/momentum_alpha/dashboard.py:3529`

Current behavior:

- `/api/dashboard/timeseries?...` returns `404` in production
- `/momentum-alpha/api/dashboard/timeseries?...` returns `200`

This breaks account-range reloads and any refresh path that depends on `loadAccountRange()`.

Related state issues in the same file:

- account range buttons are hardcoded with `1D` active in `src/momentum_alpha/dashboard.py:1511-1516`
- tab links drop current `range` in `src/momentum_alpha/dashboard.py:1835`
- refresh logic reloads range from `localStorage`, not the server-rendered state, in `src/momentum_alpha/dashboard.py:3619-3632`

### 2. Performance Summary And Detail Use Different Time Windows

The dashboard request handler correctly parses `?range=...`:

- `src/momentum_alpha/dashboard.py:3671-3684`

The snapshot loader also uses that range for round-trip reads:

- `src/momentum_alpha/dashboard.py:1156-1167`

But the trader summary is still hardcoded to `1D`:

- `src/momentum_alpha/dashboard.py:2046-2049`

This causes a single page to mix:

- `ALL`-range trade detail
- `1D` summary metrics

For trading review, this is a correctness bug, not just a UX issue.

### 3. Complete-Trade Analytics Are Bound To Account-Chart Range

The current `load_dashboard_snapshot()` uses `account_range_key` to load:

- account flows
- account snapshots
- trade round trips

Relevant code:

- `src/momentum_alpha/dashboard.py:1097-1167`

That coupling is wrong for the confirmed user requirement. Complete-trade analytics should not disappear because the account chart is currently on `1D`.

The correct product rule is:

- account metrics range controls account timeseries
- complete-trade analytics default to all fully closed round trips

### 4. Algo Order Ingestion Is Too Fragile

`ALGO_UPDATE` parsing currently expects top-level fields and refuses to persist anything if `algo_id` is missing:

- `src/momentum_alpha/user_stream.py:82-85`
- `src/momentum_alpha/user_stream.py:133-144`

Persistence path:

- `src/momentum_alpha/main.py:1172-1187`

The production evidence shows:

- `ALGO_UPDATE` activity exists in recent events
- `recent_algo_orders` remains empty

That means the current parser/extractor logic is rejecting real stop-algo events before insertion.

### 5. Stop Slippage Depends On Algo Metadata That Is Missing

Stop-trigger resolution depends on either:

- stop trigger lookup by client order id
- or previously persisted `algo_orders`

Relevant code:

- `src/momentum_alpha/runtime_store.py:418-436`
- `src/momentum_alpha/runtime_store.py:1595-1604`

Because production `algo_orders` is empty, the stop trigger cannot be resolved, so:

- `trigger_price` stays null
- `slippage_pct` stays null

This directly explains the broken `STOP SLIPPAGE ANALYSIS` tab.

### 6. Historical Trade Analytics Were Not Backfilled

The code already knows how to persist leg analytics into `trade_round_trips.payload_json`:

- `src/momentum_alpha/runtime_store.py:1536-1552`

But `rebuild_trade_analytics()` is only defined and tested:

- `src/momentum_alpha/runtime_store.py:1387`
- test-only callers in `tests/test_runtime_store.py`

There is no production command or startup path that rebuilds historical analytics after schema evolution.

That explains why production `range=ALL` detail rows exist but still show:

- `leg_count = 0`
- no leg detail
- no peak cumulative risk

### 7. Health Checks Only Measure Process Liveness

`build_runtime_health_report()` only checks:

- `strategy_state`
- `poll_log`
- `user_stream_log`
- `runtime_db`

Relevant code:

- `src/momentum_alpha/health.py:109-130`

It does not validate:

- latest `algo_orders` freshness
- stop-trigger coverage
- recent stop-slippage completeness
- historical trade analytics payload coverage

This is why the dashboard reports `OK` while trading analytics are still incomplete.

## Recommended Remediation Direction

### A. Make The Dashboard Subpath-Safe

Required changes:

- build dashboard API URLs relative to the current mounted path
- preserve current query state when switching tabs
- stop hardcoding the active account-range button
- stop letting refresh logic silently override server-rendered state with stale `localStorage`

### B. Separate Account Timeseries Scope From Complete-Trade Scope

Required product decision:

- account metrics keep their current range controls
- complete-trade analytics should load all fully closed trades by default

This prevents `Performance` from becoming empty just because the chart is on `1D`.

### C. Make `ALGO_UPDATE` Persistence Robust

Required changes:

- broaden the `ALGO_UPDATE` parser to tolerate the real production payload shape
- persist stop-algo rows even when only `client_algo_id` is available
- make missing `algo_id` diagnosable instead of silently dropping the row

### D. Treat Analytics Rebuild As A First-Class Operator Action

Required changes:

- add a supported CLI path to rebuild trade analytics for an existing runtime DB
- document when to run it after deployment
- use it to backfill historical leg analytics after shipping the fix

### E. Expand Health Checks To Cover Data Completeness

Required changes:

- add analytics freshness/completeness checks
- surface warnings when core analytical tables are empty or mostly null
- make the `System` tab useful for dashboard-quality diagnosis, not only service liveness

## Acceptance Criteria

The remediation is complete only when all of the following are true:

1. Account range switches work under `/momentum-alpha/` without `404`.
2. Tab switching preserves relevant dashboard query state.
3. `Performance` no longer reports `No closed trades` when historical round trips exist.
4. `Complete Trade Summary`, closed-trade detail, and leg aggregates are computed from the same trade population.
5. Newly generated stop exits contain non-null `trigger_price` and `slippage_pct` when the underlying stop data exists.
6. Historical round trips show real `leg_count`, `peak_cumulative_risk`, and leg detail after backfill.
7. `System` raises a warning when analytics ingestion or completeness degrades.

## Risks And Open Questions

### 1. Exact Production `ALGO_UPDATE` Shape Must Be Confirmed

The current review proves the ingestion path is broken, but a final parser fix should still be validated against one raw production `ALGO_UPDATE` payload from the user-stream logs.

### 2. Older Historical Trades May Remain Partially Null

If older fills were recorded before stop metadata existed, some historical trades may still lack:

- stop-at-entry
- per-leg risk
- stop-trigger-based slippage

That is acceptable as long as:

- the trade remains visible
- the dashboard renders missing values honestly as unavailable

### 3. Backfill Must Be Run Intentionally

Deploying code alone will not repair the already-persisted historical rows. The runtime DB needs a deliberate rebuild step after the fix lands.
