# Dashboard Frontend Issues Remediation Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Close the live position-diagnostics gap, remove misleading fallback values, and improve the trader dashboard’s readability, risk signaling, and execution/rotation context.

**Architecture:** Extend the existing position snapshot payload with live market context from the runtime, then consume that persisted data inside the dashboard renderer to compute live position diagnostics and strengthen the current dashboard sections in place. Keep the existing single-page structure, but tighten rendering semantics, formatting, and state handling so the dashboard behaves like a reliable trading console instead of a generic runtime monitor.

**Tech Stack:** Python, unittest, existing dashboard HTML/CSS/JS renderer, runtime snapshot persistence in SQLite-backed runtime store

---

## File Map

- Modify: `src/momentum_alpha/main.py`
  - Responsibility: persist live market context into latest position snapshots.
- Modify: `src/momentum_alpha/dashboard.py`
  - Responsibility: compute and render trader-facing diagnostics, charts, tables, and state styling.
- Modify: `tests/test_main.py`
  - Responsibility: verify snapshot persistence behavior from runtime code.
- Modify: `tests/test_dashboard.py`
  - Responsibility: verify dashboard rendering, formatting, and fallback behavior.

## Task 1: Persist Live Market Context Into Position Snapshots

**Files:**
- Modify: `src/momentum_alpha/main.py:123-189`
- Modify: `src/momentum_alpha/main.py:191-219`
- Modify: `tests/test_main.py:2417-2460`

- [ ] **Step 1: Write the failing test for persisted live market payload**

Add a test beside the existing snapshot persistence coverage in `tests/test_main.py` that verifies the latest position snapshot payload stores per-position live market fields and top-level market context:

```python
def test_record_position_snapshot_persists_live_market_context(self) -> None:
    from momentum_alpha.main import _record_position_snapshot
    from momentum_alpha.runtime_store import RuntimeStateStore, fetch_recent_position_snapshots

    with tempfile.TemporaryDirectory() as tmpdir:
        runtime_db_path = Path(tmpdir) / "runtime.db"
        store = RuntimeStateStore(path=runtime_db_path)

        _record_position_snapshot(
            store=store,
            timestamp="2026-04-17T00:04:00+00:00",
            previous_leader_symbol="BASEUSDT",
            positions={
                "BASEUSDT": {
                    "symbol": "BASEUSDT",
                    "side": "LONG",
                    "total_quantity": Decimal("31119"),
                    "weighted_avg_entry_price": Decimal("0.17"),
                    "stop_price": Decimal("0.15"),
                    "legs": [],
                }
            },
            order_statuses={},
            market_payloads={
                "BASEUSDT": {
                    "latest_price": "0.1834",
                    "daily_change_pct": "0.0825",
                    "previous_hour_low": "0.1701",
                    "current_hour_low": "0.1799",
                }
            },
            market_context={
                "leader_symbol": "BASEUSDT",
                "leader_gap_pct": "0.0312",
                "candidates": [
                    {
                        "symbol": "BASEUSDT",
                        "latest_price": "0.1834",
                        "daily_change_pct": "0.0825",
                        "previous_hour_low": "0.1701",
                        "current_hour_low": "0.1799",
                    }
                ],
            },
        )

        snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=1)
        payload = snapshots[0]["payload"]
        self.assertEqual(payload["positions"]["BASEUSDT"]["latest_price"], "0.1834")
        self.assertEqual(payload["positions"]["BASEUSDT"]["daily_change_pct"], "0.0825")
        self.assertEqual(payload["market_context"]["leader_symbol"], "BASEUSDT")
        self.assertEqual(payload["market_context"]["leader_gap_pct"], "0.0312")
        self.assertEqual(payload["market_context"]["candidates"][0]["symbol"], "BASEUSDT")
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_record_position_snapshot_persists_live_market_context
```

Expected: FAIL because `_record_position_snapshot()` does not yet accept or persist `market_context`.

- [ ] **Step 3: Extend `_record_position_snapshot()` to persist live market payloads**

Update `src/momentum_alpha/main.py` so `_record_position_snapshot()` accepts `market_context: dict | None = None` and writes it into the snapshot payload. Merge the per-position fields from `market_payloads` into each position node and keep the existing payload shape backward compatible.

Implementation shape:

```python
def _record_position_snapshot(
    *,
    store: RuntimeStateStore,
    timestamp: str,
    previous_leader_symbol: str | None,
    positions: dict[str, dict],
    order_statuses: dict[str, dict],
    market_payloads: dict[str, dict] | None = None,
    market_context: dict | None = None,
) -> None:
    payload_positions: dict[str, dict] = {}
    for symbol, position in (positions or {}).items():
        payload = dict(position)
        if market_payloads and symbol in market_payloads:
            payload.update(market_payloads[symbol])
        payload_positions[symbol] = payload

    payload = {
        "positions": payload_positions,
        "order_statuses": order_statuses or {},
    }
    if market_context:
        payload["market_context"] = market_context

    insert_position_snapshot(
        path=store.path,
        timestamp=timestamp,
        leader_symbol=previous_leader_symbol,
        position_count=len(positions or {}),
        order_status_count=len(order_statuses or {}),
        payload=payload,
    )
```

- [ ] **Step 4: Thread the computed market context into all snapshot recording call sites**

At each `_record_position_snapshot(...)` call site in `src/momentum_alpha/main.py`, pass both `market_payloads=market_payloads` and a lightweight `market_context` built from `_build_market_context_payloads(...)`.

Use this shape:

```python
market_payloads, leader_gap_pct = _build_market_context_payloads(snapshots=snapshots)
market_context = {
    "leader_symbol": previous_leader_symbol,
    "leader_gap_pct": str(leader_gap_pct) if leader_gap_pct is not None else None,
    "candidates": list(market_payloads.values())[:5],
}
```

Keep the current behavior when no market snapshots are available:

```python
market_context = {"leader_symbol": previous_leader_symbol, "leader_gap_pct": None, "candidates": []}
```

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_main.MainTests.test_record_position_snapshot_persists_live_market_context
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_main.py src/momentum_alpha/main.py
git commit -m "feat: persist live market context in snapshots"
```

## Task 2: Render Live Position Diagnostics From Persisted Price Data

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:491-568`
- Modify: `src/momentum_alpha/dashboard.py:673-731`
- Modify: `tests/test_dashboard.py:1196-1316`

- [ ] **Step 1: Write the failing dashboard test for live diagnostics**

Add a test in `tests/test_dashboard.py` that verifies `build_position_details()` computes live metrics when `latest_price` is present in the payload:

```python
def test_build_position_details_computes_live_price_diagnostics(self) -> None:
    from momentum_alpha.dashboard import build_position_details

    position_snapshot = {
        "payload": {
            "positions": {
                "BASEUSDT": {
                    "symbol": "BASEUSDT",
                    "side": "LONG",
                    "total_quantity": "100",
                    "weighted_avg_entry_price": "10",
                    "stop_price": "9",
                    "latest_price": "12",
                    "legs": [],
                }
            }
        }
    }

    details = build_position_details(position_snapshot, equity_value="1000")

    self.assertEqual(details[0]["latest_price"], 12.0)
    self.assertEqual(details[0]["mtm_pnl"], 200.0)
    self.assertEqual(details[0]["pnl_pct"], 20.0)
    self.assertAlmostEqual(details[0]["distance_to_stop_pct"], 25.0)
    self.assertEqual(details[0]["notional_exposure"], 1200.0)
    self.assertEqual(details[0]["r_multiple"], 2.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_computes_live_price_diagnostics
```

Expected: FAIL because the persisted `latest_price` is not yet consumed into those computed fields.

- [ ] **Step 3: Implement live diagnostics in `build_position_details()`**

Update `src/momentum_alpha/dashboard.py` so `build_position_details()` reads persisted live fields and computes:

```python
latest_price = _parse_numeric(_object_field(position, "latest_price"))
notional_exposure = None
mtm_pnl = None
pnl_pct = None
distance_to_stop_pct = None
r_multiple = None

if latest_price is not None and latest_price > 0 and total_quantity is not None:
    notional_exposure = latest_price * total_quantity
    if avg_entry is not None:
        mtm_pnl = (latest_price - avg_entry) * total_quantity
        if avg_entry > 0:
            pnl_pct = ((latest_price - avg_entry) / avg_entry) * 100

if latest_price is not None and latest_price > 0 and stop_price is not None and stop_price > 0:
    distance_to_stop_pct = ((latest_price - stop_price) / latest_price) * 100

if mtm_pnl is not None and risk not in (None, 0):
    r_multiple = mtm_pnl / risk
```

Return the new values in each position details row.

- [ ] **Step 4: Render the new fields in the position cards**

Update the position-card renderer in `src/momentum_alpha/dashboard.py` so it shows:

```python
<div class='position-metric'><span class='metric-label'>CURRENT</span><span class='metric-value'>{current_price}</span></div>
<div class='position-metric'><span class='metric-label'>MTM</span><span class='metric-value'>{mtm_pnl}</span></div>
<div class='position-metric'><span class='metric-label'>PNL %</span><span class='metric-value'>{pnl_pct}</span></div>
<div class='position-metric'><span class='metric-label'>DIST TO STOP</span><span class='metric-value'>{dist_to_stop}</span></div>
<div class='position-metric'><span class='metric-label'>R MULTIPLE</span><span class='metric-value'>{r_multiple}</span></div>
<div class='position-metric'><span class='metric-label'>NOTIONAL</span><span class='metric-value'>{notional}</span></div>
```

Keep `n/a` only when inputs are actually missing.

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_computes_live_price_diagnostics
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: render live position diagnostics"
```

## Task 3: Fix Invalid Stop Rendering And Drawdown Semantics

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:509-561`
- Modify: `src/momentum_alpha/dashboard.py:696-724`
- Modify: `src/momentum_alpha/dashboard.py:1101-1144`
- Modify: `src/momentum_alpha/dashboard.py:1186-1188`
- Modify: `tests/test_dashboard.py:1288-1316`

- [ ] **Step 1: Write the failing tests for invalid stops and zero drawdown**

Add tests in `tests/test_dashboard.py`:

```python
def test_build_position_details_treats_zero_stop_as_unset(self) -> None:
    from momentum_alpha.dashboard import build_position_details

    details = build_position_details(
        {
            "payload": {
                "positions": {
                    "ORDIUSDT": {
                        "symbol": "ORDIUSDT",
                        "total_quantity": "10",
                        "weighted_avg_entry_price": "7.04",
                        "stop_price": "0",
                        "latest_price": "7.50",
                        "legs": [],
                    }
                }
            }
        },
        equity_value="1000",
    )

    self.assertIsNone(details[0]["stop_price"])
    self.assertIsNone(details[0]["distance_to_stop_pct"])
    self.assertIsNone(details[0]["r_multiple"])


def test_compute_account_range_stats_formats_zero_drawdown_without_plus_sign(self) -> None:
    from momentum_alpha.dashboard import _compute_account_range_stats, _format_metric

    stats = _compute_account_range_stats(
        [
            {"equity": "1000", "wallet_balance": "1000", "adjusted_equity": "1000", "unrealized_pnl": "0"},
            {"equity": "1000", "wallet_balance": "1000", "adjusted_equity": "1000", "unrealized_pnl": "0"},
        ]
    )

    self.assertEqual(_format_metric(stats["drawdown_abs"], signed=True), "0.00")
```

- [ ] **Step 2: Run the tests to verify they fail**

Run:

```bash
python3 -m unittest \
  tests.test_dashboard.DashboardTests.test_build_position_details_treats_zero_stop_as_unset \
  tests.test_dashboard.DashboardTests.test_compute_account_range_stats_formats_zero_drawdown_without_plus_sign
```

Expected: FAIL because zero stop is still treated as a numeric display value and signed zero still renders with `+`.

- [ ] **Step 3: Treat non-positive stops as unavailable**

In `build_position_details()` normalize `stop_price` immediately after parsing:

```python
stop_price = _parse_decimal(_object_field(position, "stop_price"))
if stop_price is not None and stop_price <= 0:
    stop_price = None
```

Use the normalized `stop_price` everywhere in risk and distance calculations.

- [ ] **Step 4: Normalize signed zero output**

Update `_format_metric()` in `src/momentum_alpha/dashboard.py` so signed zero renders as `0.00`, not `+0.00`:

```python
if value is None:
    return "n/a"
numeric = float(value)
if abs(numeric) < 1e-9:
    numeric = 0.0
if signed and numeric != 0:
    return f"{numeric:+,.2f}{suffix}"
return f"{numeric:,.2f}{suffix}"
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:

```bash
python3 -m unittest \
  tests.test_dashboard.DashboardTests.test_build_position_details_treats_zero_stop_as_unset \
  tests.test_dashboard.DashboardTests.test_compute_account_range_stats_formats_zero_drawdown_without_plus_sign
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "fix: normalize stop and drawdown rendering"
```

## Task 4: Normalize Table Formatting And Clarify Table Semantics

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:605-668`
- Modify: `tests/test_dashboard.py:1980-2125`

- [ ] **Step 1: Write the failing rendering test for normalized tables**

Add a test in `tests/test_dashboard.py` that checks for explicit table headings and trimmed numeric output:

```python
def test_render_dashboard_html_uses_explicit_headers_and_trimmed_precision(self) -> None:
    from momentum_alpha.dashboard import render_stop_slippage_table, render_closed_trades_table

    stop_html = render_stop_slippage_table(
        [
            {
                "symbol": "KOMAUSDT",
                "expected_stop_price": "0.011133889229651234",
                "executed_price": "0.0098",
                "slippage_pct": "-11.52678424",
            }
        ]
    )
    round_trip_html = render_closed_trades_table(
        [
            {
                "symbol": "ORDIUSDT",
                "round_trip_id": "ORDIUSDT:1",
                "opened_at": "2026-04-17T11:41:01+08:00",
                "closed_at": "2026-04-17T19:00:52+08:00",
                "exit_reason": "sell",
                "net_pnl": "73.12954018",
            }
        ]
    )

    self.assertIn("SYMBOL", stop_html)
    self.assertIn("STOP", stop_html)
    self.assertIn("EXEC", stop_html)
    self.assertIn("SLIP %", stop_html)
    self.assertIn("0.011134", stop_html)
    self.assertNotIn("0.011133889229651234", stop_html)
    self.assertIn("EXIT", round_trip_html)
    self.assertIn("PNL", round_trip_html)
    self.assertIn("73.13", round_trip_html)
    self.assertNotIn("73.12954018", round_trip_html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_uses_explicit_headers_and_trimmed_precision
```

Expected: FAIL because the current helpers still emit inconsistent precision and weak table semantics.

- [ ] **Step 3: Add shared formatting helpers and update the tables**

In `src/momentum_alpha/dashboard.py`, add focused helpers such as:

```python
def _format_price(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    if abs(numeric) >= 100:
        return f"{numeric:,.2f}"
    if abs(numeric) >= 1:
        return f"{numeric:,.4f}"
    return f"{numeric:,.6f}"


def _format_quantity(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:,.4f}".rstrip("0").rstrip(".")
```

Use those helpers inside:

- `render_stop_slippage_table()`
- `render_closed_trades_table()`
- any fill or stop-analysis row renderers used by the execution section

Add a visible header row to `STOP SLIPPAGE ANALYSIS` and tighten the round-trip table labels.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_uses_explicit_headers_and_trimmed_precision
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: normalize dashboard execution formatting"
```

## Task 5: Strengthen Leader Rotation, Empty States, And Risk Styling

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:1080-1098`
- Modify: `src/momentum_alpha/dashboard.py:1302-1349`
- Modify: `src/momentum_alpha/dashboard.py:1922-1957`
- Modify: `tests/test_dashboard.py:2090-2125`

- [ ] **Step 1: Write the failing test for rotation summary and risk highlighting**

Add a rendering test in `tests/test_dashboard.py`:

```python
def test_render_dashboard_html_surfaces_rotation_summary_and_risk_state(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(
        {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "BASEUSDT",
                "position_count": 2,
                "order_status_count": 0,
                "latest_position_snapshot": {"payload": {"market_context": {"candidates": []}}},
                "latest_account_snapshot": {"equity": "1367.35", "available_balance": "401.78"},
                "latest_signal_decision": {"decision_type": "no_action", "symbol": "BASEUSDT", "timestamp": "2026-04-17T00:04:00+00:00", "payload": {}},
            },
            "recent_account_snapshots": [
                {"timestamp": "2026-04-16T00:00:00+00:00", "equity": "1000", "wallet_balance": "1000", "adjusted_equity": "1000", "unrealized_pnl": "0", "position_count": 0, "open_order_count": 0},
                {"timestamp": "2026-04-17T00:00:00+00:00", "equity": "1367.35", "wallet_balance": "952.03", "adjusted_equity": "1367.35", "unrealized_pnl": "415.32", "position_count": 2, "open_order_count": 0},
            ],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_trade_fills": [],
            "recent_signal_decisions": [],
            "leader_history": [
                {"timestamp": "2026-04-17T00:01:00+00:00", "symbol": "BASEUSDT"},
                {"timestamp": "2026-04-17T00:02:00+00:00", "symbol": "ORDIUSDT"},
                {"timestamp": "2026-04-17T00:03:00+00:00", "symbol": "BASEUSDT"},
            ],
            "recent_events": [],
            "recent_broker_orders": [],
            "event_counts": {},
            "source_counts": {},
            "pulse_points": [],
            "warnings": [],
            "strategy_config": {"submit_orders": True},
            "state_positions": {
                "BASEUSDT": {"symbol": "BASEUSDT", "weighted_avg_entry_price": "0.17", "total_quantity": "31119", "stop_price": "0.15", "risk": "482.94"},
                "ORDIUSDT": {"symbol": "ORDIUSDT", "weighted_avg_entry_price": "7.04", "total_quantity": "62.6", "stop_price": "6.10", "risk": "440.76"},
            },
        }
    )

    self.assertIn("Recent Sequence", html)
    self.assertIn("BASEUSDT → ORDIUSDT → BASEUSDT", html)
    self.assertIn("metric danger", html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_surfaces_rotation_summary_and_risk_state
```

Expected: FAIL because the dashboard does not yet render rotation summary context or thresholded risk styling.

- [ ] **Step 3: Implement rotation summary and compact empty states**

In `src/momentum_alpha/dashboard.py`:

- derive a recent-sequence string from `leader_history`
- render it near the `LEADER ROTATION` section
- when the history contains fewer than two distinct points, render `insufficient history`
- when `blocked_reason_counts` is empty, replace the full breakdown block with a compact neutral string:

```python
blocked_reason_breakdown_html = "<div class='signal-breakdown-empty compact'>No blocked signals</div>"
```

- [ ] **Step 4: Add open-risk threshold styling**

Extend top metric-card generation so the `OPEN RISK / EQUITY` card gets an explicit severity class:

```python
open_risk_pct = trader_metrics["account"].get("open_risk_pct")
if open_risk_pct is None:
    risk_state = ""
elif open_risk_pct > 60:
    risk_state = "danger"
elif open_risk_pct >= 30:
    risk_state = "warning"
else:
    risk_state = "normal"
```

Apply the class to the metric:

```python
<div class='metric {risk_state}'>
```

Add matching CSS for `.metric.warning` and `.metric.danger`.

- [ ] **Step 5: Run the test to verify it passes**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_surfaces_rotation_summary_and_risk_state
```

Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: strengthen rotation and risk states"
```

## Task 6: Add Chart Discontinuity Notes And Run Regression Coverage

**Files:**
- Modify: `src/momentum_alpha/dashboard.py:1147-1204`
- Modify: `src/momentum_alpha/dashboard.py:2050-2140`
- Modify: `tests/test_dashboard.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing test for account chart discontinuity notes**

Add a dashboard test:

```python
def test_build_account_metrics_panel_surfaces_large_jump_note(self) -> None:
    from momentum_alpha.dashboard import _build_account_metrics_panel

    html = _build_account_metrics_panel(
        [
            {"timestamp": "2026-04-16T00:00:00+00:00", "equity": "100.00", "wallet_balance": "100.00", "adjusted_equity": "100.00", "unrealized_pnl": "0.00", "position_count": 0, "open_order_count": 0},
            {"timestamp": "2026-04-16T01:00:00+00:00", "equity": "1000.00", "wallet_balance": "1000.00", "adjusted_equity": "1000.00", "unrealized_pnl": "0.00", "position_count": 0, "open_order_count": 0},
        ]
    )

    self.assertIn("Large equity jump detected", html)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m unittest tests.test_dashboard.DashboardTests.test_build_account_metrics_panel_surfaces_large_jump_note
```

Expected: FAIL because the account panel does not yet surface chart discontinuity notes.

- [ ] **Step 3: Implement a lightweight discontinuity detector**

In `src/momentum_alpha/dashboard.py`, add a helper that inspects consecutive account points and flags a note when the equity change ratio exceeds a conservative threshold:

```python
def _detect_account_discontinuity(points: list[dict]) -> str | None:
    parsed = [_parse_numeric(point.get("equity")) for point in points]
    for previous, current in zip(parsed, parsed[1:]):
        if previous and current and abs(current - previous) / abs(previous) >= 0.5:
            return "Large equity jump detected in visible range; verify whether this reflects transfers, resets, or snapshot gaps."
    return None
```

Render that note inside `_build_account_metrics_panel()` below the subtitle when present.

- [ ] **Step 4: Run targeted and regression tests**

Run:

```bash
python3 -m unittest \
  tests.test_dashboard \
  tests.test_main \
  tests.test_runtime_store \
  tests.test_health
```

Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py tests/test_main.py src/momentum_alpha/dashboard.py src/momentum_alpha/main.py
git commit -m "feat: complete dashboard frontend remediation"
```

## Self-Review

Spec coverage check:

- live-price diagnostics: Task 1, Task 2
- invalid stop rendering: Task 3
- drawdown semantics: Task 3
- account chart trust note: Task 6
- leader rotation context: Task 5
- execution/round-trip readability: Task 4
- empty and high-risk states: Task 5

Placeholder scan:

- no `TODO`, `TBD`, or deferred placeholders left in the plan
- each task includes explicit files, code examples, commands, and expected outcomes

Type consistency check:

- snapshot payload uses `market_context`
- per-position live data uses `latest_price`, `daily_change_pct`, `previous_hour_low`, `current_hour_low`
- dashboard detail fields use `latest_price`, `mtm_pnl`, `pnl_pct`, `distance_to_stop_pct`, `notional_exposure`, `r_multiple`

