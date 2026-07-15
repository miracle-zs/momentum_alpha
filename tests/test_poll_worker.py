from __future__ import annotations

import sys
import unittest
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class PollWorkerTests(unittest.TestCase):
    @staticmethod
    def _exchange_info() -> dict:
        return {
            "symbols": [
                {
                    "symbol": symbol,
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [
                        {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                        {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                        {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                        {"filterType": "MIN_NOTIONAL", "notional": "5"},
                    ],
                }
                for symbol in ("BTCUSDT", "ETHUSDT")
            ]
        }

    @staticmethod
    def _leader_change_snapshots() -> list[dict]:
        return [
            {
                "symbol": "BTCUSDT",
                "daily_open_price": Decimal("100"),
                "latest_price": Decimal("115"),
                "previous_hour_low": Decimal("108"),
                "current_hour_low": Decimal("112"),
                "tradable": True,
                "has_previous_hour_candle": True,
            },
            {
                "symbol": "ETHUSDT",
                "daily_open_price": Decimal("100"),
                "latest_price": Decimal("120"),
                "previous_hour_low": Decimal("110"),
                "current_hour_low": Decimal("116"),
                "tradable": True,
                "has_previous_hour_candle": True,
            },
        ]

    def test_poll_worker_exports_live_entrypoints(self) -> None:
        from momentum_alpha import poll_worker

        self.assertTrue(callable(poll_worker.run_once))
        self.assertTrue(callable(poll_worker.run_once_live))
        self.assertTrue(callable(poll_worker.run_forever))
        self.assertTrue(hasattr(poll_worker, "RunOnceResult"))

    def test_run_forever_passes_last_add_on_hour_to_live_runner(self) -> None:
        from momentum_alpha.execution import ExecutionPlan
        from momentum_alpha.models import StrategyState, TickDecision
        from momentum_alpha.poll_worker import RunOnceResult, run_forever
        from momentum_alpha.runtime import RuntimeTickResult

        calls = []

        class Client:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                            ],
                        }
                    ]
                }

        class Broker:
            pass

        def live_runner(**kwargs):
            calls.append(kwargs["last_add_on_hour"])
            decision = TickDecision(
                base_entries=[],
                add_on_entries=[],
                updated_stop_prices={},
                new_previous_leader_symbol=None,
                new_last_add_on_hour=2,
            )
            state = StrategyState(
                current_day=datetime(2026, 4, 21, tzinfo=timezone.utc).date(),
                previous_leader_symbol=None,
            )
            return RunOnceResult(
                runtime_result=RuntimeTickResult(
                    decision=decision,
                    execution_plan=ExecutionPlan(entry_orders=[], stop_orders=[]),
                    next_state=state,
                ),
                broker_responses=[],
                stop_replacements=[],
            )

        times = [
            datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc),
        ]

        run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=False,
            runtime_state_store=None,
            client_factory=lambda: Client(),
            broker_factory=lambda client: Broker(),
            now_provider=lambda: times.pop(0),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            run_once_live_fn=live_runner,
        )

        self.assertEqual(calls, [0, 2])

    def test_run_forever_keeps_add_on_hour_when_add_on_entry_submission_is_retryable(self) -> None:
        from momentum_alpha.execution import ExecutionPlan
        from momentum_alpha.models import EntryIntent, StrategyState, TickDecision
        from momentum_alpha.poll_worker import RunOnceResult, run_forever
        from momentum_alpha.runtime import RuntimeTickResult

        calls = []

        class Client:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                            ],
                        }
                    ]
                }

        class Broker:
            pass

        def live_runner(**kwargs):
            calls.append(kwargs["last_add_on_hour"])
            decision = TickDecision(
                base_entries=[],
                add_on_entries=[EntryIntent(symbol="BTCUSDT", stop_price=Decimal("61000"), leg_type="add_on")],
                updated_stop_prices={},
                new_previous_leader_symbol="BTCUSDT",
                new_last_add_on_hour=2,
            )
            state = StrategyState(
                current_day=datetime(2026, 4, 21, tzinfo=timezone.utc).date(),
                previous_leader_symbol="BTCUSDT",
            )
            return RunOnceResult(
                runtime_result=RuntimeTickResult(
                    decision=decision,
                    execution_plan=ExecutionPlan(entry_orders=[], stop_orders=[]),
                    next_state=state,
                ),
                broker_responses=[],
                stop_replacements=[],
                entry_order_failures=[
                    {
                        "symbol": "BTCUSDT",
                        "clientOrderId": "ma_260421020000_BTCUSDT_a00e",
                        "status": "SUBMIT_FAILED",
                        "retryable": True,
                    }
                ],
            )

        times = [
            datetime(2026, 4, 21, 1, 59, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc),
        ]

        run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=True,
            runtime_state_store=None,
            client_factory=lambda: Client(),
            broker_factory=lambda client: Broker(),
            now_provider=lambda: times.pop(0),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            run_once_live_fn=live_runner,
        )

        self.assertEqual(calls, [1, 1])

    def test_run_forever_advances_add_on_hour_after_deterministic_rejection(self) -> None:
        from types import SimpleNamespace

        from momentum_alpha.execution import ExecutionPlan
        from momentum_alpha.models import EntryIntent, StrategyState, TickDecision
        from momentum_alpha.poll_worker import RunOnceResult, run_forever
        from momentum_alpha.runtime import RuntimeTickResult

        calls = []

        class Client:
            def fetch_exchange_info(self):
                return {"symbols": []}

        def live_runner(**kwargs):
            calls.append(kwargs["last_add_on_hour"])
            decision = TickDecision(
                base_entries=[],
                add_on_entries=[EntryIntent(symbol="BTCUSDT", stop_price=Decimal("61000"), leg_type="add_on")],
                updated_stop_prices={},
                new_previous_leader_symbol="BTCUSDT",
                new_last_add_on_hour=2,
            )
            return RunOnceResult(
                runtime_result=RuntimeTickResult(
                    decision=decision,
                    execution_plan=ExecutionPlan(entry_orders=[], stop_orders=[]),
                    next_state=StrategyState(
                        current_day=datetime(2026, 4, 21, tzinfo=timezone.utc).date(),
                        previous_leader_symbol="BTCUSDT",
                    ),
                ),
                broker_responses=[],
                stop_replacements=[],
                entry_order_failures=[
                    {
                        "symbol": "BTCUSDT",
                        "clientOrderId": "ma_260421020000_BTCUSDT_a00e",
                        "status": "SUBMIT_FAILED",
                        "retryable": False,
                    }
                ],
            )

        times = [
            datetime(2026, 4, 21, 1, 59, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc),
        ]
        run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=True,
            runtime_state_store=None,
            client_factory=lambda: Client(),
            broker_factory=lambda client: SimpleNamespace(),
            now_provider=lambda: times.pop(0),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            run_once_live_fn=live_runner,
        )

        self.assertEqual(calls, [1, 2])

    def test_run_forever_refreshes_auto_symbols_during_long_running_poll(self) -> None:
        from momentum_alpha.execution import ExecutionPlan
        from momentum_alpha.models import StrategyState, TickDecision
        from momentum_alpha.poll_worker import RunOnceResult, run_forever
        from momentum_alpha.runtime import RuntimeTickResult

        symbol_batches = []

        class Client:
            def __init__(self) -> None:
                self.exchange_info_calls = 0

            def fetch_exchange_info(self):
                self.exchange_info_calls += 1
                symbols = ["BTCUSDT"] if self.exchange_info_calls == 1 else ["BTCUSDT", "NEWUSDT"]
                return {
                    "symbols": [
                        {
                            "symbol": symbol,
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.1"},
                            ],
                        }
                        for symbol in symbols
                    ]
                }

        class Broker:
            pass

        def live_runner(**kwargs):
            symbol_batches.append(kwargs["symbols"])
            decision = TickDecision(
                base_entries=[],
                add_on_entries=[],
                updated_stop_prices={},
                new_previous_leader_symbol=None,
                new_last_add_on_hour=kwargs["last_add_on_hour"],
            )
            state = StrategyState(
                current_day=datetime(2026, 4, 21, tzinfo=timezone.utc).date(),
                previous_leader_symbol=None,
            )
            return RunOnceResult(
                runtime_result=RuntimeTickResult(
                    decision=decision,
                    execution_plan=ExecutionPlan(entry_orders=[], stop_orders=[]),
                    next_state=state,
                ),
                broker_responses=[],
                stop_replacements=[],
            )

        times = [
            datetime(2026, 4, 21, 1, 0, tzinfo=timezone.utc),
            datetime(2026, 4, 21, 1, 1, tzinfo=timezone.utc),
        ]

        run_forever(
            symbols=None,
            previous_leader_symbol=None,
            submit_orders=False,
            runtime_state_store=None,
            client_factory=lambda: Client(),
            broker_factory=lambda client: Broker(),
            now_provider=lambda: times.pop(0),
            sleep_fn=lambda seconds: None,
            max_ticks=2,
            run_once_live_fn=live_runner,
        )

        self.assertEqual(symbol_batches[-1], ["BTCUSDT", "NEWUSDT"])

    def test_run_once_live_restores_daily_base_history_without_positions(self) -> None:
        from momentum_alpha.poll_worker_core_live import run_once_live
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)

        class Client:
            def fetch_exchange_info(self):
                return self_test._exchange_info()

        class Broker:
            pass

        self_test = self
        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(
                StoredStrategyState(
                    current_day="2026-06-12",
                    previous_leader_symbol="BTCUSDT",
                    daily_base_signal_times={"ETHUSDT": "2026-06-12T01:05:00+00:00"},
                    daily_base_signal_counts={"ETHUSDT": 1},
                    positions={},
                    processed_event_ids={},
                    order_statuses={},
                    recent_stop_loss_exits={},
                )
            )
            with (
                patch(
                    "momentum_alpha.poll_worker_core_live._resolve_symbols",
                    return_value=["BTCUSDT", "ETHUSDT"],
                ),
                patch(
                    "momentum_alpha.poll_worker_core_live._build_live_snapshots",
                    return_value=self._leader_change_snapshots(),
                ),
            ):
                result = run_once_live(
                    symbols=None,
                    now=now,
                    previous_leader_symbol=None,
                    client=Client(),
                    broker=Broker(),
                    submit_orders=False,
                    restore_positions=False,
                    runtime_state_store=store,
                )

        self.assertEqual(result.runtime_result.decision.base_entries, [])
        self.assertEqual(
            [item.symbol for item in result.runtime_result.decision.skipped_base_entries],
            ["ETHUSDT"],
        )

    def test_rejected_first_base_submission_releases_daily_opportunity(self) -> None:
        from momentum_alpha.poll_worker_core_live import run_once_live
        from momentum_alpha.runtime_store import RuntimeStateStore
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)

        class Client:
            def fetch_exchange_info(self):
                return self_test._exchange_info()

        class Broker:
            last_entry_order_failures = []

            def submit_execution_plan(self, plan):
                self.last_entry_order_failures = [
                    {"symbol": "ETHUSDT", "status": "SUBMIT_FAILED", "retryable": False}
                ]
                return []

        self_test = self
        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(
                StoredStrategyState(
                    current_day="2026-06-12",
                    previous_leader_symbol="BTCUSDT",
                    positions={},
                    processed_event_ids={},
                    order_statuses={},
                    recent_stop_loss_exits={},
                )
            )
            with (
                patch(
                    "momentum_alpha.poll_worker_core_live._resolve_symbols",
                    return_value=["BTCUSDT", "ETHUSDT"],
                ),
                patch(
                    "momentum_alpha.poll_worker_core_live._build_live_snapshots",
                    return_value=self._leader_change_snapshots(),
                ),
            ):
                run_once_live(
                    symbols=None,
                    now=now,
                    previous_leader_symbol=None,
                    client=Client(),
                    broker=Broker(),
                    submit_orders=True,
                    restore_positions=False,
                    runtime_state_store=store,
                )
            loaded = store.load()

        self.assertEqual(loaded.daily_base_signal_times, {})
        self.assertEqual(loaded.daily_base_signal_counts, {})

    def test_failed_stop_submission_immediately_repairs_partial_stop_coverage(self) -> None:
        from momentum_alpha.models import MarketSnapshot
        from momentum_alpha.poll_worker_core_live import _repair_failed_stop_coverage

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
        class Client:
            def fetch_position_risk(self):
                return [
                    {
                        "symbol": "ETHUSDT",
                        "positionAmt": "2",
                        "entryPrice": "120",
                        "updateTime": int(now.timestamp() * 1000),
                    }
                ]

            def fetch_open_orders(self):
                return []

            def fetch_open_algo_orders(self):
                return [
                    {
                        "symbol": "ETHUSDT",
                        "orderType": "STOP_MARKET",
                        "side": "SELL",
                        "algoStatus": "NEW",
                        "quantity": "1",
                        "triggerPrice": "110",
                        "clientAlgoId": "ma_260612020000_ETHUSDT_a00s",
                    }
                ]

        class Broker:
            def __init__(self) -> None:
                self.last_stop_replacement_failures = []
                self.replacement_calls = []

            def replace_stop_orders(self, *, replacements: list):
                self.replacement_calls = list(replacements)
                return [{"status": "NEW"}]

        broker = Broker()

        repaired, responses, failures = _repair_failed_stop_coverage(
            client=Client(),
            broker=broker,
            failed_stop_orders=[{"symbol": "ETHUSDT"}],
            runtime_market={
                "ETHUSDT": MarketSnapshot(
                    symbol="ETHUSDT",
                    daily_open_price=Decimal("100"),
                    latest_price=Decimal("120"),
                    previous_hour_low=Decimal("110"),
                    tradable=True,
                    has_previous_hour_candle=True,
                )
            },
            current_day=now,
            previous_leader_symbol="ETHUSDT",
            position_side=None,
        )

        self.assertEqual(repaired, [("ETHUSDT", Decimal("110"))])
        self.assertEqual(responses, [{"status": "NEW"}])
        self.assertEqual(failures, [])
        self.assertEqual(broker.replacement_calls, [("ETHUSDT", "2", "110")])

    def test_repeated_base_persists_complete_replay_telemetry(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.exchange_info import parse_exchange_info
        from momentum_alpha.poll_worker_core_live import run_once_live
        from momentum_alpha.runtime_store import (
            RuntimeStateStore,
            fetch_recent_audit_events,
            fetch_recent_position_snapshots,
            fetch_recent_signal_decisions,
        )
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        now = datetime(2026, 6, 12, 2, 5, tzinfo=timezone.utc)
        first_at = datetime(2026, 6, 12, 1, 5, tzinfo=timezone.utc)

        class Client:
            def fetch_exchange_info(self):
                return self_test._exchange_info()

        class Broker:
            pass

        class MarketDataCache:
            def resolve_symbols(self, *, symbols, client):
                return ["BTCUSDT", "ETHUSDT"]

            def exchange_symbol_map(self, *, client):
                return parse_exchange_info(client.fetch_exchange_info())

        self_test = self
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            store = RuntimeStateStore(path=db_path)
            store.save(
                StoredStrategyState(
                    current_day="2026-06-12",
                    previous_leader_symbol="BTCUSDT",
                    daily_base_signal_times={"ETHUSDT": first_at.isoformat()},
                    daily_base_signal_counts={"ETHUSDT": 1},
                    positions={},
                    processed_event_ids={},
                    order_statuses={},
                    recent_stop_loss_exits={},
                )
            )
            with patch(
                "momentum_alpha.poll_worker_core_live._build_live_snapshots",
                return_value=self._leader_change_snapshots(),
            ):
                run_once_live(
                    symbols=None,
                    now=now,
                    previous_leader_symbol=None,
                    client=Client(),
                    broker=Broker(),
                    submit_orders=False,
                    restore_positions=False,
                    runtime_state_store=store,
                    market_data_cache=MarketDataCache(),
                    audit_recorder=AuditRecorder(runtime_db_path=db_path, source="poll"),
                )

            decisions = fetch_recent_signal_decisions(path=db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=db_path, limit=1)
            events = fetch_recent_audit_events(path=db_path, limit=10)

        skipped = next(row for row in decisions if row["decision_type"] == "base_entry_skipped")
        self.assertEqual(skipped["symbol"], "ETHUSDT")
        self.assertEqual(skipped["intent_id"], "shadow_260612020500_ETHUSDT_02")
        self.assertEqual(
            skipped["payload"],
            {
                "base_signal_sequence": 2,
                "blocked_reason": "daily_repeat_base",
                "current_hour_low": "116",
                "daily_change_pct": "0.2",
                "daily_open_price": "100",
                "first_base_signal_at": first_at.isoformat(),
                "has_previous_hour_candle": True,
                "latest_price": "120",
                "leader_gap_pct": "0.05",
                "leg_type": "base",
                "min_notional": "5",
                "min_qty": "0.001",
                "previous_hour_low": "110",
                "shadow_opportunity_id": "shadow_260612020500_ETHUSDT_02",
                "step_size": "0.001",
                "stop_budget_usdt": "10",
                "stop_price": "110",
                "symbol": "ETHUSDT",
                "tick_size": "0.01",
                "tradable": True,
            },
        )
        self.assertEqual(snapshots[0]["payload"]["skipped_base_symbols"], ["ETHUSDT"])
        tick_event = next(row for row in events if row["event_type"] == "tick_result")
        self.assertEqual(tick_event["payload"]["skipped_base_symbols"], ["ETHUSDT"])

    def test_beijing_nine_base_block_persists_replayable_shadow_without_consuming_daily_state(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.exchange_info import parse_exchange_info
        from momentum_alpha.poll_worker_core_live import run_once_live
        from momentum_alpha.runtime_store import RuntimeStateStore, fetch_recent_signal_decisions
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        now = datetime(2026, 7, 14, 1, 5, tzinfo=timezone.utc)

        class Client:
            def fetch_exchange_info(self):
                return self_test._exchange_info()

        class Broker:
            pass

        class MarketDataCache:
            def resolve_symbols(self, *, symbols, client):
                return ["BTCUSDT", "ETHUSDT"]

            def exchange_symbol_map(self, *, client):
                return parse_exchange_info(client.fetch_exchange_info())

        self_test = self
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            store = RuntimeStateStore(path=db_path)
            store.save(
                StoredStrategyState(
                    current_day="2026-07-14",
                    previous_leader_symbol="BTCUSDT",
                    positions={},
                    processed_event_ids={},
                    order_statuses={},
                    recent_stop_loss_exits={},
                )
            )
            with patch(
                "momentum_alpha.poll_worker_core_live._build_live_snapshots",
                return_value=self._leader_change_snapshots(),
            ):
                run_once_live(
                    symbols=None,
                    now=now,
                    previous_leader_symbol=None,
                    client=Client(),
                    broker=Broker(),
                    submit_orders=False,
                    restore_positions=False,
                    runtime_state_store=store,
                    market_data_cache=MarketDataCache(),
                    audit_recorder=AuditRecorder(runtime_db_path=db_path, source="poll"),
                )
            decisions = fetch_recent_signal_decisions(path=db_path, limit=10)
            loaded = store.load()

        skipped = next(row for row in decisions if row["decision_type"] == "base_entry_skipped")
        self.assertEqual(skipped["intent_id"], "shadow_260714010500_ETHUSDT_01")
        self.assertEqual(skipped["payload"]["blocked_reason"], "beijing_09_base_block")
        self.assertEqual(skipped["payload"]["base_signal_sequence"], 1)
        self.assertEqual(skipped["payload"]["first_base_signal_at"], now.isoformat())
        self.assertEqual(loaded.daily_base_signal_times, {})
        self.assertEqual(loaded.daily_base_signal_counts, {})

    def test_early_first_add_on_persists_shadow_age_and_keeps_stop_update(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.exchange_info import parse_exchange_info
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.poll_worker_core_live import run_once_live
        from momentum_alpha.runtime_store import RuntimeStateStore, fetch_recent_signal_decisions
        from momentum_alpha.strategy_state_codec import StoredStrategyState

        now = datetime(2026, 7, 14, 2, 0, tzinfo=timezone.utc)
        base_opened_at = now - timedelta(minutes=15)
        position = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("100"),
            legs=(PositionLeg("ETHUSDT", Decimal("1"), Decimal("120"), Decimal("100"), base_opened_at, "base"),),
        )

        class Client:
            def fetch_exchange_info(self):
                return self_test._exchange_info()

            def fetch_open_orders(self):
                return []

            def fetch_position_risk(self):
                return [
                    {
                        "symbol": "ETHUSDT",
                        "positionAmt": "1",
                        "entryPrice": "120",
                        "updateTime": int(base_opened_at.timestamp() * 1000),
                    }
                ]

        class Broker:
            pass

        class MarketDataCache:
            def resolve_symbols(self, *, symbols, client):
                return ["BTCUSDT", "ETHUSDT"]

            def exchange_symbol_map(self, *, client):
                return parse_exchange_info(client.fetch_exchange_info())

        self_test = self
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            store = RuntimeStateStore(path=db_path)
            store.save(
                StoredStrategyState(
                    current_day="2026-07-14",
                    previous_leader_symbol="ETHUSDT",
                    positions={"ETHUSDT": position},
                    processed_event_ids={},
                    order_statuses={},
                    recent_stop_loss_exits={},
                )
            )
            with patch(
                "momentum_alpha.poll_worker_core_live._build_live_snapshots",
                return_value=self._leader_change_snapshots(),
            ):
                result = run_once_live(
                    symbols=None,
                    now=now,
                    previous_leader_symbol=None,
                    client=Client(),
                    broker=Broker(),
                    submit_orders=False,
                    restore_positions=True,
                    runtime_state_store=store,
                    market_data_cache=MarketDataCache(),
                    audit_recorder=AuditRecorder(runtime_db_path=db_path, source="poll"),
                    last_add_on_hour=1,
                )
            decisions = fetch_recent_signal_decisions(path=db_path, limit=10)

        self.assertEqual(result.runtime_result.decision.add_on_entries, [])
        self.assertEqual(result.runtime_result.decision.updated_stop_prices, {"ETHUSDT": Decimal("110")})
        skipped = next(row for row in decisions if row["decision_type"] == "add_on_skipped")
        self.assertEqual(skipped["payload"]["blocked_reason"], "first_add_on_before_30m")
        self.assertEqual(skipped["payload"]["base_opened_at"], base_opened_at.isoformat())
        self.assertEqual(Decimal(skipped["payload"]["base_age_minutes"]), Decimal("15"))
        self.assertTrue(skipped["payload"]["would_add_on_under_previous_strategy"])
