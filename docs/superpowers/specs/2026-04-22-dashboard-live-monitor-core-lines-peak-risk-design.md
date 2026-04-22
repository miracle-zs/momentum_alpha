# Dashboard Live Monitor Core Lines Peak Risk Design

**Date**: 2026-04-22
**Status**: Proposed

## Overview

Extend `实时监控室` so `CORE LIVE LINES` contains a fourth chart card for live position peak risk and renders as a 2x2 grid on desktop.

The current live room already has the right structure:

- `ACCOUNT RISK` is the top safety summary.
- `CORE LIVE LINES` shows the main live trend signals.
- `ACTIVE SIGNAL`, `ACTIVE POSITIONS`, and `ORDER FLOW` support live decision-making.

This change does not introduce a new room or a new route. It only adds one more chart card inside `CORE LIVE LINES` and updates the data projection needed to feed that chart.

The user approved a four-card 2x2 layout for `CORE LIVE LINES`:

- `Account Equity`
- `Margin Usage %`
- `Position Count`
- `Peak Risk`

## Confirmed User Decision

The user wants:

- `CORE LIVE LINES` to keep its current three charts.
- A new fourth chart for live position `Peak Risk`.
- The four charts to read as a balanced 2x2 block on desktop.
- The new chart to remain in `实时监控室`, not in `ACCOUNT RISK`.

The user also approved the visual direction shown in the mockup:

- `Peak Risk` should use a red accent.
- The chart should feel like a live risk boundary, not a review-room lifecycle metric.

## Problem Statement

`ACCOUNT RISK` shows the current live risk state, but it is a snapshot. `ACTIVE POSITIONS` shows individual positions, but it does not show how the position book's risk has evolved over recent snapshots.

That creates a gap in the live cockpit:

- the trader can see current risk
- the trader can see current positions
- the trader cannot quickly scan how position risk has been changing over time

`CORE LIVE LINES` is the right place to close that gap because it already holds the live trend charts the trader uses first.

## Goals

1. Add a fourth `Peak Risk` chart to `CORE LIVE LINES`.
2. Keep the existing three charts in the same order.
3. Make the four cards feel equal on desktop, not like one card is a secondary add-on.
4. Derive the chart from existing live position snapshot data.
5. Keep the chart visually distinct from review-room `PEAK LIFECYCLE RISK`.
6. Preserve the current live-room workflow and first-screen hierarchy.
7. Keep the chart usable on tablet and mobile without breaking the room layout.

## Non-Goals

This design does not include:

- a new database table
- a new route or room
- changes to trading logic
- changes to review-room lifecycle risk semantics
- a new historical analytics page
- a separate charting library

## Approaches Considered

### Approach A: Add A Fourth Equal Card

Add a new `Peak Risk` chart card to the existing `CORE LIVE LINES` strip and compute the series from recent position snapshots.

Pros:

- matches the approved mockup
- keeps live trends grouped in one place
- makes peak risk easy to scan alongside equity, usage, and position count
- uses data the dashboard already has

Cons:

- requires a new derived time-series
- requires grid and responsive CSS changes

This is the recommended approach.

### Approach B: Put Peak Risk Inside `ACCOUNT RISK`

Add a smaller peak-risk sparkline or KPI inside the account risk panel instead of `CORE LIVE LINES`.

Pros:

- less layout work
- peak risk stays near open-risk summary

Cons:

- weakens the `CORE LIVE LINES` concept
- hides the trend in a denser summary block
- makes the live room feel more crowded

This is not recommended.

### Approach C: Replace An Existing Core Line

Swap out `Position Count` or another existing line to make room for `Peak Risk`.

Pros:

- avoids growing the number of cards

Cons:

- removes an existing signal the live room already relies on
- reduces scanability instead of improving it

This is not recommended.

## Recommended Direction

Use **Approach A**.

`CORE LIVE LINES` should become a four-card 2x2 grid on desktop, with the existing three signals retained and `Peak Risk` appended as the fourth card.

The new card should:

- use the same visual weight as the other three cards
- use a red accent to communicate risk
- read as a live monitoring signal, not a review artifact

## Data And Calculation

The Peak Risk chart should be derived from the existing `recent_position_snapshots` payload already included in the dashboard snapshot.

For each position snapshot:

1. Read `payload.positions`.
2. For each open position, compute risk using the same risk math used by the live position detail view:
   - LONG: `quantity * (entry_price - stop_price)`
   - SHORT: `quantity * (stop_price - entry_price)`
3. Sum the computable position risks to get the snapshot's live position risk value.
4. Use that value as the chart point for that timestamp.

Important rules:

- Do not invent a risk value if a snapshot lacks the required entry or stop data.
- Skip incomplete positions rather than forcing them to zero.
- Keep the unit in USDT.
- The chart should reflect the live risk trend of the current position book, not the review-room lifecycle peak risk metric.

The first implementation can use the recent snapshot slice already loaded by the dashboard refresh cycle. It does not need a new query path.

## Layout Rules

### Desktop

- `CORE LIVE LINES` should render four cards in a 2x2 grid.
- The order should remain:
  1. `Account Equity`
  2. `Margin Usage %`
  3. `Position Count`
  4. `Peak Risk`
- Each row should use the same height and frame language so the two rows feel balanced.

### Tablet

- The cards should also use a 2-by-2 grid.
- `Peak Risk` should stay in the same order, not jump to a separate section.

### Mobile

- The cards should stack vertically.
- The `Peak Risk` card should remain the last core line card.
- The red accent should remain visible, but the card should not become visually louder than the rest of the live room.

## Error Handling

- If there are no usable position snapshots, the `Peak Risk` card should render the existing chart empty state.
- If some snapshots are partial, the chart should skip those points and continue rendering any valid points.
- A missing peak-risk series must not break the rest of the live room.

## Testing

The implementation should add or update tests that verify:

1. `CORE LIVE LINES` now contains four cards.
2. `Peak Risk` appears after `Position Count`.
3. The peak-risk chart uses the same live-room snapshot data path as the other charts.
4. The dashboard still renders correctly when the live snapshot data is sparse.
5. Review-room `PEAK LIFECYCLE RISK` text is unchanged, so the two risk concepts stay separate.

## Component Boundaries

The implementation should stay within the existing dashboard rendering pipeline.

Expected touch points:

- `dashboard_render_shell.py`
  - pass the extra peak-risk series into the live core lines renderer
- `dashboard_render_panels.py`
  - render the fourth `Peak Risk` card
  - update the live core lines grid layout
- `dashboard_view_model.py`
  - derive the peak-risk series from recent position snapshots
- `dashboard_assets_styles.py`
  - support the 4-card desktop layout and responsive fallbacks
- `tests/test_dashboard.py`
  - verify the new card order and live-room copy

## Success Criteria

This design is successful when:

- the live room first screen still reads as a cockpit
- `CORE LIVE LINES` now gives the user a fast visual read on current position risk trend
- the new chart fits the existing dashboard style
- nothing in the review room changes as a side effect
