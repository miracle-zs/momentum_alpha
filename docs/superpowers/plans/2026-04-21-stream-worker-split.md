# Stream Worker Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split `src/momentum_alpha/stream_worker.py` into a compatibility facade, a core event-processing module, and a loop/orchestration module without changing runtime behavior or breaking existing monkeypatch-based tests.

**Architecture:** `stream_worker_core.py` owns the per-event handler, de-duplication, persistence, and state updates. `stream_worker_loop.py` owns state hydration, REST prewarm, stream-client lifecycle, and reconnect/backoff. `stream_worker.py` stays as the compatibility facade and forwards its bound helper callables into the new implementation so patches against `momentum_alpha.stream_worker.*` still affect runtime behavior.

**Tech Stack:** Python 3.13, `unittest`, existing SQLite runtime DB helpers, existing audit/telemetry helpers, existing user-stream parser/state modules.

---

## File Map

- `src/momentum_alpha/stream_worker_core.py`: event handler construction, processed-event pruning, strategy-state persistence.
- `src/momentum_alpha/stream_worker_loop.py`: stored-state hydration, REST prewarm, reconnect loop, public `run_user_stream`.
- `src/momentum_alpha/stream_worker.py`: compatibility facade that re-exports the runtime-facing names and forwards module-bound callables into the loop/core implementation.
- `tests/test_stream_worker_split.py`: split-specific smoke tests for the new modules and the facade contract.
- `tests/test_main.py`: existing monkeypatch-based integration coverage; no structure changes expected, but the tests must still pass.

---

### Task 1: Lock the split contract with smoke tests

**Files:**
- Create: `tests/test_stream_worker_split.py`

**Scope:**
- Verify that the new modules import cleanly.
- Verify that the facade still exports the callables that `main.py` and existing tests depend on.
- Add one direct regression test for the core helper that prunes old processed event IDs.

- [ ] **Step 1: Write the failing import and contract tests**

```python
from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class StreamWorkerSplitTests(unittest.TestCase):
    def test_split_modules_import_and_expose_worker_entrypoints(self) -> None:
        from momentum_alpha import stream_worker, stream_worker_core, stream_worker_loop

        self.assertTrue(callable(stream_worker.run_user_stream))
        self.assertTrue(callable(stream_worker_core._prune_processed_event_ids))
        self.assertTrue(callable(stream_worker_core._save_user_stream_strategy_state))
        self.assertTrue(callable(stream_worker_loop.run_user_stream))

    def test_facade_still_exports_patch_targets(self) -> None:
        from momentum_alpha import stream_worker

        self.assertTrue(callable(stream_worker.extract_trade_fill))
        self.assertTrue(callable(stream_worker.insert_trade_fill))
        self.assertTrue(callable(stream_worker.insert_account_flow))
        self.assertTrue(callable(stream_worker.insert_algo_order))

    def test_prune_processed_event_ids_keeps_recent_entries(self) -> None:
        from momentum_alpha.stream_worker_core import _prune_processed_event_ids

        now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
        pruned = _prune_processed_event_ids(
            {
                "recent-1": "2026-04-15T10:00:00+00:00",
                "recent-2": "2026-04-15T11:00:00+00:00",
                "old-1": "2026-04-13T12:00:00+00:00",
            },
            now,
        )

        self.assertEqual(set(pruned.keys()), {"recent-1", "recent-2"})

    def test_save_user_stream_strategy_state_preserves_previous_leader_symbol(self) -> None:
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.stream_worker_core import _save_user_stream_strategy_state
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    positions={},
                    processed_event_ids={"evt-1": "2026-04-15T01:00:00+00:00"},
                    order_statuses={"123": {"symbol": "ETHUSDT", "status": "NEW"}},
                    recent_stop_loss_exits={},
                )
            )

            _save_user_stream_strategy_state(
                runtime_state_store=store,
                state=StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="ETHUSDT",
                    positions={},
                    processed_event_ids={
                        "evt-1": "2026-04-15T01:00:00+00:00",
                        "evt-2": "2026-04-15T02:00:00+00:00",
                    },
                    order_statuses={"123": {"symbol": "ETHUSDT", "status": "FILLED"}},
                    recent_stop_loss_exits={},
                ),
                now=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
            )

            loaded = store.load()

        self.assertEqual(loaded.previous_leader_symbol, "BTCUSDT")
        self.assertEqual(
            loaded.processed_event_ids,
            {
                "evt-1": "2026-04-15T01:00:00+00:00",
                "evt-2": "2026-04-15T02:00:00+00:00",
            },
        )
        self.assertEqual(loaded.order_statuses["123"]["status"], "FILLED")
```

- [ ] **Step 2: Run the new smoke test before the refactor**

Run: `/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_stream_worker_split -v`

Expected: fail with import errors until `stream_worker_core.py` and `stream_worker_loop.py` exist.

- [ ] **Step 3: Commit the test file once the split is in place**

```bash
git add tests/test_stream_worker_split.py
git commit -m "test: add stream worker split coverage"
```

---

### Task 2: Extract the core event-processing module

**Files:**
- Create: `src/momentum_alpha/stream_worker_core.py`
- Modify: `src/momentum_alpha/stream_worker.py`

**Scope:**
- Move `_prune_processed_event_ids` and `_save_user_stream_strategy_state` out of the monolith.
- Add a core helper that builds the per-event handler closure and owns the event-level persistence flow.
- Keep the existing error messages and audit-event names unchanged.
- Preserve monkeypatch behavior by letting the facade pass its bound helper callables into the core helper explicitly.

- [ ] **Step 1: Move the core helpers into `stream_worker_core.py`**

```python
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from collections.abc import Callable

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
from momentum_alpha.runtime_store import (
    MAX_PROCESSED_EVENT_ID_AGE_HOURS,
    RuntimeStateStore,
    insert_account_flow,
    insert_algo_order,
    insert_trade_fill,
)
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.telemetry import _record_broker_orders, _record_position_snapshot
from momentum_alpha.user_stream import (
    UserStreamEvent,
    apply_user_stream_event_to_state,
    extract_account_flows,
    extract_algo_order_event,
    extract_algo_order_status_update,
    extract_order_status_update,
    extract_trade_fill,
    user_stream_event_id,
)

def _prune_processed_event_ids(
    processed_event_ids: dict[str, str] | None,
    now: datetime,
) -> dict[str, str]:
    pass

def _save_user_stream_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
    now: datetime,
) -> None:
    pass
```

- [ ] **Step 2: Add `build_user_stream_event_handler` and move the current `_on_event` body into it**

```python
def build_user_stream_event_handler(
    *,
    logger,
    runtime_state_store: RuntimeStateStore | None,
    audit_recorder: AuditRecorder | None,
    now_provider,
    state: StrategyState,
    processed_event_ids: dict[str, str],
    order_statuses: dict[str, dict[str, object]],
    extract_trade_fill_fn=extract_trade_fill,
    extract_algo_order_event_fn=extract_algo_order_event,
    extract_account_flows_fn=extract_account_flows,
    extract_order_status_update_fn=extract_order_status_update,
    extract_algo_order_status_update_fn=extract_algo_order_status_update,
    user_stream_event_id_fn=user_stream_event_id,
    apply_user_stream_event_to_state_fn=apply_user_stream_event_to_state,
    insert_trade_fill_fn=insert_trade_fill,
    insert_algo_order_fn=insert_algo_order,
    insert_account_flow_fn=insert_account_flow,
    record_broker_orders_fn=_record_broker_orders,
    record_position_snapshot_fn=_record_position_snapshot,
    save_user_stream_strategy_state_fn=_save_user_stream_strategy_state,
) -> Callable[[UserStreamEvent], None]:
    def _on_event(event: UserStreamEvent) -> None:
        pass

    return _on_event
```

The body that moves into `_on_event` should remain behaviorally identical to the current monolith:

- keep `user_stream_event` audit records
- keep `stream_order_update` broker-order recording
- keep duplicate-event short-circuiting
- keep trade-fill, algo-order, and account-flow insert logging unchanged
- keep `account_flow_insert_error` audit records
- keep `order_statuses` updates unchanged
- keep the `apply_user_stream_event_to_state` call unchanged
- keep state persistence through `_save_user_stream_strategy_state`
- keep the final `_record_position_snapshot` call unchanged

- [ ] **Step 3: Point `stream_worker.py` at the new core module without breaking patch targets**

The facade should continue to define and export the same module-level names that current tests patch:

- `extract_trade_fill`
- `insert_trade_fill`
- `insert_account_flow`
- `insert_algo_order`
- `_record_broker_orders`
- `_record_position_snapshot`
- `run_user_stream`

The facade should call into the new core helper by passing those bound names explicitly as keyword arguments, so a patch on `momentum_alpha.stream_worker.insert_trade_fill` still changes the runtime path.

---

### Task 3: Extract the loop and reconnect orchestration

**Files:**
- Create: `src/momentum_alpha/stream_worker_loop.py`
- Modify: `src/momentum_alpha/stream_worker.py`

**Scope:**
- Move `run_user_stream`, the REST prewarm step, and the reconnect/backoff loop into `stream_worker_loop.py`.
- Keep state hydration in the loop module so the core module only handles event-level work.
- Keep the prewarm logic, reconnect log strings, and retry behavior unchanged.

- [ ] **Step 1: Move the worker bootstrap and loop into `stream_worker_loop.py`**

```python
from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path
from collections.abc import Callable

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import restore_state
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.user_stream import BinanceUserStreamClient

from .stream_worker_core import build_user_stream_event_handler

def _build_initial_user_stream_state(
    stored_state: StoredStrategyState | None,
    current_now: datetime,
) -> tuple[StrategyState, dict[str, str], dict[str, dict[str, object]]]:
    pass

def run_user_stream(
    *,
    client,
    testnet: bool,
    logger,
    runtime_state_store: RuntimeStateStore | None = None,
    now_provider=None,
    stream_client_factory=None,
    reconnect_sleep_fn=None,
    runtime_db_path: Path | None = None,
    event_handler_factory=build_user_stream_event_handler,
    extract_trade_fill_fn=None,
    extract_algo_order_event_fn=None,
    extract_account_flows_fn=None,
    extract_order_status_update_fn=None,
    extract_algo_order_status_update_fn=None,
    user_stream_event_id_fn=None,
    apply_user_stream_event_to_state_fn=None,
    insert_trade_fill_fn=None,
    insert_algo_order_fn=None,
    insert_account_flow_fn=None,
    record_broker_orders_fn=None,
    record_position_snapshot_fn=None,
    save_user_stream_strategy_state_fn=None,
    prune_processed_event_ids_fn=None,
) -> int:
    pass
```

The loop module should keep these behaviors unchanged:

- load the stored snapshot once at startup
- build `StrategyState`, `processed_event_ids`, and `order_statuses` from the snapshot
- prewarm positions and open orders before each connection attempt
- ignore optional open-algo fetch failures
- reconnect with bounded sleep backoff after stream failure
- log the returned listen key on successful stream completion

- [ ] **Step 2: Make the loop module use the core event-handler factory**

The loop should pass the runtime-facing callables it receives into `build_user_stream_event_handler` and then hand the returned closure to `stream_client.run_forever(on_event=<handler>)`.

The facade must continue to be the only place that binds the current module-level helper names, because that is what keeps `momentum_alpha.stream_worker.*` monkeypatches effective.

- [ ] **Step 3: Keep the prewarm logic and retry semantics identical**

The current prewarm block should stay functionally the same:

- fetch `position_risk`
- fetch `open_orders`
- fetch `open_algo_orders` only when the client exposes it
- swallow the optional open-algo fetch exception and continue with an empty list
- rebuild `order_statuses` from the REST open-order snapshots
- restore positions with `restore_state`
- save the updated runtime snapshot when `runtime_state_store` is available

---

### Task 4: Rewrite the facade and preserve the public import surface

**Files:**
- Modify: `src/momentum_alpha/stream_worker.py`

**Scope:**
- Turn `stream_worker.py` into a thin facade.
- Re-export the runtime-facing names used by `main.py` and the existing tests.
- Forward the monkeypatch-sensitive callables into the loop/core implementation explicitly.

- [ ] **Step 1: Replace the monolith with explicit facade imports and a forwarding `run_user_stream`**

```python
from __future__ import annotations

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import restore_state
from momentum_alpha.runtime_store import (
    MAX_PROCESSED_EVENT_ID_AGE_HOURS,
    RuntimeStateStore,
    insert_account_flow,
    insert_algo_order,
    insert_trade_fill,
)
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.telemetry import _record_broker_orders, _record_position_snapshot
from momentum_alpha.user_stream import (
    BinanceUserStreamClient,
    apply_user_stream_event_to_state,
    extract_account_flows,
    extract_algo_order_event,
    extract_algo_order_status_update,
    extract_order_status_update,
    extract_trade_fill,
    user_stream_event_id,
)

from .stream_worker_core import _prune_processed_event_ids, _save_user_stream_strategy_state
from .stream_worker_loop import run_user_stream as _run_user_stream_impl

def run_user_stream(**kwargs):
    return _run_user_stream_impl(
        **kwargs,
        extract_trade_fill_fn=extract_trade_fill,
        extract_algo_order_event_fn=extract_algo_order_event,
        extract_account_flows_fn=extract_account_flows,
        extract_order_status_update_fn=extract_order_status_update,
        extract_algo_order_status_update_fn=extract_algo_order_status_update,
        user_stream_event_id_fn=user_stream_event_id,
        apply_user_stream_event_to_state_fn=apply_user_stream_event_to_state,
        insert_trade_fill_fn=insert_trade_fill,
        insert_algo_order_fn=insert_algo_order,
        insert_account_flow_fn=insert_account_flow,
        record_broker_orders_fn=_record_broker_orders,
        record_position_snapshot_fn=_record_position_snapshot,
        save_user_stream_strategy_state_fn=_save_user_stream_strategy_state,
        prune_processed_event_ids_fn=_prune_processed_event_ids,
    )
```

This facade must continue to export the names imported by `src/momentum_alpha/main.py`:

- `_prune_processed_event_ids`
- `_save_user_stream_strategy_state`
- `run_user_stream`

It must also continue to expose the runtime dependencies that the existing patch-based tests reference directly:

- `extract_trade_fill`
- `insert_trade_fill`
- `insert_account_flow`
- `insert_algo_order`

It should keep the broader runtime-facing names importable as well:

- `AuditRecorder`
- `RuntimeStateStore`
- `StoredStrategyState`
- `StrategyState`
- `MAX_PROCESSED_EVENT_ID_AGE_HOURS`
- `restore_state`
- `BinanceUserStreamClient`
- `apply_user_stream_event_to_state`
- `extract_account_flows`
- `extract_algo_order_event`
- `extract_algo_order_status_update`
- `extract_order_status_update`
- `user_stream_event_id`
- `_record_broker_orders`
- `_record_position_snapshot`

- [ ] **Step 2: Leave `src/momentum_alpha/main.py` and `src/momentum_alpha/cli.py` untouched unless an import fails**

Those modules already import from the facade. The split should work without call-site edits if the facade keeps the same exported names.

---

### Task 5: Verify the split and commit it

**Files:**
- Modify: `src/momentum_alpha/stream_worker.py`
- Modify: `src/momentum_alpha/stream_worker_core.py`
- Modify: `src/momentum_alpha/stream_worker_loop.py`
- Modify: `tests/test_stream_worker_split.py`

**Scope:**
- Run the focused split smoke tests.
- Run the existing `stream_worker` and `main` coverage that exercises the monkeypatch boundary.
- Run the full test suite.
- Check for formatting regressions.
- Commit the split once everything is green.

- [ ] **Step 1: Run the focused stream-worker tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_stream_worker_split tests.test_stream_worker tests.test_main -v
```

Expected: `OK` with all three modules passing.

- [ ] **Step 2: Run the full test suite**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest discover -s tests -v
```

Expected: `OK`.

- [ ] **Step 3: Check formatting and commit the split**

Run:

```bash
git diff --check
git add src/momentum_alpha/stream_worker.py src/momentum_alpha/stream_worker_core.py src/momentum_alpha/stream_worker_loop.py tests/test_stream_worker_split.py
git commit -m "refactor: split stream worker"
```

Expected: no diff-check output and a new commit on `codex/architecture-refactor`.
