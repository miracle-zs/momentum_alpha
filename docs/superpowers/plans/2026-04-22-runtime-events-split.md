# Runtime Events Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split runtime event read and write accessors into focused audit, decision, order, and flow modules while keeping the existing facade modules stable for callers.

**Architecture:** Keep `runtime_reads_events.py` and `runtime_writes_events.py` as compatibility facades. Move the concrete SQL helpers into small modules grouped by responsibility, then keep `runtime_reads.py`, `runtime_writes.py`, and `runtime_store.py` pointing at the same public API so dashboard, telemetry, serverchan, stream worker, and tests continue to work unchanged.

**Tech Stack:** Python 3.12+, standard library `unittest`, SQLite helpers from `runtime_schema.py`, existing runtime read/write facades.

---

### Task 1: Add split coverage for runtime event modules

**Files:**
- Modify: `tests/test_runtime_reads_split.py`
- Modify: `tests/test_runtime_writes_split.py`

- [x] **Step 1: Add import coverage for the new runtime read modules**

```python
def test_runtime_reads_event_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        runtime_reads_events_audit,
        runtime_reads_events_decisions,
        runtime_reads_events_flows,
        runtime_reads_events_orders,
    )

    self.assertTrue(callable(runtime_reads_events_audit.fetch_notification_status))
    self.assertTrue(callable(runtime_reads_events_audit.fetch_recent_audit_events))
    self.assertTrue(callable(runtime_reads_events_audit.fetch_audit_event_counts))
    self.assertTrue(callable(runtime_reads_events_decisions.fetch_recent_signal_decisions))
    self.assertTrue(callable(runtime_reads_events_decisions.fetch_signal_decisions_for_window))
    self.assertTrue(callable(runtime_reads_events_orders.fetch_recent_broker_orders))
    self.assertTrue(callable(runtime_reads_events_orders.fetch_recent_trade_fills))
    self.assertTrue(callable(runtime_reads_events_orders.fetch_recent_algo_orders))
    self.assertTrue(callable(runtime_reads_events_flows.fetch_recent_account_flows))
    self.assertTrue(callable(runtime_reads_events_flows.fetch_account_flows_since))
```

- [x] **Step 2: Add import coverage for the new runtime write modules**

```python
def test_runtime_writes_event_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        runtime_writes_events_audit,
        runtime_writes_events_decisions,
        runtime_writes_events_flows,
        runtime_writes_events_orders,
    )

    self.assertTrue(callable(runtime_writes_events_audit.insert_audit_event))
    self.assertTrue(callable(runtime_writes_events_decisions.insert_signal_decision))
    self.assertTrue(callable(runtime_writes_events_orders.insert_broker_order))
    self.assertTrue(callable(runtime_writes_events_orders.insert_trade_fill))
    self.assertTrue(callable(runtime_writes_events_orders.insert_algo_order))
    self.assertTrue(callable(runtime_writes_events_flows.insert_account_flow))
```

- [x] **Step 3: Run the focused split tests to verify they fail before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads_split tests.test_runtime_writes_split -v
```

Expected: `FAIL` with an import error for one of the new runtime event modules.

### Task 2: Split runtime read accessors

**Files:**
- Create: `src/momentum_alpha/runtime_reads_events_audit.py`
- Create: `src/momentum_alpha/runtime_reads_events_decisions.py`
- Create: `src/momentum_alpha/runtime_reads_events_orders.py`
- Create: `src/momentum_alpha/runtime_reads_events_flows.py`
- Modify: `src/momentum_alpha/runtime_reads_events.py`

- [x] **Step 1: Move notification and audit queries into `runtime_reads_events_audit.py`**

Move these functions unchanged into the new audit module:

```text
fetch_notification_status
fetch_recent_audit_events
fetch_audit_event_counts
```

Keep the shared imports from `runtime_schema._connect`, `bootstrap_runtime_db`, and `runtime_reads_common._json_loads` local to that module.

- [x] **Step 2: Move decision queries into `runtime_reads_events_decisions.py`**

Move these functions unchanged into the new decision module:

```text
fetch_recent_signal_decisions
fetch_signal_decisions_for_window
```

- [x] **Step 3: Move order and fill queries into `runtime_reads_events_orders.py`**

Move these functions unchanged into the new order module:

```text
fetch_recent_broker_orders
fetch_recent_trade_fills
fetch_recent_algo_orders
```

- [x] **Step 4: Move account flow queries into `runtime_reads_events_flows.py`**

Move these functions unchanged into the new flow module:

```text
fetch_recent_account_flows
fetch_account_flows_since
```

- [x] **Step 5: Rewire the facade module**

Update `src/momentum_alpha/runtime_reads_events.py` so it imports and re-exports the same public functions from the new modules. Keep the existing caller-visible API identical so `runtime_reads.py`, `runtime_store.py`, `dashboard_data_loader.py`, `serverchan.py`, and the test suite do not need to change.

### Task 3: Split runtime write accessors

**Files:**
- Create: `src/momentum_alpha/runtime_writes_events_audit.py`
- Create: `src/momentum_alpha/runtime_writes_events_decisions.py`
- Create: `src/momentum_alpha/runtime_writes_events_orders.py`
- Create: `src/momentum_alpha/runtime_writes_events_flows.py`
- Modify: `src/momentum_alpha/runtime_writes_events.py`

- [x] **Step 1: Move audit writes into `runtime_writes_events_audit.py`**

Move this function unchanged into the new audit module:

```text
insert_audit_event
```

- [x] **Step 2: Move decision writes into `runtime_writes_events_decisions.py`**

Move this function unchanged into the new decision module:

```text
insert_signal_decision
```

- [x] **Step 3: Move order and fill writes into `runtime_writes_events_orders.py`**

Move these functions unchanged into the new order module:

```text
insert_broker_order
insert_trade_fill
insert_algo_order
```

- [x] **Step 4: Move account flow writes into `runtime_writes_events_flows.py`**

Move this function unchanged into the new flow module:

```text
insert_account_flow
```

- [x] **Step 5: Rewire the facade module**

Update `src/momentum_alpha/runtime_writes_events.py` so it imports and re-exports the same public functions from the new modules. Keep `runtime_writes.py` and `runtime_store.py` untouched except for the new imports resolved through the facade.

### Task 4: Verify and commit

**Files:**
- Test: `tests/test_runtime_reads_split.py`
- Test: `tests/test_runtime_writes_split.py`
- Test: `tests/test_runtime_reads.py`
- Test: `tests/test_runtime_writes.py`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_audit.py`
- Test: `tests/test_telemetry.py`
- Test: `tests/test_serverchan.py`

- [x] **Step 1: Run the focused split and facade tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_reads_split tests.test_runtime_writes_split tests.test_runtime_reads tests.test_runtime_writes -v
```

Expected: `OK`.

- [x] **Step 2: Run the integration tests that exercise runtime store and callers**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_store tests.test_audit tests.test_telemetry tests.test_serverchan -v
```

Expected: `OK`.

- [x] **Step 3: Commit the runtime event split**

```bash
git add src/momentum_alpha/runtime_reads_events.py src/momentum_alpha/runtime_reads_events_audit.py src/momentum_alpha/runtime_reads_events_decisions.py src/momentum_alpha/runtime_reads_events_orders.py src/momentum_alpha/runtime_reads_events_flows.py src/momentum_alpha/runtime_writes_events.py src/momentum_alpha/runtime_writes_events_audit.py src/momentum_alpha/runtime_writes_events_decisions.py src/momentum_alpha/runtime_writes_events_orders.py src/momentum_alpha/runtime_writes_events_flows.py tests/test_runtime_reads_split.py tests/test_runtime_writes_split.py docs/superpowers/plans/2026-04-22-runtime-events-split.md
git commit -m "refactor: split runtime event accessors"
```
