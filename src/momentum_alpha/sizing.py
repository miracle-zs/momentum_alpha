from __future__ import annotations

from decimal import Decimal

from momentum_alpha.binance_filters import SymbolFilters


def size_from_stop_budget(
    entry_price: Decimal,
    stop_price: Decimal,
    stop_budget: Decimal,
    filters: SymbolFilters | None = None,
) -> Decimal | None:
    distance = entry_price - stop_price
    if distance <= 0:
        return None

    raw_quantity = stop_budget / distance
    if filters is None:
        return raw_quantity
    return filters.valid_quantity_or_none(raw_quantity)
