from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from types import SimpleNamespace
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

    def test_trade_fill_success_triggers_rebuild_hook_once(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext, build_user_stream_event_handler
        from momentum_alpha.user_stream import parse_user_stream_event

        calls: list[str] = []
        context = UserStreamWorkerContext(
            state=StrategyState(current_day=datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc).date(), previous_leader_symbol=None, positions={}),
            processed_event_ids={},
            order_statuses={},
        )
        audit_recorder = SimpleNamespace(runtime_db_path=Path("/tmp/runtime.db"), source="user-stream", record=lambda **kwargs: None)
        handler = build_user_stream_event_handler(
            logger=lambda msg: None,
            runtime_state_store=None,
            audit_recorder=audit_recorder,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            context=context,
            insert_trade_fill_fn=lambda **kwargs: None,
            record_position_snapshot_fn=lambda **kwargs: None,
            save_user_stream_strategy_state_fn=lambda **kwargs: None,
            on_trade_fill_persisted_fn=lambda: calls.append("rebuild"),
        )

        handler(
            parse_user_stream_event(
                {
                    "e": "ORDER_TRADE_UPDATE",
                    "T": 1776230400000,
                    "o": {
                        "s": "BTCUSDT",
                        "i": 123,
                        "t": 456,
                        "X": "FILLED",
                        "x": "TRADE",
                    },
                }
            )
        )

        self.assertEqual(calls, ["rebuild"])

    def test_trade_fill_insert_failure_does_not_trigger_rebuild_hook(self) -> None:
        from momentum_alpha.models import StrategyState
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext, build_user_stream_event_handler
        from momentum_alpha.user_stream import parse_user_stream_event

        calls: list[str] = []
        context = UserStreamWorkerContext(
            state=StrategyState(current_day=datetime(2026, 4, 21, 0, 0, tzinfo=timezone.utc).date(), previous_leader_symbol=None, positions={}),
            processed_event_ids={},
            order_statuses={},
        )
        audit_recorder = SimpleNamespace(runtime_db_path=Path("/tmp/runtime.db"), source="user-stream", record=lambda **kwargs: None)

        def failing_insert_trade_fill_fn(**kwargs):
            raise RuntimeError("insert failed")

        handler = build_user_stream_event_handler(
            logger=lambda msg: None,
            runtime_state_store=None,
            audit_recorder=audit_recorder,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            context=context,
            insert_trade_fill_fn=failing_insert_trade_fill_fn,
            record_position_snapshot_fn=lambda **kwargs: None,
            save_user_stream_strategy_state_fn=lambda **kwargs: None,
            on_trade_fill_persisted_fn=lambda: calls.append("rebuild"),
        )

        handler(
            parse_user_stream_event(
                {
                    "e": "ORDER_TRADE_UPDATE",
                    "T": 1776230400000,
                    "o": {
                        "s": "BTCUSDT",
                        "i": 123,
                        "t": 456,
                        "X": "FILLED",
                        "x": "TRADE",
                    },
                }
            )
        )

        self.assertEqual(calls, [])

    def test_run_user_stream_wires_scheduler_into_event_handler(self) -> None:
        from momentum_alpha import stream_worker_loop

        notifications: list[str] = []
        closed: list[str] = []
        captured: dict[str, object] = {}

        class FakeScheduler:
            def notify(self) -> None:
                notifications.append("notify")

            def close(self) -> None:
                closed.append("close")

        def fake_scheduler_factory(**kwargs):
            captured["rebuild_fn"] = kwargs["rebuild_fn"]
            return FakeScheduler()

        def fake_event_handler_factory(**kwargs):
            captured["on_trade_fill_persisted_fn"] = kwargs["on_trade_fill_persisted_fn"]

            def _on_event(_event):
                kwargs["on_trade_fill_persisted_fn"]()

            return _on_event

        class FakeStreamClient:
            def run_forever(self, on_event):
                on_event(object())
                return "listen-key"

        result = stream_worker_loop.run_user_stream(
            client=object(),
            testnet=False,
            logger=lambda msg: None,
            runtime_state_store=None,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            stream_client_factory=lambda **kwargs: FakeStreamClient(),
            reconnect_sleep_fn=lambda seconds: None,
            runtime_db_path=Path("/tmp/runtime.db"),
            event_handler_factory=fake_event_handler_factory,
            rebuild_trade_analytics_fn=lambda path: notifications.append(f"rebuild:{path.name}"),
            scheduler_factory=fake_scheduler_factory,
        )

        self.assertEqual(result, 0)
        self.assertEqual(notifications, ["notify"])
        self.assertEqual(closed, ["close"])
        self.assertTrue(callable(captured["rebuild_fn"]))
        self.assertTrue(callable(captured["on_trade_fill_persisted_fn"]))

    def test_run_user_stream_reconnects_after_clean_stream_end_when_enabled(self) -> None:
        from momentum_alpha import stream_worker_loop

        logs: list[str] = []
        sleep_calls: list[int] = []

        class FakeStreamClient:
            attempts = 0

            def run_forever(self, on_event):
                _ = on_event
                FakeStreamClient.attempts += 1
                return f"listen-{FakeStreamClient.attempts}"

        result = stream_worker_loop.run_user_stream(
            client=object(),
            testnet=False,
            logger=lambda msg: logs.append(msg),
            runtime_state_store=None,
            now_provider=lambda: datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
            stream_client_factory=lambda **kwargs: FakeStreamClient(),
            reconnect_sleep_fn=lambda seconds: sleep_calls.append(seconds),
            reconnect_on_stream_end=True,
            max_stream_cycles=2,
        )

        self.assertEqual(result, 0)
        self.assertEqual(FakeStreamClient.attempts, 2)
        self.assertEqual(sleep_calls, [1])
        self.assertTrue(any("stream-ended attempt=1" in message for message in logs))
        self.assertTrue(any("stream-ended attempt=2" in message for message in logs))
