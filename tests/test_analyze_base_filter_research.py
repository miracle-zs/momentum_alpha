from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from analyze_base_filter_research import (  # noqa: E402
    Condition,
    completed_candles_before,
    compute_features,
    evaluate_condition,
    expand_veto_condition,
    passes_tail_constraints,
    summarize_candidate,
)


def kline(
    minute: int,
    *,
    open_price: float,
    high: float,
    low: float,
    close: float,
    quote_volume: float,
    trades: int,
    taker_buy_quote: float,
) -> list:
    open_time = minute * 60_000
    return [
        open_time,
        str(open_price),
        str(high),
        str(low),
        str(close),
        "0",
        open_time + 59_999,
        str(quote_volume),
        trades,
        "0",
        str(taker_buy_quote),
        "0",
    ]


class CompletedCandleTests(unittest.TestCase):
    def test_excludes_candle_containing_signal_timestamp(self) -> None:
        candles = [
            kline(
                100,
                open_price=100,
                high=102,
                low=99,
                close=101,
                quote_volume=1000,
                trades=10,
                taker_buy_quote=600,
            ),
            kline(
                101,
                open_price=101,
                high=104,
                low=100,
                close=103,
                quote_volume=2000,
                trades=20,
                taker_buy_quote=1200,
            ),
        ]
        signal_time = datetime.fromtimestamp(
            (101 * 60 + 30),
            tz=timezone.utc,
        )

        completed = completed_candles_before(candles, signal_time)

        self.assertEqual([row["open_minute"] for row in completed], [100])


class FeatureTests(unittest.TestCase):
    def test_computes_path_breakout_participation_and_volatility_features(self) -> None:
        closes = [100, 101, 100, 102, 103, 104]
        candles = []
        for index, close in enumerate(closes):
            candles.append(
                kline(
                    100 + index,
                    open_price=close - 0.5,
                    high=close + 1,
                    low=close - 1,
                    close=close,
                    quote_volume=100 * (index + 1),
                    trades=10 * (index + 1),
                    taker_buy_quote=60 * (index + 1),
                )
            )
        completed = completed_candles_before(
            candles,
            datetime.fromtimestamp(106 * 60, tz=timezone.utc),
        )

        features = compute_features(
            completed,
            {
                "signal_price": 104,
                "signal_stop": 100,
            },
            windows=(3, 5),
        )

        self.assertAlmostEqual(features["return_5m_pct"], 4.0)
        self.assertAlmostEqual(features["efficiency_5m"], 4 / 6)
        self.assertAlmostEqual(features["positive_share_5m"], 0.8)
        self.assertAlmostEqual(features["distance_day_high_pct"], 1 / 105 * 100)
        self.assertAlmostEqual(features["pullback_5m_pct"], 1 / 105 * 100)
        self.assertAlmostEqual(features["close_location"], 0.5)
        self.assertAlmostEqual(features["upper_wick_fraction"], 0.5)
        self.assertAlmostEqual(features["quote_volume_ratio_3m"], 500 / 200)
        self.assertAlmostEqual(features["trade_count_ratio_3m"], 50 / 20)
        self.assertAlmostEqual(features["taker_buy_share_3m"], 0.6)
        self.assertAlmostEqual(features["stop_distance_pct"], 4 / 104 * 100)
        self.assertGreater(features["realized_volatility_5m_pct"], 0)
        self.assertAlmostEqual(features["atr_5m_pct"], 2.2 / 104 * 100)

    def test_returns_blank_for_features_without_enough_history(self) -> None:
        candles = [
            kline(
                100,
                open_price=100,
                high=101,
                low=99,
                close=100,
                quote_volume=100,
                trades=10,
                taker_buy_quote=50,
            )
        ]
        completed = completed_candles_before(
            candles,
            datetime.fromtimestamp(101 * 60, tz=timezone.utc),
        )

        features = compute_features(
            completed,
            {"signal_price": 100, "signal_stop": 99},
            windows=(5,),
        )

        self.assertEqual(features["return_5m_pct"], "")
        self.assertEqual(features["efficiency_5m"], "")
        self.assertEqual(features["quote_volume_ratio_5m"], "")

    def test_day_high_ignores_previous_day_warmup_candles(self) -> None:
        candles = [
            {
                "open_minute": 99,
                "open": 190.0,
                "high": 200.0,
                "low": 180.0,
                "close": 190.0,
                "quote_volume": 100.0,
                "trades": 10,
                "taker_buy_quote": 50.0,
            },
            {
                "open_minute": 100,
                "open": 99.0,
                "high": 105.0,
                "low": 98.0,
                "close": 104.0,
                "quote_volume": 100.0,
                "trades": 10,
                "taker_buy_quote": 50.0,
            },
        ]

        features = compute_features(
            candles,
            {"signal_price": 104, "signal_stop": 100},
            windows=(1,),
            day_start_minute=100,
        )

        self.assertAlmostEqual(features["distance_day_high_pct"], 1 / 105 * 100)


class CandidateTests(unittest.TestCase):
    def setUp(self) -> None:
        self.rows = [
            {
                "round_trip_id": "loss",
                "opened_at_utc": "2026-05-30T01:00:00+00:00",
                "net_pnl": -20.0,
                "add_on_count": 1,
                "add_on_pnl": -5.0,
                "efficiency_15m": 0.1,
                "distance_day_high_pct": 3.0,
                "taker_buy_share_15m": 0.4,
            },
            {
                "round_trip_id": "tail50",
                "opened_at_utc": "2026-05-20T01:00:00+00:00",
                "net_pnl": 60.0,
                "add_on_count": 2,
                "add_on_pnl": 40.0,
                "efficiency_15m": 0.2,
                "distance_day_high_pct": 0.5,
                "taker_buy_share_15m": 0.45,
            },
            {
                "round_trip_id": "tail100",
                "opened_at_utc": "2026-06-02T01:00:00+00:00",
                "net_pnl": 120.0,
                "add_on_count": 4,
                "add_on_pnl": 100.0,
                "efficiency_15m": 0.5,
                "distance_day_high_pct": 0.2,
                "taker_buy_share_15m": 0.6,
            },
        ]
        self.conditions = (
            Condition("path", "efficiency_15m", "<=", 0.15),
            Condition("acceptance", "distance_day_high_pct", ">=", 2.0),
        )

    def test_evaluate_condition_supports_both_directions_and_missing_values(self) -> None:
        row = {"low": 1.0, "high": 3.0, "missing": ""}

        self.assertTrue(
            evaluate_condition(row, Condition("path", "low", "<=", 1.0))
        )
        self.assertTrue(
            evaluate_condition(row, Condition("path", "high", ">=", 3.0))
        )
        self.assertFalse(
            evaluate_condition(row, Condition("path", "missing", "<=", 2.0))
        )

    def test_candidate_filters_only_when_all_conditions_match(self) -> None:
        summary = summarize_candidate(
            self.rows,
            self.conditions,
            unmatched=[{"net_pnl": -7.0, "opened_at_utc": "2026-06-01"}],
        )

        self.assertEqual(summary["filtered_count"], 1)
        self.assertEqual(summary["filtered_ids"], ["loss"])
        self.assertEqual(summary["baseline_total_pnl"], 153.0)
        self.assertEqual(summary["estimated_total_pnl"], 173.0)
        self.assertEqual(summary["estimated_delta"], 20.0)
        self.assertEqual(summary["recent_delta"], 20.0)
        self.assertEqual(summary["filtered_add_on_count"], 1)
        self.assertEqual(summary["filtered_add_on_pnl"], -5.0)
        self.assertEqual(summary["tail_50_retention_pct"], 100.0)
        self.assertEqual(summary["tail_100_filtered_count"], 0)
        self.assertEqual(summary["weekly_deltas"], {"2026-W22": 20.0})

    def test_tail_constraints_reject_filtered_100_winner(self) -> None:
        conditions = (
            Condition("path", "efficiency_15m", "<=", 0.6),
            Condition("acceptance", "distance_day_high_pct", ">=", 0.1),
        )

        summary = summarize_candidate(self.rows, conditions)

        self.assertEqual(summary["tail_100_filtered_count"], 1)
        self.assertFalse(passes_tail_constraints(summary))

    def test_tail_constraints_require_98_percent_tail_retention_and_improvement(self) -> None:
        valid = {
            "tail_100_filtered_count": 0,
            "tail_50_retention_pct": 98.0,
            "estimated_delta": 1.0,
        }

        self.assertTrue(passes_tail_constraints(valid))
        self.assertFalse(
            passes_tail_constraints({**valid, "tail_50_retention_pct": 97.99})
        )
        self.assertFalse(
            passes_tail_constraints({**valid, "estimated_delta": 0.0})
        )

    def test_expands_veto_threshold_toward_filtering_more_trades(self) -> None:
        low = expand_veto_condition(
            Condition("participation", "ratio", "<=", 0.5),
            fraction=0.2,
        )
        high = expand_veto_condition(
            Condition("volatility", "distance", ">=", 3.0),
            fraction=0.2,
        )

        self.assertAlmostEqual(low.threshold, 0.6)
        self.assertAlmostEqual(high.threshold, 2.4)


if __name__ == "__main__":
    unittest.main()
