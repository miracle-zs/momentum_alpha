from __future__ import annotations

from datetime import datetime, timezone

from momentum_alpha.models import Position
from momentum_alpha.reconciliation import merge_position_history
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.runtime_state_merge import (
    position_has_leg_opened_after,
    position_has_newer_version,
)
from momentum_alpha.strategy_state_codec import StoredStrategyState


def _position_opened_after_exit(position: Position, exit_timestamp: str | None) -> bool:
    if exit_timestamp is None:
        return True
    try:
        exit_time = datetime.fromisoformat(exit_timestamp)
        return any(leg.opened_at > exit_time for leg in position.legs)
    except (TypeError, ValueError):
        # An unreadable marker must not cause a live position to be deleted.
        return True


def _parse_state_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _merge_latest_stop_loss_exits(
    existing: dict[str, str] | None,
    candidate: dict[str, str] | None,
) -> dict[str, str]:
    merged = dict(existing or {})
    for symbol, candidate_value in (candidate or {}).items():
        if symbol not in merged:
            merged[symbol] = candidate_value
            continue
        existing_time = _parse_state_timestamp(merged[symbol])
        candidate_time = _parse_state_timestamp(candidate_value)
        if existing_time is None and candidate_time is not None:
            merged[symbol] = candidate_value
        elif (
            existing_time is not None
            and candidate_time is not None
            and candidate_time >= existing_time
        ):
            merged[symbol] = candidate_value
    return merged


def _save_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
    removed_positions: dict[str, Position] | None = None,
    now: datetime | None = None,
) -> None:
    """Persist poll-owned state changes without clobbering newer stream fields."""

    def _updater(existing: StoredStrategyState | None) -> StoredStrategyState:
        existing_positions = {} if existing is None or existing.positions is None else dict(existing.positions)
        position_removal_timestamps = (
            {}
            if existing is None or existing.position_removal_timestamps is None
            else dict(existing.position_removal_timestamps)
        )
        for symbol, expected_position in (removed_positions or {}).items():
            current_position = existing_positions.get(symbol)
            if current_position is not None and not position_has_newer_version(
                current_position,
                expected_position,
            ):
                existing_positions.pop(symbol, None)
                if now is not None:
                    position_removal_timestamps[symbol] = now.astimezone(timezone.utc).isoformat()
        existing_recent_stop_loss_exits = (
            {} if existing is None or existing.recent_stop_loss_exits is None else dict(existing.recent_stop_loss_exits)
        )
        existing_recent_stop_loss_exits = _merge_latest_stop_loss_exits(
            existing_recent_stop_loss_exits,
            state.recent_stop_loss_exits,
        )
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
                removal_timestamp = position_removal_timestamps.get(symbol)
                if removal_timestamp is not None:
                    if not position_has_leg_opened_after(position, removal_timestamp):
                        continue
                    position_removal_timestamps.pop(symbol, None)
                if symbol not in recent_exits or _position_opened_after_exit(
                    position,
                    existing_recent_stop_loss_exits.get(symbol),
                ):
                    existing_positions[symbol] = merge_position_history(existing_positions.get(symbol), position)

        return StoredStrategyState(
            current_day=state.current_day,
            previous_leader_symbol=state.previous_leader_symbol,
            daily_base_signal_times=dict(state.daily_base_signal_times or {}),
            daily_base_signal_counts=dict(state.daily_base_signal_counts or {}),
            positions=existing_positions,
            processed_event_ids={} if existing is None or existing.processed_event_ids is None else existing.processed_event_ids,
            order_statuses={} if existing is None or existing.order_statuses is None else existing.order_statuses,
            recent_stop_loss_exits=existing_recent_stop_loss_exits,
            position_removal_timestamps=position_removal_timestamps,
            last_add_on_hour=(
                state.last_add_on_hour
                if state.last_add_on_hour is not None
                else (existing.last_add_on_hour if existing is not None else None)
            ),
        )

    runtime_state_store.atomic_update(_updater)
