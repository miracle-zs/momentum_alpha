# Poll Worker Core Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the poll worker core into focused state, execution, and live orchestration modules while keeping the existing public facades stable.

**Architecture:** Keep `poll_worker_core.py` as a compatibility facade and move persistence, pure execution, and live orchestration into dedicated modules. Preserve the `poll_worker.py` and `main.py` imports so existing tests, scripts, and systemd entrypoints keep working unchanged.

**Tech Stack:** Python 3.12+, standard library `unittest`, existing worker/runtime modules, existing telemetry and reconciliation helpers.

---

### Task 1: Add split coverage for the worker core modules

**Files:**
- Modify: `tests/test_poll_worker_split.py`

- [x] **Step 1: Write the failing import coverage**

```python
def test_poll_worker_core_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        poll_worker_core,
        poll_worker_core_execution,
        poll_worker_core_live,
        poll_worker_core_state,
        poll_worker_loop,
    )

    self.assertTrue(hasattr(poll_worker_core, "RunOnceResult"))
    self.assertTrue(callable(poll_worker_core_state._save_strategy_state))
    self.assertTrue(callable(poll_worker_core_execution.build_runtime_from_snapshots))
    self.assertTrue(callable(poll_worker_core_execution.run_once))
    self.assertTrue(callable(poll_worker_core_live.run_once_live))
    self.assertTrue(callable(poll_worker_loop.run_forever))
```

- [x] **Step 2: Run the focused split test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_poll_worker_split -v
```

Expected: `FAIL` with an import error for one of the new worker-core modules.

### Task 2: Split persistence and pure execution out of `poll_worker_core.py`

**Files:**
- Create: `src/momentum_alpha/poll_worker_core_state.py`
- Create: `src/momentum_alpha/poll_worker_core_execution.py`
- Modify: `src/momentum_alpha/poll_worker_core.py`

- [x] **Step 1: Move strategy-state persistence into `poll_worker_core_state.py`**

Move this function unchanged into `src/momentum_alpha/poll_worker_core_state.py`:

```text
_save_strategy_state
```

Keep the `RuntimeStateStore` and `StoredStrategyState` imports local to the new module. The function must still preserve newer stream-owned fields when the poll worker writes state.

- [x] **Step 2: Move pure execution helpers into `poll_worker_core_execution.py`**

Move these symbols into `src/momentum_alpha/poll_worker_core_execution.py`:

```text
RunOnceResult
build_runtime_from_snapshots
run_once
```

Keep the `Runtime`, `RuntimeTickResult`, `StrategyState`, `ExecutionPlan`, `TickDecision`, `BinanceBroker`, and `parse_exchange_info` dependencies local to the new module.

- [x] **Step 3: Rewire the facade module**

Update `src/momentum_alpha/poll_worker_core.py` so it only re-exports:

```text
RunOnceResult
_save_strategy_state
build_runtime_from_snapshots
run_once
run_once_live
```

At this stage, `run_once_live` can still come from `poll_worker_core_live.py` once Task 3 is complete.

### Task 3: Split live orchestration into its own module

**Files:**
- Create: `src/momentum_alpha/poll_worker_core_live.py`
- Modify: `src/momentum_alpha/poll_worker_core.py`
- Modify: `src/momentum_alpha/poll_worker.py`

- [x] **Step 1: Move `run_once_live` into `poll_worker_core_live.py`**

Move the full live orchestration function into `src/momentum_alpha/poll_worker_core_live.py` and keep these responsibilities together:

```text
position mode resolution
stored leader lookup
position restore flow
live snapshot assembly
stop replacement planning
broker submit flow
runtime state merge
audit recorder payloads
```

The module should import `run_once` from `poll_worker_core_execution.py` and `_save_strategy_state` from `poll_worker_core_state.py`.

- [x] **Step 2: Keep the public facades stable**

Update `src/momentum_alpha/poll_worker_core.py` and `src/momentum_alpha/poll_worker.py` so callers still import the same names from the same places:

```text
poll_worker_core.py:
  RunOnceResult
  _save_strategy_state
  build_runtime_from_snapshots
  run_once
  run_once_live

poll_worker.py:
  RunOnceResult
  _save_strategy_state
  build_runtime_from_snapshots
  run_once
  run_once_live
  run_forever
```

### Task 4: Verify and commit

**Files:**
- Test: `tests/test_poll_worker_split.py`
- Test: `tests/test_poll_worker.py`
- Test: `tests/test_main.py`
- Test: `tests/test_poll_worker_split.py`

- [x] **Step 1: Run the focused worker split test**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_poll_worker_split -v
```

Expected: `OK`.

- [x] **Step 2: Run the public worker facade tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_poll_worker tests.test_main -v
```

Expected: `OK`.

- [x] **Step 3: Commit the worker core split**

```bash
git add src/momentum_alpha/poll_worker_core.py src/momentum_alpha/poll_worker_core_state.py src/momentum_alpha/poll_worker_core_execution.py src/momentum_alpha/poll_worker_core_live.py src/momentum_alpha/poll_worker.py tests/test_poll_worker_split.py docs/superpowers/plans/2026-04-22-poll-worker-core-split.md
git commit -m "refactor: split poll worker core"
```
