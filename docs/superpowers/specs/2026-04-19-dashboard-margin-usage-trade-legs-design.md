# Dashboard Margin Usage And Trade Leg Analytics Design

**Date**: 2026-04-19
**Status**: Approved

## Overview

Extend the existing Momentum Alpha dashboard so a discretionary trader can answer two practical questions with production data:

1. How much real margin is currently occupied over time?
2. For each complete trade lifecycle, from base entry through repeated add-ons until the position is fully closed, how many legs were used and how much did each leg contribute?

The dashboard already exposes account snapshots, open position detail, and round-trip trade summaries. This design keeps the current architecture and expands it in-place rather than creating a new analytics surface.

The resulting first-class dashboard capabilities are:

- A real margin usage percentage line chart built from account snapshots
- A complete-trade table that treats one base entry plus all subsequent add-ons as one trade until net position returns to zero
- Expandable leg-level detail for each closed trade
- Aggregations by total leg count and by leg index to support later stop-budget optimization

## Confirmed User Decisions

The design is locked to the following user-approved choices:

- Margin view uses real account occupancy, not theoretical capital demand
- Margin usage percentage is defined as `1 - available_balance / equity`
- Closed-trade analytics include all complete round trips, not only stop-loss exits
- All analytics must live inside the existing dashboard
- Closed-trade detail is the primary view, with aggregate analytics shown after it
- Leg-level detail must include per-leg risk and per-leg contribution, not only high-level trade totals

## Problem Statement

The current dashboard is good at answering "what is open now?" but weak at answering two deeper oversight questions:

### 1. Margin Occupancy Visibility

The dashboard shows current `available_balance` and `equity`, and it already calculates current `margin_usage_pct` in summary metrics. That is useful but incomplete.

The trader needs the time-series behavior of real occupancy:

- whether current occupancy is normal or stressed
- how high occupancy peaked over the selected window
- whether free balance is consistently sufficient for the strategy

Without the time series, the current point estimate is not enough for capital planning.

### 2. True Trade Lifecycle Analysis

The strategy does not behave like a single-entry, single-exit system. After the base position is opened, the strategy continues adding until the position is eventually stopped out or otherwise fully closed.

For trading analysis, that entire lifecycle is the real trade. The trader needs to know:

- how many legs the trade used
- what the final trade PnL was
- what each leg looked like at entry
- how risk accumulated across legs
- how much each leg contributed to the final result

The current `trade_round_trips` table already captures the correct trade boundary, but the dashboard only surfaces round-trip totals. It does not persist or render the leg-level analytics needed to optimize stop budget by leg number.

## Goals

The upgraded dashboard should let the trader answer these questions quickly:

1. What is the real margin usage percentage now and across the selected window?
2. What was the peak and average margin usage in that window?
3. For each closed trade, how many legs were used and what was the final net PnL?
4. How much risk was accumulated at the peak of that trade?
5. How did each leg differ in entry time, entry price, stop at entry, risk size, and final contribution?
6. Across many samples, how do results change by total leg count and by leg index?

## Non-Goals

This design intentionally does not include:

- A new standalone analytics application or a new dashboard route
- Automatic recommendation logic for leg-specific stop budgets
- Theoretical capital-demand modeling for alternate budgets such as `20u`
- CSV or JSON export in the first delivery
- Symbol filters, strategy filters, or advanced faceted analytics
- A new normalized leg table unless the current payload-based approach proves insufficient

## Existing System Constraints

The design should preserve and exploit the current system shape:

- Account history already exists in `account_snapshots`
- Current account range switching already exists in the dashboard
- Closed-trade reconstruction already exists through `rebuild_trade_analytics()`
- `trade_round_trips` already uses the correct lifecycle boundary:
  first `BUY` opens the trip, later `BUY`s join the same trip, and the trip closes only when cumulative `SELL`s bring net quantity back to zero
- Position snapshots already persist position legs while trades are open
- The dashboard remains server-rendered Python with lightweight browser-side chart updates

This means the safest path is to extend current data flows, not create a second analytics pipeline.

## Approaches Considered

### Approach A: Query-Time Reconstruction Only

Build margin and leg analytics only inside dashboard request handlers by joining existing tables each time.

Pros:

- No schema adjustments
- Minimal write-path changes

Cons:

- Harder to keep analytics stable across historical replay
- More expensive and more brittle dashboard reads
- Closed-trade leg detail would depend on ad hoc reconstruction instead of a persisted analysis artifact

This is not recommended.

### Approach B: Hybrid Extension Of Existing Analytics

Keep margin usage derived directly from `account_snapshots`. Keep complete-trade analytics based on `trade_round_trips`, but extend `rebuild_trade_analytics()` so each round trip persists its leg analytics inside `trade_round_trips.payload_json`.

Pros:

- Reuses the existing round-trip lifecycle logic
- Supports historical backfill through the existing rebuild path
- Keeps dashboard reads simple and stable
- Avoids a disruptive schema migration

Cons:

- Leg data lives inside payload JSON instead of a first-class table
- Aggregate analytics still need in-memory grouping in the dashboard layer

This is the recommended approach.

### Approach C: Introduce A New `trade_round_trip_legs` Table

Normalize each leg into its own row and query aggregates from SQL.

Pros:

- Best long-term analytical shape
- Cleanest downstream reporting model

Cons:

- More schema and migration work now
- Larger implementation surface than needed for the current dashboard goal

This is directionally attractive, but not justified for the first delivery.

## Recommended Direction

Use Approach B.

Specifically:

- Extend account timeseries payloads with `margin_usage_pct`
- Extend `rebuild_trade_analytics()` so each `trade_round_trip` persists leg analytics in `payload_json`
- Extend the `Performance` tab to show:
  - complete-trade table first
  - expandable leg-level detail per trade
  - aggregate blocks by leg count and by leg index
- Extend the `ACCOUNT METRICS` chart controls to render margin usage percentage over the current range

## Data Definitions

### Real Margin Usage Percentage

Definition:

`margin_usage_pct = (1 - available_balance / equity) * 100`

Rules:

- If `equity` is `null`, missing, or `0`, margin usage is `null`
- If `available_balance` is missing, margin usage is `null`
- The dashboard must render `null` as unavailable, never as `0`

This is a real account-occupancy metric, not a theoretical requirement model.

### Complete Trade

A complete trade is one symbol-specific round trip where:

- the first `BUY` fill opens the trip
- any later `BUY` fills before flat closure are add-on legs inside the same trip
- `SELL` fills reduce net quantity
- the trip closes only when net quantity returns to `0`

This definition already matches current round-trip reconstruction and should remain unchanged.

### Leg

A leg is one entry fill inside a complete trade.

Leg ordering is by entry fill timestamp ascending. The first leg is the base leg and later legs are add-ons.

Each persisted leg should contain:

- `leg_index`
- `leg_type`
- `opened_at`
- `quantity`
- `entry_price`
- `stop_price_at_entry`
- `leg_risk`
- `cumulative_risk_after_leg`
- `gross_pnl_contribution`
- `fee_share`
- `net_pnl_contribution`

### Peak Cumulative Risk

For one complete trade, cumulative risk is the running sum of leg risk after each leg is opened.

`peak_cumulative_risk` is the highest available cumulative risk observed across the trade's ordered legs.

If one or more legs are missing stop-at-entry data, cumulative risk remains `null` for those legs and peak risk is calculated only when enough leg risk data exists. The trade itself must still remain visible.

## Leg Analytics Calculation

### Stop At Entry

Preferred source:

- Match the entry leg to its corresponding strategy stop order using the strategy client-order-id convention

The current client-order-id format already embeds:

- timestamp
- symbol
- leg kind (`base` or `add_on`)
- sequence
- order kind (`entry` or `stop`)

This allows an entry fill and its original stop order to be associated during trade rebuild.

Fallback behavior:

- If no corresponding stop order can be resolved, `stop_price_at_entry` is `null`
- The trade remains valid and visible

### Leg Risk

For long positions:

`leg_risk = quantity * (entry_price - stop_price_at_entry)`

Rules:

- If `stop_price_at_entry` is unavailable, leg risk is `null`
- Do not invent a stop using later stop replacements
- This metric is intended to capture the risk commitment when the leg was opened

### Cumulative Risk

`cumulative_risk_after_leg` is the running sum of available `leg_risk` values in leg order.

If a leg lacks risk data, cumulative risk for that leg is `null` unless a partial-sum convention is explicitly added later. The first delivery should prefer correctness and explicit missingness over synthetic values.

### Per-Leg PnL Contribution

The exchange does not provide leg-specific final PnL directly. The dashboard therefore uses an analysis convention:

- compute a leg gross contribution using the trade-level exit price
- allocate total fees proportionally by leg quantity share
- derive net contribution as gross contribution minus fee share

For long positions:

`gross_pnl_contribution = quantity * (weighted_avg_exit_price - entry_price)`

`fee_share = total_trade_commission * (leg_quantity / total_entry_quantity)`

`net_pnl_contribution = gross_pnl_contribution - fee_share`

This convention is explicitly analytical and must be described as such in code comments and tests.

## Persisted Trade Payload

The first delivery should not alter the `trade_round_trips` table schema. Instead, extend `payload_json` with:

- `leg_count`
- `base_leg_risk`
- `add_on_leg_count`
- `peak_cumulative_risk`
- `entry_order_ids`
- `exit_order_ids`
- `entry_trade_ids`
- `exit_trade_ids`
- `legs`

Each element of `legs` contains the fields listed in the leg definition section.

This data must be produced both:

- during full rebuild via `rebuild_trade_analytics()`
- and for future trades reconstructed from the same rebuild path

## Dashboard Information Architecture

### 1. Account Metrics Panel

Keep the existing account panel and range switches.

Extend the metric switch list from:

- `Equity`
- `Adjusted Equity`
- `Wallet`
- `Unrealized PnL`

To:

- `Equity`
- `Adjusted Equity`
- `Wallet`
- `Unrealized PnL`
- `Margin Usage %`

Add summary values for the selected visible range:

- `Current Margin Usage`
- `Peak Margin Usage`
- `Average Margin Usage`

These values should live beside the existing account overview cards rather than in a separate panel.

### 2. Performance Tab

This tab becomes the home for complete-trade analytics.

The content order should be:

1. complete-trade summary strip
2. closed-trade detail table
3. leg-count aggregate block
4. leg-index aggregate block

### 3. Closed Trade Primary Table

The default closed-trade table should show:

- `Symbol`
- `Open`
- `Close`
- `Legs`
- `Peak Risk`
- `Exit`
- `Net PnL`
- `Duration`

Each row must be expandable inline.

### 4. Inline Leg Detail

Expanded leg detail should display:

- `Leg #`
- `Type`
- `Opened At`
- `Qty`
- `Entry`
- `Stop At Entry`
- `Leg Risk`
- `Cum Risk`
- `Gross PnL`
- `Fee Share`
- `Net Contribution`

This must be inline below the selected row, not in a separate route or modal.

### 5. Aggregate Blocks

Two initial aggregate blocks are required:

#### By Total Leg Count

For `1 leg`, `2 legs`, `3 legs`, and so on, show:

- sample count
- win rate
- average net PnL
- average peak cumulative risk

#### By Leg Index

For `leg 1`, `leg 2`, `leg 3`, and so on, show:

- sample count
- average leg risk
- average net contribution
- profitable-leg ratio

These aggregates directly support later optimization of non-uniform stop budgets by leg number.

## Query And Range Behavior

### Account Range

Account metrics continue using the existing dashboard range controls:

- `1H`
- `1D`
- `1W`
- `1M`
- `1Y`
- `ALL`

The margin-usage chart must use the exact same range and downsampling logic as the rest of the account timeseries.

### Trade Range

The `Performance` tab should query all complete trades within the selected dashboard range instead of only the newest fixed `20`.

This requires a range-aware trade fetch path for analytics views.

The first delivery does not need pagination. It does need correctness for the visible selected range.

## Fallback And Missing-Data Rules

The design must prefer usable analytics over fragile completeness.

Rules:

- Missing `stop_price_at_entry` must not remove the trade from the dashboard
- Missing leg risk must not remove the trade from the dashboard
- Missing margin inputs must show `n/a`, not `0`
- Exit reason remains whatever current round-trip analytics determine: `stop_loss` or `sell`
- Existing round-trip metrics such as `net_pnl`, `commission`, and `duration_seconds` must keep their current meaning

## Implementation Shape

The following code paths are expected to change:

- `src/momentum_alpha/runtime_store.py`
  - extend `rebuild_trade_analytics()`
  - add any helper fetch functions needed for range-aware trade reads
- `src/momentum_alpha/dashboard.py`
  - include `margin_usage_pct` in account timeseries payloads
  - extend account metrics controls and rendering
  - render closed-trade expansion detail
  - compute and render leg-count and leg-index aggregations
- `tests/test_runtime_store.py`
  - verify persisted leg analytics and fallback behavior
- `tests/test_dashboard.py`
  - verify margin usage timeseries, rendering, and new trade analytics sections

No changes are planned for strategy logic, execution sizing, or live order placement behavior.

## Testing Strategy

### Runtime Store Tests

Add coverage for:

- multiple entry fills reconstructed into one round trip
- persisted `leg_count`, `peak_cumulative_risk`, and `legs[]`
- both `stop_loss` and `sell` exits
- missing stop-order data resulting in `null` leg-risk fields without dropping the trade

### Dashboard Timeseries Tests

Add coverage for:

- margin usage derived from `available_balance` and `equity`
- `null` margin usage when `equity` is `0` or missing
- preservation of existing account metric behavior

### Dashboard Rendering Tests

Add coverage for:

- `Margin Usage %` metric toggle in account metrics
- summary cards for current, peak, and average margin usage
- closed-trade primary table with `Legs` and `Peak Risk`
- inline leg-detail rendering
- aggregate blocks by leg count and by leg index

### Regression Focus

Protect the following existing behavior:

- current round-trip lifecycle definition
- stop-loss exit detection
- account range switching
- existing `Performance` tab summaries that are not being redefined

## Rollout Notes

This delivery is intentionally an analytics foundation, not a parameter-optimization engine.

Once this data is visible and stable in production, the next design can answer higher-level optimization questions such as:

- whether `10u` should remain uniform across all legs
- whether later legs should use smaller or larger risk budgets
- whether specific leg counts produce disproportionate drawdowns or poor expectancy

That next step depends on this design producing trustworthy leg-level history first.
