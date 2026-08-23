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
        self.assertTrue(callable(cli_commands_ops.rebuild_trade_analytics_command))
        self.assertTrue(callable(cli_commands_ops.prune_runtime_db_command))
        self.assertTrue(callable(cli_commands_ops.dashboard_command))

    def test_daily_report_writes_filtered_samples_separately_and_independently(self) -> None:
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
        self.assertTrue(replay_calls[0]["independent_candidate_replay"])
        self.assertNotIn("filtered_base_rows", daily_writes[0]["payload"])
        self.assertEqual(filtered_writes[0]["payload"]["summary"]["candidate_count"], 0)


if __name__ == "__main__":
    unittest.main()
