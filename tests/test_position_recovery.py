import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PositionRecoveryTests(unittest.TestCase):
    def test_fetch_complete_history_splits_saturated_ranges(self) -> None:
        from momentum_alpha.position_recovery import fetch_complete_history

        calls = []

        def fetch(**kwargs):
            calls.append((kwargs["start_time_ms"], kwargs["end_time_ms"]))
            if kwargs["start_time_ms"] == 0 and kwargs["end_time_ms"] == 9:
                return [{"id": 1}, {"id": 2}]
            return [{"id": kwargs["start_time_ms"]}]

        rows = fetch_complete_history(fetch, symbol="BTCUSDT", start_time_ms=0, end_time_ms=9, limit=2)

        self.assertEqual(len(calls), 3)
        self.assertEqual({row["id"] for row in rows}, {0, 5})

    def test_rebuild_position_groups_partial_fills_by_strategy_order(self) -> None:
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.position_recovery import rebuild_position_from_trade_history

        opened_at = datetime(2026, 7, 14, 14, 18, tzinfo=timezone.utc)
        position = Position(
            symbol="BSBUSDT",
            stop_price=Decimal("0.14585"),
            legs=(
                PositionLeg(
                    "BSBUSDT",
                    Decimal("75"),
                    Decimal("0.1570"),
                    Decimal("0.14585"),
                    opened_at,
                    "base",
                    leg_source="account_update",
                ),
                PositionLeg(
                    "BSBUSDT",
                    Decimal("589"),
                    Decimal("0.1578"),
                    Decimal("0.14585"),
                    opened_at,
                    "base",
                    entry_order_id="ma_260714141800_BSBUSDT_b00e",
                    leg_source="user_stream",
                ),
                PositionLeg(
                    "BSBUSDT",
                    Decimal("242"),
                    Decimal("0.1575"),
                    Decimal("0.14585"),
                    opened_at,
                    "add_on",
                    leg_source="reconciliation",
                ),
            ),
        )
        quantities = ["75", "174", "35", "33", "589"]
        prices = ["0.1570", "0.1572", "0.1574", "0.1576", "0.1578"]
        trades = [
            {
                "symbol": "BSBUSDT",
                "id": index,
                "orderId": 101,
                "side": "BUY",
                "price": price,
                "qty": quantity,
                "time": int(opened_at.timestamp() * 1000) + index,
            }
            for index, (quantity, price) in enumerate(zip(quantities, prices), start=1)
        ]
        orders = [
            {
                "orderId": 101,
                "clientOrderId": "ma_260714141800_BSBUSDT_b00e",
                "side": "BUY",
            }
        ]

        rebuilt = rebuild_position_from_trade_history(position=position, trades=trades, orders=orders)

        self.assertIsNotNone(rebuilt)
        assert rebuilt is not None
        self.assertEqual(rebuilt.total_quantity, Decimal("906"))
        self.assertEqual(len(rebuilt.legs), 1)
        self.assertEqual(rebuilt.legs[0].leg_type, "base")
        self.assertEqual(rebuilt.legs[0].entry_order_id, "ma_260714141800_BSBUSDT_b00e")
        self.assertEqual(rebuilt.legs[0].leg_source, "trade_recovery")
        expected_price = sum(
            Decimal(quantity) * Decimal(price)
            for quantity, price in zip(quantities, prices)
        ) / Decimal("906")
        self.assertEqual(rebuilt.legs[0].entry_price, expected_price)

    def test_rebuild_position_refuses_incomplete_trade_history(self) -> None:
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.position_recovery import rebuild_position_from_trade_history

        opened_at = datetime(2026, 7, 14, 14, 18, tzinfo=timezone.utc)
        position = Position(
            symbol="BSBUSDT",
            stop_price=Decimal("0.14585"),
            legs=(
                PositionLeg(
                    "BSBUSDT",
                    Decimal("906"),
                    Decimal("0.1575"),
                    Decimal("0.14585"),
                    opened_at,
                    "base",
                    leg_source="reconciliation",
                ),
            ),
        )

        rebuilt = rebuild_position_from_trade_history(
            position=position,
            trades=[
                {
                    "id": 1,
                    "orderId": 101,
                    "side": "BUY",
                    "price": "0.1575",
                    "qty": "664",
                    "time": int(opened_at.timestamp() * 1000),
                }
            ],
            orders=[
                {
                    "orderId": 101,
                    "clientOrderId": "ma_260714141800_BSBUSDT_b00e",
                    "side": "BUY",
                }
            ],
        )

        self.assertIsNone(rebuilt)


if __name__ == "__main__":
    unittest.main()
