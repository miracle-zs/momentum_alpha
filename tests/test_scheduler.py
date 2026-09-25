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

    def test_scheduler_waits_for_minute_boundary_after_mid_minute_start(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 37, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 58, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
            ]
        )
        calls = []
        run_loop(
            run_once=lambda now: calls.append(now),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=1,
        )
        self.assertEqual([item.second for item in calls], [0])

    def test_scheduler_stops_after_in_flight_tick_when_requested(self) -> None:
        from momentum_alpha.scheduler import run_loop

        stop_requested = False
        calls = []
        sleeps = []

        def fake_run_once(now):
            nonlocal stop_requested
            calls.append(now)
            stop_requested = True

        run_loop(
            run_once=fake_run_once,
            now_provider=lambda: datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
            sleep_fn=lambda seconds: sleeps.append(seconds),
            stop_requested=lambda: stop_requested,
        )

        self.assertEqual(len(calls), 1)
        self.assertEqual(sleeps, [])

    def test_scheduler_runs_when_started_at_second_3(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 3, tzinfo=timezone.utc),
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
        self.assertEqual(calls[0].second, 3)

    def test_scheduler_runs_when_started_at_second_20(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 20, tzinfo=timezone.utc),
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
        self.assertEqual(calls[0].second, 20)

    def test_scheduler_skips_when_started_at_second_21_until_next_minute(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 21, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 45, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
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
        self.assertEqual(calls[0].minute, 2)
        self.assertEqual(calls[0].second, 0)

    def test_scheduler_runs_latest_closed_minute_after_long_running_handler(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                # handler finishes and next iteration wakes up at 01:02:15 (15s delay)
                datetime(2026, 4, 15, 1, 2, 15, tzinfo=timezone.utc),
                # next iteration at 01:03:00
                datetime(2026, 4, 15, 1, 3, 0, tzinfo=timezone.utc),
            ]
        )
        calls = []
        run_loop(
            run_once=lambda now: calls.append(now),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=3,
        )
        self.assertEqual(len(calls), 3)
        self.assertEqual(calls[0].minute, 1)
        self.assertEqual(calls[1].minute, 2)
        self.assertEqual(calls[1].second, 15)
        self.assertEqual(calls[2].minute, 3)
        self.assertEqual(calls[2].second, 0)

    def test_scheduler_skips_when_handler_finishes_too_late_and_runs_next_boundary(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                # handler finishes late in minute 2 (at second 35 > 20)
                datetime(2026, 4, 15, 1, 2, 35, tzinfo=timezone.utc),
                # next iteration at 01:03:00
                datetime(2026, 4, 15, 1, 3, 0, tzinfo=timezone.utc),
            ]
        )
        calls = []
        run_loop(
            run_once=lambda now: calls.append(now),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].minute, 1)
        self.assertEqual(calls[1].minute, 3)

    def test_scheduler_compensates_only_latest_closed_minute_after_multi_minute_pause(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                # Process paused / blocked for 3 minutes, wakes up at 01:04:05
                datetime(2026, 4, 15, 1, 4, 5, tzinfo=timezone.utc),
            ]
        )
        calls = []
        run_loop(
            run_once=lambda now: calls.append(now),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
        )
        self.assertEqual(len(calls), 2)
        self.assertEqual(calls[0].minute, 1)
        self.assertEqual(calls[1].minute, 4)
        self.assertEqual(calls[1].second, 5)

    def test_scheduler_tracks_delay_and_missed_ticks(self) -> None:
        from momentum_alpha.scheduler import run_loop

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 5, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 4, 10, tzinfo=timezone.utc),
            ]
        )
        delays = []
        missed = []
        run_loop(
            run_once=lambda now: None,
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            on_tick=lambda now, delay: delays.append((now.minute, delay)),
            on_missed_tick=lambda count, prev, curr: missed.append((count, prev[4], curr[4])),
        )
        self.assertEqual(delays, [(1, 5.0), (4, 10.0)])
        self.assertEqual(missed, [(2, 1, 4)])  # skipped minutes 2 and 3
