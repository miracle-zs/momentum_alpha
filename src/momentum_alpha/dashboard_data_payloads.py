from __future__ import annotations

import json
from collections.abc import Mapping

from momentum_alpha.dashboard_common import _compute_margin_usage_pct, _parse_numeric

from .dashboard_data_common import _is_external_account_flow
from .dashboard_position_risk import build_position_risk_series


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
        while position_risk_index < len(position_risk_points) and (
            position_risk_points[position_risk_index].get("timestamp") or ""
        ) <= timestamp:
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
    position_risk_snapshots = snapshot.get("recent_position_risk_snapshots") or snapshot.get("recent_position_snapshots", [])
    position_risk_points = build_position_risk_series(position_risk_snapshots)
    runtime = snapshot.get("runtime") or {}
    if runtime and int(runtime.get("position_count") or 0) == 0:
        # Preserve the historical series, but make the current flat state explicit.
        latest_position_snapshot = runtime.get("latest_position_snapshot") or {}
        zero_timestamp = (
            latest_position_snapshot.get("timestamp")
            or (account_points[-1]["timestamp"] if account_points else None)
            or (position_risk_points[-1]["timestamp"] if position_risk_points else None)
        )
        if zero_timestamp is not None and (not position_risk_points or position_risk_points[-1].get("open_risk") != 0.0):
            position_risk_points.append({"timestamp": zero_timestamp, "open_risk": 0.0})
    return {
        "account": account_points,
        "position_risk": position_risk_points,
        "core_live_timeline": _build_shared_core_live_timeline(account_points, position_risk_points),
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


def build_dashboard_response_json(snapshot: dict) -> str:
    return json.dumps(snapshot, ensure_ascii=False, indent=2)
