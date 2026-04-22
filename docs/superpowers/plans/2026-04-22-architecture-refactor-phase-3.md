# Architecture Refactor Phase 3 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Continue tightening the modular monolith by splitting the remaining large dashboard presentation modules and the dashboard view-model layer without changing runtime behavior or deployment shape.

**Architecture:** Keep the current system as a modular monolith with systemd-managed long-running processes and SQLite `runtime.db`. Preserve compatibility facade modules such as `dashboard.py`, `dashboard_render.py`, `dashboard_assets.py`, and `dashboard_view_model.py` while moving implementation details into focused modules. Add lightweight split tests so future changes keep room rendering, assets, and dashboard projection logic isolated from each other.

**Tech Stack:** Python 3.12+, standard library `unittest`, server-rendered HTML/CSS/JS, SQLite, existing in-repo facades, existing systemd/script deployment.

---

## Phase 3 Plan Table

| Order | Task | Main Files | Outcome | Verification |
|---:|---|---|---|---|
| 1 | Split the dashboard render stack | `dashboard_render_shell.py`, `dashboard_render_panels.py`, `dashboard_render_tables.py`, new room/visual/table modules | Separate live/review/system room renderers, chart helpers, cosmic helpers, and table builders behind thin facades | `python -m unittest tests.test_dashboard tests.test_dashboard_render tests.test_dashboard_render_split -v` |
| 2 | Split the dashboard asset stack | `dashboard_assets_styles.py`, `dashboard_assets_head.py`, `dashboard_assets.py`, new style bundle modules | Keep base, cosmic, component, and responsive CSS in focused files while preserving the head facade | `python -m unittest tests.test_dashboard_assets tests.test_dashboard_assets_split -v` |
| 3 | Split the dashboard view-model layer | `dashboard_view_model.py`, new common/metrics/positions/range modules | Separate row filtering, streak logic, summary metrics, position details, and account-range helpers | `python -m unittest tests.test_dashboard_view_model tests.test_dashboard_view_model_split tests.test_dashboard -v` |

---

### Task 1: Split the Dashboard Render Stack

**Files:**
- Create: `src/momentum_alpha/dashboard_render_live.py`
- Create: `src/momentum_alpha/dashboard_render_review.py`
- Create: `src/momentum_alpha/dashboard_render_system.py`
- Create: `src/momentum_alpha/dashboard_render_charts.py`
- Create: `src/momentum_alpha/dashboard_render_cosmic.py`
- Create: `src/momentum_alpha/dashboard_render_tables_trades.py`
- Create: `src/momentum_alpha/dashboard_render_tables_aggregates.py`
- Create: `src/momentum_alpha/dashboard_render_tables_positions.py`
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
- Modify: `src/momentum_alpha/dashboard_render_tables.py`
- Modify: `src/momentum_alpha/dashboard_render.py`
- Modify: `tests/test_dashboard_render_split.py`

- [ ] **Step 1: Add import coverage for the new render modules**

Add this test to `tests/test_dashboard_render_split.py`:

```python
def test_dashboard_render_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        dashboard_render_charts,
        dashboard_render_cosmic,
        dashboard_render_live,
        dashboard_render_review,
        dashboard_render_system,
        dashboard_render_tables_aggregates,
        dashboard_render_tables_positions,
        dashboard_render_tables_trades,
    )

    self.assertTrue(callable(dashboard_render_live.render_dashboard_live_room))
    self.assertTrue(callable(dashboard_render_review.render_dashboard_review_room))
    self.assertTrue(callable(dashboard_render_system.render_dashboard_system_room))
    self.assertTrue(callable(dashboard_render_charts._render_line_chart_svg))
    self.assertTrue(callable(dashboard_render_cosmic.render_cosmic_identity_panel))
    self.assertTrue(callable(dashboard_render_tables_trades.render_trade_history_table))
    self.assertTrue(callable(dashboard_render_tables_aggregates.render_trade_leg_count_aggregate_table))
    self.assertTrue(callable(dashboard_render_tables_positions.render_position_cards))
```

- [ ] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_render_split -v
```

Expected: `FAIL` with an import error for one of the new dashboard render modules.

- [ ] **Step 3: Move room renderers out of `dashboard_render_shell.py`**

Create `src/momentum_alpha/dashboard_render_live.py`, `src/momentum_alpha/dashboard_render_review.py`, and `src/momentum_alpha/dashboard_render_system.py` and move the room-specific functions into them:

```text
dashboard_render_live.py:
  render_dashboard_live_room
  render_dashboard_overview_tab
  render_dashboard_execution_tab

dashboard_render_review.py:
  render_dashboard_performance_tab
  render_dashboard_review_tabs
  render_daily_review_room
  render_dashboard_review_room

dashboard_render_system.py:
  render_dashboard_system_room
  render_dashboard_system_tab
```

Keep `dashboard_render_shell.py` focused on shell composition and room/tab orchestration.

- [ ] **Step 4: Move chart and cosmic helpers out of `dashboard_render_panels.py`**

Create `src/momentum_alpha/dashboard_render_charts.py` and `src/momentum_alpha/dashboard_render_cosmic.py` and move these helpers into them:

```text
dashboard_render_charts.py:
  _render_line_chart_svg
  _render_pie_chart_svg
  _cos_deg
  _sin_deg
  _render_bar_chart_svg
  _render_timeline_svg

dashboard_render_cosmic.py:
  _render_cosmic_color_swatches
  _render_cosmic_component_gallery
  _render_cosmic_data_display
  _render_cosmic_visual_elements
  render_cosmic_identity_panel
```

Update `dashboard_render_panels.py` to import these helpers instead of defining them inline.

- [ ] **Step 5: Move table renderers out of `dashboard_render_tables.py`**

Create `src/momentum_alpha/dashboard_render_tables_trades.py`, `src/momentum_alpha/dashboard_render_tables_aggregates.py`, and `src/momentum_alpha/dashboard_render_tables_positions.py` and move these functions into them:

```text
dashboard_render_tables_trades.py:
  render_trade_history_table
  render_closed_trades_table
  _render_round_trip_leg_rows
  _render_round_trip_item

dashboard_render_tables_aggregates.py:
  render_trade_leg_count_aggregate_table
  render_trade_leg_index_aggregate_table
  render_stop_slippage_table

dashboard_render_tables_positions.py:
  render_position_cards
```

Keep `dashboard_render_tables.py` as a facade that re-exports the moved table builders.

- [ ] **Step 6: Rewire shell and facade imports**

Update `dashboard_render_shell.py` so it imports room functions from the new room modules and keeps these orchestration functions in place:

```text
_build_execution_mode
normalize_dashboard_tab
render_dashboard_room_nav
render_dashboard_tab_bar
render_dashboard_shell
render_dashboard_document
render_dashboard_body
render_dashboard_html
```

Update `dashboard_render.py` to re-export the moved room, chart, cosmic, and table entrypoints so existing imports keep working.

- [ ] **Step 7: Run dashboard render tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard tests.test_dashboard_render tests.test_dashboard_render_split -v
```

Expected: `OK`.

- [ ] **Step 8: Commit the render-stack split**

```bash
git add src/momentum_alpha/dashboard_render.py src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_render_panels.py src/momentum_alpha/dashboard_render_tables.py src/momentum_alpha/dashboard_render_live.py src/momentum_alpha/dashboard_render_review.py src/momentum_alpha/dashboard_render_system.py src/momentum_alpha/dashboard_render_charts.py src/momentum_alpha/dashboard_render_cosmic.py src/momentum_alpha/dashboard_render_tables_trades.py src/momentum_alpha/dashboard_render_tables_aggregates.py src/momentum_alpha/dashboard_render_tables_positions.py tests/test_dashboard_render_split.py
git commit -m "refactor: split dashboard render stack"
```

### Task 2: Split the Dashboard Asset Stack

**Files:**
- Create: `src/momentum_alpha/dashboard_assets_styles_base.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_cosmic.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_components.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_responsive.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Modify: `src/momentum_alpha/dashboard_assets_head.py`
- Modify: `src/momentum_alpha/dashboard_assets.py`
- Modify: `tests/test_dashboard_assets_split.py`

- [ ] **Step 1: Add import coverage for the style bundle modules**

Add this test to `tests/test_dashboard_assets_split.py`:

```python
def test_dashboard_style_bundle_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        dashboard_assets_styles_base,
        dashboard_assets_styles_components,
        dashboard_assets_styles_cosmic,
        dashboard_assets_styles_responsive,
    )

    self.assertTrue(callable(dashboard_assets_styles_base._render_dashboard_base_styles))
    self.assertTrue(callable(dashboard_assets_styles_cosmic._render_dashboard_cosmic_styles))
    self.assertTrue(callable(dashboard_assets_styles_components._render_dashboard_component_styles))
    self.assertTrue(callable(dashboard_assets_styles_responsive._render_dashboard_responsive_styles))
```

- [ ] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_assets_split -v
```

Expected: `FAIL` with an import error for one of the new style bundle modules.

- [ ] **Step 3: Move CSS helper functions into focused modules**

Move these helpers out of `dashboard_assets_styles.py`:

```text
dashboard_assets_styles_base.py:
  _render_dashboard_base_styles

dashboard_assets_styles_cosmic.py:
  _render_dashboard_cosmic_styles

dashboard_assets_styles_components.py:
  _render_dashboard_component_styles

dashboard_assets_styles_responsive.py:
  _render_dashboard_responsive_styles
```

Keep `render_dashboard_styles` in `dashboard_assets_styles.py` and have it compose the four imported helpers in the existing order.

- [ ] **Step 4: Preserve facade exports**

Update `dashboard_assets.py` so it still exports:

```text
_render_dashboard_base_styles
_render_dashboard_cosmic_styles
_render_dashboard_component_styles
_render_dashboard_responsive_styles
render_dashboard_styles
render_dashboard_head
render_dashboard_scripts
```

Update `dashboard_assets_head.py` so it stays a thin wrapper around the head HTML and the style bundle composer.

- [ ] **Step 5: Run dashboard asset tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_assets tests.test_dashboard_assets_split -v
```

Expected: `OK`.

- [ ] **Step 6: Commit the asset-stack split**

```bash
git add src/momentum_alpha/dashboard_assets.py src/momentum_alpha/dashboard_assets_head.py src/momentum_alpha/dashboard_assets_styles.py src/momentum_alpha/dashboard_assets_styles_base.py src/momentum_alpha/dashboard_assets_styles_cosmic.py src/momentum_alpha/dashboard_assets_styles_components.py src/momentum_alpha/dashboard_assets_styles_responsive.py tests/test_dashboard_assets_split.py
git commit -m "refactor: split dashboard asset stack"
```

### Task 3: Split the Dashboard View-Model Layer

**Files:**
- Create: `src/momentum_alpha/dashboard_view_model_common.py`
- Create: `src/momentum_alpha/dashboard_view_model_metrics.py`
- Create: `src/momentum_alpha/dashboard_view_model_positions.py`
- Create: `src/momentum_alpha/dashboard_view_model_ranges.py`
- Modify: `src/momentum_alpha/dashboard_view_model.py`
- Modify: `tests/test_dashboard_view_model_split.py`

- [ ] **Step 1: Add import coverage for the new view-model modules**

Create `tests/test_dashboard_view_model_split.py` with this content:

```python
from __future__ import annotations

import unittest


class DashboardViewModelSplitTests(unittest.TestCase):
    def test_dashboard_view_model_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import (
            dashboard_view_model_common,
            dashboard_view_model_metrics,
            dashboard_view_model_positions,
            dashboard_view_model_ranges,
        )

        self.assertTrue(callable(dashboard_view_model_common._parse_decimal))
        self.assertTrue(callable(dashboard_view_model_common._filter_rows_for_range))
        self.assertTrue(callable(dashboard_view_model_metrics.build_trader_summary_metrics))
        self.assertTrue(callable(dashboard_view_model_positions.build_position_details))
        self.assertTrue(callable(dashboard_view_model_ranges._compute_account_range_stats))
```

- [ ] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_view_model_split -v
```

Expected: `FAIL` with an import error for one of the new view-model modules.

- [ ] **Step 3: Move shared parsing and filtering helpers**

Create `src/momentum_alpha/dashboard_view_model_common.py` and move:

```text
_parse_decimal
_object_field
_filter_rows_for_range
_filter_rows_for_display_day
_current_streak_from_round_trips
```

These helpers stay the shared base for the remaining view-model modules.

- [ ] **Step 4: Move summary-metric logic**

Create `src/momentum_alpha/dashboard_view_model_metrics.py` and move:

```text
build_trader_summary_metrics
```

Import the shared helpers from `dashboard_view_model_common.py` and keep the summary aggregation logic isolated.

- [ ] **Step 5: Move position-detail logic**

Create `src/momentum_alpha/dashboard_view_model_positions.py` and move:

```text
build_position_details
```

Keep the position- and leg-derived calculations out of the summary metrics module.

- [ ] **Step 6: Move account-range helpers**

Create `src/momentum_alpha/dashboard_view_model_ranges.py` and move:

```text
_compute_account_range_stats
_detect_account_discontinuity
```

Update `dashboard_view_model.py` to remain a thin facade that re-exports the moved functions.

- [ ] **Step 7: Run dashboard view-model tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_view_model tests.test_dashboard_view_model_split tests.test_dashboard -v
```

Expected: `OK`.

- [ ] **Step 8: Commit the view-model split**

```bash
git add src/momentum_alpha/dashboard_view_model.py src/momentum_alpha/dashboard_view_model_common.py src/momentum_alpha/dashboard_view_model_metrics.py src/momentum_alpha/dashboard_view_model_positions.py src/momentum_alpha/dashboard_view_model_ranges.py tests/test_dashboard_view_model_split.py
git commit -m "refactor: split dashboard view-model layer"
```

---

## Self-Review

- Spec coverage: The plan covers the remaining dashboard render stack, dashboard asset stack, and dashboard view-model layer.
- Placeholder scan: No `TBD`, `TODO`, or unspecified step markers are present.
- Scope check: This phase stays within the dashboard presentation boundary and intentionally defers `dashboard_data.py`, `poll_worker_core.py`, and runtime read/write splits to the next phase.
- Type consistency: New module names follow the current naming style and keep compatibility facades in place while the implementation moves out.
