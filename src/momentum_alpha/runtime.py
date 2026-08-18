from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
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


def build_runtime(*, snapshots: list[dict], config: StrategyConfig | None = None) -> Runtime:
    market = {
        snapshot["symbol"]: MarketSnapshot(
            symbol=snapshot["symbol"],
            daily_open_price=snapshot["daily_open_price"],
            latest_price=snapshot["latest_price"],
            previous_hour_low=snapshot["previous_hour_low"],
            tradable=snapshot["tradable"],
            has_previous_hour_candle=snapshot["has_previous_hour_candle"],
            current_hour_low=snapshot.get("current_hour_low", snapshot["previous_hour_low"]),
            base_veto_features=snapshot.get("base_veto_features"),
        )
        for snapshot in snapshots
    }
    return Runtime(
        market=market,
        exchange_symbols={},
        config=config or StrategyConfig(),
    )


def process_runtime_tick(
    *,
    runtime: Runtime,
    state: StrategyState,
    now: datetime,
    position_side: str | None = None,
    last_add_on_hour: int | None = None,
) -> RuntimeTickResult:
    utc_day = now.astimezone(timezone.utc).date()
    normalized_state = state
    if state.current_day != utc_day:
        normalized_state = replace(
            state,
            current_day=utc_day,
            daily_base_signal_times={},
            daily_base_signal_counts={},
        )

    decision = process_clock_tick(
        now=now,
        state=normalized_state,
        market=runtime.market,
        last_add_on_hour=last_add_on_hour,
        entry_start_hour_utc=runtime.config.entry_start_hour_utc,
        entry_end_hour_utc=runtime.config.entry_end_hour_utc,
        blocked_base_entry_hours_beijing=runtime.config.blocked_base_entry_hours_beijing,
        first_add_on_min_hold_minutes=runtime.config.first_add_on_min_hold_minutes,
        stop_budget=Decimal(runtime.config.stop_budget_usdt),
        exchange_symbols=runtime.exchange_symbols,
        taker_fee_rate=Decimal(runtime.config.taker_fee_rate),
        base_veto_enabled=runtime.config.base_veto_enabled,
        base_veto_atr_15m_pct_threshold=Decimal(runtime.config.base_veto_atr_15m_pct_threshold),
        base_veto_trade_count_ratio_30m_threshold=Decimal(runtime.config.base_veto_trade_count_ratio_30m_threshold),
        base_veto_return_to_vol_15m_threshold=Decimal(runtime.config.base_veto_return_to_vol_15m_threshold),
    )
    execution_plan = build_execution_plan(
        symbols=runtime.exchange_symbols,
        market=runtime.market,
        decision=decision,
        stop_budget=Decimal(runtime.config.stop_budget_usdt),
        now=now,
        position_side=position_side,
    )
    next_state = replace(
        normalized_state,
        previous_leader_symbol=decision.new_previous_leader_symbol,
        daily_base_signal_times=decision.new_daily_base_signal_times,
        daily_base_signal_counts=decision.new_daily_base_signal_counts,
    )
    return RuntimeTickResult(
        decision=decision,
        execution_plan=execution_plan,
        next_state=next_state,
    )
