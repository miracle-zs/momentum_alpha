from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))


class PollWorkerTests(unittest.TestCase):
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

        self.assertEqual(calls, [1, 2])
