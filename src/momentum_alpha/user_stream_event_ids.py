from __future__ import annotations

from momentum_alpha.orders import is_strategy_client_order_id

from .user_stream_event_model import UserStreamEvent


def user_stream_event_id(event: UserStreamEvent) -> str | None:
    if event.event_type != "ORDER_TRADE_UPDATE":
        return None
    if event.order_id is None:
        return None
    if event.trade_id is not None:
        return f"{event.event_type}:{event.order_id}:trade:{event.trade_id}"
    event_time = "" if event.event_time is None else event.event_time.isoformat()
    execution_type = "" if event.execution_type is None else event.execution_type
    order_status = "" if event.order_status is None else event.order_status
    return f"{event.event_type}:{event.order_id}:state:{execution_type}:{order_status}:{event_time}"


def _is_strategy_stop_fill(event: UserStreamEvent) -> bool:
    if event.side != "SELL":
        return False
    if event.original_order_type == "STOP_MARKET":
        return True
    if not is_strategy_client_order_id(event.client_order_id):
        return False
    return bool(event.client_order_id and event.client_order_id.endswith("s"))


def _is_strategy_stop_order_for_symbol(symbol: str, order_statuses: dict[str, dict] | None) -> bool:
    """Check if there's a strategy stop-loss order for the given symbol.

    This is used to detect when a position is closed due to stop-loss trigger.
    """
    if order_statuses is None:
        return False
    for order_id, snapshot in order_statuses.items():
        if snapshot is None:
            continue
        if snapshot.get("symbol") != symbol:
            continue
        # Check if it's a stop-loss order
        order_type = snapshot.get("original_order_type")
        client_order_id = snapshot.get("client_order_id", "")
        if order_type == "STOP_MARKET":
            return True
        if is_strategy_client_order_id(client_order_id) and client_order_id.endswith("s"):
            return True
    return False
