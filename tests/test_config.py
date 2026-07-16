import sys
import unittest
from decimal import Decimal
from unittest.mock import patch
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ConfigTests(unittest.TestCase):
    def test_strategy_config_reads_stop_budget_from_environment(self) -> None:
        from momentum_alpha.config import StrategyConfig

        with patch.dict("os.environ", {"STOP_BUDGET_USDT": "25"}):
            config = StrategyConfig.from_env()

        self.assertEqual(config.stop_budget_usdt, Decimal("25"))

    def test_strategy_config_rejects_invalid_or_non_positive_stop_budget(self) -> None:
        from momentum_alpha.config import StrategyConfig

        with patch.dict("os.environ", {"STOP_BUDGET_USDT": "invalid"}):
            self.assertEqual(StrategyConfig.from_env().stop_budget_usdt, Decimal("10"))
        with patch.dict("os.environ", {"STOP_BUDGET_USDT": "0"}):
            self.assertEqual(StrategyConfig.from_env().stop_budget_usdt, Decimal("10"))
    def test_default_strategy_config_matches_spec(self) -> None:
        from momentum_alpha.config import StrategyConfig

        config = StrategyConfig()
        self.assertEqual(config.stop_budget_usdt, Decimal("10"))
        self.assertEqual(config.entry_start_hour_utc, 1)
        self.assertEqual(config.entry_end_hour_utc, 23)
        self.assertEqual(config.blocked_base_entry_hour_beijing, 9)
        self.assertEqual(config.first_add_on_min_hold_minutes, 30)
