# Runtime History Writes Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the runtime history write helpers into focused trade and review/report modules while keeping the existing `runtime_writes_history.py` facade stable for callers.

**Architecture:** Keep `runtime_writes_history.py` as a compatibility facade and move the concrete SQL insert helpers into smaller modules grouped by history type. Preserve the public API exported through `runtime_writes.py` and `runtime_store.py` so existing callers, tests, and downstream modules keep working unchanged.

**Tech Stack:** Python 3.12+, standard library `unittest`, SQLite helpers from `runtime_schema.py`, existing runtime write facades.

---

### Task 1: Add split coverage for runtime history write modules

**Files:**
- Modify: `tests/test_runtime_writes_split.py`

- [x] **Step 1: Add import coverage for the new history write modules**

```python
def test_runtime_writes_history_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        runtime_writes_history,
        runtime_writes_history_reports,
        runtime_writes_history_trades,
    )

    self.assertTrue(callable(runtime_writes_history.insert_trade_round_trip))
    self.assertTrue(callable(runtime_writes_history.insert_daily_review_report))
    self.assertTrue(callable(runtime_writes_history.insert_stop_exit_summary))
    self.assertTrue(callable(runtime_writes_history_trades.insert_trade_round_trip))
    self.assertTrue(callable(runtime_writes_history_trades.insert_stop_exit_summary))
    self.assertTrue(callable(runtime_writes_history_reports.insert_daily_review_report))
```

- [x] **Step 2: Run the focused split test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_writes_split -v
```

Expected: `FAIL` with an import error for one of the new runtime history write modules.

### Task 2: Split history trade writes from review writes

**Files:**
- Create: `src/momentum_alpha/runtime_writes_history_trades.py`
- Create: `src/momentum_alpha/runtime_writes_history_reports.py`
- Modify: `src/momentum_alpha/runtime_writes_history.py`

- [x] **Step 1: Move trade round-trip and stop-exit inserts into `runtime_writes_history_trades.py`**

Move these functions unchanged into the new trades module:

```text
insert_trade_round_trip
insert_stop_exit_summary
```

Keep the shared imports from `runtime_schema._connect`, `bootstrap_runtime_db`, and `runtime_writes_common` local to the new module.

- [x] **Step 2: Move the daily review report insert into `runtime_writes_history_reports.py`**

Move this function unchanged into the new reports module:

```text
insert_daily_review_report
```

- [x] **Step 3: Rewire the facade module**

Update `src/momentum_alpha/runtime_writes_history.py` so it imports and re-exports the same public functions from the new modules. Keep the caller-visible API identical so `runtime_writes.py`, `runtime_store.py`, and downstream modules do not need to change.

### Task 3: Verify and commit

**Files:**
- Test: `tests/test_runtime_writes_split.py`
- Test: `tests/test_runtime_writes.py`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_daily_review.py`

- [x] **Step 1: Run the focused split and facade tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_writes_split tests.test_runtime_writes -v
```

Expected: `OK`.

- [x] **Step 2: Run the integration tests that exercise runtime store callers**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_store tests.test_daily_review -v
```

Expected: `OK`.

- [x] **Step 3: Commit the runtime history write split**

```bash
git add src/momentum_alpha/runtime_writes_history.py src/momentum_alpha/runtime_writes_history_trades.py src/momentum_alpha/runtime_writes_history_reports.py tests/test_runtime_writes_split.py docs/superpowers/plans/2026-04-22-runtime-history-writes-split.md
git commit -m "refactor: split runtime history writes"
```
