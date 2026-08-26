from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BaseVetoTests(unittest.TestCase):
    def test_kline_fetch_window_is_aligned_to_recent_completed_minutes(self) -> None:
        from momentum_alpha.market_data_klines import _fetch_base_veto_klines

        class Client:
            def __init__(self) -> None:
                self.kwargs = None

            def fetch_klines(self, **kwargs):
                self.kwargs = kwargs
                return []

        client = Client()
        signal_at = datetime.fromtimestamp(3_600.001, tz=timezone.utc)

        _fetch_base_veto_klines(client=client, symbol="ETHUSDT", now=signal_at, limit=90)

        self.assertEqual(client.kwargs["end_time_ms"], 3_600_000)
        self.assertEqual(client.kwargs["start_time_ms"], 3_600_000 - 90 * 60_000)

    def test_feature_calculation_excludes_open_future_candle(self) -> None:
        from momentum_alpha.base_veto import compute_base_veto_features

        klines = []
        for minute in range(61):
            open_time = minute * 60_000
            close = Decimal("100") + Decimal(minute) / Decimal("100")
            klines.append(
                [
                    open_time,
                    str(close),
                    str(close + Decimal("1")),
                    str(close - Decimal("1")),
                    str(close),
                    "1",
                    open_time + 59_999,
                    "1000",
                    100 if minute < 30 else 50,
                    "500",
                    "500",
                    "0",
                ]
            )

        features = compute_base_veto_features(
            klines=klines,
            signal_at=datetime.fromtimestamp(60 * 60, tz=timezone.utc),
        )

        self.assertEqual(features.completed_candle_count, 60)
        self.assertEqual(features.as_of, datetime.fromtimestamp(60 * 60, tz=timezone.utc))
        self.assertIsNotNone(features.atr_15m_pct)

    def test_a_or_b_evaluation_reports_each_trigger(self) -> None:
        from momentum_alpha.base_veto import BaseVetoFeatures, evaluate_base_veto

        a = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("3.1"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                completed_candle_count=60,
            )
        )
        b = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("2.9"),
                trade_count_ratio_30m=Decimal("0.8"),
                return_to_vol_15m=Decimal("0.4"),
                completed_candle_count=60,
            )
        )
        allow = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("2.9"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                completed_candle_count=60,
            )
        )

        self.assertTrue(a.triggered)
        self.assertEqual(a.rule, "A")
        self.assertTrue(b.triggered)
        self.assertEqual(b.rule, "B")
        self.assertFalse(allow.triggered)

    def test_combined_rules_report_each_extended_trigger(self) -> None:
        from momentum_alpha.base_veto import BaseVetoFeatures, evaluate_base_veto

        d = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("2"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                taker_buy_share_15m=Decimal("0.40"),
                efficiency_15m=Decimal("0.10"),
                range_expansion_15m=Decimal("1.1"),
                breakout_5m_pct=Decimal("0.1"),
                pullback_5m_pct=Decimal("3"),
                completed_candle_count=60,
            )
        )
        e_and_breakout = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("2"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                taker_buy_share_15m=Decimal("0.60"),
                efficiency_15m=Decimal("0.40"),
                range_expansion_15m=Decimal("1.5"),
                breakout_5m_pct=Decimal("0.50"),
                pullback_5m_pct=Decimal("1.25"),
                completed_candle_count=60,
            )
        )
        breakout_only = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("2"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                taker_buy_share_15m=Decimal("0.60"),
                efficiency_15m=Decimal("0.80"),
                range_expansion_15m=Decimal("1.1"),
                breakout_5m_pct=Decimal("0.50"),
                pullback_5m_pct=Decimal("1.25"),
                completed_candle_count=60,
            )
        )

        self.assertTrue(d.triggered)
        self.assertEqual(d.rule, "D")
        self.assertTrue(d.d_triggered)
        self.assertFalse(d.e_triggered)
        self.assertFalse(d.breakout_triggered)
        self.assertTrue(e_and_breakout.triggered)
        self.assertEqual(e_and_breakout.rule, "E")
        self.assertTrue(e_and_breakout.e_triggered)
        self.assertTrue(e_and_breakout.breakout_triggered)
        self.assertFalse(breakout_only.triggered)
        self.assertIsNone(breakout_only.rule)
        self.assertTrue(breakout_only.breakout_triggered)

    def test_strategy_allows_breakout_only_entry_and_marks_it_shadow_only(self) -> None:
        from momentum_alpha.base_veto import BaseVetoFeatures
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 8, 26, 3, 5, tzinfo=timezone.utc)
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("120"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
                base_veto_features=BaseVetoFeatures(
                    atr_15m_pct=Decimal("2"),
                    trade_count_ratio_30m=Decimal("1.2"),
                    return_to_vol_15m=Decimal("0.8"),
                    taker_buy_share_15m=Decimal("0.60"),
                    efficiency_15m=Decimal("0.80"),
                    range_expansion_15m=Decimal("1.1"),
                    breakout_5m_pct=Decimal("0.50"),
                    pullback_5m_pct=Decimal("1.25"),
                    completed_candle_count=60,
                ),
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

        result = evaluate_minute_close(
            now=now,
            state=StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT"),
            market=market,
        )

        self.assertEqual([entry.symbol for entry in result.base_entries], ["ETHUSDT"])
        self.assertTrue(result.base_entries[0].base_veto_breakout_triggered)
        self.assertEqual(result.skipped_base_entries, [])

    def test_feature_calculation_includes_extended_combined_rule_inputs(self) -> None:
        from momentum_alpha.base_veto import compute_base_veto_features

        klines = []
        for minute in range(60):
            open_time = minute * 60_000
            close = Decimal("100") + Decimal(minute) / Decimal("100")
            klines.append(
                [
                    open_time,
                    str(close),
                    str(close + Decimal("1")),
                    str(close - Decimal("1")),
                    str(close),
                    "1",
                    open_time + 59_999,
                    "1000",
                    100,
                    "500",
                    "400",
                    "0",
                ]
            )

        features = compute_base_veto_features(
            klines=klines,
            signal_at=datetime.fromtimestamp(60 * 60, tz=timezone.utc),
        )

        self.assertTrue(features.data_ready)
        self.assertEqual(features.taker_buy_share_15m, Decimal("0.4"))
        self.assertIsNotNone(features.efficiency_15m)
        self.assertIsNotNone(features.range_expansion_15m)
        self.assertIsNotNone(features.breakout_5m_pct)
        self.assertIsNotNone(features.pullback_5m_pct)

    def test_incomplete_features_fail_open(self) -> None:
        from momentum_alpha.base_veto import BaseVetoFeatures, evaluate_base_veto

        decision = evaluate_base_veto(
            BaseVetoFeatures(
                atr_15m_pct=Decimal("8"),
                trade_count_ratio_30m=Decimal("0.1"),
                return_to_vol_15m=Decimal("0.1"),
                completed_candle_count=59,
            )
        )

        self.assertFalse(decision.triggered)

    def test_strategy_veto_consumes_daily_opportunity_and_blocks_later_reentry(self) -> None:
        from momentum_alpha.base_veto import BaseVetoFeatures
        from momentum_alpha.models import MarketSnapshot, StrategyState
        from momentum_alpha.strategy import evaluate_minute_close

        now = datetime(2026, 8, 18, 3, 5, tzinfo=timezone.utc)
        market = {
            "ETHUSDT": MarketSnapshot(
                symbol="ETHUSDT",
                daily_open_price=Decimal("100"),
                latest_price=Decimal("120"),
                previous_hour_low=Decimal("110"),
                tradable=True,
                has_previous_hour_candle=True,
                base_veto_features=BaseVetoFeatures(
                    atr_15m_pct=Decimal("3.5"),
                    trade_count_ratio_30m=Decimal("1.2"),
                    return_to_vol_15m=Decimal("0.8"),
                    completed_candle_count=60,
                ),
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
        state = StrategyState(current_day=now.date(), previous_leader_symbol="BTCUSDT")

        result = evaluate_minute_close(now=now, state=state, market=market)

        self.assertEqual(result.base_entries, [])
        self.assertEqual(result.blocked_reason, "base_veto")
        self.assertEqual(result.new_daily_base_signal_times, {"ETHUSDT": now})
        self.assertEqual(result.new_daily_base_signal_counts, {"ETHUSDT": 1})
        self.assertEqual(len(result.skipped_base_entries), 1)
        self.assertEqual(result.skipped_base_entries[0].base_veto_rule, "A")

        recovered_market = dict(market)
        recovered_market["ETHUSDT"] = MarketSnapshot(
            symbol="ETHUSDT",
            daily_open_price=Decimal("100"),
            latest_price=Decimal("120"),
            previous_hour_low=Decimal("110"),
            tradable=True,
            has_previous_hour_candle=True,
            base_veto_features=BaseVetoFeatures(
                atr_15m_pct=Decimal("0.5"),
                trade_count_ratio_30m=Decimal("1.2"),
                return_to_vol_15m=Decimal("0.8"),
                completed_candle_count=60,
            ),
        )
        returned = evaluate_minute_close(
            now=now + timedelta(minutes=11),
            state=StrategyState(
                current_day=now.date(),
                previous_leader_symbol="BTCUSDT",
                daily_base_signal_times=result.new_daily_base_signal_times,
                daily_base_signal_counts=result.new_daily_base_signal_counts,
            ),
            market=recovered_market,
        )

        self.assertEqual(returned.base_entries, [])
        self.assertEqual(returned.blocked_reason, "daily_repeat_base")
        self.assertEqual(returned.skipped_base_entries[0].base_signal_sequence, 2)
        self.assertEqual(returned.skipped_base_entries[0].first_base_signal_at, now)
