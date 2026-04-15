import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class SizingTests(unittest.TestCase):
    def test_sizes_entry_from_fixed_stop_loss_budget(self) -> None:
        from momentum_alpha.sizing import size_from_stop_budget

        quantity = size_from_stop_budget(
            entry_price=Decimal("110"),
            stop_price=Decimal("100"),
            stop_budget=Decimal("10"),
        )
        self.assertEqual(quantity, Decimal("1"))

    def test_returns_none_when_stop_is_not_below_entry(self) -> None:
        from momentum_alpha.sizing import size_from_stop_budget

        self.assertIsNone(
            size_from_stop_budget(
                entry_price=Decimal("100"),
                stop_price=Decimal("100"),
                stop_budget=Decimal("10"),
            )
        )
