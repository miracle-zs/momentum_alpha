from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os


@dataclass(frozen=True)
class StrategyConfig:
    stop_budget_usdt: Decimal = Decimal("10")
    taker_fee_rate: Decimal = Decimal("0.0005")
    entry_start_hour_utc: int = 1
    entry_end_hour_utc: int = 23
    blocked_base_entry_hours_beijing: tuple[int, ...] = (9, 10)
    first_add_on_min_hold_minutes: int = 30
    base_veto_enabled: bool = True
    base_veto_atr_15m_pct_threshold: Decimal = Decimal("3")
    base_veto_trade_count_ratio_30m_threshold: Decimal = Decimal("1")
    base_veto_return_to_vol_15m_threshold: Decimal = Decimal("0.5")

    @classmethod
    def from_env(cls) -> "StrategyConfig":
        raw_stop_budget = os.environ.get("STOP_BUDGET_USDT", str(cls.stop_budget_usdt))
        try:
            stop_budget = Decimal(raw_stop_budget.strip())
        except (ArithmeticError, ValueError):
            raise ValueError(
                f"STOP_BUDGET_USDT must be a positive finite decimal, got {raw_stop_budget!r}"
            ) from None
        if not stop_budget.is_finite() or stop_budget <= 0:
            raise ValueError(
                f"STOP_BUDGET_USDT must be a positive finite decimal, got {raw_stop_budget!r}"
            )

        raw_taker_fee_rate = os.environ.get("TAKER_FEE_RATE", str(cls.taker_fee_rate))
        try:
            taker_fee_rate = Decimal(raw_taker_fee_rate.strip())
        except (ArithmeticError, ValueError):
            raise ValueError(
                f"TAKER_FEE_RATE must be a finite non-negative decimal, got {raw_taker_fee_rate!r}"
            ) from None
        if not taker_fee_rate.is_finite() or taker_fee_rate < 0:
            raise ValueError(
                f"TAKER_FEE_RATE must be a finite non-negative decimal, got {raw_taker_fee_rate!r}"
            )

        def read_bool(name: str, default: bool) -> bool:
            raw_value = os.environ.get(name)
            if raw_value is None:
                return default
            normalized = raw_value.strip().lower()
            if normalized in {"1", "true", "yes", "on"}:
                return True
            if normalized in {"0", "false", "no", "off"}:
                return False
            raise ValueError(f"{name} must be a boolean, got {raw_value!r}")

        def read_decimal(name: str, default: Decimal) -> Decimal:
            raw_value = os.environ.get(name, str(default))
            try:
                value = Decimal(raw_value.strip())
            except (ArithmeticError, ValueError):
                raise ValueError(f"{name} must be a finite decimal, got {raw_value!r}") from None
            if not value.is_finite():
                raise ValueError(f"{name} must be a finite decimal, got {raw_value!r}")
            return value

        base_veto_atr_threshold = read_decimal(
            "BASE_VETO_ATR_15M_PCT_THRESHOLD",
            cls.base_veto_atr_15m_pct_threshold,
        )
        base_veto_trade_count_threshold = read_decimal(
            "BASE_VETO_TRADE_COUNT_RATIO_30M_THRESHOLD",
            cls.base_veto_trade_count_ratio_30m_threshold,
        )
        base_veto_return_to_vol_threshold = read_decimal(
            "BASE_VETO_RETURN_TO_VOL_15M_THRESHOLD",
            cls.base_veto_return_to_vol_15m_threshold,
        )
        if base_veto_atr_threshold < 0:
            raise ValueError("BASE_VETO_ATR_15M_PCT_THRESHOLD must be non-negative")
        if base_veto_trade_count_threshold < 0:
            raise ValueError("BASE_VETO_TRADE_COUNT_RATIO_30M_THRESHOLD must be non-negative")

        return cls(
            stop_budget_usdt=stop_budget,
            taker_fee_rate=taker_fee_rate,
            base_veto_enabled=read_bool("BASE_VETO_ENABLED", cls.base_veto_enabled),
            base_veto_atr_15m_pct_threshold=base_veto_atr_threshold,
            base_veto_trade_count_ratio_30m_threshold=base_veto_trade_count_threshold,
            base_veto_return_to_vol_15m_threshold=base_veto_return_to_vol_threshold,
        )
