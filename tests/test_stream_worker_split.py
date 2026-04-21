from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory


sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class StreamWorkerSplitTests(unittest.TestCase):
    def test_split_modules_import_and_expose_worker_entrypoints(self) -> None:
        from momentum_alpha import stream_worker, stream_worker_core, stream_worker_loop

        self.assertTrue(callable(stream_worker.run_user_stream))
        self.assertTrue(callable(stream_worker_core._prune_processed_event_ids))
        self.assertTrue(callable(stream_worker_core._save_user_stream_strategy_state))
        self.assertTrue(callable(stream_worker_loop.run_user_stream))

    def test_facade_still_exports_patch_targets(self) -> None:
        from momentum_alpha import stream_worker

        self.assertTrue(callable(stream_worker.extract_trade_fill))
        self.assertTrue(callable(stream_worker.insert_trade_fill))
        self.assertTrue(callable(stream_worker.insert_account_flow))
        self.assertTrue(callable(stream_worker.insert_algo_order))

    def test_prune_processed_event_ids_keeps_recent_entries(self) -> None:
        from momentum_alpha.stream_worker_core import _prune_processed_event_ids

        now = datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc)
        pruned = _prune_processed_event_ids(
            {
                "recent-1": "2026-04-15T10:00:00+00:00",
                "recent-2": "2026-04-15T11:00:00+00:00",
                "old-1": "2026-04-13T12:00:00+00:00",
            },
            now,
        )

        self.assertEqual(set(pruned.keys()), {"recent-1", "recent-2"})

    def test_save_user_stream_strategy_state_preserves_previous_leader_symbol(self) -> None:
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.stream_worker_core import _save_user_stream_strategy_state
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    positions={},
                    processed_event_ids={"evt-1": "2026-04-15T01:00:00+00:00"},
                    order_statuses={"123": {"symbol": "ETHUSDT", "status": "NEW"}},
                    recent_stop_loss_exits={},
                )
            )

            _save_user_stream_strategy_state(
                runtime_state_store=store,
                state=StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="ETHUSDT",
                    positions={},
                    processed_event_ids={
                        "evt-1": "2026-04-15T01:00:00+00:00",
                        "evt-2": "2026-04-15T02:00:00+00:00",
                    },
                    order_statuses={"123": {"symbol": "ETHUSDT", "status": "FILLED"}},
                    recent_stop_loss_exits={},
                ),
                now=datetime(2026, 4, 15, 12, 0, tzinfo=timezone.utc),
            )

            loaded = store.load()

        self.assertEqual(loaded.previous_leader_symbol, "BTCUSDT")
        self.assertEqual(
            loaded.processed_event_ids,
            {
                "evt-1": "2026-04-15T01:00:00+00:00",
                "evt-2": "2026-04-15T02:00:00+00:00",
            },
        )
        self.assertEqual(loaded.order_statuses["123"]["status"], "FILLED")
