# Dashboard Three-Room Architecture Design

**Date**: 2026-04-20
**Status**: Approved

## Overview

Restructure the Momentum Alpha dashboard around three trader workspaces:

- `实时监控室` / Live Monitoring Room
- `复盘室` / Review Room
- `系统状态室` / System Status Room

This replaces the current four-tab mental model of `Overview`, `Execution`, `Performance`, and `System` with a sharper professional trading workflow:

1. Monitor live account and position risk.
2. Review closed trades and optimize strategy parameters.
3. Verify that runtime systems and data sources are healthy.

The dashboard should still remain a single server-rendered application in the first implementation. The change is an information-architecture redesign, not a requirement to introduce a new frontend framework or split the app into multiple services.

## Confirmed User Decisions

The design is locked to the following user-approved choices:

- The dashboard should be organized into three rooms: `实时监控室`, `复盘室`, and `系统状态室`.
- `实时监控室` is the default landing room when the dashboard opens.
- `实时监控室` uses an account-risk-first first screen.
- `复盘室` is centered on `Closed Trade Detail`.
- `复盘室` uses a ledger/table-first first screen for closed trades.
- The old `Execution` tab should not remain as a separate room.
- Execution content should be split by use:
  - live execution pulse belongs in `实时监控室`
  - execution quality analysis belongs in `复盘室`
  - data-source freshness belongs in `系统状态室`
- `系统状态室` should stay close to the current system view: runtime status, data freshness, configuration, warnings, event sources, and recent events.

## Problem Statement

The current dashboard has already moved away from one long page and into a tabbed architecture. That improved structure, but the four-tab model still reflects implementation categories more than trader workflow.

The current tabs map roughly as:

- `Overview`: current trading state
- `Execution`: order and fill diagnostics
- `Performance`: closed-trade and account analytics
- `System`: runtime operations

For a professional trader, `Execution` is not a standalone mode. It is either:

- a live risk signal while monitoring open positions, or
- an analytical dimension while reviewing completed trades.

Keeping it as its own top-level room makes the dashboard less direct. It also fragments the user's attention: live execution risk is separated from live account risk, while historical slippage and fees are separated from closed-trade review.

The next dashboard shape should match the trader's actual operating loop:

1. Am I safe right now?
2. What did completed trades teach me?
3. Can I trust the system and data?

## Goals

The redesigned dashboard should let the trader answer these questions quickly:

1. What is the account's live equity, available balance, margin usage, open risk, and current PnL?
2. How have account equity, margin usage, and position count moved over the selected window?
3. Which open positions are carrying the most risk or are closest to stop?
4. Are there current execution anomalies such as recent order/fill/stop issues?
5. Which closed trades deserve review, and what happened inside each complete lifecycle?
6. How did each leg contribute to the final closed-trade result?
7. Which parameters look weak when grouped by leg count, leg index, exit reason, hold time, fees, or slippage?
8. Is the runtime healthy, and are all critical data sources fresh?

## Non-Goals

This design intentionally does not include:

- A new standalone frontend framework.
- A new route hierarchy as a required first step.
- A new separate `Execution` room.
- Automatic parameter recommendation logic.
- A normalized analytics schema beyond the current dashboard data model.
- Export workflows for CSV, JSON, or notebooks.
- Visual redesign beyond what is needed to support the new information hierarchy.

## Approaches Considered

### Approach A: Keep The Current Four Tabs

Pros:

- Lowest implementation cost.
- Preserves existing renderer names and tests.
- Avoids changing current navigation semantics.

Cons:

- Keeps `Execution` as a standalone mode even though it is not how the user wants to work.
- Splits live order/fill risk away from live account and position risk.
- Splits slippage and fill-quality review away from closed-trade analysis.
- Leaves `Performance` too broad: account analytics and closed-trade review compete for priority.

This approach is not recommended.

### Approach B: Three Rooms With Execution Split By Use

Pros:

- Matches the user's confirmed workflow.
- Makes `实时监控室` a true live trading homepage.
- Makes `复盘室` a true closed-trade review workspace.
- Keeps `系统状态室` operational and uncluttered.
- Reuses existing data and rendering helpers with a manageable reorganization.

Cons:

- Requires renaming and reorganizing existing tab renderers.
- Requires discipline so execution content does not grow into an implicit fourth room.
- Some existing tests that assert tab names or content placement will need updates.

This is the recommended approach.

### Approach C: Split Into Dedicated Multi-Page Rooms Immediately

Pros:

- Cleanest long-term route boundaries.
- Each room could eventually have room-specific endpoints and refresh policies.

Cons:

- Larger implementation surface than needed now.
- More routing and navigation churn.
- Higher risk of breaking the existing lightweight dashboard server.

This may be appropriate later, after the three-room structure has proven stable.

## Recommended Direction

Use Approach B: a three-room dashboard with execution content split by use.

The first implementation should keep one dashboard route and one server-rendered document. The top navigation changes from four implementation-oriented tabs to three trader workspaces:

- `实时监控室`
- `复盘室`
- `系统状态室`

The URL query parameter can continue to drive the active room. For example:

- `?room=live`
- `?room=review`
- `?room=system`

Keeping query-param navigation preserves direct links and refresh behavior while avoiding a route-level rewrite.

## Room 1: 实时监控室

### Purpose

Answer: "Is the account safe right now, and which live positions or execution events require attention?"

This room is the default landing view.

### First-Screen Priority

The first screen is account-risk-first. It should prioritize account pressure before detailed position review.

Primary first-screen hierarchy:

1. Account risk summary
2. Three core account/position trend lines
3. Active position state
4. Execution pulse

### Account Real-Time State

The account panel should include:

- equity
- wallet balance
- available balance
- unrealized PnL
- today net PnL
- margin usage percentage
- open risk
- open risk as percentage of equity
- current position count
- current open order count

Margin usage remains the real account occupancy metric:

`margin_usage_pct = (1 - available_balance / equity) * 100`

### Core Lines

The live room should expose three first-class line charts:

- account equity
- margin usage percentage
- position count

These charts should use the existing account range control where possible.

### Position Real-Time State

Active positions should show the fields needed for live risk inspection:

- symbol
- direction
- quantity
- weighted entry price
- stop price
- latest price
- mark-to-market PnL
- PnL percentage
- distance to stop
- notional exposure
- R multiple versus current risk
- leg count
- opened time
- leg summary

Positions should be sorted to surface risk first. A practical default is:

1. positions with known risk before positions with unknown risk
2. higher open risk before lower open risk
3. stable symbol ordering as a tie-breaker

### Execution Pulse

The live room should include only execution information that affects current monitoring:

- latest broker order
- latest algo order
- latest trade fill
- latest stop exit
- open order or stop-status anomalies when available

It should not include full historical execution analysis. That belongs in `复盘室`.

## Room 2: 复盘室

### Purpose

Answer: "What did completed trades teach us, and which strategy parameters should be optimized?"

This room is centered on `Closed Trade Detail`.

### First-Screen Priority

The first screen is ledger/table-first.

The `Closed Trade Detail` table should be the dominant first-screen object. Summary metrics and filters may sit above it, but they should not visually demote the table.

### Closed Trade Detail

The table should show complete trade lifecycles, not isolated fills.

A complete trade remains the existing round-trip definition:

- the first `BUY` opens the trade
- later `BUY`s before flat closure are add-on legs
- `SELL`s reduce net quantity
- the trade closes only when net quantity returns to zero

Recommended top-level columns:

- symbol
- opened at
- closed at
- duration
- leg count
- peak cumulative risk
- exit reason
- gross PnL
- commission
- net PnL

Each row should support expanded leg detail.

### Leg Detail

Expanded rows should show leg-level analysis:

- leg index
- leg type
- opened at
- quantity
- entry price
- stop price at entry
- leg risk
- cumulative risk after leg
- gross PnL contribution
- fee share
- net PnL contribution

Missing stop or risk data should remain explicit as unavailable. The dashboard must not synthesize risk values from later stop replacements.

### Derived Review Analysis

The review room should derive analysis from closed trade detail after the table, not before it.

Initial derived sections:

- aggregate by total leg count
- aggregate by leg index
- aggregate by exit reason
- aggregate by hold-time bucket
- stop slippage analysis
- fee and fill-quality impact

These sections exist to support strategy and parameter optimization, especially:

- stop budget sizing
- add-on thresholds
- leg-specific risk limits
- exit logic
- execution quality review

## Room 3: 系统状态室

### Purpose

Answer: "Is the system running, and can I trust the data shown in the other rooms?"

This room keeps the current system/operations responsibilities. It should not be used for trading decision summaries except where needed to explain data trust.

### Content

The system room should include:

- overall health status
- runtime database freshness
- poll event freshness
- user stream event freshness
- latest account snapshot freshness
- latest position snapshot freshness
- latest signal decision freshness
- latest trade fill freshness
- service/runtime configuration
- testnet versus production mode
- submit-orders mode
- entry window
- stop budget
- warnings
- event sources
- recent events

### Rules

- Keep operational diagnostics here.
- Do not duplicate full live account and position panels here.
- Do not duplicate closed trade analytics here.
- Use the system room to explain whether other room data is trustworthy.

## Execution Content Allocation

The old `Execution` tab should be removed as a top-level room.

Execution content is allocated by user intent:

### Live Monitoring Room

Execution content in `实时监控室` is current-state oriented:

- latest order flow card
- recent fill pulse
- latest stop exit pulse
- stop/order anomaly hints

This answers: "Is anything currently wrong with order execution?"

### Review Room

Execution content in `复盘室` is outcome-analysis oriented:

- stop slippage analysis
- fees
- fill quality
- execution impact on net PnL
- execution context inside expanded closed trades

This answers: "How did execution quality affect completed trade results?"

### System Status Room

Execution content in `系统状态室` is data-trust oriented:

- freshness of broker orders
- freshness of algo orders
- freshness of trade fills
- source event counts
- ingestion/runtime warnings

This answers: "Are execution data sources alive and trustworthy?"

## Navigation Design

The dashboard should expose three top-level navigation items:

- `实时监控室`
- `复盘室`
- `系统状态室`

Default active room:

- `实时监控室`

Behavior:

- refresh keeps the active room
- direct room links are supported
- invalid room parameters fall back to `实时监控室`
- existing account range controls should keep working where relevant

The first implementation can keep backward compatibility for old tab query parameters if useful, mapping:

- `overview` and `execution` to `live`
- `performance` to `review`
- `system` to `system`

This compatibility is optional but would reduce surprise during rollout.

## Rendering Strategy

The dashboard is currently rendered in `src/momentum_alpha/dashboard.py`.

The implementation should reorganize renderers around rooms rather than hiding or showing sections inside one large template.

Recommended renderer shape:

- `normalize_dashboard_room(value)`
- `render_dashboard_room_nav(active_room, account_range_key)`
- `render_dashboard_live_room(...)`
- `render_dashboard_review_room(...)`
- `render_dashboard_system_room(...)`

The shell remains responsible for:

- document structure
- header
- global status badge
- execution mode label
- refresh controls
- room navigation
- active room content slot

Each room renderer owns only the content for that room.

Existing helper functions should be reused where possible:

- account timeseries payload builder
- account metrics/stat calculations
- position detail builder
- position card/table renderer
- closed trade table renderer
- trade leg aggregate builders
- stop slippage renderer
- health and event renderers

## Data Boundaries

No new database tables are required for this information-architecture change.

The existing snapshot already provides the needed data:

- runtime summary
- latest account snapshot
- account snapshot history
- latest position snapshot
- recent trade fills
- recent broker orders
- recent algo orders
- recent stop exit summaries
- recent trade round trips
- signal decisions
- health report
- recent audit events
- source counts
- strategy config

Any new data work should be limited to fields needed to improve existing room content. It should not be introduced solely because the navigation changed.

## Testing Strategy

Tests should verify:

- room normalization defaults to `live`
- room navigation renders the three approved room labels
- old tab values either map correctly or fail safely to `live`
- `实时监控室` includes account risk, the three core chart metrics, active positions, and execution pulse content
- `复盘室` includes `Closed Trade Detail` before aggregate analytics
- `复盘室` includes leg detail and derived aggregate analysis when payload data is present
- `系统状态室` includes health, freshness, warnings, configuration, event sources, and recent events
- execution-only historical analysis is not rendered in the live room as a full review section
- system diagnostics do not duplicate full live monitoring or closed-trade review content

## Acceptance Criteria

The redesign is complete when:

1. Opening the dashboard lands on `实时监控室`.
2. The top navigation contains only the three approved rooms.
3. `实时监控室` first screen is account-risk-first.
4. `实时监控室` shows account equity, margin usage, and position count charts.
5. `实时监控室` shows live account state and live position state.
6. `实时监控室` includes a compact execution pulse.
7. `复盘室` is centered on `Closed Trade Detail`.
8. `复盘室` renders closed trades as a ledger/table-first view with expandable leg details.
9. `复盘室` shows aggregate analysis after the closed-trade table.
10. `系统状态室` preserves current system health and data freshness responsibilities.
11. No standalone `Execution` room remains.
12. Existing dashboard refresh behavior continues to work.

## Rollout Notes

This design supersedes the four-tab information architecture from `2026-04-17-dashboard-tabbed-architecture-design.md`.

The margin usage and closed-trade leg analytics from `2026-04-19-dashboard-margin-usage-trade-legs-design.md` remain valid. This design changes where those capabilities live:

- margin usage line chart moves into the default live monitoring room
- closed-trade leg analytics become the center of the review room
- stop slippage and fill quality become review-room analysis rather than a standalone execution room
