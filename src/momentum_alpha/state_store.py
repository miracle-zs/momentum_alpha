from __future__ import annotations

import json
import os
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from pathlib import Path
from tempfile import NamedTemporaryFile

import fcntl

from momentum_alpha.models import Position, PositionLeg


@dataclass(frozen=True)
class StoredStrategyState:
    current_day: str
    previous_leader_symbol: str | None
    positions: dict[str, Position] | None = None
    processed_event_ids: list[str] | None = None
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


def _serialize_state(state: StoredStrategyState) -> dict:
    return {
        "current_day": state.current_day,
        "previous_leader_symbol": state.previous_leader_symbol,
        "positions": {
            symbol: _serialize_position(position)
            for symbol, position in (state.positions or {}).items()
        },
        "processed_event_ids": list(state.processed_event_ids or []),
        "order_statuses": dict(state.order_statuses or {}),
        "recent_stop_loss_exits": dict(state.recent_stop_loss_exits or {}),
    }


def _deserialize_state(payload: dict) -> StoredStrategyState:
    return StoredStrategyState(
        current_day=payload["current_day"],
        previous_leader_symbol=payload.get("previous_leader_symbol"),
        positions={
            symbol: _deserialize_position(position_payload)
            for symbol, position_payload in payload.get("positions", {}).items()
        },
        processed_event_ids=payload.get("processed_event_ids", []),
        order_statuses=payload.get("order_statuses", {}),
        recent_stop_loss_exits=payload.get("recent_stop_loss_exits", {}),
    )


@dataclass(frozen=True)
class FileStateStore:
    path: Path

    @property
    def _lock_path(self) -> Path:
        return self.path.with_name(f"{self.path.name}.lock")

    @contextmanager
    def _locked(self, *, exclusive: bool):
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self._lock_path.open("a+", encoding="utf-8") as lock_file:
            fcntl.flock(lock_file.fileno(), fcntl.LOCK_EX if exclusive else fcntl.LOCK_SH)
            try:
                yield
            finally:
                fcntl.flock(lock_file.fileno(), fcntl.LOCK_UN)

    def _load_unlocked(self) -> StoredStrategyState | None:
        if not self.path.exists():
            return None
        payload = json.loads(self.path.read_text(encoding="utf-8"))
        return _deserialize_state(payload)

    def _save_unlocked(self, state: StoredStrategyState) -> None:
        payload = _serialize_state(state)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with NamedTemporaryFile(
            mode="w",
            encoding="utf-8",
            dir=self.path.parent,
            prefix=f"{self.path.name}.",
            suffix=".tmp",
            delete=False,
        ) as tmp_file:
            json.dump(payload, tmp_file, ensure_ascii=False)
            temp_path = Path(tmp_file.name)
        os.replace(temp_path, self.path)

    def load(self) -> StoredStrategyState | None:
        with self._locked(exclusive=False):
            return self._load_unlocked()

    def save(self, state: StoredStrategyState) -> None:
        with self._locked(exclusive=True):
            self._save_unlocked(state)

    def merge_save(self, state: StoredStrategyState) -> None:
        with self._locked(exclusive=True):
            existing = self._load_unlocked()
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
                recent_stop_loss_exits=(
                    state.recent_stop_loss_exits
                    if state.recent_stop_loss_exits is not None
                    else (existing.recent_stop_loss_exits if existing is not None else None)
                ),
            )
            self._save_unlocked(merged)
