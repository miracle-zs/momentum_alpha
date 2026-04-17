from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from decimal import Decimal
from html import escape
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from datetime import datetime, timedelta, timezone
from pathlib import Path
from urllib.parse import parse_qs, urlparse

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


DISPLAY_TIMEZONE_NAME = "Asia/Shanghai"
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
DASHBOARD_TABS = ("overview", "execution", "performance", "system")

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


def _format_time_only(timestamp: str | None) -> str:
    """Format timestamp to show only HH:MM:SS in display timezone."""
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M:%S")
    except ValueError:
        return str(timestamp)[:8] if len(str(timestamp)) >= 8 else str(timestamp)


def _format_time_short(timestamp: str | None) -> str:
    """Format timestamp to show only HH:MM in display timezone."""
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%H:%M")
    except ValueError:
        return str(timestamp)[:5] if len(str(timestamp)) >= 5 else str(timestamp)


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


def _object_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _filter_rows_for_range(rows: list[dict], *, timestamp_key: str, range_key: str) -> list[dict]:
    if range_key == "ALL":
        return list(rows)
    hours = {"1H": 1, "6H": 6, "24H": 24}.get(range_key)
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


def _format_duration_seconds(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    total_seconds = int(round(float(value)))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"


def build_trader_summary_metrics(
    snapshot: dict,
    *,
    position_details: list[dict],
    range_key: str = "24H",
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

    margin_usage_pct = None
    if latest_equity not in (None, 0) and latest_available is not None:
        margin_usage_pct = (1 - (latest_available / latest_equity)) * 100

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
        leg_info: list[dict] = []
        valid_leg_opened_ats: list[str] = []
        if isinstance(legs, (list, tuple)) and legs:
            for leg in legs:
                if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                    continue
                qty = _parse_decimal(_object_field(leg, "quantity")) or Decimal("0")
                entry = _parse_decimal(_object_field(leg, "entry_price")) or Decimal("0")
                total_quantity += qty
                weighted_sum += qty * entry
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
        if stop_price is not None:
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
                if stop_price is not None and latest_price > 0:
                    distance_to_stop_pct = float(((stop_price - Decimal(str(latest_price))) / Decimal(str(latest_price))) * Decimal("100"))
            else:
                mtm_pnl = float((Decimal(str(latest_price)) - avg_entry) * total_quantity)
                if stop_price is not None and latest_price > 0:
                    distance_to_stop_pct = float(((Decimal(str(latest_price)) - stop_price) / Decimal(str(latest_price))) * Decimal("100"))
            entry_notional = total_quantity * avg_entry
            if entry_notional not in (None, Decimal("0")):
                pnl_pct = float((Decimal(str(mtm_pnl)) / entry_notional) * Decimal("100"))
            if risk not in (None, Decimal("0")):
                r_multiple = float(Decimal(str(mtm_pnl)) / risk)

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


def _build_position_details_from_state_positions(positions: dict, *, equity_value: object | None = None) -> list[dict]:
    return build_position_details({"payload": {"positions": positions or {}}}, equity_value=equity_value)


def render_trade_history_table(fills: list[dict]) -> str:
    """Render HTML table for recent trade fills."""
    if not fills:
        return "<div class='trade-history-empty'>No trades</div>"

    rows = ""
    cards = ""
    for fill in fills[:10]:
        time_str = _format_time_only(fill.get("timestamp"))
        symbol = escape(str(fill.get("symbol") or "-"))
        side = fill.get("side") or "-"
        side_class = "side-buy" if side == "BUY" else "side-sell"
        qty = _format_quantity(fill.get("quantity") or fill.get("cumulative_quantity"))
        last_price = _format_price(fill.get("last_price") or fill.get("average_price"))
        commission = _format_metric(_parse_numeric(fill.get("commission")))
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
        cards += (
            f"<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{symbol}</b><span class='trade-side {side_class}'>{escape(side)}</span></div>"
            f"<div class='analytics-card-meta'>"
            f"<span>{escape(time_str)}</span><span>Qty {qty}</span><span>Px {escape(str(last_price))}</span>"
            f"</div>"
            f"<div class='analytics-card-meta'>"
            f"<span>Fee {escape(str(commission))}</span><span class='trade-status {status_class}'>{escape(status)}</span>"
            f"</div>"
            f"</div>"
        )

    return (
        f"<div class='trade-history desktop-only'>{rows}</div>"
        f"<div class='trade-card-list mobile-only'>{cards}</div>"
    )


def render_closed_trades_table(round_trips: list[dict]) -> str:
    if not round_trips:
        return "<div class='trade-history-empty'>No closed trades</div>"

    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>SYMBOL</span>"
        "<span>OPEN</span>"
        "<span>CLOSE</span>"
        "<span>EXIT</span>"
        "<span>PNL</span>"
        "</div>"
    )
    rows = ""
    cards = ""
    for trip in round_trips[:10]:
        symbol = escape(str(trip.get("symbol") or "-"))
        round_trip_id = escape(str(trip.get("round_trip_id") or "-"))
        opened_at = _format_time_only(trip.get("opened_at"))
        closed_at = _format_time_only(trip.get("closed_at"))
        net_pnl_value = _format_metric(_parse_numeric(trip.get("net_pnl")), signed=True)
        net_pnl = escape(net_pnl_value)
        exit_reason = escape(str(trip.get("exit_reason") or "-"))
        pnl_class = "side-buy" if not net_pnl_value.startswith("-") else "side-sell"
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{symbol}</b> · {round_trip_id}</span>"
            f"<span>{escape(opened_at)}</span>"
            f"<span>{escape(closed_at)}</span>"
            f"<span>{exit_reason}</span>"
            f"<span class='{pnl_class}'>{net_pnl}</span>"
            f"</div>"
        )
        cards += (
            f"<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{symbol}</b><span>{round_trip_id}</span></div>"
            f"<div class='analytics-card-meta'><span>Open {escape(opened_at)}</span><span>Close {escape(closed_at)}</span></div>"
            f"<div class='analytics-card-meta'><span>{exit_reason}</span><span class='{pnl_class}'>{net_pnl}</span></div>"
            f"</div>"
        )
    return (
        f"<div class='analytics-table desktop-only'>{header}{rows}</div>"
        f"<div class='analytics-card-list mobile-only'>{cards}</div>"
    )


def render_stop_slippage_table(stop_exits: list[dict]) -> str:
    if not stop_exits:
        return "<div class='trade-history-empty'>No stop exits</div>"

    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>SYMBOL</span>"
        "<span>STOP</span>"
        "<span>EXEC</span>"
        "<span>SLIP %</span>"
        "<span>PNL</span>"
        "</div>"
    )
    rows = ""
    cards = ""
    for item in stop_exits[:10]:
        symbol = escape(str(item.get("symbol") or "-"))
        trigger_price = escape(_format_price(item.get("trigger_price")))
        average_exit_price = escape(_format_price(item.get("average_exit_price")))
        slippage_pct_value = _format_pct_value(item.get("slippage_pct"), signed=True)
        slippage_pct = escape(slippage_pct_value)
        net_pnl_value = _format_metric(_parse_numeric(item.get("net_pnl")), signed=True)
        net_pnl = escape(net_pnl_value)
        pnl_class = "side-buy" if not net_pnl_value.startswith("-") else "side-sell"
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{symbol}</b></span>"
            f"<span>{trigger_price}</span>"
            f"<span>{average_exit_price}</span>"
            f"<span>{slippage_pct}</span>"
            f"<span class='{pnl_class}'>{net_pnl}</span>"
            f"</div>"
        )
        cards += (
            f"<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{symbol}</b><span>{slippage_pct}</span></div>"
            f"<div class='analytics-card-meta'><span>Stop {trigger_price}</span><span>Exec {average_exit_price}</span></div>"
            f"<div class='analytics-card-meta'><span>Net</span><span class='{pnl_class}'>{net_pnl}</span></div>"
            f"</div>"
        )
    return (
        f"<div class='analytics-table desktop-only'>{header}{rows}</div>"
        f"<div class='analytics-card-list mobile-only'>{cards}</div>"
    )


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

    def _position_sort_key(position: dict) -> tuple[bool, float, str]:
        risk_value = _parse_numeric(position.get("risk"))
        return (risk_value is None, -(risk_value or 0.0), str(position.get("symbol") or ""))

    def _display_metric_value(value: object | None, *, suffix: str = "") -> str:
        if value in (None, ""):
            return "n/a"
        return f"{escape(str(value))}{suffix}"

    def _display_live_price_metric(value: object | None, *, suffix: str = "") -> str:
        if value in (None, ""):
            return "n/a"
        if isinstance(value, (int, float)):
            return f"{_format_metric(float(value))}{suffix}"
        return f"{escape(str(value))}{suffix}"

    cards = ""
    for pos in sorted(positions, key=_position_sort_key):
        symbol = escape(str(pos.get("symbol") or "-"))
        direction = escape(str(pos.get("direction") or "LONG"))
        qty = escape(str(pos.get("total_quantity") or "0"))
        entry = escape(str(pos.get("entry_price") or "n/a"))
        stop = escape(str(pos.get("stop_price") or "n/a"))
        risk = _display_metric_value(pos.get("risk"), suffix=" USDT")
        risk_pct = _display_metric_value(pos.get("risk_pct_of_equity"), suffix="%")
        leg_count = _display_metric_value(pos.get("leg_count"))
        opened_at = _display_metric_value(format_timestamp_for_display(pos.get("opened_at")))
        latest_price = _display_live_price_metric(pos.get("latest_price"))
        mtm_pnl = _display_live_price_metric(pos.get("mtm_pnl"))
        pnl_pct = _display_live_price_metric(pos.get("pnl_pct"), suffix="%")
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
            f"<div class='position-metric position-risk'><span class='metric-label'>Risk</span><span class='metric-value'>{risk}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Risk %</span><span class='metric-value'>{risk_pct}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Legs</span><span class='metric-value'>{leg_count}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Opened</span><span class='metric-value'>{opened_at}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>Last</span><span class='metric-value'>{latest_price}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>MTM</span><span class='metric-value'>{mtm_pnl}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>PnL %</span><span class='metric-value'>{pnl_pct}</span></div>"
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
    account_metric_flows: list[dict] = []
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
        account_metric_flows = fetch_recent_account_flows(path=runtime_db_file, limit=1440)
        recent_trade_round_trips = fetch_recent_trade_round_trips(path=runtime_db_file, limit=20)
        recent_stop_exit_summaries = fetch_recent_stop_exit_summaries(path=runtime_db_file, limit=20)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_account_snapshots = fetch_recent_account_snapshots(path=runtime_db_file, limit=1440)
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
        "account_metric_flows": account_metric_flows,
        "recent_trade_round_trips": recent_trade_round_trips,
        "recent_stop_exit_summaries": recent_stop_exit_summaries,
        "recent_position_snapshots": recent_position_snapshots,
        "recent_account_snapshots": recent_account_snapshots,
        "state_positions": state_payload.get("positions") or {},
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
    numeric_value = float(value)
    if signed and numeric_value == 0:
        return "0.00"
    if signed:
        return f"{numeric_value:+,.2f}"
    return f"{numeric_value:,.2f}"


def _format_price(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    magnitude = abs(numeric)
    if magnitude >= 100:
        return f"{numeric:,.2f}"
    if magnitude >= 1:
        return f"{numeric:,.4f}"
    return f"{numeric:,.6f}"


def _format_quantity(value: object | None) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    return f"{numeric:,.4f}".rstrip("0").rstrip(".")


def _format_pct_value(value: object | None, *, signed: bool = False) -> str:
    numeric = _parse_numeric(value)
    if numeric is None:
        return "n/a"
    if signed and numeric != 0:
        return f"{numeric:+,.2f}%"
    return f"{numeric:,.2f}%"


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
            short_time = _format_time_short(timestamp)
            timeline += f"<text x='{x:.2f}' y='{line_y + 28:.2f}' class='timeline-time' text-anchor='middle'>{escape(short_time)}</text>"
    return f"<svg viewBox='0 0 {width} {height}' class='timeline-svg'>{timeline}</svg>"


def _compute_account_range_stats(points: list[dict], metric: str = "equity") -> dict[str, float | None]:
    if not points:
        return {
            "current_wallet": None,
            "current_equity": None,
            "current_adjusted_equity": None,
            "current_unrealized_pnl": None,
            "current_positions": None,
            "current_orders": None,
            "metric_change": None,
            "peak_equity": None,
            "drawdown_abs": None,
            "drawdown_pct": None,
        }
    first = points[0]
    last = points[-1]
    peak_equity = max((_parse_numeric(point.get("equity")) or 0.0) for point in points)
    current_equity = _parse_numeric(last.get("equity"))
    current_adjusted_equity = _parse_numeric(last.get("adjusted_equity"))
    current_wallet = _parse_numeric(last.get("wallet_balance"))
    current_pnl = _parse_numeric(last.get("unrealized_pnl"))
    metric_first = _parse_numeric(first.get(metric))
    metric_last = _parse_numeric(last.get(metric))
    metric_change = None
    if metric_first is not None and metric_last is not None:
        metric_change = metric_last - metric_first
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
        "current_positions": last.get("position_count"),
        "current_orders": last.get("open_order_count"),
        "metric_change": metric_change,
        "peak_equity": peak_equity,
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


def _build_account_metrics_panel(points: list[dict]) -> str:
    stats = _compute_account_range_stats(points)
    discontinuity_note = _detect_account_discontinuity(points)
    note_html = f"<div class='account-panel-note'>{escape(discontinuity_note)}</div>" if discontinuity_note else ""
    data_json = json.dumps(points, ensure_ascii=False)
    initial_chart = (
        "<div class='chart-empty'><span class='chart-empty-icon'>◎</span><span>waiting for account history</span></div>"
        if not points
        else "<div id='account-metrics-chart' class='account-main-chart'></div>"
    )
    return (
        "<section class='dashboard-section account-metrics-panel'>"
        "<div class='section-header'>ACCOUNT METRICS</div>"
        "<div class='account-panel-header'>"
        "<div><div class='account-panel-title'>ACCOUNT OVERVIEW</div>"
        "<div class='account-panel-subtitle'>Wallet, equity, drawdown, and time-ranged performance from account snapshots.</div></div>"
        f"{note_html}"
        "<div class='account-range-switches'>"
        "<button type='button' class='account-chip' data-account-range=\"1H\">1H</button>"
        "<button type='button' class='account-chip' data-account-range=\"6H\">6H</button>"
        "<button type='button' class='account-chip active' data-account-range=\"24H\">24H</button>"
        "<button type='button' class='account-chip' data-account-range=\"ALL\">ALL</button>"
        "</div></div>"
        "<div class='account-overview-grid'>"
        "<div class='account-overview-card'><div class='account-overview-label'>WALLET BALANCE</div>"
        f"<div class='account-overview-value' data-account-value='wallet_balance'>{escape(_format_metric(stats['current_wallet']))}</div>"
        "<div class='account-overview-sub' data-account-delta='wallet_balance'>Range Δ n/a</div></div>"
        "<div class='account-overview-card'><div class='account-overview-label'>EQUITY</div>"
        f"<div class='account-overview-value' data-account-value='equity'>{escape(_format_metric(stats['current_equity']))}</div>"
        "<div class='account-overview-sub' data-account-delta='equity'>Range Δ n/a</div></div>"
        "<div class='account-overview-card'><div class='account-overview-label'>ADJUSTED EQUITY</div>"
        f"<div class='account-overview-value' data-account-value='adjusted_equity'>{escape(_format_metric(stats['current_adjusted_equity']))}</div>"
        "<div class='account-overview-sub' data-account-delta='adjusted_equity'>Range Δ n/a</div></div>"
        "<div class='account-overview-card'><div class='account-overview-label'>UNREALIZED PNL</div>"
        f"<div class='account-overview-value' data-account-value='unrealized_pnl'>{escape(_format_metric(stats['current_unrealized_pnl'], signed=True))}</div>"
        "<div class='account-overview-sub' data-account-delta='unrealized_pnl'>Range Δ n/a</div></div>"
        "<div class='account-overview-card'><div class='account-overview-label'>OPEN EXPOSURE</div>"
        f"<div class='account-overview-value' data-account-value='exposure'>{escape(str(stats['current_positions'] or 0))} / {escape(str(stats['current_orders'] or 0))}</div>"
        "<div class='account-overview-sub'>positions / orders</div></div>"
        "<div class='account-overview-card account-overview-card-highlight'><div class='account-overview-label'>PEAK EQUITY</div>"
        f"<div class='account-overview-value' data-account-value='peak_equity'>{escape(_format_metric(stats['peak_equity']))}</div>"
        "<div class='account-overview-sub'>Best visible equity point</div></div>"
        "<div class='account-overview-card account-overview-card-highlight'><div class='account-overview-label'>CURRENT DRAWDOWN</div>"
        f"<div class='account-overview-value' data-account-value='drawdown'>{escape(_format_metric(stats['drawdown_abs'], signed=True))}</div>"
        f"<div class='account-overview-sub' data-account-drawdown-pct>{escape(_format_metric(stats['drawdown_pct'], signed=True))}%</div></div>"
        "</div>"
        "<div class='account-main-panel'>"
        "<div class='account-main-toolbar'>"
        "<div class='account-metric-switches'>"
        "<button type='button' class='account-chip active' data-account-metric=\"equity\">Equity</button>"
        "<button type='button' class='account-chip' data-account-metric=\"adjusted_equity\">Adjusted Equity</button>"
        "<button type='button' class='account-chip' data-account-metric=\"wallet_balance\">Wallet</button>"
        "<button type='button' class='account-chip' data-account-metric=\"unrealized_pnl\">Unrealized PnL</button>"
        "</div>"
        "<div class='account-main-meta'><span data-account-window-label>Visible Range</span><span data-account-point-count>"
        f"{len(points)} points</span></div>"
        "</div>"
        f"{initial_chart}"
        f"<script id='account-metrics-json' type='application/json'>{data_json}</script>"
        "</div>"
        "</section>"
    )


def normalize_dashboard_tab(value: str | None) -> str:
    tab = (value or "").strip().lower()
    return tab if tab in DASHBOARD_TABS else "overview"


def render_dashboard_tab_bar(active_tab: str) -> str:
    labels = {
        "overview": "Overview",
        "execution": "Execution",
        "performance": "Performance",
        "system": "System",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if tab == active_tab else ""}" '
            f'data-dashboard-tab="{tab}" href="/?tab={tab}">{escape(labels[tab])}</a>'
        )
        for tab in DASHBOARD_TABS
    )
    return (
        '<nav class="dashboard-tabs" data-dashboard-section="tab-bar" aria-label="Dashboard views">'
        f"{links}"
        "</nav>"
    )


def render_dashboard_overview_tab(*, top_metrics_html: str, position_cards_html: str, account_metrics_panel_html: str, hero_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-tab-content="overview">'
        f"<div class='metrics-grid'>{top_metrics_html}</div>"
        f"{hero_html}"
        "<section class='section-frame' data-collapsible-section='positions'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>ACTIVE POSITIONS</div>"
        "<button type='button' class='section-toggle' data-section-toggle='positions'>Collapse</button>"
        "</div>"
        f"<div class='dashboard-section section-body'>{position_cards_html}</div>"
        "</section>"
        "<section class='section-frame' data-collapsible-section='account'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>ACCOUNT METRICS</div>"
        "<button type='button' class='section-toggle' data-section-toggle='account'>Collapse</button>"
        "</div>"
        f"<div class='section-body'>{account_metrics_panel_html}</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_execution_tab(*, execution_summary_html: str, trade_history_html: str, stop_slippage_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-tab-content="execution">'
        "<section class='section-frame' data-collapsible-section='execution'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>EXECUTION QUALITY</div>"
        "<button type='button' class='section-toggle' data-section-toggle='execution'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Execution Summary</div>"
        f"{execution_summary_html}"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Recent Fills</div>"
        f"<div class='table-scroll'>{trade_history_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div class='section-header' style='margin-bottom:10px;'>STOP SLIPPAGE ANALYSIS</div>"
        f"<div class='table-scroll'>{stop_slippage_html}</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_performance_tab(*, closed_trades_html: str, performance_summary_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-tab-content="performance">'
        "<section class='section-frame' data-collapsible-section='performance'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>STRATEGY PERFORMANCE</div>"
        "<button type='button' class='section-toggle' data-section-toggle='performance'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Round Trips</div>"
        f"<div class='table-scroll'>{closed_trades_html}</div>"
        "</div>"
        f"<div class='chart-card'>{performance_summary_html}</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_system_tab(*, config_html: str, source_html: str, health_items_html: str, recent_events_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-tab-content="system">'
        "<section class='section-frame' data-collapsible-section='system'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>SYSTEM PANELS</div>"
        "<button type='button' class='section-toggle' data-section-toggle='system'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section bottom-row section-body'>"
        "<div class='bottom-col'>"
        "<div class='section-header'>SYSTEM OPERATIONS</div>"
        f"{config_html}"
        "<div class='section-header' style='margin-top:12px;'>EVENT SOURCES</div>"
        f"<div class='source-tags'>{source_html}</div>"
        "</div>"
        "<div class='bottom-col'>"
        "<div class='section-header'>SYSTEM HEALTH</div>"
        f"<div class='health-grid'>{health_items_html}</div>"
        "</div>"
        "<div class='bottom-col'>"
        "<div class='section-header'>RECENT EVENTS</div>"
        f"<div class='event-list' style='max-height:200px;overflow-y:auto;'>{recent_events_html}</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_shell(*, health_status: str, latest_update_display: str | None, active_tab: str, tab_bar_html: str, tab_content_html: str) -> str:
    return (
        "<body>"
        "<div class='app'>"
        "<div class='app-shell'>"
        "<header class='header'>"
        "<div class='header-left'>"
        "<div class='logo'>M</div>"
        "<div class='title-group'>"
        "<h1>Momentum Alpha</h1>"
        "<p>Leader Rotation Strategy · Real-time Trading Monitor</p>"
        "</div>"
        "</div>"
        f"<div class='status-badge {'ok' if health_status == 'OK' else 'fail'}' data-dashboard-section='status'>{escape(health_status)}</div>"
        "</header>"
        "<div class='toolbar' data-dashboard-section='toolbar'>"
        f"<div class='status-line'>Last update <strong id='last-updated-text'>{escape(format_timestamp_for_display(latest_update_display))}</strong></div>"
        "<div class='status-line'>Auto refresh 5s</div>"
        "<div class='toolbar-spacer'></div>"
        "<button type='button' class='action-button' id='manual-refresh-button'>MANUAL REFRESH</button>"
        "</div>"
        f"{tab_bar_html}"
        f"<div class='dashboard-tab-shell' data-dashboard-active-tab='{active_tab}'>{tab_content_html}</div>"
        "</div>"
        "</div>"
    )


def render_dashboard_html(snapshot: dict, strategy_config: dict | None = None, active_tab: str | None = None) -> str:
    active_tab = normalize_dashboard_tab(active_tab)
    timeseries = build_dashboard_timeseries_payload(snapshot)
    runtime = snapshot["runtime"]
    latest_signal = runtime.get("latest_signal_decision") or {}
    latest_position_snapshot = runtime.get("latest_position_snapshot") or {}
    latest_account_snapshot = runtime.get("latest_account_snapshot") or {}
    latest_signal_payload = latest_signal.get("payload") or {}
    blocked_reason = latest_signal_payload.get("blocked_reason")
    decision_status = latest_signal.get("decision_type") or "none"
    latest_signal_symbol = latest_signal.get("symbol") or "none"
    latest_signal_time = format_timestamp_for_display(latest_signal.get("timestamp"))
    account_metrics_panel_html = _build_account_metrics_panel(timeseries["account"])
    account_range_stats = _compute_account_range_stats(timeseries["account"])
    event_counts = snapshot.get("event_counts", {})
    decision_counts = {k: v for k, v in event_counts.items() if "decision" in k.lower() or "entry" in k.lower() or "signal" in k.lower()} or event_counts
    leader_history = list(reversed(snapshot.get("leader_history", [])))
    timeline_chart = _render_timeline_svg(events=leader_history)
    health_status = snapshot["health"]["overall_status"]
    # Build position cards
    equity_value = latest_account_snapshot.get("equity")
    position_details = build_position_details(latest_position_snapshot, equity_value=equity_value)
    if not position_details and snapshot.get("state_positions"):
        position_details = _build_position_details_from_state_positions(
            snapshot.get("state_positions") or {},
            equity_value=equity_value,
        )
    trader_metrics = build_trader_summary_metrics(
        snapshot,
        position_details=position_details,
        range_key="24H",
    )
    position_cards_html = render_position_cards(position_details)
    # Build trade history
    trade_fills = snapshot.get("recent_trade_fills") or []
    trade_history_html = render_trade_history_table(trade_fills)
    closed_trades_html = render_closed_trades_table(snapshot.get("recent_trade_round_trips") or [])
    stop_slippage_html = render_stop_slippage_table(snapshot.get("recent_stop_exit_summaries") or [])
    # Build strategy config
    config = strategy_config or snapshot.get("strategy_config") or {}
    config_html = (
        f"<div class='config-panel'>"
        f"<div class='config-row'><span class='config-label'>Stop Budget</span><span>{escape(str(config.get('stop_budget_usdt') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Entry Window</span><span>{escape(str(config.get('entry_window') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Testnet</span><span class='{'config-value-true' if config.get('testnet') else 'config-value-false'}'>{'Yes' if config.get('testnet') else 'No'}</span></div>"
        f"<div class='config-row'><span class='config-label'>Submit Orders</span><span class='{'config-value-true' if config.get('submit_orders') else 'config-value-false'}'>{'Yes' if config.get('submit_orders') else 'No'}</span></div>"
        f"</div>"
    )
    latest_update_display = max(
        [
            timestamp
            for timestamp in (
                runtime.get("latest_tick_result_timestamp"),
                latest_signal.get("timestamp"),
                (snapshot.get("recent_events") or [{}])[0].get("timestamp") if snapshot.get("recent_events") else None,
            )
            if timestamp
        ],
        default=None,
    )
    health_items_html = "".join(
        f"<div class='health-item status-{escape(item['status'].lower())}'>"
        f"<span class='health-status-dot'></span>"
        f"<span class='health-name'>{escape(item['name'])}</span>"
        f"<span class='health-status'>{escape(item['status'])}</span>"
        f"<span class='health-msg'>{escape(item['message'])}</span></div>"
        for item in snapshot["health"]["items"]
    )
    recent_events_html = "".join(
        f"<div class='event-item'>"
        f"<span class='event-type'>{escape(e['event_type'])}</span>"
        f"<span class='event-time'>{escape(format_timestamp_for_display(e['timestamp']))}</span>"
        f"<span class='event-source'>{escape(str(e.get('source') or '-'))}</span></div>"
        for e in snapshot["recent_events"][:12]
    ) or "<div class='event-item empty'>No recent events</div>"
    source_counts = snapshot.get("source_counts", {})
    source_html = "".join(
        f"<div class='source-tag'><span>{escape(src)}</span><b>{cnt}</b></div>"
        for src, cnt in sorted(source_counts.items())[:4]
    ) or "<div class='source-tag empty'>No sources</div>"

    def _format_pct(value: float | None, *, signed: bool = False) -> str:
        if value is None:
            return "n/a"
        if signed and float(value) == 0:
            return "0.00%"
        return f"{value:+,.2f}%" if signed else f"{value:,.2f}%"

    performance_win_rate = trader_metrics["performance"].get("win_rate")
    health_metric_state = "danger" if health_status != "OK" else ""
    blocked_reason_counts = trader_metrics["signals"].get("blocked_reason_counts", {})
    blocked_reason_summary = ", ".join(
        f"{reason}: {count}"
        for reason, count in blocked_reason_counts.items()
    ) or "No blocked signals"
    blocked_reason_breakdown_html = (
        "<div class='signal-breakdown'>"
        + "".join(
            f"<div class='signal-breakdown-item'><span class='signal-breakdown-label'>{escape(str(reason))}</span><span class='signal-breakdown-count'>{escape(str(count))}</span></div>"
            for reason, count in blocked_reason_counts.items()
        )
        + "</div>"
        if blocked_reason_counts
        else "<div class='signal-breakdown-empty compact'>No blocked signals</div>"
    )
    recent_leader_sequence = [str(item.get("symbol") or "-") for item in leader_history[:5]]
    recent_leader_sequence_html = (
        " \u2192 ".join(recent_leader_sequence)
        if len(recent_leader_sequence) >= 2
        else "insufficient history"
    )
    open_risk_pct = trader_metrics["account"].get("open_risk_pct")
    if open_risk_pct is None:
        open_risk_state = ""
    elif open_risk_pct > 60:
        open_risk_state = "danger"
    elif open_risk_pct >= 30:
        open_risk_state = "warning"
    else:
        open_risk_state = "normal"
    top_metric_cards = [
        (
            "EQUITY",
            _format_metric(trader_metrics["account"].get("current_equity")),
            "Latest account snapshot",
            "",
        ),
        (
            "TODAY NET PNL",
            _format_metric(trader_metrics["account"].get("today_net_pnl"), signed=True),
            "Adjusted equity delta across visible account history",
            "",
        ),
        (
            "OPEN RISK / EQUITY",
            _format_pct(trader_metrics["account"].get("open_risk_pct")),
            f"{_format_metric(trader_metrics['account'].get('open_risk'))} USDT at risk",
            open_risk_state,
        ),
        (
            "SYSTEM HEALTH",
            escape(health_status),
            f"Last update {format_timestamp_for_display(latest_update_display)}",
            health_metric_state,
        ),
    ]
    top_metrics_html = "".join(
        (
            f"<div class='metric {metric_state}'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value {'negative' if str(value).startswith('-') else 'positive' if str(value).startswith('+') else ''}'>{escape(str(value))}</div>"
            f"<div class='metric-sub'>{escape(subtext)}</div>"
            "</div>"
        )
        for label, value, subtext, metric_state in top_metric_cards
    )
    execution_summary_html = (
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Avg Slippage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['execution'].get('avg_slippage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Max Slippage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['execution'].get('max_slippage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Stop Exits</div><div class='decision-value'>{escape(str(trader_metrics['execution'].get('stop_exit_count') or 0))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Fee Total</div><div class='decision-value'>{escape(_format_metric(trader_metrics['execution'].get('fee_total')))}</div></div>"
        "</div>"
    )
    performance_summary_html = (
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Win Rate</div><div class='decision-value'>{escape(_format_pct(performance_win_rate * 100) if performance_win_rate is not None else 'n/a')}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Profit Factor</div><div class='decision-value'>{escape(_format_metric(trader_metrics['performance'].get('profit_factor')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Avg Win</div><div class='decision-value'>{escape(_format_metric(trader_metrics['performance'].get('avg_win')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Avg Loss</div><div class='decision-value'>{escape(_format_metric(trader_metrics['performance'].get('avg_loss'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Expectancy</div><div class='decision-value'>{escape(_format_metric(trader_metrics['performance'].get('expectancy'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Avg Hold</div><div class='decision-value'>{escape(_format_duration_seconds(trader_metrics['performance'].get('avg_hold_time_seconds')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Streak</div><div class='decision-value'>{escape(str((trader_metrics['performance'].get('current_streak') or {}).get('label') or 'n/a'))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Trade Count</div><div class='decision-value'>{escape(str(trader_metrics['performance'].get('trade_count') or 0))}</div></div>"
        "</div>"
    )
    risk_overview_html = (
        "<div class='decision-grid decision-grid-stack'>"
        f"<div class='decision-item'><div class='decision-label'>Available Balance</div><div class='decision-value'>{escape(_format_metric(trader_metrics['account'].get('current_available_balance')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Margin Usage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['account'].get('margin_usage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Drawdown</div><div class='decision-value'>{escape(_format_metric(account_range_stats.get('drawdown_abs'), signed=True))}</div><div class='decision-support'>{escape(_format_pct(account_range_stats.get('drawdown_pct'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Positions / Orders</div><div class='decision-value'>{escape(str(trader_metrics['account'].get('current_positions') or 0))} / {escape(str(trader_metrics['account'].get('current_orders') or 0))}</div></div>"
        "</div>"
    )
    hero_html = (
        "<section class='hero-grid'>"
        "<div class='hero-card hero-card-wide'>"
        "<div class='hero-eyebrow'>LIVE OVERVIEW</div>"
        "<div class='hero-title'>ACTIVE SIGNAL</div>"
        "<div class='hero-copy'>Keep the current decision, rotation context, and blocked reasons in one glance before drilling into execution details.</div>"
        "<div class='decision-grid'>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Decision Type</div>"
        f"<div class='decision-value'>{escape(str(decision_status))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Target Symbol</div>"
        f"<div class='decision-value'>{escape(str(latest_signal_symbol))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Blocked Reason</div>"
        f"<div class='decision-value'>{escape(str(blocked_reason or 'None'))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Decision Time</div>"
        f"<div class='decision-value'>{escape(latest_signal_time)}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Rotation Count</div>"
        f"<div class='decision-value'>{escape(str(trader_metrics['signals'].get('rotation_count') or 0))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Blocked Reasons</div>"
        f"{f'<div class=\"decision-value\" style=\"margin-bottom:8px;\">{escape(blocked_reason_summary)}</div>' if blocked_reason_counts else ''}"
        f"{blocked_reason_breakdown_html}"
        "</div>"
        "</div>"
        "</div>"
        "<div class='hero-card hero-card-compact'>"
        "<div class='hero-eyebrow'>RISK &amp; DEPLOYMENT</div>"
        "<div class='hero-title'>Capital Pressure</div>"
        "<div class='hero-copy'>Balance available capital against live drawdown and deployed risk before the next tick updates the book.</div>"
        f"{risk_overview_html}"
        "</div>"
        "<div class='hero-card hero-card-compact'>"
        "<div class='hero-eyebrow'>LEADER ROTATION</div>"
        "<div class='hero-title'>Sequence Monitor</div>"
        f"<div class='chart-container'>{timeline_chart}</div>"
        "<div class='rotation-summary'>"
        "<div class='rotation-summary-label'>Recent Sequence</div>"
        f"<div class='rotation-summary-value'>{escape(recent_leader_sequence_html)}</div>"
        "</div>"
        "</div>"
        "</section>"
    )
    tab_bar_html = render_dashboard_tab_bar(active_tab)
    tab_content_html = {
        "overview": render_dashboard_overview_tab(
            top_metrics_html=top_metrics_html,
            position_cards_html=position_cards_html,
            account_metrics_panel_html=account_metrics_panel_html,
            hero_html=hero_html,
        ),
        "execution": render_dashboard_execution_tab(
            execution_summary_html=execution_summary_html,
            trade_history_html=trade_history_html,
            stop_slippage_html=stop_slippage_html,
        ),
        "performance": render_dashboard_performance_tab(
            closed_trades_html=closed_trades_html,
            performance_summary_html=performance_summary_html,
        ),
        "system": render_dashboard_system_tab(
            config_html=config_html,
            source_html=source_html,
            health_items_html=health_items_html,
            recent_events_html=recent_events_html,
        ),
    }[active_tab]

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
      font-family: 'SF Pro Display', 'Segoe UI', 'PingFang SC', 'Hiragino Sans GB', sans-serif;
      background:
        radial-gradient(circle at top right, rgba(0,212,255,0.08), transparent 32%),
        radial-gradient(circle at top left, rgba(255,184,0,0.06), transparent 28%),
        var(--bg-deep);
      color: var(--fg);
      min-height: 100vh;
      line-height: 1.5;
    }}
    .app {{
      max-width: 1600px;
      margin: 0 auto;
      padding: 24px;
    }}
    .app-shell {{
      position: relative;
      border: 1px solid rgba(100,130,170,0.12);
      border-radius: 28px;
      padding: 28px;
      background: linear-gradient(180deg, rgba(8,14,23,0.92), rgba(5,9,16,0.98));
      box-shadow: 0 24px 80px rgba(0,0,0,0.35);
      overflow: hidden;
    }}
    .app-shell::before {{
      content: '';
      position: absolute;
      inset: 0;
      background:
        linear-gradient(90deg, rgba(255,255,255,0.015) 1px, transparent 1px),
        linear-gradient(rgba(255,255,255,0.015) 1px, transparent 1px);
      background-size: 36px 36px;
      mask-image: linear-gradient(180deg, rgba(0,0,0,0.45), transparent 70%);
      pointer-events: none;
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
    .metric.warning {{
      border-color: rgba(255,184,0,0.35);
      box-shadow: 0 0 0 1px rgba(255,184,0,0.08);
    }}
    .metric.danger {{
      border-color: rgba(255,68,102,0.38);
      box-shadow: 0 0 0 1px rgba(255,68,102,0.1);
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
    .hero-grid {{
      display: grid;
      grid-template-columns: 1.2fr 0.9fr 0.9fr;
      gap: 16px;
      margin-bottom: 20px;
    }}
    .hero-card {{
      position: relative;
      padding: 18px;
      border-radius: 22px;
      border: 1px solid rgba(100,130,170,0.18);
      background: linear-gradient(160deg, rgba(15,23,38,0.92), rgba(8,12,19,0.96));
      overflow: hidden;
    }}
    .hero-card::before {{
      content: '';
      position: absolute;
      inset: 0 auto auto 0;
      width: 120px;
      height: 120px;
      background: radial-gradient(circle, rgba(0,212,255,0.16), transparent 68%);
      pointer-events: none;
    }}
    .hero-card-wide {{
      min-height: 240px;
    }}
    .hero-card-compact {{
      min-height: 240px;
    }}
    .hero-eyebrow {{
      position: relative;
      font-size: 0.68rem;
      letter-spacing: 0.16em;
      color: var(--accent);
      text-transform: uppercase;
      margin-bottom: 10px;
    }}
    .hero-title {{
      position: relative;
      font-size: 1.25rem;
      font-weight: 700;
      margin-bottom: 12px;
    }}
    .hero-copy {{
      position: relative;
      max-width: 32rem;
      font-size: 0.84rem;
      color: var(--fg-muted);
      margin-bottom: 16px;
    }}
    .toolbar {{
      display: flex;
      align-items: center;
      gap: 12px;
      flex-wrap: wrap;
      margin-bottom: 20px;
    }}
    .dashboard-tabs {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      margin-bottom: 20px;
      padding: 10px;
      border: 1px solid var(--border);
      border-radius: 18px;
      background: rgba(255,255,255,0.02);
    }}
    .dashboard-tab {{
      display: inline-flex;
      align-items: center;
      justify-content: center;
      min-width: 120px;
      padding: 10px 16px;
      border-radius: 999px;
      border: 1px solid transparent;
      color: var(--fg-muted);
      text-decoration: none;
      font-size: 0.76rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      transition: transform 0.2s, background 0.2s, border-color 0.2s, color 0.2s;
    }}
    .dashboard-tab:hover {{
      transform: translateY(-1px);
      color: var(--fg);
      background: rgba(255,255,255,0.04);
    }}
    .dashboard-tab.is-active {{
      color: var(--fg);
      border-color: var(--border-accent);
      background: rgba(0,212,255,0.1);
      box-shadow: 0 0 0 1px rgba(0,212,255,0.08);
    }}
    .dashboard-tab-shell {{
      min-height: 480px;
    }}
    .dashboard-tab-panel {{
      display: block;
    }}
    .toolbar-spacer {{
      flex: 1;
    }}
    .status-line {{
      display: inline-flex;
      align-items: center;
      gap: 10px;
      padding: 8px 12px;
      border-radius: 999px;
      background: rgba(255,255,255,0.04);
      border: 1px solid var(--border);
      color: var(--fg-muted);
      font-size: 0.76rem;
    }}
    .action-button {{
      border: 1px solid var(--border-accent);
      background: rgba(0,212,255,0.08);
      color: var(--fg);
      border-radius: 999px;
      padding: 9px 14px;
      font-size: 0.72rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      cursor: pointer;
      transition: transform 0.2s, background 0.2s, border-color 0.2s;
    }}
    .action-button:hover {{
      transform: translateY(-1px);
      background: rgba(0,212,255,0.16);
    }}
    .action-button.is-refreshing {{
      border-color: rgba(255,184,0,0.35);
      background: rgba(255,184,0,0.1);
    }}
    .section-frame {{
      margin-bottom: 20px;
    }}
    .section-topbar {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 10px;
    }}
    .section-toggle {{
      border: 1px solid var(--border);
      background: rgba(255,255,255,0.03);
      color: var(--fg-muted);
      border-radius: 999px;
      padding: 6px 11px;
      font-size: 0.68rem;
      letter-spacing: 0.12em;
      text-transform: uppercase;
      cursor: pointer;
    }}
    .section-frame.is-collapsed .section-body {{
      display: none;
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
    .signal-breakdown {{
      display: flex;
      flex-direction: column;
      gap: 8px;
    }}
    .signal-breakdown-item {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      padding: 10px 12px;
      background: rgba(0,0,0,0.18);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }}
    .signal-breakdown-label {{
      font-size: 0.8rem;
      color: var(--fg);
      word-break: break-word;
    }}
    .signal-breakdown-count {{
      min-width: 28px;
      padding: 2px 8px;
      border-radius: 999px;
      background: rgba(0,212,255,0.12);
      color: var(--accent);
      font-size: 0.78rem;
      font-weight: 700;
      text-align: center;
    }}
    .signal-breakdown-empty {{
      padding: 10px 12px;
      background: rgba(0,0,0,0.18);
      border: 1px dashed var(--border);
      border-radius: var(--radius-sm);
      font-size: 0.78rem;
      color: var(--fg-muted);
    }}
    .signal-breakdown-empty.compact {{
      padding: 8px 10px;
      display: inline-flex;
      align-items: center;
      min-height: auto;
    }}
    .rotation-summary {{
      margin-top: 10px;
      padding: 10px 12px;
      background: rgba(0,0,0,0.18);
      border: 1px solid var(--border);
      border-radius: var(--radius-sm);
    }}
    .rotation-summary-label {{
      font-size: 0.68rem;
      color: var(--fg-muted);
      text-transform: uppercase;
      letter-spacing: 0.1em;
      margin-bottom: 6px;
    }}
    .rotation-summary-value {{
      font-size: 0.82rem;
      color: var(--fg);
      word-break: break-word;
    }}
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
    .refresh-indicator.error {{
      border-color: rgba(255,68,102,0.35);
      color: var(--danger);
    }}
    .refresh-dot {{
      width: 8px;
      height: 8px;
      background: var(--success);
      border-radius: 50%;
      animation: blink 1s infinite;
    }}
    .refresh-indicator.error .refresh-dot {{
      background: var(--danger);
      animation: none;
    }}
    @keyframes blink {{
      0%, 100% {{ opacity: 1; }}
      50% {{ opacity: 0.3; }}
    }}
    .positions-grid {{ display: grid; grid-template-columns: repeat(2, 1fr); gap: 12px; }}
    .position-card {{ background: rgba(0,0,0,0.3); padding: 14px; border-radius: 8px; border-left: 3px solid var(--success); }}
    .position-header {{ display: flex; justify-content: space-between; margin-bottom: 10px; }}
    .position-symbol {{ font-weight: 700; color: var(--accent); font-family: 'JetBrains Mono', 'SF Mono', monospace; }}
    .position-direction {{ font-size: 0.75rem; color: var(--fg-muted); }}
    .position-metrics {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 8px; font-size: 0.82rem; }}
    .position-metric {{ text-align: center; padding: 4px 2px; }}
    .position-metric.position-live {{
      background: rgba(0,212,255,0.06);
      border: 1px solid rgba(0,212,255,0.12);
      border-radius: 8px;
    }}
    .position-metric.position-live .metric-value {{
      font-size: 0.96rem;
      font-weight: 700;
    }}
    .position-metric.position-risk .metric-value {{
      font-size: 0.92rem;
      font-weight: 700;
    }}
    .metric-danger {{ color: var(--danger); }}
    .metric-note {{ display: block; margin-top: 4px; font-size: 0.62rem; color: var(--fg-muted); }}
    .position-legs {{ margin-top: 8px; font-size: 0.7rem; color: var(--fg-muted); }}
    .positions-empty {{ color: var(--fg-muted); text-align: center; padding: 20px; }}
    .trade-history {{ max-height: 200px; overflow-y: auto; }}
    .trade-history-empty {{ color: var(--fg-muted); text-align: center; padding: 20px; }}
    .trade-row {{ display: grid; grid-template-columns: 80px 120px 60px 80px 100px 80px 80px; gap: 8px; padding: 8px 0; border-bottom: 1px solid var(--border); font-size: 0.75rem; }}
    .trade-row:last-child {{ border-bottom: none; }}
    .analytics-grid {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .table-scroll {{ overflow-x: auto; }}
    .desktop-only {{ display: block; }}
    .mobile-only {{ display: none; }}
    .analytics-table.desktop-only {{ display: block; }}
    .analytics-card-list.mobile-only {{ display: none; }}
    .trade-history.desktop-only {{ display: block; }}
    .trade-card-list.mobile-only {{ display: none; }}
    .analytics-table {{ max-height: 220px; overflow-y: auto; }}
    .analytics-row {{ display: grid; grid-template-columns: 1.4fr 0.8fr 0.8fr 0.8fr 0.7fr; gap: 8px; padding: 9px 0; border-bottom: 1px solid var(--border); font-size: 0.78rem; align-items: center; }}
    .analytics-row.analytics-row-header {{
      color: var(--fg-muted);
      font-size: 0.68rem;
      letter-spacing: 0.08em;
      text-transform: uppercase;
      font-weight: 700;
    }}
    .analytics-row:last-child {{ border-bottom: none; }}
    .analytics-main {{ color: var(--fg); overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }}
    .trade-time {{ color: var(--fg-muted); }}
    .trade-symbol {{ color: var(--accent); font-weight: 500; }}
    .side-buy {{ color: var(--success); }}
    .side-sell {{ color: var(--danger); }}
    .status-filled {{ color: var(--success); }}
    .status-pending {{ color: var(--warning); }}
    .trade-card-list, .analytics-card-list {{
      display: flex;
      flex-direction: column;
      gap: 10px;
    }}
    .analytics-card {{
      padding: 12px;
      background: rgba(255,255,255,0.03);
      border: 1px solid var(--border);
      border-radius: 14px;
    }}
    .analytics-card-main {{
      display: flex;
      align-items: center;
      justify-content: space-between;
      gap: 12px;
      margin-bottom: 8px;
      font-size: 0.86rem;
    }}
    .analytics-card-meta {{
      display: flex;
      flex-wrap: wrap;
      gap: 10px;
      color: var(--fg-muted);
      font-size: 0.74rem;
    }}
    .section-header {{ font-size: 0.7rem; color: var(--accent); padding: 4px 0; margin-bottom: 8px; border-bottom: 1px solid var(--border); text-transform: uppercase; letter-spacing: 0.1em; }}
    .config-panel {{ background: rgba(0,0,0,0.3); padding: 12px; border-radius: 8px; font-size: 0.8rem; }}
    .config-row {{ display: flex; justify-content: space-between; padding: 4px 0; }}
    .config-label {{ color: var(--fg-muted); }}
    .config-value-true {{ color: var(--warning); }}
    .config-value-false {{ color: var(--fg-muted); }}
    .dashboard-section {{ margin-bottom: 20px; padding: 16px; background: var(--bg-panel); border: 1px solid var(--border); border-radius: var(--radius); }}
    .charts-row {{ display: grid; grid-template-columns: repeat(3, 1fr); gap: 16px; }}
    .chart-card {{ background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }}
    .account-metrics-panel {{ padding: 20px; }}
    .account-panel-header {{ display: flex; justify-content: space-between; align-items: flex-start; gap: 16px; margin-bottom: 16px; }}
    .account-panel-title {{ font-size: 0.95rem; font-weight: 700; letter-spacing: 0.06em; }}
    .account-panel-subtitle {{ font-size: 0.76rem; color: var(--fg-muted); margin-top: 6px; max-width: 680px; }}
    .account-panel-note {{
      font-size: 0.76rem;
      color: var(--warning);
      max-width: 420px;
      line-height: 1.45;
      padding: 10px 12px;
      background: rgba(255,184,0,0.08);
      border: 1px solid rgba(255,184,0,0.22);
      border-radius: var(--radius-sm);
    }}
    .account-range-switches, .account-metric-switches {{ display: flex; flex-wrap: wrap; gap: 8px; }}
    .account-chip {{ border: 1px solid var(--border); background: rgba(0,0,0,0.24); color: var(--fg-muted); border-radius: 999px; padding: 8px 12px; font-size: 0.72rem; cursor: pointer; transition: all 0.2s; }}
    .account-chip.active {{ color: var(--accent); border-color: var(--border-accent); background: rgba(0,212,255,0.08); }}
    .account-overview-grid {{ display: grid; grid-template-columns: repeat(6, 1fr); gap: 12px; margin-bottom: 16px; }}
    .account-overview-card {{ background: rgba(0,0,0,0.2); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 14px; min-height: 98px; }}
    .account-overview-card-highlight {{ background: rgba(0,212,255,0.05); border-color: var(--border-accent); }}
    .account-overview-label {{ font-size: 0.68rem; color: var(--fg-muted); letter-spacing: 0.1em; text-transform: uppercase; margin-bottom: 8px; }}
    .account-overview-value {{ font-size: 1.2rem; font-weight: 700; }}
    .account-overview-sub {{ font-size: 0.72rem; color: var(--fg-muted); margin-top: 8px; }}
    .account-main-panel {{ background: rgba(0,0,0,0.22); border: 1px solid var(--border); border-radius: var(--radius-sm); padding: 16px; }}
    .account-main-toolbar {{ display: flex; justify-content: space-between; align-items: center; gap: 16px; margin-bottom: 14px; }}
    .account-main-meta {{ display: flex; gap: 16px; font-size: 0.72rem; color: var(--fg-muted); }}
    .account-main-chart {{ min-height: 280px; }}
    .account-chart-svg {{ width: 100%; height: auto; display: block; }}
    .account-grid-line {{ stroke: rgba(100,130,170,0.12); stroke-width: 1; }}
    .account-axis-label {{ fill: var(--fg-muted); font-size: 10px; }}
    .account-series-line {{ fill: none; stroke-width: 2.5; stroke-linecap: round; stroke-linejoin: round; }}
    .account-series-area {{ opacity: 0.18; }}
    .account-last-dot {{ filter: drop-shadow(0 0 6px currentColor); }}
    .decision-row {{ display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }}
    .decision-half {{ background: rgba(0,0,0,0.2); border-radius: var(--radius-sm); padding: 12px; }}
    .bottom-row {{ display: grid; grid-template-columns: 200px 1fr 1fr; gap: 16px; }}
    .decision-grid-stack {{ grid-template-columns: 1fr 1fr; }}
    .decision-support {{ margin-top: 6px; color: var(--fg-muted); font-size: 0.76rem; }}
    .bottom-col {{ }}
    @media (max-width: 1200px) {{
      .metrics-grid {{ grid-template-columns: repeat(2, 1fr); }}
      .hero-grid {{ grid-template-columns: 1fr; }}
      .charts-row {{ grid-template-columns: 1fr; }}
      .decision-row {{ grid-template-columns: 1fr; }}
      .bottom-row {{ grid-template-columns: 1fr; }}
      .account-overview-grid {{ grid-template-columns: repeat(3, 1fr); }}
      .account-panel-header, .account-main-toolbar {{ flex-direction: column; align-items: flex-start; }}
    }}
    @media (max-width: 768px) {{
      .app {{ padding: 12px; }}
      .app-shell {{ padding: 18px; border-radius: 18px; }}
      .metrics-grid {{ grid-template-columns: 1fr; }}
      .header {{ flex-direction: column; align-items: flex-start; gap: 16px; }}
      .dashboard-tabs {{ padding: 8px; gap: 8px; }}
      .dashboard-tab {{ flex: 1 1 calc(50% - 8px); min-width: 0; }}
      .decision-grid {{ grid-template-columns: 1fr; }}
      .positions-grid {{ grid-template-columns: 1fr; }}
      .trade-row {{ min-width: 640px; grid-template-columns: 60px 80px 50px 60px 70px 60px 60px; font-size: 0.7rem; }}
      .analytics-grid {{ grid-template-columns: 1fr; }}
      .analytics-row {{ min-width: 540px; grid-template-columns: 1.2fr 0.8fr 0.8fr 0.8fr 0.7fr; font-size: 0.68rem; }}
      .account-overview-grid {{ grid-template-columns: 1fr; }}
      .desktop-only {{ display: none; }}
      .mobile-only {{ display: block; }}
      .analytics-table.desktop-only {{ display: none; }}
      .analytics-card-list.mobile-only {{ display: flex; }}
      .trade-history.desktop-only {{ display: none; }}
      .trade-card-list.mobile-only {{ display: flex; }}
    }}
  </style>
</head>
{render_dashboard_shell(
    health_status=health_status,
    latest_update_display=latest_update_display,
    active_tab=active_tab,
    tab_bar_html=tab_bar_html,
    tab_content_html=tab_content_html,
)}
  <div class="refresh-indicator {'error' if health_status != 'OK' else ''}" id="refresh-indicator">
    <div class="refresh-dot"></div>
    <span id="refresh-indicator-text">{'Unable to refresh' if health_status != 'OK' else 'Auto refresh: 5s'}</span>
  </div>
  <script>
    const ACCOUNT_METRIC_STORAGE_KEY = 'dashboard.account.metric';
    const ACCOUNT_RANGE_STORAGE_KEY = 'dashboard.account.range';
    const COLLAPSED_SECTIONS_STORAGE_KEY = 'dashboard.collapsed-sections';
    const DASHBOARD_SECTION_SELECTORS = [
      '[data-dashboard-section="status"]',
      '[data-dashboard-section="toolbar"]',
      '[data-dashboard-section="tab-bar"]',
      '[data-dashboard-active-tab]',
    ];

    function getAccountMetricsData() {{
      const jsonNode = document.getElementById('account-metrics-json');
      if (!jsonNode) return [];
      try {{
        return JSON.parse(jsonNode.textContent || '[]');
      }} catch (error) {{
        console.error(error);
        return [];
      }}
    }}
    function getCollapsedSections() {{
      try {{
        return JSON.parse(localStorage.getItem(COLLAPSED_SECTIONS_STORAGE_KEY) || '[]');
      }} catch (error) {{
        return [];
      }}
    }}
    function writeCollapsedSections(nextCollapsedSections) {{
      localStorage.setItem(COLLAPSED_SECTIONS_STORAGE_KEY, JSON.stringify(nextCollapsedSections));
    }}
    function applyCollapsedSections() {{
      const collapsedSections = new Set(getCollapsedSections());
      document.querySelectorAll('[data-collapsible-section]').forEach((section) => {{
        const sectionKey = section.dataset.collapsibleSection;
        const isCollapsed = collapsedSections.has(sectionKey);
        section.classList.toggle('is-collapsed', isCollapsed);
        const toggle = section.querySelector('[data-section-toggle]');
        if (toggle) toggle.textContent = isCollapsed ? 'Expand' : 'Collapse';
      }});
    }}
    function formatAccountValue(value, signed = false, suffix = '') {{
      if (value === null || value === undefined || Number.isNaN(value)) return 'n/a';
      const numericValue = Number(value);
      if (signed && numericValue === 0) return `0.00${{suffix}}`;
      const formatted = numericValue.toLocaleString(undefined, {{ minimumFractionDigits: 2, maximumFractionDigits: 2 }});
      const withSign = signed ? `${{numericValue > 0 ? '+' : ''}}${{formatted}}` : formatted;
      return `${{withSign}}${{suffix}}`;
    }}
    function formatAccountWindowTimestamp(timestamp) {{
      if (!timestamp) return 'n/a';
      const date = new Date(timestamp);
      const parts = new Intl.DateTimeFormat('zh-CN', {{
        hour12: false,
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit'
      }}).formatToParts(date);
      const lookup = Object.fromEntries(parts.map((part) => [part.type, part.value]));
      return `${{lookup.month}}-${{lookup.day}} ${{lookup.hour}}:${{lookup.minute}}`;
    }}
    function filterAccountPoints(points, range) {{
      if (!points.length || range === 'ALL') return points;
      const hours = {{ '1H': 1, '6H': 6, '24H': 24 }}[range] || 24;
      const latest = new Date(points[points.length - 1].timestamp).getTime();
      const cutoff = latest - hours * 60 * 60 * 1000;
      const filtered = points.filter((point) => new Date(point.timestamp).getTime() >= cutoff);
      return filtered.length ? filtered : points;
    }}
    function buildAccountChartSvg(points, metric) {{
      if (!points.length) {{
        return `<div class="chart-empty"><span class="chart-empty-icon">◎</span><span>waiting for account history</span></div>`;
      }}
      const width = 920;
      const height = 280;
      const padX = 56;
      const padY = 20;
      const values = points.map((point) => point[metric]);
      const numericValues = values.filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
      if (!numericValues.length || numericValues.length !== values.length) {{
        return `<div class="chart-empty"><span class="chart-empty-icon">◎</span><span>waiting for visible metric data</span></div>`;
      }}
      const minValue = Math.min(...numericValues);
      const maxValue = Math.max(...numericValues);
      const spread = Math.max(maxValue - minValue, 1e-9);
      const chartWidth = width - padX * 2;
      const chartHeight = height - padY * 2;
      const coords = numericValues.map((value, index) => {{
        const x = padX + (chartWidth * index / Math.max(values.length - 1, 1));
        const y = padY + chartHeight - (((value - minValue) / spread) * chartHeight);
        return [x, y];
      }});
      const polyline = coords.map(([x, y]) => `${{x.toFixed(2)}},${{y.toFixed(2)}}`).join(' ');
      const area = `${{coords[0][0].toFixed(2)}},${{(height - padY).toFixed(2)}} ` + polyline + ` ${{coords[coords.length - 1][0].toFixed(2)}},${{(height - padY).toFixed(2)}}`;
      const palette = {{ equity: '#4cc9f0', adjusted_equity: '#ffbc42', wallet_balance: '#36d98a', unrealized_pnl: '#a855f7' }};
      const stroke = palette[metric] || '#4cc9f0';
      let grid = '';
      let labels = '';
      for (let i = 0; i < 5; i++) {{
        const y = padY + (chartHeight * i / 4);
        const val = maxValue - (spread * i / 4);
        grid += `<line x1="${{padX}}" y1="${{y.toFixed(2)}}" x2="${{width - padX}}" y2="${{y.toFixed(2)}}" class="account-grid-line" />`;
        labels += `<text x="${{padX - 8}}" y="${{(y + 4).toFixed(2)}}" class="account-axis-label" text-anchor="end">${{formatAccountValue(val)}}</text>`;
      }}
      const last = coords[coords.length - 1];
      return `
        <svg viewBox="0 0 ${{width}} ${{height}}" class="account-chart-svg" role="img" aria-label="${{metric}} account chart">
          <defs>
            <linearGradient id="account-gradient-${{metric}}" x1="0%" y1="0%" x2="0%" y2="100%">
              <stop offset="0%" stop-color="${{stroke}}" stop-opacity="0.38"></stop>
              <stop offset="100%" stop-color="${{stroke}}" stop-opacity="0.02"></stop>
            </linearGradient>
          </defs>
          ${{grid}}
          ${{labels}}
          <polygon points="${{area}}" fill="url(#account-gradient-${{metric}})" class="account-series-area"></polygon>
          <polyline points="${{polyline}}" stroke="${{stroke}}" class="account-series-line"></polyline>
          <circle cx="${{last[0].toFixed(2)}}" cy="${{last[1].toFixed(2)}}" r="4" fill="${{stroke}}" class="account-last-dot"></circle>
        </svg>`;
    }}
    function updateAccountOverview(points, metric, range) {{
      if (!points.length) return;
      const first = points[0];
      const last = points[points.length - 1];
      const numericValues = points
        .map((point) => ({{
          equity: point.equity,
          wallet_balance: point.wallet_balance,
          adjusted_equity: point.adjusted_equity,
          unrealized_pnl: point.unrealized_pnl,
        }}));
      const equityPoints = numericValues
        .map((point) => point.equity)
        .filter((value) => value !== null && value !== undefined && !Number.isNaN(value));
      const peakEquity = equityPoints.length ? Math.max(...equityPoints) : null;
      const currentEquity = last.equity;
      const drawdownAbs = (currentEquity === null || currentEquity === undefined || peakEquity === null)
        ? null
        : currentEquity - peakEquity;
      const drawdownPct = (drawdownAbs === null || !peakEquity) ? null : (drawdownAbs / peakEquity) * 100;
      const computeDelta = (start, end) => {{
        if (start === null || start === undefined || end === null || end === undefined) return null;
        return end - start;
      }};
      const deltas = {{
        wallet_balance: computeDelta(first.wallet_balance, last.wallet_balance),
        equity: computeDelta(first.equity, last.equity),
        adjusted_equity: computeDelta(first.adjusted_equity, last.adjusted_equity),
        unrealized_pnl: computeDelta(first.unrealized_pnl, last.unrealized_pnl),
      }};
      const values = {{
        wallet_balance: formatAccountValue(last.wallet_balance),
        equity: formatAccountValue(last.equity),
        adjusted_equity: formatAccountValue(last.adjusted_equity),
        unrealized_pnl: formatAccountValue(last.unrealized_pnl, true),
        exposure: `${{last.position_count ?? 0}} / ${{last.open_order_count ?? 0}}`,
        peak_equity: formatAccountValue(peakEquity),
        drawdown: formatAccountValue(drawdownAbs, true),
      }};
      Object.entries(values).forEach(([key, value]) => {{
        const node = document.querySelector(`[data-account-value="${{key}}"]`);
        if (node) node.textContent = value;
      }});
      ['wallet_balance', 'equity', 'adjusted_equity', 'unrealized_pnl'].forEach((key) => {{
        const node = document.querySelector(`[data-account-delta="${{key}}"]`);
        if (node) node.textContent = `Range Δ ${{formatAccountValue(deltas[key], true)}}`;
      }});
      const ddNode = document.querySelector('[data-account-drawdown-pct]');
      if (ddNode) ddNode.textContent = formatAccountValue(drawdownPct, true, '%');
      const pointCountNode = document.querySelector('[data-account-point-count]');
      if (pointCountNode) pointCountNode.textContent = `${{points.length}} points`;
      const labelNode = document.querySelector('[data-account-window-label]');
      if (labelNode) labelNode.textContent = `${{range}} · ${{metric.replace('_', ' ').toUpperCase()}} · ${{formatAccountWindowTimestamp(first.timestamp)}} → ${{formatAccountWindowTimestamp(last.timestamp)}}`;
    }}
    function initializeAccountMetrics() {{
      const accountMetricsData = getAccountMetricsData();
      if (!Array.isArray(accountMetricsData)) return;
      let activeMetric = localStorage.getItem('dashboard.account.metric') || 'equity';
      let activeRange = localStorage.getItem('dashboard.account.range') || '24H';
      const chartNode = document.getElementById('account-metrics-chart');
      const render = () => {{
        const visible = filterAccountPoints(accountMetricsData, activeRange);
        if (chartNode) chartNode.innerHTML = buildAccountChartSvg(visible, activeMetric);
        updateAccountOverview(visible, activeMetric, activeRange);
      }};
      document.querySelectorAll('[data-account-metric]').forEach((button) => {{
        button.addEventListener('click', () => {{
          activeMetric = button.dataset.accountMetric;
          localStorage.setItem('dashboard.account.metric', activeMetric);
          document.querySelectorAll('[data-account-metric]').forEach((node) => node.classList.toggle('active', node === button));
          render();
        }});
      }});
      document.querySelectorAll('[data-account-range]').forEach((button) => {{
        button.addEventListener('click', () => {{
          activeRange = button.dataset.accountRange;
          localStorage.setItem('dashboard.account.range', activeRange);
          document.querySelectorAll('[data-account-range]').forEach((node) => node.classList.toggle('active', node === button));
          render();
        }});
      }});
      document.querySelectorAll('[data-account-metric]').forEach((node) => node.classList.toggle('active', node.dataset.accountMetric === activeMetric));
      document.querySelectorAll('[data-account-range]').forEach((node) => node.classList.toggle('active', node.dataset.accountRange === activeRange));
      render();
    }}
    function bindDashboardControls() {{
      const refreshButton = document.getElementById('manual-refresh-button');
      if (refreshButton) {{
        refreshButton.onclick = () => refreshDashboard(true);
      }}
      document.querySelectorAll('[data-section-toggle]').forEach((toggle) => {{
        toggle.onclick = () => {{
          const sectionKey = toggle.dataset.sectionToggle;
          const collapsedSections = new Set(getCollapsedSections());
          if (collapsedSections.has(sectionKey)) {{
            collapsedSections.delete(sectionKey);
          }} else {{
            collapsedSections.add(sectionKey);
          }}
          writeCollapsedSections(Array.from(collapsedSections));
          applyCollapsedSections();
        }};
      }});
      applyCollapsedSections();
    }}
    function replaceSectionFromDocument(nextDocument, selector) {{
      const current = document.querySelector(selector);
      const replacement = nextDocument.querySelector(selector);
      if (current && replacement) {{
        current.replaceWith(replacement);
      }}
    }}
    function setRefreshIndicatorState(state, label) {{
      const indicator = document.getElementById('refresh-indicator');
      const indicatorText = document.getElementById('refresh-indicator-text');
      if (!indicator || !indicatorText) return;
      indicator.classList.toggle('error', state === 'error');
      indicatorText.textContent = label;
    }}
    function updateLastRefreshTimestamp() {{
      const node = document.getElementById('last-updated-text');
      if (!node) return;
      node.textContent = new Intl.DateTimeFormat('zh-CN', {{
        hour12: false,
        timeZone: 'Asia/Shanghai',
        month: '2-digit',
        day: '2-digit',
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
      }}).format(new Date());
    }}
    async function refreshDashboard() {{
      const refreshButton = document.getElementById('manual-refresh-button');
      try {{
        if (refreshButton) refreshButton.classList.add('is-refreshing');
        const currentUrl = `${{window.location.pathname}}${{window.location.search}}`;
        const res = await fetch(currentUrl, {{ cache: 'no-store' }});
        if (!res.ok) {{
          setRefreshIndicatorState('error', 'Unable to refresh');
          return;
        }}
        const html = await res.text();
        const nextDocument = new DOMParser().parseFromString(html, 'text/html');
        DASHBOARD_SECTION_SELECTORS.forEach((selector) => replaceSectionFromDocument(nextDocument, selector));
        const nextTitle = nextDocument.querySelector('title');
        if (nextTitle) document.title = nextTitle.textContent || document.title;
        updateLastRefreshTimestamp();
        initializeAccountMetrics();
        bindDashboardControls();
        setRefreshIndicatorState('ok', 'Auto refresh: 5s');
      }} catch (e) {{
        console.error(e);
        setRefreshIndicatorState('error', 'Unable to refresh');
      }}
      finally {{
        if (refreshButton) refreshButton.classList.remove('is-refreshing');
      }}
    }}
    initializeAccountMetrics();
    bindDashboardControls();
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
            parsed_url = urlparse(self.path)
            query_params = parse_qs(parsed_url.query)
            active_tab = normalize_dashboard_tab(query_params.get("tab", [None])[0])
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
            if parsed_url.path in {"/api/dashboard", "/api/dashboard/summary", "/api/dashboard/timeseries", "/api/dashboard/tables"}:
                if parsed_url.path == "/api/dashboard/summary":
                    payload = build_dashboard_summary_payload(snapshot)
                elif parsed_url.path == "/api/dashboard/timeseries":
                    payload = build_dashboard_timeseries_payload(snapshot)
                elif parsed_url.path == "/api/dashboard/tables":
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
            if parsed_url.path == "/":
                body = render_dashboard_html(snapshot, active_tab=active_tab).encode("utf-8")
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
