# Live Dashboard Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Add a read-only single-page dashboard that shows runtime health, current strategy state, and recent audit events from the SQLite runtime artifacts.

**Architecture:** Keep the dashboard inside the existing Python project. Add a tiny dashboard module, expose one HTML route and one JSON route through a minimal standard-library HTTP server, and reuse the existing health-report builder and SQLite runtime store directly.

**Tech Stack:** Python 3.12+, unittest, standard-library `http.server`, JSON, existing shell/systemd deployment flow

---

### Task 1: Add dashboard data aggregation module

**Files:**
- Create: `src/momentum_alpha/dashboard.py`
- Modify: `src/momentum_alpha/__init__.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add tests for:
- loading runtime state from SQLite
- loading recent audit events from SQLite
- combining health, state, and audit into one dashboard payload

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: FAIL because `momentum_alpha.dashboard` does not exist.

**Step 3: Write minimal implementation**

Add:
- `load_dashboard_snapshot(...)`
- helpers to read latest audit events
- helpers to summarize current leader, position count, and recent worker/tick timestamps

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_dashboard -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py src/momentum_alpha/__init__.py tests/test_dashboard.py
git commit -m "feat: add dashboard snapshot builder"
```

### Task 2: Add failing tests for dashboard HTTP routes

**Files:**
- Modify: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests for:
- `dashboard` CLI subcommand
- HTML response from `/`
- JSON response from `/api/dashboard`

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_main -v`

Expected: FAIL because the CLI subcommand and HTTP server do not exist.

**Step 3: Write minimal implementation**

Do not implement yet. Stop after verifying the failure shape is correct.

**Step 4: Run test to verify it still fails for the intended reason**

Run: `python3 -m unittest tests.test_main -v`

Expected: FAIL mentioning missing dashboard server behavior.

**Step 5: Commit**

```bash
git add tests/test_main.py
git commit -m "test: add dashboard cli and route expectations"
```

### Task 3: Add minimal dashboard HTTP server

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_main.py`

**Step 1: Write the minimal implementation**

Add:
- `dashboard` CLI subcommand
- small HTTP handler serving:
  - `/` as HTML
  - `/api/dashboard` as JSON
- configuration flags such as:
  - `--host`
  - `--port`
  - `--runtime-db-file`

**Step 2: Run focused tests**

Run: `python3 -m unittest tests.test_dashboard tests.test_main -v`

Expected: PASS

**Step 3: Refine output**

Keep HTML intentionally simple but readable:
- health section
- runtime snapshot section
- recent audit table/list

**Step 4: Run focused tests again**

Run: `python3 -m unittest tests.test_dashboard tests.test_main -v`

Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py src/momentum_alpha/main.py tests/test_main.py tests/test_dashboard.py
git commit -m "feat: add live dashboard server"
```

### Task 4: Add launch script and documentation

**Files:**
- Create: `scripts/run_dashboard.sh`
- Modify: `deploy/env.example`
- Modify: `README.md`
- Modify: `docs/live-ops-checklist.md`
- Test: `tests/test_deploy_artifacts.py`

**Step 1: Write the failing test**

Add tests that assert:
- `scripts/run_dashboard.sh` exists and uses the project virtualenv
- `deploy/env.example` contains dashboard host/port variables if introduced
- README mentions the dashboard

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_deploy_artifacts -v`

Expected: FAIL because the script and docs do not exist yet.

**Step 3: Write minimal implementation**

Add:
- dashboard wrapper script
- README usage section
- live ops note explaining the dashboard is read-only and local-first

**Step 4: Run targeted tests**

Run: `python3 -m unittest tests.test_deploy_artifacts -v`

Expected: PASS

**Step 5: Commit**

```bash
git add scripts/run_dashboard.sh deploy/env.example README.md docs/live-ops-checklist.md tests/test_deploy_artifacts.py
git commit -m "docs: add dashboard launch artifacts"
```

### Task 5: Run full verification

**Files:**
- No new files

**Step 1: Run the complete suite**

Run: `python3 -m unittest discover -s tests -v`

Expected: PASS with the full suite green.

**Step 2: Smoke-test the CLI manually**

Run:

```bash
python3 -m momentum_alpha.main dashboard \
  --runtime-db-file ./var/runtime.db \
  --host 127.0.0.1 \
  --port 8080
```

Expected:
- HTTP server starts
- `/` returns HTML
- `/api/dashboard` returns JSON

**Step 3: Commit**

```bash
git add .
git commit -m "test: verify dashboard implementation"
```
