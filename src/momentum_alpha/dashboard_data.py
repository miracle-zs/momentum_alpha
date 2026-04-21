from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.dashboard_common import (
    ACCOUNT_RANGE_WINDOWS,
    _compute_margin_usage_pct,
    _parse_numeric,
    build_strategy_config,
    normalize_account_range,
)
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_latest_daily_review_report,
    fetch_recent_account_flows,
    fetch_recent_algo_orders,
    fetch_recent_audit_events,
    fetch_recent_broker_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_trade_round_trips_for_range,
)


def _account_flow_since(*, now: datetime, range_key: str) -> datetime:
    window = ACCOUNT_RANGE_WINDOWS.get(range_key)
    if window is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return now.astimezone(timezone.utc) - window


def _select_latest_timestamp(events: list[dict], event_type: str) -> str | None:
    for event in events:
        if event.get("event_type") == event_type:
            return event.get("timestamp")
    return None


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
        bucket_key = (
            datetime.fromisoformat(timestamp)
            .astimezone(timezone.utc)
            .replace(second=0, microsecond=0)
            .isoformat()
        )
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
    account_flows = sorted(
        snapshot.get("account_metric_flows", snapshot.get("recent_account_flows", [])),
        key=lambda item: item.get("timestamp") or "",
    )
    cumulative_external_flow = 0.0
    flow_index = 0
    account_points = []
    for row in account_rows:
        timestamp = row.get("timestamp") or ""
        while flow_index < len(account_flows) and (account_flows[flow_index].get("timestamp") or "") <= timestamp:
            flow = account_flows[flow_index]
            if _is_external_account_flow(flow):
                cumulative_external_flow += _parse_numeric(flow.get("balance_change")) or 0.0
            flow_index += 1
        equity = _parse_numeric(row.get("equity"))
        account_points.append(
            {
                "timestamp": timestamp,
                "wallet_balance": _parse_numeric(row.get("wallet_balance")),
                "available_balance": _parse_numeric(row.get("available_balance")),
                "equity": equity,
                "margin_usage_pct": _compute_margin_usage_pct(
                    available_balance=row.get("available_balance"),
                    equity=row.get("equity"),
                ),
                "adjusted_equity": None if equity is None else equity - cumulative_external_flow,
                "unrealized_pnl": _parse_numeric(row.get("unrealized_pnl")),
                "position_count": row.get("position_count"),
                "open_order_count": row.get("open_order_count"),
                "leader_symbol": row.get("leader_symbol"),
            }
        )
    return {
        "account": account_points,
        "pulse_points": snapshot.get("pulse_points", []),
        "leader_history": list(reversed(snapshot.get("leader_history", []))),
    }


def build_trade_leg_count_aggregates(round_trips: list[dict]) -> list[dict]:
    grouped: dict[int, list[dict]] = {}
    for trip in round_trips:
        payload = trip.get("payload") or {}
        leg_count = _parse_numeric(payload.get("leg_count"))
        if leg_count is None:
            continue
        leg_count_int = int(leg_count)
        if leg_count_int <= 0:
            continue
        grouped.setdefault(leg_count_int, []).append(trip)

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
            leg_index = _parse_numeric(leg.get("leg_index")) if isinstance(leg, Mapping) else None
            if leg_index is None:
                continue
            leg_index_int = int(leg_index)
            if leg_index_int <= 0:
                continue
            grouped.setdefault(leg_index_int, []).append(leg)

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


_EXTERNAL_ACCOUNT_FLOW_REASONS = {
    "DEPOSIT",
    "WITHDRAW",
    "WITHDRAW_REJECT",
    "ADMIN_DEPOSIT",
    "TRANSFER",
    "ASSET_TRANSFER",
    "MARGIN_TRANSFER",
    "INTERNAL_TRANSFER",
    "FUNDING_TRANSFER",
    "OPTIONS_TRANSFER",
}


def _is_external_account_flow(flow: dict) -> bool:
    reason = str(flow.get("reason") or "").upper()
    return reason in _EXTERNAL_ACCOUNT_FLOW_REASONS


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
    poll_log_file: Path | None = None,
    user_stream_log_file: Path | None = None,
    runtime_db_file: Path,
    recent_limit: int = 20,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
    account_range_key: str = "1D",
) -> dict:
    account_range_key = normalize_account_range(account_range_key)
    health_report = build_runtime_health_report(
        now=now,
        runtime_db_file=runtime_db_file,
    )
    warnings: list[str] = []
    state_payload: dict = {}

    if runtime_db_file.exists():
        try:
            runtime_state = RuntimeStateStore(path=runtime_db_file).load()
        except Exception as exc:
            warnings.append(f"runtime state unavailable path={runtime_db_file} error={exc}")
            runtime_state = None
        if runtime_state is not None:
            state_payload = {
                "current_day": runtime_state.current_day,
                "previous_leader_symbol": runtime_state.previous_leader_symbol,
                "positions": runtime_state.positions or {},
                "processed_event_ids": runtime_state.processed_event_ids or {},
                "order_statuses": runtime_state.order_statuses or {},
                "recent_stop_loss_exits": runtime_state.recent_stop_loss_exits or {},
            }

    recent_signal_decisions: list[dict] = []
    recent_broker_orders: list[dict] = []
    recent_trade_fills: list[dict] = []
    recent_algo_orders: list[dict] = []
    recent_account_flows: list[dict] = []
    account_metric_flows: list[dict] = []
    recent_trade_round_trips: list[dict] = []
    recent_stop_exit_summaries: list[dict] = []
    recent_position_snapshots: list[dict] = []
    recent_account_snapshots: list[dict] = []
    daily_review_report: dict | None = None

    if runtime_db_file.exists():
        events_for_metrics = _normalize_events(fetch_recent_audit_events(path=runtime_db_file, limit=max(recent_limit, 300)))
        recent_signal_decisions = fetch_recent_signal_decisions(path=runtime_db_file, limit=8)
        recent_broker_orders = fetch_recent_broker_orders(path=runtime_db_file, limit=8)
        recent_trade_fills = fetch_recent_trade_fills(path=runtime_db_file, limit=20)
        recent_algo_orders = fetch_recent_algo_orders(path=runtime_db_file, limit=20)
        recent_account_flows = fetch_recent_account_flows(path=runtime_db_file, limit=20)
        account_metric_flows = fetch_account_flows_since(
            path=runtime_db_file,
            since=_account_flow_since(now=now, range_key=account_range_key),
        )
        recent_trade_round_trips = fetch_trade_round_trips_for_range(
            path=runtime_db_file,
            now=now,
            range_key="ALL",
        )
        recent_stop_exit_summaries = fetch_recent_stop_exit_summaries(path=runtime_db_file, limit=20)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_account_snapshots = fetch_account_snapshots_for_range(path=runtime_db_file, now=now, range_key=account_range_key)
        daily_review_report = fetch_latest_daily_review_report(path=runtime_db_file)
    else:
        events_for_metrics = []
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
        "account_metric_flows": account_metric_flows,
        "recent_trade_round_trips": recent_trade_round_trips,
        "recent_stop_exit_summaries": recent_stop_exit_summaries,
        "recent_position_snapshots": recent_position_snapshots,
        "recent_account_snapshots": recent_account_snapshots,
        "daily_review_report": daily_review_report,
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
