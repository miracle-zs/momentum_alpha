# Dashboard Data Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the dashboard data assembly layer into focused modules while keeping the existing `dashboard_data.py` facade stable for callers.

**Architecture:** Keep `dashboard_data.py` as a compatibility facade and move shared helpers, payload builders, and snapshot loading into dedicated modules. Preserve current JSON shape and database access behavior so dashboard server routes, renderers, and view-model code continue to work without changes.

**Tech Stack:** Python 3.12+, standard library `unittest`, SQLite-backed runtime reads, existing in-repo facades.

---

### Task 1: Add split coverage for dashboard data modules

**Files:**
- Modify: `tests/test_dashboard_data_split.py`

- [ ] **Step 1: Write import coverage for the new dashboard data modules**

```python
def test_dashboard_data_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import (
        dashboard_data_common,
        dashboard_data_loader,
        dashboard_data_payloads,
    )

    self.assertTrue(callable(dashboard_data_common._account_flow_since))
    self.assertTrue(callable(dashboard_data_common._select_latest_timestamp))
    self.assertTrue(callable(dashboard_data_common._normalize_events))
    self.assertTrue(callable(dashboard_data_common._build_source_counts))
    self.assertTrue(callable(dashboard_data_common._build_leader_history))
    self.assertTrue(callable(dashboard_data_common._build_pulse_points))
    self.assertTrue(callable(dashboard_data_common._runtime_summary_from_sources))
    self.assertTrue(callable(dashboard_data_payloads.build_dashboard_summary_payload))
    self.assertTrue(callable(dashboard_data_payloads.build_dashboard_timeseries_payload))
    self.assertTrue(callable(dashboard_data_payloads.build_trade_leg_count_aggregates))
    self.assertTrue(callable(dashboard_data_payloads.build_trade_leg_index_aggregates))
    self.assertTrue(callable(dashboard_data_payloads.build_dashboard_tables_payload))
    self.assertTrue(callable(dashboard_data_payloads.build_dashboard_response_json))
    self.assertTrue(callable(dashboard_data_loader.load_dashboard_snapshot))
```

- [ ] **Step 2: Run the focused test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_data_split -v
```

Expected: `FAIL` with an import error for one of the new dashboard data modules.

### Task 2: Split common helpers and payload builders

**Files:**
- Create: `src/momentum_alpha/dashboard_data_common.py`
- Create: `src/momentum_alpha/dashboard_data_payloads.py`
- Modify: `src/momentum_alpha/dashboard_data.py`

- [ ] **Step 1: Move shared helper functions into `dashboard_data_common.py`**

Move these functions and constants into `src/momentum_alpha/dashboard_data_common.py`:

```text
_account_flow_since
_select_latest_timestamp
_normalize_events
_build_source_counts
_build_leader_history
_build_pulse_points
_runtime_summary_from_sources
_EXTERNAL_ACCOUNT_FLOW_REASONS
_is_external_account_flow
```

Keep the imports for `ACCOUNT_RANGE_WINDOWS`, `Counter`, `Mapping`, `datetime`, `timedelta`, `timezone`, and `normalize_account_range` local to the new module.

- [ ] **Step 2: Move payload builder functions into `dashboard_data_payloads.py`**

Move these functions into `src/momentum_alpha/dashboard_data_payloads.py`:

```text
build_dashboard_summary_payload
build_dashboard_timeseries_payload
build_trade_leg_count_aggregates
build_trade_leg_index_aggregates
build_dashboard_tables_payload
build_dashboard_response_json
```

Import the common helpers from `dashboard_data_common.py` and keep the payload JSON shape unchanged.

- [ ] **Step 3: Rewire the facade module**

Update `src/momentum_alpha/dashboard_data.py` so it only re-exports the public entrypoints used by callers:

```text
build_dashboard_summary_payload
build_dashboard_timeseries_payload
build_trade_leg_count_aggregates
build_trade_leg_index_aggregates
build_dashboard_tables_payload
load_dashboard_snapshot
build_dashboard_response_json
```

Keep the module name and signatures stable so `dashboard_server.py`, `dashboard_view_model.py`, `dashboard_render_shell.py`, and `dashboard.py` continue to import from the same place.

### Task 3: Split the snapshot loader

**Files:**
- Create: `src/momentum_alpha/dashboard_data_loader.py`
- Modify: `src/momentum_alpha/dashboard_data.py`
- Modify: `src/momentum_alpha/dashboard_data_payloads.py`

- [ ] **Step 1: Move `load_dashboard_snapshot` into `dashboard_data_loader.py`**

Keep the loader responsible for:

```text
health report loading
runtime state loading
recent event / snapshot fetches
daily review report selection
runtime summary assembly
payload assembly
```

Have it import the shared helpers from `dashboard_data_common.py` and the payload builders from `dashboard_data_payloads.py`.

- [ ] **Step 2: Keep the public facade thin**

Make `dashboard_data.py` import `load_dashboard_snapshot` from `dashboard_data_loader.py` and re-export it without additional logic.

### Task 4: Verify and commit

**Files:**
- Test: `tests/test_dashboard_data_split.py`
- Test: `tests/test_dashboard_data.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_dashboard_view_model.py`
- Test: `tests/test_dashboard_render.py`

- [ ] **Step 1: Run the focused split and facade tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_data tests.test_dashboard_data_split tests.test_dashboard tests.test_dashboard_view_model -v
```

Expected: `OK`.

- [ ] **Step 2: Run the relevant dashboard integration tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard_render tests.test_dashboard_render_split -v
```

Expected: `OK`.

- [ ] **Step 3: Commit the dashboard data split**

```bash
git add src/momentum_alpha/dashboard_data.py src/momentum_alpha/dashboard_data_common.py src/momentum_alpha/dashboard_data_payloads.py src/momentum_alpha/dashboard_data_loader.py tests/test_dashboard_data_split.py
git commit -m "refactor: split dashboard data layer"
```
