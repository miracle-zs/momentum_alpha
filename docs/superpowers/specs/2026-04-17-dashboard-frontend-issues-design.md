# Dashboard Frontend Issues Remediation Design

Date: 2026-04-17

## Summary

This spec covers the next remediation pass for the Momentum Alpha trading dashboard based on the current live frontend state. The goal is to close the position-diagnostics data loop, remove misleading fallback values, improve execution and rotation readability, and tighten the dashboard into a more reliable trader-facing control panel.

This pass stays within the existing dashboard architecture:

- extend the current snapshot payloads instead of introducing new tables
- keep the existing single-page dashboard structure
- implement missing live-price-dependent position diagnostics
- improve display correctness and visual prioritization for risk and execution data

## Problems Observed

### 1. Position diagnostics are incomplete

The live page still shows `MTM n/a` and `DIST TO STOP n/a`, with a waiting message for live price data. That means the dashboard cannot yet provide real position health diagnostics.

### 2. Missing stop values are rendered as `0`

Displaying `STOP 0` is misleading. Users can interpret that as a real stop level instead of a missing or invalid stop.

### 3. Drawdown formatting is mechanically correct but semantically weak

The page shows values like `+0.00` for drawdown. Drawdown should display as `0.00` or a negative number.

### 4. Account chart lacks context for discontinuities

Large step changes in equity or adjusted equity appear without any explanation. This makes users question whether changes are due to trading, deposits, or snapshot irregularities.

### 5. Leader rotation section is underpowered

The current timeline visualization alone does not justify the `LEADER ROTATION` heading. It needs summary context to be useful.

### 6. Execution and trade tables are hard to scan

Precision is inconsistent and the current stop-slippage and round-trip areas do not clearly express their column semantics.

### 7. Empty and high-risk states are not handled strongly enough

Some empty states consume too much space, while important risk signals such as high open-risk percentage are not visually elevated enough.

## Goals

- Show live-price-dependent position metrics whenever the runtime already has the needed data
- Never present missing stop or price values as legitimate numeric values
- Normalize dashboard numeric formatting for faster scanning
- Make leader rotation and blocked-signal areas more explanatory
- Improve readability for execution-quality and strategy-performance tables
- Make high-risk states visibly different from normal states

## Non-Goals

- no new standalone market snapshots table
- no separate frontend price polling path
- no historical deposit/withdrawal reconciliation system in this pass
- no full redesign of the entire dashboard layout

## Approach Options

### Option 1: Patch rendering only

Keep current payloads and only improve the frontend rendering.

Pros:

- smallest code diff
- lowest short-term risk

Cons:

- does not solve the missing live-price diagnostics
- leaves key trader metrics unavailable

### Option 2: Extend existing snapshot payloads and tighten rendering

Persist live market context into the existing snapshot payloads, then consume it in the dashboard to compute live position diagnostics and improve the remaining display issues.

Pros:

- solves the core missing diagnostics
- fits current architecture
- keeps data timing aligned with strategy ticks

Cons:

- touches runtime persistence and dashboard rendering together

### Option 3: Build a new dashboard-specific market data path

Add a new table or dashboard-side fetch path for live market state.

Pros:

- clean separation of concerns

Cons:

- heavier scope than required
- more moving parts
- unnecessary for the current problem

## Recommended Approach

Use Option 2.

The runtime already has the relevant market data. The main issue is that the dashboard does not consume a stable persisted form of that data. Extending the existing snapshot payloads closes the highest-priority gap without introducing new infrastructure.

## Design

### Section 1: Persist live market context into snapshots

Extend the latest position snapshot payload so each tracked position can carry:

- `latest_price`
- `daily_change_pct`
- `previous_hour_low`
- `current_hour_low`

Also add a top-level `market_context` object to the position snapshot payload containing:

- `leader_symbol`
- `leader_gap_pct`
- `candidates`

`candidates` will contain a lightweight top-five ranking only, with:

- `symbol`
- `latest_price`
- `daily_change_pct`
- `previous_hour_low`
- `current_hour_low`

This keeps the payload small enough for the dashboard while allowing lightweight signal-context display.

### Section 2: Compute live position diagnostics in the dashboard

Use existing position data plus persisted `latest_price` to compute:

- `Current Price`
- `MTM PnL`
- `PnL %`
- `Distance to Stop %`
- `R multiple`
- `Notional Exposure`

Rules:

- if `latest_price` is missing or invalid, all live-price-derived fields render as `n/a`
- if `stop_price <= 0`, render stop-derived metrics as `n/a`
- if `avg_entry <= 0`, render `PnL %` as `n/a`
- never display invalid values as `0` unless the true value is actually zero

### Section 3: Fix misleading stop rendering

Stop display must distinguish valid zero from missing data. For trading stops, `0` is not a valid operational value in this dashboard context.

Rules:

- `stop_price is None`, `""`, `0`, or non-positive -> render `n/a` or `unset`
- do not use invalid stop values when calculating `risk`, `Distance to Stop %`, or `R multiple`

### Section 4: Correct drawdown semantics

Drawdown should represent the distance from the visible peak equity to the current equity.

Rules:

- if current equity equals peak equity, display `0.00`
- if current equity is below peak, display a negative value
- do not display `+0.00`

### Section 5: Improve account chart trustworthiness

The chart will continue to render visible account history, but when step changes are large enough to indicate likely non-trading discontinuities, the dashboard should surface a lightweight note rather than leaving the move unexplained.

This pass will not classify transfers perfectly, but it will:

- allow annotation of obvious large jumps
- make the chart less visually misleading

If the available data is insufficient to classify a jump, the note will remain descriptive rather than speculative.

### Section 6: Strengthen leader rotation context

The `LEADER ROTATION` section should include summary context in addition to the timeline:

- `Rotation Count`
- recent leader sequence
- optional average switch interval when enough history exists

When history is insufficient, the UI should say so explicitly.

### Section 7: Tighten execution-quality readability

Normalize formatting across:

- execution summary
- recent fills
- stop slippage analysis
- round trips

Formatting rules:

- percentages: 2 decimals
- USDT values: 2 decimals
- prices: 4-6 decimals depending on magnitude
- quantities: trim noise and avoid long float tails

`STOP SLIPPAGE ANALYSIS` must show explicit column semantics, not free-form numeric strings.

### Section 8: Improve empty and high-risk states

Adjust empty-state handling:

- `Blocked Reasons` with no data should collapse into a compact neutral state
- empty analytical areas should not dominate visual space

Adjust high-risk handling:

- `OPEN RISK / EQUITY` should gain a warning state once it exceeds a defined threshold
- thresholds for this pass:
  - `< 30%`: normal
  - `30% - 60%`: warning
  - `> 60%`: danger

The visual change can be implemented with value color, border emphasis, or both.

### Section 9: Improve table readability for strategy performance

The round-trip area should remain information-dense but easier to scan.

Requirements:

- visible column structure
- clearer separation of symbol, timing, exit reason, and pnl
- formatting consistent with execution tables

## Implementation Breakdown

### Runtime

Files:

- `src/momentum_alpha/main.py`

Tasks:

- persist per-position live market fields into the position snapshot payload
- persist top-level `market_context` into the position snapshot payload

### Dashboard

Files:

- `src/momentum_alpha/dashboard.py`

Tasks:

- consume live market fields from the latest position snapshot
- compute and render live position diagnostics
- correct invalid stop rendering
- normalize drawdown display
- improve leader rotation summary
- improve empty states and high-risk styling
- standardize formatting for execution and performance tables
- add clearer table semantics where currently missing

### Tests

Files:

- `tests/test_main.py`
- `tests/test_dashboard.py`

Tasks:

- assert snapshot payload persistence for live market fields and `market_context`
- assert live position metrics render when data is present
- assert `n/a` fallback when data is absent
- assert invalid stop values do not render as `0`
- assert drawdown zero is not displayed as `+0.00`
- assert risk threshold styling states
- assert explicit table headings and normalized values
- assert leader rotation summary behavior for both sufficient and insufficient history

## Phases

### Phase 1

- persist live market context
- render live position diagnostics

### Phase 2

- fix invalid stop rendering
- fix drawdown formatting

### Phase 3

- normalize numeric formatting
- improve execution and round-trip readability

### Phase 4

- strengthen leader rotation context
- tighten empty states
- add high-risk emphasis

## Risks

- runtime payload shape changes may break older tests if fallback handling is not kept backward compatible
- live market data may be partially present for some symbols, so rendering logic must degrade cleanly
- number-format normalization can create snapshot-test churn if not implemented consistently

## Validation

Minimum validation before completion:

- targeted unit tests for snapshot persistence and dashboard rendering
- full `tests.test_dashboard`
- regression run for `tests.test_main`, `tests.test_runtime_store`, and `tests.test_health`

## Decision

Proceed with the phased remediation above, using existing snapshot payloads as the transport for live market context and improving the dashboard rendering in place.
