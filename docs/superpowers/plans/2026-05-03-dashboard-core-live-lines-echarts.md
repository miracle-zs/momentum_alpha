# Dashboard Core Live Lines ECharts Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the realtime monitoring room's `CORE LIVE LINES` hand-written SVG line charts with Apache ECharts loaded from a fixed CDN URL.

**Architecture:** Keep the Python server-rendered dashboard. Render ECharts mount nodes and a JSON payload for the four live core charts, then initialize the charts from the existing inline dashboard script. Dispose and recreate chart instances after auto-refresh replaces the active room DOM.

**Tech Stack:** Python 3.12, `unittest`, server-rendered HTML/CSS/JavaScript, Apache ECharts via jsDelivr CDN.

---

### Task 1: Add Regression Tests For The ECharts Contract

**Files:**
- Modify: `tests/test_dashboard_position_risk.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests**

Add assertions that `_build_live_core_lines_panel(...)` emits four `data-core-live-chart` mount points, a `core-live-lines-json` payload, no `chart-svg` inside that panel, and a `data-core-integer-axis='true'` marker on `Position Count`.

Add dashboard-level assertions that the rendered document includes `https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js`, `initializeCoreLiveCharts`, and `disposeCoreLiveCharts`.

- [ ] **Step 2: Run tests to verify failure**

Run:

```bash
python -m unittest tests.test_dashboard_position_risk tests.test_dashboard -v
```

Expected: FAIL because the current panel still renders `_render_line_chart_svg(...)` and the head does not load ECharts.

### Task 2: Render ECharts Mount Points And Load ECharts

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_panels_account.py`
- Modify: `src/momentum_alpha/dashboard_assets_head.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles_components.py`

- [ ] **Step 1: Replace live core SVG output**

Change `_build_live_core_lines_panel(...)` to render each card with:

```html
<div class='live-core-chart' data-core-live-chart data-core-metric='equity' data-core-label='Account Equity' data-core-color='#4cc9f0' data-core-integer-axis='false'>
  <div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>waiting for data</span></div>
</div>
```

Append:

```html
<script id='core-live-lines-json' type='application/json'>...</script>
```

- [ ] **Step 2: Load ECharts from CDN**

Add a fixed-version script tag to the dashboard head:

```html
<script src="https://cdn.jsdelivr.net/npm/echarts@5.6.0/dist/echarts.min.js"></script>
```

- [ ] **Step 3: Add stable chart dimensions**

Add CSS for `.live-core-chart` with a stable min-height so ECharts has a nonzero render target and empty states stay centered.

### Task 3: Initialize And Refresh ECharts

**Files:**
- Modify: `src/momentum_alpha/dashboard_assets_scripts.py`

- [ ] **Step 1: Add core live chart helpers**

Add functions to parse `core-live-lines-json`, compute the shared time domain, format Shanghai time labels, create ECharts line options, render empty states, initialize chart instances, and dispose old instances.

- [ ] **Step 2: Hook initialization into page load**

Call `initializeCoreLiveCharts()` after `initializeAccountMetrics()`.

- [ ] **Step 3: Hook refresh lifecycle**

Call `disposeCoreLiveCharts()` before replacing dashboard sections in `refreshDashboard(...)`, then call `initializeCoreLiveCharts()` after replacement and account chart refresh.

### Task 4: Verify

**Files:**
- Test: `tests/test_dashboard_position_risk.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Run focused tests**

```bash
python -m unittest tests.test_dashboard_position_risk tests.test_dashboard -v
```

Expected: PASS.

- [ ] **Step 2: Run dashboard asset/render tests**

```bash
python -m unittest tests.test_dashboard_assets tests.test_dashboard_render tests.test_dashboard_render_split -v
```

Expected: PASS.
