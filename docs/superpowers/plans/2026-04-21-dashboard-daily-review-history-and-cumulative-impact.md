# Dashboard Daily Review History and Cumulative Impact Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let the review room show any stored daily review by date, and add a historical cumulative Filter Impact summary computed from all `daily_review_reports` rows.

**Architecture:** Keep the existing single dashboard server and SQLite runtime DB. Extend the runtime read layer with a report-by-date query and a cumulative summary query over `daily_review_reports`, then update the daily review panel to support date navigation plus a separate historical summary block above the current-day report.

**Tech Stack:** Python 3.11, SQLite, existing dashboard HTML renderer, unittest-based tests.

---

### Task 1: Add runtime read helpers for dated reports and historical cumulative summary

**Files:**
- Modify: `src/momentum_alpha/runtime_reads_history.py`
- Modify: `src/momentum_alpha/runtime_store.py`
- Test: `tests/test_runtime_store.py`

- [ ] **Step 1: Write the failing tests**

Add one test that inserts two `daily_review_reports` rows for different `report_date` values and asserts a new `fetch_daily_review_report_by_date(path=db_path, report_date="2026-04-20")` helper returns the matching row rather than the latest one.

Add one test that inserts three reports and asserts a new `fetch_daily_review_reports_summary(path=db_path)` helper returns cumulative totals:

```python
summary = fetch_daily_review_reports_summary(path=db_path)
assert summary["report_count"] == 3
assert summary["trade_count"] == 35
assert summary["actual_total_pnl"] == "10.50"
assert summary["counterfactual_total_pnl"] == "16.75"
assert summary["filter_impact"] == "6.25"
```

- [ ] **Step 2: Run the targeted tests to confirm they fail**

Run:

```bash
pytest tests/test_runtime_store.py -k daily_review -v
```

Expected: fail because the new helpers do not exist yet.

- [ ] **Step 3: Implement the minimal runtime queries**

Add `fetch_daily_review_report_by_date(...)` in `runtime_reads_history.py` using `WHERE report_date = ? LIMIT 1`.

Add `fetch_daily_review_reports_summary(...)` in `runtime_reads_history.py` using `SUM(...)` over `daily_review_reports`, returning strings for the money fields and an integer `report_count`.

Re-export both helpers from `runtime_store.py`.

- [ ] **Step 4: Re-run the targeted tests**

Run:

```bash
pytest tests/test_runtime_store.py -k daily_review -v
```

Expected: pass.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/runtime_reads_history.py src/momentum_alpha/runtime_store.py tests/test_runtime_store.py
git commit -m "feat: add daily review history queries"
```

### Task 2: Let the dashboard load a specific daily review date and the cumulative summary

**Files:**
- Modify: `src/momentum_alpha/dashboard_server.py`
- Modify: `src/momentum_alpha/dashboard_data.py`
- Modify: `src/momentum_alpha/dashboard_render_utils.py`
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests**

Add a dashboard test that loads the review room with `report_date=2026-04-20` in the query string and asserts the rendered daily review block shows that report date instead of the latest one.

Add a dashboard test that injects a cumulative summary payload and asserts the rendered daily review panel includes a separate historical summary section with `Cumulative Filter Impact`.

- [ ] **Step 2: Run the targeted dashboard tests**

Run:

```bash
pytest tests/test_dashboard.py -k "daily_review or review_room" -v
```

Expected: fail because date selection and cumulative summary rendering are not wired yet.

- [ ] **Step 3: Wire query parsing and snapshot loading**

Teach `dashboard_server.py` to parse an optional `report_date` query parameter.

Update `load_dashboard_snapshot(...)` in `dashboard_data.py` so the review-room daily view loads either the requested report date or the latest report, and also includes a cumulative summary payload in the snapshot.

Extend `dashboard_render_utils.py` if needed so generated links can preserve `report_date` while navigating within the review room.

- [ ] **Step 4: Render the cumulative summary and date navigator**

Update `render_daily_review_panel(...)` in `dashboard_render_panels.py` to render:

```python
summary = report.get("history_summary")
```

Show a top navigation row with previous/next/latest controls and a visible `report_date`.

Place the cumulative summary above the current report detail, with `Cumulative Filter Impact` visually separated from the daily report's existing `Filter Impact`.

- [ ] **Step 5: Re-run the dashboard tests**

Run:

```bash
pytest tests/test_dashboard.py -k "daily_review or review_room" -v
```

Expected: pass.

- [ ] **Step 6: Commit**

```bash
git add src/momentum_alpha/dashboard_server.py src/momentum_alpha/dashboard_data.py src/momentum_alpha/dashboard_render_utils.py src/momentum_alpha/dashboard_render_panels.py tests/test_dashboard.py
git commit -m "feat: add daily review history navigation"
```

### Task 3: Run the focused regression suite

**Files:**
- No code changes expected

- [ ] **Step 1: Run the focused test suite**

Run:

```bash
pytest tests/test_runtime_store.py tests/test_dashboard.py -v
```

Expected: all tests pass.

- [ ] **Step 2: Inspect the rendered HTML expectations**

Confirm the review room still shows the existing `Filter Impact` for the selected day and the new cumulative summary separately above it.

- [ ] **Step 3: Commit if anything changed**

If any final polish is needed, commit it with a focused message after the tests are green.
