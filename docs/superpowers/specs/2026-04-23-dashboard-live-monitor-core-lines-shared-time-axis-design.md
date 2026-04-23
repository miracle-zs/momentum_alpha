# Dashboard Live Monitor Core Lines Shared Time Axis Design

**Date**: 2026-04-23
**Status**: Proposed

## Overview

Unify the four charts inside `CORE LIVE LINES` so they render against the same time axis instead of each card scaling its x positions independently.

The current live room already has the right signals:

- `Account Equity`
- `Margin Usage %`
- `Position Count`
- `Open Risk`

The problem is that the cards only look aligned because they share the same card width. Their x positions are still derived from each series' own point count, so a spike in one card can visually land at a different moment than a spike in another.

This change keeps the current room structure and chart order. It only changes how the series are projected onto the x axis.

## Confirmed User Decision

The user wants `CORE LIVE LINES` to use one shared timeline so all four charts compare the same moments in time.

The user specifically chose:

- a shared time axis
- forward-filled live values for missing samples
- no change to the live-room layout order

## Problem Statement

Today, the four live cards are visually parallel but not temporally synchronized.

- `Account Equity`, `Margin Usage %`, and `Position Count` come from `recent_account_snapshots`.
- `Open Risk` comes from `recent_position_risk_snapshots` / `recent_position_snapshots`.
- The renderer currently maps points to x positions by list index, not by timestamp.

That means:

- cards with different sample counts are not guaranteed to line up at the same moment
- a sharp move in `Open Risk` may appear aligned with the wrong part of the account curve
- the panel reads as a dashboard, but not as a true shared time-series cockpit

## Goals

1. Render the four live cards on one shared x-axis domain.
2. Keep the current 2x2 desktop layout and card order.
3. Preserve the current y-axis styling and card colors.
4. Keep `Open Risk` separate from review-room `Peak Risk`.
5. Avoid introducing a new chart library or a new room.
6. Keep sparse data handling safe and predictable.

## Non-Goals

This design does not include:

- a new database table
- a new route or room
- changes to review-room lifecycle risk semantics
- a hover tooltip system
- a visible x-axis label band under every chart

## Approaches Considered

### Approach A: Shared Timeline Spine, Recommended

Build one canonical timeline from the union of timestamps in the live account snapshots and live position-risk snapshots. Render each card against that shared timeline and compute x positions from timestamps, not from index.

Pros:

- makes all four cards compare the same moments
- preserves different update cadences without inventing a new sampling rate
- keeps the dashboard truthful when one series is sparser than the others

Cons:

- requires a small payload shape change
- requires the SVG renderer to accept timestamp-based x coordinates

### Approach B: Reproject Risk Onto Account Timestamps Only

Use account snapshot timestamps as the only x domain and map `Open Risk` onto that spine.

Pros:

- simpler than a full union spine

Cons:

- loses risk-only timestamps
- can hide important open-risk changes that happen between account samples

### Approach C: Leave The Current Axis Behavior Alone

Keep each chart independently scaled by its own point count.

Pros:

- no structural work

Cons:

- does not solve the user's problem
- keeps the cards only visually aligned, not temporally aligned

This is not recommended.

## Recommended Direction

Use **Approach A**.

The live room should build a shared time spine from the union of all relevant timestamps and then render each chart against that same spine.

The important behavior change is:

- x positions come from timestamps
- not from `point index / point count`

## Data And Calculation

### Shared Timeline Payload

`build_dashboard_timeseries_payload(...)` should produce a shared live-core timeline for `CORE LIVE LINES`.

Keep the existing per-series payloads for compatibility:

- `account`
- `position_risk`

The new shared timeline is an additional projection used only by the live core cards.

That timeline should include, for each timestamp in the union of the live account and open-risk samples:

- `timestamp`
- `equity`
- `margin_usage_pct`
- `position_count`
- `open_risk`

### Timeline Rules

- Use the sorted union of timestamps from `recent_account_snapshots` and `recent_position_risk_snapshots`.
- For each timestamp, carry forward the latest known value for each metric.
- Do not invent a value before the first known sample for a metric.
- If `Open Risk` has no valid samples, keep the card in the empty state.
- If the runtime is flat, preserve the explicit zero-state behavior already in place.

### Rendering Rules

- The SVG renderer should position points by timestamp relative to the shared domain.
- Each card should still use its own metric key and color.
- The line should only connect valid numeric samples, but the x domain must remain shared.
- The visible left-to-right progression should represent actual time order, not just sample count.

## Layout Rules

- `CORE LIVE LINES` stays a 2x2 grid on desktop.
- Card order stays:
  1. `Account Equity`
  2. `Margin Usage %`
  3. `Position Count`
  4. `Open Risk`
- Tablet and mobile responsive behavior stays unchanged.

## Error Handling

- If one series is empty, the other series must still render.
- If the union timeline only contains a single usable timestamp, the chart should still render a stable axis.
- If all data is missing, the current empty-state cards remain.
- A malformed or partial snapshot must not break the other three charts.

## Testing

The implementation should add or update tests that verify:

1. `CORE LIVE LINES` still renders four cards in the same order.
2. The live cards use a shared timestamp domain instead of independent index-based x scaling.
3. A sparse `Open Risk` series still lines up with account-series timestamps.
4. A single-point live chart still renders a stable axis.
5. The dashboard still renders when one of the live series is empty.

## Component Boundaries

Expected touch points:

- `dashboard_data_payloads.py`
  - build a shared live-core timeline from the union of account and position-risk timestamps
  - keep the existing per-series payloads for other consumers
- `dashboard_render_panels.py`
  - update the SVG rendering helper to compute x positions from timestamps
  - keep the current live core card order and styling
- `dashboard_render_shell.py`
  - pass the shared timeline into `CORE LIVE LINES`
- `tests/test_dashboard_position_risk.py`
  - cover shared-timeline and sparse-series cases
- `tests/test_dashboard.py`
  - cover dashboard-level rendering and card order

## Success Criteria

This design is successful when:

- all four `CORE LIVE LINES` charts compare the same time domain
- the open-risk spike can be read against the same moments as equity and margin usage
- the room still feels like a cockpit, not a relabeled collection of independent sparklines
- no other room or review view changes behavior
