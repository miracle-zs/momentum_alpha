import json
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeStoreTests(unittest.TestCase):
    def test_bootstrap_and_insert_audit_event(self) -> None:
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_audit_event_counts,
            fetch_recent_audit_events,
            insert_audit_event,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="tick_result",
                payload={"symbol_count": 538, "leader": "INUSDT"},
                source="poll",
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            counts = fetch_audit_event_counts(path=db_path, limit=10)

            self.assertEqual(len(events), 1)
            self.assertEqual(events[0]["event_type"], "tick_result")
            self.assertEqual(events[0]["payload"]["leader"], "INUSDT")
            self.assertEqual(events[0]["source"], "poll")
            self.assertEqual(counts, {"tick_result": 1})

    def test_fetch_recent_audit_events_returns_newest_first(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db, fetch_recent_audit_events, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 0, tzinfo=timezone.utc),
                event_type="poll_tick",
                payload={"symbol_count": 538},
            )
            insert_audit_event(
                path=db_path,
                timestamp=datetime(2026, 4, 15, 8, 1, tzinfo=timezone.utc),
                event_type="user_stream_worker_start",
                payload={"position_count": 0},
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            self.assertEqual([event["event_type"] for event in events], ["user_stream_worker_start", "poll_tick"])

    def test_bootstrap_runtime_db_is_idempotent(self) -> None:
        from momentum_alpha.runtime_store import bootstrap_runtime_db

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            bootstrap_runtime_db(path=db_path)
            self.assertTrue(db_path.exists())
