from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal


@dataclass(frozen=True)
class StrategyConfig:
    stop_budget_usdt: Decimal = Decimal("10")
    entry_start_hour_utc: int = 1
    entry_end_hour_utc: int = 23
