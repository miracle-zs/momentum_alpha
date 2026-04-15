# Trading Console Design

## Goal

Build a frontend-framework-based trading console that uses SQLite-backed telemetry as its primary data source and adds account-level visualizations for wallet balance, equity, unrealized PnL, and net value trends.

## Context

The project already has:

- a Python polling service and user-stream service
- a SQLite runtime store used by the dashboard
- a basic server-rendered dashboard with health, leader rotation, event pulse, and decision summaries

The next step is to turn this into a real operator console. The console should help an operator answer three questions within a few seconds:

1. Is the system healthy?
2. Why did it or did it not trade?
3. What is happening to account equity over time?

## Requirements

### Functional

- Introduce a frontend framework UI for the dashboard.
- Continue to use SQLite as the primary source for dashboard data.
- Add account snapshot collection on an incremental basis from now onward.
- Visualize:
  - wallet balance
  - available balance
  - account equity / net value
  - unrealized PnL
  - position count
  - leader rotation
  - event pulse
  - decision outcomes / blocked reasons
- Keep all displayed timestamps in UTC+8 using the format `YYYY-MM-DD HH:MM:SS`.

### Non-Functional

- Do not backfill historical equity in this phase.
- Do not add authentication in this phase.
- Do not add trading controls or order placement UI in this phase.
- Minimize deployment risk by keeping the Python backend and current runtime services intact.

## Recommended Approach

Use a lightweight SPA frontend backed by new JSON endpoints from the existing Python process. Persist account snapshots into SQLite on each poll tick. Keep the current server-rendered HTML path only as a temporary fallback until the SPA is mounted and stable.

This is the best tradeoff because:

- account history can begin immediately without waiting on historical API research
- SQLite remains the single operational telemetry store
- the backend stays simple and deployable on the current server
- charts can be added incrementally once the data model exists

## Architecture

### Data Collection

Add a new SQLite table such as `account_snapshots` with fields including:

- `timestamp`
- `source`
- `wallet_balance`
- `available_balance`
- `equity`
- `unrealized_pnl`
- `position_count`
- `leader_symbol`
- `payload_json`

The polling worker should write one snapshot per tick after position restoration and after decision processing, using the latest account data available from Binance private endpoints. Net value will initially be represented by the `equity` time series.

### Backend API

Add dedicated JSON endpoints for the console:

- `/api/dashboard/summary`
- `/api/dashboard/timeseries`
- `/api/dashboard/tables`

The old `/api/dashboard` endpoint can remain for compatibility, but the new frontend should use the more structured endpoints to avoid over-fetching and to keep chart payloads explicit.

### Frontend

Use a lightweight frontend framework SPA. The UI should contain:

- top summary cards for health and account state
- equity / balance / PnL charts
- leader rotation and event pulse charts
- decision overview and blocked reason cards
- recent signals, broker orders, and runtime events tables

The frontend should poll periodically instead of opening websocket subscriptions in this phase. The runtime services already write the data; the dashboard only needs to read it.

### Time Formatting

All timestamps shown in the UI should be converted to UTC+8 and rendered as:

- `2026-04-15 16:52:00`

Raw ISO timestamps may still be preserved inside JSON payloads for debugging, but they should not be used directly in the main UI.

## Data Flow

1. Poll loop fetches market and account state.
2. Poll loop writes structured signal, order, position, and account snapshots into SQLite.
3. Python dashboard backend exposes summary and timeseries JSON endpoints.
4. Frontend polls the endpoints every few seconds.
5. Frontend renders account charts and monitoring panels.

## Rollout Strategy

Phase 1:

- add account snapshot table and write path
- add backend JSON endpoints
- add SPA shell with summary cards and charts

Phase 2:

- enhance tables and filters
- improve chart interactions
- retire or reduce the old server-rendered dashboard

## Risks

- Account equity fields must come from stable Binance private API fields. The implementation should tolerate missing values and record partial snapshots rather than failing the entire tick.
- If chart payloads grow too large, frontend performance may degrade. The API should cap the returned time window.
- The new frontend build and serving model must fit the current deployment flow.

## Success Criteria

- Operators can open one page and see health, recent decision outcomes, and account equity trends.
- Dashboard display is SQLite-first.
- Account net value history begins accumulating from deployment time forward.
- The UI shows readable UTC+8 timestamps throughout the main dashboard.
