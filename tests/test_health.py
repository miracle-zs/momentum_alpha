import sys
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class HealthTests(unittest.TestCase):
    def test_build_health_report_marks_recent_db_activity_ok(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            runtime_db_file = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="user_stream_event",
                payload={"event_type": "ACCOUNT_UPDATE"},
                source="user-stream",
            )

            report = build_runtime_health_report(
                now=now,
                runtime_db_file=runtime_db_file,
            )
            self.assertEqual(report.overall_status, "OK")
            self.assertTrue(all(item.status == "OK" for item in report.items))
            self.assertEqual(report.items[1].name, "poll_events")
            self.assertEqual(report.items[2].name, "user_stream_events")
            self.assertEqual(report.items[3].name, "runtime_db")

    def test_build_health_report_marks_stale_poll_events_fail(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            runtime_db_file = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=now - timedelta(minutes=10),
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )

            report = build_runtime_health_report(
                now=now,
                runtime_db_file=runtime_db_file,
                max_poll_event_age_seconds=180,
            )
            self.assertEqual(report.overall_status, "FAIL")
            self.assertEqual(report.items[1].name, "poll_events")
            self.assertEqual(report.items[1].status, "FAIL")

    def test_build_health_report_marks_stale_user_stream_events_fail(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            runtime_db_file = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=now - timedelta(minutes=30),
                event_type="user_stream_event",
                payload={"event_type": "ACCOUNT_UPDATE"},
                source="user-stream",
            )

            report = build_runtime_health_report(
                now=now,
                runtime_db_file=runtime_db_file,
                max_user_stream_event_age_seconds=1800 - 1,
            )

            self.assertEqual(report.overall_status, "FAIL")
            self.assertEqual(report.items[2].name, "user_stream_events")
            self.assertEqual(report.items[2].status, "FAIL")
            self.assertIn("stale", report.items[2].message)

    def test_build_health_report_accepts_recent_user_stream_heartbeat(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            runtime_db_file = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_file,
                timestamp=now,
                event_type="user_stream_heartbeat",
                payload={"stream_active": True},
                source="user-stream",
            )

            report = build_runtime_health_report(
                now=now,
                runtime_db_file=runtime_db_file,
            )

            self.assertEqual(report.overall_status, "OK")
            self.assertEqual(report.items[2].name, "user_stream_events")
            self.assertEqual(report.items[2].status, "OK")
