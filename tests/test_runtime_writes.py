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


if __name__ == "__main__":
    unittest.main()
