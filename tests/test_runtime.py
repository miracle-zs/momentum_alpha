import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class RuntimeTests(unittest.TestCase):
    def test_runtime_builds_symbol_state_from_snapshots(self) -> None:
        from momentum_alpha.runtime import build_runtime

        runtime = build_runtime(
            snapshots=[
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("100"),
                    "latest_price": Decimal("110"),
                    "previous_hour_low": Decimal("105"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                }
            ]
        )
        self.assertIn("BTCUSDT", runtime.market)

    def test_runtime_processes_tick_into_execution_plan(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.models import StrategyState
        from momentum_alpha.runtime import build_runtime, process_runtime_tick

        runtime = build_runtime(
            snapshots=[
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("60000"),
                    "latest_price": Decimal("61200"),
                    "previous_hour_low": Decimal("61000"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                },
                {
                    "symbol": "ETHUSDT",
                    "daily_open_price": Decimal("3000"),
                    "latest_price": Decimal("3040"),
                    "previous_hour_low": Decimal("3020"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                },
            ]
        )
        runtime = runtime.with_exchange_symbols(
            {
                "BTCUSDT": ExchangeSymbol(
                    symbol="BTCUSDT",
                    status="TRADING",
                    filters=SymbolFilters(
                        step_size=Decimal("0.001"),
                        min_qty=Decimal("0.001"),
                        tick_size=Decimal("0.10"),
                    ),
                    min_notional=Decimal("5"),
                ),
                "ETHUSDT": ExchangeSymbol(
                    symbol="ETHUSDT",
                    status="TRADING",
                    filters=SymbolFilters(
                        step_size=Decimal("0.001"),
                        min_qty=Decimal("0.001"),
                        tick_size=Decimal("0.01"),
                    ),
                    min_notional=Decimal("5"),
                ),
            }
        )
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="ETHUSDT",
            positions={},
        )

        result = process_runtime_tick(
            runtime=runtime,
            state=state,
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(result.decision.base_entries[0].symbol, "BTCUSDT")
        self.assertEqual(result.execution_plan.entry_orders[0]["symbol"], "BTCUSDT")
        self.assertEqual(result.next_state.previous_leader_symbol, "BTCUSDT")

    def test_runtime_applies_fill_after_plan_execution(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.execution import apply_fill
        from momentum_alpha.models import StrategyState
        from momentum_alpha.runtime import build_runtime, process_runtime_tick

        runtime = build_runtime(
            snapshots=[
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("60000"),
                    "latest_price": Decimal("61200"),
                    "previous_hour_low": Decimal("61000"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                }
            ]
        ).with_exchange_symbols(
            {
                "BTCUSDT": ExchangeSymbol(
                    symbol="BTCUSDT",
                    status="TRADING",
                    filters=SymbolFilters(
                        step_size=Decimal("0.001"),
                        min_qty=Decimal("0.001"),
                        tick_size=Decimal("0.10"),
                    ),
                    min_notional=Decimal("5"),
                )
            }
        )
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol=None,
            positions={},
        )

        result = process_runtime_tick(
            runtime=runtime,
            state=state,
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
        )
        filled_state = apply_fill(
            state=result.next_state,
            symbol="BTCUSDT",
            quantity=Decimal(result.execution_plan.entry_orders[0]["quantity"]),
            entry_price=Decimal("61200"),
            stop_price=Decimal(result.decision.base_entries[0].stop_price),
            leg_type="base",
            filled_at=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
        )

        self.assertIn("BTCUSDT", filled_state.positions)
        self.assertGreater(filled_state.positions["BTCUSDT"].total_quantity, Decimal("0"))
