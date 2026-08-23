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


class SkippedBaseReplayTests(unittest.TestCase):
    @staticmethod
    def _seed(*, signal_at: datetime, shadow_id: str = "shadow-1"):
        from momentum_alpha.skipped_base_replay_data import ReplaySeed

        return ReplaySeed(
            shadow_opportunity_id=shadow_id,
            symbol="AAAUSDT",
            signal_at=signal_at,
            base_signal_sequence=2,
            first_base_signal_at=signal_at - timedelta(hours=1),
            latest_price=Decimal("110"),
            stop_price=Decimal("100"),
            stop_budget_usdt=Decimal("10"),
            step_size=Decimal("0.1"),
            min_qty=Decimal("0.1"),
            tick_size=Decimal("0.1"),
        )

    @staticmethod
    def _candle(
        open_time: datetime,
        *,
        open_price: str = "110",
        high: str = "111",
        low: str = "109",
        close: str = "110",
    ):
        from momentum_alpha.skipped_base_replay_data import ReplayCandle

        return ReplayCandle(
            open_time=open_time,
            close_time=open_time + timedelta(minutes=1) - timedelta(milliseconds=1),
            open_price=Decimal(open_price),
            high_price=Decimal(high),
            low_price=Decimal(low),
            close_price=Decimal(close),
        )

    def test_load_replay_inputs_can_select_only_base_veto_seeds(self) -> None:
        import json
        import sqlite3
        from tempfile import TemporaryDirectory

        from momentum_alpha.runtime_schema import bootstrap_runtime_db
        from momentum_alpha.skipped_base_replay_data import load_replay_inputs

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            with sqlite3.connect(db_path) as connection:
                for row_id, reason in ((1, "base_veto"), (2, "daily_repeat_base")):
                    connection.execute(
                        """
                        INSERT INTO signal_decisions(
                            id, timestamp, source, decision_type, symbol, intent_id,
                            previous_leader_symbol, next_leader_symbol, position_count,
                            order_status_count, broker_response_count, stop_replacement_count,
                            payload_json
                        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                        """,
                        (
                            row_id,
                            f"2026-06-12T01:05:0{row_id}+00:00",
                            "test",
                            "base_entry_skipped",
                            "AAAUSDT",
                            f"shadow-{row_id}",
                            None,
                            "AAAUSDT",
                            0,
                            0,
                            0,
                            0,
                            json.dumps(
                                {
                                    "blocked_reason": reason,
                                    "latest_price": "110",
                                    "stop_price": "100",
                                    "stop_budget_usdt": "10",
                                    "step_size": "0.1",
                                    "min_qty": "0.1",
                                    "tick_size": "0.1",
                                }
                            ),
                        ),
                    )
                connection.commit()

            seeds, _, _, _ = load_replay_inputs(
                runtime_db_path=db_path,
                blocked_reasons={"base_veto"},
            )

        self.assertEqual([seed.shadow_opportunity_id for seed in seeds], ["shadow-1"])

    def test_sizes_base_and_closes_all_risk_at_stop(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_seed

        signal_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        fee = Decimal("0.0005")
        result = replay_shadow_seed(
            seed=self._seed(signal_at=signal_at),
            candles=[
                self._candle(signal_at, low="99", close="100"),
            ],
            leaders={},
            cutoff=signal_at + timedelta(minutes=1),
            taker_fee_rate=fee,
        )

        self.assertEqual(result.status, "closed")
        self.assertEqual(result.base_quantity, Decimal("1.0"))
        self.assertEqual(result.exit_price, Decimal("100"))
        self.assertEqual(result.add_on_count, 0)
        self.assertEqual(
            result.net_pnl,
            Decimal("-10") - Decimal("110") * fee - Decimal("100") * fee,
        )

    def test_hour_boundary_updates_stop_then_adds_when_symbol_is_top1(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_seed

        hour_start = datetime(2026, 6, 12, 1, 0, tzinfo=timezone.utc)
        signal_at = hour_start + timedelta(minutes=30)
        candles = [
            self._candle(
                hour_start + timedelta(minutes=minute),
                low="95" if minute == 20 else "109",
                close="110",
            )
            for minute in range(60)
        ]
        candles.append(
            self._candle(
                datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc),
                low="94",
                close="95",
            )
        )

        result = replay_shadow_seed(
            seed=self._seed(signal_at=signal_at),
            candles=candles,
            leaders={datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc): "AAAUSDT"},
            cutoff=datetime(2026, 6, 12, 2, 1, tzinfo=timezone.utc),
            taker_fee_rate=Decimal("0"),
        )

        self.assertEqual(result.status, "closed")
        self.assertEqual(result.exit_price, Decimal("100"))
        self.assertEqual(result.add_on_count, 1)
        self.assertEqual(result.legs[1].entry_price, Decimal("110"))
        self.assertEqual(result.legs[1].stop_at_entry, Decimal("100"))
        self.assertEqual(result.legs[1].quantity, Decimal("1.0"))
        event_types = [event.event_type for event in result.events]
        self.assertLess(event_types.index("stop_update"), event_types.index("add_on"))

    def test_hour_boundary_skips_first_add_on_when_base_age_is_under_thirty_minutes(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_seed

        hour_start = datetime(2026, 6, 12, 1, 0, tzinfo=timezone.utc)
        signal_at = hour_start + timedelta(minutes=31)
        candles = [
            self._candle(
                hour_start + timedelta(minutes=minute),
                low="95" if minute == 20 else "109",
                close="110",
            )
            for minute in range(60)
        ]

        result = replay_shadow_seed(
            seed=self._seed(signal_at=signal_at),
            candles=candles,
            leaders={datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc): "AAAUSDT"},
            cutoff=datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc),
            taker_fee_rate=Decimal("0"),
        )

        self.assertEqual(result.add_on_count, 0)
        self.assertEqual(result.skipped_add_on_count, 1)
        self.assertIn("first_add_on_before_30m", [event.reason for event in result.events])

    def test_missing_leader_skips_add_on_and_open_result_has_mtm(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_seed

        hour_start = datetime(2026, 6, 12, 1, 0, tzinfo=timezone.utc)
        signal_at = hour_start + timedelta(minutes=30)
        candles = [
            self._candle(
                hour_start + timedelta(minutes=minute),
                low="95" if minute == 20 else "109",
                close="112" if minute == 59 else "110",
            )
            for minute in range(60)
        ]

        result = replay_shadow_seed(
            seed=self._seed(signal_at=signal_at),
            candles=candles,
            leaders={},
            cutoff=datetime(2026, 6, 12, 2, 0, tzinfo=timezone.utc),
            taker_fee_rate=Decimal("0.0005"),
        )

        self.assertEqual(result.status, "open")
        self.assertEqual(result.add_on_count, 0)
        self.assertEqual(result.skipped_add_on_count, 1)
        self.assertIsNone(result.net_pnl)
        self.assertEqual(result.mark_price_at_cutoff, Decimal("112"))
        self.assertIsNotNone(result.mark_to_market_net_pnl)
        self.assertIn("missing_leader_data", [event.reason for event in result.events])

    def test_replay_report_suppresses_overlapping_same_symbol_seeds(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_opportunities

        first_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        second_at = first_at + timedelta(minutes=1)
        third_at = first_at + timedelta(minutes=10)
        seeds = [
            self._seed(signal_at=first_at, shadow_id="shadow-1"),
            self._seed(signal_at=second_at, shadow_id="shadow-2"),
            self._seed(signal_at=third_at, shadow_id="shadow-3"),
        ]
        candles = [
            self._candle(first_at, low="109"),
            self._candle(first_at + timedelta(minutes=2), low="99"),
            self._candle(third_at, low="99"),
        ]

        report = replay_shadow_opportunities(
            seeds=seeds,
            candles_by_symbol={"AAAUSDT": candles},
            leaders={},
            cutoff=third_at + timedelta(minutes=1),
            taker_fee_rate=Decimal("0"),
            independent_candidate_replay=False,
        )

        self.assertEqual(
            [item.shadow_opportunity_id for item in report.opportunities],
            ["shadow-1", "shadow-3"],
        )
        self.assertEqual(len(report.overlaps), 1)
        self.assertEqual(report.overlaps[0].shadow_opportunity_id, "shadow-2")
        self.assertEqual(report.overlaps[0].active_shadow_opportunity_id, "shadow-1")

    def test_independent_candidate_replay_completes_overlapping_same_symbol_seeds(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_shadow_opportunities

        first_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        second_at = first_at + timedelta(minutes=1)
        third_at = first_at + timedelta(minutes=10)
        seeds = [
            self._seed(signal_at=first_at, shadow_id="shadow-1"),
            self._seed(signal_at=second_at, shadow_id="shadow-2"),
            self._seed(signal_at=third_at, shadow_id="shadow-3"),
        ]
        candles = [
            self._candle(first_at, low="109"),
            self._candle(first_at + timedelta(minutes=2), low="99"),
            self._candle(third_at, low="99"),
        ]

        report = replay_shadow_opportunities(
            seeds=seeds,
            candles_by_symbol={"AAAUSDT": candles},
            leaders={},
            cutoff=third_at + timedelta(minutes=1),
            taker_fee_rate=Decimal("0"),
        )

        self.assertEqual(
            [item.shadow_opportunity_id for item in report.opportunities],
            ["shadow-1", "shadow-2", "shadow-3"],
        )
        self.assertEqual(report.overlaps, ())

    def test_invalid_seed_becomes_unresolved(self) -> None:
        from dataclasses import replace

        from momentum_alpha.skipped_base_replay import replay_shadow_seed

        signal_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        seed = replace(self._seed(signal_at=signal_at), latest_price=None)
        result = replay_shadow_seed(
            seed=seed,
            candles=[],
            leaders={},
            cutoff=signal_at,
            taker_fee_rate=Decimal("0.0005"),
        )

        self.assertEqual(result.status, "unresolved")
        self.assertTrue(result.warnings)

    def test_unresolved_seed_does_not_block_later_seed_for_same_symbol(self) -> None:
        from dataclasses import replace

        from momentum_alpha.skipped_base_replay import replay_shadow_opportunities

        first_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        first_seed = replace(
            self._seed(signal_at=first_at),
            latest_price=None,
            shadow_opportunity_id="unresolved",
        )
        second_at = first_at + timedelta(minutes=1)
        second_seed = self._seed(signal_at=second_at, shadow_id="resolved")

        report = replay_shadow_opportunities(
            seeds=[first_seed, second_seed],
            candles_by_symbol={"AAAUSDT": [self._candle(second_at, low="99")]},
            leaders={},
            cutoff=second_at + timedelta(minutes=1),
            taker_fee_rate=Decimal("0"),
        )

        self.assertEqual(
            [item.shadow_opportunity_id for item in report.opportunities],
            ["unresolved", "resolved"],
        )
        self.assertEqual(report.overlaps, ())

    def test_orchestrator_loads_klines_and_writes_artifacts(self) -> None:
        from momentum_alpha.skipped_base_replay import replay_skipped_bases

        signal_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)
        cutoff = signal_at + timedelta(minutes=1)
        seed = self._seed(signal_at=signal_at)
        calls = []

        def fake_load_inputs(**kwargs):
            calls.append(("load", kwargs))
            return [seed], {}, ["input_warning"], cutoff

        class FakeCache:
            def load_range(self, **kwargs):
                calls.append(("klines", kwargs))
                return [self_test._candle(signal_at, low="99", close="100")]

        def fake_cache_factory(**kwargs):
            calls.append(("cache", kwargs))
            return FakeCache()

        self_test = self
        from tempfile import TemporaryDirectory

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            runtime_db_path.touch()
            output_dir = Path(tmpdir) / "out"
            report = replay_skipped_bases(
                runtime_db_path=runtime_db_path,
                output_dir=output_dir,
                start_time=signal_at,
                end_time=cutoff,
                symbols=["AAAUSDT"],
                proxy="http://127.0.0.1:7897",
                taker_fee_rate=Decimal("0.0005"),
                refresh_klines=False,
                load_inputs_fn=fake_load_inputs,
                kline_cache_factory=fake_cache_factory,
            )

            self.assertTrue((output_dir / "summary.md").exists())

        self.assertEqual(report.seed_count, 1)
        self.assertFalse(report.had_fetch_errors)
        self.assertIn("input_warning", report.warnings)
        kline_call = next(item for item in calls if item[0] == "klines")
        self.assertEqual(
            kline_call[1]["start_time"],
            datetime(2026, 6, 12, 0, 0, tzinfo=timezone.utc),
        )
        self.assertEqual(kline_call[1]["end_time"], cutoff)


if __name__ == "__main__":
    unittest.main()
