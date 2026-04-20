# Dashboard Three-Room Architecture Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reorganize the Momentum Alpha dashboard from four implementation-oriented tabs into three trader workspaces: `实时监控室`, `复盘室`, and `系统状态室`.

**Architecture:** Keep the current single-route, server-rendered Python dashboard in `src/momentum_alpha/dashboard.py`. Replace tab normalization/navigation/rendering with room normalization/navigation/rendering while keeping legacy `active_tab` and `?tab=` compatibility during rollout. Split the old Execution content by use: live execution pulse in `实时监控室`, execution quality analysis in `复盘室`, and execution data freshness in `系统状态室`.

**Tech Stack:** Python 3.12, standard-library `unittest`, server-rendered HTML/CSS/JS in `src/momentum_alpha/dashboard.py`, SQLite-backed runtime data via existing `runtime_store` helpers.

---

## File Structure

- Modify: `src/momentum_alpha/dashboard.py`
  - Replace top-level dashboard tab constants and navigation helpers with room equivalents.
  - Keep compatibility wrappers for `active_tab` call sites and `?tab=` URLs.
  - Add live-room account-risk and core-line rendering helpers.
  - Replace the `overview`, `execution`, and `performance` tab renderers with `live`, `review`, and `system` room renderers.
  - Update client-side refresh selectors from tab-specific data attributes to room-specific attributes.
- Modify: `tests/test_dashboard.py`
  - Update tab navigation tests to room navigation tests.
  - Update default dashboard assertions from `overview` to `live`.
  - Update Execution and Performance assertions to the new split behavior.
  - Keep targeted legacy compatibility tests for `active_tab` and `?tab=`.
- Create/modify only this implementation plan in `docs/superpowers/plans/2026-04-20-dashboard-three-room-architecture.md`.

Do not create new frontend packages, database tables, or route families for this change.

---

### Task 1: Introduce Room Normalization And Navigation Compatibility

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for room normalization and room links**

In `tests/test_dashboard.py`, replace the existing tab normalization/link tests near the top of `DashboardTests` with these tests. Keep `_build_tabbed_snapshot()` unchanged for now.

```python
def test_normalize_dashboard_room_defaults_to_live_and_maps_legacy_tabs(self) -> None:
    from momentum_alpha.dashboard import normalize_dashboard_room

    self.assertEqual(normalize_dashboard_room(None), "live")
    self.assertEqual(normalize_dashboard_room(""), "live")
    self.assertEqual(normalize_dashboard_room("unknown"), "live")
    self.assertEqual(normalize_dashboard_room("live"), "live")
    self.assertEqual(normalize_dashboard_room("review"), "review")
    self.assertEqual(normalize_dashboard_room("system"), "system")
    self.assertEqual(normalize_dashboard_room("overview"), "live")
    self.assertEqual(normalize_dashboard_room("execution"), "live")
    self.assertEqual(normalize_dashboard_room("performance"), "review")

def test_render_dashboard_room_nav_uses_relative_room_links(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_room_nav

    html = render_dashboard_room_nav("live", account_range_key="1W")

    self.assertIn('href="?room=live&range=1W"', html)
    self.assertIn('href="?room=review&range=1W"', html)
    self.assertIn('href="?room=system&range=1W"', html)
    self.assertIn("实时监控室", html)
    self.assertIn("复盘室", html)
    self.assertIn("系统状态室", html)
    self.assertNotIn('href="?tab=', html)
    self.assertNotIn('href="/?room=live"', html)

def test_render_dashboard_html_defaults_to_live_room_and_renders_room_links(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), account_range_key="1W")

    self.assertIn('?room=live&range=1W', html)
    self.assertIn('?room=review&range=1W', html)
    self.assertIn('?room=system&range=1W', html)
    self.assertIn('dashboard-tab is-active', html)
    self.assertIn('data-dashboard-room-content="live"', html)
    self.assertIn("实时监控室", html)
    self.assertIn("复盘室", html)
    self.assertIn("系统状态室", html)
    self.assertNotIn('?tab=overview&range=1W', html)
    self.assertNotIn("Execution</a>", html)
    self.assertNotIn("Performance</a>", html)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_normalize_dashboard_room_defaults_to_live_and_maps_legacy_tabs \
  tests.test_dashboard.DashboardTests.test_render_dashboard_room_nav_uses_relative_room_links \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_defaults_to_live_room_and_renders_room_links \
  -v
```

Expected: FAIL with import errors for `normalize_dashboard_room` and `render_dashboard_room_nav`, and old `?tab=` links still present.

- [ ] **Step 3: Add room constants, normalization, and href helpers**

In `src/momentum_alpha/dashboard.py`, replace the current `DASHBOARD_TABS` constant and `_build_dashboard_tab_href()` helper near the top with:

```python
DASHBOARD_ROOMS = ("live", "review", "system")
LEGACY_DASHBOARD_TAB_TO_ROOM = {
    "overview": "live",
    "execution": "live",
    "performance": "review",
    "system": "system",
}


def normalize_dashboard_room(value: str | None) -> str:
    room = (value or "").strip().lower()
    if room in DASHBOARD_ROOMS:
        return room
    return LEGACY_DASHBOARD_TAB_TO_ROOM.get(room, "live")


def normalize_dashboard_tab(value: str | None) -> str:
    """Backward-compatible wrapper for old callers that still pass tab names."""
    room = normalize_dashboard_room(value)
    return {"live": "overview", "review": "performance", "system": "system"}[room]


def _build_dashboard_room_href(*, room: str, account_range_key: str) -> str:
    return f"?{urlencode({'room': normalize_dashboard_room(room), 'range': normalize_account_range(account_range_key)})}"


def _build_dashboard_tab_href(*, tab: str, account_range_key: str) -> str:
    """Backward-compatible link helper for old internal call sites during migration."""
    return _build_dashboard_room_href(room=normalize_dashboard_room(tab), account_range_key=account_range_key)
```

- [ ] **Step 4: Replace the tab bar renderer with a room nav renderer**

Replace `render_dashboard_tab_bar()` in `src/momentum_alpha/dashboard.py` with:

```python
def render_dashboard_room_nav(active_room: str, *, account_range_key: str = "1D") -> str:
    active_room = normalize_dashboard_room(active_room)
    labels = {
        "live": "实时监控室",
        "review": "复盘室",
        "system": "系统状态室",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if room == active_room else ""}" '
            f'data-dashboard-room="{room}" href="{_build_dashboard_room_href(room=room, account_range_key=account_range_key)}">{escape(labels[room])}</a>'
        )
        for room in DASHBOARD_ROOMS
    )
    return (
        '<nav class="dashboard-tabs" data-dashboard-section="room-nav" aria-label="Dashboard rooms">'
        f"{links}"
        "</nav>"
    )


def render_dashboard_tab_bar(active_tab: str, *, account_range_key: str = "1D") -> str:
    """Backward-compatible wrapper for tests or callers not yet migrated."""
    return render_dashboard_room_nav(normalize_dashboard_room(active_tab), account_range_key=account_range_key)
```

- [ ] **Step 5: Update the shell to expose active room data attributes**

Change `render_dashboard_shell()` signature and content in `src/momentum_alpha/dashboard.py`:

```python
def render_dashboard_shell(
    *,
    health_status: str,
    latest_update_display: str | None,
    execution_mode_label: str,
    execution_mode_state: str,
    active_room: str,
    room_nav_html: str,
    room_content_html: str,
) -> str:
    return (
        "<body>"
        "<div class='app'>"
        "<div class='app-shell'>"
        f"{render_cosmic_identity_panel()}"
        "<header class='header'>"
        "<div class='header-left'>"
        "<div class='logo'>M</div>"
        "<div class='title-group'>"
        "<h1>Momentum Alpha</h1>"
        "<p>Leader Rotation Strategy · Real-time Trading Monitor</p>"
        "</div>"
        "</div>"
        "<div class='header-status' data-dashboard-section='status'>"
        f"<div class='mode-badge {escape(execution_mode_state)}'>{escape(execution_mode_label)}</div>"
        f"<div class='status-badge {'ok' if health_status == 'OK' else 'fail'}'>{escape(health_status)}</div>"
        "</div>"
        "</header>"
        "<div class='toolbar' data-dashboard-section='toolbar'>"
        f"<div class='status-line'>Last update <strong id='last-updated-text'>{escape(format_timestamp_for_display(latest_update_display))}</strong></div>"
        "<div class='status-line'>Auto refresh 5s</div>"
        "<div class='toolbar-spacer'></div>"
        "<button type='button' class='action-button' id='manual-refresh-button'>MANUAL REFRESH</button>"
        "</div>"
        f"{room_nav_html}"
        f"<div class='dashboard-tab-shell' data-dashboard-active-room='{escape(active_room)}'>{room_content_html}</div>"
        "</div>"
        "</div>"
    )
```

- [ ] **Step 6: Run the focused tests and commit**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_normalize_dashboard_room_defaults_to_live_and_maps_legacy_tabs \
  tests.test_dashboard.DashboardTests.test_render_dashboard_room_nav_uses_relative_room_links \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_defaults_to_live_room_and_renders_room_links \
  -v
```

Expected: PASS after later tasks wire `render_dashboard_body()` to rooms. If this task still fails because `render_dashboard_body()` has not been migrated, keep the test failure noted and do not commit until Task 2 completes the wiring.

Commit after the first passing checkpoint:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "refactor: introduce dashboard room navigation"
```

---

### Task 2: Build The Default Live Monitoring Room

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for the account-risk-first live room**

Add these tests to `tests/test_dashboard.py` near the existing dashboard rendering tests:

```python
def test_render_dashboard_html_live_room_is_account_risk_first(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["recent_broker_orders"] = [
        {
            "timestamp": "2026-04-17T00:41:00+00:00",
            "symbol": "BTCUSDT",
            "action_type": "replace_stop_order",
            "order_type": "STOP_MARKET",
            "side": "SELL",
            "order_status": "NEW",
        }
    ]
    snapshot["recent_algo_orders"] = [
        {
            "timestamp": "2026-04-17T00:41:10+00:00",
            "symbol": "BTCUSDT",
            "algo_id": "77",
            "algo_status": "WORKING",
            "order_type": "STOP_MARKET",
            "trigger_price": "81000",
        }
    ]

    html = render_dashboard_html(snapshot, account_range_key="1W")

    self.assertIn('data-dashboard-room-content="live"', html)
    self.assertIn("实时监控室", html)
    self.assertIn("ACCOUNT RISK", html)
    self.assertIn("OPEN RISK / EQUITY", html)
    self.assertIn("Available Balance", html)
    self.assertIn("Margin Usage", html)
    self.assertIn("CORE LIVE LINES", html)
    self.assertIn("Account Equity", html)
    self.assertIn("Margin Usage %", html)
    self.assertIn("Position Count", html)
    self.assertIn("ACTIVE POSITIONS", html)
    self.assertIn("ORDER FLOW", html)
    self.assertIn("Latest Broker Action", html)
    self.assertIn("replace_stop_order", html)
    self.assertIn("Latest Stop Order", html)
    self.assertIn("WORKING", html)
    self.assertLess(html.index("ACCOUNT RISK"), html.index("CORE LIVE LINES"))
    self.assertLess(html.index("CORE LIVE LINES"), html.index("ACTIVE POSITIONS"))
    self.assertLess(html.index("ACTIVE POSITIONS"), html.index("ORDER FLOW"))
    self.assertNotIn('data-dashboard-room-content="review"', html)
    self.assertNotIn("Closed Trade Detail", html)
    self.assertNotIn("SYSTEM OPERATIONS", html)

def test_render_dashboard_html_legacy_execution_tab_maps_to_live_room(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="execution")

    self.assertIn('data-dashboard-room-content="live"', html)
    self.assertIn("实时监控室", html)
    self.assertIn("ORDER FLOW", html)
    self.assertNotIn('data-dashboard-room-content="execution"', html)
    self.assertNotIn("EXECUTION QUALITY", html)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_live_room_is_account_risk_first \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_legacy_execution_tab_maps_to_live_room \
  -v
```

Expected: FAIL because the dashboard still renders `overview`/`execution` tab content instead of one live room.

- [ ] **Step 3: Add live account risk and core line helpers**

Add these helpers in `src/momentum_alpha/dashboard.py` after `_build_account_snapshot_panel()`:

```python
def _build_live_account_risk_panel(
    *,
    trader_metrics: dict[str, dict[str, object | None]],
    account_range_stats: dict[str, float | None],
) -> str:
    account_metrics = trader_metrics["account"]
    return (
        "<section class='dashboard-section live-account-risk-panel'>"
        "<div class='section-header'>ACCOUNT RISK</div>"
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Equity</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_equity')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Available Balance</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_available_balance')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Unrealized PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_unrealized_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Today Net PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('today_net_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Margin Usage</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('margin_usage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>OPEN RISK / EQUITY</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('open_risk_pct')))}</div><div class='decision-support'>{escape(_format_metric(account_metrics.get('open_risk')))} USDT at risk</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Drawdown</div><div class='decision-value'>{escape(_format_metric(account_range_stats.get('drawdown_abs'), signed=True))}</div><div class='decision-support'>{escape(_format_pct_value(account_range_stats.get('drawdown_pct'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Positions / Orders</div><div class='decision-value'>{escape(str(account_metrics.get('current_positions') or 0))} / {escape(str(account_metrics.get('current_orders') or 0))}</div></div>"
        "</div>"
        "</section>"
    )


def _build_live_core_lines_panel(account_points: list[dict]) -> str:
    charts = (
        ("Account Equity", "equity", "#4cc9f0"),
        ("Margin Usage %", "margin_usage_pct", "#ff8c42"),
        ("Position Count", "position_count", "#36d98a"),
    )
    chart_cards = "".join(
        (
            "<div class='chart-card live-core-line-card'>"
            f"<div class='section-header'>{escape(label)}</div>"
            f"{_render_line_chart_svg(points=account_points, value_key=value_key, stroke=color, fill=color)}"
            "</div>"
        )
        for label, value_key, color in charts
    )
    return (
        "<section class='dashboard-section live-core-lines-panel'>"
        "<div class='section-header'>CORE LIVE LINES</div>"
        f"<div class='analytics-grid'>{chart_cards}</div>"
        "</section>"
    )
```

- [ ] **Step 4: Replace the overview renderer with `render_dashboard_live_room()`**

Replace `render_dashboard_overview_tab()` and remove `render_dashboard_execution_tab()` from the room dispatch path. Add:

```python
def render_dashboard_live_room(
    *,
    account_risk_html: str,
    core_lines_html: str,
    hero_html: str,
    positions_html: str,
    execution_flow_html: str,
    home_command_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        f"{account_risk_html}"
        f"{core_lines_html}"
        f"{hero_html}"
        "<section class='dashboard-section active-positions-panel'>"
        "<div class='section-header'>ACTIVE POSITIONS</div>"
        f"{positions_html}"
        "</section>"
        f"{execution_flow_html}"
        f"{home_command_html}"
        "</div>"
    )
```

- [ ] **Step 5: Wire `render_dashboard_body()` to rooms**

Update `render_dashboard_document()`, `render_dashboard_body()`, and `render_dashboard_html()` signatures so `active_room` is primary and `active_tab` remains a compatibility alias:

```python
def render_dashboard_document(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    account_range_key: str = "1D",
) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        f"{render_dashboard_head()}\n"
        f"{render_dashboard_body(snapshot, strategy_config=strategy_config, active_room=active_room, active_tab=active_tab, account_range_key=account_range_key)}"
        f"{render_dashboard_scripts()}"
    )
```

At the top of `render_dashboard_body()`:

```python
active_room = normalize_dashboard_room(active_room if active_room is not None else active_tab)
account_range_key = normalize_account_range(account_range_key)
```

After `trader_metrics` and `account_range_stats` are built, add:

```python
account_risk_html = _build_live_account_risk_panel(
    trader_metrics=trader_metrics,
    account_range_stats=account_range_stats,
)
core_lines_html = _build_live_core_lines_panel(timeseries["account"])
```

Replace the tab dispatch at the end of `render_dashboard_body()` with room dispatch:

```python
room_nav_html = render_dashboard_room_nav(active_room, account_range_key=account_range_key)
room_content_html = {
    "live": render_dashboard_live_room(
        account_risk_html=account_risk_html,
        core_lines_html=core_lines_html,
        hero_html=hero_html,
        positions_html=render_position_cards(position_details),
        execution_flow_html=execution_flow_html,
        home_command_html=home_command_html,
    ),
    "review": render_dashboard_review_room(
        performance_summary_html=performance_summary_html,
        round_trip_detail_html=closed_trades_html,
        leg_count_aggregate_html=leg_count_aggregate_html,
        leg_index_aggregate_html=leg_index_aggregate_html,
        stop_slippage_html=stop_slippage_html,
    ),
    "system": render_dashboard_system_room(
        diagnostics_html=diagnostics_html,
        warning_list_html=warning_list_html,
        config_html=config_html,
        source_html=source_html,
        health_items_html=health_items_html,
        recent_events_html=recent_events_html,
    ),
}[active_room]
```

Update the `render_dashboard_shell()` call to pass `active_room`, `room_nav_html`, and `room_content_html`.

- [ ] **Step 6: Update Home Command links away from Execution/Performance**

In `_build_overview_home_command()`, replace the `action_cards` list with:

```python
action_cards = [
    (
        "复盘室",
        "Review closed trades, leg contribution, slippage, and strategy parameters.",
        _build_dashboard_room_href(room="review", account_range_key=account_range_key),
    ),
    (
        "系统状态室",
        "Check freshness, warnings, configuration, and runtime health.",
        _build_dashboard_room_href(room="system", account_range_key=account_range_key),
    ),
]
```

- [ ] **Step 7: Run focused live room tests and commit**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_live_room_is_account_risk_first \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_legacy_execution_tab_maps_to_live_room \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_defaults_to_live_room_and_renders_room_links \
  -v
```

Expected: PASS.

Commit:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: render live monitoring room as dashboard home"
```

---

### Task 3: Build The Review Room Around Closed Trade Detail

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for the review room**

Add these tests to `tests/test_dashboard.py`:

```python
def test_render_dashboard_html_review_room_is_closed_trade_detail_first(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["recent_trade_round_trips"][0]["exit_reason"] = "stop_loss"
    snapshot["recent_trade_round_trips"][0]["payload"] = {
        "leg_count": 2,
        "peak_cumulative_risk": "18.50",
        "legs": [
            {
                "leg_index": 1,
                "leg_type": "base",
                "opened_at": "2026-04-17T00:20:00+00:00",
                "quantity": "0.01",
                "entry_price": "82000",
                "stop_price_at_entry": "81000",
                "leg_risk": "10.00",
                "cumulative_risk_after_leg": "10.00",
                "gross_pnl_contribution": "20.00",
                "fee_share": "0.15",
                "net_pnl_contribution": "19.85",
            },
            {
                "leg_index": 2,
                "leg_type": "add_on",
                "opened_at": "2026-04-17T00:35:00+00:00",
                "quantity": "0.01",
                "entry_price": "82500",
                "stop_price_at_entry": "81500",
                "leg_risk": "10.00",
                "cumulative_risk_after_leg": "20.00",
                "gross_pnl_contribution": "5.00",
                "fee_share": "0.15",
                "net_pnl_contribution": "4.85",
            },
        ],
    }

    html = render_dashboard_html(snapshot, active_room="review")

    self.assertIn('data-dashboard-room-content="review"', html)
    self.assertIn("复盘室", html)
    self.assertIn("Closed Trade Detail", html)
    self.assertIn("BTCUSDT", html)
    self.assertIn("STOP LOSS", html)
    self.assertIn("round-trip-details", html)
    self.assertIn("Leg #", html)
    self.assertIn("Stop At Entry", html)
    self.assertIn("Cum Risk", html)
    self.assertIn("Fee Share", html)
    self.assertIn("Net Contribution", html)
    self.assertIn("By Total Leg Count", html)
    self.assertIn("By Leg Index", html)
    self.assertIn("STOP SLIPPAGE ANALYSIS", html)
    self.assertLess(html.index("Closed Trade Detail"), html.index("By Total Leg Count"))
    self.assertLess(html.index("Closed Trade Detail"), html.index("STOP SLIPPAGE ANALYSIS"))
    self.assertNotIn("ACTIVE POSITIONS", html)
    self.assertNotIn("ORDER FLOW", html)
    self.assertNotIn("ACCOUNT METRICS", html)

def test_render_dashboard_html_legacy_performance_tab_maps_to_review_room(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="performance")

    self.assertIn('data-dashboard-room-content="review"', html)
    self.assertIn("Closed Trade Detail", html)
    self.assertNotIn('data-dashboard-tab-content="performance"', html)
```

- [ ] **Step 2: Run the focused tests to verify failure**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_review_room_is_closed_trade_detail_first \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_legacy_performance_tab_maps_to_review_room \
  -v
```

Expected: FAIL until `render_dashboard_review_room()` exists and the dispatch is wired.

- [ ] **Step 3: Replace the performance renderer with `render_dashboard_review_room()`**

Replace `render_dashboard_performance_tab()` with:

```python
def render_dashboard_review_room(
    *,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="review">'
        "<section class='section-frame' data-collapsible-section='review'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>复盘室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Closed Trade Detail is the primary review surface; aggregates follow the ledger.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Complete Trade Summary (all closed trades)</div>"
        f"{performance_summary_html}"
        "</div>"
        "<div class='chart-card review-ledger-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Closed Trade Detail</div>"
        f"<div class='table-scroll'>{round_trip_detail_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Total Leg Count</div>"
        f"<div class='table-scroll'>{leg_count_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Leg Index</div>"
        f"<div class='table-scroll'>{leg_index_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div class='section-header' style='margin-bottom:10px;'>STOP SLIPPAGE ANALYSIS</div>"
        f"<div class='table-scroll'>{stop_slippage_html}</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )
```

Do not pass `account_metrics_panel_html` into this renderer. Account trend charts belong in the live room.

- [ ] **Step 4: Remove review room dependency on the old Account Metrics section**

In `render_dashboard_body()`, keep `account_metrics_panel_html = _build_account_metrics_panel(...)` only if it is still needed by tests or a compatibility path. The preferred implementation after Task 2 is to remove it from the review room dispatch.

If `account_metrics_panel_html` is no longer used anywhere, delete the local variable from `render_dashboard_body()` and leave `_build_account_metrics_panel()` in the file for possible future use only if existing JS/tests still rely on it. Do not delete `_build_account_metrics_panel()` in this task.

- [ ] **Step 5: Update old Execution/Performance tests to new room behavior**

Change old tests that call `active_tab="execution"` and expect full `EXECUTION QUALITY` into one of these two patterns:

```python
live_html = render_dashboard_html(snapshot, active_room="live")
review_html = render_dashboard_html(snapshot, active_room="review")

self.assertIn("ORDER FLOW", live_html)
self.assertIn("Latest Fill", live_html)
self.assertNotIn("STOP SLIPPAGE ANALYSIS", live_html)

self.assertIn("STOP SLIPPAGE ANALYSIS", review_html)
self.assertIn("Avg Slippage", review_html)
self.assertIn("Fee Total", review_html)
self.assertNotIn("ORDER FLOW", review_html)
```

Change old tests that call `active_tab="performance"` to prefer `active_room="review"`, except for one compatibility test that intentionally proves `active_tab="performance"` maps to review.

- [ ] **Step 6: Run focused review tests and commit**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_review_room_is_closed_trade_detail_first \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_legacy_performance_tab_maps_to_review_room \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_surfaces_margin_usage_controls_and_leg_analytics \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_includes_closed_trades_and_stop_slippage_sections \
  -v
```

Expected: PASS after updating the older tests to the new room semantics.

Commit:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: center review room on closed trades"
```

---

### Task 4: Preserve System Status Room Responsibilities

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for the system room boundary**

Add this test to `tests/test_dashboard.py`:

```python
def test_render_dashboard_html_system_room_preserves_runtime_diagnostics_only(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["health"] = {
        "overall_status": "DEGRADED",
        "items": [{"name": "poll", "status": "WARN", "message": "lagging"}],
    }
    snapshot["runtime"]["latest_tick_result_timestamp"] = "2026-04-17T01:05:00+00:00"
    snapshot["recent_events"] = [
        {
            "timestamp": "2026-04-17T01:05:00+00:00",
            "event_type": "tick_result",
            "payload": {"symbol": "BTCUSDT"},
            "source": "poll",
        }
    ]
    snapshot["source_counts"] = {"poll": 3, "user-stream": 1}
    snapshot["warnings"] = ["runtime db stale"]

    html = render_dashboard_html(snapshot, active_room="system")

    self.assertIn('data-dashboard-room-content="system"', html)
    self.assertIn("系统状态室", html)
    self.assertIn("SYSTEM DIAGNOSTICS", html)
    self.assertIn("Health Status", html)
    self.assertIn("DEGRADED", html)
    self.assertIn("Data Freshness", html)
    self.assertIn("Warning Count", html)
    self.assertIn("ACTIVE WARNINGS", html)
    self.assertIn("runtime db stale", html)
    self.assertIn("SYSTEM OPERATIONS", html)
    self.assertIn("EVENT SOURCES", html)
    self.assertIn("SYSTEM HEALTH", html)
    self.assertIn("RECENT EVENTS", html)
    self.assertNotIn("ACTIVE POSITIONS", html)
    self.assertNotIn("Closed Trade Detail", html)
    self.assertNotIn("ORDER FLOW", html)
```

- [ ] **Step 2: Run the focused test to verify failure**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_system_room_preserves_runtime_diagnostics_only \
  -v
```

Expected: FAIL until the old system tab renderer is renamed and dispatch is updated to room content attributes.

- [ ] **Step 3: Rename the system renderer**

Replace `render_dashboard_system_tab()` with this function name and first wrapper line:

```python
def render_dashboard_system_room(
    *,
    diagnostics_html: str,
    warning_list_html: str,
    config_html: str,
    source_html: str,
    health_items_html: str,
    recent_events_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="system">'
        "<section class='section-frame' data-collapsible-section='system'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>系统状态室</div>"
        "<button type='button' class='section-toggle' data-section-toggle='system'>Collapse</button>"
        "</div>"
        f"{diagnostics_html}"
        f"{warning_list_html}"
        "<div class='dashboard-section bottom-row section-body'>"
        "<div class='bottom-col'>"
        "<div class='section-header'>SYSTEM OPERATIONS</div>"
        f"{config_html}"
        "<div class='section-header' style='margin-top:12px;'>EVENT SOURCES</div>"
        f"<div class='source-tags'>{source_html}</div>"
        "</div>"
        "<div class='bottom-col'>"
        "<div class='section-header'>SYSTEM HEALTH</div>"
        f"<div class='health-grid'>{health_items_html}</div>"
        "</div>"
        "<div class='bottom-col'>"
        "<div class='section-header'>RECENT EVENTS</div>"
        f"<div class='event-list' style='max-height:200px;overflow-y:auto;'>{recent_events_html}</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )
```

Do not move live account panels, active position panels, closed trade tables, or execution pulse cards into this renderer.

- [ ] **Step 4: Update old system tests to use `active_room="system"`**

For existing tests that assert system diagnostics, update calls like:

```python
html = render_dashboard_html(snapshot, active_tab="system")
```

to:

```python
html = render_dashboard_html(snapshot, active_room="system")
```

Keep one compatibility assertion:

```python
legacy_html = render_dashboard_html(snapshot, active_tab="system")
self.assertIn('data-dashboard-room-content="system"', legacy_html)
```

- [ ] **Step 5: Run focused system tests and commit**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_system_room_preserves_runtime_diagnostics_only \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_system_tab_surfaces_operational_diagnostics \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_includes_health_runtime_and_recent_events \
  -v
```

Expected: PASS after updating older tests to room semantics.

Commit:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "refactor: preserve system diagnostics as status room"
```

---

### Task 5: Update Refresh JavaScript And HTTP Query Parsing

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for room refresh markers and HTTP parsing**

Add this test to `tests/test_dashboard.py`:

```python
def test_render_dashboard_html_refreshes_room_content_and_uses_room_query_state(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), active_room="live")

    self.assertIn("DASHBOARD_SECTION_SELECTORS", html)
    self.assertIn('[data-dashboard-section=\"room-nav\"]', html)
    self.assertIn("[data-dashboard-active-room]", html)
    self.assertIn("dataset.dashboardActiveRoom", html)
    self.assertIn("activeRoom === 'review'", html)
    self.assertIn("window.location.search", html)
    self.assertIn("replaceSectionFromDocument", html)
    self.assertIn("new DOMParser()", html)
    self.assertNotIn("[data-dashboard-active-tab]", html)
    self.assertNotIn("dataset.dashboardActiveTab", html)
```

If `run_dashboard_server` has direct unit tests nearby, add this fake request parsing test. If no handler-level test exists, add it to the closest dashboard server test block:

```python
def test_run_dashboard_server_accepts_room_query_before_legacy_tab_query(self) -> None:
    from momentum_alpha.dashboard import normalize_dashboard_room

    self.assertEqual(normalize_dashboard_room("review"), "review")
    self.assertEqual(normalize_dashboard_room("performance"), "review")
    self.assertEqual(normalize_dashboard_room("execution"), "live")
```

- [ ] **Step 2: Run focused tests to verify failure**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_refreshes_room_content_and_uses_room_query_state \
  tests.test_dashboard.DashboardTests.test_run_dashboard_server_accepts_room_query_before_legacy_tab_query \
  -v
```

Expected: FAIL because the JS still uses active-tab selectors.

- [ ] **Step 3: Update `render_dashboard_scripts()` selectors and refresh logic**

In `render_dashboard_scripts()`, change the selector list:

```javascript
const DASHBOARD_SECTION_SELECTORS = [
  '[data-dashboard-section="status"]',
  '[data-dashboard-section="toolbar"]',
  '[data-dashboard-section="room-nav"]',
  '[data-dashboard-active-room]',
];
```

In `refreshDashboard()`, replace:

```javascript
const activeTab = document.querySelector('[data-dashboard-active-tab]')?.dataset.dashboardActiveTab;
if (!force && activeTab === 'performance') return;
```

with:

```javascript
const activeRoom = document.querySelector('[data-dashboard-active-room]')?.dataset.dashboardActiveRoom;
if (!force && activeRoom === 'review') return;
```

Leave the review-room auto-refresh pause in place. It preserves the prior behavior that avoided refreshing the analysis-heavy performance view while the user may be expanding rows.

- [ ] **Step 4: Update `run_dashboard_server()` query parsing**

In `DashboardHandler.do_GET()`, replace:

```python
active_tab = normalize_dashboard_tab(query_params.get("tab", [None])[0])
```

with:

```python
active_room = normalize_dashboard_room(
    query_params.get("room", [query_params.get("tab", [None])[0]])[0]
)
```

When rendering HTML, pass:

```python
body = render_dashboard_html(
    snapshot,
    active_room=active_room,
    account_range_key=account_range_key,
).encode("utf-8")
```

- [ ] **Step 5: Run focused refresh/query tests and commit**

Run:

```bash
python -m unittest \
  tests.test_dashboard.DashboardTests.test_render_dashboard_html_refreshes_room_content_and_uses_room_query_state \
  tests.test_dashboard.DashboardTests.test_run_dashboard_server_accepts_room_query_before_legacy_tab_query \
  -v
```

Expected: PASS.

Commit:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "refactor: refresh dashboard by active room"
```

---

### Task 6: Clean Up Old Tab Assertions And Run Full Verification

**Files:**
- Modify: `tests/test_dashboard.py`
- Modify: `src/momentum_alpha/dashboard.py` only if a stale helper is still referenced incorrectly

- [ ] **Step 1: Search for stale tab-only expectations**

Run:

```bash
rg -n "active_tab=|data-dashboard-tab-content|data-dashboard-active-tab|\\?tab=|render_dashboard_tab_bar|Overview|Execution|Performance|EXECUTION QUALITY|STRATEGY PERFORMANCE" tests/test_dashboard.py src/momentum_alpha/dashboard.py
```

Expected: results are limited to intentional legacy compatibility wrappers/tests or CSS class names that are deliberately retained for styling.

- [ ] **Step 2: Convert stale tests to room terminology**

For each stale test found in Step 1:

Use this pattern for old `performance` tests:

```python
html = render_dashboard_html(snapshot, active_room="review")
self.assertIn('data-dashboard-room-content="review"', html)
self.assertIn("Closed Trade Detail", html)
```

Use this pattern for old `execution` tests:

```python
live_html = render_dashboard_html(snapshot, active_room="live")
review_html = render_dashboard_html(snapshot, active_room="review")

self.assertIn("ORDER FLOW", live_html)
self.assertIn("STOP SLIPPAGE ANALYSIS", review_html)
```

Use this pattern for old `overview` tests:

```python
html = render_dashboard_html(snapshot, active_room="live")
self.assertIn('data-dashboard-room-content="live"', html)
self.assertIn("ACCOUNT RISK", html)
```

Keep these compatibility checks only once:

```python
self.assertIn('data-dashboard-room-content="live"', render_dashboard_html(snapshot, active_tab="overview"))
self.assertIn('data-dashboard-room-content="live"', render_dashboard_html(snapshot, active_tab="execution"))
self.assertIn('data-dashboard-room-content="review"', render_dashboard_html(snapshot, active_tab="performance"))
self.assertIn('data-dashboard-room-content="system"', render_dashboard_html(snapshot, active_tab="system"))
```

- [ ] **Step 3: Run dashboard test file**

Run:

```bash
python -m unittest tests.test_dashboard -v
```

Expected: PASS.

- [ ] **Step 4: Run the broader affected test set**

Run:

```bash
python -m unittest tests.test_dashboard tests.test_health tests.test_runtime_store tests.test_main tests.test_deploy_artifacts -v
```

Expected: PASS.

- [ ] **Step 5: Check formatting and unstaged changes**

Run:

```bash
git diff --check
git status --short
```

Expected:

- `git diff --check` prints no output and exits 0.
- `git status --short` shows only intended dashboard/test changes plus pre-existing untracked `.superpowers/` and `assets/` if those are still present.

- [ ] **Step 6: Commit final cleanup**

Run:

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "test: align dashboard tests with three-room architecture"
```

Expected: commit succeeds.

---

## Self-Review Checklist

- Spec coverage:
  - `实时监控室` default landing room: Task 1 and Task 2.
  - Account-risk-first first screen: Task 2.
  - Equity, margin usage, and position count charts: Task 2.
  - Live account and position state: Task 2.
  - Compact execution pulse in live room: Task 2.
  - `复盘室` centered on `Closed Trade Detail`: Task 3.
  - Ledger-first closed trade review with expanded leg detail: Task 3.
  - Aggregates after the closed trade table: Task 3.
  - Execution quality analysis in review room: Task 3.
  - `系统状态室` preserving runtime health and freshness: Task 4.
  - No standalone `Execution` room: Task 1, Task 2, Task 3, Task 6.
  - Refresh and URL behavior: Task 5.
- Completion-marker scan:
  - The plan should not contain unresolved marker text or deferred-work language.
- Type consistency:
  - New public room functions use `active_room`.
  - Old compatibility call sites use `active_tab`.
  - Room data attributes use `data-dashboard-active-room` and `data-dashboard-room-content`.
  - CSS classes keep `dashboard-tab` where useful for styling continuity.
