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

    def test_user_stream_event_handler_links_trade_fill_to_poll_intent(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.models import StrategyState
        from momentum_alpha.orders import build_client_order_id
        from momentum_alpha.runtime_store import insert_broker_order
        from momentum_alpha.stream_worker_core import UserStreamWorkerContext, build_user_stream_event_handler
        from momentum_alpha.trace_ids import build_decision_id, build_order_intent_id
        from momentum_alpha.user_stream import parse_user_stream_event

        captured: dict[str, dict] = {}

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            now = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)
            decision_id = build_decision_id(now=now)
            intent_id = build_order_intent_id(symbol="BTCUSDT", opened_at=now, leg_type="base", sequence=0)
            client_order_id = build_client_order_id(
                symbol="BTCUSDT",
                opened_at=now,
                leg_type="base",
                order_kind="entry",
                sequence=0,
            )
            insert_broker_order(
                path=db_path,
                timestamp=now,
                source="poll",
                action_type="submit_execution_plan",
                symbol="BTCUSDT",
                order_id="101",
                client_order_id=client_order_id,
                decision_id=decision_id,
                intent_id=intent_id,
                order_status="NEW",
                side="BUY",
                quantity=1,
                price=100,
                payload={"clientOrderId": client_order_id},
            )

            context = UserStreamWorkerContext(
                state=StrategyState(
                    current_day=now.date(),
                    previous_leader_symbol=None,
                    positions={},
                ),
                processed_event_ids={},
                order_statuses={},
            )
            audit_recorder = AuditRecorder(runtime_db_path=db_path, source="user-stream")

            handler = build_user_stream_event_handler(
                logger=lambda msg: None,
                runtime_state_store=None,
                audit_recorder=audit_recorder,
                now_provider=lambda: now,
                context=context,
                record_broker_orders_fn=lambda **kwargs: captured.__setitem__("broker_orders", kwargs),
                insert_trade_fill_fn=lambda **kwargs: captured.__setitem__("trade_fill", kwargs),
                record_position_snapshot_fn=lambda **kwargs: captured.__setitem__("position_snapshot", kwargs),
                save_user_stream_strategy_state_fn=lambda **kwargs: None,
            )

            handler(
                parse_user_stream_event(
                    {
                        "e": "ORDER_TRADE_UPDATE",
                        "T": 1776729600000,
                        "o": {
                            "s": "BTCUSDT",
                            "i": 101,
                            "t": 202,
                            "c": client_order_id,
                            "X": "FILLED",
                            "x": "TRADE",
                            "ap": "100",
                            "z": "1",
                            "L": "100",
                            "l": "1",
                            "rp": "0",
                            "n": "0",
                            "N": "USDT",
                        },
                    }
                )
            )

        self.assertEqual(captured["trade_fill"]["decision_id"], decision_id)
        self.assertEqual(captured["trade_fill"]["intent_id"], intent_id)
        self.assertEqual(captured["broker_orders"]["decision_id"], decision_id)
        self.assertEqual(captured["broker_orders"]["responses"][0]["decision_id"], decision_id)
        self.assertEqual(captured["broker_orders"]["responses"][0]["intent_id"], intent_id)
        self.assertEqual(captured["position_snapshot"]["decision_id"], decision_id)
        self.assertEqual(captured["position_snapshot"]["intent_id"], intent_id)

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
        self.assertFalse(any("listen-" in message for message in logs))

    def test_run_user_stream_records_heartbeat_on_start(self) -> None:
        from momentum_alpha import stream_worker_loop
        from momentum_alpha.runtime_store import fetch_recent_audit_events

        now = datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc)

        class FakeStreamClient:
            def run_forever(self, on_event):
                _ = on_event
                return "listen-key"

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"

            result = stream_worker_loop.run_user_stream(
                client=object(),
                testnet=False,
                logger=lambda msg: None,
                runtime_state_store=None,
                now_provider=lambda: now,
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
                reconnect_sleep_fn=lambda seconds: None,
                runtime_db_path=runtime_db_path,
            )

            events = fetch_recent_audit_events(
                path=runtime_db_path,
                limit=10,
            )

        self.assertEqual(result, 0)
        self.assertTrue(any(event["event_type"] == "user_stream_heartbeat" for event in events))

    def test_user_stream_watchdog_requests_reconnect_when_broker_action_has_no_stream_event(self) -> None:
        from momentum_alpha import stream_worker_loop
        from momentum_alpha.runtime_store import insert_audit_event

        now = datetime(2026, 4, 21, 8, 40, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
                event_type="user_stream_event",
                payload={"event_type": "ACCOUNT_UPDATE"},
                source="user-stream",
            )
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 5, tzinfo=timezone.utc),
                event_type="broker_submit",
                payload={"symbol": "BTCUSDT"},
                source="poll",
            )

            result = stream_worker_loop._should_reconnect_stale_user_stream(
                runtime_db_path=runtime_db_path,
                now=now,
                max_silence_seconds=1800,
            )

        self.assertTrue(result.should_reconnect)
        self.assertEqual(result.latest_action_event_type, "broker_submit")
        self.assertEqual(result.silence_seconds, 2100)

    def test_user_stream_watchdog_stays_quiet_when_stream_event_follows_broker_action(self) -> None:
        from momentum_alpha import stream_worker_loop
        from momentum_alpha.runtime_store import insert_audit_event

        now = datetime(2026, 4, 21, 8, 40, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 5, tzinfo=timezone.utc),
                event_type="broker_submit",
                payload={"symbol": "BTCUSDT"},
                source="poll",
            )
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 6, tzinfo=timezone.utc),
                event_type="user_stream_event",
                payload={"event_type": "ORDER_TRADE_UPDATE"},
                source="user-stream",
            )

            result = stream_worker_loop._should_reconnect_stale_user_stream(
                runtime_db_path=runtime_db_path,
                now=now,
                max_silence_seconds=1800,
            )

        self.assertFalse(result.should_reconnect)

    def test_run_user_stream_watchdog_sets_stream_stop_event_for_stale_business_events(self) -> None:
        from momentum_alpha import stream_worker_loop
        from momentum_alpha.runtime_store import insert_audit_event

        now = datetime(2026, 4, 21, 8, 40, tzinfo=timezone.utc)
        logs: list[str] = []
        captured: dict[str, bool] = {}

        class FakeStreamClient:
            stop_event_factory = None

            def run_forever(self, on_event):
                _ = on_event
                stop_event = self.stop_event_factory()
                captured["stop_event_set"] = stop_event.wait(timeout=1)
                return "listen-key"

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 0, tzinfo=timezone.utc),
                event_type="user_stream_event",
                payload={"event_type": "ACCOUNT_UPDATE"},
                source="user-stream",
            )
            insert_audit_event(
                path=runtime_db_path,
                timestamp=datetime(2026, 4, 21, 8, 5, tzinfo=timezone.utc),
                event_type="broker_submit",
                payload={"symbol": "BTCUSDT"},
                source="poll",
            )

            result = stream_worker_loop.run_user_stream(
                client=object(),
                testnet=False,
                logger=lambda message: logs.append(message),
                runtime_state_store=None,
                now_provider=lambda: now,
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
                reconnect_sleep_fn=lambda seconds: None,
                runtime_db_path=runtime_db_path,
                max_user_stream_silence_after_action_seconds=1800,
            )

        self.assertEqual(result, 0)
        self.assertTrue(captured["stop_event_set"])
        self.assertTrue(any("event=watchdog-reconnect" in message for message in logs))
