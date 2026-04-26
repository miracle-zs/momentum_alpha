from __future__ import annotations

import json
from html import escape

from .dashboard_render_charts import _render_line_chart_svg
from .dashboard_render_utils import _format_metric, _format_pct_value
from .dashboard_view_model import _compute_account_range_stats, _detect_account_discontinuity


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
    try:
        open_risk_pct = float(account_metrics.get("open_risk_pct"))
    except (TypeError, ValueError):
        open_risk_state = ""
    else:
        if open_risk_pct > 60:
            open_risk_state = " danger"
        elif open_risk_pct >= 30:
            open_risk_state = " warning"
        else:
            open_risk_state = ""
    return (
        "<section class='dashboard-section live-account-risk-panel'>"
        "<div class='section-header'>ACCOUNT RISK</div>"
        "<div class='decision-grid live-account-risk-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Equity</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_equity')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Available Balance</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_available_balance')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Margin Usage</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('margin_usage_pct')))}</div></div>"
        f"<div class='decision-item{open_risk_state}'><div class='decision-label'>OPEN RISK / EQUITY</div><div class='decision-value'>{escape(_format_pct_value(account_metrics.get('open_risk_pct')))}</div><div class='decision-support'>{escape(_format_metric(account_metrics.get('open_risk')))} USDT at risk</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Today Net PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('today_net_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Unrealized PnL</div><div class='decision-value'>{escape(_format_metric(account_metrics.get('current_unrealized_pnl'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Drawdown</div><div class='decision-value'>{escape(_format_metric(account_range_stats.get('drawdown_abs'), signed=True))}</div><div class='decision-support'>{escape(_format_pct_value(account_range_stats.get('drawdown_pct'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Positions / Orders</div><div class='decision-value'>{escape(str(account_metrics.get('current_positions') or 0))} / {escape(str(account_metrics.get('current_orders') or 0))}</div></div>"
        "</div>"
        "</section>"
    )
def _build_live_core_lines_panel(core_live_points: list[dict]) -> str:
    chart_specs = (
        ("Account Equity", "equity", "#4cc9f0", core_live_points, "", False),
        ("Margin Usage %", "margin_usage_pct", "#ff8c42", core_live_points, "", False),
        ("Position Count", "position_count", "#36d98a", core_live_points, "", True),
        ("Open Risk", "open_risk", "#ff5d73", core_live_points, "live-core-line-card--open-risk", False),
    )
    chart_cards = "".join(
        (
            f"<div class='chart-card live-core-line-card {card_class}'>"
            f"<div class='section-header'>{escape(label)}</div>"
            f"{_render_line_chart_svg(points=points, value_key=value_key, stroke=color, fill=color, integer_axis=integer_axis)}"
            "</div>"
        )
        for label, value_key, color, points, card_class, integer_axis in chart_specs
    )
    return (
        "<section class='dashboard-section live-core-lines-panel'>"
        "<div class='section-header'>CORE LIVE LINES</div>"
        "<div class='live-core-lines-grid'>"
        f"{chart_cards}"
        "</div>"
        "</section>"
    )
