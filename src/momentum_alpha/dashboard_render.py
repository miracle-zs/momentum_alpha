from __future__ import annotations

import json
from decimal import Decimal
from html import escape
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

from .dashboard_common import (
    _parse_numeric,
    normalize_account_range,
)
from .dashboard_assets import (
    _render_dashboard_base_styles,
    _render_dashboard_component_styles,
    _render_dashboard_cosmic_styles,
    _render_dashboard_responsive_styles,
    render_dashboard_head,
    render_dashboard_scripts,
    render_dashboard_styles,
)
from .dashboard_data import (
    build_dashboard_timeseries_payload,
    build_trade_leg_count_aggregates,
    build_trade_leg_index_aggregates,
)
from .dashboard_view_model import (
    _compute_account_range_stats,
    _current_streak_from_round_trips,
    _detect_account_discontinuity,
    _filter_rows_for_display_day,
    _filter_rows_for_range,
    _object_field,
    _parse_decimal,
    build_position_details,
    build_trader_summary_metrics,
)


DISPLAY_TIMEZONE_NAME = "Asia/Shanghai"
DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
DASHBOARD_ROOMS = ("live", "review", "system")
LEGACY_DASHBOARD_TAB_TO_ROOM = {
    "overview": "live",
    "execution": "live",
    "performance": "review",
    "system": "system",
}
REVIEW_VIEWS = ("overview", "daily")


def normalize_dashboard_room(value: str | None) -> str:
    room = (value or "").strip().lower()
    if room in DASHBOARD_ROOMS:
        return room
    return LEGACY_DASHBOARD_TAB_TO_ROOM.get(room, "live")


def normalize_review_view(value: str | None) -> str:
    view = (value or "").strip().lower()
    return view if view in REVIEW_VIEWS else "overview"


def _build_dashboard_room_href(*, room: str, account_range_key: str, review_view: str | None = None) -> str:
    query = {
        "room": normalize_dashboard_room(room),
        "range": normalize_account_range(account_range_key),
    }
    if normalize_dashboard_room(room) == "review":
        query["review_view"] = normalize_review_view(review_view)
    return f"?{urlencode(query)}"


def _build_dashboard_tab_href(*, tab: str, account_range_key: str) -> str:
    return _build_dashboard_room_href(room=normalize_dashboard_room(tab), account_range_key=account_range_key)


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


def _format_datetime_compact(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
        return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%Y-%m-%d %H:%M")
    except ValueError:
        return str(timestamp)


def _format_datetime_review(timestamp: str | None) -> str:
    if not timestamp:
        return "n/a"
    try:
        parsed = datetime.fromisoformat(timestamp)
    except ValueError:
        return str(timestamp)
    return parsed.astimezone(DISPLAY_TIMEZONE).strftime("%m-%d %H:%M")


def _format_round_trip_exit_reason(exit_reason: str | None) -> str:
    if not exit_reason:
        return "n/a"
    normalized = str(exit_reason).strip().lower()
    labels = {
        "sell": "SELL",
        "stop_loss": "STOP LOSS",
        "signal_flip": "SIGNAL FLIP",
    }
    return labels.get(normalized, normalized.replace("_", " ").upper())


def _format_round_trip_id_label(round_trip_id: str | None) -> str:
    if not round_trip_id:
        return "#-"
    text = str(round_trip_id)
    if ":" in text:
        suffix = text.rsplit(":", 1)[-1]
        if suffix:
            return f"#{suffix}"
    return text


def _format_duration_seconds(value: float | int | None) -> str:
    if value is None:
        return "n/a"
    total_seconds = int(round(float(value)))
    minutes, seconds = divmod(total_seconds, 60)
    hours, minutes = divmod(minutes, 60)
    if hours:
        return f"{hours}h {minutes:02d}m"
    return f"{minutes}m {seconds:02d}s"


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
        "<div class='analytics-row round-trip-row-header'>"
        "<span class='analytics-main'>SYMBOL</span>"
        "<span>OPEN</span>"
        "<span>CLOSE</span>"
        "<span>LEGS</span>"
        "<span>PEAK RISK</span>"
        "<span>EXIT</span>"
        "<span>PNL</span>"
        "<span>DURATION</span>"
        "</div>"
    )
    rows = "".join(_render_round_trip_item(trip) for trip in round_trips)
    cards = "".join(_render_round_trip_item(trip, mobile=True) for trip in round_trips)
    return (
        f"<div class='round-trip-view desktop-only'>{header}{rows}</div>"
        f"<div class='trade-card-list mobile-only'>{cards}</div>"
    )


def render_trade_leg_count_aggregate_table(aggregates: list[dict]) -> str:
    if not aggregates:
        return "<div class='trade-history-empty'>No leg-count aggregates</div>"
    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>LEGS</span>"
        "<span>SAMPLES</span>"
        "<span>WIN RATE</span>"
        "<span>AVG NET PNL</span>"
        "<span>AVG PEAK RISK</span>"
        "</div>"
    )
    rows = ""
    cards = ""
    for item in aggregates:
        label = escape(str(item.get("label") or "-"))
        sample_count = escape(str(item.get("sample_count") or 0))
        win_rate_value = _parse_numeric(item.get("win_rate"))
        win_rate = escape(_format_pct_value(None if win_rate_value is None else win_rate_value * 100, signed=True))
        avg_net_pnl_value = _format_metric(_parse_numeric(item.get("avg_net_pnl")), signed=True)
        avg_peak_risk_value = _format_metric(_parse_numeric(item.get("avg_peak_risk")), signed=True)
        pnl_class = "side-buy" if not avg_net_pnl_value.startswith("-") else "side-sell"
        risk_class = "side-sell" if avg_peak_risk_value.startswith("-") else ""
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{label}</b></span>"
            f"<span>{sample_count}</span>"
            f"<span>{win_rate}</span>"
            f"<span class='{pnl_class}'>{escape(avg_net_pnl_value)}</span>"
            f"<span class='{risk_class}'>{escape(avg_peak_risk_value)}</span>"
            "</div>"
        )
        cards += (
            "<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{label}</b><span>{sample_count} samples</span></div>"
            f"<div class='analytics-card-meta'><span>Win {win_rate}</span><span class='{pnl_class}'>{escape(avg_net_pnl_value)}</span></div>"
            f"<div class='analytics-card-meta'><span>Peak Risk</span><span class='{risk_class}'>{escape(avg_peak_risk_value)}</span></div>"
            "</div>"
        )
    return (
        f"<div class='analytics-table desktop-only'>{header}{rows}</div>"
        f"<div class='analytics-card-list mobile-only'>{cards}</div>"
    )


def render_trade_leg_index_aggregate_table(aggregates: list[dict]) -> str:
    if not aggregates:
        return "<div class='trade-history-empty'>No leg-index aggregates</div>"
    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>LEG</span>"
        "<span>SAMPLES</span>"
        "<span>AVG LEG RISK</span>"
        "<span>AVG NET CONTRIBUTION</span>"
        "<span>PROFITABLE</span>"
        "</div>"
    )
    rows = ""
    cards = ""
    for item in aggregates:
        label = escape(str(item.get("label") or "-"))
        sample_count = escape(str(item.get("sample_count") or 0))
        avg_leg_risk_value = _format_metric(_parse_numeric(item.get("avg_leg_risk")), signed=True)
        avg_net_contribution_value = _format_metric(_parse_numeric(item.get("avg_net_contribution")), signed=True)
        profitable_ratio_value = _parse_numeric(item.get("profitable_ratio"))
        profitable_ratio = escape(
            _format_pct_value(None if profitable_ratio_value is None else profitable_ratio_value * 100, signed=True)
        )
        risk_class = "side-sell" if avg_leg_risk_value.startswith("-") else ""
        net_class = "side-buy" if not avg_net_contribution_value.startswith("-") else "side-sell"
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{label}</b></span>"
            f"<span>{sample_count}</span>"
            f"<span class='{risk_class}'>{escape(avg_leg_risk_value)}</span>"
            f"<span class='{net_class}'>{escape(avg_net_contribution_value)}</span>"
            f"<span>{profitable_ratio}</span>"
            "</div>"
        )
        cards += (
            "<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{label}</b><span>{sample_count} samples</span></div>"
            f"<div class='analytics-card-meta'><span>Leg Risk</span><span class='{risk_class}'>{escape(avg_leg_risk_value)}</span></div>"
            f"<div class='analytics-card-meta'><span>Net Contribution</span><span class='{net_class}'>{escape(avg_net_contribution_value)}</span></div>"
            f"<div class='analytics-card-meta'><span>Profitable</span><span>{profitable_ratio}</span></div>"
            "</div>"
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
        distance_to_stop = _display_live_price_metric(pos.get("distance_to_stop_pct"), suffix="%")
        notional = _display_live_price_metric(pos.get("notional_exposure"))
        r_multiple = _display_live_price_metric(pos.get("r_multiple"), suffix="R")
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
            f"<div class='position-metric'><span class='metric-label'>Risk % of Equity</span><span class='metric-value'>{risk_pct}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Legs</span><span class='metric-value'>{leg_count}</span></div>"
            f"<div class='position-metric'><span class='metric-label'>Opened</span><span class='metric-value'>{opened_at}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>Last</span><span class='metric-value'>{latest_price}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>MTM</span><span class='metric-value'>{mtm_pnl}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>PnL %</span><span class='metric-value'>{pnl_pct}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>Distance to Stop %</span><span class='metric-value'>{distance_to_stop}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>Notional</span><span class='metric-value'>{notional}</span></div>"
            f"<div class='position-metric position-live'><span class='metric-label'>R Multiple vs Risk</span><span class='metric-value'>{r_multiple}</span></div>"
            f"</div>"
            f"<div class='position-legs'>{escape(legs_str)}</div>"
            f"</div>"
        )

    return f"<div class='positions-grid'>{cards}</div>"


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


def _format_decimal_metric(value: Decimal | object | None, *, signed: bool = False, suffix: str = "") -> str:
    decimal_value = value if isinstance(value, Decimal) else _parse_decimal(value)
    if decimal_value is None:
        return "n/a"
    if signed and decimal_value == 0:
        return f"0.00{suffix}"
    prefix = "+" if signed and decimal_value > 0 else ""
    return f"{prefix}{decimal_value:,.2f}{suffix}"


def _daily_review_impact(*, actual: object | None, replay: object | None) -> Decimal | None:
    actual_value = _parse_decimal(actual)
    replay_value = _parse_decimal(replay)
    if actual_value is None or replay_value is None:
        return None
    return actual_value - replay_value


def _daily_review_win_rate(values: list[Decimal]) -> Decimal | None:
    if not values:
        return None
    wins = sum(1 for value in values if value > 0)
    return (Decimal(wins) / Decimal(len(values))) * Decimal("100")


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


def _build_account_metrics_panel(points: list[dict], *, account_range_key: str = "1D") -> str:
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
        f"<button type='button' class='account-chip{' active' if account_range_key == '1H' else ''}' data-account-range=\"1H\">1H</button>"
        f"<button type='button' class='account-chip{' active' if account_range_key == '1D' else ''}' data-account-range=\"1D\">1D</button>"
        f"<button type='button' class='account-chip{' active' if account_range_key == '1W' else ''}' data-account-range=\"1W\">1W</button>"
        f"<button type='button' class='account-chip{' active' if account_range_key == '1M' else ''}' data-account-range=\"1M\">1M</button>"
        f"<button type='button' class='account-chip{' active' if account_range_key == '1Y' else ''}' data-account-range=\"1Y\">1Y</button>"
        f"<button type='button' class='account-chip{' active' if account_range_key == 'ALL' else ''}' data-account-range=\"ALL\">ALL</button>"
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
        "<div class='account-overview-card account-overview-card-highlight'><div class='account-overview-label'>CURRENT MARGIN USAGE</div>"
        f"<div class='account-overview-value' data-account-value='current_margin_usage_pct'>{escape(_format_pct_value(stats['current_margin_usage_pct']))}</div>"
        "<div class='account-overview-sub'>Latest visible capital pressure</div></div>"
        "<div class='account-overview-card account-overview-card-highlight'><div class='account-overview-label'>PEAK MARGIN USAGE</div>"
        f"<div class='account-overview-value' data-account-value='peak_margin_usage_pct'>{escape(_format_pct_value(stats['peak_margin_usage_pct']))}</div>"
        "<div class='account-overview-sub'>Maximum visible capital pressure</div></div>"
        "<div class='account-overview-card account-overview-card-highlight'><div class='account-overview-label'>AVERAGE MARGIN USAGE</div>"
        f"<div class='account-overview-value' data-account-value='average_margin_usage_pct'>{escape(_format_pct_value(stats['average_margin_usage_pct']))}</div>"
        "<div class='account-overview-sub'>Mean visible capital pressure</div></div>"
        "</div>"
        "<div class='account-main-panel'>"
        "<div class='account-main-toolbar'>"
        "<div class='account-metric-switches'>"
        "<button type='button' class='account-chip active' data-account-metric=\"equity\">Equity</button>"
        "<button type='button' class='account-chip' data-account-metric=\"adjusted_equity\">Adjusted Equity</button>"
        "<button type='button' class='account-chip' data-account-metric=\"wallet_balance\">Wallet</button>"
        "<button type='button' class='account-chip' data-account-metric=\"unrealized_pnl\">Unrealized PnL</button>"
        "<button type='button' class='account-chip' data-account-metric=\"margin_usage_pct\">Margin Usage %</button>"
        "</div>"
        "<div class='account-main-meta'><span data-account-window-label>Visible Range</span><span data-account-point-count>"
        f"{len(points)} points</span></div>"
        "</div>"
        f"{initial_chart}"
        f"<script id='account-metrics-json' type='application/json'>{data_json}</script>"
        "</div>"
        "</section>"
    )


def _build_account_snapshot_panel(stats: dict[str, float | None]) -> str:
    return (
        "<section class='dashboard-section account-snapshot-panel'>"
        "<div class='section-header'>ACCOUNT SNAPSHOT</div>"
        "<div class='account-snapshot-grid'>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Equity</div>"
        f"<div class='account-snapshot-value'>{escape(_format_metric(stats.get('current_equity')))}</div>"
        "<div class='account-snapshot-sub'>Latest visible account equity</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Available</div>"
        f"<div class='account-snapshot-value'>{escape(_format_metric(stats.get('current_wallet')))}</div>"
        "<div class='account-snapshot-sub'>Wallet balance on record</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Drawdown</div>"
        f"<div class='account-snapshot-value'>{escape(_format_metric(stats.get('drawdown_abs'), signed=True))}</div>"
        f"<div class='account-snapshot-sub'>{escape(_format_pct_value(stats.get('drawdown_pct'), signed=True))} vs visible peak</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Exposure</div>"
        f"<div class='account-snapshot-value'>{escape(str(stats.get('current_positions') or 0))} / {escape(str(stats.get('current_orders') or 0))}</div>"
        "<div class='account-snapshot-sub'>positions / orders</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Margin Usage</div>"
        f"<div class='account-snapshot-value'>{escape(_format_pct_value(stats.get('current_margin_usage_pct')))}</div>"
        "<div class='account-snapshot-sub'>current account occupancy</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Peak Margin Usage</div>"
        f"<div class='account-snapshot-value'>{escape(_format_pct_value(stats.get('peak_margin_usage_pct')))}</div>"
        "<div class='account-snapshot-sub'>highest visible occupancy</div></div>"
        "<div class='account-snapshot-card'><div class='account-snapshot-label'>Average Margin Usage</div>"
        f"<div class='account-snapshot-value'>{escape(_format_pct_value(stats.get('average_margin_usage_pct')))}</div>"
        "<div class='account-snapshot-sub'>mean visible occupancy</div></div>"
        "</div>"
        "</section>"
    )


def _build_live_account_risk_panel(
    *,
    trader_metrics: dict[str, dict[str, object | None]],
    account_range_stats: dict[str, float | None],
) -> str:
    account_metrics = trader_metrics["account"]
    return (
        "<section class='dashboard-section live-account-risk-panel'>"
        "<div class='section-header'>ACCOUNT RISK</div>"
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Equity</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_equity')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Available Balance</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_available_balance')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Unrealized PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_unrealized_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Today Net PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('today_net_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Margin Usage</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('margin_usage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>OPEN RISK / EQUITY</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('open_risk_pct')))}</div><div class='decision-support'>{escape(_format_metric(account_metrics.get('open_risk')))} USDT at risk</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Drawdown</div><div class='decision-value'>{escape(_format_metric(account_range_stats.get('drawdown_abs'), signed=True))}</div><div class='decision-support'>{escape(_format_pct_value(account_range_stats.get('drawdown_pct'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Positions / Orders</div><div class='decision-value'>{escape(str(account_metrics.get('current_positions') or 0))} / {escape(str(account_metrics.get('current_orders') or 0))}</div></div>"
        "</div>"
        "</section>"
    )


def _build_live_core_lines_panel(account_points: list[dict]) -> str:
    chart_specs = (
        ("Account Equity", "equity", "#4cc9f0"),
        ("Margin Usage %", "margin_usage_pct", "#ff8c42"),
        ("Position Count", "position_count", "#36d98a"),
    )
    chart_cards = "".join(
        (
            "<div class='chart-card live-core-line-card'>"
            f"<div class='section-header'>{escape(label)}</div>"
            f"{_render_line_chart_svg(points=account_points, value_key=value_key, stroke=color, fill=color)}"
            "</div>"
        )
        for label, value_key, color in chart_specs
    )
    return (
        "<section class='dashboard-section live-core-lines-panel'>"
        "<div class='section-header'>CORE LIVE LINES</div>"
        f"<div class='analytics-grid'>{chart_cards}</div>"
        "</section>"
    )


def _render_round_trip_leg_rows(legs: list[dict]) -> str:
    if not legs:
        return "<div class='round-trip-leg-empty'>No leg detail available</div>"
    header = (
        "<div class='round-trip-leg-row round-trip-leg-row-header'>"
        "<span>Leg #</span>"
        "<span>Type</span>"
        "<span>Opened At</span>"
        "<span>Qty</span>"
        "<span>Entry</span>"
        "<span>Stop At Entry</span>"
        "<span>Leg Risk</span>"
        "<span>Cum Risk</span>"
        "<span>Gross PnL</span>"
        "<span>Fee Share</span>"
        "<span>Net Contribution</span>"
        "</div>"
    )
    rows = ""
    for leg in legs:
        rows += (
            "<div class='round-trip-leg-row'>"
            f"<span>{escape(str(leg.get('leg_index') or '-'))}</span>"
            f"<span>{escape(str(leg.get('leg_type') or '-'))}</span>"
            f"<span>{escape(_format_time_only(leg.get('opened_at')))}</span>"
            f"<span>{escape(_format_quantity(leg.get('quantity')))}</span>"
            f"<span>{escape(_format_price(leg.get('entry_price')))}</span>"
            f"<span>{escape(_format_price(leg.get('stop_price_at_entry')))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('leg_risk')), signed=True))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('cumulative_risk_after_leg')), signed=True))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('gross_pnl_contribution')), signed=True))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('fee_share')), signed=True))}</span>"
            f"<span>{escape(_format_metric(_parse_numeric(leg.get('net_pnl_contribution')), signed=True))}</span>"
            "</div>"
        )
    return f"<div class='round-trip-leg-table'>{header}{rows}</div>"


def _render_round_trip_item(trip: dict, *, mobile: bool = False) -> str:
    symbol = escape(str(trip.get("symbol") or "-"))
    round_trip_id = escape(_format_round_trip_id_label(trip.get("round_trip_id")))
    opened_at = _format_datetime_compact(trip.get("opened_at"))
    closed_at = _format_datetime_compact(trip.get("closed_at"))
    payload = trip.get("payload") or {}
    leg_count = _parse_numeric(payload.get("leg_count"))
    if leg_count is None:
        leg_count = len(payload.get("legs") or [])
    peak_risk = _format_metric(_parse_numeric(payload.get("peak_cumulative_risk")), signed=True)
    net_pnl_value = _format_metric(_parse_numeric(trip.get("net_pnl")), signed=True)
    exit_reason = escape(_format_round_trip_exit_reason(trip.get("exit_reason")))
    duration = _format_duration_seconds(_parse_numeric(trip.get("duration_seconds")))
    leg_count_display = escape(str(int(leg_count) if isinstance(leg_count, (int, float)) else leg_count))
    pnl_class = "side-buy" if not net_pnl_value.startswith("-") else "side-sell"
    leg_rows = _render_round_trip_leg_rows(list(payload.get("legs") or []))

    if mobile:
        return (
            "<details class='round-trip-card'>"
            "<summary class='analytics-card round-trip-card-summary'>"
            f"<div class='analytics-card-main'><b>{symbol}</b><span>{round_trip_id}</span></div>"
            f"<div class='analytics-card-meta'><span>Open {escape(opened_at)}</span><span>Close {escape(closed_at)}</span><span>Legs {leg_count_display}</span></div>"
            f"<div class='analytics-card-meta'><span>Peak Risk {escape(peak_risk)}</span><span>{exit_reason}</span><span class='{pnl_class}'>{escape(net_pnl_value)}</span></div>"
            f"<div class='analytics-card-meta'><span>Duration {escape(duration)}</span></div>"
            "</summary>"
            f"<div class='round-trip-detail-body'>{leg_rows}</div>"
            "</details>"
        )

    return (
        "<details class='round-trip-details'>"
        "<summary class='analytics-row round-trip-summary'>"
        f"<span class='analytics-main'><b>{symbol}</b> · {round_trip_id}</span>"
        f"<span>{escape(opened_at)}</span>"
        f"<span>{escape(closed_at)}</span>"
        f"<span>{leg_count_display}</span>"
        f"<span>{escape(peak_risk)}</span>"
        f"<span>{exit_reason}</span>"
        f"<span class='{pnl_class}'>{escape(net_pnl_value)}</span>"
        f"<span>{escape(duration)}</span>"
        "</summary>"
        f"<div class='round-trip-detail-body'>{leg_rows}</div>"
        "</details>"
    )


def _build_overview_home_command(
    *,
    position_details: list[dict],
    trader_metrics: dict[str, dict[str, object | None]],
    account_range_stats: dict[str, float | None],
    health_status: str,
    account_range_key: str,
) -> str:
    def _format_pct_short(value: object | None) -> str:
        numeric = _parse_numeric(value)
        if numeric is None:
            return "n/a"
        return f"{numeric:,.2f}%"

    primary_position = position_details[0] if position_details else {}
    mtm_total = sum((_parse_numeric(position.get("mtm_pnl")) or 0.0) for position in position_details)
    position_summary_items = [
        ("Live Positions", str(len(position_details))),
        ("Lead Symbol", str(primary_position.get("symbol") or "flat")),
        ("Risk %", _format_pct_short(trader_metrics["account"].get("open_risk_pct"))),
        ("MTM", _format_metric(mtm_total, signed=True)),
    ]
    account_pulse_items = [
        ("Available", _format_metric(trader_metrics["account"].get("current_available_balance"))),
        ("Drawdown", _format_metric(account_range_stats.get("drawdown_abs"), signed=True)),
        ("Exposure", f"{str(trader_metrics['account'].get('current_positions') or 0)} / {str(trader_metrics['account'].get('current_orders') or 0)}"),
        ("Health", str(health_status)),
    ]
    action_cards = [
        (
            "复盘室",
            "Review closed trades, leg contribution, slippage, and strategy parameters.",
            _build_dashboard_room_href(room="review", account_range_key=account_range_key),
        ),
        (
            "系统状态室",
            "Check freshness, warnings, configuration, and runtime health.",
            _build_dashboard_room_href(room="system", account_range_key=account_range_key),
        ),
    ]
    return (
        "<section class='dashboard-section home-command-panel'>"
        "<div class='section-header'>HOME COMMAND</div>"
        "<div class='home-command-grid'>"
        "<div class='home-command-column'>"
        "<div class='home-command-card'>"
        "<div class='home-command-card-header'>POSITION SUMMARY</div>"
        "<div class='home-command-stat-grid'>"
        + "".join(
            f"<div class='home-command-stat'><div class='home-command-label'>{escape(label)}</div><div class='home-command-value'>{escape(value)}</div></div>"
            for label, value in position_summary_items
        )
        + "</div>"
        "</div>"
        "<div class='home-command-card home-command-card-muted'>"
        "<div class='home-command-card-header'>ACCOUNT PULSE</div>"
        "<div class='home-command-chip-grid'>"
        + "".join(
            f"<div class='home-command-chip'><span>{escape(label)}</span><strong>{escape(value)}</strong></div>"
            for label, value in account_pulse_items
        )
        + "</div>"
        "</div>"
        "</div>"
        "<div class='home-command-column'>"
        "<div class='home-command-card'>"
        "<div class='home-command-card-header'>NEXT ACTIONS</div>"
        "<div class='next-actions-grid'>"
        + "".join(
            f"<a class='next-action-card' href='{href}'><span class='next-action-label'>{escape(label)}</span><span class='next-action-copy'>{escape(copy)}</span></a>"
            for label, copy, href in action_cards
        )
        + "</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
    )


def _build_execution_flow_panel(
    *,
    recent_broker_orders: list[dict],
    recent_algo_orders: list[dict],
    recent_trade_fills: list[dict],
    recent_stop_exit_summaries: list[dict],
) -> str:
    latest_broker_order = recent_broker_orders[0] if recent_broker_orders else {}
    latest_algo_order = recent_algo_orders[0] if recent_algo_orders else {}
    latest_trade_fill = recent_trade_fills[0] if recent_trade_fills else {}
    latest_stop_exit = recent_stop_exit_summaries[0] if recent_stop_exit_summaries else {}

    def _execution_flow_card(*, label: str, primary: str, secondary: str, detail: str) -> str:
        return (
            "<div class='execution-flow-card'>"
            f"<div class='execution-flow-label'>{escape(label)}</div>"
            f"<div class='execution-flow-primary'>{escape(primary or 'n/a')}</div>"
            f"<div class='execution-flow-secondary'>{escape(secondary or 'n/a')}</div>"
            f"<div class='execution-flow-detail'>{escape(detail or 'n/a')}</div>"
            "</div>"
        )

    broker_card = _execution_flow_card(
        label="Latest Broker Action",
        primary=str(latest_broker_order.get("action_type") or "n/a"),
        secondary=f"{latest_broker_order.get('symbol') or '-'} · {latest_broker_order.get('order_type') or '-'}",
        detail=f"{latest_broker_order.get('order_status') or '-'} · {format_timestamp_for_display(latest_broker_order.get('timestamp'))}",
    )
    algo_card = _execution_flow_card(
        label="Latest Stop Order",
        primary=str(latest_algo_order.get("algo_status") or "n/a"),
        secondary=f"{latest_algo_order.get('symbol') or '-'} · {latest_algo_order.get('order_type') or '-'}",
        detail=f"Trigger {latest_algo_order.get('trigger_price') or 'n/a'} · {format_timestamp_for_display(latest_algo_order.get('timestamp'))}",
    )
    fill_card = _execution_flow_card(
        label="Latest Fill",
        primary=str(latest_trade_fill.get("trade_id") or "n/a"),
        secondary=f"{latest_trade_fill.get('symbol') or '-'} · {latest_trade_fill.get('side') or '-'} · {latest_trade_fill.get('order_type') or '-'}",
        detail=f"{latest_trade_fill.get('quantity') or 'n/a'} @ {latest_trade_fill.get('average_price') or latest_trade_fill.get('last_price') or 'n/a'}",
    )
    stop_exit_card = _execution_flow_card(
        label="Latest Stop Exit",
        primary=str(latest_stop_exit.get("symbol") or "n/a"),
        secondary=f"Trigger {latest_stop_exit.get('trigger_price') or 'n/a'} · Exit {latest_stop_exit.get('average_exit_price') or 'n/a'}",
        detail=f"Slip {latest_stop_exit.get('slippage_pct') or 'n/a'}% · {format_timestamp_for_display(latest_stop_exit.get('timestamp'))}",
    )
    return (
        "<section class='dashboard-section execution-flow-panel'>"
        "<div class='section-header'>ORDER FLOW</div>"
        "<div class='execution-flow-grid'>"
        f"{broker_card}{algo_card}{fill_card}{stop_exit_card}"
        "</div>"
        "</section>"
    )


def normalize_dashboard_tab(value: str | None) -> str:
    room = normalize_dashboard_room(value)
    return {"live": "overview", "review": "performance", "system": "system"}[room]


def _build_execution_mode(config: dict) -> tuple[str, str]:
    venue = "TESTNET" if config.get("testnet") else "PROD"
    order_mode = "LIVE" if config.get("submit_orders") else "DRY RUN"
    state = "danger" if venue == "PROD" and order_mode == "LIVE" else "warning"
    return f"{venue} {order_mode}", state


def render_dashboard_room_nav(
    active_room: str,
    *,
    account_range_key: str = "1D",
    review_view: str = "overview",
) -> str:
    active_room = normalize_dashboard_room(active_room)
    review_view = normalize_review_view(review_view)
    labels = {
        "live": "实时监控室",
        "review": "复盘室",
        "system": "系统状态室",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if room == active_room else ""}" '
            f'data-dashboard-room="{room}" href="{_build_dashboard_room_href(room=room, account_range_key=account_range_key, review_view=review_view)}">{escape(labels[room])}</a>'
        )
        for room in DASHBOARD_ROOMS
    )
    return (
        '<nav class="dashboard-tabs" data-dashboard-section="room-nav" aria-label="Dashboard rooms">'
        f"{links}"
        "</nav>"
    )


def render_dashboard_tab_bar(active_tab: str, *, account_range_key: str = "1D") -> str:
    return render_dashboard_room_nav(normalize_dashboard_room(active_tab), account_range_key=account_range_key)


def render_dashboard_live_room(
    *,
    account_risk_html: str,
    core_lines_html: str,
    top_metrics_html: str,
    hero_html: str,
    positions_html: str,
    home_command_html: str,
    execution_flow_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        f"{account_risk_html}"
        f"{core_lines_html}"
        f"<div class='metrics-grid'>{top_metrics_html}</div>"
        f"{hero_html}"
        "<section class='dashboard-section active-positions-panel'>"
        "<div class='section-header'>ACTIVE POSITIONS</div>"
        f"{positions_html}"
        "</section>"
        f"{execution_flow_html}"
        f"{home_command_html}"
        "</div>"
    )


def render_dashboard_overview_tab(
    *,
    account_risk_html: str,
    core_lines_html: str,
    top_metrics_html: str,
    hero_html: str,
    positions_html: str,
    home_command_html: str,
    execution_flow_html: str,
) -> str:
    return render_dashboard_live_room(
        account_risk_html=account_risk_html,
        core_lines_html=core_lines_html,
        top_metrics_html=top_metrics_html,
        hero_html=hero_html,
        positions_html=positions_html,
        home_command_html=home_command_html,
        execution_flow_html=execution_flow_html,
    )


def render_dashboard_execution_tab(*, execution_flow_html: str, execution_summary_html: str, trade_history_html: str, stop_slippage_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        f"{execution_flow_html}"
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


def render_daily_review_panel(report: dict | None) -> str:
    if report is None:
        return (
            "<section class='chart-card daily-review-panel'>"
            "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>每日复盘</div>"
            "<div class='trade-history-empty'>No daily review report</div>"
            "</section>"
        )

    rows = []
    rows_data = sorted(
        report.get("payload", {}).get("rows", []) or [],
        key=lambda row: (
            row.get("closed_at") or "",
            row.get("round_trip_id") or "",
            row.get("symbol") or "",
        ),
        reverse=True,
    )
    actual_total = _parse_decimal(report.get("actual_total_pnl"))
    replay_total = _parse_decimal(report.get("counterfactual_total_pnl"))
    total_impact = _daily_review_impact(
        actual=report.get("actual_total_pnl"),
        replay=report.get("counterfactual_total_pnl"),
    )
    total_impact_abs = abs(total_impact) if total_impact is not None else None
    if total_impact is None:
        impact_state = ""
        impact_headline = "Filter impact unavailable"
        impact_support = "Daily report is missing actual or replay PnL."
    elif total_impact > 0:
        impact_state = "positive"
        impact_headline = f"Filter helped by {_format_decimal_metric(total_impact_abs)}"
        impact_support = "Actual strategy outperformed the unconditional hourly add-on replay."
    elif total_impact < 0:
        impact_state = "negative"
        impact_headline = f"Filter dragged by {_format_decimal_metric(total_impact_abs)}"
        impact_support = "The unconditional hourly add-on replay outperformed the actual strategy."
    else:
        impact_state = "neutral"
        impact_headline = "Filter impact flat"
        impact_support = "Actual and replay PnL matched for this report."

    actual_values: list[Decimal] = []
    replay_values: list[Decimal] = []
    row_impacts: list[Decimal] = []
    affected_trade_count = 0
    for row in rows_data:
        actual_value = _parse_decimal(row.get("actual_net_pnl"))
        replay_value = _parse_decimal(row.get("counterfactual_net_pnl"))
        if actual_value is not None:
            actual_values.append(actual_value)
        if replay_value is not None:
            replay_values.append(replay_value)
        row_impact = _daily_review_impact(
            actual=row.get("actual_net_pnl"),
            replay=row.get("counterfactual_net_pnl"),
        )
        if row_impact is not None:
            row_impacts.append(row_impact)
        replayed_add_on_count = int(_parse_numeric(row.get("replayed_add_on_count")) or 0)
        if replayed_add_on_count > 0 or (row_impact is not None and row_impact != 0):
            affected_trade_count += 1
        warnings_text = ", ".join(str(item) for item in (row.get("warnings") or [])) or "n/a"
        status_label = "WARN" if warnings_text != "n/a" else "OK"
        status_class = "warn" if status_label == "WARN" else "ok"
        impact_class = ""
        if row_impact is not None and row_impact > 0:
            impact_class = "daily-review-impact-positive"
        elif row_impact is not None and row_impact < 0:
            impact_class = "daily-review-impact-negative"
        rows.append(
            "<div class='analytics-row daily-review-row daily-review-grid'>"
            f"<span title='{escape(str(row.get('closed_at', 'n/a')))}'>{escape(_format_datetime_review(row.get('closed_at')))}</span>"
            f"<span class='analytics-main'><b>{escape(str(row.get('symbol', 'n/a')))}</b></span>"
            f"<span title='{escape(str(row.get('opened_at', 'n/a')))}'>{escape(_format_datetime_review(row.get('opened_at')))}</span>"
            f"<span>{escape(_format_decimal_metric(actual_value, signed=True))}</span>"
            f"<span>{escape(_format_decimal_metric(replay_value, signed=True))}</span>"
            f"<span class='{impact_class}'>{escape(_format_decimal_metric(row_impact, signed=True))}</span>"
            f"<span>{escape(str(replayed_add_on_count))}</span>"
            f"<span><span class='daily-review-status daily-review-status-{status_class}' title='{escape(warnings_text)}'>{status_label}</span></span>"
            "</div>"
        )
    actual_win_rate = _daily_review_win_rate(actual_values)
    replay_win_rate = _daily_review_win_rate(replay_values)
    trade_count = _parse_decimal(report.get("trade_count")) or Decimal(len(rows_data) or 0)
    avg_impact = total_impact / trade_count if total_impact is not None and trade_count else None
    positive_impacts = [impact for impact in row_impacts if impact > 0]
    negative_impacts = [impact for impact in row_impacts if impact < 0]
    best_filter_save = max(positive_impacts) if positive_impacts else Decimal("0")
    worst_filter_drag = min(negative_impacts) if negative_impacts else Decimal("0")
    kpi_items = [
        ("Report Date", str(report.get("report_date", "n/a"))),
        ("Trades", str(report.get("trade_count", "n/a"))),
        ("Actual PnL", _format_decimal_metric(actual_total, signed=True)),
        ("Replay PnL", _format_decimal_metric(replay_total, signed=True)),
        ("Filter Impact", _format_decimal_metric(total_impact, signed=True)),
        ("Replayed Add-Ons", str(report.get("replayed_add_on_count", "n/a"))),
        ("Actual Win Rate", _format_decimal_metric(actual_win_rate, suffix="%")),
        ("Replay Win Rate", _format_decimal_metric(replay_win_rate, suffix="%")),
        ("Affected Trades", str(affected_trade_count)),
        ("Avg Impact / Trade", _format_decimal_metric(avg_impact, signed=True)),
        ("Best Filter Save", _format_decimal_metric(best_filter_save, signed=True)),
        ("Worst Filter Drag", _format_decimal_metric(worst_filter_drag, signed=True)),
    ]
    kpi_html = "".join(
        (
            "<div class='daily-review-kpi'>"
            f"<div class='decision-label'>{escape(label)}</div>"
            f"<div class='decision-value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in kpi_items
    )
    rows_html = (
        "<div class='analytics-table daily-review-table'>"
        "<div class='analytics-row analytics-row-header daily-review-row-header daily-review-grid'>"
        "<span>CLOSED AT</span><span class='analytics-main'>SYMBOL</span><span>OPENED AT</span><span>ACTUAL</span><span>REPLAY</span><span>FILTER IMPACT</span><span>ADD-ONS</span><span>STATUS</span>"
        "</div>"
        f"{''.join(rows) if rows else '<div class=\"trade-history-empty\">No trade rows</div>'}"
        "</div>"
    )
    return (
        "<section class='chart-card daily-review-panel'>"
        f"<div class='daily-review-headline {impact_state}'>"
        "<div>"
        "<div class='daily-review-eyebrow'>每日复盘</div>"
        f"<div class='daily-review-title'>{escape(impact_headline)}</div>"
        f"<div class='daily-review-support'>{escape(impact_support)}</div>"
        "</div>"
        "</div>"
        f"<div class='daily-review-kpi-grid'>{kpi_html}</div>"
        f"{rows_html}"
        "</section>"
    )


def render_dashboard_performance_tab(
    *,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="review">'
        "<section class='section-frame' data-collapsible-section='review'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>复盘室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Closed Trade Detail is the primary review surface; aggregates follow the ledger.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Complete Trade Summary (all closed trades)</div>"
        f"{performance_summary_html}"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Closed Trade Detail</div>"
        f"<div class='table-scroll'>{round_trip_detail_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Total Leg Count</div>"
        f"<div class='table-scroll'>{leg_count_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>By Leg Index</div>"
        f"<div class='table-scroll'>{leg_index_aggregate_html}</div>"
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


def render_dashboard_review_tabs(active_review_view: str, *, account_range_key: str = "1D") -> str:
    active_review_view = normalize_review_view(active_review_view)
    labels = {
        "overview": "总体复盘",
        "daily": "每日复盘",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if view == active_review_view else ""}" '
            f'data-dashboard-review-view="{view}" href="{_build_dashboard_room_href(room="review", account_range_key=account_range_key, review_view=view)}">{escape(labels[view])}</a>'
        )
        for view in REVIEW_VIEWS
    )
    return (
        '<nav class="dashboard-tabs review-tabs" data-dashboard-section="review-tabs" aria-label="Review views">'
        f"{links}"
        "</nav>"
    )


def render_daily_review_room(*, daily_review_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-review-view-content="daily">'
        "<section class='section-frame' data-collapsible-section='review-daily'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>每日复盘</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>UTC+8 08:30 to UTC+8 08:30 trading window.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review-daily'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        f"{daily_review_html}"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_review_room(
    *,
    active_review_view: str,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
    daily_review_html: str,
) -> str:
    active_review_view = normalize_review_view(active_review_view)
    if active_review_view == "daily":
        body_html = render_daily_review_room(daily_review_html=daily_review_html)
    else:
        body_html = render_dashboard_performance_tab(
            performance_summary_html=performance_summary_html,
            round_trip_detail_html=round_trip_detail_html,
            leg_count_aggregate_html=leg_count_aggregate_html,
            leg_index_aggregate_html=leg_index_aggregate_html,
            stop_slippage_html=stop_slippage_html,
        )
    return f"{render_dashboard_review_tabs(active_review_view)}{body_html}"


def render_dashboard_system_room(
    *,
    diagnostics_html: str,
    warning_list_html: str,
    config_html: str,
    source_html: str,
    health_items_html: str,
    recent_events_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="system">'
        "<section class='section-frame' data-collapsible-section='system'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>系统状态室</div>"
        "<button type='button' class='section-toggle' data-section-toggle='system'>Collapse</button>"
        "</div>"
        f"{diagnostics_html}"
        f"{warning_list_html}"
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


def render_dashboard_system_tab(
    *,
    diagnostics_html: str,
    warning_list_html: str,
    config_html: str,
    source_html: str,
    health_items_html: str,
    recent_events_html: str,
) -> str:
    return render_dashboard_system_room(
        diagnostics_html=diagnostics_html,
        warning_list_html=warning_list_html,
        config_html=config_html,
        source_html=source_html,
        health_items_html=health_items_html,
        recent_events_html=recent_events_html,
    )


def _render_cosmic_color_swatches() -> str:
    swatches = (
        ("Cosmic Black", "#050507", "cosmic-dot-black"),
        ("Deep Space", "#0E0F14", "cosmic-dot-space"),
        ("Soft White", "#F5F6F8", "cosmic-dot-white"),
        ("Stardust Gold", "#F5D28A", "cosmic-dot-gold"),
        ("Night Purple", "#1A1C2A", "cosmic-dot-purple"),
    )
    return (
        "<div class='cosmic-identity-card cosmic-identity-colors'>"
        "<div class='cosmic-identity-card-label'>COLOR</div>"
        "<div class='cosmic-swatches'>"
        + "".join(
            (
                "<div class='cosmic-swatch'>"
                f"<span class='cosmic-dot {escape(css_class)}'></span>"
                "<div>"
                f"<div class='cosmic-swatch-name'>{escape(label)}</div>"
                f"<div class='cosmic-swatch-value'>{escape(value)}</div>"
                "</div>"
                "</div>"
            )
            for label, value, css_class in swatches
        )
        + "</div>"
        "<div class='cosmic-gradient-bar'></div>"
        "</div>"
    )


def _render_cosmic_component_gallery() -> str:
    return (
        "<div class='cosmic-identity-card cosmic-identity-components'>"
        "<div class='cosmic-identity-card-label'>UI COMPONENTS</div>"
        "<div class='cosmic-component-row'>"
        "<span class='cosmic-chip cosmic-chip-primary'>BUTTON</span>"
        "<span class='cosmic-chip cosmic-chip-secondary'>CANCEL</span>"
        "<span class='cosmic-chip cosmic-chip-ghost'>MORE</span>"
        "</div>"
        "<div class='cosmic-toggle-row'>"
        "<span class='cosmic-toggle cosmic-toggle-off'><span></span></span>"
        "<span class='cosmic-toggle cosmic-toggle-on'><span></span></span>"
        "</div>"
        "<div class='cosmic-tag-block'>"
        "<div class='cosmic-identity-card-label cosmic-inline-label'>TAGS</div>"
        "<div class='cosmic-tag-row'>"
        "<span class='cosmic-tag cosmic-tag-gold'>BLACK HOLE</span>"
        "<span class='cosmic-tag cosmic-tag-violet'>JUPITER</span>"
        "<span class='cosmic-tag cosmic-tag-teal'>ORBIT</span>"
        "<span class='cosmic-tag'>CARDS</span>"
        "</div>"
        "</div>"
        "</div>"
    )


def _render_cosmic_data_display() -> str:
    return (
        "<div class='cosmic-identity-card cosmic-identity-data'>"
        "<div class='cosmic-identity-card-label'>DATA DISPLAY</div>"
        "<div class='cosmic-data-grid'>"
        "<div class='cosmic-data-card'><div class='cosmic-data-label'>ENERGY</div><div class='cosmic-ring'>87%</div></div>"
        "<div class='cosmic-data-card'><div class='cosmic-data-label'>SLIDER</div><div class='cosmic-slider'><span></span></div><div class='cosmic-data-value'>72%</div></div>"
        "</div>"
        "<div class='cosmic-icon-row'>"
        "<span class='cosmic-icon'>ICON</span>"
        "<span class='cosmic-icon'>BLACK HOLE</span>"
        "<span class='cosmic-icon'>GRAVITY RING</span>"
        "<span class='cosmic-icon'>NEBULA DUST</span>"
        "</div>"
        "</div>"
    )


def _render_cosmic_visual_elements() -> str:
    visuals = (
        ("BLACK HOLE", "cosmic-visual-black-hole"),
        ("GRAVITY RING", "cosmic-visual-gravity-ring"),
        ("LIGHT GLOW", "cosmic-visual-light-glow"),
        ("NEBULA DUST", "cosmic-visual-nebula-dust"),
        ("GLASS SURFACE", "cosmic-visual-glass-surface"),
    )
    return (
        "<div class='cosmic-identity-card cosmic-identity-visuals'>"
        "<div class='cosmic-identity-card-label'>VISUAL ELEMENTS</div>"
        "<div class='cosmic-visual-tiles'>"
        + "".join(
            (
                "<div class='cosmic-visual-tile "
                f"{escape(css_class)}'>"
                "<span class='cosmic-visual-tile-glow'></span>"
                f"<span class='cosmic-visual-tile-label'>{escape(label)}</span>"
                "</div>"
            )
            for label, css_class in visuals
        )
        + "</div>"
        "</div>"
    )


def render_cosmic_identity_panel() -> str:
    return (
        "<section class='cosmic-identity-panel'>"
        "<div class='cosmic-identity-copy'>"
        "<div class='cosmic-identity-kicker'>DESIGN SYSTEM</div>"
        "<div class='cosmic-identity-title'>COSMIC GRAVITY</div>"
        "<div class='cosmic-identity-subtitle'>A control surface for the trading engine, composed as a black-gold instrument panel with dense data, soft glow, and orbit-like hierarchy.</div>"
        "</div>"
        "<div class='cosmic-identity-grid'>"
        f"{_render_cosmic_color_swatches()}"
        f"{_render_cosmic_component_gallery()}"
        f"{_render_cosmic_data_display()}"
        f"{_render_cosmic_visual_elements()}"
        "</div>"
        "</section>"
    )


def render_dashboard_shell(
    *,
    health_status: str,
    latest_update_display: str | None,
    execution_mode_label: str,
    execution_mode_state: str,
    active_room: str,
    room_nav_html: str,
    room_content_html: str,
) -> str:
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
        "<div class='header-status' data-dashboard-section='status'>"
        f"<div class='mode-badge {escape(execution_mode_state)}'>{escape(execution_mode_label)}</div>"
        f"<div class='status-badge {'ok' if health_status == 'OK' else 'fail'}'>{escape(health_status)}</div>"
        "</div>"
        "</header>"
        "<div class='toolbar' data-dashboard-section='toolbar'>"
        f"<div class='status-line'>Last update <strong id='last-updated-text'>{escape(format_timestamp_for_display(latest_update_display))}</strong></div>"
        "<div class='status-line'>Auto refresh 5s</div>"
        "<div class='toolbar-spacer'></div>"
        "<button type='button' class='action-button' id='manual-refresh-button'>MANUAL REFRESH</button>"
        "</div>"
        f"{room_nav_html}"
        f"<div class='dashboard-tab-shell' data-dashboard-active-room='{active_room}'>{room_content_html}</div>"
        "</div>"
        "</div>"
    )


def render_dashboard_document(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        f"{render_dashboard_head()}\n"
        f"{render_dashboard_body(snapshot, strategy_config=strategy_config, active_room=active_room, active_tab=active_tab, review_view=review_view, account_range_key=account_range_key)}"
        f"{render_dashboard_scripts()}"
    )


def render_dashboard_body(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    active_room = normalize_dashboard_room(active_room if active_room is not None else active_tab)
    review_view = normalize_review_view(review_view)
    account_range_key = normalize_account_range(account_range_key)
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
    config = strategy_config or snapshot.get("strategy_config") or {}
    execution_mode_label, execution_mode_state = _build_execution_mode(config)
    account_range_stats = _compute_account_range_stats(timeseries["account"])
    event_counts = snapshot.get("event_counts", {})
    decision_counts = {k: v for k, v in event_counts.items() if "decision" in k.lower() or "entry" in k.lower() or "signal" in k.lower()} or event_counts
    leader_history = list(reversed(snapshot.get("leader_history", [])))
    timeline_chart = _render_timeline_svg(events=leader_history)
    health_status = snapshot["health"]["overall_status"]
    # Build position cards
    equity_value = latest_account_snapshot.get("equity")
    position_details = build_position_details(latest_position_snapshot, equity_value=equity_value)
    trader_metrics = build_trader_summary_metrics(
        snapshot,
        position_details=position_details,
        range_key=account_range_key,
    )
    account_risk_html = _build_live_account_risk_panel(
        trader_metrics=trader_metrics,
        account_range_stats=account_range_stats,
    )
    core_lines_html = _build_live_core_lines_panel(timeseries["account"])
    home_command_html = _build_overview_home_command(
        position_details=position_details,
        trader_metrics=trader_metrics,
        account_range_stats=account_range_stats,
        health_status=health_status,
        account_range_key=account_range_key,
    )
    # Build trade history
    trade_fills = snapshot.get("recent_trade_fills") or []
    recent_broker_orders = snapshot.get("recent_broker_orders") or []
    recent_algo_orders = snapshot.get("recent_algo_orders") or []
    recent_stop_exit_summaries = snapshot.get("recent_stop_exit_summaries") or []
    trade_history_html = render_trade_history_table(trade_fills)
    recent_trade_round_trips = snapshot.get("recent_trade_round_trips") or []
    closed_trades_html = render_closed_trades_table(recent_trade_round_trips)
    leg_count_aggregate_html = render_trade_leg_count_aggregate_table(build_trade_leg_count_aggregates(recent_trade_round_trips))
    leg_index_aggregate_html = render_trade_leg_index_aggregate_table(build_trade_leg_index_aggregates(recent_trade_round_trips))
    stop_slippage_html = render_stop_slippage_table(recent_stop_exit_summaries)
    execution_flow_html = _build_execution_flow_panel(
        recent_broker_orders=recent_broker_orders,
        recent_algo_orders=recent_algo_orders,
        recent_trade_fills=trade_fills,
        recent_stop_exit_summaries=recent_stop_exit_summaries,
    )
    # Build strategy config
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
    warnings = snapshot.get("warnings", [])
    primary_source, primary_source_count = max(
        source_counts.items(),
        key=lambda item: (item[1], item[0]),
        default=("n/a", 0),
    )
    primary_source_label = primary_source if primary_source_count <= 0 else f"{primary_source} · {primary_source_count}"
    diagnostics_html = (
        "<div class='dashboard-section system-diagnostics-panel section-body'>"
        "<div class='section-header'>SYSTEM DIAGNOSTICS</div>"
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Health Status</div><div class='decision-value'>{escape(str(health_status))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Data Freshness</div><div class='decision-value'>{escape(format_timestamp_for_display(latest_update_display))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Warning Count</div><div class='decision-value'>{escape(str(len(warnings)))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Primary Source</div><div class='decision-value'>{escape(primary_source_label)}</div></div>"
        "</div>"
        "</div>"
    )
    warning_list_html = (
        "<div class='dashboard-section system-warning-panel section-body'>"
        "<div class='section-header'>ACTIVE WARNINGS</div>"
        "<div class='system-warning-list'>"
        + "".join(f"<div class='system-warning-item'>{escape(str(warning))}</div>" for warning in warnings[:5])
        + "</div>"
        "</div>"
        if warnings
        else ""
    )

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
    live_metrics_html = "".join(
        (
            f"<div class='metric {metric_state}'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value {'negative' if str(value).startswith('-') else 'positive' if str(value).startswith('+') else ''}'>{escape(str(value))}</div>"
            f"<div class='metric-sub'>{escape(subtext)}</div>"
            "</div>"
        )
        for label, value, subtext, metric_state in top_metric_cards
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
    room_nav_html = render_dashboard_room_nav(
        active_room,
        account_range_key=account_range_key,
        review_view=review_view,
    )
    daily_review_html = render_daily_review_panel(snapshot.get("daily_review_report"))
    room_content_html = {
        "live": render_dashboard_live_room(
            account_risk_html=account_risk_html,
            core_lines_html=core_lines_html,
            top_metrics_html=live_metrics_html,
            hero_html=hero_html,
            positions_html=render_position_cards(position_details),
            home_command_html=home_command_html,
            execution_flow_html=execution_flow_html,
        ),
        "review": render_dashboard_review_room(
            active_review_view=review_view if active_room == "review" else "overview",
            daily_review_html=daily_review_html,
            performance_summary_html=performance_summary_html,
            round_trip_detail_html=closed_trades_html,
            leg_count_aggregate_html=leg_count_aggregate_html,
            leg_index_aggregate_html=leg_index_aggregate_html,
            stop_slippage_html=stop_slippage_html,
        ),
        "system": render_dashboard_system_room(
            diagnostics_html=diagnostics_html,
            warning_list_html=warning_list_html,
            config_html=config_html,
            source_html=source_html,
            health_items_html=health_items_html,
            recent_events_html=recent_events_html,
        ),
    }[active_room]

    return (
        "<!-- render_dashboard_shell -->"
        + " "
        + render_dashboard_shell(
            health_status=health_status,
            latest_update_display=latest_update_display,
            execution_mode_label=execution_mode_label,
            execution_mode_state=execution_mode_state,
            active_room=active_room,
            room_nav_html=room_nav_html,
            room_content_html=room_content_html,
        )
        + f"  <div class=\"refresh-indicator {'error' if health_status != 'OK' else ''}\" id=\"refresh-indicator\">\n"
        + "    <div class=\"refresh-dot\"></div>\n"
        + f"    <span id=\"refresh-indicator-text\">{'Unable to refresh' if health_status != 'OK' else 'Auto refresh: 5s'}</span>\n"
        + "  </div>\n"
    )

def render_dashboard_html(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    return render_dashboard_document(
        snapshot,
        strategy_config=strategy_config,
        active_room=active_room,
        active_tab=active_tab,
        review_view=review_view,
        account_range_key=account_range_key,
    )
