from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.execution import apply_fill
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
            if existing_position is not None and existing_position.total_quantity == quantity:
                positions[symbol] = (
                    existing_position
                    if existing_position.stop_price == stop_price
                    else existing_position.with_stop_price(stop_price)
                )
                continue
            leg_type = "account_update_synced" if existing_position is not None else "account_update_restored"
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
                    ),
                ),
            )
        if positions == state.positions and recent_stop_loss_exits == state.recent_stop_loss_exits:
            return state
        return replace(state, positions=positions, recent_stop_loss_exits=recent_stop_loss_exits)

    if event.event_type != "ORDER_TRADE_UPDATE" or event.order_status != "FILLED" or event.symbol is None:
        return state

    if event.side == "BUY" and event.average_price is not None and event.filled_quantity is not None:
        stop_price = event.stop_price if event.stop_price is not None else Decimal("0")
        filled_at = event.event_time or datetime.now(timezone.utc)
        return apply_fill(
            state=state,
            symbol=event.symbol,
            quantity=event.filled_quantity,
            entry_price=event.average_price,
            stop_price=stop_price,
            leg_type="stream_fill",
            filled_at=filled_at,
            entry_order_id=event.client_order_id or (str(event.order_id) if event.order_id is not None else None),
        )

    if _is_strategy_stop_fill(event):
        positions = dict(state.positions)
        positions.pop(event.symbol, None)
        recent_stop_loss_exits = dict(state.recent_stop_loss_exits)
        recent_stop_loss_exits[event.symbol] = event.event_time or datetime.now(timezone.utc)
        return replace(state, positions=positions, recent_stop_loss_exits=recent_stop_loss_exits)

    return state
