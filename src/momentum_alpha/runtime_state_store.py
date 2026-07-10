from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db
from momentum_alpha.runtime_writes_common import _as_utc_iso, _decimal_to_text, _json_dumps
from momentum_alpha.strategy_state_codec import (
    StoredStrategyState,
    deserialize_strategy_state,
    serialize_strategy_state,
)
from momentum_alpha.trace_ids import build_intent_id_from_client_order_id


@dataclass(frozen=True)
class RuntimeStateStore:
    path: Path

    def load(self) -> StoredStrategyState | None:
        if not self.path.exists():
            return None
        with _connect(self.path) as connection:
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
        if not row:
            return None
        return deserialize_strategy_state(json.loads(row[0]))

    def save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(state)),),
            )

    def merge_save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = deserialize_strategy_state(json.loads(row[0])) if row else None
            merged = StoredStrategyState(
                current_day=state.current_day,
                previous_leader_symbol=state.previous_leader_symbol,
                daily_base_signal_times=(
                    state.daily_base_signal_times
                    if state.daily_base_signal_times is not None
                    else (existing.daily_base_signal_times if existing is not None else None)
                ),
                daily_base_signal_counts=(
                    state.daily_base_signal_counts
                    if state.daily_base_signal_counts is not None
                    else (existing.daily_base_signal_counts if existing is not None else None)
                ),
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
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(merged)),),
            )

    def atomic_update(
        self,
        updater: Callable[[StoredStrategyState | None], StoredStrategyState],
    ) -> StoredStrategyState:
        """Atomically update state within a single transaction.

        This method ensures that the read-modify-write operation is atomic,
        preventing race conditions between poll and user-stream processes.

        Args:
            updater: A function that takes the current state and returns the new state.
                     The function should merge its changes with the existing state.

        Returns:
            The new state after update.
        """
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = deserialize_strategy_state(json.loads(row[0])) if row else None
            new_state = updater(existing)
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(new_state)),),
            )
            return new_state

    def atomic_update_with_trade_fill(
        self,
        updater: Callable[[StoredStrategyState | None], StoredStrategyState],
        *,
        trade_fill: dict[str, Any],
    ) -> StoredStrategyState:
        """Persist one fill and its processed-event state in the same transaction."""

        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = deserialize_strategy_state(json.loads(row[0])) if row else None
            new_state = updater(existing)
            client_order_id = trade_fill.get("client_order_id")
            normalized_intent_id = trade_fill.get("intent_id") or build_intent_id_from_client_order_id(client_order_id)
            connection.execute(
                """
                INSERT OR IGNORE INTO trade_fills(
                    timestamp, source, symbol, order_id, trade_id, client_order_id,
                    decision_id, intent_id, order_status, execution_type, side,
                    order_type, quantity, cumulative_quantity, average_price,
                    last_price, realized_pnl, commission, commission_asset, payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    _as_utc_iso(trade_fill["timestamp"]),
                    trade_fill.get("source"),
                    trade_fill.get("symbol"),
                    trade_fill.get("order_id"),
                    trade_fill.get("trade_id"),
                    client_order_id,
                    trade_fill.get("decision_id"),
                    normalized_intent_id,
                    trade_fill.get("order_status"),
                    trade_fill.get("execution_type"),
                    trade_fill.get("side"),
                    trade_fill.get("order_type"),
                    _decimal_to_text(trade_fill.get("quantity")),
                    _decimal_to_text(trade_fill.get("cumulative_quantity")),
                    _decimal_to_text(trade_fill.get("average_price")),
                    _decimal_to_text(trade_fill.get("last_price")),
                    _decimal_to_text(trade_fill.get("realized_pnl")),
                    _decimal_to_text(trade_fill.get("commission")),
                    trade_fill.get("commission_asset"),
                    _json_dumps(trade_fill.get("payload") or {}),
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(new_state)),),
            )
            return new_state


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
