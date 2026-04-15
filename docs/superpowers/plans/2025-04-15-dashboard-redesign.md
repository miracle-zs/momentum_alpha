# Dashboard Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Redesign dashboard with section-based layout, position details, trade history table, and strategy config display.

**Architecture:** Single-page layout with stacked sections. Add helper functions for extracting position details from payload_json, rendering trade history table, and fetching strategy config. Maintain existing data loading logic.

**Tech Stack:** Python 3.13, stdlib only (http.server, sqlite3), inline HTML/CSS/SVG

---

## File Structure

| File | Responsibility |
|------|----------------|
| `src/momentum_alpha/dashboard.py` | Main dashboard module - add helpers, restructure HTML |
| `tests/test_dashboard.py` | Unit tests for new helper functions and HTML output |

---

### Task 1: Add Position Details Helper Functions

**Files:**
- Modify: `src/momentum_alpha/dashboard.py` (add after line 166)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests for position details extraction**

Add to `tests/test_dashboard.py`:

```python
    def test_build_position_details_extracts_legs_from_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        position_snapshot = {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base"
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on"
                            }
                        ]
                    }
                }
            }
        }

        details = build_position_details(position_snapshot)

        self.assertEqual(len(details), 1)
        self.assertEqual(details[0]["symbol"], "BTCUSDT")
        self.assertEqual(details[0]["total_quantity"], "0.015")
        self.assertEqual(details[0]["entry_price"], "82166.67")  # weighted average
        self.assertEqual(details[0]["stop_price"], "81000")
        self.assertAlmostEqual(float(details[0]["risk"]), 17.50, places=2)

    def test_build_position_details_returns_empty_list_for_missing_payload(self) -> None:
        from momentum_alpha.dashboard import build_position_details

        details = build_position_details({})
        self.assertEqual(details, [])

        details = build_position_details({"payload": {}})
        self.assertEqual(details, [])
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_extracts_legs_from_payload tests.test_dashboard.DashboardTests.test_build_position_details_returns_empty_list_for_missing_payload -v`

Expected: FAIL with "cannot import name 'build_position_details'"

- [ ] **Step 3: Implement the position details helper function**

Add to `src/momentum_alpha/dashboard.py` after line 166 (after `_parse_numeric` function):

```python
from decimal import Decimal


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def build_position_details(position_snapshot: dict) -> list[dict]:
    """Extract position details with leg breakdown from position snapshot payload."""
    payload = position_snapshot.get("payload") or {}
    positions = payload.get("positions") or {}
    if not positions:
        return []

    details: list[dict] = []
    for symbol, position in positions.items():
        legs = position.get("legs") or []
        if not legs:
            continue

        total_quantity = Decimal("0")
        weighted_sum = Decimal("0")
        stop_price = _parse_decimal(position.get("stop_price")) or Decimal("0")
        leg_info: list[dict] = []

        for leg in legs:
            qty = _parse_decimal(leg.get("quantity")) or Decimal("0")
            entry = _parse_decimal(leg.get("entry_price")) or Decimal("0")
            total_quantity += qty
            weighted_sum += qty * entry
            leg_info.append({
                "type": leg.get("leg_type") or "unknown",
                "time": leg.get("opened_at") or "",
            })

        avg_entry = weighted_sum / total_quantity if total_quantity > 0 else Decimal("0")
        risk = total_quantity * (avg_entry - stop_price)

        details.append({
            "symbol": symbol,
            "direction": "LONG",
            "total_quantity": str(total_quantity),
            "entry_price": f"{avg_entry:.2f}",
            "stop_price": str(stop_price),
            "risk": f"{risk:.2f}",
            "legs": leg_info,
        })

    return details
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_extracts_legs_from_payload tests.test_dashboard.DashboardTests.test_build_position_details_returns_empty_list_for_missing_payload -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add build_position_details helper for position card rendering"
```

---

### Task 2: Add Trade History Table Rendering

**Files:**
- Modify: `src/momentum_alpha/dashboard.py` (add after `build_position_details`)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test for trade history table rendering**

Add to `tests/test_dashboard.py`:

```python
    def test_render_trade_history_table_generates_html_rows(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        orders = [
            {
                "timestamp": "2026-04-15T09:15:23+00:00",
                "symbol": "BTCUSDT",
                "action_type": "base_entry",
                "side": "BUY",
                "quantity": 0.015,
                "order_status": "FILLED",
            },
            {
                "timestamp": "2026-04-15T08:30:15+00:00",
                "symbol": "ETHUSDT",
                "action_type": "add_on_entry",
                "side": "BUY",
                "quantity": 0.12,
                "order_status": "NEW",
            },
        ]

        html = render_trade_history_table(orders)

        self.assertIn("BTCUSDT", html)
        self.assertIn("ETHUSDT", html)
        self.assertIn("base_entry", html)
        self.assertIn("add_on_entry", html)
        self.assertIn("09:15:23", html)
        self.assertIn("08:30:15", html)
        self.assertIn("0.015", html)
        self.assertIn("0.12", html)
        self.assertIn("FILLED", html)
        self.assertIn("NEW", html)

    def test_render_trade_history_table_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_trade_history_table

        html = render_trade_history_table([])
        self.assertIn("No orders", html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_render_trade_history_table_generates_html_rows tests.test_dashboard.DashboardTests.test_render_trade_history_table_shows_empty_message -v`

Expected: FAIL with "cannot import name 'render_trade_history_table'"

- [ ] **Step 3: Implement the trade history table renderer**

Add to `src/momentum_alpha/dashboard.py` after `build_position_details`:

```python
def render_trade_history_table(orders: list[dict]) -> str:
    """Render HTML table for trade history."""
    if not orders:
        return "<div class='trade-history-empty'>No orders</div>"

    rows = ""
    for order in orders[:10]:
        timestamp = order.get("timestamp") or ""
        time_str = timestamp[11:19] if len(timestamp) >= 19 else timestamp
        symbol = escape(str(order.get("symbol") or "-"))
        action = escape(str(order.get("action_type") or "-"))
        side = order.get("side") or "-"
        side_class = "side-buy" if side == "BUY" else "side-sell"
        qty = order.get("quantity") or 0
        status = order.get("order_status") or "-"
        status_class = "status-filled" if status == "FILLED" else "status-pending"

        rows += (
            f"<div class='trade-row'>"
            f"<span class='trade-time'>{escape(time_str)}</span>"
            f"<span class='trade-symbol'>{symbol}</span>"
            f"<span class='trade-action'>{action}</span>"
            f"<span class='trade-side {side_class}'>{escape(side)}</span>"
            f"<span class='trade-qty'>{qty}</span>"
            f"<span class='trade-status {status_class}'>{escape(status)}</span>"
            f"</div>"
        )

    return f"<div class='trade-history'>{rows}</div>"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_render_trade_history_table_generates_html_rows tests.test_dashboard.DashboardTests.test_render_trade_history_table_shows_empty_message -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add render_trade_history_table for trade history display"
```

---

### Task 3: Add Strategy Config Extraction

**Files:**
- Modify: `src/momentum_alpha/dashboard.py` (add after `render_trade_history_table`)
- Modify: `src/momentum_alpha/dashboard.py` (modify `load_dashboard_snapshot` signature)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test for strategy config**

Add to `tests/test_dashboard.py`:

```python
    def test_build_strategy_config_extracts_from_runtime_config(self) -> None:
        from momentum_alpha.dashboard import build_strategy_config

        config = build_strategy_config(
            stop_budget_usdt="10",
            entry_start_hour_utc=1,
            entry_end_hour_utc=23,
            testnet=True,
            submit_orders=False,
        )

        self.assertEqual(config["stop_budget_usdt"], "10")
        self.assertEqual(config["entry_window"], "01:00-23:00 UTC")
        self.assertEqual(config["testnet"], True)
        self.assertEqual(config["submit_orders"], False)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_build_strategy_config_extracts_from_runtime_config -v`

Expected: FAIL with "cannot import name 'build_strategy_config'"

- [ ] **Step 3: Implement the strategy config builder**

Add to `src/momentum_alpha/dashboard.py` after `render_trade_history_table`:

```python
def build_strategy_config(
    *,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> dict:
    """Build strategy config dict for display."""
    return {
        "stop_budget_usdt": stop_budget_usdt or "n/a",
        "entry_window": f"{entry_start_hour_utc:02d}:00-{entry_end_hour_utc:02d}:00 UTC",
        "testnet": testnet,
        "submit_orders": submit_orders,
    }
```

- [ ] **Step 4: Run test to verify it passes**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_build_strategy_config_extracts_from_runtime_config -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add build_strategy_config for strategy parameters display"
```

---

### Task 4: Add Position Card Rendering

**Files:**
- Modify: `src/momentum_alpha/dashboard.py` (add after `build_strategy_config`)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test for position card rendering**

Add to `tests/test_dashboard.py`:

```python
    def test_render_position_cards_generates_html(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        positions = [
            {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "total_quantity": "0.015",
                "entry_price": "82166.67",
                "stop_price": "81000",
                "risk": "17.50",
                "legs": [
                    {"type": "base", "time": "2026-04-15T09:15:00+00:00"},
                    {"type": "add_on", "time": "2026-04-15T10:00:00+00:00"},
                ],
            }
        ]

        html = render_position_cards(positions)

        self.assertIn("BTCUSDT", html)
        self.assertIn("LONG", html)
        self.assertIn("0.015", html)
        self.assertIn("82166.67", html)
        self.assertIn("81000", html)
        self.assertIn("17.50", html)
        self.assertIn("base", html)
        self.assertIn("add_on", html)

    def test_render_position_cards_shows_empty_message(self) -> None:
        from momentum_alpha.dashboard import render_position_cards

        html = render_position_cards([])
        self.assertIn("No positions", html)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_render_position_cards_generates_html tests.test_dashboard.DashboardTests.test_render_position_cards_shows_empty_message -v`

Expected: FAIL with "cannot import name 'render_position_cards'"

- [ ] **Step 3: Implement the position cards renderer**

Add to `src/momentum_alpha/dashboard.py` after `build_strategy_config`:

```python
def render_position_cards(positions: list[dict]) -> str:
    """Render HTML for position detail cards."""
    if not positions:
        return "<div class='positions-empty'>No positions</div>"

    cards = ""
    for pos in positions:
        symbol = escape(str(pos.get("symbol") or "-"))
        direction = escape(str(pos.get("direction") or "LONG"))
        qty = escape(str(pos.get("total_quantity") or "0"))
        entry = escape(str(pos.get("entry_price") or "n/a"))
        stop = escape(str(pos.get("stop_price") or "n/a"))
        risk = escape(str(pos.get("risk") or "0"))
        legs = pos.get("legs") or []

        legs_str = " | ".join(
            f"Leg {i+1}: {escape(str(leg.get('type') or '-'))} · {escape(str((leg.get('time') or '')[:10]))}"
            for i, leg in enumerate(legs)
        ) if legs else "No legs"

        cards += (
            f"<div class='position-card'>"
            f"<div class='position-header'>"
            f"<span class='position-symbol'>{symbol}</span>"
            f"<span class='position-direction'>{direction}</span>"
            f"</div>"
            f"<div class='position-metrics'>"
            f"<div class='position-metric'><span class='metric-label'>Qty</span><span class='metric-value'>{qty}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Entry</span><span class='metric-value'>{entry}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Stop</span><span class='metric-value metric-danger'>{stop}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Risk</span><span class='metric-value'>{risk} USDT</span></div>"
            f"</div>"
            f"<div class='position-legs'>{escape(legs_str)}</div>"
            f"</div>"
        )

    return f"<div class='positions-grid'>{cards}</div>"
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_render_position_cards_generates_html tests.test_dashboard.DashboardTests.test_render_position_cards_shows_empty_message -v`

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add render_position_cards for position details display"
```

---

### Task 5: Restructure HTML Layout with New Sections

**Files:**
- Modify: `src/momentum_alpha/dashboard.py` (replace `render_dashboard_html` function)
- Modify: `src/momentum_alpha/dashboard.py` (update `load_dashboard_snapshot` to include config)
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test for new HTML structure**

Add to `tests/test_dashboard.py`:

```python
    def test_render_dashboard_html_includes_positions_section(self) -> None:
        from momentum_alpha.dashboard import render_dashboard_html

        html = render_dashboard_html({
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 2,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "legs": [{"symbol": "BTCUSDT", "quantity": "0.01", "entry_price": "82000", "stop_price": "81000", "opened_at": "2026-04-15T09:15:00+00:00", "leg_type": "base"}]
                            }
                        }
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_broker_orders": [],
            "recent_account_snapshots": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }, strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": True, "submit_orders": False})

        self.assertIn("POSITIONS", html)
        self.assertIn("TRADE HISTORY", html)
        self.assertIn("STRATEGY CONFIG", html)
        self.assertIn("Stop Budget", html)
        self.assertIn("10", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_includes_positions_section -v`

Expected: FAIL (TypeError: render_dashboard_html() got an unexpected keyword argument 'strategy_config')

- [ ] **Step 3: Update `render_dashboard_html` with new layout and sections**

Modify the `render_dashboard_html` function in `src/momentum_alpha/dashboard.py` (starting at line 455). Key changes:

1. Add `strategy_config: dict | None = None` parameter
2. Call `build_position_details` and `render_position_cards` for positions section
3. Call `render_trade_history_table` for trade history section
4. Add strategy config HTML rendering
5. Replace `main-layout` grid with stacked sections

Add these CSS rules inside the `<style>` block:

```css
.positions-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.position-card { background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border-left: 3px solid var(--success); }
.position-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.position-symbol { font-weight: 700; color: var(--accent); }
.position-direction { font-size: 0.75rem; color: var(--fg-muted); }
.position-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 0.8rem; }
.position-metric { text-align: center; }
.metric-danger { color: var(--danger); }
.position-legs { margin-top: 8px; font-size: 0.7rem; color: var(--fg-muted); }
.positions-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
.trade-history { max-height: 200px; overflow-y: auto; }
.trade-history-empty { color: var(--fg-muted); text-align: center; padding: 20px; }
.trade-row { display: grid; grid-template-columns: 80px 100px 100px 60px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }
.trade-row:last-child { border-bottom: none; }
.trade-time { color: var(--fg-muted); }
.trade-symbol { color: var(--accent); font-weight: 500; }
.side-buy { color: var(--success); }
.side-sell { color: var(--danger); }
.status-filled { color: var(--success); }
.status-pending { color: var(--warning); }
.section-header { font-size: 0.7rem; color: var(--accent); padding: 4px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.1em; }
.config-panel { background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; font-size: 0.8rem; }
.config-row { display: flex; justify-content: space-between; padding: 4px 0; }
.config-label { color: var(--fg-muted); }
.config-value-true { color: var(--warning); }
.config-value-false { color: var(--fg-muted); }
.dashboard-section { margin-bottom: 20px; padding: 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); }
.charts-row { display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }
.chart-card { background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }
.decision-row { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
.decision-half { background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }
.bottom-row { display: grid; grid-template-columns: 200px 1fr 1fr; gap: 16px; }
.bottom-col { }
@media (max-width: 1200px) {
  .charts-row { grid-template-columns: 1fr; }
  .decision-row { grid-template-columns: 1fr; }
  .bottom-row { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .positions-grid { grid-template-columns: 1fr; }
  .trade-row { grid-template-columns: 60px 80px 80px 50px 60px; font-size: 0.7rem; }
}
```

Replace the `main-layout` HTML section with this structure:

```html
    <section class="dashboard-section">
      <div class="section-header">POSITIONS</div>
      {position_cards_html}
    </section>
    <section class="dashboard-section">
      <div class="section-header">ACCOUNT METRICS</div>
      <div class="charts-row">
        <div class="chart-card">{equity_chart}</div>
        <div class="chart-card">{wallet_chart}</div>
        <div class="chart-card">{pnl_chart}</div>
      </div>
    </section>
    <section class="dashboard-section decision-row">
      <div class="decision-half">
        <div class="section-header">LATEST DECISION</div>
        {decision_html}
      </div>
      <div class="decision-half">
        <div class="section-header">LEADER ROTATION</div>
        {timeline_chart}
      </div>
    </section>
    <section class="dashboard-section">
      <div class="section-header">TRADE HISTORY</div>
      {trade_history_html}
    </section>
    <section class="dashboard-section bottom-row">
      <div class="bottom-col">
        <div class="section-header">STRATEGY CONFIG</div>
        {config_html}
      </div>
      <div class="bottom-col">
        <div class="section-header">SYSTEM HEALTH</div>
        {health_items_html}
      </div>
      <div class="bottom-col">
        <div class="section-header">RECENT EVENTS</div>
        {recent_events_html}
      </div>
    </section>
```

Generate HTML strings before the f-string:

```python
    # Build position cards
    latest_position_snapshot = runtime.get("latest_position_snapshot") or {}
    position_details = build_position_details(latest_position_snapshot)
    position_cards_html = render_position_cards(position_details)

    # Build trade history
    broker_orders = snapshot.get("recent_broker_orders") or []
    trade_history_html = render_trade_history_table(broker_orders)

    # Build strategy config
    config = strategy_config or {}
    config_html = (
        f"<div class='config-panel'>"
        f"<div class='config-row'><span class='config-label'>Stop Budget</span><span>{escape(str(config.get('stop_budget_usdt') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Entry Window</span><span>{escape(str(config.get('entry_window') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Testnet</span><span class='{'config-value-true' if config.get('testnet') else 'config-value-false'}'>{'Yes' if config.get('testnet') else 'No'}</span></div>"
        f"</div>"
    )
```

```css
.positions-grid { display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }
.position-card { background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border-left: 3px solid var(--success); }
.position-header { display: flex; justify-content: space-between; margin-bottom: 10px; }
.position-symbol { font-weight: 700; color: var(--accent); }
.position-direction { font-size: 0.75rem; color: var(--fg-muted); }
.position-metrics { display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 0.8rem; }
.position-metric { text-align: center; }
.position-legs { margin-top: 8px; font-size: 0.7rem; color: var(--fg-muted); }
.trade-history { max-height: 200px; overflow-y: auto; }
.trade-row { display: grid; grid-template-columns: 80px 100px 100px 60px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }
.trade-row:last-child { border-bottom: none; }
.side-buy { color: var(--success); }
.side-sell { color: var(--danger); }
.status-filled { color: var(--success); }
.status-pending { color: var(--warning); }
.config-panel { background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; font-size: 0.8rem; }
.config-row { display: flex; justify-content: space-between; padding: 4px 0; }
.config-label { color: var(--fg-muted); }
.section-header { font-size: 0.7rem; color: var(--accent); padding: 4px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.1em; }
```

- [ ] **Step 4: Update `load_dashboard_snapshot` to accept and pass strategy config**

Modify `load_dashboard_snapshot` signature in `src/momentum_alpha/dashboard.py` (line ~219) to accept optional strategy config parameters:

```python
def load_dashboard_snapshot(
    *,
    now: datetime,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    runtime_db_file: Path | None = None,
    recent_limit: int = 20,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> dict:
```

Add `strategy_config` to the returned dict (at the end, before the closing brace around line 307):

```python
        "strategy_config": build_strategy_config(
            stop_budget_usdt=stop_budget_usdt,
            entry_start_hour_utc=entry_start_hour_utc,
            entry_end_hour_utc=entry_end_hour_utc,
            testnet=testnet,
            submit_orders=submit_orders,
        ),
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `python -m unittest tests.test_dashboard -v`

Expected: All tests PASS

- [ ] **Step 6: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: restructure dashboard with sections, position details, trade history"
```

---

### Task 6: Update Main Entry Point to Pass Strategy Config

**Files:**
- Modify: `src/momentum_alpha/main.py` (update dashboard command)
- Test: `tests/test_main.py`

- [ ] **Step 1: Check how main.py invokes dashboard**

Run: `grep -n "run_dashboard_server" src/momentum_alpha/main.py`

Expected output shows the call location.

- [ ] **Step 2: Update `run_dashboard_server` signature in dashboard.py**

Modify `run_dashboard_server` in `src/momentum_alpha/dashboard.py` (line ~1077) to accept strategy config parameters:

```python
def run_dashboard_server(
    *,
    host: str,
    port: int,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    runtime_db_file: Path | None = None,
    now_provider=None,
    server_factory=ThreadingHTTPServer,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> int:
```

Pass these parameters to `load_dashboard_snapshot` call inside `DashboardHandler.do_GET`:

```python
            snapshot = load_dashboard_snapshot(
                now=now_provider().astimezone(),
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                runtime_db_file=runtime_db_file,
                stop_budget_usdt=stop_budget_usdt,
                entry_start_hour_utc=entry_start_hour_utc,
                entry_end_hour_utc=entry_end_hour_utc,
                testnet=testnet,
                submit_orders=submit_orders,
            )
```

- [ ] **Step 3: Update main.py to pass strategy config to dashboard**

Find the dashboard command section in `src/momentum_alpha/main.py`. Add config extraction and pass to `run_dashboard_server`:

```python
    stop_budget = os.environ.get("STOP_BUDGET_USDT", "10")
    testnet = os.environ.get("BINANCE_USE_TESTNET", "0") == "1"
    submit_orders = os.environ.get("SUBMIT_ORDERS", "0") == "1"

    return run_dashboard_server(
        host=args.host,
        port=args.port,
        state_file=state_file,
        poll_log_file=poll_log_file,
        user_stream_log_file=user_stream_log_file,
        audit_log_file=audit_log_file,
        runtime_db_file=runtime_db_file,
        stop_budget_usdt=stop_budget,
        testnet=testnet,
        submit_orders=submit_orders,
    )
```

- [ ] **Step 4: Run all tests**

Run: `python -m unittest discover -s tests -v`

Expected: All tests PASS

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/main.py src/momentum_alpha/dashboard.py
git commit -m "feat: pass strategy config to dashboard from main"
```

---

### Task 7: Final Verification and Cleanup

- [ ] **Step 1: Run full test suite**

Run: `python -m unittest discover -s tests -v`

Expected: All tests PASS

- [ ] **Step 2: Start dashboard locally and verify UI**

Run: `python3 -m momentum_alpha.main dashboard --state-file ./var/state.json --poll-log-file ./var/log/momentum-alpha.log --user-stream-log-file ./var/log/momentum-alpha-user-stream.log --runtime-db-file ./var/runtime.db`

Open: http://localhost:8080

Verify:
- [ ] Positions section shows position cards with entry/stop/risk
- [ ] Trade History section shows broker orders table
- [ ] Strategy Config section shows stop budget and entry window
- [ ] All existing metrics still visible
- [ ] Auto-refresh (5s) works

- [ ] **Step 3: Final commit**

```bash
git add -A
git commit -m "feat: complete dashboard redesign with sections, positions, trade history"
```

---

## Success Criteria Checklist

- [ ] All existing dashboard tests pass
- [ ] New helper functions tested
- [ ] Positions section displays entry price, stop price, quantity, risk
- [ ] Trade history table shows last 10 broker orders
- [ ] Strategy config visible without clicking
- [ ] Page responsive on mobile (sections stack vertically)
- [ ] Auto-refresh (5s) continues to work
