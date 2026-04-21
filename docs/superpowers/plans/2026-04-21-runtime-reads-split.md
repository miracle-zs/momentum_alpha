# Runtime Reads Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the monolithic `runtime_reads` layer into focused modules for event-log reads and historical/reporting reads while preserving the existing public facade and call sites.

**Architecture:** Keep `runtime_reads.py` as a compatibility facade. Move low-level SQL query helpers and row-shaping logic into small domain modules with stable boundaries: one for audit/event streams, one for historical reporting and dashboard-facing queries, and one tiny shared helper module for common JSON/time conversion. Re-export the current public read functions from the facade so `runtime_store.py`, `dashboard_data.py`, and existing tests continue to work unchanged.

**Tech Stack:** Python 3.13, `unittest`, existing SQLite helpers in `runtime_schema.py`, existing facade pattern in `runtime_store.py` and `dashboard.py`.

---

### Task 1: Add split coverage for the new read modules

**Files:**
- Create: `tests/test_runtime_reads_split.py`

**Scope:**
- Verify that the new read modules import cleanly and expose the functions that will move out of `runtime_reads.py`.

- [ ] **Step 1: Write the failing import coverage**

```python
from momentum_alpha import runtime_reads_common, runtime_reads_events, runtime_reads_history

assert callable(runtime_reads_events.fetch_recent_audit_events)
assert callable(runtime_reads_events.fetch_recent_signal_decisions)
assert callable(runtime_reads_history.fetch_recent_trade_round_trips)
assert callable(runtime_reads_history.fetch_account_snapshots_for_range)
```

- [ ] **Step 2: Run the split coverage test and confirm it fails before the refactor**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads_split -v`

Expected: fail with import errors until the new modules exist.

### Task 2: Extract shared helpers and event-log readers

**Files:**
- Create: `src/momentum_alpha/runtime_reads_common.py`
- Create: `src/momentum_alpha/runtime_reads_events.py`
- Modify: `src/momentum_alpha/runtime_reads.py`
- Modify: `src/momentum_alpha/runtime_store.py` only if the facade imports need to be adjusted

**Scope:**
- `runtime_reads_common.py`: `_json_loads`, `_as_utc_iso`, `_trade_round_trip_row_to_dict`, and any shared range constants needed by the historical queries.
- `runtime_reads_events.py`: `fetch_notification_status`, `fetch_recent_audit_events`, `fetch_audit_event_counts`, `fetch_recent_signal_decisions`, `fetch_signal_decisions_for_window`, `fetch_recent_broker_orders`, `fetch_recent_trade_fills`, `fetch_recent_algo_orders`, `fetch_recent_account_flows`, and `fetch_account_flows_since`.
- `runtime_reads.py`: remain a thin facade that re-exports the existing public read helpers.

- [ ] **Step 1: Move the common JSON/time helpers into `runtime_reads_common.py`**

```python
from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

_ACCOUNT_RANGE_DENSITY = {
    "1D": (timedelta(days=1), 60 * 60),
    "1W": (timedelta(days=7), 6 * 60 * 60),
    "1M": (timedelta(days=30), 24 * 60 * 60),
    "1Y": (timedelta(days=365), 7 * 24 * 60 * 60),
    "ALL": (None, 24 * 60 * 60),
}

def _json_loads(payload: str) -> dict:
    return json.loads(payload)

def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()

def _trade_round_trip_row_to_dict(row: tuple) -> dict:
    return {
        "round_trip_id": row[0],
        "symbol": row[1],
        "opened_at": row[2],
        "closed_at": row[3],
        "entry_fill_count": row[4],
        "exit_fill_count": row[5],
        "total_entry_quantity": row[6],
        "total_exit_quantity": row[7],
        "weighted_avg_entry_price": row[8],
        "weighted_avg_exit_price": row[9],
        "realized_pnl": row[10],
        "commission": row[11],
        "net_pnl": row[12],
        "exit_reason": row[13],
        "duration_seconds": row[14],
        "payload": _json_loads(row[15]),
    }
```

- [ ] **Step 2: Move the event-log readers into `runtime_reads_events.py`**

```python
from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_reads_common import _json_loads

# Move the notification, audit, signal, broker, fill, algo, and account-flow readers here.
```

- [ ] **Step 3: Move the `runtime_reads.py` facade over to the new modules**

```python
from __future__ import annotations

from .runtime_reads_events import (
    fetch_account_flows_since,
    fetch_audit_event_counts,
    fetch_notification_status,
    fetch_recent_account_flows,
    fetch_recent_algo_orders,
    fetch_recent_audit_events,
    fetch_recent_broker_orders,
    fetch_recent_signal_decisions,
    fetch_recent_trade_fills,
    fetch_signal_decisions_for_window,
)
from .runtime_reads_history import (
    fetch_account_snapshots_for_range,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_latest_daily_review_report,
    fetch_recent_account_snapshots,
    fetch_recent_position_snapshots,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_round_trips,
    fetch_trade_round_trips_for_range,
    fetch_trade_round_trips_for_window,
    summarize_audit_events,
)
```

### Task 3: Extract history and dashboard-facing readers

**Files:**
- Create: `src/momentum_alpha/runtime_reads_history.py`
- Modify: `src/momentum_alpha/runtime_reads.py`
- Modify: `src/momentum_alpha/dashboard_data.py` only if import paths need to change

**Scope:**
- `runtime_reads_history.py`: `fetch_recent_trade_round_trips`, `fetch_trade_round_trips_for_range`, `fetch_trade_round_trips_for_window`, `fetch_latest_daily_review_report`, `fetch_recent_stop_exit_summaries`, `fetch_recent_position_snapshots`, `fetch_recent_account_snapshots`, `fetch_account_snapshots_for_range`, `fetch_leader_history`, `fetch_event_pulse_points`, and `summarize_audit_events`.
- Keep the query shapes identical so dashboard payloads and the runtime store keep the same JSON shape.

- [ ] **Step 1: Move the history/report queries into `runtime_reads_history.py`**

```python
from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _ACCOUNT_RANGE_DENSITY, _as_utc_iso, _json_loads, _trade_round_trip_row_to_dict

# Move the round-trip, daily-review, snapshot, leader-history, pulse, and summary readers here.
```

- [ ] **Step 2: Keep the facade exports identical**

```python
# runtime_reads.py should continue to export the same public names
# so runtime_store.py and dashboard_data.py do not need call-site changes.
```

### Task 4: Verify the split and commit it

**Files:**
- Modify: `src/momentum_alpha/runtime_reads.py`
- Modify: `src/momentum_alpha/runtime_store.py` if any imports need to be grouped differently
- Modify: `tests/test_runtime_reads.py`
- Modify: `tests/test_runtime_store.py` only if a split-specific assertion needs to be added

- [ ] **Step 1: Run the focused runtime read tests**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads_split tests.test_runtime_reads tests.test_runtime_store -v`

Expected: `OK`

- [ ] **Step 2: Run the full test suite**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest discover -s tests -v`

Expected: `OK`

- [ ] **Step 3: Check for formatting regressions and commit**

Run: `git diff --check`

Expected: no output

```bash
git add src/momentum_alpha/runtime_reads.py src/momentum_alpha/runtime_reads_common.py src/momentum_alpha/runtime_reads_events.py src/momentum_alpha/runtime_reads_history.py tests/test_runtime_reads_split.py
git commit -m "refactor: split runtime reads"
```
