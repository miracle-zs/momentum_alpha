import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class StrategyTests(unittest.TestCase):
    @staticmethod
    def _leader_change_market():
        from momentum_alpha.models import MarketSnapshot

        return {
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

    def test_opens_base_entry_when_leader_changes_and_symbol_not_held(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 2, 5, tzinfo=timezone.utc)
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

        now = datetime(2026, 4, 14, 2, 5, tzinfo=timezone.utc)
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

    def test_entry_window_open_does_not_replay_leader_seen_during_blocked_window(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        blocked_time = datetime(2026, 4, 14, 0, 59, tzinfo=timezone.utc)
        entry_time = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(current_day=blocked_time.date(), previous_leader_symbol="BTCUSDT", positions={})
        market = self._leader_change_market()

        blocked = evaluate_minute_close(now=blocked_time, state=state, market=market)
        state_after_blocked_window = StrategyState(
            current_day=entry_time.date(),
            previous_leader_symbol=blocked.new_previous_leader_symbol,
            positions={},
        )
        opened = evaluate_minute_close(now=entry_time, state=state_after_blocked_window, market=market)

        self.assertEqual(blocked.blocked_reason, "outside_entry_window")
        self.assertEqual(blocked.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(opened.base_entries, [])
        self.assertEqual(opened.new_previous_leader_symbol, "ETHUSDT")

    def test_beijing_nine_blocks_base_and_records_shadow_without_consuming_daily_opportunity(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 7, 14, 1, 59, 59, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT")

        result = evaluate_minute_close(now=now, state=state, market=self._leader_change_market())

        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.blocked_reason, "beijing_09_base_block")
        self.assertEqual(result.new_previous_leader_symbol, "ETHUSDT")
        self.assertEqual(result.new_daily_base_signal_times, {})
        self.assertEqual(result.new_daily_base_signal_counts, {})
        self.assertEqual(len(result.skipped_base_entries), 1)
        skipped = result.skipped_base_entries[0]
        self.assertEqual(skipped.reason, "beijing_09_base_block")
        self.assertEqual(skipped.base_signal_sequence, 1)
        self.assertEqual(skipped.first_base_signal_at, now)
        self.assertEqual(skipped.shadow_opportunity_id, "shadow_260714015959_ETHUSDT_01")

    def test_beijing_ten_allows_new_leader_base(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT")

        result = evaluate_minute_close(now=now, state=state, market=self._leader_change_market())

        self.assertEqual([item.symbol for item in result.base_entries], ["ETHUSDT"])
        self.assertEqual(result.skipped_base_entries, [])

    def test_beijing_ten_does_not_replay_unchanged_leader_seen_at_nine(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        blocked_at = datetime(2026, 7, 14, 1, 30, tzinfo=timezone.utc)
        opened_at = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        initial = StrategyState(current_day=blocked_at.date(), previous_leader_symbol="BTCUSDT")
        blocked = evaluate_minute_close(now=blocked_at, state=initial, market=self._leader_change_market())
        after_block = StrategyState(
            current_day=opened_at.date(),
            previous_leader_symbol=blocked.new_previous_leader_symbol,
        )

        result = evaluate_minute_close(now=opened_at, state=after_block, market=self._leader_change_market())

        self.assertEqual(result.base_entries, [])
        self.assertIsNone(result.blocked_reason)

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

    def test_blocks_base_entry_during_stop_loss_cooldown(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 1, 5, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
            positions={},
            recent_stop_loss_exits={"ETHUSDT": datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)},
        )
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
        self.assertEqual(result.blocked_reason, "stop_loss_cooldown")

    def test_allows_base_entry_after_stop_loss_cooldown_expires(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 4, 14, 2, 5, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
            positions={},
            recent_stop_loss_exits={"ETHUSDT": datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)},
        )
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
        self.assertIsNone(result.blocked_reason)

    def test_hour_close_adds_only_current_leader_and_records_skipped_symbols(self) -> None:
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

        result = evaluate_hour_close(
            now=now,
            state=state,
            latest_hour_lows=latest_hour_lows,
            current_leader_symbol="ETHUSDT",
        )
        self.assertEqual([intent.symbol for intent in result.add_on_entries], ["ETHUSDT"])
        self.assertEqual([skipped.symbol for skipped in result.skipped_add_ons], ["BTCUSDT"])
        self.assertEqual(result.skipped_add_ons[0].reason, "not_current_leader")
        self.assertEqual(result.skipped_add_ons[0].stop_price, Decimal("105"))
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

        result = process_clock_tick(now=now, state=state, market=market, last_add_on_hour=0)
        self.assertEqual(result.base_entries[0].symbol, "SOLUSDT")
        self.assertEqual(result.add_on_entries, [])
        self.assertEqual(result.skipped_add_ons[0].symbol, "BTCUSDT")

    def test_add_on_runs_after_missed_midnight_hour(self) -> None:
        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import process_clock_tick

        now = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        leg_time = datetime(2026, 4, 14, 23, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("100"),
                    legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("110"), Decimal("100"), leg_time, "base"),),
                )
            },
        )
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("125"),
                previous_hour_low=Decimal("115"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = process_clock_tick(now=now, state=state, market=market, last_add_on_hour=23)

        self.assertEqual([intent.symbol for intent in result.add_on_entries], ["ETHUSDT"])
        self.assertEqual(result.updated_stop_prices["ETHUSDT"], Decimal("115"))

    def test_add_on_skips_when_stop_price_would_immediately_trigger(self) -> None:
        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import process_clock_tick

        now = datetime(2026, 4, 14, 2, 0, tzinfo=timezone.utc)
        leg_time = datetime(2026, 4, 14, 1, 0, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="ETHUSDT",
            positions={
                "ETHUSDT": Position(
                    symbol="ETHUSDT",
                    stop_price=Decimal("100"),
                    legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("110"), Decimal("100"), leg_time, "base"),),
                )
            },
        )
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("105"),
                previous_hour_low=Decimal("106"),
                tradable=True,
                has_previous_hour_candle=True,
            ),
        }

        result = process_clock_tick(now=now, state=state, market=market, last_add_on_hour=1)

        self.assertEqual(result.add_on_entries, [])
        self.assertEqual(result.updated_stop_prices, {})
        self.assertEqual(result.skipped_add_ons[0].reason, "invalid_stop_price")

    def test_first_add_on_before_thirty_minutes_is_skipped_but_stop_still_moves(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import evaluate_hour_close

        now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        base_opened_at = now - timedelta(minutes=29, seconds=59)
        position = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("100"),
            legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("110"), Decimal("100"), base_opened_at, "base"),),
        )
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="ETHUSDT",
            positions={"ETHUSDT": position},
        )

        result = evaluate_hour_close(
            now=now,
            state=state,
            latest_hour_lows={"ETHUSDT": Decimal("105")},
            latest_prices={"ETHUSDT": Decimal("120")},
            current_leader_symbol="ETHUSDT",
        )

        self.assertEqual(result.add_on_entries, [])
        self.assertEqual(result.updated_stop_prices, {"ETHUSDT": Decimal("105")})
        self.assertEqual(len(result.skipped_add_ons), 1)
        skipped = result.skipped_add_ons[0]
        self.assertEqual(skipped.reason, "first_add_on_before_30m")
        self.assertEqual(skipped.base_opened_at, base_opened_at)
        self.assertEqual(skipped.base_age_minutes, Decimal("29.98333333333333333333333333"))

    def test_first_add_on_at_thirty_minutes_is_allowed(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, StrategyState
        from momentum_alpha.strategy import evaluate_hour_close

        now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        base_opened_at = now - timedelta(minutes=30)
        position = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("100"),
            legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("110"), Decimal("100"), base_opened_at, "base"),),
        )
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="ETHUSDT",
            positions={"ETHUSDT": position},
        )

        result = evaluate_hour_close(
            now=now,
            state=state,
            latest_hour_lows={"ETHUSDT": Decimal("105")},
            latest_prices={"ETHUSDT": Decimal("120")},
            current_leader_symbol="ETHUSDT",
        )

        self.assertEqual([item.symbol for item in result.add_on_entries], ["ETHUSDT"])
        self.assertEqual(result.skipped_add_ons, [])

    def test_first_valid_base_signal_consumes_daily_opportunity(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
        )

        result = evaluate_minute_close(
            now=now,
            state=state,
            market=self._leader_change_market(),
        )

        self.assertEqual([item.symbol for item in result.base_entries], ["ETHUSDT"])
        self.assertEqual(result.skipped_base_entries, [])
        self.assertEqual(result.new_daily_base_signal_times, {"ETHUSDT": now})
        self.assertEqual(result.new_daily_base_signal_counts, {"ETHUSDT": 1})

    def test_second_valid_base_signal_is_filtered(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        first_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
            daily_base_signal_times={"ETHUSDT": first_at},
            daily_base_signal_counts={"ETHUSDT": 1},
        )

        result = evaluate_minute_close(
            now=now,
            state=state,
            market=self._leader_change_market(),
        )

        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.blocked_reason, "daily_repeat_base")
        self.assertEqual(len(result.skipped_base_entries), 1)
        skipped = result.skipped_base_entries[0]
        self.assertEqual(skipped.symbol, "ETHUSDT")
        self.assertEqual(skipped.base_signal_sequence, 2)
        self.assertEqual(skipped.first_base_signal_at, first_at)
        self.assertEqual(
            skipped.shadow_opportunity_id,
            "shadow_260612020500_ETHUSDT_02",
        )
        self.assertEqual(
            result.new_daily_base_signal_times,
            {"ETHUSDT": first_at},
        )
        self.assertEqual(result.new_daily_base_signal_counts, {"ETHUSDT": 2})

    def test_invalid_base_signal_does_not_consume_daily_opportunity(self) -> None:
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
        market = self._leader_change_market()
        market["ETHUSDT"] = MarketSnapshot(
            symbol="ETHUSDT",
            daily_open_price=Decimal("80"),
            latest_price=Decimal("108"),
            previous_hour_low=Decimal("110"),
            current_hour_low=Decimal("109"),
            tradable=True,
            has_previous_hour_candle=True,
        )
        state = StrategyState(
            current_day=now.date(),
            previous_leader_symbol="BTCUSDT",
        )

        result = evaluate_minute_close(now=now, state=state, market=market)

        self.assertEqual(result.blocked_reason, "invalid_stop_price")
        self.assertEqual(result.new_daily_base_signal_times, {})
        self.assertEqual(result.new_daily_base_signal_counts, {})
