from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from momentum_alpha.models import Position, PositionLeg


@dataclass(frozen=True)
class StoredStrategyState:
    current_day: str
    previous_leader_symbol: str | None
    positions: dict[str, Position] | None = None
    processed_event_ids: list[str] | None = None
    order_statuses: dict[str, dict] | None = None


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
            }
            for leg in position.legs
        ],
    }


def _deserialize_position(payload: dict) -> Position:
    legs = tuple(
        PositionLeg(
            symbol=leg["symbol"],
            quantity=Decimal(leg["quantity"]),
            entry_price=Decimal(leg["entry_price"]),
            stop_price=Decimal(leg["stop_price"]),
            opened_at=datetime.fromisoformat(leg["opened_at"]),
            leg_type=leg["leg_type"],
        )
        for leg in payload["legs"]
    )
    return Position(
        symbol=payload["symbol"],
        stop_price=Decimal(payload["stop_price"]),
        legs=legs,
    )


@dataclass(frozen=True)
class FileStateStore:
    path: Path

    def load(self) -> StoredStrategyState | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return StoredStrategyState(
            current_day=payload["current_day"],
            previous_leader_symbol=payload.get("previous_leader_symbol"),
            positions={
                symbol: _deserialize_position(position_payload)
                for symbol, position_payload in payload.get("positions", {}).items()
            },
            processed_event_ids=payload.get("processed_event_ids", []),
            order_statuses=payload.get("order_statuses", {}),
        )

    def save(self, state: StoredStrategyState) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "current_day": state.current_day,
            "previous_leader_symbol": state.previous_leader_symbol,
            "positions": {
                symbol: _serialize_position(position)
                for symbol, position in (state.positions or {}).items()
            },
            "processed_event_ids": list(state.processed_event_ids or []),
            "order_statuses": dict(state.order_statuses or {}),
        }
        self.path.write_text(json.dumps(payload), encoding="utf-8")

    def merge_save(self, state: StoredStrategyState) -> None:
        existing = self.load()
        merged = StoredStrategyState(
            current_day=state.current_day,
            previous_leader_symbol=state.previous_leader_symbol,
            positions=state.positions if state.positions is not None else (existing.positions if existing is not None else None),
            processed_event_ids=(
                state.processed_event_ids
                if state.processed_event_ids is not None
                else (existing.processed_event_ids if existing is not None else None)
            ),
            order_statuses=(
                state.order_statuses
                if state.order_statuses is not None
                else (existing.order_statuses if existing is not None else None)
            ),
        )
        self.save(merged)
