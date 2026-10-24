from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path
import sys
from tempfile import TemporaryDirectory
import threading
import time
import unittest

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from momentum_alpha.operational_read_model import OperationalReadModel
from momentum_alpha.runtime_schema import bootstrap_runtime_db
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    StoredStrategyState,
    insert_daily_review_report,
)


class OperationalReadModelTests(unittest.TestCase):
    def test_operational_read_model_serves_from_memory_within_ttl(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=runtime_db_file)
            model = OperationalReadModel(
                runtime_db_file=runtime_db_file,
                ttl_seconds=60.0,
            )
            calls = []

            def fake_loader():
                calls.append(len(calls) + 1)
                return {"call_index": len(calls)}

            snapshot1 = model.get_snapshot(room="live", loader=fake_loader)
            snapshot2 = model.get_snapshot(room="live", loader=fake_loader)

            self.assertEqual(snapshot1, {"call_index": 1})
            self.assertEqual(snapshot2, {"call_index": 1})
            self.assertEqual(len(calls), 1)

            # Explicit force refresh bypasses TTL
            snapshot3 = model.refresh(room="live")
            self.assertIsNotNone(snapshot3)

    def test_operational_read_model_lazy_room_separation(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc)
            bootstrap_runtime_db(path=runtime_db_file)
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-21", previous_leader_symbol="BTCUSDT")
            )
            insert_daily_review_report(
                path=runtime_db_file,
                report_date="2026-04-20",
                window_start="2026-04-20T00:00:00Z",
                window_end="2026-04-20T23:59:59Z",
                generated_at="2026-04-21T00:00:00Z",
                status="ok",
                trade_count=1,
                actual_total_pnl="10.0",
                counterfactual_total_pnl="12.0",
                pnl_delta="-2.0",
                replayed_add_on_count=0,
                stop_budget_usdt="10",
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
                warnings=[],
                payload={"review_key": "review_value"},
            )

            model = OperationalReadModel(
                runtime_db_file=runtime_db_file,
                now_provider=lambda: now,
                ttl_seconds=0.1,
            )

            # 1. Live room: lazy loads live projection and skips review report
            live_snapshot = model.get_snapshot(room="live", force_refresh=True)
            self.assertIsNone(live_snapshot.get("daily_review_report"))
            self.assertIn("runtime", live_snapshot)

            # 2. Review room: loads review report on demand
            review_snapshot = model.get_snapshot(room="review", force_refresh=True)
            self.assertIsNotNone(review_snapshot.get("daily_review_report"))
            self.assertEqual(
                review_snapshot["daily_review_report"]["payload"],
                {"review_key": "review_value"},
            )

    def test_operational_read_model_background_updater(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc)
            bootstrap_runtime_db(path=runtime_db_file)
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-21", previous_leader_symbol="ETHUSDT")
            )

            model = OperationalReadModel(
                runtime_db_file=runtime_db_file,
                now_provider=lambda: now,
                ttl_seconds=1.0,
            )

            model.start_background_updater(interval_seconds=0.05)
            try:
                time.sleep(0.2)
                self.assertTrue(model.is_fresh(room="live"))
                snapshot = model.get_snapshot(room="live")
                self.assertEqual(
                    (snapshot.get("runtime") or {}).get("previous_leader_symbol"),
                    "ETHUSDT",
                )
            finally:
                model.stop_background_updater()

    def test_operational_read_model_concurrent_thread_safety(self) -> None:
        with TemporaryDirectory() as tmpdir:
            runtime_db_file = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc)
            bootstrap_runtime_db(path=runtime_db_file)
            RuntimeStateStore(path=runtime_db_file).save(
                StoredStrategyState(current_day="2026-04-21", previous_leader_symbol="SOLUSDT")
            )
            model = OperationalReadModel(
                runtime_db_file=runtime_db_file,
                now_provider=lambda: now,
                ttl_seconds=1.0,
            )

            errors: list[Exception] = []

            def worker():
                try:
                    for _ in range(20):
                        snap = model.get_snapshot(room="live")
                        self.assertIsNotNone(snap)
                        time.sleep(0.005)
                except Exception as e:
                    errors.append(e)

            threads = [threading.Thread(target=worker) for _ in range(5)]
            for t in threads:
                t.start()
            for t in threads:
                t.join()

            self.assertEqual(errors, [])


if __name__ == "__main__":
    unittest.main()
