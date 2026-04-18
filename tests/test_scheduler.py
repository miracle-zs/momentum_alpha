import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class SchedulerTests(unittest.TestCase):
    def test_scheduler_runs_once_per_new_minute(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 30, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
            ]
        )
        calls = []
        sleeps = []

        def fake_now():
            return next(times)

        def fake_run_once(now):
            calls.append(now)

        def fake_sleep(seconds):
            sleeps.append(seconds)

        run_loop(
            run_once=fake_run_once,
            now_provider=fake_now,
            sleep_fn=fake_sleep,
            max_ticks=2,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].minute, 1)
        self.assertEqual(calls[1].minute, 2)
        self.assertEqual(len(sleeps), 3)

    def test_scheduler_skips_duplicate_same_minute(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 1, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 20, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 40, tzinfo=timezone.utc),
            ]
        )
        calls = []

        run_loop(
            run_once=lambda now: calls.append(now),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=1,
        )
        self.assertEqual(len(calls), 1)

    def test_scheduler_continues_after_handler_exception(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 3, 0, tzinfo=timezone.utc),
            ]
        )
        calls = []
        errors = []

        def flaky_run_once(now):
            calls.append(now)
            if len(calls) == 1:
                raise RuntimeError("boom")

        run_loop(
            run_once=flaky_run_once,
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            error_handler=lambda exc, now: errors.append((str(exc), now.minute)),
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(errors, [("boom", 1)])
