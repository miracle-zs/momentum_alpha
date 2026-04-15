import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ModelTests(unittest.TestCase):
    def test_leg_risk_uses_entry_minus_stop(self) -> None:
        from momentum_alpha.models import PositionLeg

        leg = PositionLeg(
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            entry_price=Decimal("110"),
            stop_price=Decimal("100"),
            opened_at=datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc),
            leg_type="base",
        )
        self.assertEqual(leg.stop_risk, Decimal("10"))

    def test_position_tracks_total_quantity(self) -> None:
        from momentum_alpha.models import Position, PositionLeg

        opened_at = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        position = Position(
            symbol="BTCUSDT",
            stop_price=Decimal("100"),
            legs=(
                PositionLeg("BTCUSDT", Decimal("1"), Decimal("110"), Decimal("100"), opened_at, "base"),
                PositionLeg("BTCUSDT", Decimal("2"), Decimal("120"), Decimal("100"), opened_at, "add_on"),
            ),
        )
        self.assertEqual(position.total_quantity, Decimal("3"))
