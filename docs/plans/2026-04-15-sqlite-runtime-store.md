# SQLite Runtime Store Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a SQLite-backed runtime store for audit, dashboard, and runtime recovery data.

**Architecture:** Introduce a small SQLite repository layer with automatic schema bootstrap and WAL mode, switch dashboard reads to SQLite, and keep runtime behavior isolated behind a few helper functions.

**Tech Stack:** Python 3.12+, sqlite3, unittest, existing CLI/scripts/systemd deployment

---

### Task 1: Add failing tests for SQLite repository bootstrap and writes

**Files:**
- Create: `tests/test_runtime_store.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add tests for:
- creating the SQLite schema
- inserting one audit event
- querying recent events and event counts

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_runtime_store -v`

Expected: FAIL because the runtime store module does not exist.

**Step 3: Write minimal implementation**

Do not implement yet. Stop after verifying failure shape.

**Step 4: Run test to verify it still fails for the intended reason**

Run: `python3 -m unittest tests.test_runtime_store -v`

Expected: FAIL mentioning missing runtime store helpers.

**Step 5: Commit**

```bash
git add tests/test_runtime_store.py
git commit -m "test: add sqlite runtime store expectations"
```

### Task 2: Add minimal SQLite runtime store module

**Files:**
- Create: `src/momentum_alpha/runtime_store.py`
- Modify: `src/momentum_alpha/__init__.py`
- Test: `tests/test_runtime_store.py`

**Step 1: Write minimal implementation**

Add:
- connection helper
- schema bootstrap
- WAL mode enablement
- `insert_audit_event(...)`
- `fetch_recent_audit_events(...)`
- `fetch_audit_event_counts(...)`

**Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_runtime_store -v`

Expected: PASS

**Step 3: Refactor lightly**

Keep SQL local and explicit. Avoid ORM or migration framework.

**Step 4: Run focused tests again**

Run: `python3 -m unittest tests.test_runtime_store -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/runtime_store.py src/momentum_alpha/__init__.py tests/test_runtime_store.py
git commit -m "feat: add sqlite runtime store"
```

### Task 3: Dual-write audit events during runtime

**Files:**
- Modify: `src/momentum_alpha/audit.py`
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests for:
- poll audit events being written to SQLite
- user-stream audit events being written to SQLite
- runtime continuing if DB write fails

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_main -v`

Expected: FAIL because runtime does not know about the DB store yet.

**Step 3: Write minimal implementation**

Extend the audit recorder layer so one record call can:
- append JSONL during migration
- insert the same event into SQLite

Guard DB writes so failures are logged but do not crash live workers.

**Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_main -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/audit.py src/momentum_alpha/main.py tests/test_main.py
git commit -m "feat: dual write audit events to sqlite"
```

### Task 4: Switch dashboard reads from JSONL to SQLite

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add tests for:
- loading recent events from SQLite
- building event counts from SQLite
- keeping runtime state reads intact

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: FAIL because the dashboard still reads JSONL directly.

**Step 3: Write minimal implementation**

Change dashboard aggregation to:
- query SQLite for recent events and counts
- read runtime state from SQLite as before
- keep health checks unchanged

Leave a small JSONL fallback only if absolutely needed during migration.

**Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: read dashboard audit data from sqlite"
```

### Task 5: Add runtime DB path configuration and scripts/docs

**Files:**
- Modify: `deploy/env.example`
- Modify: `README.md`
- Modify: `scripts/run_poll.sh`
- Modify: `scripts/run_user_stream.sh`
- Modify: `scripts/run_dashboard.sh`
- Test: `tests/test_deploy_artifacts.py`

**Step 1: Write the failing test**

Add tests that assert:
- env example contains DB path
- wrappers pass or expose DB path correctly
- README mentions `runtime.db`

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_deploy_artifacts -v`

Expected: FAIL because runtime DB config is not documented yet.

**Step 3: Write minimal implementation**

Add:
- `RUNTIME_DB_FILE`
- wrapper propagation
- README operational note for `runtime.db`

**Step 4: Run targeted tests**

Run: `python3 -m unittest tests.test_deploy_artifacts -v`

Expected: PASS

**Step 5: Commit**

```bash
git add deploy/env.example README.md scripts/run_poll.sh scripts/run_user_stream.sh scripts/run_dashboard.sh tests/test_deploy_artifacts.py
git commit -m "docs: add runtime sqlite configuration"
```

### Task 6: Optional health snapshot persistence

**Files:**
- Modify: `src/momentum_alpha/health.py`
- Modify: `src/momentum_alpha/serverchan.py`
- Test: `tests/test_health.py`
- Test: `tests/test_serverchan.py`

**Step 1: Write the failing test**

Add tests for:
- persisting one health snapshot row
- no regression in health notification behavior

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_health tests.test_serverchan -v`

Expected: FAIL because health persistence is not implemented.

**Step 3: Write minimal implementation**

Persist health snapshots only when explicitly configured or when the notification script runs.

**Step 4: Run focused tests**

Run: `python3 -m unittest tests.test_health tests.test_serverchan -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/health.py src/momentum_alpha/serverchan.py tests/test_health.py tests/test_serverchan.py
git commit -m "feat: persist health snapshots to sqlite"
```

### Task 7: Run full verification

**Files:**
- No new files

**Step 1: Run the complete suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS with the full suite green.

**Step 2: Manual smoke checks**

Run:

```bash
python3 -m momentum_alpha.main audit-report --runtime-db-file ./var/runtime.db
python3 -m momentum_alpha.main dashboard \
  --runtime-db-file ./var/runtime.db
```

Then verify:
- runtime DB file exists
- recent events appear in the dashboard
- runtime still writes state normally

**Step 3: Commit**

```bash
git add .
git commit -m "test: verify sqlite runtime store rollout"
```
