# User Stream Debounced Rebuild Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rebuild `trade_round_trips` automatically from `user-stream` after committed fills, using a 30-second debounce so bursty fills only trigger one analytics rebuild.

**Architecture:** Add a small in-process scheduler module that coalesces fill notifications and runs the existing rebuild command in a background worker. Wire the scheduler into the user-stream event path only after `trade_fills` inserts succeed, and close it cleanly when `run_user_stream` exits. Keep the manual `rebuild-trade-analytics` command unchanged.

**Tech Stack:** Python 3.11, `threading`, existing SQLite runtime store, `unittest`.

---

## File Map

- Create: `src/momentum_alpha/stream_worker_rebuild_scheduler.py`
- Modify: `src/momentum_alpha/stream_worker_core.py`
- Modify: `src/momentum_alpha/stream_worker_loop.py`
- Modify: `src/momentum_alpha/stream_worker.py`
- Create: `tests/test_stream_worker_rebuild_scheduler.py`
- Modify: `tests/test_stream_worker_split.py`

## Task 1: Add a debounced rebuild scheduler module

**Files:**
- Create: `src/momentum_alpha/stream_worker_rebuild_scheduler.py`
- Create: `tests/test_stream_worker_rebuild_scheduler.py`

- [ ] **Step 1: Write the failing tests**

Add tests that describe the required behavior of a scheduler object with a 30-second debounce window.

```python
from __future__ import annotations

import unittest
from datetime import datetime, timezone
from momentum_alpha.stream_worker_rebuild_scheduler import DebouncedRebuildScheduler


class DebouncedRebuildSchedulerTests(unittest.TestCase):
    def test_multiple_notifications_within_window_trigger_one_rebuild(self) -> None:
        now_values = [
            datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 20, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 50, tzinfo=timezone.utc),
        ]
        calls: list[datetime] = []

        def now_provider() -> datetime:
            return now_values.pop(0)

        scheduler = DebouncedRebuildScheduler(
            debounce_seconds=30,
            now_provider=now_provider,
            rebuild_fn=lambda: calls.append(now_provider()),
            logger=lambda msg: None,
        )

        scheduler.notify()
        scheduler.notify()
        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.close()

        self.assertEqual(len(calls), 1)
```

Add a second test for error handling:

```python
    def test_rebuild_errors_are_logged_and_do_not_stop_future_runs(self) -> None:
        logs: list[str] = []
        calls: list[str] = []

        scheduler = DebouncedRebuildScheduler(
            debounce_seconds=30,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc),
            rebuild_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            logger=logs.append,
        )

        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.close()

        self.assertTrue(any("boom" in line for line in logs))
        self.assertEqual(calls, [])
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
./.venv/bin/python -m unittest tests.test_stream_worker_rebuild_scheduler -v
```

Expected: fail because `DebouncedRebuildScheduler` and the test helpers do not exist yet.

- [ ] **Step 3: Implement the minimal scheduler**

Implement `DebouncedRebuildScheduler` with these rules:

```python
class DebouncedRebuildScheduler:
    def __init__(self, *, debounce_seconds, now_provider, rebuild_fn, logger):
        pass

    def notify(self) -> None:
        pass

    def flush_for_test(self) -> None:
        pass

    def close(self) -> None:
        pass
```

Implementation constraints:

- use a private background thread or equivalent worker loop so `user-stream` does not block
- coalesce repeated `notify()` calls into one rebuild
- keep the last notification time and wait until it is quiet for 30 seconds
- catch rebuild exceptions, log them, and keep the scheduler alive
- make the worker stoppable with `close()`
- keep test hooks explicit so the unit tests do not depend on wall-clock sleeping

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```bash
./.venv/bin/python -m unittest tests.test_stream_worker_rebuild_scheduler -v
```

Expected: PASS.

- [ ] **Step 5: Commit this slice**

```bash
git add src/momentum_alpha/stream_worker_rebuild_scheduler.py tests/test_stream_worker_rebuild_scheduler.py
git commit -m "feat: add debounced rebuild scheduler"
```

## Task 2: Wire fill persistence to the scheduler

**Files:**
- Modify: `src/momentum_alpha/stream_worker_core.py`
- Modify: `src/momentum_alpha/stream_worker_loop.py`
- Modify: `src/momentum_alpha/stream_worker.py`
- Modify: `tests/test_stream_worker_split.py`

- [ ] **Step 1: Write the failing tests**

Add tests that prove the rebuild trigger only fires after a fill is successfully persisted.

```python
from __future__ import annotations

import sys
import unittest
from datetime import date, datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StreamWorkerRebuildHookTests(unittest.TestCase):
    def test_trade_fill_success_triggers_rebuild_hook_once(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext, build_user_stream_event_handler
        from momentum_alpha.user_stream import parse_user_stream_event

        calls: list[str] = []
        context = UserStreamWorkerContext(
            state=StrategyState(current_day=date(2026, 4, 21), previous_leader_symbol=None, positions={}),
            processed_event_ids={},
            order_statuses={},
        )
        handler = build_user_stream_event_handler(
            logger=lambda msg: None,
            runtime_state_store=None,
            audit_recorder=None,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            context=context,
            on_trade_fill_persisted_fn=lambda: calls.append("rebuild"),
        )

        handler(parse_user_stream_event({"e": "ORDER_TRADE_UPDATE", "o": {"s": "BTCUSDT", "X": "FILLED", "x": "TRADE"}}))

        self.assertEqual(calls, ["rebuild"])

    def test_trade_fill_insert_failure_does_not_trigger_rebuild_hook(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext, build_user_stream_event_handler
        from momentum_alpha.user_stream import parse_user_stream_event

        calls: list[str] = []
        context = UserStreamWorkerContext(
            state=StrategyState(current_day=date(2026, 4, 21), previous_leader_symbol=None, positions={}),
            processed_event_ids={},
            order_statuses={},
        )

        def failing_insert_trade_fill_fn(**kwargs):
            raise RuntimeError("insert failed")

        handler = build_user_stream_event_handler(
            logger=lambda msg: None,
            runtime_state_store=None,
            audit_recorder=None,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            context=context,
            insert_trade_fill_fn=failing_insert_trade_fill_fn,
            on_trade_fill_persisted_fn=lambda: calls.append("rebuild"),
        )

        handler(parse_user_stream_event({"e": "ORDER_TRADE_UPDATE", "o": {"s": "BTCUSDT", "X": "FILLED", "x": "TRADE"}}))

        self.assertEqual(calls, [])
```

Add a `run_user_stream` wiring test that injects a fake scheduler and verifies the loop starts it once, passes the notify callback into the handler, and closes it on exit.

```python
from __future__ import annotations

import unittest
from datetime import date, datetime, timezone


class StreamWorkerLoopSchedulerTests(unittest.TestCase):
    def test_run_user_stream_wires_scheduler_into_event_handler(self) -> None:
        from momentum_alpha import stream_worker_loop

        notifications: list[str] = []
        closed: list[str] = []
        captured: dict[str, object] = {}

        class FakeScheduler:
            def notify(self) -> None:
                notifications.append("notify")

            def close(self) -> None:
                closed.append("close")

        def fake_event_handler_factory(**kwargs):
            captured["on_trade_fill_persisted_fn"] = kwargs["on_trade_fill_persisted_fn"]

            def _on_event(_event):
                kwargs["on_trade_fill_persisted_fn"]()

            return _on_event

        class FakeStreamClient:
            def run_forever(self, on_event):
                on_event(object())
                return "listen-key"

        result = stream_worker_loop.run_user_stream(
            client=object(),
            testnet=False,
            logger=lambda msg: None,
            runtime_state_store=None,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            stream_client_factory=lambda **kwargs: FakeStreamClient(),
            reconnect_sleep_fn=lambda seconds: None,
            runtime_db_path=None,
            event_handler_factory=fake_event_handler_factory,
            rebuild_trade_analytics_fn=lambda path: notifications.append("rebuild"),
            scheduler_factory=lambda **kwargs: FakeScheduler(),
        )

        self.assertEqual(result, 0)
        self.assertEqual(notifications, ["notify"])
        self.assertEqual(closed, ["close"])
        self.assertIsNotNone(captured["on_trade_fill_persisted_fn"])
```

- [ ] **Step 2: Run the tests and verify they fail**

Run:

```bash
./.venv/bin/python -m unittest tests.test_stream_worker_split -v
```

Expected: fail because the new callback and scheduler wiring are not implemented yet.

- [ ] **Step 3: Implement the wiring**

Update the event handler in `stream_worker_core.py` so it accepts a new optional callback, for example:

```python
on_trade_fill_persisted_fn: Callable[[], None] | None = None
```

Call that hook only after `insert_trade_fill_fn(...)` succeeds.

Update `stream_worker_loop.run_user_stream(...)` so it:

- accepts an optional `rebuild_trade_analytics_fn`
- accepts an optional `scheduler_factory` for tests
- enables the scheduler only when `runtime_db_path` is available
- constructs a `DebouncedRebuildScheduler` once before the reconnect loop
- passes `scheduler.notify` into `build_user_stream_event_handler(...)`
- calls `scheduler.close()` in a `finally` block

Update `src/momentum_alpha/stream_worker.py` so the facade forwards the new optional parameter(s) to `stream_worker_loop.run_user_stream` without changing the existing public entrypoint shape for callers that do not care about the scheduler.

- [ ] **Step 4: Run the tests and verify they pass**

Run:

```bash
./.venv/bin/python -m unittest tests.test_stream_worker_split tests.test_stream_worker_rebuild_scheduler -v
```

Expected: PASS.

- [ ] **Step 5: Commit this slice**

```bash
git add src/momentum_alpha/stream_worker_core.py src/momentum_alpha/stream_worker_loop.py src/momentum_alpha/stream_worker.py tests/test_stream_worker_split.py
git commit -m "feat: wire rebuild debounce into user stream"
```

## Task 3: Full regression pass and operational verification

**Files:**
- Modify: none if the earlier tasks are correct
- Test: `tests/test_main.py`, `tests/test_runtime_analytics.py`, `tests/test_stream_worker_split.py`, `tests/test_stream_worker_rebuild_scheduler.py`

- [ ] **Step 1: Run the focused regression suite**

Run:

```bash
./.venv/bin/python -m unittest tests.test_main tests.test_runtime_analytics tests.test_stream_worker_split tests.test_stream_worker_rebuild_scheduler -v
```

Expected: PASS.

- [ ] **Step 2: Verify the manual rebuild command still works**

Run:

```bash
./.venv/bin/python -m momentum_alpha.main rebuild-trade-analytics --runtime-db-file var/runtime.db
```

Expected: prints `trade-analytics-rebuilt` and exits `0`.

- [ ] **Step 3: Run the full suite if the focused regression is green**

Run:

```bash
./.venv/bin/python -m unittest
```

Expected: all tests pass.

- [ ] **Step 4: Commit the finished work**

```bash
git add src/momentum_alpha/stream_worker_core.py src/momentum_alpha/stream_worker_loop.py src/momentum_alpha/stream_worker.py src/momentum_alpha/stream_worker_rebuild_scheduler.py tests/test_main.py tests/test_runtime_analytics.py tests/test_stream_worker_rebuild_scheduler.py tests/test_stream_worker_split.py
git commit -m "feat: debounce trade analytics rebuilds in user stream"
```

## Coverage Check

This plan covers the spec requirements as follows:

- 30-second debounce: Task 1
- trigger from `user-stream` after committed fills: Task 2
- keep rebuild asynchronous: Task 1 and Task 2
- preserve manual `rebuild-trade-analytics`: Task 3
- fail-soft behavior: Task 1 and Task 2
- testing for burst coalescing, post-insert scheduling, and error handling: Tasks 1 and 2

No spec requirement is left without a task.
