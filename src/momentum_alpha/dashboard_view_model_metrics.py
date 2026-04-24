from __future__ import annotations

from collections import Counter
from datetime import datetime

from .dashboard_common import _compute_margin_usage_pct, _parse_numeric
from .dashboard_data import build_dashboard_timeseries_payload
from .dashboard_view_model_common import DISPLAY_TIMEZONE
from .dashboard_view_model_range import _filter_rows_for_display_day, _filter_rows_for_range


def _current_streak_from_round_trips(round_trips: list[dict]) -> dict[str, int | str | None]:
    if not round_trips:
        return {"label": None, "count": 0}

    ordered_round_trips = sorted(round_trips, key=lambda item: item.get("closed_at") or "")
    streak_sign: int | None = None
    streak_count = 0

    for trip in reversed(ordered_round_trips):
        net_pnl = _parse_numeric(trip.get("net_pnl"))
        if net_pnl is None or net_pnl == 0:
            if streak_count > 0:
                break
            continue

        sign = 1 if net_pnl > 0 else -1
        if streak_sign is None:
            streak_sign = sign
        if sign != streak_sign:
            break
        streak_count += 1

    if streak_count == 0 or streak_sign is None:
        return {"label": None, "count": 0}
    return {
        "label": f"{'W' if streak_sign > 0 else 'L'}{streak_count}",
        "count": streak_count,
    }


def build_trader_summary_metrics(
    snapshot: dict,
    *,
    position_details: list[dict],
    range_key: str = "1D",
) -> dict:
    account_timeline = build_dashboard_timeseries_payload(snapshot).get("account", [])
    account_rows = sorted(snapshot.get("recent_account_snapshots", []), key=lambda item: item.get("timestamp") or "")
    runtime_latest_account = (snapshot.get("runtime") or {}).get("latest_account_snapshot") or None
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

    latest_account = scoped_accounts[-1] if scoped_accounts else runtime_latest_account
    latest_equity = _parse_numeric(latest_account.get("equity")) if latest_account else None
    latest_available = _parse_numeric(latest_account.get("available_balance")) if latest_account else None
    latest_wallet = _parse_numeric(latest_account.get("wallet_balance")) if latest_account else None
    latest_unrealized_pnl = _parse_numeric(latest_account.get("unrealized_pnl")) if latest_account else None
    latest_position_count = latest_account.get("position_count") if latest_account else None
    latest_order_count = latest_account.get("open_order_count") if latest_account else None

    scoped_account_points = _filter_rows_for_range(
        account_timeline,
        timestamp_key="timestamp",
        range_key=range_key,
    )
    latest_display_date = None
    timestamp_candidates = [
        item.get("timestamp")
        for item in scoped_account_points
        if item.get("timestamp")
    ]
    timestamp_candidates.extend(
        item.get("closed_at")
        for item in scoped_round_trips
        if item.get("closed_at")
    )
    if timestamp_candidates:
        latest_display_date = max(
            datetime.fromisoformat(str(timestamp)).astimezone(DISPLAY_TIMEZONE).date()
            for timestamp in timestamp_candidates
        )

    today_net_pnl = None
    same_day_account_points = _filter_rows_for_display_day(
        scoped_account_points,
        timestamp_key="timestamp",
        target_date=latest_display_date,
    )
    same_day_round_trips = _filter_rows_for_display_day(
        scoped_round_trips,
        timestamp_key="closed_at",
        target_date=latest_display_date,
    )
    latest_same_day_account_timestamp = max(
        (item.get("timestamp") for item in same_day_account_points if item.get("timestamp")),
        default=None,
    )
    latest_same_day_round_trip_timestamp = max(
        (item.get("closed_at") for item in same_day_round_trips if item.get("closed_at")),
        default=None,
    )
    account_points_are_freshest = (
        latest_same_day_account_timestamp is not None
        and (
            latest_same_day_round_trip_timestamp is None
            or latest_same_day_account_timestamp >= latest_same_day_round_trip_timestamp
        )
    )
    if len(same_day_account_points) >= 2 and account_points_are_freshest:
        first_point = same_day_account_points[0]
        last_point = same_day_account_points[-1]
        first_adjusted_equity = _parse_numeric(first_point.get("adjusted_equity"))
        last_adjusted_equity = _parse_numeric(last_point.get("adjusted_equity"))
        if first_adjusted_equity is not None and last_adjusted_equity is not None:
            today_net_pnl = last_adjusted_equity - first_adjusted_equity
    if today_net_pnl is None:
        scoped_round_trip_pnls = [_parse_numeric(trip.get("net_pnl")) for trip in same_day_round_trips]
        scoped_round_trip_pnls = [pnl for pnl in scoped_round_trip_pnls if pnl is not None]
        if scoped_round_trip_pnls:
            today_net_pnl = sum(scoped_round_trip_pnls)

    margin_usage_pct = _compute_margin_usage_pct(
        available_balance=latest_available,
        equity=latest_equity,
    )

    open_risk = sum((_parse_numeric(position.get("risk")) or 0.0) for position in position_details)
    open_risk_pct = None
    if latest_equity not in (None, 0):
        open_risk_pct = (open_risk / latest_equity) * 100

    round_trip_pnls = [_parse_numeric(trip.get("net_pnl")) for trip in scoped_round_trips]
    round_trip_pnls = [pnl for pnl in round_trip_pnls if pnl is not None]
    wins = [pnl for pnl in round_trip_pnls if pnl > 0]
    losses = [pnl for pnl in round_trip_pnls if pnl < 0]
    commissions = [_parse_numeric(trip.get("commission")) for trip in scoped_round_trips]
    commissions = [commission for commission in commissions if commission is not None]
    total_trades = len(round_trip_pnls)
    win_rate = (len(wins) / total_trades) if total_trades else None
    profit_factor = None
    if losses:
        gross_wins = sum(wins)
        gross_losses = abs(sum(losses))
        if gross_losses:
            profit_factor = gross_wins / gross_losses
    avg_win = (sum(wins) / len(wins)) if wins else None
    avg_loss = (sum(losses) / len(losses)) if losses else None
    expectancy = (sum(round_trip_pnls) / total_trades) if total_trades else None
    durations = [_parse_numeric(trip.get("duration_seconds")) for trip in scoped_round_trips]
    durations = [duration for duration in durations if duration is not None]
    avg_hold_time_seconds = (sum(durations) / len(durations)) if durations else None

    slippages: list[float] = []
    for item in scoped_stop_exits:
        slippage = _parse_numeric(item.get("slippage_pct"))
        if slippage is None:
            trigger_price = _parse_numeric(item.get("trigger_price"))
            average_exit_price = _parse_numeric(item.get("average_exit_price"))
            if trigger_price not in (None, 0) and average_exit_price is not None:
                slippage = abs((average_exit_price - trigger_price) / trigger_price) * 100
        if slippage is not None:
            slippages.append(slippage)
    avg_slippage_pct = (sum(slippages) / len(slippages)) if slippages else None
    max_slippage_pct = max(slippages) if slippages else None
    fee_total = sum(commissions) if commissions else None
    if fee_total is None:
        stop_exit_commissions = [_parse_numeric(item.get("commission")) for item in scoped_stop_exits]
        stop_exit_commissions = [commission for commission in stop_exit_commissions if commission is not None]
        fee_total = sum(stop_exit_commissions) if stop_exit_commissions else None

    blocked_reason_counts = Counter(
        reason
        for reason in (
            (item.get("payload") or {}).get("blocked_reason")
            for item in scoped_signal_decisions
        )
        if reason
    )
    previous_symbol = None
    rotation_count = 0
    for item in scoped_leader_history:
        symbol = item.get("symbol")
        if not symbol:
            continue
        if previous_symbol is not None and symbol != previous_symbol:
            rotation_count += 1
        previous_symbol = symbol

    return {
        "account": {
            "today_net_pnl": today_net_pnl,
            "margin_usage_pct": margin_usage_pct,
            "open_risk": open_risk,
            "open_risk_pct": open_risk_pct,
            "current_wallet": latest_wallet,
            "current_equity": latest_equity,
            "current_available_balance": latest_available,
            "current_unrealized_pnl": latest_unrealized_pnl,
            "current_positions": latest_position_count,
            "current_orders": latest_order_count,
        },
        "execution": {
            "avg_slippage_pct": avg_slippage_pct,
            "max_slippage_pct": max_slippage_pct,
            "stop_exit_count": len(scoped_stop_exits),
            "fee_total": fee_total,
        },
        "performance": {
            "win_rate": win_rate,
            "profit_factor": profit_factor,
            "current_streak": _current_streak_from_round_trips(scoped_round_trips),
            "trade_count": total_trades,
            "avg_win": avg_win,
            "avg_loss": avg_loss,
            "expectancy": expectancy,
            "avg_hold_time_seconds": avg_hold_time_seconds,
        },
        "signals": {
            "blocked_reason_counts": dict(sorted(blocked_reason_counts.items())),
            "rotation_count": rotation_count,
        },
    }
