from __future__ import annotations

import json
from collections import Counter
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path

from .health import build_runtime_health_report
from .runtime_store import (
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_recent_audit_events,
    fetch_recent_account_snapshots,
    fetch_recent_broker_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
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
    recent_position_snapshots: list[dict] = []
    recent_account_snapshots: list[dict] = []
    if runtime_db_file is not None and runtime_db_file.exists():
        events_for_metrics = _normalize_events(fetch_recent_audit_events(path=runtime_db_file, limit=max(recent_limit, 300)))
        recent_signal_decisions = fetch_recent_signal_decisions(path=runtime_db_file, limit=8)
        recent_broker_orders = fetch_recent_broker_orders(path=runtime_db_file, limit=8)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_account_snapshots = fetch_recent_account_snapshots(path=runtime_db_file, limit=30)
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
        "recent_position_snapshots": recent_position_snapshots,
        "recent_account_snapshots": recent_account_snapshots,
        "recent_events": recent_events,
        "warnings": warnings,
    }


def build_dashboard_response_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)


def _format_metric(value: float | None, *, signed: bool = False) -> str:
    if value is None:
        return "n/a"
    if signed:
        return f"{value:+,.2f}"
    return f"{value:,.2f}"


def _render_line_chart_svg(*, points: list[dict], value_key: str, stroke: str, fill: str) -> str:
    values = [point.get(value_key) for point in points if isinstance(point.get(value_key), (int, float))]
    if not values:
        return "<div class='chart-empty'>waiting for account samples</div>"
    if len(values) == 1:
        values = [values[0], values[0]]
    min_value = min(values)
    max_value = max(values)
    spread = max(max_value - min_value, 1e-9)
    width = 560
    height = 220
    pad_x = 18
    pad_y = 18
    chart_width = width - pad_x * 2
    chart_height = height - pad_y * 2
    coordinates: list[tuple[float, float]] = []
    for index, value in enumerate(values):
        x = pad_x + (chart_width * index / max(len(values) - 1, 1))
        y = pad_y + chart_height - (((value - min_value) / spread) * chart_height)
        coordinates.append((x, y))
    polyline = " ".join(f"{x:.2f},{y:.2f}" for x, y in coordinates)
    area = " ".join([f"{coordinates[0][0]:.2f},{height - pad_y:.2f}", polyline, f"{coordinates[-1][0]:.2f},{height - pad_y:.2f}"])
    return (
        f"<svg viewBox='0 0 {width} {height}' class='chart-svg' role='img' aria-label='{escape(value_key)} chart'>"
        f"<polygon points='{area}' fill='{fill}'></polygon>"
        f"<polyline points='{polyline}' fill='none' stroke='{stroke}' stroke-width='3' stroke-linecap='round' stroke-linejoin='round'></polyline>"
        f"</svg>"
    )


def render_dashboard_html(snapshot: dict) -> str:
    summary = build_dashboard_summary_payload(snapshot)
    timeseries = build_dashboard_timeseries_payload(snapshot)
    health_items = "".join(
        f"<article class='health-row health-{escape(item['status'].lower())}'><div><strong>{escape(item['name'])}</strong></div>"
        f"<div>{escape(item['status'])}</div><div>{escape(item['message'])}</div></article>"
        for item in snapshot["health"]["items"]
    )
    warnings = "".join(f"<li>{escape(warning)}</li>" for warning in snapshot["warnings"]) or "<li>none</li>"
    recent_events = "".join(
        "<article class='timeline-event'>"
        f"<header><strong>{escape(event['event_type'])}</strong><time>{escape(format_timestamp_for_display(event['timestamp']))}</time></header>"
        f"<div class='timeline-source'>{escape(str(event.get('source') or 'unknown'))}</div>"
        f"<pre>{escape(json.dumps(event['payload'], ensure_ascii=False, indent=2))}</pre>"
        "</article>"
        for event in snapshot["recent_events"]
    ) or "<article class='timeline-event'><header><strong>none</strong></header></article>"
    event_bars = "".join(
        f"<div class='event-bar'><span>{escape(event_type)}</span><strong>{count}</strong></div>"
        for event_type, count in sorted(snapshot.get("event_counts", {}).items())
    ) or "<div class='event-bar'><span>none</span><strong>0</strong></div>"
    source_bars = "".join(
        f"<div class='source-chip'><span>{escape(source)}</span><strong>{count}</strong></div>"
        for source, count in sorted(snapshot.get("source_counts", {}).items())
    ) or "<div class='source-chip'><span>none</span><strong>0</strong></div>"
    leader_rows = "".join(
        f"<div class='leader-row'><span>{escape(item['symbol'])}</span><time>{escape(format_timestamp_for_display(item['timestamp']))}</time></div>"
        for item in snapshot.get("leader_history", [])
    ) or "<div class='leader-row'><span>none</span><time>n/a</time></div>"
    pulse_points = snapshot.get("pulse_points", [])
    pulse_max = max((point["event_count"] for point in pulse_points), default=1)
    pulse_bars = "".join(
        "<div class='pulse-bar-wrap'>"
        f"<div class='pulse-bar' style='height:{max(10, int(100 * point['event_count'] / pulse_max))}%;'></div>"
        f"<span>{escape(format_timestamp_for_display(point['bucket'])[11:16])}</span>"
        "</div>"
        for point in pulse_points
    ) or "<div class='pulse-bar-wrap'><div class='pulse-bar' style='height:10%;'></div><span>n/a</span></div>"
    latest_signal = snapshot["runtime"].get("latest_signal_decision") or {}
    latest_broker_order = snapshot["runtime"].get("latest_broker_order") or {}
    latest_position_snapshot = snapshot["runtime"].get("latest_position_snapshot") or {}
    latest_account_snapshot = snapshot["runtime"].get("latest_account_snapshot") or {}
    latest_signal_payload = latest_signal.get("payload") or {}
    blocked_reason = latest_signal_payload.get("blocked_reason")
    decision_status = latest_signal.get("decision_type") or "none"
    latest_signal_symbol = latest_signal.get("symbol") or "none"
    latest_signal_time = format_timestamp_for_display(latest_signal.get("timestamp"))
    wallet_balance = _format_metric(summary["account"].get("wallet_balance"))
    available_balance = _format_metric(summary["account"].get("available_balance"))
    equity = _format_metric(summary["account"].get("equity"))
    unrealized_pnl = _format_metric(summary["account"].get("unrealized_pnl"), signed=True)
    equity_chart = _render_line_chart_svg(
        points=timeseries["account"],
        value_key="equity",
        stroke="#4cc9f0",
        fill="rgba(76,201,240,0.14)",
    )
    wallet_chart = _render_line_chart_svg(
        points=timeseries["account"],
        value_key="wallet_balance",
        stroke="#36d98a",
        fill="rgba(54,217,138,0.14)",
    )
    recent_signal_rows = "".join(
        f"<div class='leader-row'><span>{escape(str(item.get('decision_type')))} · {escape(str(item.get('symbol')))}</span><time>{escape(format_timestamp_for_display(item.get('timestamp')))}</time></div>"
        for item in snapshot.get("recent_signal_decisions", [])
    ) or "<div class='leader-row'><span>none</span><time>n/a</time></div>"
    recent_broker_rows = "".join(
        f"<div class='leader-row'><span>{escape(str(item.get('action_type')))} · {escape(str(item.get('symbol')))}</span><time>{escape(format_timestamp_for_display(item.get('timestamp')))}</time></div>"
        for item in snapshot.get("recent_broker_orders", [])
    ) or "<div class='leader-row'><span>none</span><time>n/a</time></div>"
    recent_account_rows = "".join(
        f"<div class='leader-row'><span>{escape(str(item.get('leader_symbol') or 'none'))} · equity {escape(_format_metric(_parse_numeric(item.get('equity'))))}</span><time>{escape(format_timestamp_for_display(item.get('timestamp')))}</time></div>"
        for item in snapshot.get("recent_account_snapshots", [])[:8]
    ) or "<div class='leader-row'><span>none</span><time>n/a</time></div>"
    runtime = snapshot["runtime"]
    return f"""<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Momentum Alpha Dashboard</title>
  <style>
    :root {{ color-scheme: dark; --bg: #09111b; --panel: #101b27; --panel-2: #0d1621; --text: #e8f0f8; --muted: #8ea2b7; --line: #223446; --ok: #36d98a; --warn: #ffbc42; --fail: #ff5d73; --accent: #4cc9f0; }}
    * {{ box-sizing: border-box; }}
    body {{ margin: 0; font-family: "SFMono-Regular", "Menlo", monospace; background: radial-gradient(circle at top, #122033 0%, var(--bg) 55%); color: var(--text); }}
    .desk-shell {{ max-width: 1400px; margin: 0 auto; padding: 24px; }}
    .hero {{ display: flex; align-items: end; justify-content: space-between; gap: 16px; margin-bottom: 20px; }}
    .hero h1 {{ margin: 0; font-size: 2rem; letter-spacing: 0.04em; text-transform: uppercase; }}
    .hero p {{ margin: 6px 0 0; color: var(--muted); }}
    .status-pill {{ padding: 8px 14px; border-radius: 999px; font-weight: 700; border: 1px solid var(--line); }}
    .status-pill.ok {{ background: rgba(54, 217, 138, 0.14); color: var(--ok); }}
    .status-pill.fail {{ background: rgba(255, 93, 115, 0.14); color: var(--fail); }}
    .metrics {{ display: grid; gap: 14px; grid-template-columns: repeat(auto-fit, minmax(180px, 1fr)); margin-bottom: 18px; }}
    .metric-card, section {{ background: linear-gradient(180deg, rgba(20,33,48,0.96), rgba(13,22,33,0.96)); border: 1px solid var(--line); border-radius: 18px; box-shadow: 0 18px 40px rgba(0,0,0,0.25); }}
    .metric-card {{ padding: 16px; min-height: 110px; }}
    .metric-card .label {{ color: var(--muted); font-size: 0.82rem; text-transform: uppercase; letter-spacing: 0.08em; }}
    .metric-card .value {{ margin-top: 10px; font-size: 1.75rem; font-weight: 700; }}
    .metric-card .sub {{ margin-top: 8px; color: var(--muted); font-size: 0.85rem; }}
    .metric-card.pnl-positive .value {{ color: var(--ok); }}
    .metric-card.pnl-negative .value {{ color: var(--fail); }}
    .main-grid {{ display: grid; gap: 16px; grid-template-columns: 1.2fr 0.8fr; }}
    .stack {{ display: grid; gap: 16px; }}
    section {{ padding: 18px; }}
    h2 {{ margin: 0 0 14px; font-size: 1rem; letter-spacing: 0.08em; text-transform: uppercase; }}
    .chart-shell {{ display: grid; gap: 10px; }}
    .chart-svg {{ width: 100%; height: auto; display: block; border-radius: 12px; background: rgba(255,255,255,0.02); border: 1px solid rgba(255,255,255,0.05); }}
    .chart-meta {{ display: flex; justify-content: space-between; gap: 12px; color: var(--muted); font-size: 0.82rem; }}
    .chart-empty {{ display: grid; place-items: center; min-height: 220px; border-radius: 12px; border: 1px dashed rgba(255,255,255,0.12); color: var(--muted); }}
    .health-list {{ display: grid; gap: 10px; }}
    .health-row {{ display: grid; grid-template-columns: 1.1fr 0.4fr 1.8fr; gap: 10px; padding: 12px; border-radius: 12px; background: rgba(255,255,255,0.02); }}
    .health-ok {{ border: 1px solid rgba(54, 217, 138, 0.2); }}
    .health-fail {{ border: 1px solid rgba(255, 93, 115, 0.2); }}
    .event-bars, .source-mix, .leader-rotation, .decision-cards {{ display: grid; gap: 10px; }}
    .decision-cards {{ grid-template-columns: repeat(auto-fit, minmax(140px, 1fr)); }}
    .decision-card {{ padding: 14px; border-radius: 14px; border: 1px solid rgba(255,255,255,0.08); background: linear-gradient(180deg, rgba(255,255,255,0.04), rgba(255,255,255,0.02)); }}
    .decision-card .eyebrow {{ color: var(--muted); text-transform: uppercase; font-size: 0.72rem; letter-spacing: 0.08em; }}
    .decision-card .big {{ margin-top: 8px; font-size: 1.05rem; font-weight: 700; word-break: break-word; }}
    .event-bar {{ display: flex; justify-content: space-between; align-items: center; padding: 12px 14px; border-radius: 12px; background: linear-gradient(90deg, rgba(76,201,240,0.16), rgba(76,201,240,0.05)); border: 1px solid rgba(76,201,240,0.18); }}
    .event-bar span {{ color: var(--muted); text-transform: uppercase; font-size: 0.82rem; }}
    .source-chip, .leader-row {{ display: flex; justify-content: space-between; align-items: center; padding: 10px 12px; border-radius: 12px; background: rgba(255,255,255,0.03); border: 1px solid rgba(255,255,255,0.07); }}
    .source-chip span, .leader-row span {{ color: var(--muted); text-transform: uppercase; font-size: 0.82rem; }}
    .pulse-grid {{ display: grid; grid-template-columns: repeat(auto-fit, minmax(32px, 1fr)); gap: 8px; align-items: end; min-height: 180px; }}
    .pulse-bar-wrap {{ display: grid; gap: 8px; justify-items: center; align-items: end; }}
    .pulse-bar {{ width: 100%; max-width: 28px; border-radius: 999px 999px 4px 4px; background: linear-gradient(180deg, #4cc9f0, #2a7a9a); min-height: 10px; }}
    .pulse-bar-wrap span {{ color: var(--muted); font-size: 0.75rem; }}
    .timeline {{ display: grid; gap: 12px; max-height: 640px; overflow: auto; }}
    .timeline-event {{ border-left: 3px solid var(--accent); padding: 10px 12px; background: rgba(255,255,255,0.02); border-radius: 0 12px 12px 0; }}
    .timeline-event header {{ display: flex; justify-content: space-between; gap: 12px; margin-bottom: 10px; }}
    .timeline-event time {{ color: var(--muted); font-size: 0.85rem; }}
    .timeline-source {{ margin-bottom: 10px; color: var(--accent); text-transform: uppercase; font-size: 0.75rem; letter-spacing: 0.08em; }}
    .warnings ul {{ margin: 0; padding-left: 18px; }}
    .warnings li {{ margin: 8px 0; color: #ffd7a1; }}
    pre {{ margin: 0; white-space: pre-wrap; word-break: break-word; background: rgba(3, 10, 18, 0.72); color: #c8f1ff; padding: 12px; border-radius: 12px; overflow: auto; }}
    @media (max-width: 980px) {{ .main-grid {{ grid-template-columns: 1fr; }} .hero {{ flex-direction: column; align-items: start; }} }}
  </style>
</head>
<body>
  <main class="desk-shell">
    <div class="hero">
      <div>
        <h1>Momentum Alpha Dashboard</h1>
        <p>Trade desk view with live health, state, and event flow. Auto refresh every 5 seconds.</p>
      </div>
      <div class="status-pill {'ok' if snapshot['health']['overall_status'] == 'OK' else 'fail'}">overall={escape(snapshot['health']['overall_status'])}</div>
    </div>
    <div class="metrics">
      <article class="metric-card"><div class="label">Leader</div><div class="value">{escape(str(runtime['previous_leader_symbol']))}</div><div class="sub">Current previous leader symbol</div></article>
      <article class="metric-card"><div class="label">Positions</div><div class="value">{runtime['position_count']}</div><div class="sub">Open local positions</div></article>
      <article class="metric-card"><div class="label">Order States</div><div class="value">{runtime['order_status_count']}</div><div class="sub">Tracked order lifecycle entries</div></article>
      <article class="metric-card"><div class="label">Latest Tick</div><div class="value">{escape(format_timestamp_for_display(runtime['latest_tick_timestamp']))}</div><div class="sub">Most recent poll tick seen</div></article>
      <article class="metric-card"><div class="label">Wallet Balance</div><div class="value">{escape(wallet_balance)}</div><div class="sub">Futures wallet balance</div></article>
      <article class="metric-card"><div class="label">Available Balance</div><div class="value">{escape(available_balance)}</div><div class="sub">Available collateral</div></article>
      <article class="metric-card"><div class="label">Equity</div><div class="value">{escape(equity)}</div><div class="sub">Current net value</div></article>
      <article class="metric-card {'pnl-negative' if str(unrealized_pnl).startswith('-') else 'pnl-positive'}"><div class="label">Unrealized PnL</div><div class="value">{escape(unrealized_pnl)}</div><div class="sub">Mark-to-market drift</div></article>
    </div>
    <div class="main-grid">
      <div class="stack">
        <section>
          <h2>Account Equity Curve</h2>
          <div class="chart-shell">
            {equity_chart}
            <div class="chart-meta"><span>Net value curve from SQLite snapshots</span><span>{escape(format_timestamp_for_display(latest_account_snapshot.get('timestamp')))}</span></div>
          </div>
        </section>
        <section>
          <h2>Wallet Balance Curve</h2>
          <div class="chart-shell">
            {wallet_chart}
            <div class="chart-meta"><span>Wallet balance accumulation</span><span>{escape(format_timestamp_for_display(latest_account_snapshot.get('timestamp')))}</span></div>
          </div>
        </section>
        <section>
          <h2>Health Matrix</h2>
          <div class="health-list">{health_items}</div>
        </section>
        <section>
          <h2>Decision Overview</h2>
          <div class="decision-cards">
            <article class="decision-card"><div class="eyebrow">Latest Decision</div><div class="big">{escape(str(decision_status))}</div></article>
            <article class="decision-card"><div class="eyebrow">Target Symbol</div><div class="big">{escape(str(latest_signal_symbol))}</div></article>
            <article class="decision-card"><div class="eyebrow">Blocked Reason</div><div class="big">{escape(str(blocked_reason or 'none'))}</div></article>
            <article class="decision-card"><div class="eyebrow">Decision Time</div><div class="big">{escape(latest_signal_time)}</div></article>
          </div>
        </section>
        <section class="warnings">
          <h2>Warnings</h2>
          <ul>{warnings}</ul>
        </section>
      </div>
      <div class="stack">
        <section>
          <h2>Event Pulse</h2>
          <div class="event-bars">{event_bars}</div>
        </section>
        <section>
          <h2>Pulse Window</h2>
          <div class="pulse-grid">{pulse_bars}</div>
        </section>
        <section>
          <h2>Source Mix</h2>
          <div class="source-mix">{source_bars}</div>
        </section>
        <section>
          <h2>Leader Timeline</h2>
          <div class="leader-rotation">{leader_rows}</div>
        </section>
        <section>
          <h2>Leader Rotation</h2>
          <div class="leader-rotation">{leader_rows}</div>
        </section>
        <section>
          <h2>Latest Signal</h2>
          <pre>{escape(json.dumps(latest_signal, ensure_ascii=False, indent=2))}</pre>
        </section>
        <section>
          <h2>Blocked Reason</h2>
          <div class="leader-rotation"><div class='leader-row'><span>{escape(str(blocked_reason or 'none'))}</span><time>{escape(format_timestamp_for_display(latest_signal.get('timestamp')))}</time></div></div>
        </section>
        <section>
          <h2>Broker Activity</h2>
          <pre>{escape(json.dumps(latest_broker_order, ensure_ascii=False, indent=2))}</pre>
        </section>
        <section>
          <h2>Position Snapshot</h2>
          <pre>{escape(json.dumps(latest_position_snapshot, ensure_ascii=False, indent=2))}</pre>
        </section>
        <section>
          <h2>Recent Signal Decisions</h2>
          <div class="leader-rotation">{recent_signal_rows}</div>
        </section>
        <section>
          <h2>Recent Broker Orders</h2>
          <div class="leader-rotation">{recent_broker_rows}</div>
        </section>
        <section>
          <h2>Account Snapshots</h2>
          <div class="leader-rotation">{recent_account_rows}</div>
        </section>
        <section>
          <h2>Latest Result</h2>
          <pre>{escape(json.dumps(runtime, ensure_ascii=False, indent=2))}</pre>
        </section>
      </div>
    </div>
    <section style="margin-top: 16px;">
      <h2>Recent Event Timeline</h2>
      <div class="timeline">{recent_events}</div>
    </section>
  </main>
  <script>
    async function refreshDashboard() {{
      try {{
        const response = await fetch('/api/dashboard', {{ cache: 'no-store' }});
        if (!response.ok) return;
        const payload = await response.json();
        document.title = `Momentum Alpha Dashboard · ${{payload.health.overall_status}}`;
        window.location.reload();
      }} catch (error) {{
        console.error(error);
      }}
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
