import sys
import unittest
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ExecutionPlanTests(unittest.TestCase):
    def test_builds_entry_and_stop_orders_from_base_entry_intent(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.execution import build_execution_plan
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.models import EntryIntent, MarketSnapshot, TickDecision

        symbols = {
            "BTCUSDT": ExchangeSymbol(
                symbol="BTCUSDT",
                status="TRADING",
                filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
                min_notional=Decimal("5"),
            )
        }
        market = {
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("60000"),
                latest_price=Decimal("61234.56"),
                previous_hour_low=Decimal("61000"),
                tradable=True,
                has_previous_hour_candle=True,
            )
        }
        decision = TickDecision(
            base_entries=[EntryIntent(symbol="BTCUSDT", stop_price=Decimal("61000"), leg_type="base")],
            add_on_entries=[],
            updated_stop_prices={},
            new_previous_leader_symbol="BTCUSDT",
        )

        plan = build_execution_plan(
            symbols=symbols,
            market=market,
            decision=decision,
            stop_budget=Decimal("10"),
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            position_side="LONG",
        )
        self.assertEqual(len(plan.entry_orders), 1)
        self.assertEqual(plan.entry_orders[0]["type"], "MARKET")
        self.assertIn("newClientOrderId", plan.entry_orders[0])
        self.assertEqual(plan.entry_orders[0]["positionSide"], "LONG")
        self.assertEqual(len(plan.stop_orders), 1)
        self.assertEqual(plan.stop_orders[0]["type"], "STOP_MARKET")
        self.assertIn("newClientOrderId", plan.stop_orders[0])
        self.assertEqual(plan.stop_orders[0]["positionSide"], "LONG")

    def test_builds_stop_replacements_for_hourly_updates(self) -> None:
        from momentum_alpha.execution import build_stop_replacements
        from momentum_alpha.models import TickDecision

        decision = TickDecision(
            base_entries=[],
            add_on_entries=[],
            updated_stop_prices={"BTCUSDT": Decimal("60500")},
            new_previous_leader_symbol="BTCUSDT",
        )

        replacements = build_stop_replacements(decision=decision)
        self.assertEqual(replacements, [("BTCUSDT", Decimal("60500"))])


class StateUpdateTests(unittest.TestCase):
    def test_apply_fill_creates_new_position_and_updates_previous_leader(self) -> None:
        from momentum_alpha.execution import apply_fill
        from momentum_alpha.models import StrategyState

        state = StrategyState(current_day=date(2026, 4, 15), previous_leader_symbol=None, positions={})
        updated = apply_fill(
            state=state,
            symbol="BTCUSDT",
            quantity=Decimal("1"),
            entry_price=Decimal("61200"),
            stop_price=Decimal("61000"),
            leg_type="base",
            filled_at=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            new_previous_leader_symbol="BTCUSDT",
        )

        self.assertEqual(updated.previous_leader_symbol, "BTCUSDT")
        self.assertIn("BTCUSDT", updated.positions)
        self.assertEqual(updated.positions["BTCUSDT"].total_quantity, Decimal("1"))

    def test_apply_fill_appends_add_on_leg_and_updates_stop(self) -> None:
        from momentum_alpha.execution import apply_fill
        from momentum_alpha.models import Position, PositionLeg, StrategyState

        opened_at = datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc)
        state = StrategyState(
            current_day=date(2026, 4, 15),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("61000"),
                    legs=(PositionLeg("BTCUSDT", Decimal("1"), Decimal("61200"), Decimal("61000"), opened_at, "base"),),
                )
            },
        )
        updated = apply_fill(
            state=state,
            symbol="BTCUSDT",
            quantity=Decimal("0.5"),
            entry_price=Decimal("61500"),
            stop_price=Decimal("61300"),
            leg_type="add_on",
            filled_at=datetime(2026, 4, 15, 2, 0, tzinfo=timezone.utc),
        )

        self.assertEqual(updated.positions["BTCUSDT"].total_quantity, Decimal("1.5"))
        self.assertEqual(updated.positions["BTCUSDT"].stop_price, Decimal("61300"))
        self.assertEqual(len(updated.positions["BTCUSDT"].legs), 2)
