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

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            paths = {
                "state_file": root / "state.json",
                "poll_log_file": root / "momentum-alpha.log",
                "user_stream_log_file": root / "momentum-alpha-user-stream.log",
                "audit_log_file": root / "audit.jsonl",
            }
            for path in paths.values():
                path.write_text("x", encoding="utf-8")
                os.utime(path, (now.timestamp(), now.timestamp()))

            report = build_runtime_health_report(
                now=now,
                state_file=paths["state_file"],
                poll_log_file=paths["poll_log_file"],
                user_stream_log_file=paths["user_stream_log_file"],
                audit_log_file=paths["audit_log_file"],
            )
            self.assertEqual(report.overall_status, "OK")
            self.assertTrue(all(item.status == "OK" for item in report.items))

    def test_build_health_report_marks_stale_poll_log_fail(self) -> None:
        from momentum_alpha.health import build_runtime_health_report

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            state_file = root / "state.json"
            poll_log_file = root / "momentum-alpha.log"
            user_stream_log_file = root / "momentum-alpha-user-stream.log"
            audit_log_file = root / "audit.jsonl"
            for path in (state_file, poll_log_file, user_stream_log_file, audit_log_file):
                path.write_text("x", encoding="utf-8")
            fresh_ts = now.timestamp()
            stale_ts = (now - timedelta(minutes=10)).timestamp()
            os.utime(state_file, (fresh_ts, fresh_ts))
            os.utime(user_stream_log_file, (fresh_ts, fresh_ts))
            os.utime(audit_log_file, (fresh_ts, fresh_ts))
            os.utime(poll_log_file, (stale_ts, stale_ts))

            report = build_runtime_health_report(
                now=now,
                state_file=state_file,
                poll_log_file=poll_log_file,
                user_stream_log_file=user_stream_log_file,
                audit_log_file=audit_log_file,
                max_poll_log_age_seconds=180,
            )
            self.assertEqual(report.overall_status, "FAIL")
            self.assertEqual(report.items[1].name, "poll_log")
            self.assertEqual(report.items[1].status, "FAIL")
