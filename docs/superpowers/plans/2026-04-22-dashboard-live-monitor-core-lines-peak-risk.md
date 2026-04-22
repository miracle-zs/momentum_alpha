# Dashboard Live Monitor Core Lines 2x2 Layout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Reflow `CORE LIVE LINES` into a fixed 2x2 grid on desktop and tablet while keeping the existing four charts and their order unchanged.

**Architecture:** Keep the live risk data path and chart rendering as-is. Only adjust the live-core-lines CSS so the existing four cards render as two balanced rows on wider screens and collapse to a single column on mobile. The tests should prove both the card order and the desktop layout string so we do not regress back to the 4-column strip.

**Tech Stack:** Python 3.11, pytest, server-rendered HTML, existing dashboard CSS.

---

## File Structure

- Modify `src/momentum_alpha/dashboard_assets_styles.py`: change the `CORE LIVE LINES` grid from a 4-column desktop strip to a 2-column desktop/tablet grid, and keep the mobile stack behavior.
- Modify `tests/test_dashboard.py`: add a regression assertion that the rendered HTML contains the 2-column `CORE LIVE LINES` rule and still orders `Peak Risk` after `Position Count`.

## Task 1: Reflow the live core-lines grid

**Files:**
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_dashboard_html_uses_two_column_live_core_lines_grid(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), active_room="live")

    self.assertIn("CORE LIVE LINES", html)
    self.assertIn("live-core-lines-grid", html)
    self.assertIn("Position Count", html)
    self.assertIn("Peak Risk", html)
    self.assertLess(html.index("Position Count"), html.index("Peak Risk"))
    self.assertIn(
        ".live-core-lines-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 16px; }",
        html,
    )
    self.assertIn(".live-core-lines-grid { grid-template-columns: 1fr; }", html)
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_dashboard.py -k live_core_lines -v`

Expected: FAIL because the rendered CSS still uses the 4-column desktop rule for `.live-core-lines-grid`.

- [ ] **Step 3: Update the live core-lines CSS**

```css
.live-core-lines-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 16px;
}
.live-core-line-card {
  min-height: 248px;
}
@media (max-width: 768px) {
  .live-core-lines-grid {
    grid-template-columns: 1fr;
  }
}
```

Delete the now-redundant `@media (max-width: 1200px)` override for `.live-core-lines-grid`, since tablet should also stay 2x2.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -v
python3 -m pytest tests/test_dashboard_position_risk.py -v
```

Expected: both commands PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: reflow live core lines to 2x2"
```
