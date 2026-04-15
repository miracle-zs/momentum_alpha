import json
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
    def test_audit_recorder_appends_json_lines(self) -> None:
        from momentum_alpha.audit import AuditRecorder, read_audit_events

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            recorder = AuditRecorder(path=path)
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

            events = read_audit_events(path=path)
            self.assertEqual(len(events), 2)
            self.assertEqual(events[0]["event_type"], "tick_result")
            self.assertEqual(events[1]["payload"]["order_status"], "FILLED")

    def test_summarize_recent_events_groups_by_type(self) -> None:
        from momentum_alpha.audit import AuditRecorder, summarize_audit_events

        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "audit.jsonl"
            recorder = AuditRecorder(path=path)
            base_time = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            recorder.record(event_type="tick_result", now=base_time, payload={"symbol": "BTCUSDT"})
            recorder.record(event_type="tick_result", now=base_time + timedelta(minutes=1), payload={"symbol": "ETHUSDT"})
            recorder.record(event_type="poll_error", now=base_time + timedelta(minutes=2), payload={"message": "boom"})

            summary = summarize_audit_events(
                path=path,
                now=base_time + timedelta(minutes=3),
                since_minutes=10,
                limit=10,
            )
            self.assertEqual(summary["total_events"], 3)
            self.assertEqual(summary["counts"]["tick_result"], 2)
            self.assertEqual(summary["counts"]["poll_error"], 1)
            self.assertEqual(summary["recent_events"][0]["event_type"], "poll_error")
