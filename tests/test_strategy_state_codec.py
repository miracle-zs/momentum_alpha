import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StrategyStateCodecTests(unittest.TestCase):
    def test_round_trip_strategy_state(self) -> None:
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.strategy_state_codec import (
            StoredStrategyState,
            deserialize_strategy_state,
            serialize_strategy_state,
        )

        opened_at = datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc)
        state = StoredStrategyState(
            current_day="2026-04-15",
            previous_leader_symbol="BTCUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("106"),
                    legs=(
                        PositionLeg(
                            symbol="ETHUSDT",
                            quantity=Decimal("2"),
                            entry_price=Decimal("108"),
                            stop_price=Decimal("106"),
                            opened_at=opened_at,
                            leg_type="stream_fill",
                        ),
                    ),
                )
            },
            processed_event_ids={"evt-1": "2026-04-15T01:00:00+00:00"},
            order_statuses={"101": {"symbol": "ETHUSDT", "status": "NEW"}},
            recent_stop_loss_exits={"ETHUSDT": "2026-04-15T01:05:00+00:00"},
        )

        payload = serialize_strategy_state(state)
        restored = deserialize_strategy_state(payload)

        self.assertEqual(restored.current_day, "2026-04-15")
        self.assertEqual(restored.previous_leader_symbol, "BTCUSDT")
        self.assertEqual(restored.positions["ETHUSDT"].total_quantity, Decimal("2"))
        self.assertEqual(restored.processed_event_ids, {"evt-1": "2026-04-15T01:00:00+00:00"})
        self.assertEqual(restored.order_statuses["101"]["status"], "NEW")
        self.assertEqual(restored.recent_stop_loss_exits["ETHUSDT"], "2026-04-15T01:05:00+00:00")

    def test_deserialize_legacy_event_id_list(self) -> None:
        from momentum_alpha.strategy_state_codec import deserialize_strategy_state

        restored = deserialize_strategy_state(
            {
                "current_day": "2026-04-15",
                "previous_leader_symbol": None,
                "positions": {},
                "processed_event_ids": ["evt-1"],
                "order_statuses": {},
                "recent_stop_loss_exits": {},
            }
        )

        self.assertIn("evt-1", restored.processed_event_ids)
        self.assertIsInstance(restored.processed_event_ids["evt-1"], str)


if __name__ == "__main__":
    unittest.main()
