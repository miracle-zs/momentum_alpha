from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.exchange_info import ExchangeSymbol


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
    timestamp_token = opened_at.astimezone(timezone.utc).strftime("%y%m%d%H%M%S")
    symbol_token = "".join(ch for ch in symbol.upper() if ch.isalnum())[-10:] or "UNKNOWN"
    leg_token = "b" if leg_type == "base" else "a"
    kind_token = "e" if order_kind == "entry" else "s"
    return f"{STRATEGY_CLIENT_ORDER_ID_PREFIX}{timestamp_token}_{symbol_token}_{leg_token}{sequence:02d}{kind_token}"


def is_strategy_client_order_id(client_order_id: str | None) -> bool:
    return bool(client_order_id and client_order_id.startswith(STRATEGY_CLIENT_ORDER_ID_PREFIX))


def build_market_entry_order(
    *,
    symbol: ExchangeSymbol,
    quantity: Decimal,
    client_order_id: str | None = None,
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
    return payload


def build_stop_market_order(
    *,
    symbol: ExchangeSymbol,
    quantity: Decimal,
    stop_price: Decimal,
    client_order_id: str | None = None,
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
    return payload
