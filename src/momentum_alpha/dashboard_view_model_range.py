from __future__ import annotations

from datetime import datetime, timedelta

from .dashboard_common import _compute_margin_usage_pct, _parse_numeric
from .dashboard_view_model_common import DISPLAY_TIMEZONE


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
