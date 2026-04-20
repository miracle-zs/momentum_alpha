# Dashboard Daily Review Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a daily review block inside `复盘室` that summarizes the previous `UTC+8 08:30 -> UTC+8 08:30` trading window, and generate that report daily with a scheduled job.

**Architecture:** Keep the existing single dashboard server. Add a focused `daily_review` domain module for window calculation and counterfactual replay, extend `runtime_store` with a persisted daily-report table and query helpers, and have the dashboard render the latest stored report rather than recomputing it on every request. The replay must use stored market/symbol metadata and the same sizing rules as live execution, so the report can reconstruct the unconditional hourly add-on counterfactual without reaching back to the exchange.

**Tech Stack:** Python standard library, SQLite, `unittest`, existing `momentum_alpha.dashboard`, `momentum_alpha.runtime_store`, and `momentum_alpha.main` patterns, plus existing shell wrappers and systemd units.

---

## File Map

- Create: `src/momentum_alpha/daily_review.py`
  - Responsibility: compute the `08:30 Asia/Shanghai` window, replay the unconditional hourly add-on counterfactual, and assemble a report object from runtime DB inputs.
- Modify: `src/momentum_alpha/runtime_store.py`
  - Responsibility: persist daily review reports and expose query helpers for report inputs and latest stored report.
- Modify: `src/momentum_alpha/main.py`
  - Responsibility: enrich stored snapshot payloads with symbol filter metadata, add the `daily-review-report` CLI command, and wire the scheduled report generation path.
- Modify: `src/momentum_alpha/dashboard.py`
  - Responsibility: load the latest daily review report and render the daily review block inside `复盘室`.
- Create: `tests/test_daily_review.py`
  - Responsibility: cover window boundaries, counterfactual replay totals, and warning behavior.
- Modify: `tests/test_runtime_store.py`
  - Responsibility: verify the new report table exists and report rows round-trip through SQLite.
- Modify: `tests/test_main.py`
  - Responsibility: verify market payloads persist filter metadata needed for report replay and that the CLI command is wired.
- Modify: `tests/test_dashboard.py`
  - Responsibility: verify the daily review block renders in `复盘室` and shows the expected summary fields.
- Create: `scripts/run_daily_review_report.sh`
  - Responsibility: invoke the new CLI command from cron/systemd with the runtime DB path.
- Create: `deploy/systemd/momentum-alpha-daily-review-report.service`
  - Responsibility: run one report generation pass.
- Create: `deploy/systemd/momentum-alpha-daily-review-report.timer`
  - Responsibility: fire the report service daily at `08:30`.
- Modify: `scripts/install_systemd.sh`
  - Responsibility: install and enable the new timer/service pair.
- Modify: `docs/live-ops-checklist.md`
  - Responsibility: document the daily report job alongside the existing health and analytics jobs.
- Modify: `tests/test_deploy_artifacts.py`
  - Responsibility: verify the new script and systemd unit files are present and reference the new command.

## Task 1: Persist Daily Review Reports And Store Replay Inputs Needed For Sizing

**Files:**
- Modify: `src/momentum_alpha/main.py:225-335, 920-1045`
- Modify: `src/momentum_alpha/runtime_store.py:1-220, 872-980, 1412-1455`
- Modify: `tests/test_main.py`
- Modify: `tests/test_runtime_store.py`

- [ ] **Step 1: Write failing tests for replay inputs and report persistence**

Add a `tests/test_main.py` case that proves market payloads now carry symbol filter metadata:

```python
def test_build_market_context_payloads_includes_symbol_filters(self) -> None:
    from decimal import Decimal
    from momentum_alpha.binance_filters import SymbolFilters
    from momentum_alpha.exchange_info import ExchangeSymbol
    from momentum_alpha.main import _build_market_context_payloads

    snapshots = [
        {
            "symbol": "BTCUSDT",
            "daily_open_price": Decimal("100"),
            "latest_price": Decimal("110"),
            "previous_hour_low": Decimal("98"),
            "tradable": True,
            "has_previous_hour_candle": True,
            "current_hour_low": Decimal("97"),
        }
    ]
    exchange_symbols = {
        "BTCUSDT": ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.1")),
            min_notional=Decimal("5"),
        )
    }

    payloads, leader_gap_pct = _build_market_context_payloads(
        snapshots=snapshots,
        exchange_symbols=exchange_symbols,
    )

    self.assertIsNone(leader_gap_pct)
    self.assertEqual(payloads["BTCUSDT"]["step_size"], "0.001")
    self.assertEqual(payloads["BTCUSDT"]["min_qty"], "0.001")
    self.assertEqual(payloads["BTCUSDT"]["tick_size"], "0.1")
```

Add a `tests/test_runtime_store.py` case that proves the new daily report table exists and a stored report can be fetched back:

```python
def test_daily_review_report_round_trips_through_sqlite(self) -> None:
    from momentum_alpha.runtime_store import (
        bootstrap_runtime_db,
        fetch_latest_daily_review_report,
        insert_daily_review_report,
    )

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "runtime.db"
        bootstrap_runtime_db(path=db_path)
        insert_daily_review_report(
            path=db_path,
            report_date="2026-04-21",
            window_start="2026-04-20T08:30:00+08:00",
            window_end="2026-04-21T08:30:00+08:00",
            generated_at="2026-04-21T08:30:01+08:00",
            status="ok",
            trade_count=2,
            actual_total_pnl="12.50",
            counterfactual_total_pnl="18.25",
            pnl_delta="5.75",
            replayed_add_on_count=3,
            warnings=["partial_replay"],
            payload={
                "rows": [
                    {
                        "symbol": "BTCUSDT",
                        "opened_at": "2026-04-20T09:00:00+08:00",
                        "closed_at": "2026-04-20T12:00:00+08:00",
                        "actual_net_pnl": "5.00",
                        "counterfactual_net_pnl": "7.50",
                    }
                ],
                "strategy_config": {"stop_budget_usdt": "10"},
            },
        )

        report = fetch_latest_daily_review_report(path=db_path)

        self.assertEqual(report["report_date"], "2026-04-21")
        self.assertEqual(report["status"], "ok")
        self.assertEqual(report["trade_count"], 2)
        self.assertEqual(report["payload"]["rows"][0]["symbol"], "BTCUSDT")
```

- [ ] **Step 2: Run the focused tests and confirm they fail**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_build_market_context_payloads_includes_symbol_filters tests.test_runtime_store.RuntimeStoreTests.test_daily_review_report_round_trips_through_sqlite -v
```

Expected: FAIL because `_build_market_context_payloads` does not yet accept `exchange_symbols`, and the daily report table/helpers do not exist yet.

- [ ] **Step 3: Add symbol filter metadata to stored snapshot payloads and daily report persistence**

In `src/momentum_alpha/main.py`, extend `_build_market_context_payloads` so it can accept the live exchange symbol map and append filter metadata:

```python
def _build_market_context_payloads(
    *,
    snapshots: list[dict],
    exchange_symbols: dict[str, object] | None = None,
) -> tuple[dict[str, dict], Decimal | None]:
    for item in ordered:
        exchange_symbol = None if exchange_symbols is None else exchange_symbols.get(item["symbol"])
        filters = getattr(exchange_symbol, "filters", None)
        payloads[item["symbol"]] = {
            "latest_price": str(item["latest_price"]),
            "daily_open_price": str(item["daily_open_price"]),
            "daily_change_pct": str(item["daily_change_pct"]),
            "previous_hour_low": str(item["previous_hour_low"]),
            "current_hour_low": str(item["current_hour_low"]),
            "leader_gap_pct": str(leader_gap_pct) if item["symbol"] == ordered[0]["symbol"] and leader_gap_pct is not None else None,
            "step_size": str(filters.step_size) if filters is not None else None,
            "min_qty": str(filters.min_qty) if filters is not None else None,
            "tick_size": str(filters.tick_size) if filters is not None else None,
        }
```

Thread the same `exchange_symbols` map into the `_record_position_snapshot(...)` and `_record_signal_decision(...)` payloads by passing through the enriched `market_payloads`. The goal is that the stored `position_snapshots.payload.positions[symbol]`, `position_snapshots.payload.market_context.candidates[*]`, and `signal_decisions.payload` rows contain the filter fields needed for later replay.

In `src/momentum_alpha/runtime_store.py`, add a new persisted table and helpers near the existing `trade_round_trips` schema:

```python
CREATE TABLE IF NOT EXISTS daily_review_reports (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    report_date TEXT NOT NULL,
    window_start TEXT NOT NULL,
    window_end TEXT NOT NULL,
    generated_at TEXT NOT NULL,
    status TEXT NOT NULL,
    trade_count INTEGER NOT NULL,
    actual_total_pnl TEXT NOT NULL,
    counterfactual_total_pnl TEXT NOT NULL,
    pnl_delta TEXT NOT NULL,
    replayed_add_on_count INTEGER NOT NULL,
    stop_budget_usdt TEXT NOT NULL,
    entry_start_hour_utc INTEGER NOT NULL,
    entry_end_hour_utc INTEGER NOT NULL,
    warning_json TEXT NOT NULL,
    payload_json TEXT NOT NULL
);
CREATE UNIQUE INDEX IF NOT EXISTS idx_daily_review_reports_report_date
    ON daily_review_reports(report_date);
CREATE INDEX IF NOT EXISTS idx_daily_review_reports_generated_at
    ON daily_review_reports(generated_at DESC);
```

Add these helpers in `src/momentum_alpha/runtime_store.py`:

```python
def insert_daily_review_report(
    *,
    path: Path,
    report_date: str,
    window_start: str,
    window_end: str,
    generated_at: str,
    status: str,
    trade_count: int,
    actual_total_pnl: str,
    counterfactual_total_pnl: str,
    pnl_delta: str,
    replayed_add_on_count: int,
    stop_budget_usdt: str,
    entry_start_hour_utc: int,
    entry_end_hour_utc: int,
    warnings: list[str],
    payload: dict,
) -> None:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        connection.execute(
            """
            INSERT INTO daily_review_reports (
                report_date, window_start, window_end, generated_at, status, trade_count,
                actual_total_pnl, counterfactual_total_pnl, pnl_delta, replayed_add_on_count,
                stop_budget_usdt, entry_start_hour_utc, entry_end_hour_utc, warning_json, payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                report_date,
                window_start,
                window_end,
                generated_at,
                status,
                trade_count,
                actual_total_pnl,
                counterfactual_total_pnl,
                pnl_delta,
                replayed_add_on_count,
                stop_budget_usdt,
                entry_start_hour_utc,
                entry_end_hour_utc,
                json.dumps(warnings, ensure_ascii=False),
                json.dumps(payload, ensure_ascii=False),
            ),
        )
        connection.commit()

def fetch_latest_daily_review_report(*, path: Path) -> dict | None:
    with sqlite3.connect(path) as connection:
        connection.row_factory = sqlite3.Row
        row = connection.execute(
            "SELECT * FROM daily_review_reports ORDER BY generated_at DESC, id DESC LIMIT 1"
        ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["warnings"] = json.loads(result.pop("warning_json"))
        result["payload"] = json.loads(result.pop("payload_json"))
        return result

def fetch_trade_round_trips_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
    return fetch_trade_round_trips_between(path=path, start=window_start, end=window_end)

def fetch_signal_decisions_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
    return fetch_signal_decisions_between(path=path, start=window_start, end=window_end)
```

- [ ] **Step 4: Run the targeted tests again and verify they pass**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_build_market_context_payloads_includes_symbol_filters tests.test_runtime_store.RuntimeStoreTests.test_daily_review_report_round_trips_through_sqlite -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/main.py src/momentum_alpha/runtime_store.py tests/test_main.py tests/test_runtime_store.py
git commit -m "feat: persist daily review replay inputs"
```

## Task 2: Build The Daily Review Replay Engine And CLI Command

**Files:**
- Create: `src/momentum_alpha/daily_review.py`
- Modify: `src/momentum_alpha/main.py:1407-1605, 1608-1735`
- Create: `tests/test_daily_review.py`

- [ ] **Step 1: Write failing tests for the report window and counterfactual replay**

Create `tests/test_daily_review.py` with focused tests that cover the local `08:30` window and the unconditional add-on replay:

```python
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from unittest.mock import patch


class DailyReviewTests(unittest.TestCase):
    def test_build_daily_review_window_anchors_to_0830_asia_shanghai(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_window

        window = build_daily_review_window(
            now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc)
        )

        self.assertEqual(window.report_date, "2026-04-21")
        self.assertEqual(window.window_start.isoformat(), "2026-04-20T08:30:00+08:00")
        self.assertEqual(window.window_end.isoformat(), "2026-04-21T08:30:00+08:00")

    def test_build_daily_review_report_replays_skipped_add_ons(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_report

        trade_round_trips = [
            {
                "round_trip_id": "BTCUSDT:1",
                "symbol": "BTCUSDT",
                "opened_at": "2026-04-20T09:00:00+08:00",
                "closed_at": "2026-04-20T12:00:00+08:00",
                "net_pnl": "10.00",
                "legs": [
                    {"leg_type": "base", "quantity": "1", "entry_price": "100", "exit_price": "110", "net_pnl_contribution": "10.00"},
                ],
            }
        ]
        signal_decisions = [
            {
                "timestamp": "2026-04-20T10:00:00+08:00",
                "decision_type": "add_on_skipped",
                "symbol": "BTCUSDT",
                "payload": {
                    "latest_price": "105",
                    "stop_price": "95",
                    "step_size": "0.001",
                    "min_qty": "0.001",
                    "tick_size": "0.1",
                },
            }
        ]

        with patch("momentum_alpha.daily_review.fetch_trade_round_trips_for_window", return_value=trade_round_trips), patch(
            "momentum_alpha.daily_review.fetch_signal_decisions_for_window",
            return_value=signal_decisions,
        ):
            report = build_daily_review_report(
                path=Path("/tmp/runtime.db"),
                now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc),
                stop_budget_usdt=Decimal("10"),
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
            )

        self.assertEqual(report.trade_count, 1)
        self.assertEqual(report.actual_total_pnl, "10.00")
        self.assertGreater(Decimal(report.counterfactual_total_pnl), Decimal("10.00"))
        self.assertEqual(report.rows[0].symbol, "BTCUSDT")
```

The replay test should use a small, deterministic fixture where:

- one trade closes inside the window
- one `add_on_skipped` decision exists for the same symbol and lifetime
- the stored market payload contains `latest_price`, `stop_price`, `step_size`, `min_qty`, and `tick_size`
- the expected counterfactual PnL is larger than the real PnL by a predictable amount

- [ ] **Step 2: Run the new tests and confirm they fail**

Run:

```bash
python3 -m unittest tests.test_daily_review -v
```

Expected: FAIL because the module and replay helpers do not exist yet.

- [ ] **Step 3: Implement the replay engine and report builder**

Create `src/momentum_alpha/daily_review.py` with these concrete pieces:

```python
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.binance_filters import SymbolFilters
from momentum_alpha.orders import is_strategy_client_order_id
from momentum_alpha.sizing import size_from_stop_budget
from momentum_alpha.runtime_store import (
    fetch_signal_decisions_for_window,
    fetch_trade_round_trips_for_window,
)

DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
DAILY_REVIEW_CUTOFF_HOUR = 8
DAILY_REVIEW_CUTOFF_MINUTE = 30

@dataclass(frozen=True)
class DailyReviewWindow:
    report_date: str
    window_start: datetime
    window_end: datetime

@dataclass(frozen=True)
class DailyReviewTradeRow:
    round_trip_id: str
    symbol: str
    opened_at: str
    closed_at: str
    actual_net_pnl: str
    counterfactual_net_pnl: str
    pnl_delta: str
    leg_count: int
    replayed_add_on_count: int
    warnings: tuple[str, ...]

@dataclass(frozen=True)
class DailyReviewReport:
    report_date: str
    window_start: str
    window_end: str
    generated_at: str
    status: str
    trade_count: int
    actual_total_pnl: str
    counterfactual_total_pnl: str
    pnl_delta: str
    replayed_add_on_count: int
    stop_budget_usdt: str
    entry_start_hour_utc: int
    entry_end_hour_utc: int
    warnings: tuple[str, ...]
    rows: tuple[DailyReviewTradeRow, ...]
```

Add these functions in the same module:

```python
def build_daily_review_window(*, now: datetime) -> DailyReviewWindow:
    local_now = now.astimezone(DISPLAY_TIMEZONE)
    today_anchor = local_now.replace(hour=DAILY_REVIEW_CUTOFF_HOUR, minute=DAILY_REVIEW_CUTOFF_MINUTE, second=0, microsecond=0)
    if local_now >= today_anchor:
        window_end = today_anchor
    else:
        window_end = today_anchor - timedelta(days=1)
    window_start = window_end - timedelta(days=1)
    return DailyReviewWindow(
        report_date=window_end.date().isoformat(),
        window_start=window_start,
        window_end=window_end,
    )

def build_daily_review_report(
    *,
    path: Path,
    now: datetime,
    stop_budget_usdt: Decimal,
    entry_start_hour_utc: int,
    entry_end_hour_utc: int,
) -> DailyReviewReport:
    window = build_daily_review_window(now=now)
    trade_round_trips = fetch_trade_round_trips_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    signal_decisions = fetch_signal_decisions_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    rows, warnings = _build_daily_review_rows(
        trade_round_trips=trade_round_trips,
        signal_decisions=signal_decisions,
        stop_budget_usdt=stop_budget_usdt,
    )
    report = DailyReviewReport(
        report_date=window.report_date,
        window_start=window.window_start.isoformat(),
        window_end=window.window_end.isoformat(),
        generated_at=now.astimezone(DISPLAY_TIMEZONE).isoformat(),
        status="ok" if not warnings else "warning",
        trade_count=len(rows),
        actual_total_pnl=str(sum((Decimal(row.actual_net_pnl) for row in rows), Decimal("0"))),
        counterfactual_total_pnl=str(sum((Decimal(row.counterfactual_net_pnl) for row in rows), Decimal("0"))),
        pnl_delta=str(
            sum((Decimal(row.counterfactual_net_pnl) for row in rows), Decimal("0"))
            - sum((Decimal(row.actual_net_pnl) for row in rows), Decimal("0"))
        ),
        replayed_add_on_count=sum(row.replayed_add_on_count for row in rows),
        stop_budget_usdt=str(stop_budget_usdt),
        entry_start_hour_utc=entry_start_hour_utc,
        entry_end_hour_utc=entry_end_hour_utc,
        warnings=tuple(warnings),
        rows=tuple(rows),
    )
    return report
```

The replay helper should use the stored market payload fields and `SymbolFilters(step_size, min_qty, tick_size)` to recreate the quantity for each skipped add-on:

```python
filters = SymbolFilters(
    step_size=Decimal(signal_payload["step_size"]),
    min_qty=Decimal(signal_payload["min_qty"]),
    tick_size=Decimal(signal_payload["tick_size"]),
)
quantity = size_from_stop_budget(
    entry_price=Decimal(signal_payload["latest_price"]),
    stop_price=Decimal(signal_payload["stop_price"]),
    stop_budget=stop_budget_usdt,
    filters=filters,
)
```

Counterfactual PnL should be computed from the actual trade exit price and the replayed leg set. If any add-on row is missing the sizing inputs, the row should be marked incomplete and the report should carry a warning instead of inventing a quantity.

Update `src/momentum_alpha/main.py` to add a new parser branch:

```python
daily_review_parser = subparsers.add_parser("daily-review-report")
daily_review_parser.add_argument("--runtime-db-file", required=True)
daily_review_parser.add_argument("--stop-budget-usdt", default="10")
daily_review_parser.add_argument("--entry-start-hour-utc", type=int, default=1)
daily_review_parser.add_argument("--entry-end-hour-utc", type=int, default=23)
```

The command branch should call the new builder, persist the report with `insert_daily_review_report(...)`, and print a short operator summary:

```python
if args.command == "daily-review-report":
    report = build_daily_review_report(
        path=Path(os.path.abspath(args.runtime_db_file)),
        now=now_provider(),
        stop_budget_usdt=Decimal(args.stop_budget_usdt),
        entry_start_hour_utc=args.entry_start_hour_utc,
        entry_end_hour_utc=args.entry_end_hour_utc,
    )
    insert_daily_review_report(
        path=Path(os.path.abspath(args.runtime_db_file)),
        report_date=report.report_date,
        window_start=report.window_start,
        window_end=report.window_end,
        generated_at=report.generated_at,
        status=report.status,
        trade_count=report.trade_count,
        actual_total_pnl=report.actual_total_pnl,
        counterfactual_total_pnl=report.counterfactual_total_pnl,
        pnl_delta=report.pnl_delta,
        replayed_add_on_count=report.replayed_add_on_count,
        stop_budget_usdt=report.stop_budget_usdt,
        entry_start_hour_utc=report.entry_start_hour_utc,
        entry_end_hour_utc=report.entry_end_hour_utc,
        warnings=list(report.warnings),
        payload={
            "rows": [row.__dict__ for row in report.rows],
            "strategy_config": {
                "stop_budget_usdt": report.stop_budget_usdt,
                "entry_window": f"{report.entry_start_hour_utc:02d}:00-{report.entry_end_hour_utc:02d}:00 UTC",
            },
        },
    )
    print(f"report_date={report.report_date}")
    print(f"trade_count={report.trade_count}")
    print(f"actual_total_pnl={report.actual_total_pnl}")
    print(f"counterfactual_total_pnl={report.counterfactual_total_pnl}")
    return 0
```

- [ ] **Step 4: Run the targeted tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_daily_review -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/daily_review.py src/momentum_alpha/main.py tests/test_daily_review.py
git commit -m "feat: add daily review report builder"
```

## Task 3: Render The Daily Review Block In The Dashboard Review Room

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:28-35, 1189-1325, 2067-2125, 3815-4075`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing dashboard tests for the new daily review section**

Add a dashboard test that injects a stored daily report and asserts the `review` room renders it before the broader `Closed Trade Detail` section:

```python
def test_render_dashboard_html_shows_daily_review_block_in_review_room(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["daily_review_report"] = {
        "report_date": "2026-04-21",
        "window_start": "2026-04-20T08:30:00+08:00",
        "window_end": "2026-04-21T08:30:00+08:00",
        "generated_at": "2026-04-21T08:30:01+08:00",
        "status": "ok",
        "trade_count": 2,
        "actual_total_pnl": "12.50",
        "counterfactual_total_pnl": "18.25",
        "pnl_delta": "5.75",
        "replayed_add_on_count": 3,
        "warnings": [],
        "payload": {
            "rows": [
                {
                    "symbol": "BTCUSDT",
                    "opened_at": "2026-04-20T09:00:00+08:00",
                    "closed_at": "2026-04-20T12:00:00+08:00",
                    "actual_net_pnl": "5.00",
                    "counterfactual_net_pnl": "7.50",
                    "pnl_delta": "2.50",
                    "leg_count": 2,
                    "replayed_add_on_count": 1,
                }
            ]
        },
    }

    html = render_dashboard_html(snapshot, active_room="review")

    self.assertIn("每日复盘", html)
    self.assertIn("2026-04-21", html)
    self.assertIn("12.50", html)
    self.assertIn("18.25", html)
    self.assertLess(html.index("每日复盘"), html.index("Closed Trade Detail"))
```

- [ ] **Step 2: Run the targeted test and confirm it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_shows_daily_review_block_in_review_room -v
```

Expected: FAIL because the dashboard does not yet load or render the daily report.

- [ ] **Step 3: Load the latest daily report and render a compact daily summary card**

In `src/momentum_alpha/dashboard.py`, import the new fetch helper and wire it into `load_dashboard_snapshot(...)`:

```python
from .runtime_store import fetch_latest_daily_review_report

daily_review_report = (
    fetch_latest_daily_review_report(path=runtime_db_file)
    if runtime_db_file.exists()
    else None
)
```

Then add `"daily_review_report": daily_review_report,` to the snapshot dictionary that `load_dashboard_snapshot(...)` already returns.

Add a renderer that keeps the daily block compact and separate from the existing ledger:

```python
def render_daily_review_panel(report: dict | None) -> str:
    if report is None:
        return "<section class='dashboard-section daily-review-panel'><div class='section-header'>每日复盘</div><div class='trade-history-empty'>No daily review report</div></section>"

    rows = "".join(
        f"<div class='analytics-row'>"
        f"<span class='analytics-main'><b>{escape(str(row['symbol']))}</b></span>"
        f"<span>{escape(str(row['opened_at']))}</span>"
        f"<span>{escape(str(row['closed_at']))}</span>"
        f"<span>{escape(str(row['actual_net_pnl']))}</span>"
        f"<span>{escape(str(row['counterfactual_net_pnl']))}</span>"
        f"<span>{escape(str(row['pnl_delta']))}</span>"
        "</div>"
        for row in (report.get("payload", {}).get("rows") or [])
    )
    return (
        "<section class='dashboard-section daily-review-panel'>"
        "<div class='section-header'>每日复盘</div>"
        "<div class='daily-review-summary'>"
        f"<div>Report Date <b>{escape(str(report['report_date']))}</b></div>"
        f"<div>Trades <b>{escape(str(report['trade_count']))}</b></div>"
        f"<div>Actual <b>{escape(str(report['actual_total_pnl']))}</b></div>"
        f"<div>Counterfactual <b>{escape(str(report['counterfactual_total_pnl']))}</b></div>"
        f"<div>Delta <b>{escape(str(report['pnl_delta']))}</b></div>"
        "</div>"
        f"<div class='analytics-table'>{rows}</div>"
        "</section>"
    )
```

Change `render_dashboard_performance_tab(...)` to accept a `daily_review_html: str` argument and place it before the `Closed Trade Detail` card, then pass that argument through `render_dashboard_review_room(...)`:

```python
def render_dashboard_performance_tab(
    *,
    daily_review_html: str,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="review">'
        "<section class='section-frame' data-collapsible-section='review'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>复盘室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Closed Trade Detail is the primary review surface; aggregates follow the ledger.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        f"{daily_review_html}"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Complete Trade Summary (all closed trades)</div>"
        f"{performance_summary_html}"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Closed Trade Detail</div>"
        f"<div class='table-scroll'>{round_trip_detail_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Total Leg Count</div>"
        f"<div class='table-scroll'>{leg_count_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Leg Index</div>"
        f"<div class='table-scroll'>{leg_index_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div class='section-header' style='margin-bottom:10px;'>STOP SLIPPAGE ANALYSIS</div>"
        f"<div class='table-scroll'>{stop_slippage_html}</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )

def render_dashboard_review_room(
    *,
    daily_review_html: str,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
    ) -> str:
        return render_dashboard_performance_tab(
            daily_review_html=daily_review_html,
            performance_summary_html=performance_summary_html,
            round_trip_detail_html=round_trip_detail_html,
        leg_count_aggregate_html=leg_count_aggregate_html,
        leg_index_aggregate_html=leg_index_aggregate_html,
        stop_slippage_html=stop_slippage_html,
    )
```

Keep the existing ledger and aggregate sections intact.

- [ ] **Step 4: Run the targeted dashboard test and verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_shows_daily_review_block_in_review_room -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard.py tests/test_dashboard.py
git commit -m "feat: render daily review in dashboard"
```

## Task 4: Add The 08:30 Daily Job And Document The New Operational Step

**Files:**
- Create: `scripts/run_daily_review_report.sh`
- Create: `deploy/systemd/momentum-alpha-daily-review-report.service`
- Create: `deploy/systemd/momentum-alpha-daily-review-report.timer`
- Modify: `scripts/install_systemd.sh`
- Modify: `docs/live-ops-checklist.md`
- Modify: `tests/test_deploy_artifacts.py`

- [ ] **Step 1: Write failing deployment-artifact tests for the new script and unit files**

Add assertions to `tests/test_deploy_artifacts.py` that the repo contains the new operational wrappers:

```python
def test_daily_review_report_script_invokes_daily_review_command(self) -> None:
    content = (ROOT / "scripts" / "run_daily_review_report.sh").read_text()
    self.assertIn("daily-review-report", content)
    self.assertIn("--runtime-db-file", content)

def test_daily_review_systemd_service_declares_the_report_command(self) -> None:
    service = (ROOT / "deploy" / "systemd" / "momentum-alpha-daily-review-report.service").read_text()
    timer = (ROOT / "deploy" / "systemd" / "momentum-alpha-daily-review-report.timer").read_text()
    self.assertIn("daily-review-report", service)
    self.assertIn("OnCalendar=", timer)
```

- [ ] **Step 2: Run the artifact tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_deploy_artifacts -v
```

Expected: FAIL because the script and unit files do not yet exist.

- [ ] **Step 3: Add the script and systemd units**

Create `scripts/run_daily_review_report.sh` following the same pattern as `scripts/audit_report.sh`:

```bash
#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"
STOP_BUDGET_USDT="${STOP_BUDGET_USDT:-10}"
ENTRY_START_HOUR_UTC="${ENTRY_START_HOUR_UTC:-1}"
ENTRY_END_HOUR_UTC="${ENTRY_END_HOUR_UTC:-23}"

exec "${VENV_PYTHON}" -m momentum_alpha.main daily-review-report \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --stop-budget-usdt "${STOP_BUDGET_USDT}" \
  --entry-start-hour-utc "${ENTRY_START_HOUR_UTC}" \
  --entry-end-hour-utc "${ENTRY_END_HOUR_UTC}"
```

Create `deploy/systemd/momentum-alpha-daily-review-report.service`:

```ini
[Unit]
Description=Momentum Alpha Daily Review Report
After=network-online.target

[Service]
Type=oneshot
WorkingDirectory=/root/momentum_alpha
Environment=RUNTIME_DB_FILE=/root/momentum_alpha/var/runtime.db
Environment=STOP_BUDGET_USDT=10
Environment=ENTRY_START_HOUR_UTC=1
Environment=ENTRY_END_HOUR_UTC=23
ExecStart=/root/momentum_alpha/scripts/run_daily_review_report.sh
```

Create `deploy/systemd/momentum-alpha-daily-review-report.timer`:

```ini
[Unit]
Description=Run Momentum Alpha Daily Review Report at 08:30

[Timer]
OnCalendar=*-*-* 08:30:00
Persistent=true
Unit=momentum-alpha-daily-review-report.service

[Install]
WantedBy=timers.target
```

Update `scripts/install_systemd.sh` so it copies and enables the new service and timer alongside the existing units:

```bash
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-daily-review-report.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-daily-review-report.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl enable --now momentum-alpha-daily-review-report.timer
```

Document the new operational step in `docs/live-ops-checklist.md` under the daily checks section:

```md
- Confirm the daily review timer has run successfully at 08:30 and produced a fresh `daily_review_reports` row in `runtime.db`
- Use `bash scripts/run_daily_review_report.sh` manually when you need to backfill or debug the daily report
```

- [ ] **Step 4: Run the artifact tests and verify they pass**

Run:

```bash
python3 -m unittest tests.test_deploy_artifacts -v
```

Expected: PASS.

- [ ] **Step 5: Commit**

```bash
git add scripts/run_daily_review_report.sh deploy/systemd/momentum-alpha-daily-review-report.service deploy/systemd/momentum-alpha-daily-review-report.timer scripts/install_systemd.sh docs/live-ops-checklist.md tests/test_deploy_artifacts.py
git commit -m "feat: schedule daily review report"
```

## Self-Review Checklist

- [ ] The daily window is explicitly anchored to `08:30 Asia/Shanghai`.
- [ ] The replay uses stored market payloads and stored filter metadata, not live exchange queries.
- [ ] The persisted report stores both actual and counterfactual totals.
- [ ] The dashboard renders the daily block inside `复盘室` and keeps the broad closed-trade ledger intact.
- [ ] The scheduler is externalized as a daily systemd job, not as an in-app loop.
- [ ] The tests cover the window boundary, persistence, replay totals, dashboard rendering, and deploy artifacts.
