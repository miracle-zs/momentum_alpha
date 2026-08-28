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


class RuntimeWritesTests(unittest.TestCase):
    def test_runtime_writes_module_handles_simple_runtime_db_updates(self) -> None:
        from momentum_alpha import runtime_writes
        from momentum_alpha.runtime_store import fetch_notification_status, fetch_recent_audit_events

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"

            runtime_writes.insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="runtime_writes_smoke",
                payload={"source": "runtime_writes"},
            )
            runtime_writes.save_notification_status(
                path=db_path,
                status_key="serverchan",
                status="OK",
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            stored = fetch_notification_status(path=db_path, status_key="serverchan")

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "runtime_writes_smoke")
            self.assertEqual(stored["status"], "OK")

    def test_snapshot_writes_update_dashboard_live_state_and_series(self) -> None:
        from momentum_alpha.runtime_store import insert_account_snapshot, insert_position_snapshot

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            timestamp = datetime(2026, 4, 15, 8, 0, 35, tzinfo=timezone.utc)
            insert_account_snapshot(
                path=db_path,
                timestamp=timestamp,
                source="poll",
                position_count=1,
                open_order_count=2,
                wallet_balance="1000.00",
                available_balance="800.00",
                equity="1100.00",
                unrealized_pnl="12.00",
                payload={"account": "live"},
            )
            insert_position_snapshot(
                path=db_path,
                timestamp=timestamp,
                source="poll",
                leader_symbol="BTCUSDT",
                position_count=1,
                order_status_count=2,
                payload={"positions": {"BTCUSDT": {"total_quantity": "1"}}},
            )

            connection = sqlite3.connect(db_path)
            try:
                state_rows = connection.execute(
                    "SELECT state_key, timestamp, payload_json FROM dashboard_live_state ORDER BY state_key"
                ).fetchall()
                series_rows = connection.execute(
                    "SELECT series_type, bucket_timestamp, payload_json FROM dashboard_live_series ORDER BY series_type"
                ).fetchall()
            finally:
                connection.close()

        self.assertEqual([row[0] for row in state_rows], ["latest_account_snapshot", "latest_position_snapshot"])
        self.assertEqual(state_rows[0][1], "2026-04-15T08:00:35+00:00")
        self.assertIn('"equity": "1100.00"', state_rows[0][2])
        self.assertEqual([row[0] for row in series_rows], ["account", "position"])
        self.assertEqual(series_rows[0][1], "2026-04-15T08:00:00+00:00")
        self.assertIn('"equity": "1100.00"', series_rows[0][2])


if __name__ == "__main__":
    unittest.main()
