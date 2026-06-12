import sys
import unittest
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class PollWorkerSplitTests(unittest.TestCase):
    def test_poll_worker_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import poll_worker_core, poll_worker_core_execution, poll_worker_core_live, poll_worker_core_state, poll_worker_loop

        self.assertTrue(callable(poll_worker_core.run_once))
        self.assertTrue(callable(poll_worker_core.run_once_live))
        self.assertTrue(callable(poll_worker_loop.run_forever))
        self.assertTrue(hasattr(poll_worker_core, "RunOnceResult"))
        self.assertTrue(callable(poll_worker_core_state._save_strategy_state))
        self.assertTrue(callable(poll_worker_core_execution.build_runtime_from_snapshots))
        self.assertTrue(callable(poll_worker_core_execution.run_once))
        self.assertTrue(callable(poll_worker_core_live.run_once_live))

    def test_poll_save_replaces_daily_maps_and_preserves_stream_fields(self) -> None:
        from momentum_alpha.poll_worker_core_state import _save_strategy_state
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(
                StoredStrategyState(
                    current_day="2026-06-12",
                    previous_leader_symbol="BTCUSDT",
                    daily_base_signal_times={"BTCUSDT": "2026-06-12T01:00:00+00:00"},
                    daily_base_signal_counts={"BTCUSDT": 1},
                    positions={},
                    processed_event_ids={"evt-1": "2026-06-12T01:00:00+00:00"},
                    order_statuses={"1": {"status": "NEW"}},
                    recent_stop_loss_exits={},
                )
            )

            _save_strategy_state(
                runtime_state_store=store,
                state=StoredStrategyState(
                    current_day="2026-06-12",
                    previous_leader_symbol="ETHUSDT",
                    daily_base_signal_times={"ETHUSDT": "2026-06-12T02:00:00+00:00"},
                    daily_base_signal_counts={"ETHUSDT": 2},
                    positions={},
                    recent_stop_loss_exits={},
                ),
            )
            loaded = store.load()

        self.assertEqual(
            loaded.daily_base_signal_times,
            {"ETHUSDT": "2026-06-12T02:00:00+00:00"},
        )
        self.assertEqual(loaded.daily_base_signal_counts, {"ETHUSDT": 2})
        self.assertEqual(loaded.processed_event_ids, {"evt-1": "2026-06-12T01:00:00+00:00"})
        self.assertEqual(loaded.order_statuses, {"1": {"status": "NEW"}})


if __name__ == "__main__":
    unittest.main()
