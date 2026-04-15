from __future__ import annotations

from decimal import Decimal

from momentum_alpha.exchange_info import ExchangeSymbol


def _format_decimal(value: Decimal) -> str:
    return format(value, "f")


def _normalized_quantity(symbol: ExchangeSymbol, quantity: Decimal) -> Decimal:
    normalized = symbol.filters.valid_quantity_or_none(quantity)
    if normalized is None:
        raise ValueError(f"quantity is invalid for {symbol.symbol}")
    return normalized


def build_market_entry_order(*, symbol: ExchangeSymbol, quantity: Decimal) -> dict[str, str]:
    normalized_quantity = _normalized_quantity(symbol, quantity)
    return {
        "symbol": symbol.symbol,
        "side": "BUY",
        "type": "MARKET",
        "quantity": _format_decimal(normalized_quantity),
    }


def build_stop_market_order(*, symbol: ExchangeSymbol, quantity: Decimal, stop_price: Decimal) -> dict[str, str]:
    normalized_quantity = _normalized_quantity(symbol, quantity)
    normalized_stop_price = symbol.filters.normalize_price(stop_price)
    return {
        "symbol": symbol.symbol,
        "side": "SELL",
        "type": "STOP_MARKET",
        "quantity": _format_decimal(normalized_quantity),
        "stopPrice": _format_decimal(normalized_stop_price.quantize(symbol.filters.tick_size)),
        "workingType": "CONTRACT_PRICE",
    }
