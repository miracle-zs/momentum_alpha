import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class ConfigTests(unittest.TestCase):
    def test_default_strategy_config_matches_spec(self) -> None:
        from momentum_alpha.config import StrategyConfig

        config = StrategyConfig()
        self.assertEqual(config.stop_budget_usdt, Decimal("10"))
        self.assertEqual(config.entry_start_hour_utc, 1)
        self.assertEqual(config.entry_end_hour_utc, 23)
