# Trader Dashboard Upgrade Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Rework the dashboard into a trader-first control panel with account/risk summaries, execution-quality aggregates, performance analytics, richer position diagnostics, and lower-priority system operations.

**Architecture:** Keep the work centered in `src/momentum_alpha/dashboard.py` and extend the existing snapshot, summary, timeseries, and HTML render flow rather than introducing a new module or schema. Add pure aggregation helpers first, then use those helpers in HTML rendering so most new behavior is testable without spinning up the HTTP server.

**Tech Stack:** Python 3, `unittest`, existing SQLite-backed runtime store, server-rendered HTML/CSS/JS in `dashboard.py`

---

### Task 1: Add Trader-Facing Aggregation Helpers

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests for account, execution, performance, and signal aggregates**

```python
def test_build_trader_summary_metrics_computes_account_risk_and_execution_stats(self) -> None:
    from momentum_alpha.dashboard import build_trader_summary_metrics

    metrics = build_trader_summary_metrics(
        snapshot={
            "recent_account_snapshots": [
                {
                    "timestamp": "2026-04-16T00:00:00+00:00",
                    "wallet_balance": "1000.00",
                    "available_balance": "900.00",
                    "equity": "1000.00",
                    "unrealized_pnl": "0.00",
                    "position_count": 0,
                    "open_order_count": 0,
                    "leader_symbol": "AAAUSDT",
                },
                {
                    "timestamp": "2026-04-16T01:00:00+00:00",
                    "wallet_balance": "1030.00",
                    "available_balance": "780.00",
                    "equity": "1080.00",
                    "unrealized_pnl": "30.00",
                    "position_count": 2,
                    "open_order_count": 1,
                    "leader_symbol": "BBBUSDT",
                },
            ],
            "recent_trade_round_trips": [
                {"closed_at": "2026-04-16T00:20:00+00:00", "net_pnl": "40.00", "duration_seconds": 600},
                {"closed_at": "2026-04-16T00:40:00+00:00", "net_pnl": "-10.00", "duration_seconds": 300},
                {"closed_at": "2026-04-16T00:50:00+00:00", "net_pnl": "20.00", "duration_seconds": 900},
            ],
            "recent_stop_exit_summaries": [
                {"timestamp": "2026-04-16T00:35:00+00:00", "slippage_pct": "1.50", "commission": "0.50"},
                {"timestamp": "2026-04-16T00:45:00+00:00", "slippage_pct": "2.50", "commission": "0.75"},
            ],
            "recent_signal_decisions": [
                {"timestamp": "2026-04-16T00:10:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                {"timestamp": "2026-04-16T00:30:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                {"timestamp": "2026-04-16T00:55:00+00:00", "payload": {"blocked_reason": "invalid_stop_price"}},
            ],
            "leader_history": [
                {"timestamp": "2026-04-16T00:00:00+00:00", "symbol": "AAAUSDT"},
                {"timestamp": "2026-04-16T00:15:00+00:00", "symbol": "BBBUSDT"},
                {"timestamp": "2026-04-16T00:40:00+00:00", "symbol": "CCCUSDT"},
            ],
        },
        position_details=[
            {"symbol": "AAAUSDT", "risk": "50.00"},
            {"symbol": "BBBUSDT", "risk": "25.00"},
        ],
        range_key="24H",
    )

    self.assertEqual(metrics["account"]["today_net_pnl"], 80.0)
    self.assertEqual(metrics["account"]["margin_usage_pct"], 27.77777777777778)
    self.assertEqual(metrics["account"]["open_risk"], 75.0)
    self.assertEqual(metrics["account"]["open_risk_pct"], 6.944444444444445)
    self.assertEqual(metrics["performance"]["win_rate"], 2 / 3)
    self.assertEqual(metrics["performance"]["profit_factor"], 6.0)
    self.assertEqual(metrics["performance"]["current_streak"]["label"], "W2")
    self.assertEqual(metrics["execution"]["avg_slippage_pct"], 2.0)
    self.assertEqual(metrics["execution"]["max_slippage_pct"], 2.5)
    self.assertEqual(metrics["signals"]["blocked_reason_counts"]["risk_limit"], 2)
    self.assertEqual(metrics["signals"]["rotation_count"], 2)

def test_build_trader_summary_metrics_returns_none_or_empty_values_when_data_missing(self) -> None:
    from momentum_alpha.dashboard import build_trader_summary_metrics

    metrics = build_trader_summary_metrics(
        snapshot={
            "recent_account_snapshots": [],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_signal_decisions": [],
            "leader_history": [],
        },
        position_details=[],
        range_key="24H",
    )

    self.assertIsNone(metrics["account"]["today_net_pnl"])
    self.assertIsNone(metrics["account"]["margin_usage_pct"])
    self.assertEqual(metrics["signals"]["blocked_reason_counts"], {})
    self.assertEqual(metrics["signals"]["rotation_count"], 0)
```

- [ ] **Step 2: Run the targeted tests to verify the new tests fail for the expected reason**

Run: `python -m pytest tests/test_dashboard.py -k trader_summary_metrics -v`

Expected: `FAIL` with an import or attribute error because `build_trader_summary_metrics` does not exist yet.

- [ ] **Step 3: Write the minimal aggregation helpers in `src/momentum_alpha/dashboard.py`**

```python
def _filter_rows_for_range(rows: list[dict], *, timestamp_key: str, range_key: str) -> list[dict]:
    if range_key == "ALL":
        return list(rows)
    hours = {"1H": 1, "6H": 6, "24H": 24}.get(range_key)
    if not hours or not rows:
        return list(rows)
    parsed_rows = [row for row in rows if row.get(timestamp_key)]
    if not parsed_rows:
        return []
    end_at = max(datetime.fromisoformat(row[timestamp_key]) for row in parsed_rows)
    start_at = end_at - timedelta(hours=hours)
    return [
        row
        for row in parsed_rows
        if datetime.fromisoformat(row[timestamp_key]) >= start_at
    ]


def build_trader_summary_metrics(snapshot: dict, *, position_details: list[dict], range_key: str = "24H") -> dict:
    account_rows = sorted(snapshot.get("recent_account_snapshots", []), key=lambda item: item.get("timestamp") or "")
    scoped_accounts = _filter_rows_for_range(account_rows, timestamp_key="timestamp", range_key=range_key)
    scoped_round_trips = _filter_rows_for_range(
        sorted(snapshot.get("recent_trade_round_trips", []), key=lambda item: item.get("closed_at") or ""),
        timestamp_key="closed_at",
        range_key=range_key,
    )
    scoped_stop_exits = _filter_rows_for_range(
        sorted(snapshot.get("recent_stop_exit_summaries", []), key=lambda item: item.get("timestamp") or ""),
        timestamp_key="timestamp",
        range_key=range_key,
    )
    scoped_signal_decisions = _filter_rows_for_range(
        sorted(snapshot.get("recent_signal_decisions", []), key=lambda item: item.get("timestamp") or ""),
        timestamp_key="timestamp",
        range_key=range_key,
    )
    scoped_leader_history = _filter_rows_for_range(
        sorted(snapshot.get("leader_history", []), key=lambda item: item.get("timestamp") or ""),
        timestamp_key="timestamp",
        range_key=range_key,
    )
    # compute account, execution, performance, and signals summaries here
```

- [ ] **Step 4: Run the targeted tests to verify the new helper passes**

Run: `python -m pytest tests/test_dashboard.py -k trader_summary_metrics -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: add trader dashboard summary metrics"
```

### Task 2: Expand Position Diagnostics For Risk-First Rendering

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests for richer position diagnostics and ordering**

```python
def test_build_position_details_includes_risk_pct_leg_count_and_opened_time(self) -> None:
    from momentum_alpha.dashboard import build_position_details

    details = build_position_details(
        {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "legs": [
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.01",
                                "entry_price": "82000",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T09:15:00+00:00",
                                "leg_type": "base",
                            },
                            {
                                "symbol": "BTCUSDT",
                                "quantity": "0.005",
                                "entry_price": "82500",
                                "stop_price": "81000",
                                "opened_at": "2026-04-15T10:00:00+00:00",
                                "leg_type": "add_on",
                            },
                        ],
                    }
                }
            }
        },
        equity_value=350.0,
    )

    self.assertEqual(details[0]["leg_count"], 2)
    self.assertEqual(details[0]["opened_at"], "2026-04-15T09:15:00+00:00")
    self.assertAlmostEqual(details[0]["risk_pct_of_equity"], 5.0, places=2)
    self.assertEqual(details[0]["mtm_pnl"], None)
    self.assertEqual(details[0]["distance_to_stop_pct"], None)

def test_render_position_cards_orders_by_highest_risk_and_renders_na_fields(self) -> None:
    from momentum_alpha.dashboard import render_position_cards

    html = render_position_cards(
        [
            {
                "symbol": "LOWUSDT",
                "direction": "LONG",
                "total_quantity": "1",
                "entry_price": "10.00",
                "stop_price": "9.00",
                "risk": "1.00",
                "risk_pct_of_equity": 0.5,
                "leg_count": 1,
                "opened_at": "2026-04-15T09:00:00+00:00",
                "mtm_pnl": None,
                "distance_to_stop_pct": None,
                "legs": [],
            },
            {
                "symbol": "HIGHUSDT",
                "direction": "LONG",
                "total_quantity": "5",
                "entry_price": "20.00",
                "stop_price": "18.00",
                "risk": "10.00",
                "risk_pct_of_equity": 5.0,
                "leg_count": 2,
                "opened_at": "2026-04-15T08:00:00+00:00",
                "mtm_pnl": None,
                "distance_to_stop_pct": None,
                "legs": [],
            },
        ]
    )

    self.assertLess(html.index("HIGHUSDT"), html.index("LOWUSDT"))
    self.assertIn("Risk %", html)
    self.assertIn("Legs", html)
    self.assertIn("Opened", html)
    self.assertIn("MTM", html)
    self.assertIn("n/a", html)
```

- [ ] **Step 2: Run the targeted tests to verify the new tests fail**

Run: `python -m pytest tests/test_dashboard.py -k "risk_pct_leg_count or na_fields" -v`

Expected: `FAIL` because `build_position_details` and `render_position_cards` do not yet emit the new fields.

- [ ] **Step 3: Implement the minimal position-detail expansion and risk-first ordering**

```python
def build_position_details(position_snapshot: dict, equity_value: float | None = None) -> list[dict]:
    ...
    details.append(
        {
            "symbol": symbol,
            "direction": "LONG",
            "total_quantity": str(total_quantity),
            "entry_price": f"{avg_entry:.2f}",
            "stop_price": str(stop_price),
            "risk": f"{risk:.2f}",
            "risk_pct_of_equity": None if not equity_value else float((risk / Decimal(str(equity_value))) * Decimal("100")),
            "leg_count": len(legs),
            "opened_at": min((leg.get("opened_at") or "" for leg in legs), default=""),
            "mtm_pnl": None,
            "distance_to_stop_pct": None,
            "legs": leg_info,
        }
    )
    return sorted(details, key=lambda item: (-float(item.get("risk") or 0), str(item.get("symbol") or "")))


def render_position_cards(positions: list[dict]) -> str:
    ordered_positions = sorted(positions, key=lambda item: (-float(item.get("risk") or 0), str(item.get("symbol") or "")))
    ...
```

- [ ] **Step 4: Run the targeted tests to verify the new position behavior passes**

Run: `python -m pytest tests/test_dashboard.py -k "risk_pct_leg_count or na_fields" -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: expand dashboard position diagnostics"
```

### Task 3: Rebuild The Dashboard Layout Around Trader Priorities

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing HTML-render tests for the new information hierarchy**

```python
def test_render_dashboard_html_reorders_sections_for_trader_first_layout(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(
        {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "PLAYUSDT",
                "position_count": 1,
                "order_status_count": 1,
                "latest_position_snapshot": {"payload": {}},
                "latest_account_snapshot": {
                    "wallet_balance": "1000.00",
                    "available_balance": "800.00",
                    "equity": "1050.00",
                    "unrealized_pnl": "50.00",
                    "position_count": 1,
                    "open_order_count": 1,
                },
                "latest_signal_decision": {"decision_type": "base_entry", "symbol": "PLAYUSDT", "timestamp": "2026-04-16T01:00:00+00:00"},
            },
            "recent_account_snapshots": [],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_trade_fills": [],
            "recent_signal_decisions": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        },
        strategy_config={"stop_budget_usdt": "10", "entry_window": "01:00-23:00 UTC", "testnet": False, "submit_orders": True},
    )

    self.assertIn("TODAY NET PNL", html)
    self.assertIn("AVAILABLE BALANCE", html)
    self.assertIn("MARGIN USAGE", html)
    self.assertIn("OPEN RISK / EQUITY", html)
    self.assertIn("POSITION DIAGNOSTICS", html)
    self.assertIn("EXECUTION QUALITY", html)
    self.assertIn("STRATEGY PERFORMANCE", html)
    self.assertIn("SIGNAL & ROTATION", html)
    self.assertIn("SYSTEM OPERATIONS", html)
    self.assertLess(html.index("TODAY NET PNL"), html.index("SYSTEM OPERATIONS"))

def test_render_dashboard_html_shows_unavailable_market_dependent_metrics_as_na(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(
        {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BTCUSDT",
                "position_count": 1,
                "order_status_count": 0,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {
                            "BTCUSDT": {
                                "symbol": "BTCUSDT",
                                "stop_price": "81000",
                                "legs": [
                                    {
                                        "symbol": "BTCUSDT",
                                        "quantity": "0.01",
                                        "entry_price": "82000",
                                        "stop_price": "81000",
                                        "opened_at": "2026-04-15T09:15:00+00:00",
                                        "leg_type": "base",
                                    }
                                ],
                            }
                        }
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "available_balance": "900", "equity": "1000", "unrealized_pnl": "0"},
                "latest_signal_decision": {},
            },
            "recent_account_snapshots": [],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_trade_fills": [],
            "recent_signal_decisions": [],
            "recent_events": [],
            "event_counts": {},
            "source_counts": {},
            "leader_history": [],
            "pulse_points": [],
            "warnings": [],
        }
    )

    self.assertIn("Current Price", html)
    self.assertIn("Distance To Stop", html)
    self.assertIn("waiting for live price data", html)
```

- [ ] **Step 2: Run the targeted HTML tests to verify they fail**

Run: `python -m pytest tests/test_dashboard.py -k "trader_first_layout or unavailable_market_dependent_metrics" -v`

Expected: `FAIL` because `render_dashboard_html` still renders the old section ordering and labels.

- [ ] **Step 3: Implement the new HTML structure and wire the new metrics into rendering**

```python
trader_metrics = build_trader_summary_metrics(snapshot, position_details=position_details, range_key="24H")

top_summary_html = (
    "<div class='trader-top-grid'>"
    f"{render_summary_metric_card('TODAY NET PNL', trader_metrics['account']['today_net_pnl'], signed=True)}"
    f"{render_summary_metric_card('EQUITY', trader_metrics['account']['equity'])}"
    f"{render_summary_metric_card('AVAILABLE BALANCE', trader_metrics['account']['available_balance'])}"
    f"{render_summary_metric_card('MARGIN USAGE', trader_metrics['account']['margin_usage_pct'], suffix='%')}"
    f"{render_summary_metric_card('OPEN RISK / EQUITY', trader_metrics['account']['open_risk_pct'], suffix='%')}"
    f"{render_summary_metric_card('CURRENT DRAWDOWN', trader_metrics['account']['drawdown_abs'], signed=True)}"
    "</div>"
)

return f\"\"\"<!doctype html>
...
<section class="dashboard-section">
  <div class="section-header">POSITION DIAGNOSTICS</div>
  {position_cards_html}
</section>
<section class="dashboard-section">
  <div class="section-header">EXECUTION QUALITY</div>
  {execution_summary_html}
</section>
<section class="dashboard-section">
  <div class="section-header">STRATEGY PERFORMANCE</div>
  {performance_summary_html}
</section>
<section class="dashboard-section">
  <div class="section-header">SIGNAL &amp; ROTATION</div>
  {signal_context_html}
</section>
<section class="dashboard-section bottom-row">
  <div class="section-header">SYSTEM OPERATIONS</div>
  ...
</section>
\"\"\"
```

- [ ] **Step 4: Run the targeted HTML tests to verify the new layout passes**

Run: `python -m pytest tests/test_dashboard.py -k "trader_first_layout or unavailable_market_dependent_metrics" -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: redesign dashboard for trader-first layout"
```

### Task 4: Verify Snapshot/API Compatibility And Full Dashboard Regression Coverage

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing regression test for summary/timeseries/tables compatibility**

```python
def test_dashboard_api_helpers_preserve_existing_payloads_while_exposing_trader_metrics(self) -> None:
    from momentum_alpha.dashboard import (
        build_dashboard_summary_payload,
        build_dashboard_tables_payload,
        build_dashboard_timeseries_payload,
        build_trader_summary_metrics,
    )

    snapshot = {
        "health": {"overall_status": "OK", "items": []},
        "runtime": {
            "previous_leader_symbol": "PLAYUSDT",
            "position_count": 1,
            "order_status_count": 2,
            "latest_account_snapshot": {
                "wallet_balance": "1234.56",
                "available_balance": "1200.00",
                "equity": "1260.12",
                "unrealized_pnl": "25.56",
                "position_count": 1,
                "open_order_count": 2,
            },
        },
        "recent_account_snapshots": [
            {"timestamp": "2026-04-15T08:48:00+00:00", "wallet_balance": "1230.00", "available_balance": "1190.00", "equity": "1250.00", "unrealized_pnl": "20.00", "position_count": 1, "open_order_count": 1, "leader_symbol": "ONUSDT"},
            {"timestamp": "2026-04-15T08:49:00+00:00", "wallet_balance": "1234.56", "available_balance": "1200.00", "equity": "1260.12", "unrealized_pnl": "25.56", "position_count": 1, "open_order_count": 2, "leader_symbol": "PLAYUSDT"},
        ],
        "recent_trade_round_trips": [{"closed_at": "2026-04-15T08:49:00+00:00", "net_pnl": "10.00", "duration_seconds": 60}],
        "recent_stop_exit_summaries": [{"timestamp": "2026-04-15T08:49:00+00:00", "slippage_pct": "1.25", "commission": "0.10"}],
        "recent_signal_decisions": [{"timestamp": "2026-04-15T08:49:00+00:00", "payload": {"blocked_reason": "risk_limit"}}],
        "leader_history": [{"timestamp": "2026-04-15T08:49:00+00:00", "symbol": "PLAYUSDT"}],
        "pulse_points": [],
        "event_counts": {},
        "source_counts": {},
        "recent_events": [],
        "warnings": [],
    }

    summary = build_dashboard_summary_payload(snapshot)
    timeseries = build_dashboard_timeseries_payload(snapshot)
    tables = build_dashboard_tables_payload(snapshot)
    trader = build_trader_summary_metrics(snapshot, position_details=[{"risk": "25.00"}], range_key="24H")

    self.assertEqual(summary["account"]["equity"], 1260.12)
    self.assertEqual(timeseries["account"][1]["leader_symbol"], "PLAYUSDT")
    self.assertEqual(tables["recent_trade_round_trips"][0]["net_pnl"], "10.00")
    self.assertEqual(trader["execution"]["avg_slippage_pct"], 1.25)
```

- [ ] **Step 2: Run the regression test to verify it fails only if compatibility broke or helper is missing**

Run: `python -m pytest tests/test_dashboard.py -k "payloads_while_exposing_trader_metrics" -v`

Expected: `FAIL` until the final compatibility adjustments are complete.

- [ ] **Step 3: Make any final compatibility adjustments and run the full dashboard test file**

```python
# keep existing API helper behavior intact
summary = build_dashboard_summary_payload(snapshot)
timeseries = build_dashboard_timeseries_payload(snapshot)
tables = build_dashboard_tables_payload(snapshot)

# ensure new rendering uses trader helpers without mutating source payload shapes
trader_metrics = build_trader_summary_metrics(snapshot, position_details=position_details, range_key="24H")
```

Run: `python -m pytest tests/test_dashboard.py -v`

Expected: `PASS`

- [ ] **Step 4: Run the broader targeted regression set covering dashboard-adjacent modules**

Run: `python -m pytest tests/test_main.py tests/test_runtime_store.py tests/test_health.py -v`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "test: verify trader dashboard upgrade compatibility"
```

## Self-Review

- Spec coverage: This plan covers the top summary strip, position diagnostics, execution quality, strategy performance, signal and rotation context, system operations demotion, and explicit `n/a` handling for unsupported live-price metrics.
- Placeholder scan: All tasks name concrete files, commands, tests, and implementation targets. No `TODO`/`TBD` placeholders remain.
- Type consistency: The plan consistently uses `build_trader_summary_metrics`, `build_position_details(..., equity_value=...)`, and `render_position_cards` as the primary new interfaces.
