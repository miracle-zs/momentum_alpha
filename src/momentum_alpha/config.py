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
        return cls(stop_budget_usdt=stop_budget, taker_fee_rate=taker_fee_rate)
