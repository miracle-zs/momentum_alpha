# Live Monitor Room Redesign Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild the realtime monitoring room so `CORE LIVE LINES` has its own full-width row and the live workflow reads top-to-bottom as risk, lines, signal, positions, orders, then commands.

**Architecture:** Keep the existing dashboard data model and reuse the current section renderers, but change the live-room shell from a side-by-side control block into a stacked analysis flow. The page should preserve the current dark cockpit visual language while giving each major live section a clear lane and a stronger hierarchy.

**Tech Stack:** Python string rendering in `src/momentum_alpha/dashboard_render_shell.py`, dashboard CSS in `src/momentum_alpha/dashboard_assets_styles.py`, regression tests in `tests/test_dashboard.py`.

---

### Task 1: Rebuild the live room DOM order

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_shell.py:86-128`
- Test: `tests/test_dashboard.py:2728-2745`

- [ ] **Step 1: Write the failing test**

Add assertions that the live room HTML now reads in this order:

```python
self.assertLess(overview_html.index("ACCOUNT RISK"), overview_html.index("CORE LIVE LINES"))
self.assertLess(overview_html.index("CORE LIVE LINES"), overview_html.index("ACTIVE SIGNAL"))
self.assertLess(overview_html.index("ACTIVE SIGNAL"), overview_html.index("ACTIVE POSITIONS"))
self.assertLess(overview_html.index("ACTIVE POSITIONS"), overview_html.index("ORDER FLOW"))
self.assertLess(overview_html.index("ORDER FLOW"), overview_html.index("HOME COMMAND"))
self.assertLess(overview_html.index("HOME COMMAND"), overview_html.index("data-live-metrics-panel"))
```

The test should fail against the current live-room structure because `CORE LIVE LINES` is still rendered inside the two-column control grid instead of its own full-width band.

- [ ] **Step 2: Run the focused test to confirm the failure**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the live-room order assertions fail before the layout is updated.

- [ ] **Step 3: Rebuild `render_dashboard_live_room()` with stacked bands**

Update the function so the live room renders as explicit full-width sections in this order:

```python
return (
    '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
    "<section class='section-frame live-control-frame'>"
    "<div class='section-topbar'>"
    "<div>"
    "<div class='section-header'>实时监控室</div>"
    "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Use the cockpit to read risk, trend, and action surface in one pass.</div>"
    "</div>"
    "</div>"
    f"<div class='live-risk-band'>{account_risk_html}</div>"
    f"<div class='live-core-lines-band'>{core_lines_html}</div>"
    f"<div class='live-signal-band'>{hero_html}</div>"
    "<div class='live-decision-grid'>"
    f"<div class='live-decision-main'>{positions_html}</div>"
    f"<div class='live-decision-side'>{execution_flow_html}</div>"
    "</div>"
    f"<div class='live-command-band'>{home_command_html}</div>"
    f"<div class='metrics-grid live-metrics-grid' data-live-metrics-panel>{top_metrics_html}</div>"
    "</section>"
    "</div>"
)
```

Keep `render_dashboard_overview_tab()` delegating to `render_dashboard_live_room()` so the overview tab inherits the same layout without a second copy of the structure.

- [ ] **Step 4: Run the live room test again**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the live-room ordering assertions pass and the overview tab still contains the same live-room content.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_render_shell.py tests/test_dashboard.py
git commit -m "feat: stack live room into full-width workflow bands"
```

---

### Task 2: Add layout styles for the full-width live bands

**Files:**
- Modify: `src/momentum_alpha/dashboard_assets_styles.py:540-576`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py:700-748`
- Test: `tests/test_dashboard.py:3680-3715`

- [ ] **Step 1: Write the failing styling expectation in the test**

Keep the existing structural assertions and make sure the live room test still checks for the presence of the live-room containers after the DOM rewrite:

```python
self.assertIn("live-control-frame", html)
self.assertIn("live-metrics-grid", html)
self.assertIn("CORE LIVE LINES", html)
self.assertIn("HOME COMMAND", html)
```

The test should continue to fail until the CSS and DOM are updated together, because the new full-width bands need dedicated classes and spacing rules.

- [ ] **Step 2: Add CSS for the new live bands**

Introduce full-width live band wrappers and keep the current cockpit aesthetic:

```css
.live-control-frame { display: flex; flex-direction: column; gap: 16px; }
.live-risk-band,
.live-core-lines-band,
.live-signal-band,
.live-command-band {
  width: 100%;
  border: 1px solid var(--border);
  border-radius: var(--radius-sm);
  background: linear-gradient(180deg, rgba(245,210,138,0.05), rgba(0,0,0,0.15));
  padding: 16px;
}
.live-core-lines-band {
  background: linear-gradient(180deg, rgba(245,210,138,0.08), rgba(0,0,0,0.18));
}
.live-signal-band {
  background: linear-gradient(180deg, rgba(74,201,240,0.06), rgba(0,0,0,0.14));
}
.live-decision-grid {
  display: grid;
  grid-template-columns: minmax(0, 1.45fr) minmax(340px, 0.95fr);
  gap: 16px;
  align-items: start;
}
.live-decision-main,
.live-decision-side {
  min-width: 0;
}
```

If `HOME COMMAND` needs its own tighter card framing, keep that styling inside the existing `dashboard-section` markup rather than introducing a new visual system.

- [ ] **Step 3: Preserve the responsive stack on smaller screens**

Extend the current mobile rules so the new full-width bands stay one column and the two-column decision row collapses cleanly:

```css
@media (max-width: 1024px) {
  .live-decision-grid { grid-template-columns: 1fr; }
}
@media (max-width: 768px) {
  .live-risk-band,
  .live-core-lines-band,
  .live-signal-band,
  .live-command-band,
  .live-decision-grid { width: 100%; }
}
```

This keeps the live room readable on tablet and mobile without changing the existing typography system.

- [ ] **Step 4: Run the dashboard tests**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
```

Expected: the layout assertions still pass, and the live room remains responsive in the generated HTML structure.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: style live room as stacked cockpit bands"
```

---

### Task 3: Verify the redesigned live room end to end

**Files:**
- Modify: `tests/test_dashboard.py`
- Read: `src/momentum_alpha/dashboard_render_shell.py`
- Read: `src/momentum_alpha/dashboard_assets_styles.py`

- [ ] **Step 1: Run the targeted dashboard test suite**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -q
```

Expected: all dashboard tests pass, including the live-room order assertions and the overview-tab coverage.

- [ ] **Step 2: Run the runtime-store regression suite**

Run:

```bash
python3 -m pytest tests/test_runtime_store.py -v
```

Expected: pass. The live-room redesign should not touch persistence behavior, and this confirms the dashboard changes stayed in the rendering layer.

- [ ] **Step 3: Check the final diff for scope**

Run:

```bash
git diff -- src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
```

Expected: only live-room layout, live-room styling, and the matching dashboard assertions should appear in the diff. No runtime store or data-access changes should be needed.

- [ ] **Step 4: Commit**

```bash
git add src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: redesign live monitoring room layout"
```
