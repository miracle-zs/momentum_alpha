from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal, ROUND_DOWN


def _round_down_to_increment(value: Decimal, increment: Decimal) -> Decimal:
    if increment <= 0:
        raise ValueError("increment must be positive")
    units = (value / increment).to_integral_value(rounding=ROUND_DOWN)
    return units * increment


@dataclass(frozen=True)
class SymbolFilters:
    step_size: Decimal
    min_qty: Decimal
    tick_size: Decimal

    def normalize_quantity(self, quantity: Decimal) -> Decimal:
        return _round_down_to_increment(quantity, self.step_size)

    def valid_quantity_or_none(self, quantity: Decimal) -> Decimal | None:
        normalized = self.normalize_quantity(quantity)
        if normalized < self.min_qty or normalized <= 0:
            return None
        return normalized

    def normalize_price(self, price: Decimal) -> Decimal:
        return _round_down_to_increment(price, self.tick_size)
