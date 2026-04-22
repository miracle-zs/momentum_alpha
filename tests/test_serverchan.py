import io
import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ServerChanTests(unittest.TestCase):
    def test_notify_on_fail_transition_and_persist_status(self) -> None:
        from momentum_alpha.runtime_store import fetch_notification_status
        from momentum_alpha.serverchan import process_health_notification

        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"code":0,"message":"","data":{"errno":0}}'

        def fake_opener(request, timeout=10):
            requests.append(
                {
                    "url": request.full_url,
                    "method": request.get_method(),
                    "data": request.data.decode("utf-8"),
                    "timeout": timeout,
                }
            )
            return FakeResponse()

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            output = "\n".join(
                [
                    "overall=FAIL",
                    "poll_events status=FAIL stale age_seconds=900 max_age_seconds=180",
                ]
            )
            result = process_health_notification(
                sendkey="SCT123456",
                runtime_db_path=runtime_db_path,
                health_output=output,
                now=datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc),
                hostname="vm-1",
                opener=fake_opener,
            )
            self.assertTrue(result["notified"])
            self.assertEqual(result["event"], "fail")
            self.assertEqual(len(requests), 1)
            self.assertEqual(requests[0]["url"], "https://sctapi.ftqq.com/SCT123456.send")
            self.assertEqual(requests[0]["method"], "POST")
            self.assertIn("text=Momentum+Alpha+%E5%81%A5%E5%BA%B7%E5%91%8A%E8%AD%A6+%40+vm-1", requests[0]["data"])
            stored = fetch_notification_status(path=runtime_db_path, status_key="serverchan")
            self.assertEqual(stored["status"], "FAIL")

    def test_notify_on_recovery_transition_only_once(self) -> None:
        from momentum_alpha.runtime_store import fetch_notification_status, save_notification_status
        from momentum_alpha.serverchan import process_health_notification

        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"code":0,"message":"","data":{"errno":0}}'

        def fake_opener(request, timeout=10):
            requests.append(request.data.decode("utf-8"))
            return FakeResponse()

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            save_notification_status(
                path=runtime_db_path,
                status_key="serverchan",
                status="FAIL",
                timestamp=datetime(2026, 4, 15, 6, 59, tzinfo=timezone.utc),
            )
            output = "\n".join(
                [
                    "overall=OK",
                    "poll_events status=OK fresh age_seconds=5",
                ]
            )
            result = process_health_notification(
                sendkey="SCT123456",
                runtime_db_path=runtime_db_path,
                health_output=output,
                now=datetime(2026, 4, 15, 7, 1, tzinfo=timezone.utc),
                hostname="vm-1",
                opener=fake_opener,
            )
            self.assertTrue(result["notified"])
            self.assertEqual(result["event"], "recovered")
            self.assertEqual(len(requests), 1)
            self.assertIn("Momentum+Alpha+%E5%B7%B2%E6%81%A2%E5%A4%8D+%40+vm-1", requests[0])

            result = process_health_notification(
                sendkey="SCT123456",
                runtime_db_path=runtime_db_path,
                health_output=output,
                now=datetime(2026, 4, 15, 7, 2, tzinfo=timezone.utc),
                hostname="vm-1",
                opener=fake_opener,
            )
            self.assertFalse(result["notified"])
            self.assertEqual(result["event"], "none")
            self.assertEqual(len(requests), 1)
            stored = fetch_notification_status(path=runtime_db_path, status_key="serverchan")
            self.assertEqual(stored["status"], "OK")

    def test_cli_main_reads_health_output_file(self) -> None:
        from momentum_alpha.serverchan import cli_main

        requests = []

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b'{"code":0}'

        def fake_opener(request, timeout=10):
            requests.append(request.full_url)
            return FakeResponse()

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            health_path = Path(tmpdir) / "health.txt"
            health_path.write_text("overall=FAIL\nruntime_db status=FAIL missing runtime_db\n", encoding="utf-8")
            stdout = io.StringIO()
            exit_code = cli_main(
                argv=[
                    "--sendkey",
                    "SCT123456",
                    "--runtime-db-file",
                    str(runtime_db_path),
                    "--health-output-file",
                    str(health_path),
                    "--hostname",
                    "vm-1",
                ],
                now_provider=lambda: datetime(2026, 4, 15, 7, 0, tzinfo=timezone.utc),
                opener=fake_opener,
                stdout=stdout,
            )
            self.assertEqual(exit_code, 0)
            self.assertIn("notified=yes", stdout.getvalue())
            self.assertEqual(requests, ["https://sctapi.ftqq.com/SCT123456.send"])
