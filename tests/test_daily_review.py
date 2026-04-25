import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DailyReviewTests(unittest.TestCase):
    def test_build_daily_review_window_anchors_to_0830_asia_shanghai(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_window

        window = build_daily_review_window(now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc))

        self.assertEqual(window.report_date, "2026-04-21")
        self.assertEqual(window.window_start.isoformat(), "2026-04-20T08:30:00+08:00")
        self.assertEqual(window.window_end.isoformat(), "2026-04-21T08:30:00+08:00")

    def test_build_daily_review_report_replays_skipped_add_ons(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_report
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_signal_decision, insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="BTCUSDT:1",
                symbol="BTCUSDT",
                opened_at=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="110",
                realized_pnl="10.00",
                commission="0.00",
                net_pnl="10.00",
                exit_reason="take_profit",
                duration_seconds=3 * 3600,
                payload={
                    "legs": [
                        {
                            "leg_index": 1,
                            "leg_type": "base",
                            "opened_at": "2026-04-20T09:00:00+08:00",
                            "quantity": "1",
                            "entry_price": "100",
                            "stop_price_at_entry": "95",
                            "leg_risk": "5",
                            "cumulative_risk_after_leg": "5",
                            "gross_pnl_contribution": "10",
                            "fee_share": "0",
                            "net_pnl_contribution": "10",
                        }
                    ]
                },
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
                source="poll",
                decision_type="add_on_skipped",
                symbol="BTCUSDT",
                previous_leader_symbol="BTCUSDT",
                next_leader_symbol="BTCUSDT",
                position_count=1,
                order_status_count=0,
                broker_response_count=0,
                stop_replacement_count=0,
                payload={
                    "latest_price": "105",
                    "stop_price": "95",
                    "step_size": "0.001",
                    "min_qty": "0.001",
                    "tick_size": "0.1",
                },
            )

            report = build_daily_review_report(
                path=db_path,
                now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc),
                stop_budget_usdt=Decimal("10"),
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
            )

        self.assertEqual(report.trade_count, 1)
        self.assertEqual(report.actual_total_pnl, "10.00")
        self.assertEqual(report.rows[0].symbol, "BTCUSDT")
        self.assertGreater(Decimal(report.counterfactual_total_pnl), Decimal(report.actual_total_pnl))
        self.assertEqual(report.replayed_add_on_count, 1)

    def test_build_daily_review_report_includes_account_reconciliation(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_report
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            insert_account_flow,
            insert_account_snapshot,
            insert_trade_round_trip,
        )

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="KATUSDT:1",
                symbol="KATUSDT",
                opened_at=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="58",
                realized_pnl="-42.00",
                commission="0.00",
                net_pnl="-42.00",
                exit_reason="stop_loss",
                duration_seconds=3 * 3600,
                payload={"legs": []},
            )
            insert_account_flow(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                source="backfill-income-history",
                reason="REALIZED_PNL",
                asset="USDT",
                balance_change="-120.00",
                payload={"incomeType": "REALIZED_PNL"},
            )
            insert_account_flow(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                source="backfill-income-history",
                reason="COMMISSION",
                asset="USDT",
                balance_change="-4.00",
                payload={"incomeType": "COMMISSION"},
            )
            insert_account_flow(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                source="backfill-income-history",
                reason="FUNDING_FEE",
                asset="USDT",
                balance_change="-1.00",
                payload={"incomeType": "FUNDING_FEE"},
            )
            insert_account_flow(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc),
                source="backfill-income-history",
                reason="TRANSFER",
                asset="USDT",
                balance_change="300.00",
                payload={"incomeType": "TRANSFER"},
            )
            insert_account_flow(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                source="user-stream",
                reason="ORDER",
                asset="USDT",
                balance_change="-125.00",
                payload={"m": "ORDER"},
            )
            insert_account_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 8, 31, tzinfo=timezone.utc),
                source="poll",
                wallet_balance="1000.00",
                available_balance="980.00",
                equity="1005.00",
                unrealized_pnl="5.00",
                position_count=1,
                open_order_count=1,
                payload={},
            )
            insert_account_snapshot(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 13, 0, tzinfo=timezone.utc),
                source="poll",
                wallet_balance="875.00",
                available_balance="870.00",
                equity="874.00",
                unrealized_pnl="-1.00",
                position_count=0,
                open_order_count=0,
                payload={},
            )

            report = build_daily_review_report(
                path=db_path,
                now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc),
                stop_budget_usdt=Decimal("10"),
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
            )

        reconciliation = report.account_reconciliation
        self.assertEqual(reconciliation.income_total_pnl, "-125.00")
        self.assertEqual(reconciliation.income_realized_pnl, "-120.00")
        self.assertEqual(reconciliation.income_commission, "-4.00")
        self.assertEqual(reconciliation.income_funding_fee, "-1.00")
        self.assertEqual(reconciliation.income_other, "0")
        self.assertEqual(reconciliation.income_transfer_total, "300.00")
        self.assertEqual(reconciliation.trade_vs_income_delta, "-83.00")
        self.assertEqual(reconciliation.wallet_balance_delta, "-125.00")
        self.assertEqual(reconciliation.equity_delta, "-131.00")

    def test_build_daily_review_report_sorts_rows_by_closed_at_descending(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_report
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="AAAUSDT:1",
                symbol="AAAUSDT",
                opened_at=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="100",
                weighted_avg_exit_price="110",
                realized_pnl="10.00",
                commission="0.00",
                net_pnl="10.00",
                exit_reason="take_profit",
                duration_seconds=3600,
                payload={"legs": []},
            )
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="BBBUSD:1",
                symbol="BBBUSD",
                opened_at=datetime(2026, 4, 20, 11, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 4, 20, 12, 0, tzinfo=timezone.utc),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="200",
                weighted_avg_exit_price="190",
                realized_pnl="-10.00",
                commission="0.00",
                net_pnl="-10.00",
                exit_reason="stop_loss",
                duration_seconds=3600,
                payload={"legs": []},
            )

            report = build_daily_review_report(
                path=db_path,
                now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc),
                stop_budget_usdt=Decimal("10"),
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
            )

        self.assertEqual([row.round_trip_id for row in report.rows], ["BBBUSD:1", "AAAUSDT:1"])

    def test_build_daily_review_report_warns_when_replay_inputs_are_missing(self) -> None:
        from momentum_alpha.daily_review import build_daily_review_report
        from momentum_alpha.runtime_store import bootstrap_runtime_db, insert_signal_decision, insert_trade_round_trip

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            bootstrap_runtime_db(path=db_path)
            insert_trade_round_trip(
                path=db_path,
                round_trip_id="ETHUSDT:1",
                symbol="ETHUSDT",
                opened_at=datetime(2026, 4, 20, 9, 0, tzinfo=timezone.utc),
                closed_at=datetime(2026, 4, 20, 10, 0, tzinfo=timezone.utc),
                entry_fill_count=1,
                exit_fill_count=1,
                total_entry_quantity="1",
                total_exit_quantity="1",
                weighted_avg_entry_price="200",
                weighted_avg_exit_price="190",
                realized_pnl="-10.00",
                commission="0.00",
                net_pnl="-10.00",
                exit_reason="stop_loss",
                duration_seconds=3600,
                payload={"legs": []},
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 4, 20, 9, 30, tzinfo=timezone.utc),
                source="poll",
                decision_type="add_on_skipped",
                symbol="ETHUSDT",
                previous_leader_symbol="ETHUSDT",
                next_leader_symbol="ETHUSDT",
                position_count=1,
                order_status_count=0,
                broker_response_count=0,
                stop_replacement_count=0,
                payload={"latest_price": "195", "stop_price": "185"},
            )

            report = build_daily_review_report(
                path=db_path,
                now=datetime(2026, 4, 21, 0, 31, tzinfo=timezone.utc),
                stop_budget_usdt=Decimal("10"),
                entry_start_hour_utc=1,
                entry_end_hour_utc=23,
            )

        self.assertTrue(report.warnings)
