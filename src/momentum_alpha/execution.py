from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.exchange_info import ExchangeSymbol
from momentum_alpha.models import EntryIntent, MarketSnapshot, Position, PositionLeg, StrategyState, TickDecision
from momentum_alpha.orders import build_client_order_id, build_market_entry_order, build_stop_market_order
from momentum_alpha.sizing import size_from_stop_budget


@dataclass(frozen=True)
class ExecutionPlan:
    entry_orders: list[dict[str, str]]
    stop_orders: list[dict[str, str]]


def _build_orders_for_intent(
    *,
    intent: EntryIntent,
    now: datetime,
    sequence: int,
    symbols: dict[str, ExchangeSymbol],
    market: dict[str, MarketSnapshot],
    stop_budget: Decimal,
    position_side: str | None,
) -> tuple[dict[str, str], dict[str, str]] | None:
    exchange_symbol = symbols.get(intent.symbol)
    snapshot = market.get(intent.symbol)
    if exchange_symbol is None or snapshot is None:
        return None

    quantity = size_from_stop_budget(
        entry_price=snapshot.latest_price,
        stop_price=intent.stop_price,
        stop_budget=stop_budget,
        filters=exchange_symbol.filters,
    )
    if quantity is None:
        return None

    opened_at = now.astimezone(timezone.utc)
    entry_order = build_market_entry_order(
        symbol=exchange_symbol,
        quantity=quantity,
        client_order_id=build_client_order_id(
            symbol=intent.symbol,
            opened_at=opened_at,
            leg_type=intent.leg_type,
            order_kind="entry",
            sequence=sequence,
        ),
        position_side=position_side,
    )
    stop_order = build_stop_market_order(
        symbol=exchange_symbol,
        quantity=quantity,
        stop_price=intent.stop_price,
        client_order_id=build_client_order_id(
            symbol=intent.symbol,
            opened_at=opened_at,
            leg_type=intent.leg_type,
            order_kind="stop",
            sequence=sequence,
        ),
        position_side=position_side,
    )
    return entry_order, stop_order


def build_execution_plan(
    *,
    symbols: dict[str, ExchangeSymbol],
    market: dict[str, MarketSnapshot],
    decision: TickDecision,
    stop_budget: Decimal,
    now: datetime,
    position_side: str | None = None,
) -> ExecutionPlan:
    entry_orders: list[dict[str, str]] = []
    stop_orders: list[dict[str, str]] = []
    intents = [*decision.base_entries, *decision.add_on_entries]
    for sequence, intent in enumerate(intents):
        built = _build_orders_for_intent(
            intent=intent,
            now=now,
            sequence=sequence,
            symbols=symbols,
            market=market,
            stop_budget=stop_budget,
            position_side=position_side,
        )
        if built is None:
            continue
        entry_order, stop_order = built
        entry_orders.append(entry_order)
        stop_orders.append(stop_order)
    return ExecutionPlan(entry_orders=entry_orders, stop_orders=stop_orders)


def build_stop_replacements(*, decision: TickDecision) -> list[tuple[str, Decimal]]:
    return sorted(decision.updated_stop_prices.items())


def apply_fill(
    *,
    state: StrategyState,
    symbol: str,
    quantity: Decimal,
    entry_price: Decimal,
    stop_price: Decimal,
    leg_type: str,
    filled_at: datetime,
    entry_order_id: str | None = None,
    new_previous_leader_symbol: str | None = None,
) -> StrategyState:
    positions = dict(state.positions)
    position = positions.get(symbol)
    new_leg = PositionLeg(
        symbol=symbol,
        quantity=quantity,
        entry_price=entry_price,
        stop_price=stop_price,
        opened_at=filled_at,
        leg_type=leg_type,
        entry_order_id=entry_order_id,
    )

    if position is None:
        positions[symbol] = Position(symbol=symbol, stop_price=stop_price, legs=(new_leg,))
    else:
        updated_legs = list(position.with_stop_price(stop_price).legs)
        last_leg = updated_legs[-1] if updated_legs else None
        if (
            last_leg is not None
            and last_leg.entry_order_id is not None
            and entry_order_id is not None
            and last_leg.entry_order_id == entry_order_id
            and last_leg.leg_type == leg_type
        ):
            merged_quantity = last_leg.quantity + quantity
            merged_entry_price = (
                (last_leg.entry_price * last_leg.quantity) + (entry_price * quantity)
            ) / merged_quantity
            updated_legs[-1] = replace(
                last_leg,
                quantity=merged_quantity,
                entry_price=merged_entry_price,
                stop_price=stop_price,
            )
        else:
            updated_legs.append(new_leg)
        positions[symbol] = Position(symbol=symbol, stop_price=stop_price, legs=tuple(updated_legs))

    return replace(
        state,
        previous_leader_symbol=new_previous_leader_symbol if new_previous_leader_symbol is not None else state.previous_leader_symbol,
        positions=positions,
    )
