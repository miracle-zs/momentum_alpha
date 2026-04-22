# Runtime State Store Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Extract `RuntimeStateStore` into a dedicated module while keeping `runtime_store.py` as a stable compatibility facade for existing callers.

**Architecture:** Move the SQLite-backed strategy-state persistence class into `runtime_state_store.py`. Keep `runtime_store.py` as the public entrypoint for the wider runtime read/write facade so `dashboard`, `poll_worker`, `stream_worker`, and tests keep importing the same names. Leave `MAX_PROCESSED_EVENT_ID_AGE_HOURS` in `runtime_store.py` because it is a worker policy constant, not a storage concern. Do not change persistence behavior or SQL shape; this is a boundary cleanup, not a storage rewrite.

**Tech Stack:** Python 3.12+, standard library `unittest`, SQLite helpers from `runtime_schema.py`, existing strategy-state codec helpers.

---

### Task 1: Add split coverage for the runtime state store

**Files:**
- Create: `tests/test_runtime_store_split.py`

- [x] **Step 1: Write import coverage for the new state-store module**

```python
def test_runtime_state_store_split_module_exports_key_entrypoints(self) -> None:
    from momentum_alpha import runtime_state_store, runtime_store

    self.assertTrue(hasattr(runtime_state_store, "RuntimeStateStore"))
    self.assertTrue(hasattr(runtime_state_store, "_json_dumps"))
    self.assertTrue(hasattr(runtime_store, "RuntimeStateStore"))
    self.assertTrue(hasattr(runtime_store, "MAX_PROCESSED_EVENT_ID_AGE_HOURS"))
    self.assertIs(runtime_store.RuntimeStateStore, runtime_state_store.RuntimeStateStore)
```

- [x] **Step 2: Run the focused split test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_store_split -v
```

Expected: `FAIL` with an import error for `momentum_alpha.runtime_state_store`.

### Task 2: Extract `RuntimeStateStore` into its own module

**Files:**
- Create: `src/momentum_alpha/runtime_state_store.py`
- Modify: `src/momentum_alpha/runtime_store.py`

- [x] **Step 1: Move the state-store class into `runtime_state_store.py`**

Move this code into the new module without changing behavior:

```text
@dataclass(frozen=True)
class RuntimeStateStore:
    path: Path

    def load(self) -> StoredStrategyState | None: ...
    def save(self, state: StoredStrategyState) -> None: ...
    def merge_save(self, state: StoredStrategyState) -> None: ...
    def atomic_update(self, updater: Callable[[StoredStrategyState | None], StoredStrategyState]) -> StoredStrategyState: ...

def _json_dumps(payload: dict) -> str: ...
```

Keep the imports for `json`, `dataclass`, `Path`, `StoredStrategyState`, `deserialize_strategy_state`, `serialize_strategy_state`, `bootstrap_runtime_db`, and `_connect` local to the new module.
Keep `MAX_PROCESSED_EVENT_ID_AGE_HOURS` in `runtime_store.py` and continue exporting it there.

- [x] **Step 2: Rewire `runtime_store.py` as a compatibility facade**

Update `src/momentum_alpha/runtime_store.py` so it imports `RuntimeStateStore` from `runtime_state_store.py` and continues to re-export the existing runtime read/write helpers from `runtime_reads.py` and `runtime_writes.py`.

Keep these caller-visible names stable:

```text
RuntimeStateStore
StoredStrategyState
MAX_PROCESSED_EVENT_ID_AGE_HOURS
rebuild_trade_analytics
all existing read/write facade functions
```

### Task 3: Verify and commit

**Files:**
- Test: `tests/test_runtime_store_split.py`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_main.py`
- Test: `tests/test_stream_worker.py`
- Test: `tests/test_stream_worker_split.py`
- Test: `tests/test_dashboard.py`

- [x] **Step 1: Run the focused split and facade tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_runtime_store_split tests.test_runtime_store -v
```

Expected: `OK`.

- [x] **Step 2: Run the integration tests that use the runtime state store**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_main tests.test_stream_worker tests.test_stream_worker_split tests.test_dashboard -v
```

Expected: `OK`.

- [x] **Step 3: Commit the state-store split**

```bash
git add src/momentum_alpha/runtime_store.py src/momentum_alpha/runtime_state_store.py tests/test_runtime_store_split.py docs/superpowers/plans/2026-04-22-runtime-state-store-split.md
git commit -m "refactor: split runtime state store"
```
