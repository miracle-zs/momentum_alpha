from __future__ import annotations

from html import escape

from .dashboard_render_utils import _build_dashboard_room_href, _format_metric, _parse_numeric


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
