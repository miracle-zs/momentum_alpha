from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.leg_semantics import normalize_legacy_leg_source, normalize_legacy_leg_type
from momentum_alpha.models import Position, PositionLeg


@dataclass(frozen=True)
class StoredStrategyState:
    current_day: str
    previous_leader_symbol: str | None
    daily_base_signal_times: dict[str, str] | None = None
    daily_base_signal_counts: dict[str, int] | None = None
    positions: dict[str, Position] | None = None
    processed_event_ids: dict[str, str] | None = None  # {event_id: iso_timestamp}
    order_statuses: dict[str, dict] | None = None
    recent_stop_loss_exits: dict[str, str] | None = None


def _serialize_position(position: Position) -> dict:
    return {
        "symbol": position.symbol,
        "stop_price": str(position.stop_price),
        "legs": [
            {
                "symbol": leg.symbol,
                "quantity": str(leg.quantity),
                "entry_price": str(leg.entry_price),
                "stop_price": str(leg.stop_price),
                "opened_at": leg.opened_at.isoformat(),
                "leg_type": leg.leg_type,
                "entry_order_id": leg.entry_order_id,
                "leg_source": leg.leg_source,
            }
            for leg in position.legs
        ],
    }


def _deserialize_position(payload: dict) -> Position:
    legs = []
    for leg_index, leg in enumerate(payload["legs"]):
        raw_leg_type = leg.get("leg_type")
        entry_order_id = leg.get("entry_order_id")
        legs.append(
            PositionLeg(
                symbol=leg["symbol"],
                quantity=Decimal(leg["quantity"]),
                entry_price=Decimal(leg["entry_price"]),
                stop_price=Decimal(leg["stop_price"]),
                opened_at=datetime.fromisoformat(leg["opened_at"]),
                leg_type=normalize_legacy_leg_type(
                    raw_leg_type,
                    entry_order_id=entry_order_id,
                    leg_index=leg_index,
                ),
                entry_order_id=entry_order_id,
                leg_source=normalize_legacy_leg_source(raw_leg_type, leg.get("leg_source")),
            )
        )
    return Position(
        symbol=payload["symbol"],
        stop_price=Decimal(payload["stop_price"]),
        legs=tuple(legs),
    )


def serialize_strategy_state(state: StoredStrategyState) -> dict:
    return {
        "current_day": state.current_day,
        "previous_leader_symbol": state.previous_leader_symbol,
        "daily_base_signal_times": dict(state.daily_base_signal_times or {}),
        "daily_base_signal_counts": dict(state.daily_base_signal_counts or {}),
        "positions": {
            symbol: _serialize_position(position)
            for symbol, position in (state.positions or {}).items()
        },
        "processed_event_ids": dict(state.processed_event_ids or {}),
        "order_statuses": dict(state.order_statuses or {}),
        "recent_stop_loss_exits": dict(state.recent_stop_loss_exits or {}),
    }


def deserialize_strategy_state(payload: dict) -> StoredStrategyState:
    raw_event_ids = payload.get("processed_event_ids", [])
    if isinstance(raw_event_ids, list):
        processed_event_ids = {
            event_id: datetime.now(timezone.utc).isoformat()
            for event_id in raw_event_ids
        }
    else:
        processed_event_ids = dict(raw_event_ids)

    return StoredStrategyState(
        current_day=payload["current_day"],
        previous_leader_symbol=payload.get("previous_leader_symbol"),
        daily_base_signal_times=dict(payload.get("daily_base_signal_times", {})),
        daily_base_signal_counts={
            str(symbol): int(count)
            for symbol, count in payload.get("daily_base_signal_counts", {}).items()
        },
        positions={
            symbol: _deserialize_position(position_payload)
            for symbol, position_payload in payload.get("positions", {}).items()
        },
        processed_event_ids=processed_event_ids,
        order_statuses=payload.get("order_statuses", {}),
        recent_stop_loss_exits=payload.get("recent_stop_loss_exits", {}),
    )
