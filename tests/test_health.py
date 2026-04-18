import os
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
    def test_build_health_report_marks_recent_files_ok(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            paths = {
                "poll_log_file": root / "momentum-alpha.log",
                "user_stream_log_file": root / "momentum-alpha-user-stream.log",
                "runtime_db_file": root / "runtime.db",
            }
            for name, path in paths.items():
                if name != "runtime_db_file":
                    path.write_text("x", encoding="utf-8")
                    os.utime(path, (now.timestamp(), now.timestamp()))

            # Save strategy state to database
            RuntimeStateStore(path=paths["runtime_db_file"]).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=paths["runtime_db_file"],
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )

            report = build_runtime_health_report(
                now=now,
                poll_log_file=paths["poll_log_file"],
                user_stream_log_file=paths["user_stream_log_file"],
                runtime_db_file=paths["runtime_db_file"],
            )
            self.assertEqual(report.overall_status, "OK")
            self.assertTrue(all(item.status == "OK" for item in report.items))
            self.assertEqual(report.items[3].name, "runtime_db")

    def test_build_health_report_marks_stale_poll_log_fail(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"
            for path in (poll_log_file, user_stream_log_file):
                path.write_text("x", encoding="utf-8")
            fresh_ts = now.timestamp()
            stale_ts = (now - timedelta(minutes=10)).timestamp()
            os.utime(user_stream_log_file, (fresh_ts, fresh_ts))
            os.utime(poll_log_file, (stale_ts, stale_ts))

            # Save strategy state to database
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

            report = build_runtime_health_report(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
                max_poll_log_age_seconds=180,
            )
            self.assertEqual(report.overall_status, "FAIL")
            self.assertEqual(report.items[1].name, "poll_log")
            self.assertEqual(report.items[1].status, "FAIL")

    def test_build_health_report_uses_runtime_db_for_audit_freshness(self) -> None:
        from momentum_alpha.health import build_runtime_health_report
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            runtime_db_file = root / "runtime.db"
            for path in (poll_log_file, user_stream_log_file):
                path.write_text("x", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            # Save strategy state to database
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

            report = build_runtime_health_report(
                now=now,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                runtime_db_file=runtime_db_file,
            )

            self.assertEqual(report.overall_status, "OK")
            self.assertEqual(report.items[-1].name, "runtime_db")
            self.assertEqual(report.items[-1].status, "OK")
