# Dashboard And Structured Runtime Store Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Upgrade the live dashboard into a more visual trading monitor while expanding SQLite from a generic event sink into a structured runtime store for signals, orders, and position snapshots.

**Architecture:** Keep SQLite as the runtime recovery source of truth and the primary analytics and dashboard backend. Extend the existing runtime database with structured tables written by `poll` and `user-stream`, then teach the dashboard to prefer those tables for richer summaries, charts, and recent activity panels while keeping `audit_events` as a general event log.

**Tech Stack:** Python 3, SQLite, stdlib HTTP server, HTML/CSS/JS dashboard, unittest

---

### Task 1: Add runtime store schema for structured telemetry

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Test: `tests/test_runtime_store.py`

**Step 1: Write the failing tests**

Add tests covering:
- schema bootstrap creates `signal_decisions`, `broker_orders`, and `position_snapshots`
- inserts and reads preserve timestamps and typed summary fields
- dashboard-facing aggregations can read leader changes and recent broker activity from the new tables

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_runtime_store -v
```

Expected: FAIL because new tables/functions do not exist yet.

**Step 3: Write minimal implementation**

Extend `runtime_store.py` with:
- schema DDL for:
  - `signal_decisions`
  - `broker_orders`
  - `position_snapshots`
- insert helpers such as:
  - `insert_signal_decision(...)`
  - `insert_broker_order(...)`
  - `insert_position_snapshot(...)`
- read helpers for:
  - recent signal decisions
  - recent broker orders
  - recent position snapshots
  - chart-friendly leader history and event pulse queries

Keep payload-style fields JSON where necessary, but expose first-class columns for the fields the dashboard needs to query directly.

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_runtime_store -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/runtime_store.py tests/test_runtime_store.py
git commit -m "feat: add structured runtime store tables"
```

### Task 2: Persist structured signal and broker data from poll

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Modify: `src/momentum_alpha/audit.py`
- Test: `tests/test_main.py`
- Test: `tests/test_audit.py`

**Step 1: Write the failing tests**

Add tests proving that:
- each poll tick persists a position snapshot
- each `tick_result` persists a signal decision row for base entries, add-ons, stop updates, and skipped/no-op cases
- broker responses persist order rows with symbol, action type, and response payload summary

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_main tests.test_audit -v
```

Expected: FAIL because structured inserts are not being called.

**Step 3: Write minimal implementation**

Update the poll execution path so that after each tick it:
- records a `position_snapshot` with leader, position count, order count, and submit flags
- records `signal_decision` rows for:
  - base entry symbols
  - add-on symbols
  - updated stop symbols
  - no-op tick outcome with explicit decision type
- records `broker_order` rows from broker responses with action type and normalized payload

Keep `audit_events` writes intact.

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_main tests.test_audit -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/main.py src/momentum_alpha/audit.py tests/test_main.py tests/test_audit.py
git commit -m "feat: persist structured poll telemetry"
```

### Task 3: Persist structured user-stream activity

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing tests**

Add tests proving that:
- `user_stream_worker_start` also writes a position snapshot row
- order/account update handling writes broker/order lifecycle records or stream-side position snapshots when state changes

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_main -v
```

Expected: FAIL because user-stream only writes generic audit events.

**Step 3: Write minimal implementation**

In the user-stream path:
- write an initial `position_snapshot` when prewarm completes
- on relevant order/account events, write structured broker/order lifecycle rows or updated snapshots
- normalize symbols, event types, and order statuses so the dashboard can render them without reparsing raw JSON

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_main -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/main.py tests/test_main.py
git commit -m "feat: persist structured user-stream telemetry"
```

### Task 4: Expand dashboard snapshot API for visual trading monitor data

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing tests**

Add tests proving `/api/dashboard` snapshot now includes:
- latest broker activity summary
- latest signal decision summary
- recent position snapshot summary
- chart-ready arrays for:
  - leader rotation
  - pulse window
  - source mix
  - recent order outcomes

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected: FAIL because the current snapshot only returns generic event summaries.

**Step 3: Write minimal implementation**

Teach `load_dashboard_snapshot(...)` to:
- query structured tables from `runtime_store.py`
- populate a richer `runtime` section with:
  - latest signal summary
  - latest broker activity summary
  - latest position snapshot summary
- return chart-friendly collections for the dashboard UI
- continue falling back to `audit_events` only when structured data is absent

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add structured dashboard snapshot queries"
```

### Task 5: Redesign the dashboard into a richer trading monitor

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing tests**

Add HTML assertions for:
- chart sections for pulse, leader rotation, and broker activity
- summary cards for latest signal and latest broker response
- recent position snapshot panel
- auto-refresh still present

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected: FAIL because the HTML does not yet render the new visual sections.

**Step 3: Write minimal implementation**

Refactor `render_dashboard_html(...)` to produce a more visual monitor:
- keep deep dark trade-desk styling
- add distinct cards for:
  - latest signal decision
  - latest broker activity
  - current runtime snapshot
- add simple chart-like visual blocks using CSS for:
  - pulse bars
  - source mix
  - leader rotation list/timeline
  - recent order outcomes

Stay within the current no-framework, single-file HTML approach.

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: upgrade dashboard into a visual trading monitor"
```

### Task 6: Update CLI, scripts, and docs for structured-store-first usage

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Modify: `scripts/check_health.sh`
- Modify: `scripts/audit_report.sh`
- Modify: `scripts/run_dashboard.sh`
- Modify: `README.md`
- Modify: `docs/live-ops-checklist.md`
- Test: `tests/test_main.py`
- Test: `tests/test_deploy_artifacts.py`

**Step 1: Write the failing tests**

Add tests proving:
- CLI help and command plumbing still accept `--runtime-db-file`
- shell scripts document and prefer the structured runtime store
- docs mention the new structured telemetry tables and dashboard capabilities

**Step 2: Run test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_main tests.test_deploy_artifacts -v
```

Expected: FAIL because docs/scripts do not yet mention the new structured store behavior.

**Step 3: Write minimal implementation**

Update:
- script defaults and comments for `RUNTIME_DB_FILE`
- README/live ops docs to explain:
  - what tables exist
  - what the dashboard reads
  - how to inspect SQLite directly

Keep instructions focused on the new runtime store-first workflow.

**Step 4: Run test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_main tests.test_deploy_artifacts -v
```

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/main.py scripts/check_health.sh scripts/audit_report.sh scripts/run_dashboard.sh README.md docs/live-ops-checklist.md tests/test_main.py tests/test_deploy_artifacts.py
git commit -m "docs: document structured runtime store workflow"
```

### Task 7: Run full regression and prepare rollout notes

**Files:**
- Modify if needed: any files touched by regressions

**Step 1: Run full test suite**

Run:

```bash
python3 -m unittest discover -s tests -v
```

Expected: PASS

**Step 2: Fix any regressions minimally**

If failures appear, patch the smallest possible surface and rerun the affected tests first, then rerun the full suite.

**Step 3: Capture rollout commands**

Prepare the exact server rollout commands:

```bash
cd /root/momentum_alpha
git pull
./.venv/bin/python -m pip install -e .[live]
chmod +x scripts/run_poll.sh scripts/run_user_stream.sh scripts/check_health.sh scripts/audit_report.sh scripts/run_dashboard.sh
systemctl restart momentum-alpha-user-stream.service
systemctl restart momentum-alpha.service
pkill -f 'momentum_alpha.main dashboard' || true
nohup bash scripts/run_dashboard.sh > /root/momentum_alpha/var/log/momentum-alpha-dashboard.log 2>&1 &
```

**Step 4: Commit final regression fixes if any**

```bash
git add <files>
git commit -m "test: stabilize structured runtime monitor rollout"
```
