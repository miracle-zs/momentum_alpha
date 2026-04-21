# Architecture Refactor Roadmap Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the remaining monolithic dashboard, worker, and stream modules into focused modules while preserving the existing public entrypoints.

**Architecture:** Keep `dashboard.py`, `dashboard_render.py`, `dashboard_assets.py`, `poll_worker.py`, and `user_stream.py` as compatibility facades. Move each file's mixed responsibilities into focused modules with stable boundaries, then re-export the existing public functions and classes from the facade modules. Do not change the runtime behavior or the dashboard HTML shape while splitting.

**Tech Stack:** Python 3.13, `unittest`, existing in-repo helpers and facades.

---

### Task 1: Split dashboard rendering by responsibility

**Files:**
- Create: `src/momentum_alpha/dashboard_render_utils.py`
- Create: `src/momentum_alpha/dashboard_render_tables.py`
- Create: `src/momentum_alpha/dashboard_render_panels.py`
- Create: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_render.py`
- Modify: `tests/test_dashboard_render_split.py`

**Scope:**
- `dashboard_render_utils.py`: room/tab normalization, URL builders, timestamp/price/quantity/percent formatting, and daily-review math helpers.
- `dashboard_render_tables.py`: trade history, closed-trade, leg-aggregate, stop-slippage, position-card, and round-trip row renderers.
- `dashboard_render_panels.py`: account metrics, account snapshot, live risk, live core lines, home command, execution flow, cosmic identity, and daily review panels.
- `dashboard_render_shell.py`: room nav, room/tab wrappers, shell/document/body/html orchestration.
- `dashboard_render.py`: keep as a thin re-export facade.

- [ ] **Step 1: Add failing import coverage for the new dashboard render modules**

```python
from momentum_alpha import dashboard_render_panels, dashboard_render_shell, dashboard_render_tables, dashboard_render_utils

assert callable(dashboard_render_utils.normalize_dashboard_room)
assert callable(dashboard_render_tables.render_trade_history_table)
assert callable(dashboard_render_panels.render_cosmic_identity_panel)
assert callable(dashboard_render_shell.render_dashboard_html)
```

- [ ] **Step 2: Move the pure helpers and table renderers out of `dashboard_render.py`**

```python
# dashboard_render_utils.py
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal
from html import escape
from urllib.parse import urlencode

from .dashboard_common import normalize_account_range, _parse_numeric

# Move normalize_dashboard_room, normalize_review_view, URL builders,
# timestamp formatters, metric formatters, and daily-review math helpers here.

# dashboard_render_tables.py
from __future__ import annotations

from html import escape

from .dashboard_render_utils import (
    _format_duration_seconds,
    _format_metric,
    _format_pct_value,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    format_timestamp_for_display,
    _parse_numeric,
)

# Move the trade/round-trip/aggregate/position renderers here.
```

- [ ] **Step 3: Move panel builders into `dashboard_render_panels.py`**

```python
from __future__ import annotations

from html import escape

from .dashboard_data import build_trade_leg_count_aggregates, build_trade_leg_index_aggregates
from .dashboard_render_tables import render_closed_trades_table, render_position_cards, render_stop_slippage_table, render_trade_history_table
from .dashboard_render_utils import (
    _daily_review_impact,
    _daily_review_win_rate,
    _format_decimal_metric,
    _format_duration_seconds,
    _format_metric,
    _format_pct_value,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    _format_time_only,
    _format_time_short,
    format_timestamp_for_display,
)

# Move account panels, home command, execution flow, cosmic identity, and daily review panel here.
```

- [ ] **Step 4: Move the shell/body orchestration into `dashboard_render_shell.py`**

```python
from __future__ import annotations

from html import escape

from .dashboard_assets import render_dashboard_head, render_dashboard_scripts
from .dashboard_common import normalize_account_range
from .dashboard_data import build_dashboard_timeseries_payload, build_trade_leg_count_aggregates, build_trade_leg_index_aggregates
from .dashboard_render_panels import (
    _build_account_metrics_panel,
    _build_account_snapshot_panel,
    _build_execution_flow_panel,
    _build_live_account_risk_panel,
    _build_live_core_lines_panel,
    _build_overview_home_command,
    _build_execution_mode,
    render_cosmic_identity_panel,
    render_daily_review_panel,
)

# Move room nav, room/tab wrappers, shell/document/body/html here.
```

- [ ] **Step 5: Run the focused dashboard render tests**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard tests.test_dashboard_render -v`

Expected: `OK`

- [ ] **Step 6: Commit the dashboard render split**

```bash
git add src/momentum_alpha/dashboard_render.py src/momentum_alpha/dashboard_render_utils.py src/momentum_alpha/dashboard_render_tables.py src/momentum_alpha/dashboard_render_panels.py src/momentum_alpha/dashboard_render_shell.py tests/test_dashboard_render_split.py
git commit -m "refactor: split dashboard render"
```

### Task 2: Split dashboard assets by responsibility

**Files:**
- Create: `src/momentum_alpha/dashboard_assets_styles.py`
- Create: `src/momentum_alpha/dashboard_assets_head.py`
- Create: `src/momentum_alpha/dashboard_assets_scripts.py`
- Modify: `src/momentum_alpha/dashboard_assets.py`
- Modify: `tests/test_dashboard_assets.py`

**Scope:**
- `dashboard_assets_styles.py`: all style-string builders and `render_dashboard_styles`.
- `dashboard_assets_head.py`: head wrapper that injects the stylesheet bundle.
- `dashboard_assets_scripts.py`: dashboard client-side script bundle.
- `dashboard_assets.py`: thin re-export facade.

- [ ] **Step 1: Add failing import coverage for the split asset modules**

```python
from momentum_alpha import dashboard_assets_styles, dashboard_assets_head, dashboard_assets_scripts

assert callable(dashboard_assets_styles.render_dashboard_styles)
assert callable(dashboard_assets_head.render_dashboard_head)
assert callable(dashboard_assets_scripts.render_dashboard_scripts)
```

- [ ] **Step 2: Move the CSS builders into `dashboard_assets_styles.py`**

```python
from __future__ import annotations

# Move _render_dashboard_base_styles, _render_dashboard_cosmic_styles,
# _render_dashboard_component_styles, _render_dashboard_responsive_styles,
# and render_dashboard_styles here.
```

- [ ] **Step 3: Move the head wrapper into `dashboard_assets_head.py`**

```python
from __future__ import annotations

from .dashboard_assets_styles import render_dashboard_styles

# Move render_dashboard_head here.
```

- [ ] **Step 4: Move the dashboard script bundle into `dashboard_assets_scripts.py`**

```python
from __future__ import annotations

# Move render_dashboard_scripts and its helper constants here.
```

- [ ] **Step 5: Run the focused dashboard asset tests**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_assets -v`

Expected: `OK`

- [ ] **Step 6: Commit the dashboard asset split**

```bash
git add src/momentum_alpha/dashboard_assets.py src/momentum_alpha/dashboard_assets_styles.py src/momentum_alpha/dashboard_assets_head.py src/momentum_alpha/dashboard_assets_scripts.py tests/test_dashboard_assets.py
git commit -m "refactor: split dashboard assets"
```

### Task 3: Split poll worker orchestration from the loop

**Files:**
- Create: `src/momentum_alpha/poll_worker_core.py`
- Create: `src/momentum_alpha/poll_worker_loop.py`
- Modify: `src/momentum_alpha/poll_worker.py`
- Modify: `tests/test_poll_worker.py`

**Scope:**
- `poll_worker_core.py`: `RunOnceResult`, `_save_strategy_state`, `build_runtime_from_snapshots`, `run_once`, and `run_once_live`.
- `poll_worker_loop.py`: `run_forever`.
- `poll_worker.py`: compatibility facade.

- [ ] **Step 1: Add failing import coverage for the split poll worker modules**

```python
from momentum_alpha import poll_worker_core, poll_worker_loop

assert callable(poll_worker_core.run_once)
assert callable(poll_worker_core.run_once_live)
assert callable(poll_worker_loop.run_forever)
```

- [ ] **Step 2: Move the core tick logic into `poll_worker_core.py`**

```python
from __future__ import annotations

from dataclasses import dataclass, replace

# Move RunOnceResult, _save_strategy_state, build_runtime_from_snapshots,
# run_once, and run_once_live here.
```

- [ ] **Step 3: Move the forever loop into `poll_worker_loop.py`**

```python
from __future__ import annotations

# Move run_forever here and import run_once_live from poll_worker_core.py.
```

- [ ] **Step 4: Run the focused poll worker tests**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_poll_worker -v`

Expected: `OK`

- [ ] **Step 5: Commit the poll worker split**

```bash
git add src/momentum_alpha/poll_worker.py src/momentum_alpha/poll_worker_core.py src/momentum_alpha/poll_worker_loop.py tests/test_poll_worker.py
git commit -m "refactor: split poll worker"
```

### Task 4: Split user stream parsing, state, and client code

**Files:**
- Create: `src/momentum_alpha/user_stream_events.py`
- Create: `src/momentum_alpha/user_stream_state.py`
- Create: `src/momentum_alpha/user_stream_client.py`
- Modify: `src/momentum_alpha/user_stream.py`
- Modify: `tests/test_user_stream.py`

**Scope:**
- `user_stream_events.py`: `UserStreamEvent`, parsing helpers, and event extractors.
- `user_stream_state.py`: `apply_user_stream_event_to_state` plus stop-order/state helpers.
- `user_stream_client.py`: `BinanceUserStreamClient` and the websocket/keepalive runners.
- `user_stream.py`: compatibility facade.

- [ ] **Step 1: Add failing import coverage for the split user stream modules**

```python
from momentum_alpha import user_stream_events, user_stream_state, user_stream_client

assert callable(user_stream_events.parse_user_stream_event)
assert callable(user_stream_state.apply_user_stream_event_to_state)
assert callable(user_stream_client.BinanceUserStreamClient)
```

- [ ] **Step 2: Move event parsing and extractors into `user_stream_events.py`**

```python
from __future__ import annotations

# Move UserStreamEvent, _parse_decimal, parse_user_stream_event,
# extract_trade_fill, extract_account_flows, extract_algo_order_event,
# user_stream_event_id, extract_order_status_update,
# extract_algo_order_status_update, extract_flat_position_symbols,
# extract_positive_account_positions, and resolve_stop_price_from_order_statuses here.
```

- [ ] **Step 3: Move state application logic into `user_stream_state.py`**

```python
from __future__ import annotations

# Move _is_strategy_stop_fill, _is_strategy_stop_order_for_symbol,
# and apply_user_stream_event_to_state here.
```

- [ ] **Step 4: Move the client into `user_stream_client.py`**

```python
from __future__ import annotations

# Move BinanceUserStreamClient, _default_websocket_runner,
# and _default_keepalive_runner here.
```

- [ ] **Step 5: Run the focused user stream tests**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_user_stream -v`

Expected: `OK`

- [ ] **Step 6: Commit the user stream split**

```bash
git add src/momentum_alpha/user_stream.py src/momentum_alpha/user_stream_events.py src/momentum_alpha/user_stream_state.py src/momentum_alpha/user_stream_client.py tests/test_user_stream.py
git commit -m "refactor: split user stream"
```

### Task 5: Finish with a full verification sweep

**Files:**
- No new files expected.

- [ ] **Step 1: Run the full test suite**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest discover -s tests -v`

Expected: `OK`

- [ ] **Step 2: Check for formatting drift**

Run: `git diff --check`

Expected: no output

- [ ] **Step 3: Review the remaining refactor surface**

If `dashboard_view_model.py` and `dashboard_data.py` still look cohesive, leave them intact. If later work shows a concrete mixed responsibility, add a new plan rather than widening this one.

