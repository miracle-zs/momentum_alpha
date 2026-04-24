from __future__ import annotations

from html import escape

from .dashboard_render_utils import _format_metric, _parse_numeric, format_timestamp_for_display


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
