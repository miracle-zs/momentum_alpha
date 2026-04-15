import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ReconciliationTests(unittest.TestCase):
    def test_restore_state_builds_positions_from_position_risk_and_open_orders(self) -> None:
        from momentum_alpha.reconciliation import restore_state

        position_risk = [
            {
                "symbol": "BTCUSDT",
                "positionAmt": "0.010",
                "entryPrice": "61200",
                "updateTime": 1700000000000,
            }
        ]
        open_orders = [
            {
                "symbol": "BTCUSDT",
                "type": "STOP_MARKET",
                "stopPrice": "61000",
            }
        ]

        state = restore_state(
            current_day="2026-04-15",
            previous_leader_symbol="ETHUSDT",
            position_risk=position_risk,
            open_orders=open_orders,
        )
        self.assertEqual(state.previous_leader_symbol, "ETHUSDT")
        self.assertIn("BTCUSDT", state.positions)
        self.assertEqual(state.positions["BTCUSDT"].stop_price, Decimal("61000"))
        self.assertEqual(state.positions["BTCUSDT"].total_quantity, Decimal("0.010"))

    def test_restore_state_ignores_flat_positions(self) -> None:
        from momentum_alpha.reconciliation import restore_state

        state = restore_state(
            current_day="2026-04-15",
            previous_leader_symbol=None,
            position_risk=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0",
                    "entryPrice": "0",
                    "updateTime": 1700000000000,
                }
            ],
            open_orders=[],
        )
        self.assertEqual(state.positions, {})

    def test_build_stop_reconciliation_plan_replaces_mismatched_stop(self) -> None:
        from momentum_alpha.models import Position, PositionLeg, TickDecision
        from momentum_alpha.reconciliation import build_stop_reconciliation_plan, restore_state
        from datetime import datetime, timezone, date

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        state = restore_state(
            current_day="2026-04-15",
            previous_leader_symbol="ETHUSDT",
            position_risk=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.010",
                    "entryPrice": "61200",
                    "updateTime": 1700000000000,
                }
            ],
            open_orders=[
                {
                    "symbol": "BTCUSDT",
                    "type": "STOP_MARKET",
                    "stopPrice": "61000",
                }
            ],
        )
        decision = TickDecision(
            base_entries=[],
            add_on_entries=[],
            updated_stop_prices={"BTCUSDT": Decimal("61100")},
            new_previous_leader_symbol="BTCUSDT",
        )

        plan = build_stop_reconciliation_plan(state=state, decision=decision)
        self.assertEqual(plan, [("BTCUSDT", Decimal("61100"))])

    def test_build_stop_reconciliation_plan_ignores_matching_stop(self) -> None:
        from momentum_alpha.models import TickDecision
        from momentum_alpha.reconciliation import build_stop_reconciliation_plan, restore_state

        state = restore_state(
            current_day="2026-04-15",
            previous_leader_symbol="ETHUSDT",
            position_risk=[
                {
                    "symbol": "BTCUSDT",
                    "positionAmt": "0.010",
                    "entryPrice": "61200",
                    "updateTime": 1700000000000,
                }
            ],
            open_orders=[
                {
                    "symbol": "BTCUSDT",
                    "type": "STOP_MARKET",
                    "stopPrice": "61000",
                }
            ],
        )
        decision = TickDecision(
            base_entries=[],
            add_on_entries=[],
            updated_stop_prices={"BTCUSDT": Decimal("61000")},
            new_previous_leader_symbol="BTCUSDT",
        )

        plan = build_stop_reconciliation_plan(state=state, decision=decision)
        self.assertEqual(plan, [])
