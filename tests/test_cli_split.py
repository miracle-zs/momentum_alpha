from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from pathlib import Path
from tempfile import TemporaryDirectory
from types import SimpleNamespace


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class CliSplitTests(unittest.TestCase):
    def test_cli_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import cli_commands, cli_commands_live, cli_commands_ops, cli_commands_reports

        self.assertTrue(callable(cli_commands.run_cli_command))
        self.assertTrue(callable(cli_commands_live.run_live_commands))
        self.assertTrue(callable(cli_commands_live.run_once_live_command))
        self.assertTrue(callable(cli_commands_live.poll_command))
        self.assertTrue(callable(cli_commands_live.user_stream_command))
        self.assertTrue(callable(cli_commands_reports.run_reporting_commands))
        self.assertTrue(callable(cli_commands_reports.healthcheck_command))
        self.assertTrue(callable(cli_commands_reports.audit_report_command))
        self.assertTrue(callable(cli_commands_reports.daily_review_report_command))
        self.assertTrue(callable(cli_commands_ops.run_ops_commands))
        self.assertTrue(callable(cli_commands_ops.backfill_account_flows_command))
        self.assertTrue(callable(cli_commands_ops.sync_trade_data_command))
        self.assertTrue(callable(cli_commands_ops.request_live_resync_command))
        self.assertTrue(callable(cli_commands_ops.rebuild_trade_analytics_command))
        self.assertTrue(callable(cli_commands_ops.prune_runtime_db_command))
        self.assertTrue(callable(cli_commands_ops.dashboard_command))

    def test_daily_report_writes_filtered_samples_with_continuous_strategy_state(self) -> None:
        from momentum_alpha.cli_commands_reports import daily_review_report_command
        from momentum_alpha.cli_parser import build_cli_parser

        replay_calls: list[dict] = []
        daily_writes: list[dict] = []
        filtered_writes: list[dict] = []
        replay_report = SimpleNamespace(opportunities=(), warnings=(), had_fetch_errors=False)
        account = SimpleNamespace(
            income_total_pnl="0",
            trade_vs_income_delta="0",
        )
        daily_report = SimpleNamespace(
            report_date="2026-08-23",
            window_start="2026-08-22T08:30:00+08:00",
            window_end="2026-08-23T08:30:00+08:00",
            generated_at="2026-08-23T08:31:00+08:00",
            status="ok",
            trade_count=0,
            actual_total_pnl="0",
            counterfactual_total_pnl="0",
            pnl_delta="0",
            replayed_add_on_count=0,
            stop_budget_usdt="10",
            entry_start_hour_utc=1,
            entry_end_hour_utc=23,
            warnings=(),
            rows=(),
            account_reconciliation=account,
        )
        filtered_report = SimpleNamespace(
            report_date="2026-08-23",
            window_start="2026-08-22T08:30:00+08:00",
            window_end="2026-08-23T08:30:00+08:00",
            generated_at="2026-08-23T08:31:02+08:00",
            status="ok",
            warnings=(),
            summary={"candidate_count": 0, "closed_sample_pnl_sum": "0"},
            rows=(),
        )

        with TemporaryDirectory() as tmpdir:
            runtime_db = Path(tmpdir) / "runtime.db"
            runtime_db.touch()
            parser = build_cli_parser()
            args = parser.parse_args(
                [
                    "daily-review-report",
                    "--runtime-db-file",
                    str(runtime_db),
                    "--stop-budget-usdt",
                    "10",
                    "--entry-start-hour-utc",
                    "1",
                    "--entry-end-hour-utc",
                    "23",
                    "--replay-filtered-bases",
                ]
            )

            exit_code = daily_review_report_command(
                parser=parser,
                args=args,
                now_provider=lambda: datetime(2026, 8, 23, 1, 0, tzinfo=timezone.utc),
                build_daily_review_report_fn=lambda **_kwargs: daily_report,
                build_filtered_base_review_report_fn=lambda **kwargs: (
                    self.assertIs(kwargs["replay_report"], replay_report) or filtered_report
                ),
                insert_daily_review_report_fn=lambda **kwargs: daily_writes.append(kwargs),
                insert_filtered_base_review_report_fn=lambda **kwargs: filtered_writes.append(kwargs),
                replay_skipped_bases_fn=lambda **kwargs: replay_calls.append(kwargs) or replay_report,
            )

        self.assertEqual(exit_code, 0)
        self.assertFalse(replay_calls[0]["independent_candidate_replay"])
        self.assertTrue(replay_calls[0]["enforce_daily_base_limit"])
        self.assertNotIn("filtered_base_rows", daily_writes[0]["payload"])
        self.assertEqual(filtered_writes[0]["payload"]["summary"]["candidate_count"], 0)

    def test_refresh_open_filtered_report_finalizes_recent_historical_window(self) -> None:
        from decimal import Decimal

        from momentum_alpha.cli_commands_reports import refresh_open_filtered_base_reports
        from momentum_alpha.filtered_base_review import build_filtered_base_review_report
        from momentum_alpha.runtime_store import (
            bootstrap_runtime_db,
            fetch_filtered_base_review_report_by_date,
            insert_filtered_base_review_report,
            insert_signal_decision,
        )

        replay_calls: list[dict] = []
        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            output_dir = Path(tmpdir) / "replay"
            bootstrap_runtime_db(path=db_path)
            signal_at = datetime(2026, 8, 24, 23, 5, tzinfo=timezone.utc)
            window_start = datetime(2026, 8, 24, 8, 30, tzinfo=timezone.utc)
            window_end = datetime(2026, 8, 25, 0, 30, tzinfo=timezone.utc)
            insert_signal_decision(
                path=db_path,
                timestamp=signal_at,
                source="poll",
                decision_type="base_entry_skipped",
                symbol="TACUSDT",
                previous_leader_symbol="BTCUSDT",
                next_leader_symbol="TACUSDT",
                position_count=0,
                order_status_count=0,
                broker_response_count=0,
                stop_replacement_count=0,
                payload={
                    "blocked_reason": "base_veto",
                    "shadow_opportunity_id": "shadow-open",
                    "latest_price": "0.0021040",
                    "stop_price": "0.0020300",
                },
            )
            insert_signal_decision(
                path=db_path,
                timestamp=datetime(2026, 8, 24, 22, 0, tzinfo=timezone.utc),
                source="poll",
                decision_type="base_entry_skipped",
                symbol="OTHERUSDT",
                previous_leader_symbol="BTCUSDT",
                next_leader_symbol="OTHERUSDT",
                position_count=0,
                order_status_count=0,
                broker_response_count=0,
                stop_replacement_count=0,
                payload={
                    "blocked_reason": "base_veto",
                    "shadow_opportunity_id": "shadow-closed",
                    "latest_price": "1",
                    "stop_price": "0.95",
                },
            )
            insert_filtered_base_review_report(
                path=db_path,
                report_date="2026-08-25",
                window_start=window_start.isoformat(),
                window_end=window_end.isoformat(),
                generated_at="2026-08-25T00:31:00+00:00",
                status="ok",
                warnings=[],
                payload={
                    "summary": {
                        "candidate_count": 1,
                        "accepted_count": 1,
                        "closed_count": 0,
                        "open_count": 1,
                        "pending_count": 0,
                    },
                    "rows": [
                        {
                            "sample_id": "shadow-open",
                            "symbol": "TACUSDT",
                            "status": "open",
                            "mark_to_market_net_pnl": "16.60",
                        },
                        {
                            "sample_id": "shadow-closed",
                            "symbol": "OTHERUSDT",
                            "status": "closed",
                            "net_pnl": "-2",
                        },
                    ],
                },
            )
            replay_result = SimpleNamespace(
                shadow_opportunity_id="shadow-open",
                status="closed",
                base_entry_price=Decimal("0.0021040"),
                initial_stop_price=Decimal("0.0020300"),
                exit_at=datetime(2026, 8, 25, 1, 30, tzinfo=timezone.utc),
                exit_price=Decimal("0.0021570"),
                net_pnl=Decimal("1.33921359600"),
                mark_to_market_net_pnl=None,
                duration_minutes=Decimal("144.99"),
                add_on_count=1,
                warnings=(),
            )
            closed_result = SimpleNamespace(
                shadow_opportunity_id="shadow-closed",
                status="closed",
                base_entry_price=Decimal("1"),
                initial_stop_price=Decimal("0.95"),
                exit_at=datetime(2026, 8, 24, 23, 0, tzinfo=timezone.utc),
                exit_price=Decimal("0.98"),
                net_pnl=Decimal("-2"),
                mark_to_market_net_pnl=None,
                duration_minutes=Decimal("60"),
                add_on_count=0,
                warnings=(),
            )
            replay_report = SimpleNamespace(
                opportunities=(replay_result, closed_result),
                overlaps=(),
                suppressed=(),
                warnings=(),
                had_fetch_errors=False,
                replay_mode="continuous_strategy",
            )

            refreshed_dates = refresh_open_filtered_base_reports(
                path=db_path,
                now=datetime(2026, 8, 26, 0, 31, tzinfo=timezone.utc),
                current_report_date="2026-08-26",
                replay_output_dir=output_dir,
                replay_skipped_bases_fn=lambda **kwargs: replay_calls.append(kwargs) or replay_report,
                build_filtered_base_review_report_fn=build_filtered_base_review_report,
                insert_filtered_base_review_report_fn=insert_filtered_base_review_report,
            )
            refreshed = fetch_filtered_base_review_report_by_date(
                path=db_path,
                report_date="2026-08-25",
            )

        self.assertEqual(refreshed_dates, ["2026-08-25"])
        self.assertEqual(replay_calls[0]["seed_end_time"], window_end)
        self.assertEqual(replay_calls[0]["end_time"], datetime(2026, 8, 26, 0, 31, tzinfo=timezone.utc))
        self.assertEqual(replay_calls[0]["symbols"], ["OTHERUSDT", "TACUSDT"])
        self.assertEqual(refreshed["payload"]["summary"]["closed_count"], 2)
        self.assertEqual(
            {row["sample_id"] for row in refreshed["payload"]["rows"]},
            {"shadow-open", "shadow-closed"},
        )


if __name__ == "__main__":
    unittest.main()
