import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeReadsTests(unittest.TestCase):
    def test_runtime_reads_module_exposes_recent_event_queries(self) -> None:
        from momentum_alpha import runtime_reads
        from momentum_alpha.runtime_store import bootstrap_runtime_db
        from momentum_alpha.runtime_writes import insert_audit_event, insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            timestamp = datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc)
            insert_audit_event(
                path=db_path,
                timestamp=timestamp,
                event_type="runtime_reads_smoke",
                payload={"source": "runtime_reads"},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="BTCUSDT:1",
                symbol="BTCUSDT",
                opened_at=timestamp,
                closed_at=timestamp,
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="120",
                realized_pnl="20",
                commission="0.1",
                net_pnl="19.9",
                exit_reason="sell",
                duration_seconds=0,
                payload={"legs": []},
            )

            events = runtime_reads.fetch_recent_audit_events(path=db_path, limit=10)
            round_trips = runtime_reads.fetch_recent_trade_round_trips(path=db_path, limit=10)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "runtime_reads_smoke")
            self.assertEqual(len(round_trips), 1)
            self.assertEqual(round_trips[0]["symbol"], "BTCUSDT")


if __name__ == "__main__":
    unittest.main()
