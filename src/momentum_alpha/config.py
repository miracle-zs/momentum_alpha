from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal
import os


@dataclass(frozen=True)
class StrategyConfig:
    stop_budget_usdt: Decimal = Decimal("10")
    entry_start_hour_utc: int = 1
    entry_end_hour_utc: int = 23
    blocked_base_entry_hour_beijing: int = 9
    first_add_on_min_hold_minutes: int = 30

    @classmethod
    def from_env(cls) -> "StrategyConfig":
        raw_stop_budget = os.environ.get("STOP_BUDGET_USDT")
        if raw_stop_budget is None:
            return cls()
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
        return cls(stop_budget_usdt=stop_budget)
