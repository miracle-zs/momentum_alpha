from __future__ import annotations

from html import escape

from .dashboard_render_utils import format_timestamp_for_display


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
