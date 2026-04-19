# DB-Only Runtime Storage Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make runtime data storage database-only by requiring `runtime.db` for live commands, removing JSON state persistence, moving notification state into SQLite, and stopping health/dashboard data reads from operational log files.

**Architecture:** `runtime.db` becomes the only durable store for strategy state, audit events, structured analytics, and notification status. Systemd log files remain operational logs, but health and dashboard logic no longer depend on log freshness as a data source. Historical `state.json` and `audit.jsonl` references are removed from code, deploy examples, tests, and docs.

**Tech Stack:** Python standard library, SQLite, `unittest`, existing shell wrapper scripts, existing `momentum_alpha.runtime_store` repository style.

---

## Scope Definition

This plan treats these as durable data storage and moves or keeps them in SQLite:

- Strategy state: previous leader, positions, processed event ids, order statuses, recent stop-loss exits.
- Audit and analytics: events, signal decisions, broker orders, fills, account flows, snapshots, round trips, stop exit summaries.
- Health notification status: last OK/WARN/FAIL state used to deduplicate ServerChan notifications.
- Health/dashboard runtime status: computed from `runtime.db` audit events and state tables.

This plan does not try to store these in SQLite:

- Systemd stdout/stderr logs in `var/log/`. They are operational logs, not application state.
- Temporary shell files created with `mktemp` during a single command invocation. They are not durable storage and are deleted by traps.
- Historical local files under `var/`. They are operator artifacts and should be archived or removed manually after DB-only deployment is verified.

## File Structure

- Modify `src/momentum_alpha/main.py`: require a runtime DB path for live commands and remove log-file health/dashboard arguments after downstream changes.
- Modify `src/momentum_alpha/runtime_store.py`: keep the central schema and add notification status helpers.
- Create `src/momentum_alpha/strategy_state_codec.py`: own `StoredStrategyState` and JSON payload serialization/deserialization without file I/O.
- Delete `src/momentum_alpha/state_store.py`: remove JSON file persistence from production source.
- Modify `src/momentum_alpha/health.py`: replace log file freshness checks with audit-event freshness checks in SQLite.
- Modify `src/momentum_alpha/dashboard.py`: call DB-only health report and no longer require log file paths.
- Modify `src/momentum_alpha/serverchan.py`: persist notification status in `runtime.db` instead of a JSON status file.
- Modify `scripts/check_health.sh`, `scripts/check_health_and_notify.sh`, `scripts/run_dashboard.sh`: pass only DB-backed runtime state inputs.
- Modify `deploy/env.example`: remove `STATE_FILE` and `SERVERCHAN_STATUS_FILE`.
- Modify docs: `README.md`, `CLAUDE.md`, `docs/live-deployment-checklist.md`, `docs/live-ops-checklist.md`.
- Modify tests: `tests/test_main.py`, `tests/test_runtime_store.py`, `tests/test_health.py`, `tests/test_dashboard.py`, `tests/test_serverchan.py`, `tests/test_deploy_artifacts.py`.
- Delete `tests/test_state_store.py`; add `tests/test_strategy_state_codec.py`.

---

### Task 1: Require Runtime DB For Live CLI Commands

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write failing tests for missing DB configuration**

Add tests near the existing CLI argument tests in `tests/test_main.py`:

```python
    def test_cli_poll_requires_runtime_db_file_or_env(self) -> None:
        from momentum_alpha.main import cli_main

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit) as caught:
                cli_main(argv=["poll", "--symbols", "BTCUSDT"])

        self.assertEqual(caught.exception.code, 2)

    def test_cli_user_stream_requires_runtime_db_file_or_env(self) -> None:
        from momentum_alpha.main import cli_main

        with patch.dict("os.environ", {}, clear=True):
            with self.assertRaises(SystemExit) as caught:
                cli_main(argv=["user-stream", "--testnet"])

        self.assertEqual(caught.exception.code, 2)

    def test_cli_run_once_live_uses_runtime_db_env(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        class FakeClient:
            def fetch_position_mode(self):
                return {"dualSidePosition": False}

            def fetch_exchange_info(self):
                return {"symbols": [{"symbol": "BTCUSDT", "contractType": "PERPETUAL", "status": "TRADING"}]}

            def fetch_24hr_tickers(self):
                return [{"symbol": "BTCUSDT", "priceChangePercent": "1"}]

            def fetch_klines(self, symbol, interval, limit):
                return [
                    [0, "100", "110", "90", "105", "1", 0, "1", 1, "1", "1", "0"],
                    [0, "105", "120", "95", "115", "1", 0, "1", 1, "1", "1", "0"],
                ]

            def fetch_account_info(self):
                return {}

        class FakeBroker:
            def __init__(self, client):
                self.client = client

            def submit_execution_plan(self, plan):
                return []

        def broker_factory(client):
            calls.append(client)
            return FakeBroker(client)

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            with patch.dict("os.environ", {"RUNTIME_DB_FILE": str(db_path), "BINANCE_API_KEY": "x", "BINANCE_API_SECRET": "y"}):
                result = cli_main(
                    argv=["run-once-live", "--symbols", "BTCUSDT"],
                    client_factory=lambda testnet=False: FakeClient(),
                    broker_factory=broker_factory,
                    now_provider=lambda: datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
                )

        self.assertEqual(result, 0)
        self.assertTrue(db_path.exists())
```

- [ ] **Step 2: Run the targeted test and verify failure**

Run:

```bash
python -m unittest tests.test_main -v
```

Expected: the new missing-DB tests fail because `poll` and `user-stream` currently allow `runtime_db_path=None`, and the env-backed `run-once-live` test may not create the DB before implementation is tightened.

- [ ] **Step 3: Add a CLI helper that requires DB configuration**

In `src/momentum_alpha/main.py`, add this helper after `resolve_runtime_db_path`:

```python
def _require_runtime_db_path(*, parser: argparse.ArgumentParser, command: str, explicit_path: str | None) -> Path:
    runtime_db_path = resolve_runtime_db_path(explicit_path=explicit_path)
    if runtime_db_path is None:
        parser.error(f"{command} requires --runtime-db-file or RUNTIME_DB_FILE")
    return runtime_db_path
```

Update the command branches:

```python
runtime_db_path = _require_runtime_db_path(
    parser=parser,
    command=args.command,
    explicit_path=args.runtime_db_file,
)
```

Apply that replacement in the `run-once-live`, `poll`, and `user-stream` branches. Leave `healthcheck`, `audit-report`, `backfill-account-flows`, and `dashboard` explicit DB arguments as-is until later tasks update their CLI surfaces.

- [ ] **Step 4: Run targeted tests**

Run:

```bash
python -m unittest tests.test_main -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/main.py tests/test_main.py
git commit -m "refactor: require runtime database for live commands"
```

---

### Task 2: Remove JSON File State Store

**Files:**
- Create: `src/momentum_alpha/strategy_state_codec.py`
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `src/momentum_alpha/main.py`
- Delete: `src/momentum_alpha/state_store.py`
- Create: `tests/test_strategy_state_codec.py`
- Delete: `tests/test_state_store.py`
- Modify: tests that import `StoredStrategyState` from `momentum_alpha.state_store`

- [ ] **Step 1: Write codec tests without file I/O**

Create `tests/test_strategy_state_codec.py`:

```python
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))


class StrategyStateCodecTests(unittest.TestCase):
    def test_round_trips_strategy_state_payload(self) -> None:
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.strategy_state_codec import (
            StoredStrategyState,
            deserialize_strategy_state,
            serialize_strategy_state,
        )

        opened_at = datetime(2026, 4, 19, 1, 2, tzinfo=timezone.utc)
        state = StoredStrategyState(
            current_day="2026-04-19",
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("90000"),
                    legs=(
                        PositionLeg(
                            symbol="BTCUSDT",
                            quantity=Decimal("0.01"),
                            entry_price=Decimal("95000"),
                            stop_price=Decimal("90000"),
                            opened_at=opened_at,
                            leg_type="base",
                        ),
                    ),
                )
            },
            processed_event_ids={"evt-1": "2026-04-19T01:02:03+00:00"},
            order_statuses={"1": {"status": "NEW"}},
            recent_stop_loss_exits={"ETHUSDT": "2026-04-19T01:03:00+00:00"},
        )

        payload = serialize_strategy_state(state)
        restored = deserialize_strategy_state(payload)

        self.assertEqual(restored.current_day, "2026-04-19")
        self.assertEqual(restored.previous_leader_symbol, "BTCUSDT")
        self.assertEqual(restored.positions["BTCUSDT"].total_quantity, Decimal("0.01"))
        self.assertEqual(restored.processed_event_ids, {"evt-1": "2026-04-19T01:02:03+00:00"})
        self.assertEqual(restored.order_statuses, {"1": {"status": "NEW"}})
        self.assertEqual(restored.recent_stop_loss_exits, {"ETHUSDT": "2026-04-19T01:03:00+00:00"})

    def test_deserializes_legacy_processed_event_id_list(self) -> None:
        from momentum_alpha.strategy_state_codec import deserialize_strategy_state

        restored = deserialize_strategy_state(
            {
                "current_day": "2026-04-19",
                "previous_leader_symbol": None,
                "positions": {},
                "processed_event_ids": ["evt-1"],
                "order_statuses": {},
                "recent_stop_loss_exits": {},
            }
        )

        self.assertIn("evt-1", restored.processed_event_ids)
        self.assertIsInstance(restored.processed_event_ids["evt-1"], str)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run codec tests and verify failure**

Run:

```bash
python -m unittest tests.test_strategy_state_codec -v
```

Expected: FAIL with `ModuleNotFoundError: No module named 'momentum_alpha.strategy_state_codec'`.

- [ ] **Step 3: Create the codec module**

Create `src/momentum_alpha/strategy_state_codec.py` by moving the dataclass and serializer/deserializer code from `state_store.py`, but do not include `FileStateStore`, locks, temp files, `json`, `os`, `fcntl`, or `NamedTemporaryFile`.

Use these public names:

```python
@dataclass(frozen=True)
class StoredStrategyState:
    current_day: str
    previous_leader_symbol: str | None
    positions: dict[str, Position] | None = None
    processed_event_ids: dict[str, str] | None = None
    order_statuses: dict[str, dict] | None = None
    recent_stop_loss_exits: dict[str, str] | None = None


def serialize_strategy_state(state: StoredStrategyState) -> dict:
    ...


def deserialize_strategy_state(payload: dict) -> StoredStrategyState:
    ...
```

Keep helper names private:

```python
def _serialize_position(position: Position) -> dict:
    ...


def _deserialize_position(payload: dict) -> Position:
    ...
```

- [ ] **Step 4: Update runtime imports**

In `src/momentum_alpha/runtime_store.py`, replace:

```python
from momentum_alpha.state_store import StoredStrategyState, _deserialize_state, _serialize_state
```

with:

```python
from momentum_alpha.strategy_state_codec import (
    StoredStrategyState,
    deserialize_strategy_state,
    serialize_strategy_state,
)
```

Then replace:

```python
_deserialize_state(json.loads(row[0]))
_json_dumps(_serialize_state(state))
```

with:

```python
deserialize_strategy_state(json.loads(row[0]))
_json_dumps(serialize_strategy_state(state))
```

In `src/momentum_alpha/main.py`, replace:

```python
from momentum_alpha.state_store import StoredStrategyState
```

with:

```python
from momentum_alpha.strategy_state_codec import StoredStrategyState
```

Apply the same import update in tests that currently import `StoredStrategyState` from `momentum_alpha.state_store`.

- [ ] **Step 5: Delete file-store source and tests**

Delete:

```bash
src/momentum_alpha/state_store.py
tests/test_state_store.py
```

Do not add a compatibility shim. This is an intentional break from JSON state persistence.

- [ ] **Step 6: Run affected tests**

Run:

```bash
python -m unittest tests.test_strategy_state_codec tests.test_runtime_store tests.test_main tests.test_dashboard tests.test_health -v
```

Expected: PASS.

- [ ] **Step 7: Verify no production import remains**

Run:

```bash
rg -n "state_store|FileStateStore|state\\.json|--state-file" src tests
```

Expected: no output.

- [ ] **Step 8: Commit**

```bash
git add src/momentum_alpha/strategy_state_codec.py src/momentum_alpha/runtime_store.py src/momentum_alpha/main.py tests
git add -u src/momentum_alpha/state_store.py tests/test_state_store.py
git commit -m "refactor: remove json strategy state store"
```

---

### Task 3: Make Health Checks DB-Only

**Files:**
- Modify: `src/momentum_alpha/health.py`
- Modify: `src/momentum_alpha/main.py`
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `scripts/check_health.sh`
- Modify: `scripts/run_dashboard.sh`
- Test: `tests/test_health.py`
- Test: `tests/test_main.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_deploy_artifacts.py`

- [ ] **Step 1: Write failing health tests for DB source freshness**

In `tests/test_health.py`, add tests that insert audit events into `runtime.db` and do not create log files:

```python
    def test_health_report_uses_runtime_db_events_without_log_files(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        now = datetime(2026, 4, 19, 1, 10, tzinfo=timezone.utc)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=db_path).save(
                StoredStrategyState(current_day="2026-04-19", previous_leader_symbol="BTCUSDT")
            )
            insert_audit_event(path=db_path, timestamp=now, event_type="poll_tick", payload={}, source="poll")
            insert_audit_event(
                path=db_path,
                timestamp=now,
                event_type="user_stream_worker_start",
                payload={},
                source="user-stream",
            )

            report = build_runtime_health_report(now=now, runtime_db_file=db_path)

        self.assertEqual(report.overall_status, "OK")
        self.assertNotIn("poll_log", [item.name for item in report.items])
        self.assertNotIn("user_stream_log", [item.name for item in report.items])
        self.assertIn("poll_events", [item.name for item in report.items])
        self.assertIn("user_stream_events", [item.name for item in report.items])

    def test_health_report_fails_when_user_stream_events_are_stale(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        now = datetime(2026, 4, 19, 1, 10, tzinfo=timezone.utc)
        stale = now - timedelta(hours=2)
        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=db_path).save(
                StoredStrategyState(current_day="2026-04-19", previous_leader_symbol="BTCUSDT")
            )
            insert_audit_event(path=db_path, timestamp=now, event_type="poll_tick", payload={}, source="poll")
            insert_audit_event(
                path=db_path,
                timestamp=stale,
                event_type="user_stream_worker_start",
                payload={},
                source="user-stream",
            )

            report = build_runtime_health_report(
                now=now,
                runtime_db_file=db_path,
                max_user_stream_event_age_seconds=1800,
            )

        item_by_name = {item.name: item for item in report.items}
        self.assertEqual(item_by_name["user_stream_events"].status, "FAIL")
        self.assertEqual(report.overall_status, "FAIL")
```

- [ ] **Step 2: Run health tests and verify failure**

Run:

```bash
python -m unittest tests.test_health -v
```

Expected: FAIL because `build_runtime_health_report` still requires `poll_log_file` and `user_stream_log_file`.

- [ ] **Step 3: Replace file freshness checks with audit event freshness checks**

In `src/momentum_alpha/health.py`, remove `_check_file_freshness` if no longer used and add:

```python
def _check_audit_event_freshness(
    *,
    name: str,
    path: Path,
    now: datetime,
    max_age_seconds: int,
    event_types: tuple[str, ...],
) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem(name=name, status="FAIL", message=f"missing path={path}")
    placeholders = ", ".join("?" for _ in event_types)
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                f"""
                SELECT timestamp
                FROM audit_events
                WHERE event_type IN ({placeholders})
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                event_types,
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return HealthCheckItem(name=name, status="FAIL", message=f"invalid path={path} error={exc}")
    if row is None or not row[0]:
        return HealthCheckItem(name=name, status="WARN", message=f"no events event_types={','.join(event_types)}")
    latest_timestamp = datetime.fromisoformat(row[0]).astimezone(timezone.utc)
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - latest_timestamp.timestamp())
    if age_seconds > max_age_seconds:
        return HealthCheckItem(
            name=name,
            status="FAIL",
            message=f"stale age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name=name, status="OK", message=f"fresh age_seconds={age_seconds}")
```

Change `build_runtime_health_report` signature to:

```python
def build_runtime_health_report(
    *,
    now: datetime,
    runtime_db_file: Path,
    max_poll_event_age_seconds: int = 180,
    max_user_stream_event_age_seconds: int = 1800,
    max_runtime_db_age_seconds: int = 1800,
    max_state_age_seconds: int = 3600,
) -> RuntimeHealthReport:
```

Build items as:

```python
items = [
    _check_strategy_state_freshness(path=runtime_db_file, now=now, max_age_seconds=max_state_age_seconds),
    _check_audit_event_freshness(
        name="poll_events",
        path=runtime_db_file,
        now=now,
        max_age_seconds=max_poll_event_age_seconds,
        event_types=("poll_tick", "poll_worker_start", "tick_result"),
    ),
    _check_audit_event_freshness(
        name="user_stream_events",
        path=runtime_db_file,
        now=now,
        max_age_seconds=max_user_stream_event_age_seconds,
        event_types=("user_stream_worker_start", "user_stream_event"),
    ),
    _check_runtime_db_freshness(path=runtime_db_file, now=now, max_age_seconds=max_runtime_db_age_seconds),
]
```

- [ ] **Step 4: Update CLI and scripts**

In `src/momentum_alpha/main.py`, change healthcheck parser args:

```python
healthcheck_parser.add_argument("--runtime-db-file", required=True)
healthcheck_parser.add_argument("--max-state-age-seconds", type=int, default=3600)
healthcheck_parser.add_argument("--max-poll-event-age-seconds", type=int, default=180)
healthcheck_parser.add_argument("--max-user-stream-event-age-seconds", type=int, default=1800)
healthcheck_parser.add_argument("--max-runtime-db-age-seconds", type=int, default=1800)
```

Update the healthcheck branch call:

```python
report = build_runtime_health_report(
    now=now_provider(),
    runtime_db_file=Path(os.path.abspath(args.runtime_db_file)),
    max_state_age_seconds=args.max_state_age_seconds,
    max_poll_event_age_seconds=args.max_poll_event_age_seconds,
    max_user_stream_event_age_seconds=args.max_user_stream_event_age_seconds,
    max_runtime_db_age_seconds=args.max_runtime_db_age_seconds,
)
```

In `scripts/check_health.sh`, remove `POLL_LOG_FILE`, `USER_STREAM_LOG_FILE`, and the two log CLI args. Keep:

```bash
RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"

ARGS=(
  healthcheck
  --runtime-db-file "${RUNTIME_DB_FILE}"
)
```

- [ ] **Step 5: Update dashboard function signatures**

In `src/momentum_alpha/dashboard.py`, change `load_dashboard_snapshot` to remove `poll_log_file` and `user_stream_log_file` parameters. Update the health report call to:

```python
health_report = build_runtime_health_report(
    now=now,
    runtime_db_file=runtime_db_file,
)
```

Update `run_dashboard_server` and the request handler call site so only `runtime_db_file` is threaded through for health data.

In `src/momentum_alpha/main.py`, remove dashboard parser args:

```python
dashboard_parser.add_argument("--poll-log-file", required=True)
dashboard_parser.add_argument("--user-stream-log-file", required=True)
```

Update the dashboard branch call to remove those keyword arguments.

In `scripts/run_dashboard.sh`, remove `POLL_LOG_FILE`, `USER_STREAM_LOG_FILE`, and the two dashboard CLI args.

- [ ] **Step 6: Update affected tests**

Update `tests/test_dashboard.py` fixtures so calls to `load_dashboard_snapshot` no longer create or pass log files. Keep `runtime_db_file` setup and audit inserts.

Update `tests/test_main.py` healthcheck/dashboard CLI tests to assert only `runtime_db_file` is passed.

Update `tests/test_deploy_artifacts.py`:

```python
    def test_check_health_script_uses_runtime_db_only(self) -> None:
        content = (ROOT / "scripts" / "check_health.sh").read_text()
        self.assertIn("RUNTIME_DB_FILE", content)
        self.assertNotIn("POLL_LOG_FILE", content)
        self.assertNotIn("USER_STREAM_LOG_FILE", content)
        self.assertNotIn("--poll-log-file", content)
        self.assertNotIn("--user-stream-log-file", content)
```

- [ ] **Step 7: Run affected tests**

Run:

```bash
python -m unittest tests.test_health tests.test_dashboard tests.test_main tests.test_deploy_artifacts -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/momentum_alpha/health.py src/momentum_alpha/main.py src/momentum_alpha/dashboard.py scripts/check_health.sh scripts/run_dashboard.sh tests
git commit -m "refactor: derive health status from runtime database"
```

---

### Task 4: Store ServerChan Notification Status In SQLite

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `src/momentum_alpha/serverchan.py`
- Modify: `scripts/check_health_and_notify.sh`
- Modify: `deploy/env.example`
- Test: `tests/test_runtime_store.py`
- Test: `tests/test_serverchan.py`
- Test: `tests/test_deploy_artifacts.py`

- [ ] **Step 1: Write runtime store tests for notification status**

Add to `tests/test_runtime_store.py`:

```python
    def test_health_notification_status_round_trips(self) -> None:
        from momentum_alpha.runtime_store import (
            fetch_notification_status,
            save_notification_status,
        )

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 19, 1, 2, tzinfo=timezone.utc)

            self.assertIsNone(fetch_notification_status(path=db_path, status_key="serverchan"))
            save_notification_status(path=db_path, status_key="serverchan", status="FAIL", timestamp=now)
            row = fetch_notification_status(path=db_path, status_key="serverchan")

        self.assertEqual(row, {"status": "FAIL", "updated_at": "2026-04-19T01:02:00+00:00"})
```

- [ ] **Step 2: Run runtime store test and verify failure**

Run:

```bash
python -m unittest tests.test_runtime_store.RuntimeStoreTests.test_health_notification_status_round_trips -v
```

Expected: FAIL because the helper functions do not exist.

- [ ] **Step 3: Add notification status schema and helpers**

In `src/momentum_alpha/runtime_store.py`, add to `SCHEMA`:

```sql
CREATE TABLE IF NOT EXISTS notification_statuses (
    status_key TEXT PRIMARY KEY,
    status TEXT NOT NULL,
    updated_at TEXT NOT NULL
);
```

Add helpers near other fetch/insert functions:

```python
def fetch_notification_status(*, path: Path, status_key: str) -> dict | None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM notification_statuses WHERE status_key = ?",
            (status_key,),
        ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "updated_at": row[1]}


def save_notification_status(*, path: Path, status_key: str, status: str, timestamp: datetime) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO notification_statuses(status_key, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(status_key) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (status_key, status, _as_utc_iso(timestamp)),
        )
```

- [ ] **Step 4: Write ServerChan DB status tests**

In `tests/test_serverchan.py`, replace status-file based tests with DB-backed tests:

```python
    def test_process_health_notification_persists_status_in_runtime_db(self) -> None:
        from momentum_alpha.runtime_store import fetch_notification_status
        from momentum_alpha.serverchan import process_health_notification

        sent = []

        def opener(request, timeout):
            sent.append((request, timeout))

            class Response:
                def __enter__(self):
                    return self

                def __exit__(self, exc_type, exc, tb):
                    return None

                def read(self):
                    return b"ok"

            return Response()

        with tempfile.TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 19, 1, 2, tzinfo=timezone.utc)
            result = process_health_notification(
                sendkey="key",
                runtime_db_path=db_path,
                health_output="overall=FAIL\nruntime_db status=FAIL stale\n",
                now=now,
                hostname="host1",
                opener=opener,
            )
            stored = fetch_notification_status(path=db_path, status_key="serverchan")

        self.assertEqual(result["previous_status"], None)
        self.assertEqual(result["current_status"], "FAIL")
        self.assertEqual(result["event"], "fail")
        self.assertEqual(stored["status"], "FAIL")
        self.assertEqual(len(sent), 1)
```

- [ ] **Step 5: Modify ServerChan implementation**

In `src/momentum_alpha/serverchan.py`, import:

```python
from momentum_alpha.runtime_store import fetch_notification_status, save_notification_status
```

Replace `_load_status` and `_save_status` file helpers with DB helpers:

```python
def _load_status(*, runtime_db_path: Path, status_key: str) -> str | None:
    row = fetch_notification_status(path=runtime_db_path, status_key=status_key)
    if row is None:
        return None
    status = row.get("status")
    return str(status) if status in {"OK", "WARN", "FAIL"} else None


def _save_status(*, runtime_db_path: Path, status_key: str, status: str, now: datetime) -> None:
    save_notification_status(path=runtime_db_path, status_key=status_key, status=status, timestamp=now)
```

Change `process_health_notification` signature:

```python
def process_health_notification(
    *,
    sendkey: str,
    runtime_db_path: Path,
    health_output: str,
    now: datetime,
    hostname: str,
    status_key: str = "serverchan",
    opener=urlopen,
) -> dict:
```

Use:

```python
previous_status = _load_status(runtime_db_path=runtime_db_path, status_key=status_key)
...
_save_status(runtime_db_path=runtime_db_path, status_key=status_key, status=current_status, now=now)
```

Update CLI parser:

```python
parser.add_argument("--runtime-db-file", required=True)
parser.add_argument("--status-key", default="serverchan")
```

Remove `--status-file`.

- [ ] **Step 6: Update scripts and deploy example**

In `scripts/check_health_and_notify.sh`, remove `SERVERCHAN_STATUS_FILE` and pass:

```bash
exec "${VENV_PYTHON}" -m momentum_alpha.serverchan \
  --sendkey "${SERVERCHAN_SENDKEY}" \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --health-output-file "${TMP_OUTPUT}" \
  --hostname "$(hostname)"
```

Ensure `RUNTIME_DB_FILE` is defined in the script:

```bash
RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"
```

In `deploy/env.example`, remove:

```bash
SERVERCHAN_STATUS_FILE=/Users/your-user/momentum_alpha/var/health_status.json
```

- [ ] **Step 7: Run affected tests**

Run:

```bash
python -m unittest tests.test_runtime_store tests.test_serverchan tests.test_deploy_artifacts -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add src/momentum_alpha/runtime_store.py src/momentum_alpha/serverchan.py scripts/check_health_and_notify.sh deploy/env.example tests
git commit -m "refactor: persist notification status in sqlite"
```

---

### Task 5: Clean Documentation And Deploy References

**Files:**
- Modify: `README.md`
- Modify: `CLAUDE.md`
- Modify: `docs/live-deployment-checklist.md`
- Modify: `docs/live-ops-checklist.md`
- Modify: `deploy/env.example`
- Test: `tests/test_deploy_artifacts.py`

- [ ] **Step 1: Write deploy artifact assertions**

Add to `tests/test_deploy_artifacts.py`:

```python
    def test_env_example_has_no_json_state_configuration(self) -> None:
        content = (ROOT / "deploy" / "env.example").read_text()
        self.assertIn("RUNTIME_DB_FILE=", content)
        self.assertNotIn("STATE_FILE=", content)
        self.assertNotIn("AUDIT_LOG_FILE=", content)
        self.assertNotIn("SERVERCHAN_STATUS_FILE=", content)

    def test_readme_no_longer_mentions_state_file_cli(self) -> None:
        content = (ROOT / "README.md").read_text()
        self.assertNotIn("--state-file", content)
        self.assertNotIn("state.json", content)
        self.assertNotIn("audit.jsonl", content)
        self.assertIn("--runtime-db-file", content)
```

- [ ] **Step 2: Run tests and verify failure**

Run:

```bash
python -m unittest tests.test_deploy_artifacts -v
```

Expected: FAIL because docs and env example still mention JSON state/audit artifacts.

- [ ] **Step 3: Update README commands and architecture**

Replace all CLI examples that use `--state-file` with `--runtime-db-file ./var/runtime.db`.

Replace the data flow section text with:

```text
Market Snapshots -> Strategy Evaluation -> Execution Plan -> Broker -> Binance API
                         |
                         v
                   Runtime DB (runtime.db)
```

Replace dashboard data source bullets with:

```markdown
The dashboard reads runtime state, health, recent events, fills, account flows, and snapshots from `runtime.db`.
```

Replace safety note:

```markdown
- Runtime persistence stores previous leader, local position view, processed user-stream event ids, tracked order statuses, structured audit events, and dashboard query data in `runtime.db`.
```

- [ ] **Step 4: Update CLAUDE.md**

Change persistence section:

```markdown
**Persistence**:
- `strategy_state_codec.py`: Strategy state payload schema and serialization helpers, no file I/O
- `runtime_store.py`: SQLite-backed runtime state, audit, analytics, and notification status store
```

Change deployment runtime directories:

```markdown
- `var/runtime.db`: SQLite runtime state, audit events, analytics, and notification status
- `var/log/`: Operational service logs
```

Remove examples and architecture lines that mention:

```text
--state-file
state.json
audit.jsonl
JSON-based strategy state persistence
```

- [ ] **Step 5: Update live docs**

In `docs/live-deployment-checklist.md` and `docs/live-ops-checklist.md`, replace state/audit file checks with DB checks:

```markdown
- Confirm `RUNTIME_DB_FILE` points to a persistent writable SQLite path.
- Confirm `runtime.db` has fresh `strategy_state` and `audit_events` rows after startup.
- Use `bash scripts/audit_report.sh` to review the latest structured decision and fill history from `runtime.db`.
```

Remove checks that require:

```text
STATE_FILE
AUDIT_LOG_FILE
state.json exists
audit.jsonl is growing
```

- [ ] **Step 6: Run documentation grep**

Run:

```bash
rg -n "STATE_FILE|AUDIT_LOG_FILE|SERVERCHAN_STATUS_FILE|--state-file|state\\.json|audit\\.jsonl|FileStateStore" README.md CLAUDE.md docs deploy src scripts tests
```

Expected: no output except historical implementation plan files under `docs/plans/` and `docs/superpowers/plans/` if the command is intentionally broadened to include archived plans. For the strict check, run:

```bash
rg -n "STATE_FILE|AUDIT_LOG_FILE|SERVERCHAN_STATUS_FILE|--state-file|state\\.json|audit\\.jsonl|FileStateStore" README.md CLAUDE.md docs/live-deployment-checklist.md docs/live-ops-checklist.md deploy src scripts tests
```

Expected: no output.

- [ ] **Step 7: Run deploy tests**

Run:

```bash
python -m unittest tests.test_deploy_artifacts -v
```

Expected: PASS.

- [ ] **Step 8: Commit**

```bash
git add README.md CLAUDE.md docs/live-deployment-checklist.md docs/live-ops-checklist.md deploy/env.example tests/test_deploy_artifacts.py
git commit -m "docs: document database-only runtime storage"
```

---

### Task 6: Final Verification And Operator Cleanup Guidance

**Files:**
- Modify only if verification exposes gaps.

- [ ] **Step 1: Run full test suite**

Run:

```bash
python -m unittest discover -s tests -v
```

Expected: PASS.

- [ ] **Step 2: Verify DB schema includes all runtime tables**

Run:

```bash
python - <<'PY'
from pathlib import Path
import sqlite3
from momentum_alpha.runtime_store import bootstrap_runtime_db

path = Path("/tmp/momentum-alpha-db-only-verification.db")
if path.exists():
    path.unlink()
bootstrap_runtime_db(path=path)
connection = sqlite3.connect(path)
try:
    tables = {row[0] for row in connection.execute("SELECT name FROM sqlite_master WHERE type='table'")}
finally:
    connection.close()
print("\n".join(sorted(tables)))
PY
```

Expected output includes:

```text
account_flows
account_snapshots
algo_orders
audit_events
broker_orders
notification_statuses
position_snapshots
signal_decisions
stop_exit_summaries
strategy_state
trade_fills
trade_round_trips
```

- [ ] **Step 3: Verify no production file persistence remains**

Run:

```bash
rg -n "NamedTemporaryFile|json\\.dump|write_text|read_text|fcntl|FileStateStore|state\\.json|audit\\.jsonl|--state-file|STATE_FILE|AUDIT_LOG_FILE|SERVERCHAN_STATUS_FILE" src scripts deploy README.md CLAUDE.md docs/live-deployment-checklist.md docs/live-ops-checklist.md
```

Expected: output is limited to non-storage uses such as HTTP JSON response serialization, test fixture reads, or script text unrelated to durable state. Investigate and remove any remaining durable JSON/file state writes.

- [ ] **Step 4: Verify local runtime DB has expected tables**

Run:

```bash
sqlite3 var/runtime.db ".tables"
```

Expected: output includes `strategy_state`, `audit_events`, structured runtime tables, and `notification_statuses` after the service or bootstrap code has run once.

- [ ] **Step 5: Provide safe operator cleanup instructions**

Do not delete historical files automatically. Give the operator this command block after DB-only tests and services have been verified:

```bash
mkdir -p var/archive-pre-db-only
mv var/state.json var/state.json.lock var/audit.jsonl var/archive-pre-db-only/ 2>/dev/null || true
```

Then ask the operator to restart services and run:

```bash
bash scripts/check_health.sh
bash scripts/audit_report.sh
```

Expected: both commands work without recreating `state.json` or `audit.jsonl`.

- [ ] **Step 6: Commit any final verification fixes**

If verification required edits:

```bash
git add <changed-files>
git commit -m "fix: complete database-only runtime verification"
```

If no edits were required, do not create an empty commit.

---

## Self-Review

- Spec coverage: The plan covers CLI DB enforcement, JSON state-store removal, DB-only health/dashboard reads, DB-backed notification status, docs/deploy cleanup, and final verification.
- Placeholder scan: The plan contains no unresolved placeholder steps.
- Type consistency: `StoredStrategyState` moves to `strategy_state_codec.py`; `runtime_store.py` imports the same type and public serializer functions consistently. `notification_statuses` is the table name used by runtime store helpers and final schema verification.
