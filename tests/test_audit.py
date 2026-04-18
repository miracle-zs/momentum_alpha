import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class AuditTests(unittest.TestCase):
    def test_audit_recorder_writes_runtime_db_events(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.runtime_store import fetch_recent_audit_events

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="poll")
            recorder.record(
                event_type="tick_result",
                now=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
                payload={"base_entry_symbols": ["BTCUSDT"]},
            )
            recorder.record(
                event_type="user_stream_event",
                now=datetime(2026, 4, 15, 14, 1, tzinfo=timezone.utc),
                payload={"symbol": "BTCUSDT", "order_status": "FILLED"},
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_type"], "user_stream_event")
            self.assertEqual(events[0]["payload"]["order_status"], "FILLED")
            self.assertEqual(events[0]["source"], "poll")
            self.assertEqual(events[1]["event_type"], "tick_result")

    def test_summarize_recent_events_groups_by_type(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.runtime_store import summarize_audit_events

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="poll")
            base_time = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            recorder.record(event_type="tick_result", now=base_time, payload={"symbol": "BTCUSDT"})
            recorder.record(event_type="tick_result", now=base_time + timedelta(minutes=1), payload={"symbol": "ETHUSDT"})
            recorder.record(event_type="poll_error", now=base_time + timedelta(minutes=2), payload={"message": "boom"})

            summary = summarize_audit_events(
                path=db_path,
                now=base_time + timedelta(minutes=3),
                since_minutes=10,
                limit=10,
            )
            self.assertEqual(summary["total_events"], 3)
            self.assertEqual(summary["counts"]["tick_result"], 2)
            self.assertEqual(summary["counts"]["poll_error"], 1)
            self.assertEqual(summary["recent_events"][0]["event_type"], "poll_error")

    def test_audit_recorder_coerces_payload_values_for_runtime_db(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.runtime_store import fetch_recent_audit_events

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="user-stream")
            recorder.record(
                event_type="payload_coercion",
                now=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
                payload={
                    "timestamp": datetime(2026, 4, 15, 14, 1, tzinfo=timezone.utc),
                    "values": (1, 2),
                    "nested": {"seen": True},
                },
            )

            events = fetch_recent_audit_events(path=db_path, limit=10)
            self.assertEqual(events[0]["payload"]["timestamp"], "2026-04-15T14:01:00+00:00")
            self.assertEqual(events[0]["payload"]["values"], [1, 2])
            self.assertEqual(events[0]["payload"]["nested"], {"seen": True})

    def test_audit_recorder_swallows_runtime_db_write_failures(self) -> None:
        from momentum_alpha.audit import AuditRecorder

        calls = []

        def failing_writer(**kwargs):
            calls.append(kwargs)
            raise RuntimeError("db down")

        with TemporaryDirectory() as tmpdir:
            recorder = AuditRecorder(
                runtime_db_path=Path(tmpdir) / "runtime.db",
                db_insert_fn=failing_writer,
            )
            recorder.record(
                event_type="tick_result",
                now=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
                payload={"symbol": "BTCUSDT"},
            )

            self.assertEqual(len(calls), 1)
            self.assertEqual(calls[0]["event_type"], "tick_result")
