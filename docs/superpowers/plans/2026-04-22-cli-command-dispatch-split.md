# CLI Command Dispatch Split Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Split the CLI command dispatcher into focused modules for live, reporting, and ops commands while keeping the existing CLI facade stable.

**Architecture:** Keep `cli_commands.py` as a compatibility facade and move the actual command handlers into smaller modules grouped by behavior. Preserve the public CLI entrypoint in `cli.py` and the parser/env helpers in `cli_parser.py` and `cli_env.py` so existing tests, scripts, and systemd entrypoints continue to work unchanged.

**Tech Stack:** Python 3.12+, standard library `unittest`, existing CLI/parser/env helpers, existing worker and dashboard entrypoints.

---

### Task 1: Add split coverage for the new CLI command modules

**Files:**
- Add: `tests/test_cli_split.py`

- [x] **Step 1: Write the failing import coverage**

```python
def test_cli_split_modules_export_key_entrypoints(self) -> None:
    from momentum_alpha import cli_commands, cli_commands_live, cli_commands_ops, cli_commands_reports

    self.assertTrue(callable(cli_commands.run_cli_command))
    self.assertTrue(callable(cli_commands_live.run_live_commands))
    self.assertTrue(callable(cli_commands_live.run_once_live_command))
    self.assertTrue(callable(cli_commands_live.poll_command))
    self.assertTrue(callable(cli_commands_live.user_stream_command))
    self.assertTrue(callable(cli_commands_reports.run_reporting_commands))
    self.assertTrue(callable(cli_commands_reports.healthcheck_command))
    self.assertTrue(callable(cli_commands_reports.audit_report_command))
    self.assertTrue(callable(cli_commands_reports.daily_review_report_command))
    self.assertTrue(callable(cli_commands_ops.run_ops_commands))
    self.assertTrue(callable(cli_commands_ops.backfill_account_flows_command))
    self.assertTrue(callable(cli_commands_ops.rebuild_trade_analytics_command))
    self.assertTrue(callable(cli_commands_ops.dashboard_command))
```

- [x] **Step 2: Run the focused split test to verify it fails before the split**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_cli_split -v
```

Expected: `FAIL` with an import error for one of the new CLI command modules.

### Task 2: Extract live command handling

**Files:**
- Create: `src/momentum_alpha/cli_commands_live.py`
- Modify: `src/momentum_alpha/cli_commands.py`

- [x] **Step 1: Move live command handlers into `cli_commands_live.py`**

Move the following command branches into a new module:

```text
run-once-live
poll
user-stream
```

The new module should expose these functions:

```text
run_live_commands
run_once_live_command
poll_command
user_stream_command
```

Each function should keep using the existing helpers from `cli_env.py`, `poll_worker.py`, `stream_worker.py`, and the current `client_factory` / `broker_factory` / `now_provider` injection points.

- [x] **Step 2: Rewire `cli_commands.py` to delegate live commands**

Keep `run_cli_command` as the public facade, but have it delegate the live commands to `cli_commands_live.py` before checking report or ops commands.

### Task 3: Extract reporting and ops command handling

**Files:**
- Create: `src/momentum_alpha/cli_commands_reports.py`
- Create: `src/momentum_alpha/cli_commands_ops.py`
- Modify: `src/momentum_alpha/cli_commands.py`

- [x] **Step 1: Move reporting command handlers into `cli_commands_reports.py`**

Move these command branches into the reporting module:

```text
healthcheck
audit-report
daily-review-report
```

The module should expose:

```text
run_reporting_commands
healthcheck_command
audit_report_command
daily_review_report_command
```

Keep the existing `build_runtime_health_report`, `summarize_audit_events`, `build_daily_review_report`, and `insert_daily_review_report` call paths intact.

- [x] **Step 2: Move ops command handlers into `cli_commands_ops.py`**

Move these command branches into the ops module:

```text
backfill-account-flows
rebuild-trade-analytics
dashboard
```

The module should expose:

```text
run_ops_commands
backfill_account_flows_command
rebuild_trade_analytics_command
dashboard_command
```

Keep the existing `backfill_account_flows`, `rebuild_trade_analytics`, and `run_dashboard_server` call paths intact.

- [x] **Step 3: Rewire the facade module**

Update `src/momentum_alpha/cli_commands.py` so it imports and re-exports the top-level dispatch entrypoints from the new modules. Keep the `run_cli_command` signature and caller-visible behavior unchanged.

### Task 4: Verify and commit

**Files:**
- Test: `tests/test_cli_split.py`
- Test: `tests/test_cli.py`
- Test: `tests/test_main.py`
- Test: `tests/test_dashboard.py`

- [x] **Step 1: Run the focused split test**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_cli_split -v
```

Expected: `OK`.

- [x] **Step 2: Run the public CLI and entrypoint tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_cli tests.test_main -v
```

Expected: `OK`.

- [x] **Step 3: Run the dashboard/worker command integration tests**

Run:

```bash
/Users/zhangshuai/PycharmProjects/momentum_alpha/.venv/bin/python -m unittest tests.test_dashboard -v
```

Expected: `OK`.

- [x] **Step 4: Commit the CLI command dispatch split**

```bash
git add src/momentum_alpha/cli_commands.py src/momentum_alpha/cli_commands_live.py src/momentum_alpha/cli_commands_reports.py src/momentum_alpha/cli_commands_ops.py tests/test_cli_split.py docs/superpowers/plans/2026-04-22-cli-command-dispatch-split.md
git commit -m "refactor: split CLI command dispatch"
```
