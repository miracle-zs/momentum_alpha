import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StrategyTests(unittest.TestCase):
    def test_opens_base_entry_when_leader_changes_and_symbol_not_held(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("120"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("115"),
                previous_hour_low=Decimal("108"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual([intent.symbol for intent in result.base_entries], ["ETHUSDT"])
        self.assertEqual(result.base_entries[0].stop_price, Decimal("110"))
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")

    def test_base_entry_uses_current_hour_low_when_price_is_below_previous_hour_low(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("108"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
                current_hour_low=Decimal("106"),
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("105"),
                previous_hour_low=Decimal("103"),
                tradable=True,
                has_previous_hour_candle=True,
                current_hour_low=Decimal("102"),
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual([intent.symbol for intent in result.base_entries], ["ETHUSDT"])
        self.assertEqual(result.base_entries[0].stop_price, Decimal("106"))

    def test_skips_base_entry_before_utc_one(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 0, 59, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("120"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("115"),
                previous_hour_low=Decimal("108"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(result.blocked_reason, "outside_entry_window")

    def test_reports_blocked_reason_when_leader_already_held(self) -> None:
        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        leg_time = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("110"),
                    legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("120"), Decimal("110"), leg_time, "base"),),
                )
            },
        )
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("125"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("115"),
                previous_hour_low=Decimal("108"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(result.blocked_reason, "already_holding")

    def test_reports_blocked_reason_when_previous_hour_candle_missing(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("120"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=False,
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("115"),
                previous_hour_low=Decimal("108"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(result.blocked_reason, "missing_previous_hour_candle")

    def test_reports_blocked_reason_when_stop_price_is_not_below_latest_price(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("108"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
                current_hour_low=Decimal("109"),
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("105"),
                previous_hour_low=Decimal("103"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = evaluate_minute_close(now=now, state=state, market=market)
        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(result.blocked_reason, "invalid_stop_price")

    def test_hour_close_updates_stops_and_adds_one_leg_per_open_symbol(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import evaluate_hour_close

        now = datetime(2026, 4, 14, 2, 0, tzinfo=timezone.utc)
        leg_time = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="ETHUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("100"),
                    legs=(PositionLeg("BTCUSDT", Decimal("1"), Decimal("110"), Decimal("100"), leg_time, "base"),),
                ),
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("200"),
                    legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("210"), Decimal("200"), leg_time, "base"),),
                ),
            },
        )
        latest_hour_lows = {"BTCUSDT": Decimal("105"), "ETHUSDT": Decimal("205")}

        result = evaluate_hour_close(now=now, state=state, latest_hour_lows=latest_hour_lows)
        self.assertEqual([intent.symbol for intent in result.add_on_entries], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual(result.updated_stop_prices["BTCUSDT"], Decimal("105"))
        self.assertEqual(result.updated_stop_prices["ETHUSDT"], Decimal("205"))

    def test_hour_boundary_processes_base_entry_before_add_on(self) -> None:
        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import process_clock_tick

        now = datetime(2026, 4, 14, 2, 0, tzinfo=timezone.utc)
        leg_time = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("100"),
                    legs=(PositionLeg("BTCUSDT", Decimal("1"), Decimal("110"), Decimal("100"), leg_time, "base"),),
                )
            },
        )
        market = {
            "SOLUSDT": MarketSnapshot(
                symbol="SOLUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("125"),
                previous_hour_low=Decimal("115"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("110"),
                previous_hour_low=Decimal("105"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = process_clock_tick(now=now, state=state, market=market)
        self.assertEqual(result.base_entries[0].symbol, "SOLUSDT")
        self.assertEqual(result.add_on_entries[0].symbol, "BTCUSDT")
