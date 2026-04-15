from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from momentum_alpha.binance_filters import SymbolFilters


@dataclass(frozen=True)
class ExchangeSymbol:
    symbol: str
    status: str
    filters: SymbolFilters
    min_notional: Decimal


def _filters_by_type(raw_filters: list[dict]) -> dict[str, dict]:
    return {item["filterType"]: item for item in raw_filters}


def parse_exchange_info(payload: dict) -> dict[str, ExchangeSymbol]:
    symbols: dict[str, ExchangeSymbol] = {}
    for item in payload.get("symbols", []):
        if item.get("contractType") != "PERPETUAL":
            continue
        if item.get("quoteAsset") != "USDT":
            continue

        filters = _filters_by_type(item.get("filters", []))
        lot_size = filters.get("LOT_SIZE")
        market_lot_size = filters.get("MARKET_LOT_SIZE", lot_size)
        price_filter = filters.get("PRICE_FILTER")
        min_notional = filters.get("MIN_NOTIONAL")
        if not lot_size or not price_filter or not market_lot_size:
            continue

        symbol_filters = SymbolFilters(
            step_size=Decimal(market_lot_size["stepSize"]),
            min_qty=Decimal(market_lot_size["minQty"]),
            tick_size=Decimal(price_filter["tickSize"]),
        )
        symbols[item["symbol"]] = ExchangeSymbol(
            symbol=item["symbol"],
            status=item.get("status", "UNKNOWN"),
            filters=symbol_filters,
            min_notional=Decimal(min_notional["notional"]) if min_notional else Decimal("0"),
        )
    return symbols
