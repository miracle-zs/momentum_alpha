from __future__ import annotations

import csv
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


def _utc(year: int, month: int, day: int, hour: int, minute: int = 0) -> datetime:
    return datetime(year, month, day, hour, minute, tzinfo=timezone.utc)


class LeaderOpportunityDiagnosticsTests(unittest.TestCase):
    def test_build_leader_opportunity_diagnostics_groups_contiguous_rank1_rows(self) -> None:
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics
        from momentum_alpha.runtime_writes_history_trades import insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            leader_candidates_db_path = Path(tmpdir) / "leader_candidates.db"
            insert_leader_candidate_snapshots_bulk(
                path=leader_candidates_db_path,
                rows=[
                    {
                        "timestamp": _utc(2026, 5, 1, 1, 0),
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "110",
                        "daily_change_pct": "0.10",
                        "previous_hour_low": "99",
                        "current_hour_low": "100",
                        "leader_gap_pct": "0.02",
                        "payload": {"symbol": "AAAUSDT"},
                    },
                    {
                        "timestamp": _utc(2026, 5, 1, 1, 5),
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "120",
                        "daily_change_pct": "0.20",
                        "previous_hour_low": "99",
                        "current_hour_low": "101",
                        "leader_gap_pct": "0.01",
                        "payload": {"symbol": "AAAUSDT"},
                    },
                    {
                        "timestamp": _utc(2026, 5, 1, 1, 10),
                        "source": "position-snapshot-replay",
                        "symbol": "BBBUSDT",
                        "rank": 1,
                        "daily_open_price": "200",
                        "latest_price": "210",
                        "daily_change_pct": "0.05",
                        "previous_hour_low": "198",
                        "current_hour_low": "199",
                        "leader_gap_pct": "0.03",
                        "payload": {"symbol": "BBBUSDT"},
                    },
                    {
                        "timestamp": _utc(2026, 5, 1, 1, 15),
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "125",
                        "daily_change_pct": "0.25",
                        "previous_hour_low": "99",
                        "current_hour_low": "102",
                        "leader_gap_pct": "0.02",
                        "payload": {"symbol": "AAAUSDT"},
                    },
                ],
            )
            insert_trade_round_trip(
                path=runtime_db_path,
                round_trip_id="rt-1",
                symbol="AAAUSDT",
                opened_at=_utc(2026, 5, 1, 1, 2),
                closed_at=_utc(2026, 5, 1, 1, 7),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="0.10",
                total_exit_quantity="0.10",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="120",
                realized_pnl="20",
                commission="1",
                net_pnl="19",
                exit_reason="take_profit",
                duration_seconds=300,
                payload={"round_trip_id": "rt-1"},
            )

            report = build_leader_opportunity_diagnostics(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=leader_candidates_db_path,
                start_time=_utc(2026, 5, 1, 1, 0),
                end_time=_utc(2026, 5, 1, 1, 20),
            )

        self.assertEqual([row["symbol"] for row in report.rows], ["AAAUSDT", "BBBUSDT", "AAAUSDT"])
        self.assertEqual(report.rows[0]["trade_status"], "matched_closed_round_trip")
        self.assertEqual(report.rows[0]["miss_reason"], "")
        self.assertEqual(report.rows[0]["capture_rate"], "1")

    def test_build_leader_opportunity_diagnostics_uses_blocked_reason_for_miss(self) -> None:
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics
        from momentum_alpha.runtime_writes_events_decisions import insert_signal_decision

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            leader_candidates_db_path = Path(tmpdir) / "leader_candidates.db"
            insert_leader_candidate_snapshots_bulk(
                path=leader_candidates_db_path,
                rows=[
                    {
                        "timestamp": _utc(2026, 5, 1, 2, 0),
                        "source": "position-snapshot-replay",
                        "symbol": "CCCUSDT",
                        "rank": 1,
                        "daily_open_price": "300",
                        "latest_price": "330",
                        "daily_change_pct": "0.10",
                        "previous_hour_low": "299",
                        "current_hour_low": "301",
                        "leader_gap_pct": "0.02",
                        "payload": {"symbol": "CCCUSDT"},
                    }
                ],
            )
            insert_signal_decision(
                path=runtime_db_path,
                timestamp=_utc(2026, 5, 1, 2, 2),
                source="poll",
                decision_id="dec-1",
                decision_type="base_entry",
                symbol="CCCUSDT",
                payload={"blocked_reason": "invalid_stop_price"},
            )

            report = build_leader_opportunity_diagnostics(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=leader_candidates_db_path,
                start_time=_utc(2026, 5, 1, 2, 0),
                end_time=_utc(2026, 5, 1, 2, 10),
            )

        self.assertEqual(report.rows[0]["trade_status"], "missed")
        self.assertEqual(report.rows[0]["miss_reason"], "invalid_stop_price")

    def test_build_leader_opportunity_diagnostics_ignores_round_trip_opened_before_run_start(self) -> None:
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics
        from momentum_alpha.runtime_writes_events_decisions import insert_signal_decision
        from momentum_alpha.runtime_writes_history_trades import insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            leader_candidates_db_path = Path(tmpdir) / "leader_candidates.db"
            insert_leader_candidate_snapshots_bulk(
                path=leader_candidates_db_path,
                rows=[
                    {
                        "timestamp": _utc(2026, 5, 1, 3, 0),
                        "source": "position-snapshot-replay",
                        "symbol": "DDDTUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "110",
                        "daily_change_pct": "0.10",
                        "previous_hour_low": "99",
                        "current_hour_low": "100",
                        "leader_gap_pct": "0.02",
                        "payload": {"symbol": "DDDTUSDT"},
                    },
                    {
                        "timestamp": _utc(2026, 5, 1, 3, 5),
                        "source": "position-snapshot-replay",
                        "symbol": "DDDTUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "120",
                        "daily_change_pct": "0.20",
                        "previous_hour_low": "99",
                        "current_hour_low": "101",
                        "leader_gap_pct": "0.01",
                        "payload": {"symbol": "DDDTUSDT"},
                    },
                ],
            )
            insert_signal_decision(
                path=runtime_db_path,
                timestamp=_utc(2026, 5, 1, 3, 2),
                source="poll",
                decision_id="dec-2",
                decision_type="base_entry",
                symbol="DDDTUSDT",
                payload={},
            )
            insert_trade_round_trip(
                path=runtime_db_path,
                round_trip_id="rt-preexisting",
                symbol="DDDTUSDT",
                opened_at=_utc(2026, 5, 1, 2, 55),
                closed_at=_utc(2026, 5, 1, 3, 7),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="0.10",
                total_exit_quantity="0.10",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="120",
                realized_pnl="20",
                commission="1",
                net_pnl="19",
                exit_reason="take_profit",
                duration_seconds=720,
                payload={"round_trip_id": "rt-preexisting"},
            )

            report = build_leader_opportunity_diagnostics(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=leader_candidates_db_path,
                start_time=_utc(2026, 5, 1, 3, 0),
                end_time=_utc(2026, 5, 1, 3, 10),
            )

        self.assertNotEqual(report.rows[0]["trade_status"], "matched_closed_round_trip")
        self.assertEqual(report.rows[0]["matched_round_trip_id"], "")

    def test_write_opportunity_diagnostics_csv_writes_header_and_rows(self) -> None:
        from momentum_alpha.leader_opportunity_diagnostics import write_opportunity_diagnostics_csv

        with TemporaryDirectory() as tmpdir:
            csv_path = Path(tmpdir) / "opportunity_diagnostics.csv"
            write_opportunity_diagnostics_csv(
                path=csv_path,
                rows=[
                    {
                        "run_id": "1",
                        "symbol": "AAAUSDT",
                        "run_start": "2026-05-01T01:00:00+00:00",
                        "run_end": "2026-05-01T01:10:00+00:00",
                        "run_minutes": "10",
                        "snapshot_count": "2",
                        "start_daily_change_pct": "0.10",
                        "peak_daily_change_pct": "0.20",
                        "peak_timestamp": "2026-05-01T01:05:00+00:00",
                        "leader_gap_pct_start": "0.05",
                        "trade_status": "matched_closed_round_trip",
                        "signal_decision_id": "dec-1",
                        "decision_type": "base_entry",
                        "matched_round_trip_id": "rt-1",
                        "entered_at": "2026-05-01T01:02:00+00:00",
                        "exit_at": "2026-05-01T01:09:00+00:00",
                        "entry_price": "100",
                        "exit_price": "120",
                        "realized_pnl": "18",
                        "net_pnl": "17",
                        "peak_return_pct": "0.20",
                        "realized_return_pct": "0.20",
                        "capture_rate": "1",
                        "miss_reason": "",
                        "notes": "matched on closed round trip",
                    }
                ],
            )

            with csv_path.open(encoding="utf-8", newline="") as handle:
                rows = list(csv.reader(handle))

        self.assertEqual(
            rows[0],
            [
                "run_id",
                "symbol",
                "run_start",
                "run_end",
                "run_minutes",
                "snapshot_count",
                "start_daily_change_pct",
                "peak_daily_change_pct",
                "peak_timestamp",
                "leader_gap_pct_start",
                "trade_status",
                "signal_decision_id",
                "decision_type",
                "matched_round_trip_id",
                "entered_at",
                "exit_at",
                "entry_price",
                "exit_price",
                "realized_pnl",
                "net_pnl",
                "peak_return_pct",
                "realized_return_pct",
                "capture_rate",
                "miss_reason",
                "notes",
            ],
        )
        self.assertEqual(rows[1][1], "AAAUSDT")

    def test_build_leader_opportunity_diagnostics_raises_for_missing_runtime_db(self) -> None:
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk
        from momentum_alpha.leader_opportunity_diagnostics import build_leader_opportunity_diagnostics

        with TemporaryDirectory() as tmpdir:
            leader_candidates_db_path = Path(tmpdir) / "leader_candidates.db"
            insert_leader_candidate_snapshots_bulk(
                path=leader_candidates_db_path,
                rows=[
                    {
                        "timestamp": _utc(2026, 5, 1, 1, 0),
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "110",
                        "daily_change_pct": "0.10",
                        "previous_hour_low": "99",
                        "current_hour_low": "100",
                        "leader_gap_pct": "0.02",
                        "payload": {"symbol": "AAAUSDT"},
                    }
                ],
            )

            with self.assertRaises(FileNotFoundError):
                build_leader_opportunity_diagnostics(
                    runtime_db_path=Path(tmpdir) / "missing-runtime.db",
                    leader_candidates_db_path=leader_candidates_db_path,
                )


if __name__ == "__main__":
    unittest.main()
