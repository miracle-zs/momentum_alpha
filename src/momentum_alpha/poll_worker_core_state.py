from __future__ import annotations

from datetime import datetime

from momentum_alpha.models import Position
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.strategy_state_codec import StoredStrategyState


def _position_opened_after_exit(position: Position, exit_timestamp: str | None) -> bool:
    if exit_timestamp is None:
        return True
    try:
        exit_time = datetime.fromisoformat(exit_timestamp)
        return any(leg.opened_at > exit_time for leg in position.legs)
    except (TypeError, ValueError):
        return False


def _save_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
) -> None:
    """Persist poll-owned state changes without clobbering newer stream fields."""

    def _updater(existing: StoredStrategyState | None) -> StoredStrategyState:
        existing_positions = {} if existing is None or existing.positions is None else dict(existing.positions)
        existing_recent_stop_loss_exits = (
            {} if existing is None or existing.recent_stop_loss_exits is None else dict(existing.recent_stop_loss_exits)
        )
        if state.recent_stop_loss_exits is not None:
            existing_recent_stop_loss_exits.update(state.recent_stop_loss_exits)
        recent_exits = set(existing_recent_stop_loss_exits.keys())

        for symbol in recent_exits:
            existing_position = existing_positions.get(symbol)
            if existing_position is not None and not _position_opened_after_exit(
                existing_position,
                existing_recent_stop_loss_exits.get(symbol),
            ):
                existing_positions.pop(symbol, None)

        if state.positions is not None:
            for symbol, position in state.positions.items():
                if symbol not in recent_exits or _position_opened_after_exit(
                    position,
                    existing_recent_stop_loss_exits.get(symbol),
                ):
                    existing_positions[symbol] = position

        return StoredStrategyState(
            current_day=state.current_day,
            previous_leader_symbol=state.previous_leader_symbol,
            positions=existing_positions,
            processed_event_ids={} if existing is None or existing.processed_event_ids is None else existing.processed_event_ids,
            order_statuses={} if existing is None or existing.order_statuses is None else existing.order_statuses,
            recent_stop_loss_exits=existing_recent_stop_loss_exits,
        )

    runtime_state_store.atomic_update(_updater)
