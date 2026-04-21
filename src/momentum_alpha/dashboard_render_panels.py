from __future__ import annotations

import json
from decimal import Decimal
from html import escape

from .dashboard_render_utils import (
    DISPLAY_TIMEZONE_NAME,
    _daily_review_impact,
    _daily_review_win_rate,
    _build_dashboard_room_href,
    _format_datetime_compact,
    _format_datetime_review,
    _format_decimal_metric,
    _format_duration_seconds,
    _format_metric,
    _format_pct_value,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    _format_time_only,
    _format_time_short,
    _parse_decimal,
    format_timestamp_for_display,
    _parse_numeric,
)
from .dashboard_view_model import _compute_account_range_stats, _detect_account_discontinuity


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


def render_daily_review_panel(report: dict | None) -> str:
    if report is None:
        return (
            "<section class='chart-card daily-review-panel'>"
            "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>每日复盘</div>"
            "<div class='trade-history-empty'>No daily review report</div>"
            "</section>"
        )

    selected_report_date = str(report.get("selected_report_date") or report.get("report_date") or "n/a")
    available_report_dates = [str(item) for item in (report.get("available_report_dates") or []) if item]
    selected_index = available_report_dates.index(selected_report_date) if selected_report_date in available_report_dates else -1
    previous_report_date = available_report_dates[selected_index - 1] if selected_index > 0 else None
    next_report_date = available_report_dates[selected_index + 1] if selected_index >= 0 and selected_index < len(available_report_dates) - 1 else None
    latest_report_date = available_report_dates[-1] if available_report_dates else selected_report_date
    history_summary = report.get("history_summary") or {}
    history_total_actual = _parse_decimal(history_summary.get("actual_total_pnl"))
    history_total_replay = _parse_decimal(history_summary.get("counterfactual_total_pnl"))
    history_filter_impact = _daily_review_impact(
        actual=history_summary.get("actual_total_pnl"),
        replay=history_summary.get("counterfactual_total_pnl"),
    )
    history_summary_items = [
        ("Total Reports", str(history_summary.get("report_count", "n/a"))),
        ("Total Trades", str(history_summary.get("trade_count", "n/a"))),
        ("Cumulative Actual PnL", _format_decimal_metric(history_total_actual, signed=True)),
        ("Cumulative Replay PnL", _format_decimal_metric(history_total_replay, signed=True)),
        ("Cumulative Filter Impact", _format_decimal_metric(history_filter_impact, signed=True)),
        ("Historical Replayed Add-Ons", str(history_summary.get("replayed_add_on_count", "n/a"))),
    ]
    history_summary_html = "".join(
        (
            "<div class='daily-review-kpi daily-review-history-kpi'>"
            f"<div class='decision-label'>{escape(label)}</div>"
            f"<div class='decision-value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in history_summary_items
    )
    date_options = "".join(
        (
            "<option "
            f"value='{escape(date)}'"
            f"{' selected' if date == selected_report_date else ''}>"
            f"{escape(date)}"
            "</option>"
        )
        for date in available_report_dates
    )
    navigation_items = []
    if previous_report_date is None:
        navigation_items.append("<span class='daily-review-nav-link daily-review-nav-link-disabled'>Prev</span>")
    else:
        navigation_items.append(
            (
                "<a class='daily-review-nav-link' "
                f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily', extra_query={'report_date': previous_report_date}))}'>"
                "Prev"
                "</a>"
            )
        )
    navigation_items.append(
        f"<span class='daily-review-nav-current'>{escape(selected_report_date)}</span>"
    )
    if next_report_date is None:
        navigation_items.append("<span class='daily-review-nav-link daily-review-nav-link-disabled'>Next</span>")
    else:
        navigation_items.append(
            (
                "<a class='daily-review-nav-link' "
                f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily', extra_query={'report_date': next_report_date}))}'>"
                "Next"
                "</a>"
            )
        )
    navigation_items.append(
        (
            "<a class='daily-review-nav-link daily-review-nav-link-latest' "
            f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily'))}'>"
            f"Latest {escape(latest_report_date)}"
            "</a>"
        )
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
        ("Actual PnL", _format_decimal_metric(actual_total, signed=True)),
        ("Trades", str(report.get("trade_count", "n/a"))),
        ("Actual Win Rate", _format_decimal_metric(actual_win_rate, suffix="%")),
        ("Affected Trades", str(affected_trade_count)),
        ("Best Filter Save", _format_decimal_metric(best_filter_save, signed=True)),
        ("Filter Impact", _format_decimal_metric(total_impact, signed=True)),
        ("Replay PnL", _format_decimal_metric(replay_total, signed=True)),
        ("Replayed Add-Ons", str(report.get("replayed_add_on_count", "n/a"))),
        ("Replay Win Rate", _format_decimal_metric(replay_win_rate, suffix="%")),
        ("Avg Impact / Trade", _format_decimal_metric(avg_impact, signed=True)),
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
        "<div class='daily-review-toolbar'>"
        "<div class='daily-review-toolbar-left'>"
        "<div class='daily-review-eyebrow'>HISTORY</div>"
        "<form class='daily-review-date-form' method='get' action='?room=review&range=1D&review_view=daily'>"
        "<label class='daily-review-date-label' for='daily-review-date-select'>Jump to date</label>"
        f"<select id='daily-review-date-select' name='report_date' class='daily-review-date-select' onchange='this.form.submit()'>{date_options}</select>"
        "</form>"
        f"<div class='daily-review-nav'>{''.join(navigation_items)}</div>"
        "</div>"
        "<div class='daily-review-toolbar-note'>Historical Filter Impact is aggregated across every stored daily review.</div>"
        "</div>"
        "<div class='daily-review-history-summary'>"
        "<div class='daily-review-history-summary-head'>"
        "<div class='daily-review-eyebrow'>HISTORICAL SUMMARY</div>"
        "<div class='daily-review-history-title'>Cumulative Filter Impact</div>"
        "</div>"
        f"<div class='daily-review-kpi-grid daily-review-history-grid'>{history_summary_html}</div>"
        "</div>"
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
