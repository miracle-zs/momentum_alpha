from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime
from decimal import Decimal

from momentum_alpha.config import StrategyConfig
from momentum_alpha.execution import ExecutionPlan, build_execution_plan
from momentum_alpha.exchange_info import ExchangeSymbol
from momentum_alpha.models import MarketSnapshot
from momentum_alpha.models import StrategyState, TickDecision
from momentum_alpha.strategy import process_clock_tick


@dataclass(frozen=True)
class Runtime:
    market: dict[str, MarketSnapshot]
    exchange_symbols: dict[str, ExchangeSymbol]
    config: StrategyConfig

    def with_exchange_symbols(self, exchange_symbols: dict[str, ExchangeSymbol]) -> "Runtime":
        return replace(self, exchange_symbols=exchange_symbols)


@dataclass(frozen=True)
class RuntimeTickResult:
    decision: TickDecision
    execution_plan: ExecutionPlan
    next_state: StrategyState


def build_runtime(*, snapshots: list[dict]) -> Runtime:
    market = {
        snapshot["symbol"]: MarketSnapshot(
            symbol=snapshot["symbol"],
            daily_open_price=snapshot["daily_open_price"],
            latest_price=snapshot["latest_price"],
            previous_hour_low=snapshot["previous_hour_low"],
            tradable=snapshot["tradable"],
            has_previous_hour_candle=snapshot["has_previous_hour_candle"],
            current_hour_low=snapshot.get("current_hour_low", snapshot["previous_hour_low"]),
        )
        for snapshot in snapshots
    }
    return Runtime(
        market=market,
        exchange_symbols={},
        config=StrategyConfig(),
    )


def process_runtime_tick(
    *,
    runtime: Runtime,
    state: StrategyState,
    now: datetime,
) -> RuntimeTickResult:
    decision = process_clock_tick(now=now, state=state, market=runtime.market)
    execution_plan = build_execution_plan(
        symbols=runtime.exchange_symbols,
        market=runtime.market,
        decision=decision,
        stop_budget=Decimal(runtime.config.stop_budget_usdt),
        now=now,
    )
    next_state = replace(state, previous_leader_symbol=decision.new_previous_leader_symbol)
    return RuntimeTickResult(
        decision=decision,
        execution_plan=execution_plan,
        next_state=next_state,
    )
