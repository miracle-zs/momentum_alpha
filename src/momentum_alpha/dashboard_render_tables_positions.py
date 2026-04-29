from __future__ import annotations

from html import escape

from .dashboard_render_utils import _format_metric, _parse_numeric, format_timestamp_for_display


def render_position_cards(positions: list[dict]) -> str:
    """Render HTML for active position details."""
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

    def _value_state_class(value: object | None) -> str:
        parsed = _parse_numeric(value)
        if parsed is None:
            return "value-neutral"
        if parsed > 0:
            return "value-positive"
        if parsed < 0:
            return "value-negative"
        return "value-neutral"

    headers = (
        "#",
        "Symbol",
        "Side",
        "Size",
        "Entry",
        "Mark",
        "Unrealized PnL",
        "PnL %",
        "R Multiple",
        "Open Risk",
        "Stop / Distance",
        "Notional",
        "Entry Time",
        "Legs",
    )
    header_html = "".join(f"<th scope='col'>{escape(header)}</th>" for header in headers)
    rows = ""
    for index, pos in enumerate(sorted(positions, key=_position_sort_key), start=1):
        symbol = escape(str(pos.get("symbol") or "-"))
        raw_direction = str(pos.get("direction") or "LONG").upper()
        direction = escape(raw_direction)
        direction_state = "short" if raw_direction == "SHORT" else "long"
        qty = escape(str(pos.get("total_quantity") or "0"))
        entry = escape(str(pos.get("entry_price") or "n/a"))
        stop = escape(str(pos.get("stop_price") or "n/a"))
        risk = _display_metric_value(pos.get("risk"), suffix=" USDT")
        risk_pct = _display_metric_value(pos.get("risk_pct_of_equity"), suffix="%")
        opened_at = _display_metric_value(format_timestamp_for_display(pos.get("opened_at")))
        latest_price = _display_live_price_metric(pos.get("latest_price"))
        mtm_pnl = _display_live_price_metric(pos.get("mtm_pnl"))
        pnl_pct = _display_live_price_metric(pos.get("pnl_pct"), suffix="%")
        distance_to_stop = _display_live_price_metric(pos.get("distance_to_stop_pct"), suffix="%")
        notional = _display_live_price_metric(pos.get("notional_exposure"))
        r_multiple = _display_live_price_metric(pos.get("r_multiple"), suffix="R")
        legs = pos.get("legs") or []
        leg_count = pos.get("leg_count")
        if leg_count in (None, ""):
            leg_count = len(legs) if legs else None

        legs_detail = " | ".join(
            f"Leg {i+1}: {escape(str(leg.get('type') or '-'))} · {escape(str((leg.get('time') or '')[:10]))}"
            for i, leg in enumerate(legs)
        ) if legs else "No legs"
        legs_summary = "n/a" if leg_count in (None, "") else f"{escape(str(leg_count))} leg{'s' if str(leg_count) != '1' else ''}"

        rows += (
            "<tr>"
            f"<td class='position-index-cell'>{index}</td>"
            f"<td class='position-symbol-cell'>{symbol}</td>"
            f"<td><span class='position-side position-side-{direction_state}'>{direction}</span></td>"
            f"<td>{qty}</td>"
            f"<td>{entry}</td>"
            f"<td>{latest_price}</td>"
            f"<td class='{_value_state_class(pos.get('mtm_pnl'))}'>{mtm_pnl}</td>"
            f"<td class='{_value_state_class(pos.get('pnl_pct'))}'>{pnl_pct}</td>"
            f"<td class='{_value_state_class(pos.get('r_multiple'))}'>{r_multiple}</td>"
            f"<td><span class='position-primary'>{risk}</span><span class='position-subtle'>Risk % of Equity {risk_pct}</span></td>"
            f"<td><span class='position-primary metric-danger'>{stop}</span><span class='position-subtle'>Distance to Stop % {distance_to_stop}</span></td>"
            f"<td>{notional}</td>"
            f"<td>{opened_at}</td>"
            f"<td><span class='position-legs-summary' title='{escape(legs_detail)}'>{legs_summary}</span></td>"
            "</tr>"
        )

    return f"<div class='positions-table-shell'><table class='positions-table'><thead><tr>{header_html}</tr></thead><tbody>{rows}</tbody></table></div>"
