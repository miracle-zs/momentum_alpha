# Dashboard Live And System Room Layout Design

**Date**: 2026-04-21
**Status**: Proposed

## Overview

Refine the dashboard's `实时监控室` and `系统状态室` so each room has a single obvious first-screen purpose:

- `实时监控室` becomes a trader cockpit for live decision-making.
- `系统状态室` becomes an ops console for system health and diagnostics.

The goal is not to introduce new data sources or a new routing model. The dashboard should keep its current three-room structure and server-rendered implementation. This change is purely about layout hierarchy, section ordering, and information density.

The current rooms already contain the right building blocks. The remaining problem is that the first screen of each room still feels too broad:

- live risk, live signal, positions, and execution are present, but not prioritized enough
- system health, configuration, warnings, and event logs are present, but not organized around diagnosis flow

This design tightens the hierarchy so the user can answer the room's main question in one pass.

## Confirmed User Decision

The user confirmed that both rooms should be optimized.

The desired direction is:

- `实时监控室` should feel like a cockpit
- `系统状态室` should feel like a console

## Problem Statement

The current layout already uses separate regions, but the visual hierarchy still reads like a collection of cards rather than a trading workflow.

In `实时监控室`, the user wants the most important live question first:

- Is the account safe?
- What signal is active?
- Which positions or execution details need attention next?

In `系统状态室`, the user wants the operational question first:

- Is the system healthy?
- What is warning?
- What changed recently?
- Which source or config layer should be inspected next?

Without a clearer hierarchy, both rooms remain informative but slower to scan.

## Goals

### `实时监控室`

1. Make live risk the first visual anchor.
2. Keep the current signal and decision state visible without competing with risk.
3. Show positions and execution in support of the live decision, not as equal peers.
4. Preserve the current data fields and room navigation.
5. Keep the room readable on desktop and mobile without adding a new framework.

### `系统状态室`

1. Make system health the first visual anchor.
2. Separate health, configuration, warnings, and recent events into clearer layers.
3. Keep data freshness and source visibility obvious.
4. Preserve the existing diagnostic information instead of removing content.
5. Keep the room fast to render and simple to maintain.

## Non-Goals

This design does not include:

- new routes
- new database tables
- new data sources
- changes to the trading logic
- changes to the daily review room
- a frontend framework rewrite

## Approaches Considered

### Approach A: Minimal Reorder Only

Move sections around, but keep the current cards and grid widths almost unchanged.

Pros:

- very low implementation risk
- easy to review
- no major CSS rewrite

Cons:

- only partially solves the hierarchy problem
- rooms still look like general dashboards rather than purpose-built workspaces

This is not recommended.

### Approach B: Cockpit And Console Re-layout

Rebuild the room shells around a clear first-screen hierarchy:

- `实时监控室`: risk summary, signal context, positions, execution
- `系统状态室`: diagnostics summary, config/source panel, warnings, recent events

Pros:

- best match for the user's workflow
- stronger first-screen readability
- preserves existing data while improving focus

Cons:

- requires CSS and shell markup updates
- some tests need to be updated if section ordering changes

This is the recommended approach.

### Approach C: Deeper Visual Overhaul

Introduce more aggressive styling, larger contrast blocks, and more dramatic section treatment.

Pros:

- can look more distinctive
- could make the dashboard feel more productized

Cons:

- higher risk of overdesign
- more likely to drift away from the current dashboard language

This is not recommended for the first pass.

## Recommended Direction

Use **Approach B**.

The layout should remain aligned with the current dashboard style, but the room shells should be reorganized so each room reads as a dedicated workspace:

- `实时监控室` should immediately answer "Am I safe right now?"
- `系统状态室` should immediately answer "Is the platform healthy?"

## Room 1: 实时监控室

### Purpose

Answer: "What is the live account state, what is the active signal, and what should I inspect next?"

### Layout Strategy

The room should read top-to-bottom in this order:

1. live risk summary
2. core account trend lines
3. active signal and decision context
4. active positions
5. execution / order-flow details

### First Screen Priority

The first screen should favor the following reading order:

1. account risk
2. active signal
3. position exposure
4. execution pulse

The live room should not feel like a generic mixed dashboard. It should feel like a cockpit where the user can make a trading decision quickly.

### Section Rules

- `ACCOUNT RISK` should remain the strongest visual element.
- `CORE LIVE LINES` should stay near the top and support the live risk read.
- `ACTIVE SIGNAL` should stay visible but should not compete with risk.
- `ACTIVE POSITIONS` should remain a primary work surface.
- `ORDER FLOW` and related execution blocks should read as supporting diagnostics.

### Data Preservation

This change should not remove any of the live room's current data fields. It only changes priority and composition.

## Room 2: 系统状态室

### Purpose

Answer: "Is the system healthy, what is warning, and where should I inspect first?"

### Layout Strategy

The room should read top-to-bottom in this order:

1. system diagnostics summary
2. config and source information
3. active warnings
4. recent events

### First Screen Priority

The first screen should answer system health before exposing the event stream.

The diagnostics summary should be treated as the main anchor because it is the fastest way to tell whether the platform is healthy or not.

### Section Rules

- `SYSTEM DIAGNOSTICS` should be first and concise.
- configuration and data-source context should be visible but secondary.
- warnings should be clearly separated from the general event list.
- recent events should remain readable as a feed, not as the dominant visual block.

### Data Preservation

The system room should keep the current health, configuration, warnings, sources, and recent events. The change is only in arrangement and emphasis.

## Component Boundaries

The implementation should keep the existing dashboard renderer structure and adjust the room shell markup plus CSS classes.

Expected boundary areas:

- live room shell markup in `dashboard_render_shell.py`
- system room shell markup in `dashboard_render_shell.py`
- section-specific CSS in `dashboard_assets_styles.py`
- regression coverage in `tests/test_dashboard.py`

The data model should not change for this work.

## Error Handling And Fallbacks

The layout change should preserve current empty-state behavior:

- if a room has no positions, no warnings, or no recent events, the existing empty state should continue to render
- if a section is missing data, the room should still render the rest of the content
- no new runtime failure mode should be introduced by the re-layout

## Testing

The implementation should include tests that verify:

1. `实时监控室` still renders the current live sections in the intended order.
2. `系统状态室` still renders diagnostics, warnings, config, source data, and recent events.
3. The new layout keeps the room-specific section labels in the expected sequence.
4. Existing review-room tests remain unchanged.

The tests should be resilient to copy tweaks where possible and should focus on section presence and order rather than exact spacing.

## Rollout Notes

This change should be purely additive in behavior and visual hierarchy.

It is safe to ship without a migration because:

- no stored data format changes
- no runtime schema changes
- no routing changes
- no new feature flags

## Open Questions

None. The user has already confirmed the desired direction: `实时监控室` should become a cockpit and `系统状态室` should become a console.
