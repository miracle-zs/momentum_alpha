from __future__ import annotations

import json
from collections import Counter
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .health import build_runtime_health_report
from .runtime_store import (
    RuntimeStateStore,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_recent_account_flows,
    fetch_recent_audit_events,
    fetch_recent_account_snapshots,
    fetch_recent_algo_orders,
    fetch_recent_broker_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_recent_trade_round_trips,
)


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))

def _load_state_file(*, path: Path) -> tuple[dict, list[str]]:
    if not path.exists():
        return {}, [f"state file missing path={path}"]
    try:
        return json.loads(path.read_text(encoding="utf-8")), []
    except json.JSONDecodeError as exc:
        return {}, [f"state file invalid path={path} error={exc}"]


def _select_latest_timestamp(events: list[dict], event_type: str) -> str | None:
    for event in events:
        if event.get("event_type") == event_type:
            return event.get("timestamp")
    return None


def format_timestamp_for_display(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return str(timestamp)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M:%S")


def _load_recent_events(*, path: Path, recent_limit: int) -> tuple[list[dict], list[str]]:
    if not path.exists():
        return [], [f"audit file missing path={path}"]
    events: list[dict] = []
    warnings: list[str] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        try:
            events.append(json.loads(line))
        except json.JSONDecodeError as exc:
            warnings.append(f"audit file invalid path={path} line={line_number} error={exc}")
    sorted_events = sorted(events, key=lambda item: item.get("timestamp", ""), reverse=True)
    for event in sorted_events:
        event.setdefault("source", "audit-file")
    return sorted_events[:recent_limit], warnings


def _normalize_events(events: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for event in events:
        normalized.append(
            {
                "timestamp": event.get("timestamp"),
                "event_type": event.get("event_type"),
                "payload": event.get("payload") or {},
                "source": event.get("source") or "unknown",
            }
        )
    return normalized


def _build_source_counts(events: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(event.get("source") or "unknown" for event in events).items()))


def _build_leader_history(events: list[dict], limit: int = 8) -> list[dict]:
    leader_history: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if event.get("event_type") != "tick_result":
            continue
        payload = event.get("payload") or {}
        symbol = payload.get("next_previous_leader_symbol") or payload.get("previous_leader_symbol")
        if not symbol:
            continue
        key = (event.get("timestamp") or "", str(symbol))
        if key in seen:
            continue
        seen.add(key)
        leader_history.append({"timestamp": event.get("timestamp"), "symbol": str(symbol)})
        if len(leader_history) >= limit:
            break
    return leader_history


def _build_pulse_points(events: list[dict], *, now: datetime, minutes: int = 10) -> list[dict]:
    utc_now = now.astimezone(timezone.utc)
    buckets = []
    bucket_counts: Counter[str] = Counter()
    for offset in range(minutes - 1, -1, -1):
        bucket_dt = (utc_now - timedelta(minutes=offset)).replace(second=0, microsecond=0)
        bucket_key = bucket_dt.isoformat()
        buckets.append(bucket_key)
    bucket_set = set(buckets)
    for event in events:
        timestamp = event.get("timestamp")
        if not timestamp:
            continue
        bucket_key = datetime.fromisoformat(timestamp).astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
        if bucket_key in bucket_set:
            bucket_counts[bucket_key] += 1
    return [{"bucket": bucket, "event_count": bucket_counts.get(bucket, 0)} for bucket in buckets]


def _runtime_summary_from_sources(
    *,
    state_payload: dict,
    latest_account_snapshot: dict | None,
    latest_position_snapshot: dict | None,
    latest_signal_decision: dict | None,
) -> tuple[str | None, int, int]:
    if latest_position_snapshot is not None:
        return (
            latest_position_snapshot.get("leader_symbol"),
            int(latest_position_snapshot.get("position_count") or 0),
            int(latest_position_snapshot.get("order_status_count") or 0),
        )
    if latest_signal_decision is not None:
        return (
            latest_signal_decision.get("next_leader_symbol") or latest_signal_decision.get("symbol"),
            int(latest_signal_decision.get("position_count") or 0),
            int(latest_signal_decision.get("order_status_count") or 0),
        )
    if latest_account_snapshot is not None:
        return (
            latest_account_snapshot.get("leader_symbol"),
            int(latest_account_snapshot.get("position_count") or 0),
            len(state_payload.get("order_statuses") or {}),
        )
    positions = state_payload.get("positions") or {}
    order_statuses = state_payload.get("order_statuses") or {}
    return (
        state_payload.get("previous_leader_symbol"),
        len(positions),
        len(order_statuses),
    )


def _parse_numeric(value: object | None) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def build_position_details(position_snapshot: dict) -> list[dict]:
    """Extract position details with leg breakdown from position snapshot payload."""
    payload = position_snapshot.get("payload") or {}
    positions = payload.get("positions") or {}
    if not positions:
        return []

    details: list[dict] = []
    for symbol, position in positions.items():
        legs = position.get("legs") or []
        if not legs:
            continue

        total_quantity = Decimal("0")
        weighted_sum = Decimal("0")
        stop_price = _parse_decimal(position.get("stop_price")) or Decimal("0")
        leg_info: list[dict] = []

        for leg in legs:
            qty = _parse_decimal(leg.get("quantity")) or Decimal("0")
            entry = _parse_decimal(leg.get("entry_price")) or Decimal("0")
            total_quantity += qty
            weighted_sum += qty * entry
            leg_info.append({
                "type": leg.get("leg_type") or "unknown",
                "time": leg.get("opened_at") or "",
            })

        avg_entry = weighted_sum / total_quantity if total_quantity > 0 else Decimal("0")
        risk = total_quantity * (avg_entry - stop_price)

        details.append({
            "symbol": symbol,
            "direction": "LONG",
            "total_quantity": str(total_quantity),
            "entry_price": f"{avg_entry:.2f}",
            "stop_price": str(stop_price),
            "risk": f"{risk:.2f}",
            "legs": leg_info,
        })

    return details


def render_trade_history_table(fills: list[dict]) -> str:
    """Render HTML table for recent trade fills."""
    if not fills:
        return "<div class='trade-history-empty'>No trades</div>"

    rows = ""
    for fill in fills[:10]:
        timestamp = fill.get("timestamp") or ""
        time_str = timestamp[11:19] if len(timestamp) >= 19 else timestamp
        symbol = escape(str(fill.get("symbol") or "-"))
        side = fill.get("side") or "-"
        side_class = "side-buy" if side == "BUY" else "side-sell"
        qty = fill.get("quantity") or fill.get("cumulative_quantity") or "-"
        last_price = fill.get("last_price") or fill.get("average_price") or "-"
        commission = fill.get("commission") or "-"
        status = fill.get("order_status") or "-"
        status_class = "status-filled" if status == "FILLED" else "status-pending"

        rows += (
            f"<div class='trade-row'>"
            f"<span class='trade-time'>{escape(time_str)}</span>"
            f"<span class='trade-symbol'>{symbol}</span>"
            f"<span class='trade-side {side_class}'>{escape(side)}</span>"
            f"<span class='trade-qty'>{qty}</span>"
            f"<span class='trade-price'>{escape(str(last_price))}</span>"
            f"<span class='trade-commission'>{escape(str(commission))}</span>"
            f"<span class='trade-status {status_class}'>{escape(status)}</span>"
            f"</div>"
        )

    return f"<div class='trade-history'>{rows}</div>"


def render_closed_trades_table(round_trips: list[dict]) -> str:
    if not round_trips:
        return "<div class='trade-history-empty'>No closed trades</div>"

    rows = ""
    for trip in round_trips[:10]:
        symbol = escape(str(trip.get("symbol") or "-"))
        round_trip_id = escape(str(trip.get("round_trip_id") or "-"))
        opened_at = format_timestamp_for_display(trip.get("opened_at"))
        closed_at = format_timestamp_for_display(trip.get("closed_at"))
        net_pnl = escape(str(trip.get("net_pnl") or "-"))
        exit_reason = escape(str(trip.get("exit_reason") or "-"))
        pnl_class = "side-buy" if not str(net_pnl).startswith("-") else "side-sell"
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{symbol}</b> · {round_trip_id}</span>"
            f"<span>{escape(opened_at[11:19] if len(opened_at) >= 19 else opened_at)}</span>"
            f"<span>{escape(closed_at[11:19] if len(closed_at) >= 19 else closed_at)}</span>"
            f"<span>{exit_reason}</span>"
            f"<span class='{pnl_class}'>{net_pnl}</span>"
            f"</div>"
        )
    return f"<div class='analytics-table'>{rows}</div>"


def render_stop_slippage_table(stop_exits: list[dict]) -> str:
    if not stop_exits:
        return "<div class='trade-history-empty'>No stop exits</div>"

    rows = ""
    for item in stop_exits[:10]:
        symbol = escape(str(item.get("symbol") or "-"))
        trigger_price = escape(str(item.get("trigger_price") or "-"))
        average_exit_price = escape(str(item.get("average_exit_price") or "-"))
        slippage_pct = escape(str(item.get("slippage_pct") or "-"))
        net_pnl = escape(str(item.get("net_pnl") or "-"))
        pnl_class = "side-buy" if not str(net_pnl).startswith("-") else "side-sell"
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{symbol}</b></span>"
            f"<span>{trigger_price}</span>"
            f"<span>{average_exit_price}</span>"
            f"<span>{slippage_pct}%</span>"
            f"<span class='{pnl_class}'>{net_pnl}</span>"
            f"</div>"
        )
    return f"<div class='analytics-table'>{rows}</div>"


def build_strategy_config(
    *,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> dict:
    """Build strategy config dict for display."""
    return {
        "stop_budget_usdt": stop_budget_usdt or "n/a",
        "entry_window": f"{entry_start_hour_utc:02d}:00-{entry_end_hour_utc:02d}:00 UTC",
        "testnet": testnet,
        "submit_orders": submit_orders,
    }


def render_position_cards(positions: list[dict]) -> str:
    """Render HTML for position detail cards."""
    if not positions:
        return "<div class='positions-empty'>No positions</div>"

    cards = ""
    for pos in positions:
        symbol = escape(str(pos.get("symbol") or "-"))
        direction = escape(str(pos.get("direction") or "LONG"))
        qty = escape(str(pos.get("total_quantity") or "0"))
        entry = escape(str(pos.get("entry_price") or "n/a"))
        stop = escape(str(pos.get("stop_price") or "n/a"))
        risk = escape(str(pos.get("risk") or "0"))
        legs = pos.get("legs") or []

        legs_str = " | ".join(
            f"Leg {i+1}: {escape(str(leg.get('type') or '-'))} · {escape(str((leg.get('time') or '')[:10]))}"
            for i, leg in enumerate(legs)
        ) if legs else "No legs"

        cards += (
            f"<div class='position-card'>"
            f"<div class='position-header'>"
            f"<span class='position-symbol'>{symbol}</span>"
            f"<span class='position-direction'>{direction}</span>"
            f"</div>"
            f"<div class='position-metrics'>"
            f"<div class='position-metric'><span class='metric-label'>Qty</span><span class='metric-value'>{qty}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Entry</span><span class='metric-value'>{entry}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Stop</span><span class='metric-value metric-danger'>{stop}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Risk</span><span class='metric-value'>{risk} USDT</span></div>"
            f"</div>"
            f"<div class='position-legs'>{escape(legs_str)}</div>"
            f"</div>"
        )

    return f"<div class='positions-grid'>{cards}</div>"


def build_dashboard_summary_payload(snapshot: dict) -> dict:
    latest_account = snapshot.get("runtime", {}).get("latest_account_snapshot") or {}
    return {
        "health": snapshot.get("health", {}),
        "runtime": snapshot.get("runtime", {}),
        "account": {
            "wallet_balance": _parse_numeric(latest_account.get("wallet_balance")),
            "available_balance": _parse_numeric(latest_account.get("available_balance")),
            "equity": _parse_numeric(latest_account.get("equity")),
            "unrealized_pnl": _parse_numeric(latest_account.get("unrealized_pnl")),
            "position_count": latest_account.get("position_count"),
            "open_order_count": latest_account.get("open_order_count"),
        },
        "event_counts": snapshot.get("event_counts", {}),
        "source_counts": snapshot.get("source_counts", {}),
        "warnings": snapshot.get("warnings", []),
    }


def build_dashboard_timeseries_payload(snapshot: dict) -> dict:
    account_rows = sorted(snapshot.get("recent_account_snapshots", []), key=lambda item: item.get("timestamp") or "")
    return {
        "account": [
            {
                "timestamp": row.get("timestamp"),
                "wallet_balance": _parse_numeric(row.get("wallet_balance")),
                "available_balance": _parse_numeric(row.get("available_balance")),
                "equity": _parse_numeric(row.get("equity")),
                "unrealized_pnl": _parse_numeric(row.get("unrealized_pnl")),
                "position_count": row.get("position_count"),
                "open_order_count": row.get("open_order_count"),
                "leader_symbol": row.get("leader_symbol"),
            }
            for row in account_rows
        ],
        "pulse_points": snapshot.get("pulse_points", []),
        "leader_history": list(reversed(snapshot.get("leader_history", []))),
    }


def build_dashboard_tables_payload(snapshot: dict) -> dict:
    return {
        "recent_signal_decisions": snapshot.get("recent_signal_decisions", []),
        "recent_broker_orders": snapshot.get("recent_broker_orders", []),
        "recent_trade_fills": snapshot.get("recent_trade_fills", []),
        "recent_algo_orders": snapshot.get("recent_algo_orders", []),
        "recent_account_flows": snapshot.get("recent_account_flows", []),
        "recent_trade_round_trips": snapshot.get("recent_trade_round_trips", []),
        "recent_stop_exit_summaries": snapshot.get("recent_stop_exit_summaries", []),
        "recent_position_snapshots": snapshot.get("recent_position_snapshots", []),
        "recent_account_snapshots": snapshot.get("recent_account_snapshots", []),
        "recent_events": snapshot.get("recent_events", []),
    }


def load_dashboard_snapshot(
    *,
    now: datetime,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    runtime_db_file: Path | None = None,
    recent_limit: int = 20,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> dict:
    health_report = build_runtime_health_report(
        now=now,
        state_file=state_file,
        poll_log_file=poll_log_file,
        user_stream_log_file=user_stream_log_file,
        runtime_db_file=runtime_db_file,
        audit_log_file=audit_log_file,
    )
    state_payload, warnings = _load_state_file(path=state_file)
    recent_signal_decisions: list[dict] = []
    recent_broker_orders: list[dict] = []
    recent_trade_fills: list[dict] = []
    recent_algo_orders: list[dict] = []
    recent_account_flows: list[dict] = []
    recent_trade_round_trips: list[dict] = []
    recent_stop_exit_summaries: list[dict] = []
    recent_position_snapshots: list[dict] = []
    recent_account_snapshots: list[dict] = []
    if runtime_db_file is not None and runtime_db_file.exists():
        events_for_metrics = _normalize_events(fetch_recent_audit_events(path=runtime_db_file, limit=max(recent_limit, 300)))
        recent_signal_decisions = fetch_recent_signal_decisions(path=runtime_db_file, limit=8)
        recent_broker_orders = fetch_recent_broker_orders(path=runtime_db_file, limit=8)
        recent_trade_fills = fetch_recent_trade_fills(path=runtime_db_file, limit=20)
        recent_algo_orders = fetch_recent_algo_orders(path=runtime_db_file, limit=20)
        recent_account_flows = fetch_recent_account_flows(path=runtime_db_file, limit=20)
        recent_trade_round_trips = fetch_recent_trade_round_trips(path=runtime_db_file, limit=20)
        recent_stop_exit_summaries = fetch_recent_stop_exit_summaries(path=runtime_db_file, limit=20)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_account_snapshots = fetch_recent_account_snapshots(path=runtime_db_file, limit=30)
        if not state_payload:
            runtime_state = RuntimeStateStore(path=runtime_db_file).load()
            if runtime_state is not None:
                state_payload = {
                    "current_day": runtime_state.current_day,
                    "previous_leader_symbol": runtime_state.previous_leader_symbol,
                    "positions": runtime_state.positions or {},
                    "processed_event_ids": runtime_state.processed_event_ids or [],
                    "order_statuses": runtime_state.order_statuses or {},
                }
    else:
        events_for_metrics, audit_warnings = _load_recent_events(path=audit_log_file, recent_limit=max(recent_limit, 300))
        warnings.extend(audit_warnings)
        events_for_metrics = _normalize_events(events_for_metrics)
    recent_events = events_for_metrics[:recent_limit]
    event_counts = dict(sorted(Counter(event.get("event_type") for event in events_for_metrics if event.get("event_type")).items()))
    source_counts = _build_source_counts(events_for_metrics)
    if runtime_db_file is not None and runtime_db_file.exists():
        leader_history = fetch_leader_history(path=runtime_db_file, limit=8)
        if not leader_history:
            leader_history = _build_leader_history(events_for_metrics)
        pulse_points = fetch_event_pulse_points(path=runtime_db_file, now=now, since_minutes=10, bucket_minutes=1, limit=10)
        if not pulse_points:
            pulse_points = _build_pulse_points(events_for_metrics, now=now)
    else:
        leader_history = _build_leader_history(events_for_metrics)
        pulse_points = _build_pulse_points(events_for_metrics, now=now)
    latest_position_snapshot = recent_position_snapshots[0] if recent_position_snapshots else None
    latest_signal_decision = recent_signal_decisions[0] if recent_signal_decisions else None
    latest_broker_order = recent_broker_orders[0] if recent_broker_orders else None
    latest_account_snapshot = recent_account_snapshots[0] if recent_account_snapshots else None
    previous_leader_symbol, position_count, order_status_count = _runtime_summary_from_sources(
        state_payload=state_payload,
        latest_account_snapshot=latest_account_snapshot,
        latest_position_snapshot=latest_position_snapshot,
        latest_signal_decision=latest_signal_decision,
    )

    return {
        "health": {
            "overall_status": health_report.overall_status,
            "items": [
                {"name": item.name, "status": item.status, "message": item.message}
                for item in health_report.items
            ],
        },
        "runtime": {
            "previous_leader_symbol": previous_leader_symbol,
            "position_count": position_count,
            "order_status_count": order_status_count,
            "latest_tick_timestamp": _select_latest_timestamp(recent_events, "poll_tick"),
            "latest_tick_result_timestamp": _select_latest_timestamp(recent_events, "tick_result"),
            "latest_poll_worker_start_timestamp": _select_latest_timestamp(recent_events, "poll_worker_start"),
            "latest_user_stream_start_timestamp": _select_latest_timestamp(recent_events, "user_stream_worker_start"),
            "latest_signal_decision": latest_signal_decision,
            "latest_broker_order": latest_broker_order,
            "latest_position_snapshot": latest_position_snapshot,
            "latest_account_snapshot": latest_account_snapshot,
        },
        "event_counts": event_counts,
        "source_counts": source_counts,
        "leader_history": leader_history,
        "pulse_points": pulse_points,
        "recent_signal_decisions": recent_signal_decisions,
        "recent_broker_orders": recent_broker_orders,
        "recent_trade_fills": recent_trade_fills,
        "recent_algo_orders": recent_algo_orders,
        "recent_account_flows": recent_account_flows,
        "recent_trade_round_trips": recent_trade_round_trips,
        "recent_stop_exit_summaries": recent_stop_exit_summaries,
        "recent_position_snapshots": recent_position_snapshots,
        "recent_account_snapshots": recent_account_snapshots,
        "recent_events": recent_events,
        "warnings": warnings,
        "strategy_config": build_strategy_config(
            stop_budget_usdt=stop_budget_usdt,
            entry_start_hour_utc=entry_start_hour_utc,
            entry_end_hour_utc=entry_end_hour_utc,
            testnet=testnet,
            submit_orders=submit_orders,
        ),
    }


def build_dashboard_response_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _format_metric(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if signed:
        return f"{value:+,.2f}"
    return f"{value:,.2f}"


def _render_line_chart_svg(*, points: list[dict], value_key: str, stroke: str, fill: str, show_grid: bool = True) -> str:
    values = [point.get(value_key) for point in points if isinstance(point.get(value_key), (int, float))]
    if not values:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>waiting for data</span></div>"
    if len(values) == 1:
        values = [values[0], values[0]]
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1e-9)
    width = 600
    height = 200
    pad_x = 50
    pad_y = 20
    chart_width = width - pad_x * 2
    chart_height = height - pad_y * 2
    coordinates: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        x = pad_x + (chart_width * index / max(len(values) - 1, 1))
        y = pad_y + chart_height - (((value - min_value) / spread) * chart_height)
        coordinates.append((x, y))
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    area = " ".join([f"{coordinates[0][0]:.2f},{height - pad_y:.2f}", polyline, f"{coordinates[-1][0]:.2f},{height - pad_y:.2f}"])
    grid_lines = ""
    if show_grid:
        for i in range(5):
            y = pad_y + (chart_height * i / 4)
            grid_lines += f"<line x1='{pad_x}' y1='{y:.2f}' x2='{width - pad_x}' y2='{y:.2f}' class='grid-line'/>"
        for i in range(5):
            x = pad_x + (chart_width * i / 4)
            grid_lines += f"<line x1='{x:.2f}' y1='{pad_y}' x2='{x:.2f}' y2='{height - pad_y}' class='grid-line'/>"
    y_labels = ""
    for i in range(5):
        y = pad_y + (chart_height * i / 4)
        val = max_value - (spread * i / 4)
        y_labels += f"<text x='{pad_x - 8}' y='{y + 4:.2f}' class='axis-label' text-anchor='end'>{val:,.0f}</text>"
    dots = ""
    for x, y in coordinates[-3:]:
        dots += f"<circle cx='{x:.2f}' cy='{y:.2f}' r='4' fill='{stroke}' class='chart-dot'/>"
    return (
        f"<svg viewBox='0 0 {width} {height}' class='chart-svg' role='img' aria-label='{escape(value_key)} chart'>"
        f"<defs><linearGradient id='grad-{escape(value_key)}' x1='0%' y1='0%' x2='0%' y2='100%'>"
        f"<stop offset='0%' stop-color='{stroke}' stop-opacity='0.3'/><stop offset='100%' stop-color='{stroke}' stop-opacity='0.02'/></linearGradient></defs>"
        f"{grid_lines}{y_labels}"
        f"<polygon points='{area}' fill='url(#grad-{escape(value_key)})'></polygon>"
        f"<polyline points='{polyline}' fill='none' stroke='{stroke}' stroke-width='2.5' stroke-linecap='round' stroke-linejoin='round'></polyline>"
        f"{dots}"
        f"</svg>"
    )


def _render_pie_chart_svg(*, data: dict[str, int], colors: list[str] | None = None) -> str:
    if not data:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no data</span></div>"
    default_colors = ["#4cc9f0", "#36d98a", "#ffbc42", "#ff5d73", "#a855f7", "#ec4899", "#f97316", "#14b8a6"]
    colors = colors or default_colors
    total = sum(data.values())
    size = 160
    cx, cy = size / 2, size / 2
    r = size / 2 - 20
    paths = ""
    legend = ""
    start_angle = -90
    for i, (label, count) in enumerate(sorted(data.items(), key=lambda x: -x[1])):
        angle = (count / total) * 360
        end_angle = start_angle + angle
        x1 = cx + r * _cos_deg(start_angle)
        y1 = cy + r * _sin_deg(start_angle)
        x2 = cx + r * _cos_deg(end_angle)
        y2 = cy + r * _sin_deg(end_angle)
        large_arc = 1 if angle > 180 else 0
        color = colors[i % len(colors)]
        paths += f"<path d='M{cx},{cy} L{x1:.2f},{y1:.2f} A{r},{r} 0 {large_arc},1 {x2:.2f},{y2:.2f} Z' fill='{color}' class='pie-slice'/>"
        legend += f"<div class='legend-item'><span class='legend-color' style='background:{color}'></span><span class='legend-label'>{escape(label)}</span><span class='legend-value'>{count}</span></div>"
        start_angle = end_angle
    return f"<div class='pie-container'><svg viewBox='0 0 {size} {size}' class='pie-svg'>{paths}</svg><div class='pie-legend'>{legend}</div></div>"


def _cos_deg(angle: float) -> float:
    import math
    return math.cos(math.radians(angle))


def _sin_deg(angle: float) -> float:
    import math
    return math.sin(math.radians(angle))


def _render_bar_chart_svg(*, data: dict[str, int], color: str = "#4cc9f0") -> str:
    if not data:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no data</span></div>"
    width = 400
    height = 180
    pad_x = 60
    pad_y = 20
    bar_width = max(20, (width - pad_x * 2) / len(data) - 8)
    max_val = max(data.values())
    bars = ""
    labels = ""
    for i, (label, val) in enumerate(sorted(data.items())):
        x = pad_x + i * (bar_width + 8)
        bar_height = (val / max_val) * (height - pad_y * 2 - 20) if max_val > 0 else 0
        y = height - pad_y - bar_height
        bars += f"<rect x='{x:.2f}' y='{y:.2f}' width='{bar_width:.2f}' height='{bar_height:.2f}' fill='{color}' rx='4' class='bar-rect'/>"
        bars += f"<text x='{x + bar_width/2:.2f}' y='{y - 6:.2f}' class='bar-value' text-anchor='middle'>{val}</text>"
        short_label = label[:10] + "..." if len(label) > 10 else label
        labels += f"<text x='{x + bar_width/2:.2f}' y='{height - 6:.2f}' class='bar-label' text-anchor='middle' transform='rotate(-30 {x + bar_width/2:.2f},{height - 6:.2f})'>{escape(short_label)}</text>"
    return f"<svg viewBox='0 0 {width} {height}' class='bar-svg'>{bars}{labels}</svg>"


def _render_timeline_svg(*, events: list[dict]) -> str:
    if not events:
        return "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>no events</span></div>"
    width = 600
    height = 120
    pad = 40
    line_y = height / 2
    timeline = f"<line x1='{pad}' y1='{line_y}' x2='{width - pad}' y2='{line_y}' class='timeline-line'/>"
    step = (width - pad * 2) / max(len(events) - 1, 1)
    for i, event in enumerate(events[:10]):
        x = pad + i * step
        symbol = event.get("symbol", "?")
        timestamp = event.get("timestamp", "")
        is_current = i == len(events[:10]) - 1
        color = "#4cc9f0" if is_current else "#36d98a" if i % 2 == 0 else "#ffbc42"
        radius = 12 if is_current else 8
        timeline += f"<circle cx='{x:.2f}' cy='{line_y:.2f}' r='{radius}' fill='{color}' class='timeline-dot{' current' if is_current else ''}'/>"
        timeline += f"<text x='{x:.2f}' y='{line_y - 22:.2f}' class='timeline-label' text-anchor='middle'>{escape(str(symbol))}</text>"
        if timestamp:
            formatted_time = format_timestamp_for_display(timestamp)
            short_time = formatted_time[11:16] if len(formatted_time) >= 16 else formatted_time[-5:]
            timeline += f"<text x='{x:.2f}' y='{line_y + 28:.2f}' class='timeline-time' text-anchor='middle'>{escape(short_time)}</text>"
    return f"<svg viewBox='0 0 {width} {height}' class='timeline-svg'>{timeline}</svg>"


def render_dashboard_html(snapshot: dict, strategy_config: dict | None = None) -> str:
    summary = build_dashboard_summary_payload(snapshot)
    timeseries = build_dashboard_timeseries_payload(snapshot)
    runtime = snapshot["runtime"]
    latest_signal = runtime.get("latest_signal_decision") or {}
    latest_broker_order = runtime.get("latest_broker_order") or {}
    latest_position_snapshot = runtime.get("latest_position_snapshot") or {}
    latest_account_snapshot = runtime.get("latest_account_snapshot") or {}
    latest_signal_payload = latest_signal.get("payload") or {}
    blocked_reason = latest_signal_payload.get("blocked_reason")
    decision_status = latest_signal.get("decision_type") or "none"
    latest_signal_symbol = latest_signal.get("symbol") or "none"
    latest_signal_time = format_timestamp_for_display(latest_signal.get("timestamp"))
    wallet_balance = _format_metric(summary["account"].get("wallet_balance"))
    available_balance = _format_metric(summary["account"].get("available_balance"))
    equity = _format_metric(summary["account"].get("equity"))
    unrealized_pnl = _format_metric(summary["account"].get("unrealized_pnl"), signed=True)
    pnl_positive = not str(unrealized_pnl).startswith("-")
    equity_chart = _render_line_chart_svg(points=timeseries["account"], value_key="equity", stroke="#4cc9f0", fill="rgba(76,201,240,0.14)")
    wallet_chart = _render_line_chart_svg(points=timeseries["account"], value_key="wallet_balance", stroke="#36d98a", fill="rgba(54,217,138,0.14)")
    pnl_chart = _render_line_chart_svg(points=timeseries["account"], value_key="unrealized_pnl", stroke="#a855f7", fill="rgba(168,85,247,0.14)", show_grid=False)
    event_counts = snapshot.get("event_counts", {})
    decision_counts = {k: v for k, v in event_counts.items() if "decision" in k.lower() or "entry" in k.lower() or "signal" in k.lower()} or event_counts
    pie_chart = _render_pie_chart_svg(data=decision_counts)
    bar_chart = _render_bar_chart_svg(data=dict(list(event_counts.items())[:6]), color="#4cc9f0")
    leader_history = list(reversed(snapshot.get("leader_history", [])))
    timeline_chart = _render_timeline_svg(events=leader_history)
    health_status = snapshot["health"]["overall_status"]
    # Build position cards
    position_details = build_position_details(latest_position_snapshot)
    position_cards_html = render_position_cards(position_details)
    # Build trade history
    trade_fills = snapshot.get("recent_trade_fills") or []
    trade_history_html = render_trade_history_table(trade_fills)
    closed_trades_html = render_closed_trades_table(snapshot.get("recent_trade_round_trips") or [])
    stop_slippage_html = render_stop_slippage_table(snapshot.get("recent_stop_exit_summaries") or [])
    # Build strategy config
    config = strategy_config or {}
    config_html = (
        f"<div class='config-panel'>"
        f"<div class='config-row'><span class='config-label'>Stop Budget</span><span>{escape(str(config.get('stop_budget_usdt') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Entry Window</span><span>{escape(str(config.get('entry_window') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Testnet</span><span class='{'config-value-true' if config.get('testnet') else 'config-value-false'}'>{'Yes' if config.get('testnet') else 'No'}</span></div>"
        f"</div>"
    )
    health_items_html = "".join(
        f"<div class='health-item status-{escape(item['status'].lower())}'>"
        f"<span class='health-status-dot'></span>"
        f"<span class='health-name'>{escape(item['name'])}</span>"
        f"<span class='health-status'>{escape(item['status'])}</span>"
        f"<span class='health-msg'>{escape(item['message'])}</span></div>"
        for item in snapshot["health"]["items"]
    )
    warnings_html = "".join(f"<li>{escape(w)}</li>" for w in snapshot["warnings"]) or "<li class='no-warning'>No warnings</li>"
    recent_events_html = "".join(
        f"<div class='event-item'>"
        f"<span class='event-type'>{escape(e['event_type'])}</span>"
        f"<span class='event-time'>{escape(format_timestamp_for_display(e['timestamp']))}</span>"
        f"<span class='event-source'>{escape(str(e.get('source') or '-'))}</span></div>"
        for e in snapshot["recent_events"][:12]
    ) or "<div class='event-item empty'>No recent events</div>"
    signal_rows_html = "".join(
        f"<div class='data-row'><span class='row-main'>{escape(str(item.get('decision_type')))} · {escape(str(item.get('symbol')))}</span><span class='row-time'>{escape(format_timestamp_for_display(item.get('timestamp')))}</span></div>"
        for item in snapshot.get("recent_signal_decisions", [])[:5]
    ) or "<div class='data-row empty'>No signals</div>"
    broker_rows_html = "".join(
        f"<div class='data-row'><span class='row-main'>{escape(str(item.get('action_type')))} · {escape(str(item.get('symbol')))}</span><span class='row-time'>{escape(format_timestamp_for_display(item.get('timestamp')))}</span></div>"
        for item in snapshot.get("recent_broker_orders", [])[:5]
    ) or "<div class='data-row empty'>No orders</div>"
    account_rows_html = "".join(
        f"<div class='data-row'><span class='row-main'>{escape(str(item.get('leader_symbol') or '-'))} · Equity: {escape(_format_metric(_parse_numeric(item.get('equity'))))}</span><span class='row-time'>{escape(format_timestamp_for_display(item.get('timestamp')))}</span></div>"
        for item in snapshot.get("recent_account_snapshots", [])[:5]
    ) or "<div class='data-row empty'>No snapshots</div>"
    pulse_points = snapshot.get("pulse_points", [])
    pulse_max = max((p["event_count"] for p in pulse_points), default=1)
    pulse_html = "".join(
        f"<div class='pulse-col'><div class='pulse-bar' style='height:{max(12, int(100 * p["event_count"] / pulse_max))}%;'></div><span class='pulse-label'>{escape(format_timestamp_for_display(p['bucket'])[11:16])}</span></div>"
        for p in pulse_points
    ) or "<div class='pulse-col empty'><div class='pulse-bar' style='height:12%;'></div><span>n/a</span></div>"
    source_counts = snapshot.get("source_counts", {})
    source_html = "".join(
        f"<div class='source-tag'><span>{escape(src)}</span><b>{cnt}</b></div>"
        for src, cnt in sorted(source_counts.items())[:4]
    ) or "<div class='source-tag empty'>No sources</div>"

    return f"""<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha | 交易监控面板</title>
  <style>
    :root {{
      --bg-deep: #060a10;
      --bg: #0c1018;
      --bg-panel: linear-gradient(145deg, rgba(16,24,40,0.95), rgba(10,16,28,0.98));
      --bg-card: rgba(18,28,45,0.8);
      --fg: #e4eaf2;
      --fg-muted: #6b7d95;
      --accent: #00d4ff;
      --accent-glow: rgba(0,212,255,0.25);
      --success: #00ff88;
      --success-bg: rgba(0,255,136,0.1);
      --warning: #ffb800;
      --danger: #ff4466;
      --danger-bg: rgba(255,68,102,0.1);
      --border: rgba(100,130,170,0.15);
      --border-accent: rgba(0,212,255,0.3);
      --shadow: 0 8px 32px rgba(0,0,0,0.4);
      --radius: 16px;
      --radius-sm: 8px;
    }}
    * {{ margin: 0; padding: 0; box-sizing: border-box; }}
    body {{
      font-family: 'SF Mono', 'JetBrains Mono', 'Fira Code', 'Menlo', monospace;
      background: var(--bg-deep);
      color: var(--fg);
      min-height: 100vh;
      line-height: 1.5;
    }}
    .app {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px;
    }}
    .header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 28px;
      padding-bottom: 20px;
      border-bottom: 1px solid var(--border);
    }}
    .header-left {{
      display: flex;
      align-items: center;
      gap: 16px;
    }}
    .logo {{
      width: 48px;
      height: 48px;
      background: linear-gradient(135deg, var(--accent), #0088cc);
      border-radius: 12px;
      display: flex;
      align-items: center;
      justify-content: center;
      font-size: 24px;
      font-weight: 700;
      box-shadow: 0 4px 20px var(--accent-glow);
    }}
    .title-group h1 {{
      font-size: 1.5rem;
      font-weight: 700;
      letter-spacing: 0.02em;
      background: linear-gradient(90deg, var(--fg), var(--accent));
      -webkit-background-clip: text;
      -webkit-text-fill-color: transparent;
      background-clip: text;
    }}
    .title-group p {{
      font-size: 0.8rem;
      color: var(--fg-muted);
      margin-top: 2px;
    }}
    .status-badge {{
      padding: 10px 20px;
      border-radius: 100px;
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      border: 1px solid;
    }}
    .status-badge.ok {{
      background: var(--success-bg);
      color: var(--success);
      border-color: rgba(0,255,136,0.3);
    }}
    .status-badge.fail {{
      background: var(--danger-bg);
      color: var(--danger);
      border-color: rgba(255,68,102,0.3);
      animation: pulse-danger 2s infinite;
    }}
    @keyframes pulse-danger {{
      0%, 100% {{ box-shadow: 0 0 0 0 rgba(255,68,102,0.4); }}
      50% {{ box-shadow: 0 0 0 10px rgba(255,68,102,0); }}
    }}
    .metrics-grid {{
      display: grid;
      grid-template-columns: repeat(4, 1fr);
      gap: 16px;
      margin-bottom: 24px;
    }}
    .metric {{
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
      position: relative;
      overflow: hidden;
      transition: transform 0.2s, box-shadow 0.2s;
    }}
    .metric:hover {{
      transform: translateY(-2px);
      box-shadow: var(--shadow);
    }}
    .metric::before {{
      content: '';
      position: absolute;
      top: 0;
      left: 0;
      right: 0;
      height: 3px;
      background: linear-gradient(90deg, var(--accent), transparent);
    }}
    .metric-label {{
      font-size: 0.72rem;
      color: var(--fg-muted);
      text-transform: uppercase;
      letter-spacing: 0.12em;
      margin-bottom: 8px;
    }}
    .metric-value {{
      font-size: 1.6rem;
      font-weight: 700;
      color: var(--fg);
    }}
    .metric-value.positive {{ color: var(--success); }}
    .metric-value.negative {{ color: var(--danger); }}
    .metric-sub {{
      font-size: 0.75rem;
      color: var(--fg-muted);
      margin-top: 6px;
    }}
    .main-layout {{
      display: grid;
      grid-template-columns: 1fr 380px;
      gap: 20px;
    }}
    .left-panel, .right-panel {{
      display: flex;
      flex-direction: column;
      gap: 20px;
    }}
    .card {{
      background: var(--bg-panel);
      border: 1px solid var(--border);
      border-radius: var(--radius);
      padding: 20px;
    }}
    .card-header {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      margin-bottom: 16px;
      padding-bottom: 12px;
      border-bottom: 1px solid var(--border);
    }}
    .card-title {{
      font-size: 0.85rem;
      font-weight: 600;
      text-transform: uppercase;
      letter-spacing: 0.08em;
      color: var(--fg-muted);
    }}
    .card-title::before {{
      content: '■';
      margin-right: 8px;
      color: var(--accent);
    }}
    .chart-container {{
      background: rgba(0,0,0,0.2);
      border-radius: var(--radius-sm);
      padding: 12px;
      margin-top: 8px;
    }}
    .chart-svg, .bar-svg, .timeline-svg, .pie-svg {{
      width: 100%;
      height: auto;
      display: block;
    }}
    .chart-svg .grid-line {{ stroke: rgba(100,130,170,0.1); stroke-width: 1; }}
    .chart-svg .axis-label {{ font-size: 9px; fill: var(--fg-muted); }}
    .chart-svg .chart-dot {{ filter: drop-shadow(0 0 4px currentColor); }}
    .chart-empty {{
      display: flex;
      flex-direction: column;
      align-items: center;
      justify-content: center;
      min-height: 160px;
      color: var(--fg-muted);
      font-size: 0.85rem;
      gap: 8px;
    }}
    .chart-empty-icon {{ font-size: 2rem; opacity: 0.3; }}
    .pie-container {{ display: flex; align-items: center; gap: 20px; }}
    .pie-svg {{ width: 140px; height: 140px; flex-shrink: 0; }}
    .pie-slice {{ transition: transform 0.2s; transform-origin: center; }}
    .pie-slice:hover {{ transform: scale(1.05); }}
    .pie-legend {{ display: flex; flex-direction: column; gap: 6px; font-size: 0.75rem; }}
    .legend-item {{ display: flex; align-items: center; gap: 8px; }}
    .legend-color {{ width: 10px; height: 10px; border-radius: 2px; flex-shrink: 0; }}
    .legend-label {{ color: var(--fg-muted); flex: 1; }}
    .legend-value {{ font-weight: 600; }}
    .bar-svg .bar-rect {{ transition: opacity 0.2s; }}
    .bar-svg .bar-rect:hover {{ opacity: 0.8; }}
    .bar-svg .bar-value {{ font-size: 9px; fill: var(--fg); font-weight: 600; }}
    .bar-svg .bar-label {{ font-size: 8px; fill: var(--fg-muted); }}
    .timeline-svg .timeline-line {{ stroke: var(--border); stroke-width: 2; stroke-dasharray: 4 4; }}
    .timeline-svg .timeline-dot {{ filter: drop-shadow(0 0 6px currentColor); transition: r 0.2s; }}
    .timeline-svg .timeline-dot.current {{ animation: pulse-dot 1.5s infinite; }}
    @keyframes pulse-dot {{
      0%, 100% {{ r: 12; }}
      50% {{ r: 16; }}
    }}
    .timeline-svg .timeline-label {{ font-size: 10px; fill: var(--fg); font-weight: 600; }}
    .timeline-svg .timeline-time {{ font-size: 8px; fill: var(--fg-muted); }}
    .health-grid {{ display: flex; flex-direction: column; gap: 10px; }}
    .health-item {{
      display: grid;
      grid-template-columns: 8px 1fr 80px 1fr;
      gap: 12px;
      align-items: center;
      padding: 12px 14px;
      background: rgba(0,0,0,0.2);
      border-radius: var(--radius-sm);
      border-left: 3px solid transparent;
    }}
    .health-item.status-ok {{ border-left-color: var(--success); }}
    .health-item.status-fail {{ border-left-color: var(--danger); }}
    .health-status-dot {{
      width: 8px;
      height: 8px;
      border-radius: 50%;
      background: var(--fg-muted);
    }}
    .status-ok .health-status-dot {{ background: var(--success); box-shadow: 0 0 8px var(--success); }}
    .status-fail .health-status-dot {{ background: var(--danger); box-shadow: 0 0 8px var(--danger); }}
    .health-name {{ font-size: 0.8rem; font-weight: 500; }}
    .health-status {{ font-size: 0.72rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .status-ok .health-status {{ color: var(--success); }}
    .status-fail .health-status {{ color: var(--danger); }}
    .health-msg {{ font-size: 0.75rem; color: var(--fg-muted); }}
    .decision-grid {{
      display: grid;
      grid-template-columns: repeat(2, 1fr);
      gap: 12px;
    }}
    .decision-item {{
      background: rgba(0,0,0,0.25);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
      padding: 14px;
    }}
    .decision-label {{
      font-size: 0.68rem;
      color: var(--fg-muted);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 6px;
    }}
    .decision-value {{
      font-size: 1rem;
      font-weight: 600;
      word-break: break-word;
    }}
    .pulse-container {{
      display: flex;
      align-items: flex-end;
      justify-content: space-between;
      height: 140px;
      padding: 16px 0;
      gap: 4px;
    }}
    .pulse-col {{
      flex: 1;
      display: flex;
      flex-direction: column;
      align-items: center;
      height: 100%;
      justify-content: flex-end;
    }}
    .pulse-bar {{
      width: 100%;
      max-width: 28px;
      background: linear-gradient(180deg, var(--accent), #0066aa);
      border-radius: 4px 4px 0 0;
      min-height: 12px;
      transition: height 0.3s;
    }}
    .pulse-label {{
      font-size: 0.65rem;
      color: var(--fg-muted);
      margin-top: 6px;
    }}
    .data-list {{ display: flex; flex-direction: column; gap: 8px; }}
    .data-row {{
      display: flex;
      justify-content: space-between;
      align-items: center;
      padding: 10px 12px;
      background: rgba(0,0,0,0.2);
      border-radius: var(--radius-sm);
      font-size: 0.8rem;
      border-left: 2px solid var(--accent);
    }}
    .data-row.empty {{ border-left-color: var(--border); color: var(--fg-muted); }}
    .row-main {{ flex: 1; }}
    .row-time {{ color: var(--fg-muted); font-size: 0.72rem; }}
    .source-tags {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .source-tag {{
      display: flex;
      align-items: center;
      gap: 8px;
      padding: 8px 12px;
      background: rgba(0,212,255,0.08);
      border: 1px solid rgba(0,212,255,0.2);
      border-radius: 100px;
      font-size: 0.75rem;
    }}
    .source-tag span {{ color: var(--fg-muted); }}
    .source-tag b {{ color: var(--accent); }}
    .event-list {{ max-height: 320px; overflow-y: auto; }}
    .event-item {{
      display: grid;
      grid-template-columns: 1fr 130px 80px;
      gap: 12px;
      padding: 10px 0;
      border-bottom: 1px solid var(--border);
      font-size: 0.78rem;
    }}
    .event-item:last-child {{ border-bottom: none; }}
    .event-item.empty {{ color: var(--fg-muted); }}
    .event-type {{ font-weight: 500; color: var(--accent); }}
    .event-time, .event-source {{ color: var(--fg-muted); font-size: 0.72rem; }}
    .warnings-list {{ list-style: none; }}
    .warnings-list li {{
      padding: 10px 12px;
      background: rgba(255,184,0,0.1);
      border-left: 3px solid var(--warning);
      border-radius: 0 var(--radius-sm) var(--radius-sm) 0;
      margin-bottom: 8px;
      font-size: 0.8rem;
      color: var(--warning);
    }}
    .warnings-list li.no-warning {{
      background: rgba(0,255,136,0.05);
      border-left-color: var(--success);
      color: var(--success);
    }}
    .json-view {{
      background: rgba(0,0,0,0.3);
      border-radius: var(--radius-sm);
      padding: 14px;
      font-size: 0.72rem;
      color: #8be9fd;
      overflow-x: auto;
      max-height: 200px;
      white-space: pre-wrap;
      word-break: break-all;
    }}
    .refresh-indicator {{
      position: fixed;
      bottom: 20px;
      right: 20px;
      padding: 10px 16px;
      background: var(--bg-card);
      border: 1px solid var(--border);
      border-radius: 100px;
      font-size: 0.75rem;
      color: var(--fg-muted);
      display: flex;
      align-items: center;
      gap: 8px;
    }}
    .refresh-dot {{
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      animation: blink 1s infinite;
    }}
    @keyframes blink {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.3; }}
    }}
    .positions-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    .position-card {{ background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border-left: 3px solid var(--success); }}
    .position-header {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
    .position-symbol {{ font-weight: 700; color: var(--accent); }}
    .position-direction {{ font-size: 0.75rem; color: var(--fg-muted); }}
    .position-metrics {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 8px; font-size: 0.8rem; }}
    .position-metric {{ text-align: center; }}
    .metric-danger {{ color: var(--danger); }}
    .position-legs {{ margin-top: 8px; font-size: 0.7rem; color: var(--fg-muted); }}
    .positions-empty {{ color: var(--fg-muted); text-align: center; padding: 20px; }}
    .trade-history {{ max-height: 200px; overflow-y: auto; }}
    .trade-history-empty {{ color: var(--fg-muted); text-align: center; padding: 20px; }}
    .trade-row {{ display: grid; grid-template-columns: 80px 120px 60px 80px 100px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }}
    .trade-row:last-child {{ border-bottom: none; }}
    .analytics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .analytics-table {{ max-height: 220px; overflow-y: auto; }}
    .analytics-row {{ display: grid; grid-template-columns: 1.4fr 0.8fr 0.8fr 0.8fr 0.7fr; gap: 8px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; align-items: center; }}
    .analytics-row:last-child {{ border-bottom: none; }}
    .analytics-main {{ color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .trade-time {{ color: var(--fg-muted); }}
    .trade-symbol {{ color: var(--accent); font-weight: 500; }}
    .side-buy {{ color: var(--success); }}
    .side-sell {{ color: var(--danger); }}
    .status-filled {{ color: var(--success); }}
    .status-pending {{ color: var(--warning); }}
    .section-header {{ font-size: 0.7rem; color: var(--accent); padding: 4px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.1em; }}
    .config-panel {{ background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; font-size: 0.8rem; }}
    .config-row {{ display: flex; justify-content: space-between; padding: 4px 0; }}
    .config-label {{ color: var(--fg-muted); }}
    .config-value-true {{ color: var(--warning); }}
    .config-value-false {{ color: var(--fg-muted); }}
    .dashboard-section {{ margin-bottom: 20px; padding: 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); }}
    .charts-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .chart-card {{ background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }}
    .decision-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .decision-half {{ background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }}
    .bottom-row {{ display: grid; grid-template-columns: 200px 1fr 1fr; gap: 16px; }}
    .bottom-col {{ }}
    @media (max-width: 1200px) {{
      .main-layout {{ grid-template-columns: 1fr; }}
      .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .charts-row {{ grid-template-columns: 1fr; }}
      .decision-row {{ grid-template-columns: 1fr; }}
      .bottom-row {{ grid-template-columns: 1fr; }}
    }}
    @media (max-width: 768px) {{
      .metrics-grid {{ grid-template-columns: 1fr; }}
      .header {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
      .decision-grid {{ grid-template-columns: 1fr; }}
      .positions-grid {{ grid-template-columns: 1fr; }}
      .trade-row {{ grid-template-columns: 60px 80px 50px 60px 70px 60px 60px; font-size: 0.7rem; }}
      .analytics-grid {{ grid-template-columns: 1fr; }}
      .analytics-row {{ grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr; font-size: 0.68rem; }}
    }}
  </style>
</head>
<body>
  <div class="app">
    <header class="header">
      <div class="header-left">
        <div class="logo">M</div>
        <div class="title-group">
          <h1>Momentum Alpha</h1>
          <p>Leader Rotation Strategy · Real-time Trading Monitor</p>
        </div>
      </div>
      <div class="status-badge {'ok' if health_status == 'OK' else 'fail'}">{escape(health_status)}</div>
    </header>
    <div class="metrics-grid">
      <div class="metric">
        <div class="metric-label">Current Leader</div>
        <div class="metric-value">{escape(str(runtime['previous_leader_symbol'] or '-'))}</div>
        <div class="metric-sub">Highest daily gain symbol</div>
      </div>
      <div class="metric">
        <div class="metric-label">Positions</div>
        <div class="metric-value">{runtime['position_count']}</div>
        <div class="metric-sub">{runtime['order_status_count']} tracked orders</div>
      </div>
      <div class="metric">
        <div class="metric-label">Wallet Balance</div>
        <div class="metric-value">{escape(wallet_balance)}</div>
        <div class="metric-sub">USDT futures wallet</div>
      </div>
      <div class="metric">
        <div class="metric-label">Unrealized PnL</div>
        <div class="metric-value {'positive' if pnl_positive else 'negative'}">{escape(unrealized_pnl)}</div>
        <div class="metric-sub">Mark-to-market</div>
      </div>
    </div>
    <section class="dashboard-section">
      <div class="section-header">POSITIONS</div>
      {position_cards_html}
    </section>
    <section class="dashboard-section">
      <div class="section-header">ACCOUNT METRICS</div>
      <div class="charts-row">
        <div class="chart-card">
          <div style="font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;">Equity Curve</div>
          {equity_chart}
        </div>
        <div class="chart-card">
          <div style="font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;">Wallet Balance</div>
          {wallet_chart}
        </div>
        <div class="chart-card">
          <div style="font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;">Unrealized PnL</div>
          {pnl_chart}
        </div>
      </div>
    </section>
    <section class="dashboard-section decision-row">
      <div class="decision-half">
        <div class="section-header">LATEST DECISION</div>
        <div class="decision-grid">
          <div class="decision-item">
            <div class="decision-label">Decision Type</div>
            <div class="decision-value">{escape(str(decision_status))}</div>
          </div>
          <div class="decision-item">
            <div class="decision-label">Target Symbol</div>
            <div class="decision-value">{escape(str(latest_signal_symbol))}</div>
          </div>
          <div class="decision-item">
            <div class="decision-label">Blocked Reason</div>
            <div class="decision-value">{escape(str(blocked_reason or 'None'))}</div>
          </div>
          <div class="decision-item">
            <div class="decision-label">Decision Time</div>
            <div class="decision-value">{escape(latest_signal_time)}</div>
          </div>
        </div>
      </div>
      <div class="decision-half">
        <div class="section-header">LEADER ROTATION</div>
        <div class="chart-container">{timeline_chart}</div>
      </div>
    </section>
    <section class="dashboard-section">
      <div class="section-header">TRADE HISTORY</div>
      {trade_history_html}
    </section>
    <section class="dashboard-section">
      <div class="section-header">CLOSED TRADES</div>
      <div class="analytics-grid">
        <div class="chart-card">
          <div style="font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;">Round Trips</div>
          {closed_trades_html}
        </div>
        <div class="chart-card">
          <div class="section-header" style="margin-bottom:10px;">STOP SLIPPAGE ANALYSIS</div>
          {stop_slippage_html}
        </div>
      </div>
    </section>
    <section class="dashboard-section bottom-row">
      <div class="bottom-col">
        <div class="section-header">STRATEGY CONFIG</div>
        {config_html}
      </div>
      <div class="bottom-col">
        <div class="section-header">SYSTEM HEALTH</div>
        <div class="health-grid">{health_items_html}</div>
      </div>
      <div class="bottom-col">
        <div class="section-header">RECENT EVENTS</div>
        <div class="event-list" style="max-height:200px;overflow-y:auto;">{recent_events_html}</div>
      </div>
    </section>
  </div>
  <div class="refresh-indicator">
    <div class="refresh-dot"></div>
    <span>Auto refresh: 5s</span>
  </div>
  <script>
    async function refreshDashboard() {{
      try {{
        const res = await fetch('/api/dashboard', {{ cache: 'no-store' }});
        if (!res.ok) return;
        const data = await res.json();
        document.title = `Momentum Alpha | ${{data.health.overall_status}}`;
        window.location.reload();
      }} catch (e) {{ console.error(e); }}
    }}
    setInterval(refreshDashboard, 5000);
  </script>
</body>
</html>"""


def run_dashboard_server(
    *,
    host: str,
    port: int,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    runtime_db_file: Path | None = None,
    now_provider=None,
    server_factory=ThreadingHTTPServer,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
) -> int:
    now_provider = now_provider or datetime.now

    class DashboardHandler(BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            snapshot = load_dashboard_snapshot(
                now=now_provider().astimezone(),
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                runtime_db_file=runtime_db_file,
                stop_budget_usdt=stop_budget_usdt,
                entry_start_hour_utc=entry_start_hour_utc,
                entry_end_hour_utc=entry_end_hour_utc,
                testnet=testnet,
                submit_orders=submit_orders,
            )
            if self.path in {"/api/dashboard", "/api/dashboard/summary", "/api/dashboard/timeseries", "/api/dashboard/tables"}:
                if self.path == "/api/dashboard/summary":
                    payload = build_dashboard_summary_payload(snapshot)
                elif self.path == "/api/dashboard/timeseries":
                    payload = build_dashboard_timeseries_payload(snapshot)
                elif self.path == "/api/dashboard/tables":
                    payload = build_dashboard_tables_payload(snapshot)
                else:
                    payload = snapshot
                body = build_dashboard_response_json(payload).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            if self.path == "/":
                body = render_dashboard_html(snapshot).encode("utf-8")
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)
                return
            self.send_response(404)
            self.end_headers()

        def log_message(self, format, *args):  # noqa: A003
            return

    with server_factory((host, port), DashboardHandler) as server:
        server.serve_forever()
    return 0
