from __future__ import annotations

import sys
import unittest
from pathlib import Path


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


if __name__ == "__main__":
    unittest.main()
