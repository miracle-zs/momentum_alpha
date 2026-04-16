# Dashboard Live Price Data Design

**Date**: 2026-04-16
**Status**: Approved

## Overview

Extend the existing runtime snapshot pipeline so the trader dashboard can render live-price-dependent diagnostics without introducing a new database table or a separate market-data fetch path inside the dashboard.

The system already computes market snapshots during each trading tick. The missing piece is persistence: current prices and candidate-ranking context are not written into the structured dashboard payloads that the dashboard actually reads.

This design fixes that by extending the existing `position_snapshot` payload with market context and per-position live-price data.

## Problem

The dashboard currently reserves space for:
- Current Price
- MTM PnL
- PnL %
- Distance to Stop %
- R multiple
- Candidate ranking summary

But these fields still render as `n/a` because the dashboard does not persist the market snapshot data it needs.

Meanwhile, the runtime already has:
- `MarketSnapshot.latest_price`
- `daily_change_pct`
- `previous_hour_low`
- `current_hour_low`
- leader selection inputs
- leader-gap calculation logic

So this is not a market-data acquisition problem. It is a snapshot persistence problem.

## Goal

Persist enough runtime market context into the existing snapshot payloads so the dashboard can render:
- Current Price
- MTM PnL
- PnL %
- Distance to Stop %
- R multiple
- Notional Exposure
- a lightweight top-candidate ranking summary

without changing the dashboard server API shape or adding a new storage table.

## Non-Goals

This design does not include:
- a new `market_snapshots` table
- dashboard-side direct REST calls for prices
- historical market-chart panels
- a full candidate-ranking explorer
- advanced leader-strength analytics beyond the existing leader gap

## Recommended Approach

Use the existing `position_snapshots.payload` as the persistence point for live market context.

### Why this approach

- Lowest migration risk: no new schema
- Best timing consistency: dashboard sees the same market view used by the trading decision
- Minimal dashboard complexity: no additional fetch path or async price loading
- Reuses existing snapshot-reading logic already wired into `dashboard.py`

## Data Placement

### Position Snapshot Payload

Extend `position_snapshot.payload.positions[*]` so each persisted position can include:
- `latest_price`
- `daily_change_pct`
- `previous_hour_low`
- `current_hour_low`

These values should only be attached when market data for that symbol exists in the current runtime tick.

### Position Snapshot Market Context

Extend `position_snapshot.payload` with a new top-level `market_context` object:

- `leader_symbol`
- `leader_gap_pct`
- `candidates`

Where `candidates` is a small list containing the top-ranked market symbols for dashboard display.

Each candidate item should include:
- `symbol`
- `latest_price`
- `daily_change_pct`
- `previous_hour_low`
- `current_hour_low`

The first implementation should cap `candidates` to the top 5 ranked symbols.

## Data Source

The source of truth remains the runtime market snapshot already assembled during polling.

The implementation should reuse the runtime market data path that currently produces:
- `latest_price`
- `daily_open_price`
- `previous_hour_low`
- `current_hour_low`
- `daily_change_pct`
- `leader_gap_pct`

The existing helper that builds market context payloads should be reused or modestly expanded rather than replaced.

## Field Definitions

### Persisted Fields

For each position:
- `latest_price`: latest runtime tick price for the symbol
- `daily_change_pct`: `(latest_price - daily_open_price) / daily_open_price`
- `previous_hour_low`: previous closed hour low used by the strategy
- `current_hour_low`: current in-progress hour low when available

For dashboard market context:
- `leader_symbol`: current top-ranked symbol
- `leader_gap_pct`: difference in `daily_change_pct` between rank 1 and rank 2
- `candidates`: ranked top symbols for display

## Dashboard-Derived Metrics

The dashboard should compute these values from persisted snapshot data:

### Current Price

Display the persisted `latest_price`.

### MTM PnL

`(latest_price - avg_entry) * total_quantity`

### PnL %

`(latest_price - avg_entry) / avg_entry * 100`

### Distance to Stop %

`(latest_price - stop_price) / latest_price * 100`

### R multiple

`mtm_pnl / risk`

Only valid when `risk > 0`.

### Notional Exposure

`latest_price * total_quantity`

## Rendering Rules

The dashboard must continue to render explicit unavailable values when inputs are missing.

Display `n/a` when:
- `latest_price` is missing or invalid
- `avg_entry <= 0`
- `stop_price` is missing or non-positive
- `risk <= 0`

Metric-specific constraints:
- `PnL %` requires valid `avg_entry`
- `Distance to Stop %` requires valid `latest_price` and `stop_price`
- `R multiple` requires valid `risk` and `mtm_pnl`

The goal is still correctness over apparent completeness.

## Candidate Ranking Display

The first implementation should add a lightweight candidate summary to the signal section.

Display:
- top 5 candidate symbols
- each candidate’s `daily_change_pct`
- leader `leader_gap_pct`

This is not intended to be a full ranking page. It is just enough to show why the current leader is leading.

## Code Changes

Expected files:

- `src/momentum_alpha/main.py`
  - extend snapshot payload recording with market-context fields
- `src/momentum_alpha/dashboard.py`
  - read the new persisted fields
  - compute live-price-dependent position diagnostics
  - render candidate summary
- `tests/test_main.py`
  - verify snapshot payload persistence
- `tests/test_dashboard.py`
  - verify derived metrics and candidate rendering

## Backward Compatibility

The dashboard must remain compatible with older snapshot payloads that do not contain these fields.

If the new payload fields are absent:
- existing sections should still render
- live-price-derived metrics should still fall back to `n/a`
- candidate summary should degrade gracefully to empty or unavailable state

## Testing Strategy

Required tests:

1. Snapshot persistence test
   - verifies `position_snapshot.payload.positions[*].latest_price` and related fields are recorded
   - verifies `payload.market_context.candidates` and `leader_gap_pct` are recorded

2. Dashboard position-metric test
   - verifies Current Price, MTM PnL, PnL %, Distance to Stop %, R multiple, and Notional Exposure render when persisted fields exist

3. Candidate summary test
   - verifies candidate symbols and leader gap are rendered from snapshot payload

4. Backward-compatibility test
   - verifies old payloads still render with `n/a`

## Risks

### Payload bloat

Adding market context to snapshots increases payload size.

Mitigation:
- only store top 5 candidates
- only attach per-symbol market fields to persisted positions, not the entire market universe

### Data drift between decision and dashboard

If the dashboard fetched prices independently, it could disagree with the executed tick.

Mitigation:
- persist the tick’s market view directly into the snapshot used by the dashboard

### Partial data availability

Some symbols may have incomplete market context during edge cases.

Mitigation:
- preserve `n/a` rendering rules
- never fabricate values from missing inputs

## Success Criteria

The change is successful when:

1. Open position cards show real current-price-dependent metrics when runtime market data exists
2. Candidate ranking summary appears without adding a new table
3. The dashboard still works against old snapshot payloads
4. No new external fetch path is added to the dashboard
