# Dashboard Live Monitor Core Lines Shared Time Axis Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make the four `CORE LIVE LINES` charts share one timestamp domain so `Account Equity`, `Margin Usage %`, `Position Count`, and `Open Risk` line up on the same moments in time.

**Architecture:** Build one shared live-core timeline from the union of account and open-risk timestamps, preserve the existing per-series payloads for compatibility, and render each chart from timestamp-based x coordinates instead of per-series index positions. The live room keeps the same 2x2 layout and card order; only the time projection changes.

**Tech Stack:** Python 3.11, server-rendered HTML/SVG, pytest, existing dashboard rendering pipeline.

---

## File Structure

- Modify: `src/momentum_alpha/dashboard_data_payloads.py`
  - Add the shared live-core timeline projection.
  - Keep `account` and `position_risk` payloads unchanged for other consumers.
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
  - Change the SVG renderer to compute x coordinates from timestamps.
  - Update the live-core panel to render all four cards from the shared timeline.
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
  - Pass the shared live-core timeline into `CORE LIVE LINES`.
- Modify: `tests/test_dashboard_position_risk.py`
  - Cover shared timeline projection and timestamp-based x spacing.
- Modify: `tests/test_dashboard.py`
  - Cover dashboard-level wiring and room-level regression.

## Task 1: Build a shared live-core timeline in the payload layer

**Files:**
- Modify: `src/momentum_alpha/dashboard_data_payloads.py`
- Modify: `tests/test_dashboard_position_risk.py`

- [ ] **Step 1: Write the failing test**

```python
def test_build_dashboard_timeseries_payload_creates_shared_core_live_timeline(self) -> None:
    from momentum_alpha.dashboard import build_dashboard_timeseries_payload

    snapshot = {
        "recent_account_snapshots": [
            {
                "timestamp": "2026-04-23T09:00:00+00:00",
                "wallet_balance": "100.00",
                "available_balance": "90.00",
                "equity": "100.00",
                "unrealized_pnl": "0.00",
                "position_count": 1,
                "open_order_count": 1,
            },
            {
                "timestamp": "2026-04-23T09:05:00+00:00",
                "wallet_balance": "102.00",
                "available_balance": "92.00",
                "equity": "102.00",
                "unrealized_pnl": "2.00",
                "position_count": 1,
                "open_order_count": 1,
            },
        ],
        "recent_position_risk_snapshots": [
            {
                "timestamp": "2026-04-23T09:02:00+00:00",
                "payload": {
                    "positions": {
                        "BTCUSDT": {
                            "side": "LONG",
                            "legs": [
                                {"quantity": "1", "entry_price": "100", "stop_price": "90"}
                            ],
                        }
                    }
                },
            }
        ],
    }

    payload = build_dashboard_timeseries_payload(snapshot)

    self.assertEqual(
        [point["timestamp"] for point in payload["core_live_timeline"]],
        [
            "2026-04-23T09:00:00+00:00",
            "2026-04-23T09:02:00+00:00",
            "2026-04-23T09:05:00+00:00",
        ],
    )
    self.assertEqual(payload["core_live_timeline"][0]["open_risk"], None)
    self.assertEqual(payload["core_live_timeline"][1]["open_risk"], 10.0)
    self.assertEqual(payload["core_live_timeline"][2]["open_risk"], 10.0)
    self.assertEqual(payload["core_live_timeline"][1]["equity"], 100.0)
    self.assertEqual(payload["account"][0]["equity"], 100.0)
    self.assertEqual(payload["position_risk"][0]["open_risk"], 10.0)
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_dashboard_position_risk.py -k shared_core_live_timeline -v
```

Expected: FAIL because `build_dashboard_timeseries_payload(...)` does not yet return `core_live_timeline`.

- [ ] **Step 3: Implement the shared timeline projection**

Add a small helper in `dashboard_data_payloads.py` that merges the timestamp sets from `account_points` and `position_risk_points`, then forward-fills the latest known values for each metric:

```python
def _build_shared_core_live_timeline(account_points: list[dict], position_risk_points: list[dict]) -> list[dict]:
    timestamps = sorted(
        {
            point["timestamp"]
            for point in account_points + position_risk_points
            if point.get("timestamp")
        }
    )
    shared_points: list[dict] = []
    account_index = 0
    position_risk_index = 0
    latest_account_point: dict | None = None
    latest_position_risk_point: dict | None = None

    for timestamp in timestamps:
        while account_index < len(account_points) and (account_points[account_index].get("timestamp") or "") <= timestamp:
            latest_account_point = account_points[account_index]
            account_index += 1
        while position_risk_index < len(position_risk_points) and (position_risk_points[position_risk_index].get("timestamp") or "") <= timestamp:
            latest_position_risk_point = position_risk_points[position_risk_index]
            position_risk_index += 1

        shared_points.append(
            {
                "timestamp": timestamp,
                "equity": None if latest_account_point is None else latest_account_point.get("equity"),
                "margin_usage_pct": None if latest_account_point is None else latest_account_point.get("margin_usage_pct"),
                "position_count": None if latest_account_point is None else latest_account_point.get("position_count"),
                "open_risk": None if latest_position_risk_point is None else latest_position_risk_point.get("open_risk"),
            }
        )

    return shared_points
```

Then extend `build_dashboard_timeseries_payload(...)` to return:

```python
return {
    "account": account_points,
    "position_risk": position_risk_points,
    "core_live_timeline": _build_shared_core_live_timeline(account_points, position_risk_points),
    "pulse_points": snapshot.get("pulse_points", []),
    "leader_history": list(reversed(snapshot.get("leader_history", []))),
}
```

Keep `account` and `position_risk` unchanged so existing consumers do not break.

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_dashboard_position_risk.py -k shared_core_live_timeline -v
python3 -m pytest tests/test_dashboard_position_risk.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_data_payloads.py tests/test_dashboard_position_risk.py
git commit -m "feat: add shared live core timeline payload"
```

## Task 2: Render live core charts from timestamp-based x coordinates

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
- Modify: `tests/test_dashboard_position_risk.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_line_chart_svg_uses_timestamp_spacing(self) -> None:
    from momentum_alpha.dashboard_render_panels import _render_line_chart_svg
    import re

    svg = _render_line_chart_svg(
        points=[
            {"timestamp": "2026-04-23T09:00:00+00:00", "equity": 100.0},
            {"timestamp": "2026-04-23T09:10:00+00:00", "equity": 110.0},
            {"timestamp": "2026-04-23T10:10:00+00:00", "equity": 120.0},
        ],
        value_key="equity",
        stroke="#4cc9f0",
        fill="#4cc9f0",
    )

    match = re.search(r"<polyline points='([^']+)'", svg)
    self.assertIsNotNone(match)
    x_values = [float(pair.split(",")[0]) for pair in match.group(1).split()]
    self.assertLess(x_values[1] - x_values[0], x_values[2] - x_values[1])
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_dashboard_position_risk.py -k timestamp_spacing -v
```

Expected: FAIL because `_render_line_chart_svg(...)` still spaces points by index, not by timestamp.

- [ ] **Step 3: Update the SVG renderer and the live-core panel**

In `dashboard_render_panels.py`, add timestamp parsing and use a shared timestamp domain when computing x positions:

```python
from datetime import datetime

def _parse_chart_timestamp(timestamp: str | None) -> datetime | None:
    if not timestamp:
        return None
    try:
        return datetime.fromisoformat(timestamp)
    except ValueError:
        return None
```

Then change `_render_line_chart_svg(...)` so it:

- reads `timestamp` from each point
- computes the x coordinate from the point's timestamp relative to the earliest and latest timestamp in the series
- expands a single-timestamp domain slightly so the dot does not collapse into a zero-width axis
- keeps the current y-axis formatting, colors, dots, and empty-state behavior

Update `_build_live_core_lines_panel(...)` to take the shared timeline list once and pass that same list to all four cards:

```python
def _build_live_core_lines_panel(core_live_points: list[dict]) -> str:
    chart_specs = (
        ("Account Equity", "equity", "#4cc9f0", core_live_points, ""),
        ("Margin Usage %", "margin_usage_pct", "#ff8c42", core_live_points, ""),
        ("Position Count", "position_count", "#36d98a", core_live_points, ""),
        ("Open Risk", "open_risk", "#ff5d73", core_live_points, "live-core-line-card--open-risk"),
    )
```

- [ ] **Step 4: Run the test to verify it passes**

Run:

```bash
python3 -m pytest tests/test_dashboard_position_risk.py -k timestamp_spacing -v
python3 -m pytest tests/test_dashboard_position_risk.py -v
```

Expected: both PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_render_panels.py tests/test_dashboard_position_risk.py
git commit -m "feat: render live core lines on shared timestamps"
```

## Task 3: Wire the live room to the shared timeline and add dashboard regressions

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing test**

```python
def test_render_dashboard_html_keeps_live_core_lines_order_with_shared_timeline(self) -> None:
    from momentum_alpha.dashboard import build_dashboard_timeseries_payload, render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["recent_account_snapshots"] = [
        {
            "timestamp": "2026-04-23T09:00:00+00:00",
            "wallet_balance": "100.00",
            "available_balance": "90.00",
            "equity": "100.00",
            "unrealized_pnl": "0.00",
            "position_count": 1,
            "open_order_count": 1,
        },
        {
            "timestamp": "2026-04-23T09:05:00+00:00",
            "wallet_balance": "102.00",
            "available_balance": "92.00",
            "equity": "102.00",
            "unrealized_pnl": "2.00",
            "position_count": 1,
            "open_order_count": 1,
        },
    ]
    snapshot["recent_position_risk_snapshots"] = [
        {
            "timestamp": "2026-04-23T09:02:00+00:00",
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "side": "LONG",
                        "legs": [
                            {"quantity": "1", "entry_price": "100", "stop_price": "90"}
                        ],
                    }
                }
            },
        }
    ]

    timeseries = build_dashboard_timeseries_payload(snapshot)
    self.assertIn("core_live_timeline", timeseries)
    self.assertEqual(len(timeseries["core_live_timeline"]), 3)

    html = render_dashboard_html(snapshot, account_range_key="1D")
    self.assertIn("CORE LIVE LINES", html)
    self.assertIn("Open Risk", html)
    self.assertLess(html.index("Position Count"), html.index("Open Risk"))
```

- [ ] **Step 2: Run the test to verify it fails**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k shared_timeline -v
```

Expected: FAIL because `render_dashboard_html(...)` still wires the live room through the old two-argument core-lines call.

- [ ] **Step 3: Wire `render_dashboard_body(...)` to the shared timeline**

In `dashboard_render_shell.py`, change the live-room call site from:

```python
core_lines_html = _build_live_core_lines_panel(timeseries["account"], timeseries["position_risk"])
```

to:

```python
core_lines_html = _build_live_core_lines_panel(timeseries["core_live_timeline"])
```

Keep the rest of the live-room structure unchanged.

- [ ] **Step 4: Run the tests to verify they pass**

Run:

```bash
python3 -m pytest tests/test_dashboard.py -k shared_timeline -v
python3 -m pytest tests/test_dashboard.py -v
python3 -m pytest tests/test_dashboard_position_risk.py -v
```

Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_render_shell.py tests/test_dashboard.py
git commit -m "feat: wire live core lines to shared timeline"
```

## Final Verification

After all three tasks:

1. Run the focused tests above.
2. Run the full dashboard suite:

```bash
python3 -m pytest tests/test_dashboard.py -q
python3 -m pytest tests/test_dashboard_position_risk.py -q
```

3. Confirm the live room still renders the same four cards in the same order, but the charts now share one time axis.
