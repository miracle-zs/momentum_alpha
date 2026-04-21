# Dashboard Live And System Room Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework `实时监控室` into a cockpit and `系统状态室` into an ops console by changing room shell layout, section priority, and supporting CSS without changing the data model.

**Architecture:** Keep the existing three-room dashboard and server-rendered flow. Update the room shell markup in `dashboard_render_shell.py` so each room has a stronger first-screen hierarchy, then tune `dashboard_assets_styles.py` so the new room shells read correctly on desktop and mobile. Add focused regression tests in `tests/test_dashboard.py` to lock the intended section order and preserve empty-state behavior.

**Tech Stack:** Python 3, pytest, server-rendered HTML strings, existing dashboard CSS utilities.

---

### Task 1: Rebuild `实时监控室` as a cockpit

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add an order-focused dashboard test that asserts the live room renders its sections in cockpit order, with live risk first and execution last.

```python
def test_render_dashboard_html_orders_live_room_sections_as_cockpit():
    html = render_dashboard_html(snapshot, active_room="live")
    assert html.index("实时监控室") < html.index("ACCOUNT RISK")
    assert html.index("ACCOUNT RISK") < html.index("CORE LIVE LINES")
    assert html.index("CORE LIVE LINES") < html.index("ACTIVE SIGNAL")
    assert html.index("ACTIVE SIGNAL") < html.index("ACTIVE POSITIONS")
    assert html.index("ACTIVE POSITIONS") < html.index("ORDER FLOW")
```

- [ ] **Step 2: Run the focused test and confirm the current layout does not yet satisfy the cockpit ordering**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k live_room -v
```

Expected: the new order assertion fails or the room order assertion does not pass yet.

- [ ] **Step 3: Update the live room shell markup**

Modify `render_dashboard_live_room()` in `src/momentum_alpha/dashboard_render_shell.py` so the top-to-bottom structure is:

```python
return (
    '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
    "<section class='section-frame live-control-frame'>"
    "<div class='section-topbar'>...</div>"
    "<div class='live-control-grid'>"
    f"{account_risk_html}"
    f"{core_lines_html}"
    "</div>"
    f"<div class='metrics-grid live-metrics-grid'>{top_metrics_html}</div>"
    "<div class='live-decision-grid'>"
    f"<div class='live-decision-main'>{hero_html}</div>"
    "<div class='live-decision-side'>"
    "<section class='dashboard-section active-positions-panel live-card-shell'>"
    "<div class='section-header'>ACTIVE POSITIONS</div>"
    f"{positions_html}"
    "</section>"
    "</div>"
    "</div>"
    "<div class='live-ops-grid'>"
    f"{execution_flow_html}"
    f"{home_command_html}"
    "</div>"
    "</section>"
    "</div>"
)
```

Update `dashboard_assets_styles.py` so the live room keeps the cockpit hierarchy with clear section separation and responsive collapse to one column on smaller screens.

- [ ] **Step 4: Re-run the live room test and the dashboard suite**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k live_room -v
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the cockpit-order assertion passes and the dashboard suite stays green.

- [ ] **Step 5: Commit the live-room change**

```bash
git add src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: refine live room cockpit layout"
```

### Task 2: Rebuild `系统状态室` as an ops console

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

Add an order-focused dashboard test that asserts the system room renders diagnostics before config, warnings before events, and keeps the console structure intact.

```python
def test_render_dashboard_html_orders_system_room_sections_as_console():
    html = render_dashboard_html(snapshot, active_room="system")
    assert html.index("SYSTEM DIAGNOSTICS") < html.index("SYSTEM OPERATIONS")
    assert html.index("SYSTEM OPERATIONS") < html.index("EVENT SOURCES")
    assert html.index("EVENT SOURCES") < html.index("SYSTEM HEALTH")
    assert html.index("SYSTEM HEALTH") < html.index("RECENT EVENTS")
```

- [ ] **Step 2: Run the focused test and verify the current room order still needs adjustment**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k system_room -v
```

Expected: the console-order assertion fails or does not yet reflect the target hierarchy.

- [ ] **Step 3: Update the system room shell markup**

Modify `render_dashboard_system_room()` in `src/momentum_alpha/dashboard_render_shell.py` so the structure reads:

```python
return (
    '<div class="dashboard-tab-panel" data-dashboard-room-content="system">'
    "<section class='section-frame' data-collapsible-section='system'>"
    "<div class='section-topbar'>...</div>"
    "<div class='dashboard-section section-body system-analysis-shell'>"
    "<div class='system-summary-strip'>"
    "<div class='system-summary-head'>...</div>"
    f"{diagnostics_html}"
    f"{warning_list_html}"
    "</div>"
    "<div class='system-console-grid'>"
    "<div class='system-console-left'>"
    f"{config_html}"
    f"{source_html}"
    f"{health_items_html}"
    "</div>"
    "<div class='chart-card system-console-events'>"
    f"{recent_events_html}"
    "</div>"
    "</div>"
    "</div>"
    "</section>"
    "</div>"
)
```

Tune `dashboard_assets_styles.py` so the diagnostics strip stays visually dominant, the console grid remains legible on desktop, and the layout collapses cleanly on mobile.

- [ ] **Step 4: Re-run the system room test and the dashboard suite**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k system_room -v
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the system console-order assertion passes and the dashboard suite stays green.

- [ ] **Step 5: Commit the system-room change**

```bash
git add src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: refine system room console layout"
```

### Task 3: Verify cross-room regression coverage

**Files:**
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Add or update a combined dashboard regression**

Keep one dashboard-level test that renders all three rooms and confirms:

```python
def test_render_dashboard_html_keeps_all_rooms_present():
    live_html = render_dashboard_html(snapshot, active_room="live")
    review_html = render_dashboard_html(snapshot, active_room="review")
    system_html = render_dashboard_html(snapshot, active_room="system")
    assert "实时监控室" in live_html
    assert "复盘室" in review_html
    assert "系统状态室" in system_html
```

Use the existing test file to preserve the review-room assertions already in place.

- [ ] **Step 2: Run the full dashboard test file**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the entire dashboard test suite passes after the room layout updates.

- [ ] **Step 3: Commit the regression test update**

```bash
git add tests/test_dashboard.py
git commit -m "test: lock dashboard room layout regressions"
```

### Task 4: Final review and cleanup

**Files:**
- Review: `src/momentum_alpha/dashboard_render_shell.py`
- Review: `src/momentum_alpha/dashboard_assets_styles.py`
- Review: `tests/test_dashboard.py`

- [ ] **Step 1: Review the rendered section order**

Check that:

- `实时监控室` reads as cockpit-first
- `系统状态室` reads as diagnostics-first
- the review room remains unchanged

- [ ] **Step 2: Run the full relevant test suite**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
python3 -m pytest tests/test_runtime_store.py -q
```

Expected: both suites pass.

- [ ] **Step 3: Commit any final cleanup**

```bash
git add src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "docs: finalize live and system room layout work"
```

## Coverage Check

This plan covers the spec requirements as follows:

- `实时监控室` cockpit hierarchy: Task 1
- `系统状态室` console hierarchy: Task 2
- responsive and visual hierarchy tuning: Tasks 1 and 2
- regression protection: Task 3
- unchanged data model and no router rewrite: Tasks 1-4

No spec requirement is left without a task.
