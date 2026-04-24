from __future__ import annotations

from html import escape

from .dashboard_render_utils import (
    _format_metric,
    _format_pct_value,
    _format_price,
    _parse_numeric,
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

    def _compute_slip_cost_value(item: dict) -> float | None:
        exit_quantity = _parse_numeric(item.get("exit_quantity"))
        if exit_quantity is None:
            return None
        slippage_abs = _parse_numeric(item.get("slippage_abs"))
        if slippage_abs is None:
            trigger_price = _parse_numeric(item.get("trigger_price"))
            average_exit_price = _parse_numeric(item.get("average_exit_price"))
            if trigger_price is None or average_exit_price is None:
                return None
            slippage_abs = max(trigger_price - average_exit_price, 0.0)
        return max(slippage_abs, 0.0) * exit_quantity

    header = (
        "<div class='analytics-row analytics-row-header'>"
        "<span class='analytics-main'>SYMBOL</span>"
        "<span>TRIGGER</span>"
        "<span>EXEC</span>"
        "<span>SLIP %</span>"
        "<span>SLIP COST</span>"
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
        slip_cost_value = _compute_slip_cost_value(item)
        slip_cost = escape(_format_metric(slip_cost_value))
        slip_cost_class = "side-sell" if slip_cost_value and slip_cost_value > 0 else ""
        rows += (
            f"<div class='analytics-row'>"
            f"<span class='analytics-main'><b>{symbol}</b></span>"
            f"<span>{trigger_price}</span>"
            f"<span>{average_exit_price}</span>"
            f"<span>{slippage_pct}</span>"
            f"<span class='{slip_cost_class}'>{slip_cost}</span>"
            f"</div>"
        )
        cards += (
            f"<div class='analytics-card'>"
            f"<div class='analytics-card-main'><b>{symbol}</b><span>{slippage_pct}</span></div>"
            f"<div class='analytics-card-meta'><span>Trigger {trigger_price}</span><span>Exec {average_exit_price}</span></div>"
            f"<div class='analytics-card-meta'><span>Slip Cost</span><span class='{slip_cost_class}'>{slip_cost}</span></div>"
            f"</div>"
        )
    return (
        f"<div class='analytics-table desktop-only'>{header}{rows}</div>"
        f"<div class='analytics-card-list mobile-only'>{cards}</div>"
    )
