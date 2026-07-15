from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.execution import apply_fill
from momentum_alpha.leg_semantics import infer_leg_type_from_client_order_id
from momentum_alpha.models import Position, PositionLeg, StrategyState
from momentum_alpha.orders import is_strategy_client_order_id

from .user_stream_events import (
    UserStreamEvent,
    _is_strategy_stop_fill,
    _is_strategy_stop_order_for_symbol,
    extract_flat_position_symbols,
    extract_positive_account_positions,
    resolve_stop_price_from_order_statuses,
)

def apply_user_stream_event_to_state(
    *,
    state: StrategyState,
    event: UserStreamEvent,
    order_statuses: dict[str, dict] | None = None,
) -> StrategyState:
    if event.event_type == "ACCOUNT_UPDATE":
        flat_symbols = extract_flat_position_symbols(event)
        positions = dict(state.positions)
        recent_stop_loss_exits = dict(state.recent_stop_loss_exits)

        # When a position goes flat, check if it's due to stop-loss trigger
        # and update recent_stop_loss_exits accordingly
        for symbol in flat_symbols:
            positions.pop(symbol, None)
            # Check if this symbol had a position before and if there's a stop order
            if symbol in state.positions and _is_strategy_stop_order_for_symbol(symbol, order_statuses):
                recent_stop_loss_exits[symbol] = event.event_time or datetime.now(timezone.utc)

        restored_at = event.event_time or datetime.now(timezone.utc)
        for symbol, quantity, entry_price in extract_positive_account_positions(event):
            existing_position = positions.get(symbol)
            resolved_stop_price = resolve_stop_price_from_order_statuses(symbol=symbol, order_statuses=order_statuses)
            stop_price = (
                resolved_stop_price
                if resolved_stop_price is not None
                else (existing_position.stop_price if existing_position is not None else Decimal("0"))
            )
            if existing_position is not None and quantity >= existing_position.total_quantity:
                positions[symbol] = (
                    existing_position
                    if existing_position.stop_price == stop_price
                    else existing_position.with_stop_price(stop_price)
                )
                continue
            leg_type = existing_position.legs[0].leg_type if existing_position is not None and existing_position.legs else "base"
            positions[symbol] = Position(
                symbol=symbol,
                stop_price=stop_price,
                legs=(
                    PositionLeg(
                        symbol=symbol,
                        quantity=quantity,
                        entry_price=entry_price,
                        stop_price=stop_price,
                        opened_at=restored_at,
                        leg_type=leg_type,
                        leg_source="account_update",
                    ),
                ),
            )
        if positions == state.positions and recent_stop_loss_exits == state.recent_stop_loss_exits:
            return state
        return replace(state, positions=positions, recent_stop_loss_exits=recent_stop_loss_exits)

    if event.event_type != "ORDER_TRADE_UPDATE" or event.symbol is None:
        return state

    fill_quantity = event.last_filled_quantity or event.filled_quantity
    if (
        event.execution_type == "TRADE"
        and event.side == "BUY"
        and is_strategy_client_order_id(event.client_order_id)
        and (event.last_filled_price is not None or event.average_price is not None)
        and fill_quantity is not None
        and fill_quantity > 0
    ):
        stop_price = event.stop_price if event.stop_price is not None else Decimal("0")
        filled_at = event.event_time or datetime.now(timezone.utc)
        return apply_fill(
            state=state,
            symbol=event.symbol,
            quantity=fill_quantity,
            entry_price=event.last_filled_price or event.average_price or Decimal("0"),
            stop_price=stop_price,
            leg_type=infer_leg_type_from_client_order_id(event.client_order_id) or "base",
            filled_at=filled_at,
            entry_order_id=event.client_order_id or (str(event.order_id) if event.order_id is not None else None),
            leg_source="user_stream",
            cumulative_quantity=event.filled_quantity,
            cumulative_average_price=event.average_price,
        )

    if event.order_status == "FILLED" and _is_strategy_stop_fill(event):
        positions = dict(state.positions)
        positions.pop(event.symbol, None)
        recent_stop_loss_exits = dict(state.recent_stop_loss_exits)
        recent_stop_loss_exits[event.symbol] = event.event_time or datetime.now(timezone.utc)
        return replace(state, positions=positions, recent_stop_loss_exits=recent_stop_loss_exits)

    return state
