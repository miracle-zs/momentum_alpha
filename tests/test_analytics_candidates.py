import sqlite3
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class AnalyticsCandidateTests(unittest.TestCase):
    def test_bootstrap_creates_leader_candidate_table_and_indexes(self) -> None:
        from momentum_alpha.analytics_schema import bootstrap_leader_candidates_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            bootstrap_leader_candidates_db(path=db_path)

            connection = sqlite3.connect(db_path)
            try:
                tables = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='table' ORDER BY name"
                    )
                }
                indexes = {
                    row[0]
                    for row in connection.execute(
                        "SELECT name FROM sqlite_master WHERE type='index' ORDER BY name"
                    )
                }
            finally:
                connection.close()

        self.assertIn("leader_candidate_snapshots", tables)
        self.assertIn("idx_leader_candidate_snapshots_unique", indexes)
        self.assertIn("idx_leader_candidate_snapshots_rank_time", indexes)
        self.assertIn("idx_leader_candidate_snapshots_symbol_time", indexes)

    def test_insert_and_fetch_leader_candidate_snapshots(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            inserted = insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[
                    {
                        "timestamp": timestamp,
                        "source": "position-snapshot-replay",
                        "symbol": "AAAUSDT",
                        "rank": 1,
                        "daily_open_price": "100",
                        "latest_price": "112",
                        "daily_change_pct": "0.12",
                        "previous_hour_low": "105",
                        "current_hour_low": "108",
                        "leader_gap_pct": "0.03",
                        "payload": {"symbol": "AAAUSDT", "rank": 1},
                    },
                    {
                        "timestamp": timestamp,
                        "source": "position-snapshot-replay",
                        "symbol": "BBBUSDT",
                        "rank": 2,
                        "daily_open_price": "200",
                        "latest_price": "218",
                        "daily_change_pct": "0.09",
                        "previous_hour_low": "210",
                        "current_hour_low": "214",
                        "leader_gap_pct": None,
                        "payload": {"symbol": "BBBUSDT", "rank": 2},
                    },
                ],
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual([row["symbol"] for row in rows], ["AAAUSDT", "BBBUSDT"])
        self.assertEqual(rows[0]["source"], "position-snapshot-replay")
        self.assertEqual(rows[0]["rank"], 1)
        self.assertEqual(rows[0]["payload"]["symbol"], "AAAUSDT")

    def test_kline_backfill_rows_replace_replay_rows_but_replay_does_not_replace_kline_rows(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            base_row = {
                "timestamp": timestamp,
                "symbol": "AAAUSDT",
                "rank": 1,
                "daily_open_price": "100",
                "latest_price": "112",
                "daily_change_pct": "0.12",
                "previous_hour_low": "105",
                "current_hour_low": "108",
                "leader_gap_pct": "0.03",
                "payload": {},
            }
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "position-snapshot-replay", "latest_price": "112"}],
            )
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "kline-backfill", "latest_price": "113"}],
            )
            insert_leader_candidate_snapshots_bulk(
                path=db_path,
                rows=[{**base_row, "source": "position-snapshot-replay", "latest_price": "111"}],
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0]["source"], "kline-backfill")
        self.assertEqual(rows[0]["latest_price"], "113")

    def test_replay_position_snapshot_candidates_expands_runtime_candidates(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import replay_position_snapshot_candidates
        from momentum_alpha.runtime_store import insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            analytics_db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            insert_position_snapshot(
                path=runtime_db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol="AAAUSDT",
                position_count=0,
                order_status_count=0,
                payload={
                    "market_context": {
                        "leader_symbol": "AAAUSDT",
                        "leader_gap_pct": "0.03",
                        "candidates": [
                            {
                                "symbol": "AAAUSDT",
                                "daily_open_price": "100",
                                "latest_price": "112",
                                "daily_change_pct": "0.12",
                                "previous_hour_low": "105",
                                "current_hour_low": "108",
                                "leader_gap_pct": "0.03",
                            },
                            {
                                "symbol": "BBBUSDT",
                                "daily_open_price": "200",
                                "latest_price": "218",
                                "daily_change_pct": "0.09",
                                "previous_hour_low": "210",
                                "current_hour_low": "214",
                            },
                        ],
                    }
                },
            )

            inserted = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            inserted_again = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=analytics_db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual(inserted_again, 2)
        self.assertEqual([(row["symbol"], row["rank"]) for row in rows], [("AAAUSDT", 1), ("BBBUSDT", 2)])
        self.assertEqual(rows[0]["source"], "position-snapshot-replay")
        self.assertEqual(rows[0]["leader_gap_pct"], "0.03")

    def test_replay_position_snapshot_candidates_skips_malformed_candidates(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import replay_position_snapshot_candidates
        from momentum_alpha.runtime_store import insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            analytics_db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            insert_position_snapshot(
                path=runtime_db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol=None,
                position_count=0,
                order_status_count=0,
                payload={
                    "market_context": {
                        "candidates": [
                            {"latest_price": "112"},
                            {"symbol": "AAAUSDT", "latest_price": "112"},
                        ]
                    }
                },
            )

            inserted = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=analytics_db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 1)
        self.assertEqual([row["symbol"] for row in rows], ["AAAUSDT"])
        self.assertEqual(rows[0]["rank"], 2)

    def test_replay_position_snapshot_candidates_uses_leader_symbol_when_candidate_symbol_missing(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import replay_position_snapshot_candidates
        from momentum_alpha.runtime_store import insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            analytics_db_path = Path(tmpdir) / "leader_candidates.db"
            timestamp = datetime(2026, 5, 1, 1, 5, tzinfo=timezone.utc)
            insert_position_snapshot(
                path=runtime_db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol="AAAUSDT",
                position_count=0,
                order_status_count=0,
                payload={
                    "market_context": {
                        "leader_symbol": "AAAUSDT",
                        "leader_gap_pct": "0.03",
                        "candidates": [
                            {
                                "latest_price": "112",
                                "daily_open_price": "100",
                                "daily_change_pct": "0.12",
                                "previous_hour_low": "105",
                                "current_hour_low": "108",
                                "leader_gap_pct": "0.03",
                            }
                        ],
                    }
                },
            )

            inserted = replay_position_snapshot_candidates(
                runtime_db_path=runtime_db_path,
                leader_candidates_db_path=analytics_db_path,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=analytics_db_path,
                window_start=datetime(2026, 5, 1, 1, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 1, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 1)
        self.assertEqual([row["symbol"] for row in rows], ["AAAUSDT"])
        self.assertEqual(rows[0]["rank"], 1)

    def test_backfill_leader_candidates_from_klines_ranks_top_n(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import backfill_leader_candidates_from_klines

        class FakeClient:
            def __init__(self):
                self.calls = []

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                self.calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
                data = {
                    "AAAUSDT": [
                        [1777593600000, "100", "102", "99", "100", "1"],
                        [1777593900000, "100", "112", "100", "111", "1"],
                        [1777594200000, "111", "115", "109", "114", "1"],
                    ],
                    "BBBUSDT": [
                        [1777593600000, "200", "202", "198", "200", "1"],
                        [1777593900000, "200", "225", "199", "224", "1"],
                        [1777594200000, "218", "219", "213", "214", "1"],
                    ],
                    "CCCUSDT": [
                        [1777593600000, "50", "51", "49", "50", "1"],
                        [1777593900000, "50", "52", "50", "52", "1"],
                        [1777594200000, "52", "53", "51", "53", "1"],
                    ],
                }
                return data[symbol]

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            client = FakeClient()
            inserted = backfill_leader_candidates_from_klines(
                client=client,
                leader_candidates_db_path=db_path,
                start_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 5, 1, 0, 15, tzinfo=timezone.utc),
                symbols=["AAAUSDT", "BBBUSDT", "CCCUSDT"],
                interval="5m",
                top_n=2,
                logger=lambda message: None,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 0, 15, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 6)
        self.assertEqual(len(client.calls), 3)
        by_timestamp = {}
        for row in rows:
            by_timestamp.setdefault(row["timestamp"], []).append(row)
        self.assertEqual(len(by_timestamp), 3)
        second_snapshot = by_timestamp["2026-05-01T00:05:00+00:00"]
        self.assertEqual([(row["symbol"], row["rank"]) for row in second_snapshot], [("BBBUSDT", 1), ("AAAUSDT", 2)])
        self.assertEqual(second_snapshot[0]["daily_change_pct"], "0.12")
        self.assertEqual(second_snapshot[0]["leader_gap_pct"], "0.01")
        self.assertEqual(second_snapshot[0]["current_hour_low"], "198")

    def test_backfill_leader_candidates_from_klines_flushes_each_day(self) -> None:
        from momentum_alpha.cli_backfill_candidates import backfill_leader_candidates_from_klines
        from unittest.mock import patch

        class FakeClient:
            def __init__(self):
                self.calls = []

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                self.calls.append((symbol, interval, limit, start_time_ms, end_time_ms))
                day_start_ms = start_time_ms + 60 * 60 * 1000
                if symbol == "AAAUSDT":
                    return [
                        [day_start_ms, "100", "101", "99", "100", "1"],
                        [day_start_ms + 300000, "100", "112", "100", "111", "1"],
                    ]
                return [
                    [day_start_ms, "200", "201", "198", "200", "1"],
                    [day_start_ms + 300000, "200", "226", "199", "225", "1"],
                ]

        batches = []

        def fake_insert_leader_candidate_snapshots_bulk(*, path, rows):
            materialized_rows = list(rows)
            batches.append([row["timestamp"] for row in materialized_rows])
            return len(materialized_rows)

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            client = FakeClient()
            with patch(
                "momentum_alpha.cli_backfill_candidates.insert_leader_candidate_snapshots_bulk",
                side_effect=fake_insert_leader_candidate_snapshots_bulk,
            ):
                inserted = backfill_leader_candidates_from_klines(
                    client=client,
                    leader_candidates_db_path=db_path,
                    start_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                    end_time=datetime(2026, 5, 3, 0, 0, tzinfo=timezone.utc),
                    symbols=["AAAUSDT", "BBBUSDT"],
                    interval="5m",
                    top_n=1,
                    logger=lambda message: None,
                )

        self.assertEqual(inserted, 4)
        self.assertEqual(len(batches), 2)

    def test_backfill_leader_candidates_from_klines_continues_after_symbol_failure(self) -> None:
        from momentum_alpha.analytics_reads_candidates import fetch_leader_candidate_snapshots_for_window
        from momentum_alpha.cli_backfill_candidates import backfill_leader_candidates_from_klines

        class PartialClient:
            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if symbol == "BADUSDT":
                    raise RuntimeError("fetch failed")
                return [
                    [1777593600000, "100", "102", "99", "100", "1"],
                    [1777593900000, "100", "112", "100", "112", "1"],
                ]

        messages = []
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "leader_candidates.db"
            inserted = backfill_leader_candidates_from_klines(
                client=PartialClient(),
                leader_candidates_db_path=db_path,
                start_time=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 5, 1, 0, 10, tzinfo=timezone.utc),
                symbols=["BADUSDT", "AAAUSDT"],
                interval="5m",
                top_n=5,
                logger=messages.append,
            )
            rows = fetch_leader_candidate_snapshots_for_window(
                path=db_path,
                window_start=datetime(2026, 5, 1, 0, 0, tzinfo=timezone.utc),
                window_end=datetime(2026, 5, 1, 0, 10, tzinfo=timezone.utc),
            )

        self.assertEqual(inserted, 2)
        self.assertEqual({row["symbol"] for row in rows}, {"AAAUSDT"})
        self.assertTrue(any("failed_symbols=1" in message for message in messages))
