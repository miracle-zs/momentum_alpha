from __future__ import annotations

from html import escape

from .dashboard_render_utils import (
    _format_duration_seconds,
    _format_datetime_compact,
    _format_metric,
    _format_pct_value,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    _format_time_only,
    _parse_numeric,
    format_timestamp_for_display,
)


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
