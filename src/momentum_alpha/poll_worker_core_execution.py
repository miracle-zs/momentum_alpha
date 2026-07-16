from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from decimal import Decimal

from momentum_alpha.broker import BinanceBroker
from momentum_alpha.config import StrategyConfig
from momentum_alpha.exchange_info import parse_exchange_info
from momentum_alpha.models import StrategyState
from momentum_alpha.runtime import Runtime, RuntimeTickResult, build_runtime, process_runtime_tick


@dataclass(frozen=True)
class RunOnceResult:
    runtime_result: RuntimeTickResult
    broker_responses: list[dict]
    stop_replacements: list[tuple[str, Decimal]]
    entry_order_failures: list[dict] = field(default_factory=list)
    stop_order_failures: list[dict] = field(default_factory=list)

    @property
    def execution_plan(self):
        return self.runtime_result.execution_plan


def build_runtime_from_snapshots(
    *,
    snapshots: list[dict],
    config: StrategyConfig | None = None,
) -> Runtime:
    return build_runtime(snapshots=snapshots, config=config)


def run_once(
    *,
    snapshots: list[dict],
    now: datetime,
    previous_leader_symbol: str | None,
    client,
    broker: BinanceBroker,
    submit_orders: bool,
    initial_state: StrategyState | None = None,
    exchange_symbols: dict | None = None,
    position_side: str | None = None,
    last_add_on_hour: int | None = None,
    strategy_config: StrategyConfig | None = None,
) -> RunOnceResult:
    runtime = build_runtime_from_snapshots(snapshots=snapshots, config=strategy_config).with_exchange_symbols(
        exchange_symbols if exchange_symbols is not None else parse_exchange_info(client.fetch_exchange_info())
    )
    state = initial_state or StrategyState(
        current_day=date(now.year, now.month, now.day),
        previous_leader_symbol=previous_leader_symbol,
        positions={},
        recent_stop_loss_exits={},
    )
    runtime_result = process_runtime_tick(
        runtime=runtime,
        state=state,
        now=now,
        position_side=position_side,
        last_add_on_hour=last_add_on_hour,
    )
    broker_responses = broker.submit_execution_plan(runtime_result.execution_plan) if submit_orders else []
    entry_order_failures = list(getattr(broker, "last_entry_order_failures", []) or []) if submit_orders else []
    stop_order_failures = list(getattr(broker, "last_stop_order_failures", []) or []) if submit_orders else []
    return RunOnceResult(
        runtime_result=runtime_result,
        broker_responses=broker_responses,
        stop_replacements=[],
        entry_order_failures=entry_order_failures,
        stop_order_failures=stop_order_failures,
    )
