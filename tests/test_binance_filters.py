import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BinanceFilterTests(unittest.TestCase):
    def test_rounds_quantity_down_to_step_size(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters

        filters = SymbolFilters(step_size=Decimal("0.1"), min_qty=Decimal("1"), tick_size=Decimal("0.01"))
        self.assertEqual(filters.normalize_quantity(Decimal("1.29")), Decimal("1.2"))

    def test_rejects_quantity_below_minimum(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters

        filters = SymbolFilters(step_size=Decimal("0.1"), min_qty=Decimal("1"), tick_size=Decimal("0.01"))
        self.assertIsNone(filters.valid_quantity_or_none(Decimal("0.9")))

    def test_rounds_price_down_to_tick_size(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters

        filters = SymbolFilters(step_size=Decimal("0.1"), min_qty=Decimal("1"), tick_size=Decimal("0.05"))
        self.assertEqual(filters.normalize_price(Decimal("123.47")), Decimal("123.45"))
