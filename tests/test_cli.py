from __future__ import annotations

import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class CliTests(unittest.TestCase):
    def test_cli_module_exports_environment_and_entrypoint_helpers(self) -> None:
        from momentum_alpha import cli
        from momentum_alpha import cli_backfill, cli_backfill_candidates, cli_commands, cli_env, cli_parser
        from momentum_alpha import leader_opportunity_diagnostics

        self.assertTrue(callable(cli.cli_main))
        self.assertTrue(callable(cli.resolve_runtime_db_path))
        self.assertTrue(callable(cli.load_credentials_from_env))
        self.assertTrue(callable(cli.load_runtime_settings_from_env))
        self.assertTrue(callable(cli_env.resolve_runtime_db_path))
        self.assertTrue(callable(cli_env._build_client_from_factory))
        self.assertTrue(callable(cli_backfill.backfill_account_flows))
        self.assertTrue(callable(cli_backfill_candidates.backfill_leader_candidates))
        self.assertTrue(callable(cli.backfill_leader_candidates))
        self.assertTrue(callable(cli.diagnose_opportunities))
        self.assertTrue(callable(leader_opportunity_diagnostics.diagnose_opportunities))
        self.assertTrue(callable(cli_parser.build_cli_parser))
        self.assertTrue(callable(cli_commands.run_cli_command))

    def test_cli_parser_supports_diagnose_opportunities_defaults(self) -> None:
        from momentum_alpha.cli_parser import build_cli_parser

        args = build_cli_parser().parse_args(
            ["diagnose-opportunities", "--runtime-db-file", "/tmp/runtime.db"]
        )

        self.assertEqual(args.command, "diagnose-opportunities")
        self.assertEqual(args.output_file, "./local_analytics/opportunity_diagnostics.csv")
        self.assertEqual(args.min_peak_change_pct, Decimal("0"))

    def test_cli_parser_supports_skipped_base_replay_defaults(self) -> None:
        from momentum_alpha.cli_parser import build_cli_parser

        args = build_cli_parser().parse_args(
            ["replay-skipped-base", "--runtime-db-file", "/tmp/runtime.db"]
        )

        self.assertEqual(args.command, "replay-skipped-base")
        self.assertEqual(args.output_dir, "./local_analytics/skipped_base_replay")
        self.assertEqual(args.proxy, "http://127.0.0.1:7897")
        self.assertEqual(args.taker_fee_rate, Decimal("0.0005"))
        self.assertFalse(args.refresh_klines)


if __name__ == "__main__":
    unittest.main()
