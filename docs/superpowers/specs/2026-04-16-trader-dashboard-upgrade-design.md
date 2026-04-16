# Trader Dashboard Upgrade Design

**Date**: 2026-04-16
**Status**: Approved

## Overview

Upgrade the Momentum Alpha dashboard from a runtime monitoring page into a trader-first control panel.

The new dashboard should prioritize live decision-making and risk control:
- Surface account health and open risk before infrastructure details
- Show whether current positions are healthy, threatened, or over-sized
- Summarize execution quality and realized performance, not just raw events
- Preserve system health and audit visibility, but move them into lower-priority sections

The redesign must remain a single-page dashboard that auto-refreshes and works with the existing SQLite-backed runtime store. First delivery should rely on already persisted data wherever possible and avoid inventing values when required market context is unavailable.

## Problems With The Current Dashboard

The current dashboard is useful for proving the bot is running, but it is not sufficient for discretionary oversight of a live strategy.

Key gaps:
- Top-of-page metrics emphasize leader, position count, wallet balance, and unrealized PnL, but omit realized and net performance
- Position cards show entry, stop, quantity, and risk, but not enough context to judge position quality
- Execution data is shown as raw rows rather than as summarized execution-quality metrics
- Closed trade data is visible, but performance analytics are missing
- Signal context shows what the strategy did, but not enough about why it did it or whether rotation behavior is stable
- System health shares equal visual priority with trader-facing performance and risk information

## Goals

The upgraded dashboard should let a professional trader answer these questions in a few seconds:

1. Is the account making or losing money right now?
2. How much capital is free, how much is at risk, and how stressed is the portfolio?
3. Which open positions need attention first?
4. Is execution quality degrading through slippage or fees?
5. Is the strategy currently performing well over the selected lookback window?
6. Is leader rotation behaving normally, or is the strategy churning or getting blocked?

## Non-Goals

These are intentionally excluded from the first implementation:
- A new database schema unless the current schema proves insufficient
- A full multi-page analytics application
- Synthetic estimates for mark-to-market values when reliable market price data is not available
- Complex candidate-ranking analytics that require signal inputs not currently persisted

## Primary User View

The dashboard will be optimized for **live trading and risk oversight first**.

Secondary analytics and review content remain available, but are visually subordinate to live account, position, and execution information.

## Information Architecture

The page should be reorganized into six sections, in this order:

### 1. Top Summary Strip

This row becomes the trader’s immediate situational view.

Primary cards:
- `Today Net PnL`
- `Equity`
- `Available Balance`
- `Margin Usage`
- `Open Risk / Equity %`
- `Current Drawdown`

These cards must be visually prominent and use directional coloring for positive or negative states.

### 2. Position Diagnostics

This section should show open positions ordered by operational urgency, not just symbol order.

First implementation should sort positions by:
1. Highest absolute open risk
2. Then smallest remaining distance to stop when that data exists
3. Otherwise by symbol

Each card should expose:
- Symbol
- Direction
- Total quantity
- Average entry
- Stop price
- Open risk in USDT
- Open risk as percent of current equity
- Leg count
- Open timestamps or leg timestamps

The layout must reserve space for future metrics that depend on live price inputs:
- Current price
- Position MTM PnL
- Position PnL %
- Distance to stop %
- R multiple
- Notional exposure

When those values are unavailable, the card should show `n/a` with a small explanation rather than display a guessed number.

### 3. Execution Quality

This section should summarize how well the strategy is getting in and out, especially around stop exits.

Metrics:
- Average slippage %
- Maximum slippage %
- Stop exit count
- Fee total
- Recent fills

The visual emphasis should be on aggregate execution quality first, with raw fill rows shown beneath or beside the aggregates.

### 4. Strategy Performance

This section should turn recent round-trip data into compact trading analytics.

Metrics:
- Win rate
- Profit factor
- Average win
- Average loss
- Expectancy
- Average hold time
- Consecutive wins / losses
- Recent closed trade round trips

These metrics should use the selected dashboard time window.

### 5. Signal And Rotation Context

This section keeps the strategy explainable during live operation.

Content:
- Latest decision
- Blocked-reason breakdown
- Leader rotation frequency
- Leader timeline

Where enough recent decision data exists, blocked reasons should be grouped and summarized instead of shown only as a single latest value.

### 6. System Operations

This is still necessary, but it moves to the bottom of the page.

Content:
- Strategy config
- System health
- Recent events

This preserves operational debugging without forcing it into the main decision area.

## Time Window Behavior

All analytics and aggregate cards that depend on historical data should share a unified time-window control:
- `1H`
- `6H`
- `24H`
- `ALL`

The default visible window is `24H`.

Window-sensitive sections:
- Account and PnL cards
- Drawdown calculations
- Execution summaries
- Performance analytics
- Rotation frequency and blocked-reason breakdowns

Window-insensitive sections:
- Current open positions
- Latest decision
- Latest system health
- Recent events list

## Data Availability Tiers

To keep the first release honest, all metrics should be classified by data confidence.

### Tier A: Directly Available From Existing Data

These values already exist in runtime snapshots or stored trade rows:

- `wallet_balance`
- `available_balance`
- `equity`
- `unrealized_pnl`
- `position_count`
- `open_order_count`
- `realized_pnl`
- `commission`
- `net_pnl`
- `duration_seconds`
- `weighted_avg_entry_price`
- `weighted_avg_exit_price`
- `exit_reason`
- `slippage_abs`
- `slippage_pct`
- `leader_symbol`
- `blocked_reason`

These should be treated as implementation-ready.

### Tier B: Safely Derivable From Existing Data

These values are not persisted as standalone fields, but can be computed reliably from current tables:

- `Today Net PnL`
- `Range Net PnL`
- `Open Risk`
- `Open Risk / Equity %`
- `Margin Usage` using `1 - available_balance / equity`
- `Win Rate`
- `Profit Factor`
- `Average Win`
- `Average Loss`
- `Expectancy`
- `Consecutive Wins / Losses`
- `Average Hold Time`
- `Leader Rotation Frequency`
- `Blocked Reason Breakdown`
- `Fee Total`
- `Average Slippage %`
- `Maximum Slippage %`

These should be implemented in dashboard aggregation helpers rather than by altering the persistence schema in the first pass.

### Tier C: Requires New Market Or Signal Inputs

These values should have reserved UI space but display `n/a` until reliable data exists:

- Current price / mark price
- Position MTM PnL
- Position PnL %
- Distance to stop %
- R multiple
- Notional exposure
- Candidate ranking
- Leader advantage versus second-ranked symbol
- Signal-to-fill latency

The UI must explicitly indicate that these are waiting on live price or ranking inputs.

## Metric Definitions

To avoid ambiguity, the first release should use these definitions:

### Today Net PnL

Use the selected range’s change in adjusted equity when account history is available. Adjusted equity should remove known external transfers using the existing account flow normalization already present in the dashboard.

If adjusted equity history is unavailable for the selected window, fall back to summing `trade_round_trips.net_pnl` in that range.

### Margin Usage

Approximate as:

`1 - available_balance / equity`

If equity is zero or missing, display `n/a`.

### Open Risk

Sum the open-risk amount for all positions:

`total_quantity * (avg_entry - stop_price)`

This matches the current long-only system model and should be clearly labeled in USDT.

### Open Risk / Equity %

Compute:

`open_risk / equity * 100`

If equity is missing or zero, display `n/a`.

### Win Rate

Compute over closed round trips in the selected window:

`winning_round_trips / total_round_trips`

Where a winner is `net_pnl > 0`.

### Profit Factor

Compute:

`sum(positive net_pnl) / abs(sum(negative net_pnl))`

If there are no losing trades, display `n/a` or an explicit non-infinite placeholder that does not mislead.

### Expectancy

Compute as average `net_pnl` per closed round trip in the window.

### Consecutive Wins / Losses

Count the current streak by traversing recent round trips from most recent backwards until the sign changes.

### Leader Rotation Frequency

Count changes in the leader history within the selected range and present:
- total rotations
- average interval between rotations when enough points exist

## First Release Scope

The first implementation should deliver all of the following:

### Must Ship

- Reorganized page hierarchy with trader-first ordering
- Summary cards for account, risk, and drawdown
- Enhanced position diagnostics using current position snapshots
- Aggregate execution-quality cards
- Aggregate strategy-performance cards
- Blocked-reason breakdown
- Rotation-frequency summary
- Preserved system health, strategy config, and recent events in a lower-priority section
- Consistent `n/a` treatment for unsupported metrics

### May Be Deferred Within The Same Branch If Data Is Missing

- Current price
- Position MTM PnL
- Position PnL %
- Distance to stop %
- R multiple
- Notional exposure
- Candidate-ranking panel
- Leader-vs-runner-up strength comparison

These should not block the first delivery if the data model cannot support them honestly.

## UI Behavior Requirements

- Auto-refresh remains enabled
- Time-window selection updates all window-sensitive metrics consistently
- Positive and negative values use existing success and danger palette conventions
- Cards should remain legible on desktop and mobile
- Missing metrics must render as explicit unavailable values, not blank space
- Trader-facing sections should visually dominate the page more than system-health sections

## Implementation Approach

The first implementation should prefer local aggregation inside the dashboard module.

Expected code changes:
- Extend snapshot-to-summary aggregation in `src/momentum_alpha/dashboard.py`
- Add helper functions for performance, risk, execution, and signal-context summaries
- Rework the HTML structure and section ordering in `render_dashboard_html`
- Preserve existing JSON API split points unless the new metrics require extra payload keys
- Avoid modifying the runtime store schema unless tests prove the current data is insufficient

## Testing Strategy

The work should be test-first and should primarily extend `tests/test_dashboard.py`.

Required coverage:
- Aggregation helpers for account and risk metrics
- Performance-metric calculations from round-trip data
- Execution-quality calculations from stop-exit summaries and fills
- Blocked-reason grouping and leader-rotation metrics
- HTML rendering for the new top summary cards and major sections
- Explicit `n/a` rendering when live-price-dependent fields are unavailable

Tests should validate both data correctness and the presence of user-visible labels that define the redesigned dashboard structure.

## Risks And Tradeoffs

### Risk: Overstating Precision

Trader dashboards are dangerous when they imply values that are not actually backed by current data.

Mitigation:
- Separate implemented metrics from reserved placeholders
- Render unavailable values explicitly
- Avoid estimating mark-to-market metrics without live price data

### Risk: Too Much Density

Adding all requested metrics to one page can easily create noise.

Mitigation:
- Promote only the highest-value metrics into the summary strip
- Keep performance and execution analytics grouped
- Move operational details to the bottom of the page

### Risk: Mixed Time Semantics

Some values are current-state metrics and others are range-based metrics.

Mitigation:
- Use shared range controls only for aggregate historical sections
- Keep current-state sections labeled as current snapshots

## Success Criteria

The upgrade is successful when:

1. The dashboard reads as a trader control panel rather than a system-status page
2. A user can assess account PnL, free capital, drawdown, and open risk from the top section alone
3. Open positions are sortable and interpretable from a risk perspective
4. Execution quality and strategy performance are visible without reading raw rows
5. Unsupported live-price metrics are shown honestly as unavailable
6. Existing health and event visibility are preserved
