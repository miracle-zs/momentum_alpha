from __future__ import annotations

from .user_stream_event_model import UserStreamEvent
from .user_stream_event_parser import _parse_decimal


def extract_trade_fill(event: UserStreamEvent) -> dict | None:
    if event.event_type != "ORDER_TRADE_UPDATE":
        return None
    if event.execution_type != "TRADE":
        return None
    if event.symbol is None or event.order_id is None or event.trade_id is None:
        return None
    return {
        "symbol": event.symbol,
        "order_id": str(event.order_id),
        "trade_id": str(event.trade_id),
        "client_order_id": event.client_order_id,
        "order_status": event.order_status,
        "execution_type": event.execution_type,
        "side": event.side,
        "order_type": event.original_order_type,
        "quantity": event.last_filled_quantity,
        "cumulative_quantity": event.filled_quantity,
        "average_price": event.average_price,
        "last_price": event.last_filled_price,
        "realized_pnl": event.realized_pnl,
        "commission": event.commission,
        "commission_asset": event.commission_asset,
    }


def extract_account_flows(event: UserStreamEvent) -> list[dict]:
    if event.event_type != "ACCOUNT_UPDATE":
        return []
    account_payload = event.payload.get("a", {})
    flows: list[dict] = []
    for balance in account_payload.get("B", []):
        flows.append(
            {
                "reason": account_payload.get("m"),
                "asset": balance.get("a"),
                "wallet_balance": _parse_decimal(balance.get("wb")),
                "cross_wallet_balance": _parse_decimal(balance.get("cw")),
                "balance_change": _parse_decimal(balance.get("bc")),
            }
        )
    return flows


def extract_algo_order_event(event: UserStreamEvent) -> dict | None:
    if event.event_type != "ALGO_UPDATE":
        return None
    if event.algo_id is None and event.client_algo_id is None:
        return None
    return {
        "symbol": event.symbol,
        "algo_id": str(event.algo_id) if event.algo_id is not None else None,
        "client_algo_id": event.client_algo_id,
        "algo_status": event.algo_status,
        "side": event.side,
        "order_type": event.original_order_type,
        "trigger_price": event.trigger_price,
    }


def extract_order_status_update(event: UserStreamEvent) -> tuple[str, dict | None] | None:
    if event.event_type != "ORDER_TRADE_UPDATE" or event.order_id is None:
        return None
    if (
        event.order_status == "FILLED"
        and event.side == "SELL"
        and event.original_order_type == "STOP_MARKET"
    ):
        return (str(event.order_id), None)
    return (
        str(event.order_id),
        {
            "symbol": event.symbol,
            "status": event.order_status,
            "execution_type": event.execution_type,
            "side": event.side,
            "client_order_id": event.client_order_id,
            "original_order_type": event.original_order_type,
            "stop_price": str(event.stop_price) if event.stop_price is not None else None,
            "event_time": event.event_time.isoformat() if event.event_time is not None else None,
        },
    )


def extract_algo_order_status_update(event: UserStreamEvent) -> tuple[str, dict | None] | None:
    """Extract algo order status from ALGO_UPDATE events for stop-loss tracking."""
    if event.event_type != "ALGO_UPDATE":
        return None
    key_id = event.client_algo_id or event.algo_id
    if key_id is None:
        return None
    # Use "algo:" prefix to distinguish from regular orders.
    # Prefer clientAlgoId so updates remain stable even if algoId is absent.
    key = f"algo:{key_id}"
    # Terminal states - remove from tracking
    terminal_statuses = {"TRIGGERED", "FINISHED", "CANCELED", "CANCELLED", "EXPIRED", "REJECTED", "FAILED"}
    if event.algo_status in terminal_statuses:
        return (key, None)
    return (
        key,
        {
            "symbol": event.symbol,
            "status": event.algo_status,
            "side": event.side,
            "client_order_id": event.client_algo_id,
            "original_order_type": "STOP_MARKET",  # Algo orders for this strategy are stop orders
            "stop_price": str(event.trigger_price) if event.trigger_price is not None else None,
            "event_time": event.event_time.isoformat() if event.event_time is not None else None,
        },
    )
