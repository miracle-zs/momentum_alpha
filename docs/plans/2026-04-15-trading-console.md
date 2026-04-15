# Trading Console Implementation Plan

> **For Claude:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task.

**Goal:** Build a framework-based trading console that reads SQLite-backed telemetry, records incremental account snapshots, and visualizes health, leader rotation, event pulse, and account equity data.

**Architecture:** Extend the runtime store with account snapshot persistence, add structured Python JSON endpoints for summary/timeseries/table data, and serve a lightweight SPA that renders charts and operator-focused tables. Keep existing runtime services intact and make SQLite the primary dashboard source.

**Tech Stack:** Python, SQLite, unittest, lightweight frontend framework SPA, charting library or framework-native chart wrappers, existing dashboard HTTP server.

---

### Task 1: Account Snapshot Persistence

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_main.py`

**Step 1: Write the failing test**

Add tests for:
- creating an `account_snapshots` table
- inserting and reading recent account snapshots
- poll ticks writing one account snapshot into SQLite

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_runtime_store tests.test_main -v`
Expected: FAIL for missing account snapshot functions / schema.

**Step 3: Write minimal implementation**

Implement:
- schema for `account_snapshots`
- insert and fetch helpers
- poll-time snapshot writing with the latest account values available

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_runtime_store tests.test_main -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/runtime_store.py src/momentum_alpha/main.py tests/test_runtime_store.py tests/test_main.py
git commit -m "feat: record account snapshots in runtime store"
```

### Task 2: Dashboard API Restructure

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add tests for:
- summary endpoint payload structure
- timeseries endpoint structure for equity / balance / pulse / leader series
- table payloads for recent signals, orders, and events

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: FAIL because the new endpoint builders do not exist.

**Step 3: Write minimal implementation**

Implement structured payload builders that expose:
- summary cards
- account timeseries
- leader timeseries
- pulse bars
- recent tables

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: add structured trading console dashboard APIs"
```

### Task 3: Frontend App Shell

**Files:**
- Create: `frontend/package.json`
- Create: `frontend/src/main.*`
- Create: `frontend/src/App.*`
- Create: `frontend/src/components/*`
- Create: `frontend/src/styles.*`
- Modify: backend serving files as needed
- Test: frontend smoke coverage and backend artifact tests where appropriate

**Step 1: Write the failing test**

Add tests or artifact checks that verify:
- built frontend assets can be served
- dashboard shell references the frontend bundle
- key UI labels exist in the rendered output

**Step 2: Run test to verify it fails**

Run the relevant Python tests plus frontend test command if added.
Expected: FAIL because the frontend app does not exist yet.

**Step 3: Write minimal implementation**

Create a lightweight SPA with:
- summary cards
- charts for equity / balance / unrealized PnL / pulse
- leader timeline
- decision overview
- recent tables

**Step 4: Run test to verify it passes**

Run the frontend build and relevant test commands.
Expected: PASS

**Step 5: Commit**

```bash
git add frontend src/momentum_alpha/dashboard.py tests
git commit -m "feat: add frontend trading console shell"
```

### Task 4: UTC+8 Formatting and Visual Refinement

**Files:**
- Modify: frontend UI components
- Modify: `src/momentum_alpha/dashboard.py` if backend formatting helpers are reused
- Test: `tests/test_dashboard.py`

**Step 1: Write the failing test**

Add tests for:
- `YYYY-MM-DD HH:MM:SS` UTC+8 formatting
- chart / table rendering of the converted timestamps

**Step 2: Run test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: FAIL if formatting or rendering differs.

**Step 3: Write minimal implementation**

Ensure all major displayed timestamps use UTC+8 formatting and remove raw ISO timestamps from the main operator view.

**Step 4: Run test to verify it passes**

Run: `python3 -m unittest tests.test_dashboard -v`
Expected: PASS

**Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py frontend tests/test_dashboard.py
git commit -m "feat: standardize trading console time display"
```

### Task 5: Full Verification and Deployment Notes

**Files:**
- Modify: `README.md`
- Modify: deployment scripts/docs if needed
- Test: full suite

**Step 1: Write the failing test**

Add or update artifact tests for:
- frontend build artifacts
- run scripts or deployment notes needed for the SPA

**Step 2: Run test to verify it fails**

Run the relevant artifact tests.
Expected: FAIL before docs/scripts are updated.

**Step 3: Write minimal implementation**

Update documentation and deploy instructions for:
- installing frontend dependencies
- building or serving the frontend
- restarting dashboard services

**Step 4: Run test to verify it passes**

Run:
- `python3 -m unittest discover -s tests -v`
- frontend build command

Expected: PASS

**Step 5: Commit**

```bash
git add README.md docs scripts tests
git commit -m "docs: add trading console deployment workflow"
```
