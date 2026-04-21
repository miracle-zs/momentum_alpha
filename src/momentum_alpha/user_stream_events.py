from __future__ import annotations

import json
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from dataclasses import replace

from momentum_alpha.binance_client import BINANCE_FSTREAM_WS_URL, BINANCE_TESTNET_FSTREAM_WS_URL
from momentum_alpha.execution import apply_fill
from momentum_alpha.models import Position, PositionLeg, StrategyState
from momentum_alpha.orders import is_strategy_client_order_id


def _parse_decimal(value):
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


@dataclass(frozen=True)
class UserStreamEvent:
    event_type: str
    payload: dict
    symbol: str | None = None
    order_status: str | None = None
    execution_type: str | None = None
    side: str | None = None
    average_price: Decimal | None = None
    filled_quantity: Decimal | None = None
    last_filled_price: Decimal | None = None
    last_filled_quantity: Decimal | None = None
    realized_pnl: Decimal | None = None
    commission: Decimal | None = None
    commission_asset: str | None = None
    stop_price: Decimal | None = None
    original_order_type: str | None = None
    event_time: datetime | None = None
    order_id: int | None = None
    trade_id: int | None = None
    client_order_id: str | None = None
    account_update_reason: str | None = None
    # Algo order fields
    algo_id: int | None = None
    client_algo_id: str | None = None
    algo_status: str | None = None
    trigger_price: Decimal | None = None


def parse_user_stream_event(payload: dict) -> UserStreamEvent:
    event_type = payload.get("e", "UNKNOWN")
    order_payload = payload.get("o", {})
    symbol = order_payload.get("s") or payload.get("s")
    event_time_ms = payload.get("T") or payload.get("E") or payload.get("t")

    return UserStreamEvent(
        event_type=event_type,
        payload=payload,
        symbol=symbol,
        order_status=order_payload.get("X") or payload.get("X") or payload.get("algoStatus"),
        execution_type=order_payload.get("x"),
        side=order_payload.get("S") or payload.get("S"),
        average_price=_parse_decimal(order_payload.get("ap")),
        filled_quantity=_parse_decimal(order_payload.get("z")),
        last_filled_price=_parse_decimal(order_payload.get("L")),
        last_filled_quantity=_parse_decimal(order_payload.get("l")),
        realized_pnl=_parse_decimal(order_payload.get("rp")),
        commission=_parse_decimal(order_payload.get("n")),
        commission_asset=order_payload.get("N"),
        stop_price=_parse_decimal(order_payload.get("sp")),
        original_order_type=order_payload.get("ot") or payload.get("orderType"),
        event_time=datetime.fromtimestamp(int(event_time_ms) / 1000, tz=timezone.utc) if event_time_ms is not None else None,
        order_id=order_payload.get("i"),
        trade_id=order_payload.get("t"),
        client_order_id=order_payload.get("c"),
        account_update_reason=(payload.get("a") or {}).get("m"),
        # Algo order fields
        algo_id=payload.get("algoId") or order_payload.get("algoId"),
        client_algo_id=payload.get("clientAlgoId") or order_payload.get("clientAlgoId"),
        algo_status=payload.get("algoStatus") or order_payload.get("algoStatus"),
        trigger_price=_parse_decimal(payload.get("triggerPrice") or order_payload.get("triggerPrice")),
    )


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
    terminal_statuses = {"TRIGGERED", "CANCELLED", "EXPIRED", "FAILED"}
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


def extract_flat_position_symbols(event: UserStreamEvent) -> tuple[str, ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    flat_symbols: list[str] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount == Decimal("0"):
            flat_symbols.append(symbol)
    return tuple(flat_symbols)


def extract_positive_account_positions(event: UserStreamEvent) -> tuple[tuple[str, Decimal, Decimal], ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    positive_positions: list[tuple[str, Decimal, Decimal]] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
            entry_price = Decimal(str(position_payload.get("ep", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount > Decimal("0"):
            positive_positions.append((symbol, position_amount, entry_price))
    return tuple(positive_positions)


def resolve_stop_price_from_order_statuses(*, symbol: str, order_statuses: dict[str, dict] | None) -> Decimal | None:
    if not order_statuses:
        return None
    # Active statuses include both regular order statuses and algo order statuses
    active_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING"}
    fallback_stop_price: Decimal | None = None
    for order_snapshot in order_statuses.values():
        if order_snapshot.get("symbol") != symbol:
            continue
        if order_snapshot.get("side") != "SELL":
            continue
        if order_snapshot.get("original_order_type") != "STOP_MARKET":
            continue
        if order_snapshot.get("status") not in active_statuses:
            continue
        stop_price = order_snapshot.get("stop_price")
        if stop_price in (None, ""):
            continue
        try:
            parsed = Decimal(str(stop_price))
        except (InvalidOperation, TypeError):
            continue
        if is_strategy_client_order_id(order_snapshot.get("client_order_id")):
            return parsed
        if fallback_stop_price is None:
            fallback_stop_price = parsed
    return fallback_stop_price


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
