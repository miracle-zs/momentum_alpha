import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ReconciliationTests(unittest.TestCase):
    def test_merge_position_history_updates_aggregate_without_inventing_add_on(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.reconciliation import merge_position_history

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        existing = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("9"),
            legs=(PositionLeg("ETHUSDT", Decimal("100"), Decimal("10"), Decimal("9"), opened_at, "base"),),
        )
        candidate = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("9.5"),
            legs=(
                PositionLeg(
                    "ETHUSDT",
                    Decimal("150"),
                    Decimal("10.6666666666666666666666666667"),
                    Decimal("9.5"),
                    opened_at,
                    "restored",
                ),
            ),
        )

        merged = merge_position_history(existing, candidate)

        self.assertEqual(merged.total_quantity, Decimal("150"))
        self.assertEqual(len(merged.legs), 1)
        self.assertEqual(merged.legs[0].leg_type, "base")
        self.assertEqual(merged.legs[0].quantity, Decimal("150"))
        self.assertAlmostEqual(float(merged.legs[0].entry_price), 10.666666666666666, places=9)
        self.assertEqual(merged.legs[0].leg_source, "reconciliation")
        self.assertEqual(merged.stop_price, Decimal("9.5"))

    def test_merge_position_history_prefers_known_candidate_legs(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.reconciliation import merge_position_history

        opened_at = datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc)
        existing = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("9"),
            legs=(PositionLeg("ETHUSDT", Decimal("100"), Decimal("10"), Decimal("9"), opened_at, "restored"),),
        )
        candidate = Position(
            symbol="ETHUSDT",
            stop_price=Decimal("9.5"),
            legs=(
                PositionLeg("ETHUSDT", Decimal("100"), Decimal("10"), Decimal("9.5"), opened_at, "base"),
                PositionLeg("ETHUSDT", Decimal("50"), Decimal("12"), Decimal("9.5"), opened_at, "add_on"),
            ),
        )

        merged = merge_position_history(existing, candidate)

        self.assertEqual(merged.legs, candidate.legs)

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
        self.assertEqual(state.daily_base_signal_times, {})
        self.assertEqual(state.daily_base_signal_counts, {})

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

    def test_restore_state_reads_stop_from_open_algo_orders(self) -> None:
        from momentum_alpha.reconciliation import restore_state

        state = restore_state(
            current_day="2026-04-15",
            previous_leader_symbol=None,
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
                    "orderType": "STOP_MARKET",
                    "triggerPrice": "61000",
                    "clientAlgoId": "ma_foo",
                }
            ],
        )
        self.assertEqual(state.positions["BTCUSDT"].stop_price, Decimal("61000"))

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

    def test_build_missing_stop_reconciliation_plan_targets_restored_position_without_stop(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.reconciliation import build_missing_stop_reconciliation_plan

        state = StrategyState(
            current_day=datetime(2026, 4, 15, tzinfo=timezone.utc).date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("0"),
                    legs=(
                        PositionLeg(
                            symbol="BTCUSDT",
                            quantity=Decimal("0.010"),
                            entry_price=Decimal("61100"),
                            stop_price=Decimal("0"),
                            opened_at=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                            leg_type="restored",
                        ),
                    ),
                )
            },
        )
        market = {
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("60000"),
                latest_price=Decimal("61200"),
                previous_hour_low=Decimal("61000"),
                tradable=True,
                has_previous_hour_candle=True,
            )
        }

        plan = build_missing_stop_reconciliation_plan(state=state, market=market)
        self.assertEqual(plan, [("BTCUSDT", Decimal("61000"))])

    def test_stop_coverage_plan_replaces_partial_stop_coverage(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.reconciliation import build_stop_coverage_reconciliation_plan

        state = StrategyState(
            current_day=datetime(2026, 4, 15, tzinfo=timezone.utc).date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("61000"),
                    legs=(
                        PositionLeg(
                            symbol="BTCUSDT",
                            quantity=Decimal("0.020"),
                            entry_price=Decimal("61100"),
                            stop_price=Decimal("61000"),
                            opened_at=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                            leg_type="restored",
                        ),
                    ),
                )
            },
        )
        market = {
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("60000"),
                latest_price=Decimal("61200"),
                previous_hour_low=Decimal("61000"),
                tradable=True,
                has_previous_hour_candle=True,
            )
        }
        open_orders = [
            {
                "symbol": "BTCUSDT",
                "orderType": "STOP_MARKET",
                "side": "SELL",
                "status": "NEW",
                "quantity": "0.010",
                "triggerPrice": "61000",
                "clientAlgoId": "ma_260415010000_BTCUSDT_a00s",
            }
        ]

        plan = build_stop_coverage_reconciliation_plan(state=state, market=market, open_orders=open_orders)

        self.assertEqual(plan, [("BTCUSDT", Decimal("61000"))])

    def test_build_stale_stop_reconciliation_plan_retries_stop_below_previous_hour_low(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.reconciliation import build_stale_stop_reconciliation_plan

        state = StrategyState(
            current_day=datetime(2026, 4, 15, tzinfo=timezone.utc).date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("60900"),
                    legs=(
                        PositionLeg(
                            symbol="BTCUSDT",
                            quantity=Decimal("0.010"),
                            entry_price=Decimal("61100"),
                            stop_price=Decimal("60900"),
                            opened_at=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                            leg_type="restored",
                        ),
                    ),
                )
            },
        )
        market = {
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("60000"),
                latest_price=Decimal("61200"),
                previous_hour_low=Decimal("61000"),
                tradable=True,
                has_previous_hour_candle=True,
            )
        }

        plan = build_stale_stop_reconciliation_plan(state=state, market=market)
        self.assertEqual(plan, [("BTCUSDT", Decimal("61000"))])

    def test_build_stale_stop_reconciliation_plan_skips_immediate_trigger_target(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState
        from momentum_alpha.reconciliation import build_stale_stop_reconciliation_plan

        state = StrategyState(
            current_day=datetime(2026, 4, 15, tzinfo=timezone.utc).date(),
            previous_leader_symbol="BTCUSDT",
            positions={
                "BTCUSDT": Position(
                    symbol="BTCUSDT",
                    stop_price=Decimal("60900"),
                    legs=(
                        PositionLeg(
                            symbol="BTCUSDT",
                            quantity=Decimal("0.010"),
                            entry_price=Decimal("61100"),
                            stop_price=Decimal("60900"),
                            opened_at=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                            leg_type="restored",
                        ),
                    ),
                )
            },
        )
        market = {
            "BTCUSDT": MarketSnapshot(
                symbol="BTCUSDT",
                daily_open_price=Decimal("60000"),
                latest_price=Decimal("60950"),
                previous_hour_low=Decimal("61000"),
                tradable=True,
                has_previous_hour_candle=True,
            )
        }

        plan = build_stale_stop_reconciliation_plan(state=state, market=market)
        self.assertEqual(plan, [])
