from __future__ import annotations

import unittest
from datetime import datetime, timezone
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DebouncedRebuildSchedulerTests(unittest.TestCase):
    def test_multiple_notifications_within_window_trigger_one_rebuild(self) -> None:
        from momentum_alpha.stream_worker_rebuild_scheduler import DebouncedRebuildScheduler

        now_values = [
            datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 10, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 20, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 8, 0, 50, tzinfo=timezone.utc),
        ]
        calls: list[str] = []

        def now_provider() -> datetime:
            return now_values.pop(0)

        scheduler = DebouncedRebuildScheduler(
            debounce_seconds=30,
            now_provider=now_provider,
            rebuild_fn=lambda: calls.append("rebuild"),
            logger=lambda msg: None,
            start_worker=False,
        )

        scheduler.notify()
        scheduler.notify()
        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.close()

        self.assertEqual(len(calls), 1)

    def test_rebuild_errors_are_logged_and_do_not_stop_future_runs(self) -> None:
        from momentum_alpha.stream_worker_rebuild_scheduler import DebouncedRebuildScheduler

        logs: list[str] = []

        scheduler = DebouncedRebuildScheduler(
            debounce_seconds=30,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, 0, tzinfo=timezone.utc),
            rebuild_fn=lambda: (_ for _ in ()).throw(RuntimeError("boom")),
            logger=logs.append,
            start_worker=False,
        )

        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.notify()
        scheduler.flush_for_test()
        scheduler.close()

        self.assertTrue(any("boom" in line for line in logs))


if __name__ == "__main__":
    unittest.main()
