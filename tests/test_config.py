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

        for value in ("invalid", "0", "-1", "NaN", "Infinity", ""):
            with self.subTest(value=value), patch.dict("os.environ", {"STOP_BUDGET_USDT": value}):
                with self.assertRaisesRegex(ValueError, "STOP_BUDGET_USDT"):
                    StrategyConfig.from_env()

    def test_strategy_config_uses_default_stop_budget_when_environment_is_absent(self) -> None:
        from momentum_alpha.config import StrategyConfig

        with patch.dict("os.environ", {}, clear=True):
            config = StrategyConfig.from_env()

        self.assertEqual(config.stop_budget_usdt, Decimal("10"))
        self.assertEqual(config.taker_fee_rate, Decimal("0.0005"))

    def test_strategy_config_reads_taker_fee_rate_from_environment(self) -> None:
        from momentum_alpha.config import StrategyConfig

        with patch.dict("os.environ", {"TAKER_FEE_RATE": "0.0004"}, clear=True):
            config = StrategyConfig.from_env()

        self.assertEqual(config.taker_fee_rate, Decimal("0.0004"))

    def test_strategy_config_rejects_invalid_taker_fee_rate(self) -> None:
        from momentum_alpha.config import StrategyConfig

        for value in ("invalid", "-0.1", "NaN", "Infinity"):
            with self.subTest(value=value), patch.dict("os.environ", {"TAKER_FEE_RATE": value}, clear=True):
                with self.assertRaisesRegex(ValueError, "TAKER_FEE_RATE"):
                    StrategyConfig.from_env()

    def test_default_strategy_config_matches_spec(self) -> None:
        from momentum_alpha.config import StrategyConfig

        config = StrategyConfig()
        self.assertEqual(config.stop_budget_usdt, Decimal("10"))
        self.assertEqual(config.taker_fee_rate, Decimal("0.0005"))
        self.assertEqual(config.entry_start_hour_utc, 1)
        self.assertEqual(config.entry_end_hour_utc, 23)
        self.assertEqual(config.blocked_base_entry_hours_beijing, (9, 10))
        self.assertEqual(config.first_add_on_min_hold_minutes, 30)
        self.assertTrue(config.base_veto_enabled)
        self.assertEqual(config.base_veto_atr_15m_pct_threshold, Decimal("3"))
        self.assertEqual(config.base_veto_trade_count_ratio_30m_threshold, Decimal("1"))
        self.assertEqual(config.base_veto_return_to_vol_15m_threshold, Decimal("0.5"))

    def test_strategy_config_reads_base_veto_settings_from_environment(self) -> None:
        from momentum_alpha.config import StrategyConfig

        with patch.dict(
            "os.environ",
            {
                "BASE_VETO_ENABLED": "false",
                "BASE_VETO_ATR_15M_PCT_THRESHOLD": "3.2",
                "BASE_VETO_TRADE_COUNT_RATIO_30M_THRESHOLD": "0.9",
                "BASE_VETO_RETURN_TO_VOL_15M_THRESHOLD": "0.4",
            },
            clear=True,
        ):
            config = StrategyConfig.from_env()

        self.assertFalse(config.base_veto_enabled)
        self.assertEqual(config.base_veto_atr_15m_pct_threshold, Decimal("3.2"))
        self.assertEqual(config.base_veto_trade_count_ratio_30m_threshold, Decimal("0.9"))
        self.assertEqual(config.base_veto_return_to_vol_15m_threshold, Decimal("0.4"))
