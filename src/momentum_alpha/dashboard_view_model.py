from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from decimal import Decimal

from .dashboard_common import _compute_margin_usage_pct, _parse_numeric
from .dashboard_data import build_dashboard_timeseries_payload


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None

def _object_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)

def _filter_rows_for_range(rows: list[dict], *, timestamp_key: str, range_key: str) -> list[dict]:
    if range_key == "ALL":
        return list(rows)
    hours = {
        "1H": 1,
        "1D": 24,
        "1W": 24 * 7,
        "1M": 24 * 30,
        "1Y": 24 * 365,
    }.get(range_key)
    if not hours or not rows:
        return list(rows)
    parsed_rows = [row for row in rows if row.get(timestamp_key)]
    if not parsed_rows:
        return []
    try:
        end_at = max(datetime.fromisoformat(str(row[timestamp_key])) for row in parsed_rows)
    except ValueError:
        return list(rows)
    start_at = end_at - timedelta(hours=hours)
    return [
        row
        for row in parsed_rows
        if datetime.fromisoformat(str(row[timestamp_key])) >= start_at
    ]

def _filter_rows_for_display_day(rows: list[dict], *, timestamp_key: str, target_date: object | None = None) -> list[dict]:
    if not rows:
        return []

    dated_rows: list[tuple[datetime, dict]] = []
    for row in rows:
        timestamp = row.get(timestamp_key)
        if not timestamp:
            continue
        try:
            parsed = datetime.fromisoformat(str(timestamp)).astimezone(DISPLAY_TIMEZONE)
        except ValueError:
            continue
        dated_rows.append((parsed, row))
    if not dated_rows:
        return []

    effective_date = target_date or dated_rows[-1][0].date()
    return [row for parsed, row in dated_rows if parsed.date() == effective_date]

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

def build_position_details(position_snapshot: dict, equity_value: object | None = None) -> list[dict]:
    """Extract position details with leg breakdown from position snapshot payload."""
    payload = position_snapshot.get("payload") or {}
    positions = payload.get("positions") or {}
    if not positions or not isinstance(positions, Mapping):
        return []

    equity_decimal = _parse_decimal(equity_value)
    details: list[dict] = []
    for symbol, position in positions.items():
        if not isinstance(position, Mapping) and not hasattr(position, "__dict__") and not hasattr(type(position), "__dataclass_fields__"):
            continue
        legs = _object_field(position, "legs") or []
        stop_price = _parse_decimal(_object_field(position, "stop_price"))
        if stop_price is not None and stop_price <= 0:
            stop_price = None
        latest_price = _parse_numeric(_object_field(position, "latest_price"))
        direction = str(_object_field(position, "side") or _object_field(position, "direction") or "LONG").upper()
        total_quantity = Decimal("0")
        weighted_sum = Decimal("0")
        weighted_stop_sum = Decimal("0")
        leg_stop_values_known = True
        leg_info: list[dict] = []
        valid_leg_opened_ats: list[str] = []
        if isinstance(legs, (list, tuple)) and legs:
            for leg in legs:
                if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                    continue
                qty = _parse_decimal(_object_field(leg, "quantity")) or Decimal("0")
                entry = _parse_decimal(_object_field(leg, "entry_price")) or Decimal("0")
                leg_stop = _parse_decimal(_object_field(leg, "stop_price"))
                total_quantity += qty
                weighted_sum += qty * entry
                if leg_stop is None:
                    leg_stop_values_known = False
                else:
                    weighted_stop_sum += qty * leg_stop
                leg_opened_at = _object_field(leg, "opened_at")
                if leg_opened_at is not None:
                    valid_leg_opened_ats.append(str(leg_opened_at))
                leg_info.append({
                    "type": _object_field(leg, "leg_type") or "unknown",
                    "time": str(leg_opened_at) if leg_opened_at is not None else "",
                })
        else:
            total_quantity = _parse_decimal(_object_field(position, "total_quantity")) or Decimal("0")
            avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
            if avg_entry is None:
                avg_entry = _parse_decimal(_object_field(position, "entry_price"))
            if total_quantity > 0 and avg_entry is not None:
                weighted_sum = total_quantity * avg_entry

        if total_quantity <= 0:
            continue
        if weighted_sum <= 0 and not leg_info:
            avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
            if avg_entry is None:
                avg_entry = _parse_decimal(_object_field(position, "entry_price"))
            if avg_entry is None:
                continue
            weighted_sum = total_quantity * avg_entry

        avg_entry = weighted_sum / total_quantity if total_quantity > 0 else Decimal("0")
        risk = None
        if isinstance(legs, (list, tuple)) and legs:
            leg_risk_sum = Decimal("0")
            leg_risk_known = True
            for leg in legs:
                if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                    continue
                qty = _parse_decimal(_object_field(leg, "quantity"))
                entry = _parse_decimal(_object_field(leg, "entry_price"))
                leg_stop = _parse_decimal(_object_field(leg, "stop_price"))
                if leg_stop is None:
                    leg_stop = stop_price
                if qty is None or entry is None or leg_stop is None:
                    leg_risk_known = False
                    continue
                if direction == "SHORT":
                    leg_risk_sum += qty * (leg_stop - entry)
                else:
                    leg_risk_sum += qty * (entry - leg_stop)
            if leg_risk_known:
                risk = leg_risk_sum
        if risk is None and stop_price is not None:
            risk = total_quantity * (avg_entry - stop_price)
            if direction == "SHORT":
                risk = total_quantity * (stop_price - avg_entry)
        opened_at = _object_field(position, "opened_at")
        if not opened_at:
            parsed_leg_opened_ats: list[tuple[datetime, str]] = []
            for leg_opened_at in valid_leg_opened_ats:
                try:
                    parsed_leg_opened_ats.append((datetime.fromisoformat(str(leg_opened_at)), str(leg_opened_at)))
                except ValueError:
                    continue
            if parsed_leg_opened_ats:
                opened_at = min(parsed_leg_opened_ats, key=lambda item: item[0])[1]
            elif valid_leg_opened_ats:
                opened_at = valid_leg_opened_ats[0]
        risk_pct_of_equity = None
        if risk is not None and equity_decimal not in (None, Decimal("0")):
            risk_pct_of_equity = f"{((risk / equity_decimal) * Decimal('100')):.2f}"
        notional_exposure = None
        mtm_pnl = None
        pnl_pct = None
        distance_to_stop_pct = None
        r_multiple = None
        if latest_price is not None:
            notional_exposure = float(total_quantity * Decimal(str(latest_price)))
            if direction == "SHORT":
                mtm_pnl = float((avg_entry - Decimal(str(latest_price))) * total_quantity)
            else:
                mtm_pnl = float((Decimal(str(latest_price)) - avg_entry) * total_quantity)
            entry_notional = total_quantity * avg_entry
            if entry_notional not in (None, Decimal("0")):
                pnl_pct = float((Decimal(str(mtm_pnl)) / entry_notional) * Decimal("100"))
            if risk not in (None, Decimal("0")):
                r_multiple = float(Decimal(str(mtm_pnl)) / risk)
            effective_stop_price = stop_price
            if leg_info and leg_stop_values_known and total_quantity > 0:
                effective_stop_price = weighted_stop_sum / total_quantity
            if effective_stop_price is not None and latest_price > 0:
                if direction == "SHORT":
                    distance_to_stop_pct = float(((effective_stop_price - Decimal(str(latest_price))) / Decimal(str(latest_price))) * Decimal("100"))
                else:
                    distance_to_stop_pct = float(((Decimal(str(latest_price)) - effective_stop_price) / Decimal(str(latest_price))) * Decimal("100"))

        details.append({
            "symbol": symbol,
            "direction": direction,
            "total_quantity": str(total_quantity),
            "entry_price": f"{avg_entry:.2f}",
            "stop_price": str(stop_price) if stop_price is not None else None,
            "risk": f"{risk:.2f}" if risk is not None else None,
            "risk_pct_of_equity": risk_pct_of_equity,
            "leg_count": len(leg_info),
            "opened_at": opened_at,
            "latest_price": latest_price,
            "mtm_pnl": mtm_pnl,
            "pnl_pct": pnl_pct,
            "distance_to_stop_pct": distance_to_stop_pct,
            "notional_exposure": notional_exposure,
            "r_multiple": r_multiple,
            "legs": leg_info,
        })

    return details

def _compute_account_range_stats(points: list[dict], metric: str = "equity") -> dict[str, float | None]:
    if not points:
        return {
            "current_wallet": None,
            "current_equity": None,
            "current_adjusted_equity": None,
            "current_unrealized_pnl": None,
            "current_margin_usage_pct": None,
            "current_positions": None,
            "current_orders": None,
            "metric_change": None,
            "peak_equity": None,
            "peak_margin_usage_pct": None,
            "average_margin_usage_pct": None,
            "drawdown_abs": None,
            "drawdown_pct": None,
        }
    first = points[0]
    last = points[-1]
    peak_equity = max((_parse_numeric(point.get("equity")) or 0.0) for point in points)
    margin_usage_points = [
        _compute_margin_usage_pct(
            available_balance=point.get("available_balance"),
            equity=point.get("equity"),
        )
        for point in points
    ]
    margin_usage_points = [value for value in margin_usage_points if value is not None]
    current_equity = _parse_numeric(last.get("equity"))
    current_adjusted_equity = _parse_numeric(last.get("adjusted_equity"))
    current_wallet = _parse_numeric(last.get("wallet_balance"))
    current_pnl = _parse_numeric(last.get("unrealized_pnl"))
    current_margin_usage_pct = _compute_margin_usage_pct(
        available_balance=last.get("available_balance"),
        equity=last.get("equity"),
    )
    metric_first = _parse_numeric(first.get(metric))
    metric_last = _parse_numeric(last.get(metric))
    metric_change = None
    if metric_first is not None and metric_last is not None:
        metric_change = metric_last - metric_first
    peak_margin_usage_pct = max(margin_usage_points) if margin_usage_points else None
    average_margin_usage_pct = sum(margin_usage_points) / len(margin_usage_points) if margin_usage_points else None
    drawdown_abs = None
    drawdown_pct = None
    if current_equity is not None:
        drawdown_abs = current_equity - peak_equity
        if peak_equity:
            drawdown_pct = (drawdown_abs / peak_equity) * 100
    return {
        "current_wallet": current_wallet,
        "current_equity": current_equity,
        "current_adjusted_equity": current_adjusted_equity,
        "current_unrealized_pnl": current_pnl,
        "current_margin_usage_pct": current_margin_usage_pct,
        "current_positions": last.get("position_count"),
        "current_orders": last.get("open_order_count"),
        "metric_change": metric_change,
        "peak_equity": peak_equity,
        "peak_margin_usage_pct": peak_margin_usage_pct,
        "average_margin_usage_pct": average_margin_usage_pct,
        "drawdown_abs": drawdown_abs,
        "drawdown_pct": drawdown_pct,
    }

def _detect_account_discontinuity(points: list[dict]) -> str | None:
    parsed = [_parse_numeric(point.get("equity")) for point in points]
    for previous, current in zip(parsed, parsed[1:]):
        if previous in (None, 0) or current is None:
            continue
        if abs(current - previous) / abs(previous) >= 0.5:
            return "Large equity jump detected in visible range; verify whether this reflects transfers, resets, or snapshot gaps."
    return None
