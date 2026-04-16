# Dashboard Live Price Data Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Persist runtime market data into snapshot payloads so the dashboard can render live-price-dependent position diagnostics and a lightweight candidate summary, while also surfacing the already-computed signal aggregation values.

**Architecture:** Extend the existing runtime snapshot payloads in `main.py` rather than adding a new database table. The dashboard will continue reading the latest structured snapshots, but `dashboard.py` will derive current-price metrics from newly persisted per-position market fields and render candidate, blocked-reason, and rotation summaries from the same payloads and existing trader metric helpers.

**Tech Stack:** Python 3, `unittest`, existing SQLite runtime store, server-rendered HTML/CSS/JS in `dashboard.py`

---

### Task 1: Persist Live Market Context Into Snapshot Payloads

**Files:**
- Modify: `src/momentum_alpha/main.py`
- Test: `tests/test_main.py`

- [ ] **Step 1: Write the failing tests for persisted market context**

```python
def test_run_once_records_live_market_context_in_position_snapshot_payload(self) -> None:
    from momentum_alpha.runtime_store import fetch_recent_position_snapshots

    # after a live tick with one open position, the latest position snapshot payload
    # should include latest_price, daily_change_pct, previous_hour_low, current_hour_low,
    # and top-level market_context candidates / leader_gap_pct.
    ...
    self.assertEqual(snapshot["payload"]["positions"]["BTCUSDT"]["latest_price"], "61200")
    self.assertEqual(snapshot["payload"]["positions"]["BTCUSDT"]["daily_change_pct"], "0.02")
    self.assertEqual(snapshot["payload"]["market_context"]["leader_symbol"], "BTCUSDT")
    self.assertEqual(snapshot["payload"]["market_context"]["candidates"][0]["symbol"], "BTCUSDT")

def test_run_once_limits_market_context_candidates_to_top_five(self) -> None:
    from momentum_alpha.runtime_store import fetch_recent_position_snapshots

    ...
    self.assertEqual(len(snapshot["payload"]["market_context"]["candidates"]), 5)
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `python3 -m unittest tests.test_main.MainTests.test_run_once_records_live_market_context_in_position_snapshot_payload tests.test_main.MainTests.test_run_once_limits_market_context_candidates_to_top_five`

Expected: `FAIL` because the snapshot payload does not yet persist these market-context fields.

- [ ] **Step 3: Implement minimal payload persistence in `src/momentum_alpha/main.py`**

```python
def _build_market_context_payloads(*, snapshots: list[dict], candidate_limit: int = 5) -> tuple[dict[str, dict], dict]:
    ordered = sorted(
        [...],
        key=lambda item: item["daily_change_pct"],
        reverse=True,
    )
    leader_gap_pct = ...
    per_symbol_payloads = {}
    for item in ordered:
        per_symbol_payloads[item["symbol"]] = {
            "latest_price": str(item["latest_price"]),
            "daily_change_pct": str(item["daily_change_pct"]),
            "previous_hour_low": str(item["previous_hour_low"]),
            "current_hour_low": str(item["current_hour_low"]),
        }
    market_context = {
        "leader_symbol": ordered[0]["symbol"] if ordered else None,
        "leader_gap_pct": str(leader_gap_pct) if leader_gap_pct is not None else None,
        "candidates": [
            {
                "symbol": item["symbol"],
                "latest_price": str(item["latest_price"]),
                "daily_change_pct": str(item["daily_change_pct"]),
                "previous_hour_low": str(item["previous_hour_low"]),
                "current_hour_low": str(item["current_hour_low"]),
            }
            for item in ordered[:candidate_limit]
        ],
    }
    return per_symbol_payloads, market_context


position_payload = payload or {}
positions_payload = position_payload.get("positions") or {}
for symbol, position in positions_payload.items():
    if symbol in per_symbol_payloads and isinstance(position, dict):
        position.update(per_symbol_payloads[symbol])
position_payload["market_context"] = market_context
```

- [ ] **Step 4: Run the targeted tests to verify the new persistence passes**

Run: `python3 -m unittest tests.test_main.MainTests.test_run_once_records_live_market_context_in_position_snapshot_payload tests.test_main.MainTests.test_run_once_limits_market_context_candidates_to_top_five`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_main.py src/momentum_alpha/main.py
git commit -m "feat: persist live market context in snapshots"
```

### Task 2: Compute Live-Price Position Diagnostics In The Dashboard

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests for persisted live-price position metrics**

```python
def test_build_position_details_computes_live_price_metrics_when_market_fields_exist(self) -> None:
    from momentum_alpha.dashboard import build_position_details

    details = build_position_details(
        {
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "symbol": "BTCUSDT",
                        "stop_price": "81000",
                        "latest_price": "83000",
                        "daily_change_pct": "0.025",
                        "previous_hour_low": "81200",
                        "current_hour_low": "81800",
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
        equity_value="1000",
    )

    self.assertEqual(details[0]["current_price"], "83000")
    self.assertEqual(details[0]["notional_exposure"], "830.00")
    self.assertEqual(details[0]["mtm_pnl"], "10.00")
    self.assertEqual(details[0]["pnl_pct"], "1.22")
    self.assertEqual(details[0]["distance_to_stop_pct"], "2.41")
    self.assertEqual(details[0]["r_multiple"], "1.00")

def test_render_position_cards_shows_live_price_metrics_when_available(self) -> None:
    from momentum_alpha.dashboard import render_position_cards

    html = render_position_cards(
        [
            {
                "symbol": "BTCUSDT",
                "direction": "LONG",
                "total_quantity": "0.01",
                "entry_price": "82000.00",
                "stop_price": "81000",
                "risk": "10.00",
                "risk_pct_of_equity": "1.00",
                "current_price": "83000",
                "notional_exposure": "830.00",
                "mtm_pnl": "10.00",
                "pnl_pct": "1.22",
                "distance_to_stop_pct": "2.41",
                "r_multiple": "1.00",
                "leg_count": 1,
                "opened_at": "2026-04-15T09:15:00+00:00",
                "legs": [],
            }
        ]
    )

    self.assertIn("Current Price", html)
    self.assertIn("PnL %", html)
    self.assertIn("R", html)
    self.assertIn("83000", html)
    self.assertIn("1.22%", html)
```

- [ ] **Step 2: Run the targeted tests to verify they fail**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_computes_live_price_metrics_when_market_fields_exist tests.test_dashboard.DashboardTests.test_render_position_cards_shows_live_price_metrics_when_available`

Expected: `FAIL` because the live-price-derived fields are not computed or rendered yet.

- [ ] **Step 3: Implement the minimal dashboard metric derivation**

```python
latest_price = _parse_decimal(_object_field(position, "latest_price"))
mtm_pnl = None
pnl_pct = None
distance_to_stop_pct = None
r_multiple = None
notional_exposure = None
if latest_price is not None and total_quantity > 0:
    notional_exposure = latest_price * total_quantity
    mtm_pnl = (latest_price - avg_entry) * total_quantity
if latest_price is not None and avg_entry > 0:
    pnl_pct = ((latest_price - avg_entry) / avg_entry) * Decimal("100")
if latest_price is not None and stop_price is not None and latest_price > 0 and stop_price > 0:
    distance_to_stop_pct = ((latest_price - stop_price) / latest_price) * Decimal("100")
if mtm_pnl is not None and risk is not None and risk > 0:
    r_multiple = mtm_pnl / risk
```

- [ ] **Step 4: Run the targeted tests to verify the live-price diagnostics pass**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_build_position_details_computes_live_price_metrics_when_market_fields_exist tests.test_dashboard.DashboardTests.test_render_position_cards_shows_live_price_metrics_when_available`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: render live price position diagnostics"
```

### Task 3: Render Candidate Summary And Signal Aggregates

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing tests for candidate summary and signal aggregation rendering**

```python
def test_render_dashboard_html_shows_market_context_candidates_and_signal_aggregates(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    html = render_dashboard_html(
        {
            "health": {"overall_status": "OK", "items": []},
            "runtime": {
                "previous_leader_symbol": "AAAUSDT",
                "position_count": 1,
                "order_status_count": 0,
                "latest_position_snapshot": {
                    "payload": {
                        "positions": {},
                        "market_context": {
                            "leader_symbol": "AAAUSDT",
                            "leader_gap_pct": "0.0042",
                            "candidates": [
                                {"symbol": "AAAUSDT", "daily_change_pct": "0.0321", "latest_price": "1.01"},
                                {"symbol": "BBBUSDT", "daily_change_pct": "0.0279", "latest_price": "0.98"},
                            ],
                        },
                    }
                },
                "latest_account_snapshot": {"wallet_balance": "1000", "available_balance": "900", "equity": "1000"},
                "latest_signal_decision": {"decision_type": "base_entry", "symbol": "AAAUSDT", "timestamp": "2026-04-16T00:55:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
            },
            "recent_signal_decisions": [
                {"timestamp": "2026-04-16T00:10:00+00:00", "payload": {"blocked_reason": "risk_limit"}},
                {"timestamp": "2026-04-16T00:30:00+00:00", "payload": {"blocked_reason": "invalid_stop_price"}},
            ],
            "leader_history": [
                {"timestamp": "2026-04-16T00:00:00+00:00", "symbol": "AAAUSDT"},
                {"timestamp": "2026-04-16T00:15:00+00:00", "symbol": "BBBUSDT"},
            ],
            "recent_account_snapshots": [],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_trade_fills": [],
            "recent_events": [],
            "recent_broker_orders": [],
            "event_counts": {},
            "source_counts": {},
            "pulse_points": [],
            "warnings": [],
        }
    )

    self.assertIn("Rotation Count", html)
    self.assertIn("Blocked Reasons", html)
    self.assertIn("Top Candidates", html)
    self.assertIn("Leader Gap", html)
    self.assertIn("AAAUSDT", html)
    self.assertIn("BBBUSDT", html)
```

- [ ] **Step 2: Run the targeted test to verify it fails**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_shows_market_context_candidates_and_signal_aggregates`

Expected: `FAIL` because candidate ranking is not rendered yet and signal aggregation output is incomplete.

- [ ] **Step 3: Implement the minimal signal/candidate rendering**

```python
market_context = (latest_position_snapshot.get("payload") or {}).get("market_context") or {}
candidates = market_context.get("candidates") or []
candidate_rows_html = "".join(
    f"<div class='data-row'><span class='row-main'>{escape(item.get('symbol') or '-')} · {escape(str(item.get('daily_change_pct') or 'n/a'))}</span>"
    f"<span class='row-time'>{escape(str(item.get('latest_price') or 'n/a'))}</span></div>"
    for item in candidates[:5]
) or "<div class='data-row empty'>No candidates</div>"
```

- [ ] **Step 4: Run the targeted test to verify candidate and signal rendering passes**

Run: `python3 -m unittest tests.test_dashboard.DashboardTests.test_render_dashboard_html_shows_market_context_candidates_and_signal_aggregates`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py src/momentum_alpha/dashboard.py
git commit -m "feat: show candidate ranking and signal aggregates"
```

### Task 4: Full Dashboard Regression And Backward Compatibility

**Files:**
- Modify: `src/momentum_alpha/dashboard.py`
- Test: `tests/test_dashboard.py`, `tests/test_main.py`

- [ ] **Step 1: Write the failing backward-compatibility test for old payloads**

```python
def test_render_dashboard_html_keeps_live_price_metrics_unavailable_for_legacy_payloads(self) -> None:
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
                "latest_account_snapshot": {"wallet_balance": "1000", "available_balance": "900", "equity": "1000"},
                "latest_signal_decision": {},
            },
            "recent_account_snapshots": [],
            "recent_trade_round_trips": [],
            "recent_stop_exit_summaries": [],
            "recent_trade_fills": [],
            "recent_signal_decisions": [],
            "leader_history": [],
            "recent_events": [],
            "recent_broker_orders": [],
            "event_counts": {},
            "source_counts": {},
            "pulse_points": [],
            "warnings": [],
        }
    )

    self.assertIn("waiting for live price data", html)
```

- [ ] **Step 2: Run the compatibility and full regression tests**

Run: `python3 -m unittest tests.test_dashboard tests.test_main tests.test_runtime_store tests.test_health`

Expected: `PASS`

- [ ] **Step 3: Make any final compatibility adjustments if the regression set exposes issues**

```python
# preserve legacy snapshot behavior:
# if latest_price / market_context are absent, continue rendering n/a and empty candidate state
```

- [ ] **Step 4: Re-run the full regression tests**

Run: `python3 -m unittest tests.test_dashboard tests.test_main tests.test_runtime_store tests.test_health`

Expected: `PASS`

- [ ] **Step 5: Commit**

```bash
git add tests/test_dashboard.py tests/test_main.py src/momentum_alpha/dashboard.py src/momentum_alpha/main.py
git commit -m "test: verify live price dashboard data compatibility"
```

## Self-Review

- Spec coverage: The plan covers persisted per-position live market fields, top-5 candidate summary, live-price-derived dashboard metrics, backward compatibility, and the already-approved signal aggregate display gap.
- Placeholder scan: All tasks specify exact files, commands, expected failures, and concrete implementation targets.
- Type consistency: The plan consistently uses `market_context`, `candidates`, `latest_price`, and `build_position_details` as the shared interfaces between `main.py` and `dashboard.py`.
