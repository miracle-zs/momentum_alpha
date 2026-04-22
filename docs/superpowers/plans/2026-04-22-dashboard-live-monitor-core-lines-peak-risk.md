# Dashboard Live Monitor Core Lines Peak Risk Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add a fourth live `Peak Risk` chart to `实时监控室` CORE LIVE LINES using the existing position snapshot stream.

**Architecture:** Introduce one shared position-risk helper so the live position detail view and the new peak-risk series use the same math. Extend the dashboard timeseries payload with a `position_risk` series built from `recent_position_snapshots`, then pass that series into the live room renderer and present it as a fourth equal-width card. Keep the change server-rendered, with responsive CSS that stays 4-wide on desktop, 2x2 on tablet, and stacked on mobile.

**Tech Stack:** Python 3.11, pytest, server-rendered HTML, inline SVG charts, existing dashboard CSS.

---

## File Structure

- Create `src/momentum_alpha/dashboard_position_risk.py`: shared helpers for per-position risk math and for building the live peak-risk series from snapshots.
- Modify `src/momentum_alpha/dashboard_data_payloads.py`: add `position_risk` to `build_dashboard_timeseries_payload`.
- Modify `src/momentum_alpha/dashboard_view_model.py`: reuse the shared helper inside `build_position_details` so the detail card and the chart share the same formula.
- Modify `src/momentum_alpha/dashboard_render_shell.py`: pass `timeseries["position_risk"]` into the live core lines renderer.
- Modify `src/momentum_alpha/dashboard_render_panels.py`: render the fourth `Peak Risk` card and keep the existing three cards in order.
- Modify `src/momentum_alpha/dashboard_assets_styles.py`: add a live-only 4-card grid and responsive breakpoints.
- Modify `tests/test_dashboard.py`: assert the live room renders the new card/order and the live panel still behaves with sparse snapshots.
- Create `tests/test_dashboard_position_risk.py`: keep the risk-math and series-builder tests focused and small.

## Task 1: Extract shared position-risk math and emit the series

**Files:**
- Create: `src/momentum_alpha/dashboard_position_risk.py`
- Modify: `src/momentum_alpha/dashboard_data_payloads.py`
- Modify: `src/momentum_alpha/dashboard_view_model.py`
- Create: `tests/test_dashboard_position_risk.py`

- [ ] **Step 1: Write the failing tests**

```python
from decimal import Decimal

from momentum_alpha.dashboard import build_dashboard_timeseries_payload, build_position_details
from momentum_alpha.dashboard_position_risk import build_position_risk_series, compute_position_risk


def test_compute_position_risk_handles_long_and_short_books():
    long_position = {
        "side": "LONG",
        "legs": [
            {"quantity": "1", "entry_price": "100", "stop_price": "90"},
        ],
    }
    short_position = {
        "side": "SHORT",
        "legs": [
            {"quantity": "2", "entry_price": "100", "stop_price": "108"},
        ],
    }
    assert compute_position_risk(long_position) == Decimal("10")
    assert compute_position_risk(short_position) == Decimal("16")


def test_build_position_risk_series_skips_incomplete_positions():
    snapshots = [
        {
            "timestamp": "2026-04-15T08:48:00+00:00",
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "side": "LONG",
                        "legs": [{"quantity": "1", "entry_price": "100", "stop_price": "90"}],
                    },
                    "BROKEN": {
                        "side": "LONG",
                        "legs": [{"quantity": "1", "entry_price": "100"}],
                    },
                }
            },
        },
        {
            "timestamp": "2026-04-15T08:49:00+00:00",
            "payload": {"positions": {}},
        },
    ]
    series = build_position_risk_series(snapshots)
    assert series == [{"timestamp": "2026-04-15T08:48:00+00:00", "peak_risk": 10.0}]


def test_build_dashboard_timeseries_payload_includes_position_risk():
    snapshot = {
        "recent_account_snapshots": [],
        "account_metric_flows": [],
        "leader_history": [],
        "pulse_points": [],
        "recent_position_snapshots": [
            {
                "timestamp": "2026-04-15T08:48:00+00:00",
                "payload": {
                    "positions": {
                        "BTCUSDT": {
                            "side": "LONG",
                            "legs": [{"quantity": "1", "entry_price": "100", "stop_price": "90"}],
                        }
                    }
                },
            }
        ],
    }
    payload = build_dashboard_timeseries_payload(snapshot)
    assert payload["position_risk"] == [{"timestamp": "2026-04-15T08:48:00+00:00", "peak_risk": 10.0}]


def test_build_position_details_uses_shared_risk_math():
    position_snapshot = {
        "payload": {
            "positions": {
                "ETHUSDT": {
                    "side": "SHORT",
                    "stop_price": "108",
                    "latest_price": "96",
                    "legs": [
                        {
                            "quantity": "2",
                            "entry_price": "100",
                            "stop_price": "108",
                            "opened_at": "2026-04-15T08:00:00+00:00",
                        }
                    ],
                }
            }
        }
    }
    details = build_position_details(position_snapshot, equity_value="1000")
    assert details[0]["risk"] == "16.00"
```

- [ ] **Step 2: Run test to verify it fails**

Run: `python3 -m pytest tests/test_dashboard_position_risk.py -v`

Expected: fail because `dashboard_position_risk.py` does not exist yet and `position_risk` is missing from the payload.

- [ ] **Step 3: Write the shared helper and wire it into the payload**

```python
# src/momentum_alpha/dashboard_position_risk.py
from collections.abc import Mapping
from decimal import Decimal


def _object_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def compute_position_risk(position: object) -> Decimal | None:
    if not isinstance(position, Mapping) and not hasattr(position, "__dict__") and not hasattr(type(position), "__dataclass_fields__"):
        return None

    direction = str(_object_field(position, "side") or _object_field(position, "direction") or "LONG").upper()
    legs = _object_field(position, "legs") or []
    stop_price = _parse_decimal(_object_field(position, "stop_price"))
    if stop_price is not None and stop_price <= 0:
        stop_price = None

    total_quantity = Decimal("0")
    weighted_entry_sum = Decimal("0")
    weighted_stop_sum = Decimal("0")
    leg_stop_values_known = True
    leg_seen = False

    if isinstance(legs, (list, tuple)) and legs:
        for leg in legs:
            if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                continue
            qty = _parse_decimal(_object_field(leg, "quantity"))
            entry = _parse_decimal(_object_field(leg, "entry_price"))
            leg_stop = _parse_decimal(_object_field(leg, "stop_price"))
            if leg_stop is None:
                leg_stop = stop_price
            if qty is None or entry is None:
                continue
            leg_seen = True
            total_quantity += qty
            weighted_entry_sum += qty * entry
            if leg_stop is None:
                leg_stop_values_known = False
            else:
                weighted_stop_sum += qty * leg_stop
        if leg_seen and leg_stop_values_known and total_quantity > 0:
            if direction == "SHORT":
                return weighted_stop_sum - weighted_entry_sum
            return weighted_entry_sum - weighted_stop_sum

    if stop_price is None:
        return None

    if total_quantity <= 0:
        total_quantity = _parse_decimal(_object_field(position, "total_quantity")) or Decimal("0")
    avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
    if avg_entry is None:
        avg_entry = _parse_decimal(_object_field(position, "entry_price"))
    if total_quantity <= 0 or avg_entry is None:
        return None

    if direction == "SHORT":
        return total_quantity * (stop_price - avg_entry)
    return total_quantity * (avg_entry - stop_price)


def build_position_risk_series(position_snapshots: list[dict]) -> list[dict]:
    series: list[dict] = []
    for snapshot in sorted(position_snapshots, key=lambda item: item.get("timestamp") or ""):
        timestamp = snapshot.get("timestamp")
        payload = snapshot.get("payload") or {}
        positions = payload.get("positions") or {}
        if not timestamp or not isinstance(positions, Mapping):
            continue
        snapshot_risk = Decimal("0")
        snapshot_has_risk = False
        for position in positions.values():
            risk = compute_position_risk(position)
            if risk is None:
                continue
            snapshot_risk += risk
            snapshot_has_risk = True
        if snapshot_has_risk:
            series.append({"timestamp": timestamp, "peak_risk": float(snapshot_risk)})
    return series
```

```python
# src/momentum_alpha/dashboard_data_payloads.py
from .dashboard_position_risk import build_position_risk_series
```

Add this line inside `build_dashboard_timeseries_payload(...)` right before the return block:

```python
"position_risk": build_position_risk_series(snapshot.get("recent_position_snapshots", [])),
```

```python
# src/momentum_alpha/dashboard_view_model.py
from .dashboard_position_risk import compute_position_risk
```

Replace the existing risk calculation inside `build_position_details(...)` with:

```python
risk = compute_position_risk(position)
```

Keep the existing `details.append` block unchanged except for the `risk` field line:

```python
"risk": f"{risk:.2f}" if risk is not None else None,
```

- [ ] **Step 4: Run the focused tests again**

Run: `python3 -m pytest tests/test_dashboard_position_risk.py -v`

Expected: PASS with the new shared helper and timeseries key.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_position_risk.py src/momentum_alpha/dashboard_data_payloads.py src/momentum_alpha/dashboard_view_model.py tests/test_dashboard_position_risk.py
git commit -m "feat: add live peak risk series"
```

## Task 2: Render the fourth core-line card and update layout

**Files:**
- Modify: `src/momentum_alpha/dashboard_render_shell.py`
- Modify: `src/momentum_alpha/dashboard_render_panels.py`
- Modify: `src/momentum_alpha/dashboard_assets_styles.py`
- Modify: `tests/test_dashboard.py`

- [ ] **Step 1: Write the failing layout test**

```python
def test_render_dashboard_html_shows_four_core_line_cards(self) -> None:
    from momentum_alpha.dashboard import render_dashboard_html

    snapshot = self._build_tabbed_snapshot()
    snapshot["recent_position_snapshots"] = [
        {
            "timestamp": "2026-04-17T00:45:00+00:00",
            "payload": {
                "positions": {
                    "BTCUSDT": {
                        "side": "LONG",
                        "legs": [
                            {"quantity": "1", "entry_price": "100", "stop_price": "90"},
                        ],
                    }
                }
            },
        }
    ]

    html = render_dashboard_html(snapshot, active_room="live")
    self.assertIn("CORE LIVE LINES", html)
    self.assertIn("Account Equity", html)
    self.assertIn("Margin Usage %", html)
    self.assertIn("Position Count", html)
    self.assertIn("Peak Risk", html)
    self.assertLess(html.index("Position Count"), html.index("Peak Risk"))
    self.assertIn("live-core-lines-grid", html)
    self.assertIn("live-core-line-card--peak-risk", html)
```

- [ ] **Step 2: Run the test and confirm the old 3-card layout fails**

Run: `python3 -m pytest tests/test_dashboard.py -k core_line -v`

Expected: failure because `Peak Risk` is not rendered yet and the live room still uses the 3-card grid.

- [ ] **Step 3: Update the live renderer and shell**

```python
# src/momentum_alpha/dashboard_render_shell.py
core_lines_html = _build_live_core_lines_panel(
    timeseries["account"],
    timeseries["position_risk"],
)
```

```python
# src/momentum_alpha/dashboard_render_panels.py
def _build_live_core_lines_panel(account_points: list[dict], peak_risk_points: list[dict]) -> str:
    chart_specs = (
        ("Account Equity", "equity", "#4cc9f0", account_points, ""),
        ("Margin Usage %", "margin_usage_pct", "#ff8c42", account_points, ""),
        ("Position Count", "position_count", "#36d98a", account_points, ""),
        ("Peak Risk", "peak_risk", "#ff5d73", peak_risk_points, "live-core-line-card--peak-risk"),
    )
    chart_cards = "".join(
        (
            f"<div class='chart-card live-core-line-card {card_class}'>"
            f"<div class='section-header'>{escape(label)}</div>"
            f"{_render_line_chart_svg(points=points, value_key=value_key, stroke=color, fill=color)}"
            "</div>"
        )
        for label, value_key, color, points, card_class in chart_specs
    )
    return (
        "<section class='dashboard-section live-core-lines-panel'>"
        "<div class='section-header'>CORE LIVE LINES</div>"
        "<div class='live-core-lines-grid'>"
        f"{chart_cards}"
        "</div>"
        "</section>"
    )
```

```css
/* src/momentum_alpha/dashboard_assets_styles.py */
.live-core-lines-grid {
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 16px;
}
.live-core-line-card--peak-risk {
  border-color: rgba(255, 93, 115, 0.24);
}
.live-core-line-card--peak-risk .section-header {
  color: var(--danger);
}
@media (max-width: 1200px) {
  .live-core-lines-grid {
    grid-template-columns: repeat(2, minmax(0, 1fr));
  }
}
@media (max-width: 768px) {
  .live-core-lines-grid {
    grid-template-columns: 1fr;
  }
}
```

- [ ] **Step 4: Run the dashboard tests again**

Run: `python3 -m pytest tests/test_dashboard.py -v`

Expected: the live-room assertions pass and the rest of the dashboard suite stays green.

- [ ] **Step 5: Commit**

```bash
git add src/momentum_alpha/dashboard_render_shell.py src/momentum_alpha/dashboard_render_panels.py src/momentum_alpha/dashboard_assets_styles.py tests/test_dashboard.py
git commit -m "feat: add peak risk to live core lines"
```

## Task 3: Full regression pass and handoff

**Files:**
- Test: `tests/test_dashboard_position_risk.py`
- Test: `tests/test_dashboard.py`
- Test: `tests/test_runtime_store.py`

- [ ] **Step 1: Run the focused new tests**

Run: `python3 -m pytest tests/test_dashboard_position_risk.py -v`

Expected: PASS.

- [ ] **Step 2: Run the dashboard suite**

Run: `python3 -m pytest tests/test_dashboard.py -v`

Expected: PASS, including the new `Peak Risk` card order and the 4-card grid.

- [ ] **Step 3: Run the runtime-store suite**

Run: `python3 -m pytest tests/test_runtime_store.py -v`

Expected: PASS, proving the position snapshot data path still loads cleanly.

- [ ] **Step 4: Review the rendered HTML once**

Open the live dashboard locally and confirm:

- `CORE LIVE LINES` reads as four equal cards on desktop.
- `Peak Risk` stays red-accented.
- The card collapses to 2x2 on tablet and stacked cards on mobile.

- [ ] **Step 5: Handoff**

No new commit is needed here if Task 2 already committed the code. If the verification exposed a regression, fix it in the relevant task and recommit before handoff.

## Coverage Check

- `CORE LIVE LINES` gets a new fourth card: Task 2.
- The chart uses the live snapshot stream: Task 1 and Task 2.
- The live position risk math is shared with the detail view: Task 1.
- Responsive layout stays intact: Task 2.
- The dashboard remains green under existing tests: Task 3.
