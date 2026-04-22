# Architecture Refactor Phase 2 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox syntax for tracking.

**Goal:** Tighten the current modular monolith by splitting the remaining large dashboard, runtime persistence, CLI, market-data, and user-stream modules without changing trading behavior or deployment shape.

**Architecture:** Keep the current system as a modular monolith with systemd-managed long-running processes and SQLite `runtime.db`. Preserve compatibility facade modules such as `dashboard.py`, `dashboard_render.py`, `dashboard_assets.py`, `runtime_store.py`, `cli.py`, `market_data.py`, and `user_stream_events.py`, while moving implementation details into focused modules. Add lightweight architecture boundary tests so future changes do not pull infrastructure or presentation dependencies back into strategy/runtime core.

**Tech Stack:** Python 3.12+, standard library `unittest`, SQLite, existing in-repo facades, existing systemd/script deployment.

---

## Phase 2 Plan Table

| Order | Task | Main Files | Outcome | Verification |
|---:|---|---|---|---|
| 1 | Add architecture boundary guard tests | `tests/test_architecture_boundaries.py` | Prevent core strategy/runtime modules from importing dashboard, broker, Binance client, SQLite, HTTP server, or WebSocket dependencies | `python -m unittest tests.test_architecture_boundaries -v` |
| 2 | Split dashboard room renderers | `dashboard_render_shell.py`, new `dashboard_render_live.py`, `dashboard_render_review.py`, `dashboard_render_system.py` | Keep shell orchestration separate from live/review/system room HTML | `python -m unittest tests.test_dashboard tests.test_dashboard_render tests.test_dashboard_render_split -v` |
| 3 | Split dashboard charts and visual panels | `dashboard_render_panels.py`, new `dashboard_render_charts.py`, `dashboard_render_cosmic.py` | Reduce panel module size and isolate SVG/chart/cosmic reference helpers | `python -m unittest tests.test_dashboard tests.test_dashboard_render_split -v` |
| 4 | Split dashboard CSS bundles | `dashboard_assets_styles.py`, new style bundle modules | Keep base, cosmic, component, and responsive CSS in focused files | `python -m unittest tests.test_dashboard_assets tests.test_dashboard_assets_split -v` |
| 5 | Split runtime write repositories | `runtime_writes.py`, new write modules | Separate event, report, and snapshot inserts while preserving `runtime_store.py` facade imports | `python -m unittest tests.test_runtime_writes tests.test_runtime_store -v` |
| 6 | Split runtime history reads | `runtime_reads_history.py`, new read modules | Separate trade, daily-review, snapshot, and dashboard-history queries | `python -m unittest tests.test_runtime_reads tests.test_runtime_store tests.test_dashboard_data -v` |
| 7 | Split trade analytics rebuild logic | `runtime_analytics.py`, new analytics modules | Isolate decimal helpers, leg payload building, stop trigger resolution, and rebuild orchestration | `python -m unittest tests.test_runtime_analytics tests.test_runtime_store -v` |
| 8 | Split CLI parser and command handlers | `cli.py`, new `cli_env.py`, `cli_backfill.py`, `cli_commands.py`, `cli_parser.py` | Separate command parsing, environment/factory helpers, and command execution branches | `python -m unittest tests.test_cli tests.test_main tests.test_deploy_artifacts -v` |
| 9 | Split market-data snapshot assembly | `market_data.py`, new market-data modules | Separate symbol resolution, time windows, kline fetching, cache, and snapshot assembly | `python -m unittest tests.test_market_data tests.test_main -v` |
| 10 | Split user-stream event parsing/extraction | `user_stream_events.py`, new user-stream event modules | Separate event model, parser, extractors, id/status helpers, and account-position helpers | `python -m unittest tests.test_user_stream tests.test_user_stream_split tests.test_main -v` |
| 11 | Update architecture docs and run final verification | `README.md`, `CLAUDE.md`, architecture plan docs | Documentation aligned with the completed phase-2 module boundaries | `python -m unittest discover -s tests -v` |

---

### Task 1: Add Architecture Boundary Guard Tests

**Files:**
- Create: `tests/test_architecture_boundaries.py`

- [x] **Step 1: Add the boundary test file**

Create `tests/test_architecture_boundaries.py` with this content:

```python
from __future__ import annotations

import ast
from pathlib import Path
import unittest


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SRC_ROOT = PROJECT_ROOT / "src" / "momentum_alpha"

CORE_MODULES = (
    "models.py",
    "strategy.py",
    "runtime.py",
    "execution.py",
    "orders.py",
    "sizing.py",
    "binance_filters.py",
    "exchange_info.py",
    "config.py",
)

FORBIDDEN_CORE_IMPORT_PREFIXES = (
    "momentum_alpha.dashboard",
    "momentum_alpha.dashboard_",
    "momentum_alpha.runtime_store",
    "momentum_alpha.runtime_reads",
    "momentum_alpha.runtime_writes",
    "momentum_alpha.runtime_schema",
    "momentum_alpha.runtime_analytics",
    "momentum_alpha.binance_client",
    "momentum_alpha.broker",
    "momentum_alpha.user_stream",
    "momentum_alpha.poll_worker",
    "momentum_alpha.stream_worker",
)

FORBIDDEN_STANDARD_IMPORTS = {
    "sqlite3",
    "http.server",
    "websocket",
}


def _imports_for(path: Path) -> list[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    imports: list[str] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            imports.extend(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module is not None:
            imports.append(node.module)
    return imports


class ArchitectureBoundaryTests(unittest.TestCase):
    def test_core_modules_do_not_import_infrastructure_or_presentation(self) -> None:
        violations: list[str] = []
        for module_name in CORE_MODULES:
            path = SRC_ROOT / module_name
            for imported in _imports_for(path):
                if imported in FORBIDDEN_STANDARD_IMPORTS:
                    violations.append(f"{module_name} imports {imported}")
                    continue
                if any(imported == prefix or imported.startswith(f"{prefix}.") for prefix in FORBIDDEN_CORE_IMPORT_PREFIXES):
                    violations.append(f"{module_name} imports {imported}")
        self.assertEqual([], violations)
```

- [x] **Step 2: Run the boundary test**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_architecture_boundaries -v
```

Expected: `OK`.

- [x] **Step 3: Commit the boundary guard**

```bash
git add tests/test_architecture_boundaries.py
git commit -m "test: add architecture boundary guard"
```

### Task 2: Split Dashboard Room Renderers

**Files:**
- Create: `src/momentum_alpha/dashboard_render_live.py`
- Create: `src/momentum_alpha/dashboard_render_review.py`
- Create: `src/momentum_alpha/dashboard_render_system.py`
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_render.py`
- Modify: `tests/test_dashboard_render_split.py`

- [x] **Step 1: Add import coverage for room modules**

Add this test to `tests/test_dashboard_render_split.py`:

```python
def test_dashboard_room_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import dashboard_render_live, dashboard_render_review, dashboard_render_system

    self.assertTrue(callable(dashboard_render_live.render_dashboard_live_room))
    self.assertTrue(callable(dashboard_render_live.render_dashboard_execution_tab))
    self.assertTrue(callable(dashboard_render_review.render_dashboard_review_room))
    self.assertTrue(callable(dashboard_render_review.render_daily_review_room))
    self.assertTrue(callable(dashboard_render_system.render_dashboard_system_room))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_render_split -v
```

Expected: `FAIL` with an import error for one of the new dashboard room modules.

- [x] **Step 3: Move live room functions**

Create `src/momentum_alpha/dashboard_render_live.py` and move these functions from `dashboard_render_shell.py`:

```text
render_dashboard_live_room
render_dashboard_overview_tab
render_dashboard_execution_tab
```

Keep imports local to the new module:

```python
from __future__ import annotations

from .dashboard_render_panels import (
    _build_execution_flow_panel,
    _build_live_account_risk_panel,
    _build_live_core_lines_panel,
    _build_overview_home_command,
)
from .dashboard_render_tables import (
    render_position_cards,
    render_stop_slippage_table,
    render_trade_history_table,
)
```

- [x] **Step 4: Move review room functions**

Create `src/momentum_alpha/dashboard_render_review.py` and move these functions from `dashboard_render_shell.py`:

```text
render_dashboard_performance_tab
render_dashboard_review_tabs
render_daily_review_room
render_dashboard_review_room
```

Keep review constants and URL helpers imported from the existing utility modules:

```python
from __future__ import annotations

from html import escape

from .dashboard_common import normalize_account_range
from .dashboard_data import build_trade_leg_count_aggregates, build_trade_leg_index_aggregates
from .dashboard_render_panels import _build_account_metrics_panel, render_daily_review_panel
from .dashboard_render_tables import (
    render_closed_trades_table,
    render_trade_leg_count_aggregate_table,
    render_trade_leg_index_aggregate_table,
)
from .dashboard_render_utils import REVIEW_VIEWS, _build_dashboard_room_href, normalize_review_view
```

- [x] **Step 5: Move system room functions**

Create `src/momentum_alpha/dashboard_render_system.py` and move these functions from `dashboard_render_shell.py`:

```text
render_dashboard_system_room
render_dashboard_system_tab
```

Keep system-specific HTML rendering in this module and import format helpers from `dashboard_render_utils.py`.

- [x] **Step 6: Rewire shell and facade imports**

Update `dashboard_render_shell.py` so it imports the room functions from the new modules and keeps these orchestration functions in place:

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

Update `dashboard_render.py` to re-export the moved functions from the new room modules.

- [x] **Step 7: Run dashboard render tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard tests.test_dashboard_render tests.test_dashboard_render_split -v
```

Expected: `OK`.

- [x] **Step 8: Commit the dashboard room split**

```bash
git add src/momentum_alpha/dashboard_render.py src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_render_live.py src/momentum_alpha/dashboard_render_review.py src/momentum_alpha/dashboard_render_system.py tests/test_dashboard_render_split.py
git commit -m "refactor: split dashboard room renderers"
```

### Task 3: Split Dashboard Charts and Visual Panels

**Files:**
- Create: `src/momentum_alpha/dashboard_render_charts.py`
- Create: `src/momentum_alpha/dashboard_render_cosmic.py`
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
- Modify: `src/momentum_alpha/dashboard_render.py`
- Modify: `tests/test_dashboard_render_split.py`

- [x] **Step 1: Add import coverage for chart and cosmic modules**

Add this test to `tests/test_dashboard_render_split.py`:

```python
def test_dashboard_visual_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import dashboard_render_charts, dashboard_render_cosmic

    self.assertTrue(callable(dashboard_render_charts._render_line_chart_svg))
    self.assertTrue(callable(dashboard_render_charts._render_pie_chart_svg))
    self.assertTrue(callable(dashboard_render_charts._render_bar_chart_svg))
    self.assertTrue(callable(dashboard_render_charts._render_timeline_svg))
    self.assertTrue(callable(dashboard_render_cosmic.render_cosmic_identity_panel))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_render_split -v
```

Expected: `FAIL` with an import error for `dashboard_render_charts` or `dashboard_render_cosmic`.

- [x] **Step 3: Move chart helpers**

Create `src/momentum_alpha/dashboard_render_charts.py` and move these functions from `dashboard_render_panels.py`:

```text
_render_line_chart_svg
_render_pie_chart_svg
_cos_deg
_sin_deg
_render_bar_chart_svg
_render_timeline_svg
```

Update `dashboard_render_panels.py` to import the chart helpers from `dashboard_render_charts.py`.

- [x] **Step 4: Move cosmic reference panel helpers**

Create `src/momentum_alpha/dashboard_render_cosmic.py` and move these functions from `dashboard_render_panels.py`:

```text
_render_cosmic_color_swatches
_render_cosmic_component_gallery
_render_cosmic_data_display
_render_cosmic_visual_elements
render_cosmic_identity_panel
```

Update `dashboard_render_panels.py` and `dashboard_render.py` to import and re-export `render_cosmic_identity_panel`.

- [x] **Step 5: Run dashboard tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard tests.test_dashboard_render_split -v
```

Expected: `OK`.

- [x] **Step 6: Commit the chart and visual panel split**

```bash
git add src/momentum_alpha/dashboard_render.py src/momentum_alpha/dashboard_render_panels.py src/momentum_alpha/dashboard_render_charts.py src/momentum_alpha/dashboard_render_cosmic.py tests/test_dashboard_render_split.py
git commit -m "refactor: split dashboard chart and visual panels"
```

### Task 4: Split Dashboard CSS Bundles

**Files:**
- Create: `src/momentum_alpha/dashboard_assets_styles_base.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_cosmic.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_components.py`
- Create: `src/momentum_alpha/dashboard_assets_styles_responsive.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Modify: `src/momentum_alpha/dashboard_assets.py`
- Modify: `tests/test_dashboard_assets_split.py`

- [x] **Step 1: Add import coverage for CSS bundle modules**

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

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_assets_split -v
```

Expected: `FAIL` with an import error for one of the new style modules.

- [x] **Step 3: Move CSS helper functions**

Move these functions from `dashboard_assets_styles.py` into the named files:

```text
dashboard_assets_styles_base.py: _render_dashboard_base_styles
dashboard_assets_styles_cosmic.py: _render_dashboard_cosmic_styles
dashboard_assets_styles_components.py: _render_dashboard_component_styles
dashboard_assets_styles_responsive.py: _render_dashboard_responsive_styles
```

Keep `render_dashboard_styles` in `dashboard_assets_styles.py` and have it compose the four imported helpers in the existing order.

- [x] **Step 4: Preserve facade exports**

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

- [x] **Step 5: Run dashboard asset tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_assets tests.test_dashboard_assets_split -v
```

Expected: `OK`.

- [x] **Step 6: Commit the CSS bundle split**

```bash
git add src/momentum_alpha/dashboard_assets.py src/momentum_alpha/dashboard_assets_styles.py src/momentum_alpha/dashboard_assets_styles_base.py src/momentum_alpha/dashboard_assets_styles_cosmic.py src/momentum_alpha/dashboard_assets_styles_components.py src/momentum_alpha/dashboard_assets_styles_responsive.py tests/test_dashboard_assets_split.py
git commit -m "refactor: split dashboard style bundles"
```

### Task 5: Split Runtime Write Repositories

**Files:**
- Create: `src/momentum_alpha/runtime_writes_events.py`
- Create: `src/momentum_alpha/runtime_writes_reports.py`
- Create: `src/momentum_alpha/runtime_writes_snapshots.py`
- Modify: `src/momentum_alpha/runtime_writes.py`
- Modify: `tests/test_runtime_writes_split.py`

- [x] **Step 1: Add import coverage for write modules**

Create `tests/test_runtime_writes_split.py` with this content:

```python
from __future__ import annotations

import unittest


class RuntimeWritesSplitTests(unittest.TestCase):
    def test_runtime_write_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import runtime_writes_events, runtime_writes_reports, runtime_writes_snapshots

        self.assertTrue(callable(runtime_writes_events.insert_audit_event))
        self.assertTrue(callable(runtime_writes_events.insert_trade_fill))
        self.assertTrue(callable(runtime_writes_reports.insert_trade_round_trip))
        self.assertTrue(callable(runtime_writes_reports.insert_daily_review_report))
        self.assertTrue(callable(runtime_writes_snapshots.insert_position_snapshot))
        self.assertTrue(callable(runtime_writes_snapshots.insert_account_snapshot))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_writes_split -v
```

Expected: `FAIL` with an import error for one of the new runtime write modules.

- [x] **Step 3: Move event write functions**

Create `runtime_writes_events.py` and move these functions from `runtime_writes.py`:

```text
save_notification_status
insert_audit_event
insert_signal_decision
insert_broker_order
insert_trade_fill
insert_algo_order
insert_account_flow
```

Move or import the shared helpers `_json_dumps`, `_as_utc_iso`, and `_decimal_to_text` so behavior remains byte-for-byte compatible for stored values.

- [x] **Step 4: Move report write functions**

Create `runtime_writes_reports.py` and move these functions from `runtime_writes.py`:

```text
insert_trade_round_trip
insert_daily_review_report
insert_stop_exit_summary
```

Reuse `_json_dumps`, `_as_utc_iso`, and `_decimal_to_text`.

- [x] **Step 5: Move snapshot write functions**

Create `runtime_writes_snapshots.py` and move these functions from `runtime_writes.py`:

```text
insert_position_snapshot
insert_account_snapshot
```

Reuse `_bool_to_int`, `_json_dumps`, `_as_utc_iso`, and `_decimal_to_text`.

- [x] **Step 6: Convert `runtime_writes.py` into a facade**

Keep `runtime_writes.py` as a re-export facade for every function that `runtime_store.py`, `telemetry.py`, `serverchan.py`, and tests currently import.

- [x] **Step 7: Run runtime write tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_writes tests.test_runtime_writes_split tests.test_runtime_store -v
```

Expected: `OK`.

- [x] **Step 8: Commit the runtime write split**

```bash
git add src/momentum_alpha/runtime_writes.py src/momentum_alpha/runtime_writes_events.py src/momentum_alpha/runtime_writes_reports.py src/momentum_alpha/runtime_writes_snapshots.py tests/test_runtime_writes_split.py
git commit -m "refactor: split runtime write repositories"
```

### Task 6: Split Runtime History Reads

**Files:**
- Create: `src/momentum_alpha/runtime_reads_trades.py`
- Create: `src/momentum_alpha/runtime_reads_reviews.py`
- Create: `src/momentum_alpha/runtime_reads_snapshots.py`
- Create: `src/momentum_alpha/runtime_reads_dashboard.py`
- Modify: `src/momentum_alpha/runtime_reads_history.py`
- Modify: `src/momentum_alpha/runtime_reads.py`
- Modify: `tests/test_runtime_reads_split.py`

- [x] **Step 1: Add import coverage for read modules**

Add this test to `tests/test_runtime_reads_split.py`:

```python
def test_runtime_history_read_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        runtime_reads_dashboard,
        runtime_reads_reviews,
        runtime_reads_snapshots,
        runtime_reads_trades,
    )

    self.assertTrue(callable(runtime_reads_trades.fetch_recent_trade_round_trips))
    self.assertTrue(callable(runtime_reads_trades.fetch_trade_round_trips_for_window))
    self.assertTrue(callable(runtime_reads_reviews.fetch_latest_daily_review_report))
    self.assertTrue(callable(runtime_reads_snapshots.fetch_recent_account_snapshots))
    self.assertTrue(callable(runtime_reads_dashboard.fetch_leader_history))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads_split -v
```

Expected: `FAIL` with an import error for one of the new runtime read modules.

- [x] **Step 3: Move trade history queries**

Create `runtime_reads_trades.py` and move these functions from `runtime_reads_history.py`:

```text
fetch_recent_trade_round_trips
fetch_trade_round_trips_for_range
fetch_trade_round_trips_for_window
fetch_recent_stop_exit_summaries
```

- [x] **Step 4: Move daily review queries**

Create `runtime_reads_reviews.py` and move these functions from `runtime_reads_history.py`:

```text
fetch_latest_daily_review_report
fetch_daily_review_report_by_date
fetch_daily_review_report_dates
fetch_daily_review_reports_summary
```

- [x] **Step 5: Move snapshot queries**

Create `runtime_reads_snapshots.py` and move these functions from `runtime_reads_history.py`:

```text
fetch_recent_position_snapshots
fetch_recent_account_snapshots
fetch_account_snapshots_for_range
```

- [x] **Step 6: Move dashboard history queries**

Create `runtime_reads_dashboard.py` and move these functions from `runtime_reads_history.py`:

```text
fetch_leader_history
fetch_event_pulse_points
summarize_audit_events
```

- [x] **Step 7: Preserve read facades**

Update `runtime_reads_history.py` and `runtime_reads.py` so existing imports from `runtime_store.py`, `dashboard_data.py`, `daily_review.py`, and tests keep working.

- [x] **Step 8: Run runtime read tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads tests.test_runtime_reads_split tests.test_runtime_store tests.test_dashboard_data -v
```

Expected: `OK`.

- [x] **Step 9: Commit the runtime read split**

```bash
git add src/momentum_alpha/runtime_reads.py src/momentum_alpha/runtime_reads_history.py src/momentum_alpha/runtime_reads_trades.py src/momentum_alpha/runtime_reads_reviews.py src/momentum_alpha/runtime_reads_snapshots.py src/momentum_alpha/runtime_reads_dashboard.py tests/test_runtime_reads_split.py
git commit -m "refactor: split runtime history reads"
```

### Task 7: Split Trade Analytics Rebuild Logic

**Files:**
- Create: `src/momentum_alpha/runtime_analytics_common.py`
- Create: `src/momentum_alpha/runtime_analytics_legs.py`
- Create: `src/momentum_alpha/runtime_analytics_stops.py`
- Create: `src/momentum_alpha/runtime_analytics_rebuild.py`
- Modify: `src/momentum_alpha/runtime_analytics.py`
- Modify: `tests/test_runtime_analytics.py`

- [x] **Step 1: Add import coverage for analytics modules**

Add this test to `tests/test_runtime_analytics.py`:

```python
def test_runtime_analytics_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        runtime_analytics_common,
        runtime_analytics_legs,
        runtime_analytics_rebuild,
        runtime_analytics_stops,
    )

    self.assertTrue(callable(runtime_analytics_common._text_to_decimal))
    self.assertTrue(callable(runtime_analytics_legs._build_trade_round_trip_leg_payload))
    self.assertTrue(callable(runtime_analytics_stops._resolve_stop_trigger_price_for_exit))
    self.assertTrue(callable(runtime_analytics_rebuild.rebuild_trade_analytics))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_analytics.RuntimeAnalyticsTests.test_runtime_analytics_split_modules_export_key_entrypoints -v
```

Expected: `FAIL` with an import error for one of the new analytics modules.

- [x] **Step 3: Move shared analytics helpers**

Create `runtime_analytics_common.py` and move:

```text
_json_dumps
_json_loads
_as_utc_iso
_decimal_to_text
_text_to_decimal
_text_to_optional_decimal
```

- [x] **Step 4: Move leg analytics helpers**

Create `runtime_analytics_legs.py` and move:

```text
_strategy_stop_client_order_id
_trade_leg_type_from_client_order_id
_build_trade_round_trip_leg_payload
```

- [x] **Step 5: Move stop trigger helpers**

Create `runtime_analytics_stops.py` and move:

```text
_resolve_stop_trigger_price_for_exit
_extract_stop_trigger_price_from_broker_order
_extract_stop_trigger_price_from_signal_decision
```

- [x] **Step 6: Move rebuild orchestration**

Create `runtime_analytics_rebuild.py` and move:

```text
rebuild_trade_analytics
```

Update imports so `runtime_analytics_rebuild.py` uses helpers from the new common, legs, and stops modules.

- [x] **Step 7: Preserve `runtime_analytics.py` facade exports**

Update `runtime_analytics.py` to re-export the moved helper functions and `rebuild_trade_analytics`.

- [x] **Step 8: Run analytics tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_analytics tests.test_runtime_store -v
```

Expected: `OK`.

- [x] **Step 9: Commit the analytics split**

```bash
git add src/momentum_alpha/runtime_analytics.py src/momentum_alpha/runtime_analytics_common.py src/momentum_alpha/runtime_analytics_legs.py src/momentum_alpha/runtime_analytics_stops.py src/momentum_alpha/runtime_analytics_rebuild.py tests/test_runtime_analytics.py
git commit -m "refactor: split runtime analytics rebuild"
```

### Task 8: Split CLI Parser and Command Handlers

**Files:**
- Create: `src/momentum_alpha/cli_env.py`
- Create: `src/momentum_alpha/cli_backfill.py`
- Create: `src/momentum_alpha/cli_parser.py`
- Create: `src/momentum_alpha/cli_commands.py`
- Modify: `src/momentum_alpha/cli.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_cli.py`
- Modify: `tests/test_main.py`

- [x] **Step 1: Add import coverage for CLI modules**

Add this test to `tests/test_cli.py`:

```python
def test_cli_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import cli_backfill, cli_commands, cli_env, cli_parser

    self.assertTrue(callable(cli_env.resolve_runtime_db_path))
    self.assertTrue(callable(cli_env.load_credentials_from_env))
    self.assertTrue(callable(cli_backfill.backfill_account_flows))
    self.assertTrue(callable(cli_parser.build_cli_parser))
    self.assertTrue(callable(cli_commands.run_cli_command))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_cli -v
```

Expected: `FAIL` with an import error for one of the new CLI modules.

- [x] **Step 3: Move environment and factory helpers**

Create `cli_env.py` and move these helpers from `cli.py`:

```text
resolve_runtime_db_path
_require_runtime_db_path
_build_audit_recorder
_build_runtime_state_store
load_credentials_from_env
load_runtime_settings_from_env
_parse_cli_datetime
_build_client_from_factory
```

- [x] **Step 4: Move account-flow backfill helpers**

Create `cli_backfill.py` and move:

```text
_account_flow_exists
backfill_account_flows
```

- [x] **Step 5: Move parser construction**

Create `cli_parser.py` with a function:

```python
def build_cli_parser() -> argparse.ArgumentParser:
    ...
```

Move all `argparse` parser and subparser setup from `cli_main` into `build_cli_parser`.

- [x] **Step 6: Move command dispatch**

Create `cli_commands.py` with a function:

```python
def run_cli_command(
    *,
    parser,
    args,
    client_factory,
    broker_factory,
    now_provider,
    run_forever_fn,
    run_user_stream_fn,
    run_dashboard_fn,
    backfill_account_flows_fn,
    rebuild_trade_analytics_fn,
) -> int:
    ...
```

Move the existing `if args.command == ...` branches from `cli_main` into `run_cli_command`.

- [x] **Step 7: Keep `cli.py` as the public entrypoint**

Update `cli.py` so `cli_main` builds the parser, normalizes default factories, calls `run_cli_command`, and re-exports the helpers currently imported by `main.py` and tests.

- [x] **Step 8: Run CLI and main tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_cli tests.test_main tests.test_deploy_artifacts -v
```

Expected: `OK`.

- [x] **Step 9: Commit the CLI split**

```bash
git add src/momentum_alpha/cli.py src/momentum_alpha/cli_env.py src/momentum_alpha/cli_backfill.py src/momentum_alpha/cli_parser.py src/momentum_alpha/cli_commands.py src/momentum_alpha/main.py tests/test_cli.py tests/test_main.py
git commit -m "refactor: split cli command handling"
```

### Task 9: Split Market Data Snapshot Assembly

**Files:**
- Create: `src/momentum_alpha/market_data_symbols.py`
- Create: `src/momentum_alpha/market_data_windows.py`
- Create: `src/momentum_alpha/market_data_klines.py`
- Create: `src/momentum_alpha/market_data_cache.py`
- Create: `src/momentum_alpha/market_data_snapshots.py`
- Modify: `src/momentum_alpha/market_data.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `tests/test_market_data.py`

- [x] **Step 1: Add import coverage for market-data modules**

Add this test to `tests/test_market_data.py`:

```python
def test_market_data_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        market_data_cache,
        market_data_klines,
        market_data_snapshots,
        market_data_symbols,
        market_data_windows,
    )

    self.assertTrue(callable(market_data_symbols._resolve_symbols))
    self.assertTrue(callable(market_data_windows._utc_midnight_window_ms))
    self.assertTrue(callable(market_data_klines._fetch_daily_open_klines))
    self.assertTrue(callable(market_data_snapshots._build_live_snapshots))
    self.assertTrue(callable(market_data_cache.LiveMarketDataCache))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_market_data -v
```

Expected: `FAIL` with an import error for one of the new market-data modules.

- [x] **Step 3: Move symbol resolution**

Create `market_data_symbols.py` and move:

```text
_resolve_symbols
```

- [x] **Step 4: Move time-window helpers**

Create `market_data_windows.py` and move:

```text
_utc_midnight_window_ms
_previous_closed_hour_window_ms
_current_hour_window_ms
```

- [x] **Step 5: Move kline fetch helpers**

Create `market_data_klines.py` and move:

```text
_fetch_daily_open_klines
_fetch_previous_hour_klines
_fetch_current_hour_klines
```

- [x] **Step 6: Move cache class**

Create `market_data_cache.py` and move:

```text
LiveMarketDataCache
```

- [x] **Step 7: Move snapshot assembly**

Create `market_data_snapshots.py` and move:

```text
_build_live_snapshots
```

- [x] **Step 8: Preserve `market_data.py` facade exports**

Update `market_data.py` to re-export every moved symbol used by `main.py`, `poll_worker_core.py`, and tests.

- [x] **Step 9: Run market-data tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_market_data tests.test_main -v
```

Expected: `OK`.

- [x] **Step 10: Commit the market-data split**

```bash
git add src/momentum_alpha/market_data.py src/momentum_alpha/market_data_symbols.py src/momentum_alpha/market_data_windows.py src/momentum_alpha/market_data_klines.py src/momentum_alpha/market_data_cache.py src/momentum_alpha/market_data_snapshots.py src/momentum_alpha/main.py tests/test_market_data.py
git commit -m "refactor: split market data assembly"
```

### Task 10: Split User-Stream Event Parsing and Extraction

**Files:**
- Create: `src/momentum_alpha/user_stream_event_model.py`
- Create: `src/momentum_alpha/user_stream_event_parser.py`
- Create: `src/momentum_alpha/user_stream_event_extractors.py`
- Create: `src/momentum_alpha/user_stream_event_ids.py`
- Create: `src/momentum_alpha/user_stream_account_positions.py`
- Modify: `src/momentum_alpha/user_stream_events.py`
- Modify: `src/momentum_alpha/user_stream.py`
- Modify: `tests/test_user_stream_split.py`

- [x] **Step 1: Add import coverage for user-stream event modules**

Add this test to `tests/test_user_stream_split.py`:

```python
def test_user_stream_event_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        user_stream_account_positions,
        user_stream_event_extractors,
        user_stream_event_ids,
        user_stream_event_model,
        user_stream_event_parser,
    )

    self.assertTrue(callable(user_stream_event_model.UserStreamEvent))
    self.assertTrue(callable(user_stream_event_parser.parse_user_stream_event))
    self.assertTrue(callable(user_stream_event_extractors.extract_trade_fill))
    self.assertTrue(callable(user_stream_event_ids.user_stream_event_id))
    self.assertTrue(callable(user_stream_account_positions.extract_positive_account_positions))
```

- [x] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_user_stream_split -v
```

Expected: `FAIL` with an import error for one of the new user-stream event modules.

- [x] **Step 3: Move event model**

Create `user_stream_event_model.py` and move:

```text
UserStreamEvent
```

Move `_parse_decimal` here if both parser and account-position helpers need it.

- [x] **Step 4: Move parser**

Create `user_stream_event_parser.py` and move:

```text
parse_user_stream_event
```

- [x] **Step 5: Move event extractors**

Create `user_stream_event_extractors.py` and move:

```text
extract_trade_fill
extract_account_flows
extract_algo_order_event
extract_order_status_update
extract_algo_order_status_update
```

- [x] **Step 6: Move event id and stop-order predicates**

Create `user_stream_event_ids.py` and move:

```text
user_stream_event_id
_is_strategy_stop_fill
_is_strategy_stop_order_for_symbol
```

- [x] **Step 7: Move account-position helpers**

Create `user_stream_account_positions.py` and move:

```text
extract_flat_position_symbols
extract_positive_account_positions
resolve_stop_price_from_order_statuses
```

- [x] **Step 8: Preserve user-stream facades**

Update `user_stream_events.py` and `user_stream.py` to re-export the moved names used by `stream_worker_core.py`, `stream_worker_loop.py`, `user_stream_state.py`, `main.py`, and tests.

- [x] **Step 9: Run user-stream tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_user_stream tests.test_user_stream_split tests.test_main -v
```

Expected: `OK`.

- [x] **Step 10: Commit the user-stream event split**

```bash
git add src/momentum_alpha/user_stream.py src/momentum_alpha/user_stream_events.py src/momentum_alpha/user_stream_event_model.py src/momentum_alpha/user_stream_event_parser.py src/momentum_alpha/user_stream_event_extractors.py src/momentum_alpha/user_stream_event_ids.py src/momentum_alpha/user_stream_account_positions.py tests/test_user_stream_split.py
git commit -m "refactor: split user stream event parsing"
```

### Task 11: Update Architecture Docs and Run Final Verification

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/superpowers/plans/2026-04-22-architecture-refactor-phase-2.md`

- [x] **Step 1: Update README architecture notes**

In `README.md`, update the architecture/deployment descriptions so they mention:

```text
- CLI command parsing and command execution live behind `momentum_alpha.cli`.
- Poll and user-stream remain separate long-running processes.
- Dashboard is still server-rendered, with focused render, data, view-model, and asset modules.
- Runtime persistence remains SQLite-backed through `runtime_store.py` compatibility exports and focused `runtime_reads_*` / `runtime_writes_*` modules.
```

- [x] **Step 2: Update CLAUDE.md module map**

In `CLAUDE.md`, update the "Key Modules" section so it includes:

```text
- `cli.py` plus `cli_*`: CLI entrypoint, parser, command handlers, environment helpers
- `market_data.py` plus `market_data_*`: live symbol resolution, kline windows, cache, snapshot assembly
- `runtime_store.py`, `runtime_reads_*`, `runtime_writes_*`, `runtime_analytics_*`: SQLite runtime state, telemetry, query, and analytics layers
- `dashboard.py`, `dashboard_data.py`, `dashboard_view_model.py`, `dashboard_render_*`, `dashboard_assets_*`, `dashboard_server.py`: read-only monitoring UI
- `user_stream_events.py` plus `user_stream_event_*`: Binance user-data event model, parsing, idempotency, and extractors
```

- [x] **Step 3: Mark this plan's task table complete**

Update the plan table and task checkboxes after each preceding task has been committed. Leave no completed checkbox unchecked.

- [x] **Step 4: Run final verification**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest discover -s tests -v
```

Expected: `OK`.

- [x] **Step 5: Check diff cleanliness**

Run:

```bash
git diff --check
git status --short
```

Expected: `git diff --check` exits successfully. `git status --short` shows only the intentional documentation changes before the final commit.

- [x] **Step 6: Commit the docs and final verification update**

```bash
git add README.md CLAUDE.md docs/superpowers/plans/2026-04-22-architecture-refactor-phase-2.md
git commit -m "docs: update architecture map after phase 2"
```

---

## Self-Review

- Spec coverage: The plan covers dashboard render/assets, runtime writes/reads/analytics, CLI, market data, user-stream event parsing, architecture boundary tests, documentation, and final full verification.
- Placeholder scan: No `TBD`, `TODO`, or unspecified edge-case tasks are present. Each task names exact files, function groups, commands, expected results, and commit boundaries.
- Type consistency: New module names use the existing project naming style and preserve current facade imports so existing tests and deployment entrypoints continue working.
