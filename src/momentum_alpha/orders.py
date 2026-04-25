from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.exchange_info import ExchangeSymbol
from momentum_alpha.trace_ids import build_order_intent_id


STRATEGY_CLIENT_ORDER_ID_PREFIX = "ma_"


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _normalized_quantity(symbol: ExchangeSymbol, quantity: Decimal) -> Decimal:
    normalized = symbol.filters.valid_quantity_or_none(quantity)
    if normalized is None:
        raise ValueError(f"quantity is invalid for {symbol.symbol}")
    return normalized


def build_client_order_id(
    *,
    symbol: str,
    opened_at: datetime,
    leg_type: str,
    order_kind: str,
    sequence: int,
) -> str:
    intent_token = build_order_intent_id(symbol=symbol, opened_at=opened_at, leg_type=leg_type, sequence=sequence)
    kind_token = "e" if order_kind == "entry" else "s"
    return f"{intent_token}{kind_token}"


def is_strategy_client_order_id(client_order_id: str | None) -> bool:
    return bool(client_order_id and client_order_id.startswith(STRATEGY_CLIENT_ORDER_ID_PREFIX))


def build_market_entry_order(
    *,
    symbol: ExchangeSymbol,
    quantity: Decimal,
    client_order_id: str | None = None,
    position_side: str | None = None,
) -> dict[str, str]:
    normalized_quantity = _normalized_quantity(symbol, quantity)
    payload = {
        "symbol": symbol.symbol,
        "side": "BUY",
        "type": "MARKET",
        "quantity": _format_decimal(normalized_quantity),
    }
    if client_order_id:
        payload["newClientOrderId"] = client_order_id
    if position_side:
        payload["positionSide"] = position_side
    return payload


def build_stop_market_order(
    *,
    symbol: ExchangeSymbol,
    quantity: Decimal,
    stop_price: Decimal,
    client_order_id: str | None = None,
    position_side: str | None = None,
) -> dict[str, str]:
    normalized_quantity = _normalized_quantity(symbol, quantity)
    normalized_stop_price = symbol.filters.normalize_price(stop_price)
    payload = {
        "symbol": symbol.symbol,
        "side": "SELL",
        "type": "STOP_MARKET",
        "quantity": _format_decimal(normalized_quantity),
        "stopPrice": _format_decimal(normalized_stop_price.quantize(symbol.filters.tick_size)),
        "workingType": "CONTRACT_PRICE",
    }
    if client_order_id:
        payload["newClientOrderId"] = client_order_id
    if position_side:
        payload["positionSide"] = position_side
    return payload
