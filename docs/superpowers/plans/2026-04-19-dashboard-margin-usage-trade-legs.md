# Dashboard Margin Usage And Trade Leg Analytics Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add real margin-usage charting plus complete-trade and leg-level analytics to the existing dashboard, using the current runtime store and round-trip rebuild flow.

**Architecture:** Keep real margin usage derived directly from `account_snapshots`, because that metric already exists implicitly in persisted account history. Extend `rebuild_trade_analytics()` so `trade_round_trips.payload_json` carries stable leg analytics, then teach the dashboard to query full-range round trips, aggregate them in memory, and render a trader-first `Performance` view with expandable leg detail and leg-count summaries.

**Tech Stack:** Python, unittest, SQLite-backed runtime store in `src/momentum_alpha/runtime_store.py`, server-rendered HTML/CSS/JS dashboard in `src/momentum_alpha/dashboard.py`

---

## Worktree Note

This plan was written from the primary worktree. Before execution, create or switch to a dedicated git worktree if you want isolation from unrelated local edits.

## File Map

- Modify: `src/momentum_alpha/runtime_store.py`
  - Responsibility: add range-aware closed-trade reads and extend `rebuild_trade_analytics()` to persist leg analytics in `trade_round_trips.payload_json`.
- Modify: `src/momentum_alpha/dashboard.py`
  - Responsibility: derive `margin_usage_pct` in account timeseries, extend account range stats, load full-range round trips for the `Performance` tab, compute trade aggregates, and render expandable leg-detail UI.
- Modify: `tests/test_runtime_store.py`
  - Responsibility: verify trade rebuild payload shape, stop-price fallback behavior, and round-trip range reads.
- Modify: `tests/test_dashboard.py`
  - Responsibility: verify margin-usage timeseries and account metrics rendering, plus performance-tab trade analytics and leg-detail rendering.

## Task 1: Add Range-Aware Closed-Trade Reads In The Runtime Store

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `tests/test_runtime_store.py`

- [ ] **Step 1: Write the failing test for range-aware round-trip queries**

Add this test to `tests/test_runtime_store.py` inside `RuntimeStoreTests`:

```python
def test_fetch_trade_round_trips_for_range_returns_all_rows_in_visible_window(self) -> None:
    from momentum_alpha.runtime_store import (
        bootstrap_runtime_db,
        fetch_trade_round_trips_for_range,
        insert_trade_round_trip,
    )

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "runtime.db"
        bootstrap_runtime_db(path=db_path)

        insert_trade_round_trip(
            path=db_path,
            round_trip_id="BTCUSDT:1",
            symbol="BTCUSDT",
            opened_at=datetime(2026, 4, 19, 0, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 4, 19, 0, 30, tzinfo=timezone.utc),
            entry_fill_count=1,
            exit_fill_count=1,
            total_entry_quantity="1",
            total_exit_quantity="1",
            weighted_avg_entry_price="100",
            weighted_avg_exit_price="105",
            realized_pnl="5",
            commission="0.1",
            net_pnl="4.9",
            exit_reason="sell",
            duration_seconds=1800,
            payload={"leg_count": 1},
        )
        insert_trade_round_trip(
            path=db_path,
            round_trip_id="BTCUSDT:2",
            symbol="BTCUSDT",
            opened_at=datetime(2026, 4, 19, 4, 0, tzinfo=timezone.utc),
            closed_at=datetime(2026, 4, 19, 4, 30, tzinfo=timezone.utc),
            entry_fill_count=2,
            exit_fill_count=1,
            total_entry_quantity="2",
            total_exit_quantity="2",
            weighted_avg_entry_price="110",
            weighted_avg_exit_price="115",
            realized_pnl="10",
            commission="0.2",
            net_pnl="9.8",
            exit_reason="stop_loss",
            duration_seconds=1800,
            payload={"leg_count": 2},
        )

        rows = fetch_trade_round_trips_for_range(
            path=db_path,
            now=datetime(2026, 4, 19, 5, 0, tzinfo=timezone.utc),
            range_key="1D",
        )

        self.assertEqual([row["round_trip_id"] for row in rows], ["BTCUSDT:2", "BTCUSDT:1"])
        self.assertEqual(rows[0]["payload"]["leg_count"], 2)
```

- [ ] **Step 2: Run the targeted test and confirm failure**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_fetch_trade_round_trips_for_range_returns_all_rows_in_visible_window
```

Expected: FAIL because `fetch_trade_round_trips_for_range()` does not exist yet.

- [ ] **Step 3: Implement the range-aware fetch helper**

In `src/momentum_alpha/runtime_store.py`, add a shared round-trip window map near the account range density constants:

```python
_ROUND_TRIP_RANGE_WINDOWS = {
    "1H": timedelta(hours=1),
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
    "1M": timedelta(days=30),
    "1Y": timedelta(days=365),
    "ALL": None,
}
```

Then add the new fetch helper below `fetch_recent_trade_round_trips()`:

```python
def fetch_trade_round_trips_for_range(
    *,
    path: Path,
    now: datetime,
    range_key: str,
) -> list[dict]:
    if not path.exists():
        return []
    window = _ROUND_TRIP_RANGE_WINDOWS.get(range_key, _ROUND_TRIP_RANGE_WINDOWS["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "" if cutoff is None else "WHERE closed_at >= ?"
    params = () if cutoff is None else (cutoff.isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            {where_clause}
            ORDER BY closed_at DESC, id DESC
            """,
            params,
        ).fetchall()
    return [
        {
            "round_trip_id": row[0],
            "symbol": row[1],
            "opened_at": row[2],
            "closed_at": row[3],
            "entry_fill_count": row[4],
            "exit_fill_count": row[5],
            "total_entry_quantity": row[6],
            "total_exit_quantity": row[7],
            "weighted_avg_entry_price": row[8],
            "weighted_avg_exit_price": row[9],
            "realized_pnl": row[10],
            "commission": row[11],
            "net_pnl": row[12],
            "exit_reason": row[13],
            "duration_seconds": row[14],
            "payload": _json_loads(row[15]),
        }
        for row in rows
    ]
```

- [ ] **Step 4: Re-run the targeted test**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_fetch_trade_round_trips_for_range_returns_all_rows_in_visible_window
```

Expected: PASS

- [ ] **Step 5: Commit the task**

Run:

```bash
git add tests/test_runtime_store.py src/momentum_alpha/runtime_store.py
git commit -m "feat: add ranged closed-trade runtime queries"
```

Expected: commit succeeds and records the new range-aware closed-trade query helper.

## Task 2: Persist Leg Analytics Inside Rebuilt Round Trips

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `tests/test_runtime_store.py`

- [ ] **Step 1: Write the failing test for multi-leg payload reconstruction**

Add this test to `tests/test_runtime_store.py`:

```python
def test_rebuild_trade_analytics_persists_leg_metrics_for_multi_leg_round_trip(self) -> None:
    from momentum_alpha.runtime_store import (
        bootstrap_runtime_db,
        fetch_recent_trade_round_trips,
        insert_algo_order,
        insert_trade_fill,
        rebuild_trade_analytics,
    )

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "runtime.db"
        bootstrap_runtime_db(path=db_path)

        insert_algo_order(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 0, 0, 1, tzinfo=timezone.utc),
            source="user-stream",
            symbol="BTCUSDT",
            algo_id="11",
            client_algo_id="ma_260419000000_BTCUSDT_b00s",
            algo_status="WORKING",
            side="SELL",
            order_type="STOP_MARKET",
            trigger_price="100",
            payload={},
        )
        insert_algo_order(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 0, 10, 1, tzinfo=timezone.utc),
            source="user-stream",
            symbol="BTCUSDT",
            algo_id="12",
            client_algo_id="ma_260419001000_BTCUSDT_a01s",
            algo_status="WORKING",
            side="SELL",
            order_type="STOP_MARKET",
            trigger_price="115",
            payload={},
        )

        insert_trade_fill(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 0, 0, 0, tzinfo=timezone.utc),
            source="user-stream",
            symbol="BTCUSDT",
            order_id="1",
            trade_id="101",
            client_order_id="ma_260419000000_BTCUSDT_b00e",
            order_status="FILLED",
            execution_type="TRADE",
            side="BUY",
            order_type="MARKET",
            quantity="1",
            cumulative_quantity="1",
            average_price="110",
            last_price="110",
            realized_pnl="0",
            commission="0.3",
            commission_asset="USDT",
            payload={},
        )
        insert_trade_fill(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 0, 10, 0, tzinfo=timezone.utc),
            source="user-stream",
            symbol="BTCUSDT",
            order_id="2",
            trade_id="102",
            client_order_id="ma_260419001000_BTCUSDT_a01e",
            order_status="FILLED",
            execution_type="TRADE",
            side="BUY",
            order_type="MARKET",
            quantity="2",
            cumulative_quantity="2",
            average_price="120",
            last_price="120",
            realized_pnl="0",
            commission="0.6",
            commission_asset="USDT",
            payload={},
        )
        insert_trade_fill(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 0, 20, 0, tzinfo=timezone.utc),
            source="user-stream",
            symbol="BTCUSDT",
            order_id="3",
            trade_id="103",
            client_order_id="manual-exit",
            order_status="FILLED",
            execution_type="TRADE",
            side="SELL",
            order_type="MARKET",
            quantity="3",
            cumulative_quantity="3",
            average_price="130",
            last_price="130",
            realized_pnl="40",
            commission="1.1",
            commission_asset="USDT",
            payload={},
        )

        rebuild_trade_analytics(path=db_path)
        round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)

        self.assertEqual(len(round_trips), 1)
        payload = round_trips[0]["payload"]
        self.assertEqual(payload["leg_count"], 2)
        self.assertEqual(payload["add_on_leg_count"], 1)
        self.assertEqual(payload["base_leg_risk"], "10")
        self.assertEqual(payload["peak_cumulative_risk"], "20")
        self.assertEqual(payload["legs"][0]["leg_type"], "base")
        self.assertEqual(payload["legs"][0]["stop_price_at_entry"], "100")
        self.assertEqual(payload["legs"][0]["leg_risk"], "10")
        self.assertEqual(payload["legs"][0]["cumulative_risk_after_leg"], "10")
        self.assertEqual(payload["legs"][1]["leg_type"], "add_on")
        self.assertEqual(payload["legs"][1]["stop_price_at_entry"], "115")
        self.assertEqual(payload["legs"][1]["leg_risk"], "10")
        self.assertEqual(payload["legs"][1]["cumulative_risk_after_leg"], "20")
```

- [ ] **Step 2: Run the targeted test and confirm failure**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_rebuild_trade_analytics_persists_leg_metrics_for_multi_leg_round_trip
```

Expected: FAIL because the rebuilt round-trip payload only contains order and trade ids.

- [ ] **Step 3: Add helper functions for client-order matching and leg payload assembly**

In `src/momentum_alpha/runtime_store.py`, add these helpers above `rebuild_trade_analytics()`:

```python
def _strategy_leg_key(client_order_id: str | None) -> str | None:
    if not is_strategy_client_order_id(client_order_id):
        return None
    normalized = str(client_order_id)
    if len(normalized) < 2:
        return None
    return normalized[:-1]


def _leg_type_from_client_order_id(client_order_id: str | None) -> str:
    key = _strategy_leg_key(client_order_id)
    if key is None:
        return "unknown"
    suffix = key.rsplit("_", 1)[-1]
    return "base" if suffix.startswith("b") else "add_on"


def _resolve_entry_stop_prices(*, entry_fills: list[dict], algo_rows: list[dict]) -> dict[str, Decimal]:
    stop_by_key: dict[str, Decimal] = {}
    for algo_row in algo_rows:
        if algo_row["order_type"] != "STOP_MARKET":
            continue
        key = _strategy_leg_key(algo_row["client_algo_id"])
        if key is None or algo_row["trigger_price"] <= Decimal("0"):
            continue
        stop_by_key.setdefault(key, algo_row["trigger_price"])
    resolved: dict[str, Decimal] = {}
    for fill in entry_fills:
        key = _strategy_leg_key(fill["client_order_id"])
        if key is None:
            continue
        if key in stop_by_key:
            resolved[key] = stop_by_key[key]
    return resolved


def _build_round_trip_leg_payload(
    *,
    entry_fills: list[dict],
    weighted_exit: Decimal,
    total_entry_qty: Decimal,
    commission_total: Decimal,
    stop_prices_by_key: dict[str, Decimal],
) -> tuple[list[dict], Decimal | None, Decimal | None]:
    legs: list[dict] = []
    cumulative_risk = Decimal("0")
    peak_cumulative_risk: Decimal | None = None
    base_leg_risk: Decimal | None = None
    for index, fill in enumerate(entry_fills, start=1):
        key = _strategy_leg_key(fill["client_order_id"])
        stop_price = stop_prices_by_key.get(key) if key is not None else None
        leg_risk = None if stop_price is None else fill["quantity"] * (fill["price"] - stop_price)
        cumulative_risk_after_leg = None
        if leg_risk is not None:
            cumulative_risk += leg_risk
            cumulative_risk_after_leg = cumulative_risk
            peak_cumulative_risk = cumulative_risk if peak_cumulative_risk is None else max(peak_cumulative_risk, cumulative_risk)
            if index == 1:
                base_leg_risk = leg_risk
        gross_contribution = fill["quantity"] * (weighted_exit - fill["price"])
        fee_share = commission_total * (fill["quantity"] / total_entry_qty)
        legs.append(
            {
                "leg_index": index,
                "leg_type": _leg_type_from_client_order_id(fill["client_order_id"]),
                "opened_at": fill["timestamp"],
                "quantity": _decimal_to_text(fill["quantity"]),
                "entry_price": _decimal_to_text(fill["price"]),
                "stop_price_at_entry": _decimal_to_text(stop_price),
                "leg_risk": _decimal_to_text(leg_risk),
                "cumulative_risk_after_leg": _decimal_to_text(cumulative_risk_after_leg),
                "gross_pnl_contribution": _decimal_to_text(gross_contribution),
                "fee_share": _decimal_to_text(fee_share),
                "net_pnl_contribution": _decimal_to_text(gross_contribution - fee_share),
            }
        )
    return legs, base_leg_risk, peak_cumulative_risk
```

- [ ] **Step 4: Thread leg payload generation into `rebuild_trade_analytics()`**

Update the core insert section in `rebuild_trade_analytics()` like this:

```python
stop_prices_by_key = _resolve_entry_stop_prices(
    entry_fills=entry_fills,
    algo_rows=algo_by_symbol.get(symbol, []),
)
legs, base_leg_risk, peak_cumulative_risk = _build_round_trip_leg_payload(
    entry_fills=entry_fills,
    weighted_exit=weighted_exit,
    total_entry_qty=total_entry_qty,
    commission_total=commission_total,
    stop_prices_by_key=stop_prices_by_key,
)
round_trip_payload = {
    "entry_order_ids": [item["order_id"] for item in entry_fills if item["order_id"] is not None],
    "exit_order_ids": [item["order_id"] for item in exit_fills if item["order_id"] is not None],
    "entry_trade_ids": [item["trade_id"] for item in entry_fills if item["trade_id"] is not None],
    "exit_trade_ids": [item["trade_id"] for item in exit_fills if item["trade_id"] is not None],
    "leg_count": len(legs),
    "add_on_leg_count": max(len(legs) - 1, 0),
    "base_leg_risk": _decimal_to_text(base_leg_risk),
    "peak_cumulative_risk": _decimal_to_text(peak_cumulative_risk),
    "legs": legs,
}
```

- [ ] **Step 5: Re-run the targeted test**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_rebuild_trade_analytics_persists_leg_metrics_for_multi_leg_round_trip
```

Expected: PASS

- [ ] **Step 6: Commit the task**

Run:

```bash
git add tests/test_runtime_store.py src/momentum_alpha/runtime_store.py
git commit -m "feat: persist leg analytics in rebuilt round trips"
```

Expected: commit succeeds and records the leg-payload rebuild logic.

## Task 3: Preserve Trades When Stop-At-Entry Data Is Missing

**Files:**
- Modify: `src/momentum_alpha/runtime_store.py`
- Modify: `tests/test_runtime_store.py`

- [ ] **Step 1: Write the failing fallback test**

Add this test to `tests/test_runtime_store.py`:

```python
def test_rebuild_trade_analytics_keeps_trade_visible_when_stop_price_is_missing(self) -> None:
    from momentum_alpha.runtime_store import (
        bootstrap_runtime_db,
        fetch_recent_trade_round_trips,
        insert_trade_fill,
        rebuild_trade_analytics,
    )

    with TemporaryDirectory() as tmpdir:
        db_path = Path(tmpdir) / "runtime.db"
        bootstrap_runtime_db(path=db_path)

        insert_trade_fill(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 1, 0, tzinfo=timezone.utc),
            source="user-stream",
            symbol="ETHUSDT",
            order_id="10",
            trade_id="210",
            client_order_id="manual-entry",
            order_status="FILLED",
            execution_type="TRADE",
            side="BUY",
            order_type="MARKET",
            quantity="1",
            cumulative_quantity="1",
            average_price="200",
            last_price="200",
            realized_pnl="0",
            commission="0.2",
            commission_asset="USDT",
            payload={},
        )
        insert_trade_fill(
            path=db_path,
            timestamp=datetime(2026, 4, 19, 1, 20, tzinfo=timezone.utc),
            source="user-stream",
            symbol="ETHUSDT",
            order_id="11",
            trade_id="211",
            client_order_id="manual-exit",
            order_status="FILLED",
            execution_type="TRADE",
            side="SELL",
            order_type="MARKET",
            quantity="1",
            cumulative_quantity="1",
            average_price="210",
            last_price="210",
            realized_pnl="10",
            commission="0.3",
            commission_asset="USDT",
            payload={},
        )

        rebuild_trade_analytics(path=db_path)
        round_trips = fetch_recent_trade_round_trips(path=db_path, limit=10)

        self.assertEqual(len(round_trips), 1)
        payload = round_trips[0]["payload"]
        self.assertEqual(payload["leg_count"], 1)
        self.assertIsNone(payload["base_leg_risk"])
        self.assertIsNone(payload["peak_cumulative_risk"])
        self.assertIsNone(payload["legs"][0]["stop_price_at_entry"])
        self.assertIsNone(payload["legs"][0]["leg_risk"])
        self.assertEqual(round_trips[0]["net_pnl"], "9.5")
```

- [ ] **Step 2: Run the fallback test and confirm failure**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_rebuild_trade_analytics_keeps_trade_visible_when_stop_price_is_missing
```

Expected: FAIL if the implementation still assumes every leg can resolve a stop price or serializes missing decimals incorrectly.

- [ ] **Step 3: Make the leg payload serialization explicitly null-safe**

In `src/momentum_alpha/runtime_store.py`, keep `_decimal_to_text()` unchanged and make sure `_build_round_trip_leg_payload()` passes `None` when a stop price or risk value is unavailable:

```python
stop_price_text = _decimal_to_text(stop_price) if stop_price is not None else None
leg_risk_text = _decimal_to_text(leg_risk) if leg_risk is not None else None
cumulative_risk_text = (
    _decimal_to_text(cumulative_risk_after_leg)
    if cumulative_risk_after_leg is not None
    else None
)
```

Then use those local values in the leg payload instead of calling `_decimal_to_text()` unconditionally.

- [ ] **Step 4: Re-run the fallback test and the existing stop-loss regression**

Run:

```bash
python3 -m unittest tests.test_runtime_store.RuntimeStoreTests.test_rebuild_trade_analytics_keeps_trade_visible_when_stop_price_is_missing tests.test_runtime_store.RuntimeStoreTests.test_rebuild_trade_analytics_marks_algo_triggered_market_sell_as_stop_loss
```

Expected: PASS for both tests.

- [ ] **Step 5: Commit the task**

Run:

```bash
git add tests/test_runtime_store.py src/momentum_alpha/runtime_store.py
git commit -m "fix: keep rebuilt trades when leg stop data is missing"
```

Expected: commit succeeds and preserves trade visibility for imperfect historical data.

## Task 4: Add Margin Usage To Account Timeseries And Account Stats

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing timeseries tests**

Add these tests to `tests/test_dashboard.py` inside `DashboardTests`:

```python
def test_build_dashboard_timeseries_payload_includes_margin_usage_pct(self) -> None:
    from momentum_alpha.dashboard import build_dashboard_timeseries_payload

    payload = build_dashboard_timeseries_payload(
        {
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-19T00:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "800.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 1,
                    "open_order_count": 1,
                    "leader_symbol": "BTCUSDT",
                }
            ],
            "recent_account_flows": [],
            "account_metric_flows": [],
            "leader_history": [],
            "pulse_points": [],
        }
    )

    self.assertEqual(payload["account"][0]["margin_usage_pct"], 20.0)


def test_build_dashboard_timeseries_payload_uses_null_margin_usage_when_equity_is_zero(self) -> None:
    from momentum_alpha.dashboard import build_dashboard_timeseries_payload

    payload = build_dashboard_timeseries_payload(
        {
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-19T00:00:00+00:00",
                    "wallet_balance": "0.00",
                    "available_balance": "0.00",
                    "equity": "0.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                    "leader_symbol": None,
                }
            ],
            "recent_account_flows": [],
            "account_metric_flows": [],
            "leader_history": [],
            "pulse_points": [],
        }
    )

    self.assertIsNone(payload["account"][0]["margin_usage_pct"])
```

- [ ] **Step 2: Run the targeted timeseries tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_dashboard_timeseries_payload_includes_margin_usage_pct tests.test_dashboard.DashboardTests.test_build_dashboard_timeseries_payload_uses_null_margin_usage_when_equity_is_zero
```

Expected: FAIL because account timeseries points do not currently include `margin_usage_pct`.

- [ ] **Step 3: Implement a reusable margin-usage helper and extend account points**

In `src/momentum_alpha/dashboard.py`, add:

```python
def _compute_margin_usage_pct(*, available_balance: object | None, equity: object | None) -> float | None:
    available_value = _parse_numeric(available_balance)
    equity_value = _parse_numeric(equity)
    if available_value is None or equity_value in (None, 0):
        return None
    return (1 - (available_value / equity_value)) * 100
```

Then update `build_dashboard_timeseries_payload()` so each account point includes:

```python
margin_usage_pct = _compute_margin_usage_pct(
    available_balance=row.get("available_balance"),
    equity=row.get("equity"),
)
```

and stores it in the emitted point:

```python
"margin_usage_pct": margin_usage_pct,
```

- [ ] **Step 4: Extend account range stats to expose current, peak, and average margin usage**

Update `_compute_account_range_stats()` in `src/momentum_alpha/dashboard.py`:

```python
margin_points = [
    _parse_numeric(point.get("margin_usage_pct"))
    for point in points
]
margin_points = [value for value in margin_points if value is not None]
current_margin_usage = _parse_numeric(last.get("margin_usage_pct"))
peak_margin_usage = max(margin_points) if margin_points else None
avg_margin_usage = (sum(margin_points) / len(margin_points)) if margin_points else None
```

Add these keys to both the empty return branch and the populated return branch:

```python
"current_margin_usage_pct": current_margin_usage,
"peak_margin_usage_pct": peak_margin_usage,
"avg_margin_usage_pct": avg_margin_usage,
```

- [ ] **Step 5: Re-run the targeted tests**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_dashboard_timeseries_payload_includes_margin_usage_pct tests.test_dashboard.DashboardTests.test_build_dashboard_timeseries_payload_uses_null_margin_usage_when_equity_is_zero
```

Expected: PASS

- [ ] **Step 6: Commit the task**

Run:

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: add margin usage to account timeseries"
```

Expected: commit succeeds and records the new margin-usage account metric.

## Task 5: Wire Full-Range Round Trips And Aggregate Helpers Into Dashboard Data

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write failing tests for aggregate helpers and full-range trade loading**

Add these tests to `tests/test_dashboard.py`:

```python
def test_build_trade_leg_count_aggregates_groups_by_leg_count(self) -> None:
    from momentum_alpha.dashboard import build_trade_leg_count_aggregates

    rows = [
        {"net_pnl": "10", "payload": {"leg_count": 1, "peak_cumulative_risk": "10"}},
        {"net_pnl": "-5", "payload": {"leg_count": 2, "peak_cumulative_risk": "20"}},
        {"net_pnl": "8", "payload": {"leg_count": 2, "peak_cumulative_risk": "18"}},
    ]

    aggregates = build_trade_leg_count_aggregates(rows)

    self.assertEqual(aggregates[0]["label"], "1 legs")
    self.assertEqual(aggregates[0]["sample_count"], 1)
    self.assertEqual(aggregates[1]["label"], "2 legs")
    self.assertEqual(aggregates[1]["sample_count"], 2)
    self.assertAlmostEqual(aggregates[1]["avg_net_pnl"], 1.5)
    self.assertAlmostEqual(aggregates[1]["avg_peak_risk"], 19.0)


def test_build_trade_leg_index_aggregates_groups_by_leg_position(self) -> None:
    from momentum_alpha.dashboard import build_trade_leg_index_aggregates

    rows = [
        {
            "payload": {
                "legs": [
                    {"leg_index": 1, "leg_risk": "10", "net_pnl_contribution": "4"},
                    {"leg_index": 2, "leg_risk": "8", "net_pnl_contribution": "-1"},
                ]
            }
        },
        {
            "payload": {
                "legs": [
                    {"leg_index": 1, "leg_risk": "12", "net_pnl_contribution": "6"},
                    {"leg_index": 2, "leg_risk": "9", "net_pnl_contribution": "2"},
                ]
            }
        },
    ]

    aggregates = build_trade_leg_index_aggregates(rows)

    self.assertEqual(aggregates[0]["label"], "Leg 1")
    self.assertEqual(aggregates[0]["sample_count"], 2)
    self.assertAlmostEqual(aggregates[0]["avg_leg_risk"], 11.0)
    self.assertAlmostEqual(aggregates[0]["avg_net_contribution"], 5.0)
    self.assertAlmostEqual(aggregates[0]["profitable_ratio"], 1.0)
    self.assertEqual(aggregates[1]["label"], "Leg 2")
    self.assertAlmostEqual(aggregates[1]["profitable_ratio"], 0.5)
```

- [ ] **Step 2: Run the targeted aggregate tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_trade_leg_count_aggregates_groups_by_leg_count tests.test_dashboard.DashboardTests.test_build_trade_leg_index_aggregates_groups_by_leg_position
```

Expected: FAIL because the aggregate helpers do not exist yet.

- [ ] **Step 3: Implement aggregate helpers in `src/momentum_alpha/dashboard.py`**

Add these helpers near the other dashboard data-shaping functions:

```python
def build_trade_leg_count_aggregates(round_trips: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for trip in round_trips:
        leg_count = int((trip.get("payload") or {}).get("leg_count") or 0)
        if leg_count <= 0:
            continue
        grouped.setdefault(leg_count, []).append(trip)
    rows: list[dict] = []
    for leg_count in sorted(grouped):
        trips = grouped[leg_count]
        net_values = [_parse_numeric(trip.get("net_pnl")) for trip in trips]
        net_values = [value for value in net_values if value is not None]
        peak_values = [_parse_numeric((trip.get("payload") or {}).get("peak_cumulative_risk")) for trip in trips]
        peak_values = [value for value in peak_values if value is not None]
        win_count = len([value for value in net_values if value > 0])
        rows.append(
            {
                "label": f"{leg_count} legs",
                "leg_count": leg_count,
                "sample_count": len(trips),
                "win_rate": (win_count / len(net_values)) if net_values else None,
                "avg_net_pnl": (sum(net_values) / len(net_values)) if net_values else None,
                "avg_peak_risk": (sum(peak_values) / len(peak_values)) if peak_values else None,
            }
        )
    return rows


def build_trade_leg_index_aggregates(round_trips: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for trip in round_trips:
        for leg in (trip.get("payload") or {}).get("legs") or []:
            leg_index = int(leg.get("leg_index") or 0)
            if leg_index <= 0:
                continue
            grouped.setdefault(leg_index, []).append(leg)
    rows: list[dict] = []
    for leg_index in sorted(grouped):
        legs = grouped[leg_index]
        risk_values = [_parse_numeric(leg.get("leg_risk")) for leg in legs]
        risk_values = [value for value in risk_values if value is not None]
        net_values = [_parse_numeric(leg.get("net_pnl_contribution")) for leg in legs]
        net_values = [value for value in net_values if value is not None]
        profitable_count = len([value for value in net_values if value > 0])
        rows.append(
            {
                "label": f"Leg {leg_index}",
                "leg_index": leg_index,
                "sample_count": len(legs),
                "avg_leg_risk": (sum(risk_values) / len(risk_values)) if risk_values else None,
                "avg_net_contribution": (sum(net_values) / len(net_values)) if net_values else None,
                "profitable_ratio": (profitable_count / len(net_values)) if net_values else None,
            }
        )
    return rows
```

- [ ] **Step 4: Load full-range closed trades into the snapshot and summary path**

Update the import list at the top of `src/momentum_alpha/dashboard.py`:

```python
from .runtime_store import (
    RuntimeStateStore,
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_recent_account_flows,
    fetch_recent_audit_events,
    fetch_recent_algo_orders,
    fetch_recent_broker_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_trade_round_trips_for_range,
)
```

Then update `load_dashboard_snapshot()` so round trips come from the new range-aware helper:

```python
recent_trade_round_trips = fetch_trade_round_trips_for_range(
    path=runtime_db_file,
    now=now,
    range_key=account_range_key,
)
```

- [ ] **Step 5: Re-run the targeted aggregate tests**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_trade_leg_count_aggregates_groups_by_leg_count tests.test_dashboard.DashboardTests.test_build_trade_leg_index_aggregates_groups_by_leg_position
```

Expected: PASS

- [ ] **Step 6: Commit the task**

Run:

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: add dashboard trade leg aggregate helpers"
```

Expected: commit succeeds and records the data-shaping layer for new performance analytics.

## Task 6: Render Margin Usage Controls And Performance Leg Detail In The Dashboard

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing rendering tests**

Add these tests to `tests/test_dashboard.py`:

```python
def test_render_dashboard_html_includes_margin_usage_account_controls(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(self._build_tabbed_snapshot(), active_tab="performance")

    self.assertIn('data-account-metric="margin_usage_pct"', html)
    self.assertIn("CURRENT MARGIN USAGE", html)
    self.assertIn("PEAK MARGIN USAGE", html)
    self.assertIn("AVERAGE MARGIN USAGE", html)


def test_render_closed_trades_table_renders_leg_columns_and_detail_rows(self) -> None:
    from momentum_alpha.dashboard import render_closed_trades_table

    html = render_closed_trades_table(
        [
            {
                "round_trip_id": "BTCUSDT:1",
                "symbol": "BTCUSDT",
                "opened_at": "2026-04-19T00:00:00+00:00",
                "closed_at": "2026-04-19T00:20:00+00:00",
                "net_pnl": "37.0",
                "exit_reason": "sell",
                "duration_seconds": 1200,
                "payload": {
                    "leg_count": 2,
                    "peak_cumulative_risk": "20",
                    "legs": [
                        {
                            "leg_index": 1,
                            "leg_type": "base",
                            "opened_at": "2026-04-19T00:00:00+00:00",
                            "quantity": "1",
                            "entry_price": "110",
                            "stop_price_at_entry": "100",
                            "leg_risk": "10",
                            "cumulative_risk_after_leg": "10",
                            "gross_pnl_contribution": "20",
                            "fee_share": "0.47",
                            "net_pnl_contribution": "19.53",
                        }
                    ],
                },
            }
        ]
    )

    self.assertIn("LEGS", html)
    self.assertIn("PEAK RISK", html)
    self.assertIn("Leg #", html)
    self.assertIn("Net Contribution", html)
    self.assertIn("BTCUSDT:1", html)


def test_render_dashboard_html_performance_tab_shows_leg_aggregate_sections(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["recent_trade_round_trips"] = [
        {
            "round_trip_id": "BTCUSDT:1",
            "symbol": "BTCUSDT",
            "opened_at": "2026-04-19T00:00:00+00:00",
            "closed_at": "2026-04-19T00:20:00+00:00",
            "net_pnl": "37.0",
            "commission": "2.0",
            "duration_seconds": 1200,
            "exit_reason": "sell",
            "payload": {
                "leg_count": 2,
                "peak_cumulative_risk": "20",
                "legs": [
                    {"leg_index": 1, "leg_risk": "10", "net_pnl_contribution": "19.5"},
                    {"leg_index": 2, "leg_risk": "10", "net_pnl_contribution": "17.5"},
                ],
            },
        }
    ]

    html = render_dashboard_html(snapshot, active_tab="performance")

    self.assertIn("COMPLETE TRADE HISTORY", html)
    self.assertIn("BY LEG COUNT", html)
    self.assertIn("BY LEG INDEX", html)
    self.assertIn("Leg 1", html)
```

- [ ] **Step 2: Run the targeted rendering tests and confirm failure**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_includes_margin_usage_account_controls tests.test_dashboard.DashboardTests.test_render_closed_trades_table_renders_leg_columns_and_detail_rows tests.test_dashboard.DashboardTests.test_render_dashboard_html_performance_tab_shows_leg_aggregate_sections
```

Expected: FAIL because the account panel lacks the new controls and the performance renderer only shows the old round-trip table.

- [ ] **Step 3: Extend the account metrics panel and client-side chart toggle**

In `src/momentum_alpha/dashboard.py`, update `_build_account_metrics_panel()` so the overview grid includes the new cards:

```python
"<div class='account-overview-card'><div class='account-overview-label'>CURRENT MARGIN USAGE</div>"
f"<div class='account-overview-value' data-account-value='current_margin_usage_pct'>{escape(_format_metric(stats['current_margin_usage_pct']))}%</div>"
"<div class='account-overview-sub'>Latest visible occupancy</div></div>"
"<div class='account-overview-card'><div class='account-overview-label'>PEAK MARGIN USAGE</div>"
f"<div class='account-overview-value' data-account-value='peak_margin_usage_pct'>{escape(_format_metric(stats['peak_margin_usage_pct']))}%</div>"
"<div class='account-overview-sub'>Highest visible occupancy</div></div>"
"<div class='account-overview-card'><div class='account-overview-label'>AVERAGE MARGIN USAGE</div>"
f"<div class='account-overview-value' data-account-value='avg_margin_usage_pct'>{escape(_format_metric(stats['avg_margin_usage_pct']))}%</div>"
"<div class='account-overview-sub'>Mean visible occupancy</div></div>"
```

Also extend the metric switch strip:

```python
"<button type='button' class='account-chip' data-account-metric=\"margin_usage_pct\">Margin Usage %</button>"
```

Then update the client-side account chart JS palette and value maps:

```javascript
const palette = {
  equity: '#4cc9f0',
  adjusted_equity: '#ffbc42',
  wallet_balance: '#36d98a',
  unrealized_pnl: '#a855f7',
  margin_usage_pct: '#ff5d73',
};
```

and:

```javascript
margin_usage_pct: point.margin_usage_pct,
```

plus the overview values map:

```javascript
current_margin_usage_pct: formatAccountValue(last.margin_usage_pct, false, '%'),
peak_margin_usage_pct: formatAccountValue(
  numericValues.map((point) => point.margin_usage_pct).filter((value) => value !== null && value !== undefined && !Number.isNaN(value)).length
    ? Math.max(...numericValues.map((point) => point.margin_usage_pct).filter((value) => value !== null && value !== undefined && !Number.isNaN(value)))
    : null,
  false,
  '%'
),
avg_margin_usage_pct: formatAccountValue(
  (() => {
    const visibleMargins = numericValues.map((point) => point.margin_usage_pct).filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
    return visibleMargins.length ? visibleMargins.reduce((sum, value) => sum + value, 0) / visibleMargins.length : null;
  })(),
  false,
  '%'
),
```

- [ ] **Step 4: Extend `render_closed_trades_table()` and `render_dashboard_performance_tab()`**

Replace the current `render_closed_trades_table()` implementation in `src/momentum_alpha/dashboard.py` with a detail-aware version:

```python
def render_closed_trades_table(round_trips: list[dict]) -> str:
    if not round_trips:
        return "<div class='trade-history-empty'>No closed trades</div>"

    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>SYMBOL</span>"
        "<span>OPEN</span>"
        "<span>CLOSE</span>"
        "<span>LEGS</span>"
        "<span>PEAK RISK</span>"
        "<span>EXIT</span>"
        "<span>PNL</span>"
        "<span>DURATION</span>"
        "</div>"
    )
    rows = ""
    for trip in round_trips[:20]:
        payload = trip.get("payload") or {}
        legs = payload.get("legs") or []
        detail_header = (
            "<div class='trade-leg-row trade-leg-row-header'>"
            "<span>Leg #</span><span>Type</span><span>Opened At</span><span>Qty</span><span>Entry</span>"
            "<span>Stop At Entry</span><span>Leg Risk</span><span>Cum Risk</span><span>Gross PnL</span>"
            "<span>Fee Share</span><span>Net Contribution</span>"
            "</div>"
        )
        detail_rows = "".join(
            f"<div class='trade-leg-row'>"
            f"<span>{escape(str(leg.get('leg_index') or '-'))}</span>"
            f"<span>{escape(str(leg.get('leg_type') or '-'))}</span>"
            f"<span>{escape(_format_time_only(leg.get('opened_at')))}</span>"
            f"<span>{escape(_format_quantity(leg.get('quantity')))}</span>"
            f"<span>{escape(_format_price(leg.get('entry_price')))}</span>"
            f"<span>{escape(_format_price(leg.get('stop_price_at_entry')))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('leg_risk'))))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('cumulative_risk_after_leg'))))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('gross_pnl_contribution')), signed=True))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('fee_share'))))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('net_pnl_contribution')), signed=True))}</span>"
            f"</div>"
            for leg in legs
        ) or "<div class='trade-leg-empty'>No leg detail</div>"
        rows += (
            f"<details class='trade-round-trip-details'>"
            f"<summary class='analytics-row'>"
            f"<span class='analytics-main'><b>{escape(str(trip.get('symbol') or '-'))}</b> · {escape(str(trip.get('round_trip_id') or '-'))}</span>"
            f"<span>{escape(_format_time_only(trip.get('opened_at')))}</span>"
            f"<span>{escape(_format_time_only(trip.get('closed_at')))}</span>"
            f"<span>{escape(str(payload.get('leg_count') or 0))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(payload.get('peak_cumulative_risk'))))}</span>"
            f"<span>{escape(str(trip.get('exit_reason') or '-'))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(trip.get('net_pnl')), signed=True))}</span>"
            f"<span>{escape(_format_duration_seconds(_parse_numeric(trip.get('duration_seconds'))))}</span>"
            f"</summary>"
            f"<div class='trade-leg-detail'>{detail_header}{detail_rows}</div>"
            f"</details>"
        )
    return f"<div class='analytics-table desktop-only'>{header}{rows}</div>"
```

Then add two small render helpers:

```python
def render_trade_leg_count_aggregate_table(rows: list[dict]) -> str:
    if not rows:
        return "<div class='trade-history-empty'>No leg-count aggregates</div>"
    return (
        "<div class='analytics-table desktop-only'>"
        "<div class='analytics-row analytics-row-header'><span class='analytics-main'>GROUP</span><span>SAMPLES</span><span>WIN RATE</span><span>AVG PNL</span><span>AVG PEAK RISK</span></div>"
        + "".join(
            f"<div class='analytics-row'><span class='analytics-main'>{escape(row['label'])}</span><span>{row['sample_count']}</span><span>{escape(_format_pct_value((row.get('win_rate') or 0) * 100 if row.get('win_rate') is not None else None))}</span><span>{escape(_format_metric(row.get('avg_net_pnl'), signed=True))}</span><span>{escape(_format_metric(row.get('avg_peak_risk')))}</span></div>"
            for row in rows
        )
        + "</div>"
    )


def render_trade_leg_index_aggregate_table(rows: list[dict]) -> str:
    if not rows:
        return "<div class='trade-history-empty'>No leg-index aggregates</div>"
    return (
        "<div class='analytics-table desktop-only'>"
        "<div class='analytics-row analytics-row-header'><span class='analytics-main'>LEG</span><span>SAMPLES</span><span>AVG RISK</span><span>AVG NET</span><span>PROFITABLE</span></div>"
        + "".join(
            f"<div class='analytics-row'><span class='analytics-main'>{escape(row['label'])}</span><span>{row['sample_count']}</span><span>{escape(_format_metric(row.get('avg_leg_risk')))}</span><span>{escape(_format_metric(row.get('avg_net_contribution'), signed=True))}</span><span>{escape(_format_pct_value((row.get('profitable_ratio') or 0) * 100 if row.get('profitable_ratio') is not None else None))}</span></div>"
            for row in rows
        )
        + "</div>"
    )
```

Finally, update `render_dashboard_performance_tab()` to accept:

```python
def render_dashboard_performance_tab(
    *,
    closed_trades_html: str,
    performance_summary_html: str,
    account_metrics_panel_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
) -> str:
```

and render the new sections:

```python
"<div class='chart-card'>"
"<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>COMPLETE TRADE HISTORY</div>"
f"<div class='table-scroll'>{closed_trades_html}</div>"
"</div>"
"<div class='chart-card'>"
"<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>BY LEG COUNT</div>"
f"{leg_count_aggregate_html}"
"</div>"
"<div class='chart-card'>"
"<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>BY LEG INDEX</div>"
f"{leg_index_aggregate_html}"
"</div>"
```

Also update `render_dashboard_html()` to call:

```python
leg_count_aggregates = build_trade_leg_count_aggregates(snapshot.get("recent_trade_round_trips") or [])
leg_index_aggregates = build_trade_leg_index_aggregates(snapshot.get("recent_trade_round_trips") or [])
leg_count_aggregate_html = render_trade_leg_count_aggregate_table(leg_count_aggregates)
leg_index_aggregate_html = render_trade_leg_index_aggregate_table(leg_index_aggregates)
```

and pass both aggregate HTML fragments into `render_dashboard_performance_tab(...)`.

- [ ] **Step 5: Re-run the targeted rendering tests**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_includes_margin_usage_account_controls tests.test_dashboard.DashboardTests.test_render_closed_trades_table_renders_leg_columns_and_detail_rows tests.test_dashboard.DashboardTests.test_render_dashboard_html_performance_tab_shows_leg_aggregate_sections
```

Expected: PASS

- [ ] **Step 6: Run the focused regression slice**

Run:

```bash
python3 -m unittest tests.test_runtime_store tests.test_dashboard
```

Expected: PASS

- [ ] **Step 7: Commit the task**

Run:

```bash
git add tests/test_runtime_store.py tests/test_dashboard.py src/momentum_alpha/runtime_store.py src/momentum_alpha/dashboard.py
git commit -m "feat: add dashboard margin and trade leg analytics"
```

Expected: commit succeeds and records the end-to-end dashboard analytics delivery.
