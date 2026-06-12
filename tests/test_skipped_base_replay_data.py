from __future__ import annotations

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


class SkippedBaseReplayDataTests(unittest.TestCase):
    def test_loads_filtered_seeds_and_last_leader_per_minute(self) -> None:
        from momentum_alpha.runtime_store import insert_signal_decision
        from momentum_alpha.skipped_base_replay_data import load_replay_inputs

        start = datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc)
        end = datetime(2026, 6, 12, 4, 0, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry_skipped",
                symbol="AAAUSDT",
                next_leader_symbol="AAAUSDT",
                intent_id="shadow_aaa",
                payload={
                    "shadow_opportunity_id": "shadow_aaa",
                    "base_signal_sequence": 2,
                    "first_base_signal_at": "2026-06-12T01:00:00+00:00",
                    "latest_price": "110",
                    "stop_price": "100",
                    "stop_budget_usdt": "10",
                    "step_size": "0.1",
                    "min_qty": "0.1",
                    "tick_size": "0.1",
                },
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 6, 12, 2, 6, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry_skipped",
                symbol="BBBUSDT",
                next_leader_symbol="BBBUSDT",
                payload={},
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 6, 12, 3, 0, 5, tzinfo=timezone.utc),
                source="poll",
                decision_type="no_action",
                next_leader_symbol="BBBUSDT",
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 6, 12, 3, 0, 50, tzinfo=timezone.utc),
                source="poll",
                decision_type="add_on",
                next_leader_symbol="AAAUSDT",
            )

            seeds, leaders, warnings, cutoff = load_replay_inputs(
                runtime_db_path=db_path,
                start_time=start,
                end_time=end,
                symbols={"AAAUSDT"},
            )

        self.assertEqual([seed.symbol for seed in seeds], ["AAAUSDT"])
        self.assertEqual(seeds[0].base_signal_sequence, 2)
        self.assertEqual(seeds[0].latest_price, Decimal("110"))
        self.assertEqual(
            leaders[datetime(2026, 6, 12, 3, 0, tzinfo=timezone.utc)],
            "AAAUSDT",
        )
        self.assertTrue(any("conflicting_leader" in item for item in warnings))
        self.assertEqual(cutoff, datetime(2026, 6, 12, 3, 0, 50, tzinfo=timezone.utc))

    def test_malformed_seed_is_retained_with_warnings(self) -> None:
        from momentum_alpha.runtime_store import insert_signal_decision
        from momentum_alpha.skipped_base_replay_data import load_replay_inputs

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            signal_at = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
            insert_signal_decision(
                path=db_path,
                timestamp=signal_at,
                source="poll",
                decision_type="base_entry_skipped",
                symbol="AAAUSDT",
                next_leader_symbol="AAAUSDT",
                payload={
                    "base_signal_sequence": "bad",
                    "latest_price": "bad",
                },
            )

            seeds, _, warnings, _ = load_replay_inputs(runtime_db_path=db_path)

        self.assertEqual(len(seeds), 1)
        self.assertEqual(seeds[0].signal_at, signal_at)
        self.assertIsNone(seeds[0].latest_price)
        self.assertTrue(seeds[0].warnings)
        self.assertTrue(warnings)

    def test_binance_cache_uses_proxy_and_reuses_symbol_day(self) -> None:
        from momentum_alpha.skipped_base_replay_data import BinanceKlineCache

        calls = []

        def fake_request_json(**kwargs):
            calls.append(kwargs)
            return [
                [
                    1781222400000,
                    "10",
                    "11",
                    "9",
                    "10.5",
                    "100",
                    1781222459999,
                ]
            ]

        with TemporaryDirectory() as tmpdir:
            cache = BinanceKlineCache(
                cache_path=Path(tmpdir) / "klines.json",
                proxy="http://127.0.0.1:7897",
                request_json=fake_request_json,
            )
            start = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)
            end = datetime(2026, 6, 12, 0, 1, tzinfo=timezone.utc)
            first = cache.load_range(symbol="AAAUSDT", start_time=start, end_time=end)
            second = cache.load_range(symbol="AAAUSDT", start_time=start, end_time=end)

        self.assertEqual(first[0].close_price, Decimal("10.5"))
        self.assertEqual(first, second)
        self.assertEqual(len(calls), 1)
        self.assertEqual(calls[0]["proxy"], "http://127.0.0.1:7897")

    def test_refresh_refetches_and_excludes_incomplete_candles(self) -> None:
        from momentum_alpha.skipped_base_replay_data import BinanceKlineCache

        calls = []

        def fake_request_json(**kwargs):
            calls.append(kwargs)
            return [
                [1781222400000, "10", "11", "9", "10.5", "1", 1781222459999],
                [1781222460000, "10.5", "12", "10", "11", "1", 1781222519999],
            ]

        with TemporaryDirectory() as tmpdir:
            cache = BinanceKlineCache(
                cache_path=Path(tmpdir) / "klines.json",
                request_json=fake_request_json,
            )
            start = datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc)
            end = datetime(2026, 6, 12, 0, 1, tzinfo=timezone.utc)
            candles = cache.load_range(
                symbol="AAAUSDT",
                start_time=start,
                end_time=end,
                refresh=True,
            )
            cache.load_range(
                symbol="AAAUSDT",
                start_time=start,
                end_time=end,
                refresh=True,
            )

        self.assertEqual(len(candles), 1)
        self.assertEqual(len(calls), 2)

    def test_failed_day_keeps_successful_cached_days(self) -> None:
        from momentum_alpha.skipped_base_replay_data import BinanceKlineCache, KlineFetchError

        calls = 0

        def fake_request_json(**kwargs):
            nonlocal calls
            calls += 1
            if calls == 1:
                return [
                    [1781222400000, "10", "11", "9", "10.5", "1", 1781222459999],
                ]
            raise RuntimeError("network down")

        with TemporaryDirectory() as tmpdir:
            cache_path = Path(tmpdir) / "klines.json"
            cache = BinanceKlineCache(
                cache_path=cache_path,
                request_json=fake_request_json,
                max_attempts=1,
            )
            with self.assertRaises(KlineFetchError):
                cache.load_range(
                    symbol="AAAUSDT",
                    start_time=datetime(2026, 6, 12, tzinfo=timezone.utc),
                    end_time=datetime(2026, 6, 13, 0, 1, tzinfo=timezone.utc),
                )

            persisted = cache_path.read_text(encoding="utf-8")

        self.assertIn("AAAUSDT:2026-06-12", persisted)


if __name__ == "__main__":
    unittest.main()
