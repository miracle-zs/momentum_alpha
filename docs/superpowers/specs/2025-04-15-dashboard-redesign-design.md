# Dashboard Redesign Design

**Date**: 2025-04-15
**Status**: Approved

## Overview

Redesign the Momentum Alpha trading dashboard with improved information hierarchy and new features:
- Better organized single-page layout with clear sections
- Position details panel showing entry/stop/quantity/risk
- Trade history table with broker orders
- Strategy configuration display

## Problems with Current Design

1. **Layout chaos** — Information is scattered across left/right panels without clear organization
2. **Missing position details** — No visibility into entry price, stop price, quantity, or risk per position
3. **No trade history** — Broker orders shown as simple list, not actionable table
4. **Hidden strategy config** — Current parameters not displayed anywhere

## Proposed Solution

### Section-Based Single Page Layout

All information visible on one page, organized into clear sections from top to bottom:

```
┌─────────────────────────────────────────────────────────────┐
│  Header: Logo + Title + Health Status Badge                 │
├─────────────────────────────────────────────────────────────┤
│  Key Metrics Row (5 cards)                                  │
│  [Leader] [Positions] [Equity] [Unrealized PnL] [Orders]    │
├─────────────────────────────────────────────────────────────┤
│  POSITIONS SECTION                                           │
│  ┌──────────────────┐  ┌──────────────────┐                 │
│  │ BTCUSDT LONG     │  │ ETHUSDT LONG     │                 │
│  │ Qty | Entry | Stop│  │ Qty | Entry | Stop│                │
│  │ Risk | Legs      │  │ Risk | Legs      │                 │
│  └──────────────────┘  └──────────────────┘                 │
├─────────────────────────────────────────────────────────────┤
│  ACCOUNT METRICS SECTION                                     │
│  [Equity Chart] [Wallet Chart] [PnL Chart]                  │
├─────────────────────────────────────────────────────────────┤
│  DECISION & LEADER ROTATION (side by side)                  │
│  [Latest Decision]  [Leader Timeline]                       │
├─────────────────────────────────────────────────────────────┤
│  TRADE HISTORY SECTION                                       │
│  Time | Symbol | Action | Side | Qty | Status               │
│  (scrollable table, last 10 orders)                         │
├─────────────────────────────────────────────────────────────┤
│  BOTTOM ROW (3 columns)                                      │
│  [Strategy Config] [System Health] [Recent Events]          │
└─────────────────────────────────────────────────────────────┘
```

### New Features

#### 1. Position Details Panel

Each position card shows:
- Symbol + Direction (LONG/SHORT)
- Quantity (total across legs)
- Entry Price (weighted average or first leg)
- Stop Price (current stop level)
- Risk Amount (quantity × (entry - stop))
- Leg breakdown: `Leg 1: base · 09:15 | Leg 2: add_on · 10:00`

**Data Source**: `position_snapshots.payload_json` contains full `Position` object with legs

#### 2. Trade History Table

Scrollable table with columns:
- Timestamp
- Symbol
- Action Type (base_entry, add_on_entry, stop_loss, etc.)
- Side (BUY/SELL)
- Quantity
- Order Status (FILLED, NEW, CANCELED)

**Data Source**: `broker_orders` table

#### 3. Strategy Configuration Panel

Always visible sidebar showing:
- Stop Budget (USDT)
- Entry Window (UTC hours)
- Testnet Mode (Yes/No)
- Submit Orders flag

**Data Source**: Runtime config (passed to dashboard), state file

### Layout Changes

| Current | New |
|---------|-----|
| 4 metric cards | 5 metric cards (added Tracked Orders) |
| Left/right panel split | Full-width sections |
| Simple position count | Full position details |
| Signal/Order lists | Trade history table |
| No config display | Config panel always visible |

### Visual Style

Keep the current dark tech aesthetic:
- Background: `#060a10` (deep)
- Cards: `rgba(18,28,45,0.8)`
- Accent: `#00d4ff` (cyan)
- Success: `#00ff88` (green)
- Danger: `#ff4466` (red)
- Monospace font family

## Implementation Notes

### Data Loading Changes

1. **Fetch position legs**: Extract from `position_snapshots.payload_json`
2. **Calculate weighted entry**: Average entry price across legs
3. **Calculate risk**: Sum of `quantity × (entry - stop)` per leg
4. **Fetch trade history**: Use `fetch_recent_broker_orders()` with expanded fields

### New Helper Functions

```python
def _build_position_details(position_snapshot: dict) -> dict:
    """Extract position details with leg breakdown."""

def _render_position_card(position: dict) -> str:
    """Render HTML for a single position card."""

def _render_trade_history_table(orders: list[dict]) -> str:
    """Render HTML table for trade history."""

def _get_strategy_config(state: dict, runtime_config: dict) -> dict:
    """Extract strategy config for display."""
```

### HTML Structure Changes

- Remove `main-layout` grid with left/right panels
- Replace with stacked sections using `<section>` tags
- Each section has a header with accent-colored label
- Position cards use 2-column grid inside section
- Trade history uses `<table>` for proper alignment

## Success Criteria

1. All existing metrics still visible
2. Position details show entry/stop/quantity/risk for each position
3. Trade history displays last 10 broker orders in table format
4. Strategy config visible without clicking
5. Page remains responsive on mobile (stack sections vertically)
6. Auto-refresh (5s) continues to work
