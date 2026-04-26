# Dashboard Complete UI Redesign Design

**Date**: 2026-04-26
**Status**: Proposed

## Overview

Redesign the Momentum Alpha dashboard UI around the mockups generated for the current three-room architecture:

- `实时监控室` / Live Monitoring Room
- `复盘室` / Review Room
- `系统状态室` / System Status Room

The dashboard remains a Python server-rendered, read-only monitoring application. This redesign is a front-end composition and styling update only. It does not change strategy logic, order execution, runtime persistence, database schema, dashboard API payloads, or service deployment.

The first implementation should prioritize `实时监控室`, because it is the default landing room and the page where the complete mockup showed the most missing structure. The other rooms should then be aligned to the same visual system without changing their data semantics.

## Visual References

The project-local core page mockups for this redesign are four images:

- `assets/research/ui-reference/dashboard-redesign-live-complete.png`
- `assets/research/ui-reference/dashboard-redesign-review-overview.png`
- `assets/research/ui-reference/dashboard-redesign-daily-review.png`
- `assets/research/ui-reference/dashboard-redesign-system-status.png`

These images are design targets, not pixel-perfect implementation requirements. The actual implementation must respect the existing server-rendered HTML, current data availability, responsive constraints, and test coverage.

`assets/research/ui-reference/dashboard-redesign-live-first-screen.png` is an earlier supporting draft for live-room hierarchy only. It is superseded by `dashboard-redesign-live-complete.png` and is not counted as a core page mockup.

## Confirmed Direction

The user wants documentation completed before any code implementation begins.

The UI direction is:

- dark-first `Cosmic Gravity` trading terminal
- professional trader cockpit, not a marketing page
- dense but organized operational information
- warm gold primary accents, muted teal/cyan chart accents, green/amber/red status semantics
- sharp 6-8px cards and panels with thin borders
- compact controls and readable numerical hierarchy
- no new frontend framework

The page scope is:

- `实时监控室`
- `复盘室 / 总体复盘`
- `复盘室 / 每日复盘`
- `系统状态室`

The implementation order is:

1. `实时监控室`
2. shared visual system polish
3. `复盘室 / 总体复盘`
4. `复盘室 / 每日复盘`
5. `系统状态室`
6. responsive and browser verification

## Problem Statement

The project already has the correct information architecture: three trader workspaces plus review subviews. The remaining problem is that the rendered UI still reads too much like a collection of general dashboard cards. The redesigned mockups make the intended hierarchy clearer:

- live monitoring should answer "Am I safe right now?"
- review should answer "What did closed trades teach us?"
- daily review should answer "What changed in the current UTC+8 review window?"
- system status should answer "Can I trust the platform right now?"

The first live-room mockup was useful, but it did not show every live-room block. The corrected complete live-room mockup includes the full page structure. The code update should use that complete version as the authoritative live-room target.

## Goals

1. Make `实时监控室` a complete live cockpit with every current live-room section visible in the intended order.
2. Preserve the current data model and renderer boundaries.
3. Align all rooms to one visual system without making them indistinguishable.
4. Keep account risk visually dominant on the live page.
5. Keep `Closed Trade Detail` dominant on the review overview page.
6. Keep daily review separate from live monitoring and historical review.
7. Keep diagnostics dominant on the system status page.
8. Preserve current empty states, fallback rendering, query-param navigation, and legacy tab compatibility.
9. Add tests for section presence, section order, and CSS hook availability.
10. Verify the final dashboard in a browser after tests pass.

## Non-Goals

This redesign does not include:

- a React, Vue, or SPA rewrite
- new backend routes
- new database fields or runtime schema changes
- changes to strategy decisions, sizing, order submission, or reconciliation
- a new charting library
- CSV, notebook, or image export workflows
- auto-generated parameter recommendations
- changing `/api/dashboard` JSON semantics
- removing legacy tab normalization

## Approaches Considered

### Approach A: CSS-Only Skin

Only update existing styles and leave HTML order mostly unchanged.

Pros:

- lowest risk
- fast to implement
- little test churn

Cons:

- does not fully solve the live-room completeness problem
- keeps weak hierarchy where some supporting panels compete with primary panels
- makes the mockups hard to realize because layout structure stays too flat

This is not recommended.

### Approach B: Room Shell Recomposition With Shared Styling

Keep existing data builders, but adjust room shell markup and CSS classes so each room has a clearer composition.

Pros:

- matches the generated mockups
- preserves renderer and data boundaries
- keeps testable HTML section order
- allows a phased rollout by room

Cons:

- requires tests to be updated for new section order
- requires CSS work across component and responsive styles

This is the recommended approach.

### Approach C: New Frontend Layer

Introduce a dedicated frontend app and consume `/api/dashboard`.

Pros:

- cleanest long-term separation
- easier to build advanced interactions later

Cons:

- too large for the current request
- adds build/deployment complexity
- duplicates existing server-rendered UI behavior

This is not recommended for this phase.

## Recommended Direction

Use Approach B: room shell recomposition with shared styling.

The implementation should keep the current renderer helpers:

- `_build_live_account_risk_panel`
- `_build_live_core_lines_panel`
- `_build_execution_flow_panel`
- `_build_overview_home_command`
- `render_position_cards`
- `render_closed_trades_table`
- `render_daily_review_panel`

The primary code changes should be in room-level composition and CSS:

- `src/momentum_alpha/dashboard_render_live.py`
- `src/momentum_alpha/dashboard_render_review.py`
- `src/momentum_alpha/dashboard_render_system.py`
- `src/momentum_alpha/dashboard_assets_styles_components.py`
- `src/momentum_alpha/dashboard_assets_styles_responsive.py`

`dashboard_render_shell.py` should remain focused on data assembly and room dispatch. It may receive class-name or section-label adjustments only when a room helper needs a new input.

## Page Design

### `实时监控室`

Purpose: answer "Is the account safe right now, and what should I inspect next?"

The complete live-room order is:

1. Header, toolbar, and three-room navigation
2. `实时监控室` room header
3. `ACCOUNT RISK`
4. `CORE LIVE LINES`
5. `ACTIVE SIGNAL`
6. `Deployment Guardrails`
7. `Sequence Monitor`
8. `ACTIVE POSITIONS`
9. `ORDER FLOW`
10. `HOME COMMAND`
11. bottom live metrics: `EQUITY`, `TODAY NET PNL`, `OPEN RISK / EQUITY`, `SYSTEM HEALTH`

`ACCOUNT RISK` must be the strongest visual anchor. It should stay above the chart grid and include the current account pressure numbers:

- equity
- available balance
- margin usage
- open risk / equity
- today net PnL
- unrealized PnL
- current drawdown
- positions / orders

`CORE LIVE LINES` stays a 2x2 grid:

- Account Equity
- Margin Usage %
- Position Count
- Open Risk

The charts already use a shared live-core timeline. The redesign must not break that behavior.

The signal band should present three related blocks in one visual group:

- `ACTIVE SIGNAL`: decision type, target symbol, blocked reason, decision time, rotation count, blocked-reason breakdown
- `Deployment Guardrails`: qualitative live posture, sizing rule, and action reminder
- `Sequence Monitor`: leader timeline plus recent leader sequence

`ACTIVE POSITIONS` and `ORDER FLOW` should sit together as the live decision work surface. Positions get the larger column; order flow is a supporting diagnostic column.

`HOME COMMAND` remains a navigation and action-surface band. It should not visually compete with account risk.

Bottom live metrics are secondary confirmation cards and should remain visible after the primary work surface.

### `复盘室 / 总体复盘`

Purpose: answer "What did completed trades teach us?"

The page order is:

1. review subnav with `总体复盘` active
2. `TRADE REVIEW SUMMARY`
3. dominant `Closed Trade Detail` ledger
4. evidence grid:
   - `By Total Leg Count`
   - `By Leg Index`
   - `Stop Slippage Analysis`

`Closed Trade Detail` must be the largest and most important object on the page. The summary ribbon supports it and should not demote it.

The table remains lifecycle-based, not fill-based. It should continue to represent round trips and their leg details.

### `复盘室 / 每日复盘`

Purpose: answer "What changed in the selected UTC+8 08:30 to UTC+8 08:30 review window?"

The page keeps the existing `render_daily_review_panel` data and controls. Styling should align it to the new visual system:

- date/report controls stay compact
- daily headline stays visible
- KPI grid remains scannable
- daily trade table remains readable
- history/cumulative impact sections stay secondary to the selected-day report

No new daily-review data source is required for this phase.

### `系统状态室`

Purpose: answer "Can I trust the platform right now?"

The page order is:

1. `SYSTEM DIAGNOSTICS`
2. `ACTIVE WARNINGS`, when warnings exist
3. `SYSTEM HEALTH`
4. `SYSTEM CONFIG`
5. `RECENT EVENTS`

Diagnostics are the first visual anchor. Warnings must be visually separate from the event stream. Recent events stay filtered to meaningful action events rather than poll heartbeats.

## Component And Styling Rules

Shared styling should follow these rules:

- use the existing dark palette and `Cosmic Gravity` references
- keep card radii at 6-8px for operational panels
- use thin borders instead of heavy shadows
- use gold for section anchors and priority outlines
- use teal/cyan for live data and chart support
- use green, amber, and red only for status semantics
- keep typography compact and readable
- keep section labels uppercase where existing code already does so
- avoid nested cards inside decorative cards
- avoid decorative gradient orbs, blobs, and marketing hero layouts
- avoid large empty panels with little data
- preserve mobile stacking behavior

## Data Flow

The data flow remains unchanged:

1. `render_dashboard_body` builds the dashboard snapshot-derived view model.
2. `render_dashboard_room_nav` renders three-room navigation.
3. Room helpers render the active room.
4. Panel helpers render reusable account, chart, execution, position, review, and daily-review content.
5. CSS from `render_dashboard_styles` controls layout and visual hierarchy.

The redesign must not alter:

- `build_dashboard_timeseries_payload`
- runtime read/write modules
- runtime analytics
- strategy state
- dashboard API response fields

## Error Handling And Empty States

All current empty-state behavior must continue:

- no positions renders a positions empty state
- no live chart points renders chart empty state
- no action events renders `No recent action events`
- no warnings omits or minimizes the warning list without breaking the system room
- missing account or position values render as `n/a`
- malformed partial snapshots do not break the whole dashboard document

## Testing Requirements

Update or add tests for:

1. live room renders every complete-section label in the intended order
2. live room still includes `POSITION SUMMARY`, `ACCOUNT PULSE`, and `NEXT ACTIONS` inside `HOME COMMAND`
3. live room still renders four `CORE LIVE LINES` cards
4. live room still uses the shared core live timeline behavior
5. review overview renders review subnav, summary ribbon, closed-trade ledger, and evidence grid in order
6. daily review renders through the review room subnav with `每日复盘` active
7. system room renders diagnostics before health/config/events
8. CSS output includes the new live-room layout hooks
9. responsive CSS includes stacking rules for the new live-room grids

Tests should assert section presence and relative order, not pixel values.

## Rollout Plan

Roll out in small, testable passes:

1. document and approve this spec
2. document and approve the implementation plan
3. update live-room tests
4. update live-room markup
5. update shared live-room CSS
6. run dashboard tests
7. visually verify the dashboard locally
8. repeat the same pattern for review overview, daily review, and system status

## Success Criteria

The redesign is successful when:

- `实时监控室` includes every intended live-room block in the complete mockup order
- `ACCOUNT RISK` is the first and strongest live-room anchor
- review overview is table-first and `Closed Trade Detail` remains dominant
- daily review keeps its UTC+8 report workflow while matching the visual system
- system status reads as an ops console with diagnostics first
- all dashboard tests pass
- the local dashboard renders without overlapping text or incoherent layout on desktop and mobile widths
- no trading, persistence, API, or deployment behavior changes

## Spec Self-Review

Placeholder scan: no placeholders remain.

Internal consistency: the page scope, implementation order, and file boundaries align with the existing three-room dashboard architecture.

Scope check: this is one dashboard UI redesign plan. It is broad, but it can be implemented safely in room-by-room tasks. The first implementation task should be limited to `实时监控室`.

Ambiguity check: the complete live-room mockup is the authoritative target for `实时监控室`; the earlier first-screen mockup is a supporting reference only.
