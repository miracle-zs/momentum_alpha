from __future__ import annotations

from html import escape

from .dashboard_render_utils import (
    _format_datetime_compact,
    _format_duration_seconds,
    _format_metric,
    _format_price,
    _format_quantity,
    _format_round_trip_exit_reason,
    _format_round_trip_id_label,
    _format_time_only,
    _parse_numeric,
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
