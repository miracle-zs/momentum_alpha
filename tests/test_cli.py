from __future__ import annotations

import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class CliTests(unittest.TestCase):
    def test_cli_module_exports_environment_and_entrypoint_helpers(self) -> None:
        from momentum_alpha import cli
        from momentum_alpha import cli_backfill, cli_commands, cli_env, cli_parser

        self.assertTrue(callable(cli.cli_main))
        self.assertTrue(callable(cli.resolve_runtime_db_path))
        self.assertTrue(callable(cli.load_credentials_from_env))
        self.assertTrue(callable(cli.load_runtime_settings_from_env))
        self.assertTrue(callable(cli_env.resolve_runtime_db_path))
        self.assertTrue(callable(cli_env._build_client_from_factory))
        self.assertTrue(callable(cli_backfill.backfill_account_flows))
        self.assertTrue(callable(cli_parser.build_cli_parser))
        self.assertTrue(callable(cli_commands.run_cli_command))


if __name__ == "__main__":
    unittest.main()
