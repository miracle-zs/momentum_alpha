import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StateStoreTests(unittest.TestCase):
    def test_save_and_load_state_round_trip(self) -> None:
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            expected = StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            store.save(expected)

            loaded = store.load()
            self.assertEqual(loaded.current_day, "2026-04-15")
            self.assertEqual(loaded.previous_leader_symbol, "BTCUSDT")

    def test_save_and_load_positions_round_trip(self) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            expected = StoredStrategyState(
                current_day="2026-04-15",
                previous_leader_symbol="BTCUSDT",
                positions={
                    "ETHUSDT": Position(
                        symbol="ETHUSDT",
                        stop_price=Decimal("106"),
                        legs=(
                            PositionLeg(
                                "ETHUSDT",
                                Decimal("2"),
                                Decimal("108"),
                                Decimal("106"),
                                datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc),
                                "stream_fill",
                            ),
                        ),
                    )
                },
            )
            store.save(expected)

            loaded = store.load()
            self.assertIn("ETHUSDT", loaded.positions)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))

    def test_load_returns_none_when_file_missing(self) -> None:
        from momentum_alpha.state_store import FileStateStore

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "missing.json"
            store = FileStateStore(path=path)
            self.assertIsNone(store.load())

    def test_merge_save_preserves_existing_positions_when_new_state_omits_them(self) -> None:
        from datetime import datetime, timezone
        from decimal import Decimal

        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    positions={
                        "ETHUSDT": Position(
                            symbol="ETHUSDT",
                            stop_price=Decimal("106"),
                            legs=(
                                PositionLeg(
                                    "ETHUSDT",
                                    Decimal("2"),
                                    Decimal("108"),
                                    Decimal("106"),
                                    datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc),
                                    "stream_fill",
                                ),
                            ),
                        )
                    },
                )
            )
            store.merge_save(StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="SOLUSDT"))
            loaded = store.load()
            self.assertEqual(loaded.previous_leader_symbol, "SOLUSDT")
            self.assertIn("ETHUSDT", loaded.positions)

    def test_merge_save_preserves_processed_event_ids_when_new_state_omits_them(self) -> None:
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    processed_event_ids=["event-1"],
                )
            )
            store.merge_save(StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="SOLUSDT"))
            loaded = store.load()
            self.assertEqual(loaded.processed_event_ids, ["event-1"])

    def test_save_and_load_order_statuses_round_trip(self) -> None:
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    order_statuses={
                        "101": {
                            "symbol": "BTCUSDT",
                            "status": "NEW",
                            "execution_type": "NEW",
                            "side": "SELL",
                            "original_order_type": "STOP_MARKET",
                        }
                    },
                )
            )
            loaded = store.load()
            self.assertEqual(loaded.order_statuses["101"]["status"], "NEW")
            self.assertEqual(loaded.order_statuses["101"]["symbol"], "BTCUSDT")

    def test_save_and_load_recent_stop_loss_exits_round_trip(self) -> None:
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    recent_stop_loss_exits={"ETHUSDT": "2026-04-15T01:05:00+00:00"},
                )
            )

            loaded = store.load()

            self.assertEqual(loaded.recent_stop_loss_exits["ETHUSDT"], "2026-04-15T01:05:00+00:00")

    def test_merge_save_preserves_order_statuses_when_new_state_omits_them(self) -> None:
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "state.json"
            store = FileStateStore(path=path)
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    order_statuses={"101": {"symbol": "BTCUSDT", "status": "NEW"}},
                )
            )
            store.merge_save(StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="SOLUSDT"))
            loaded = store.load()
            self.assertEqual(loaded.order_statuses["101"]["status"], "NEW")
