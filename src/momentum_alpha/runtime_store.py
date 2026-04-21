from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

from momentum_alpha.runtime_analytics import rebuild_trade_analytics
from momentum_alpha.runtime_reads import (
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_audit_event_counts,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_latest_daily_review_report,
    fetch_notification_status,
    fetch_recent_account_flows,
    fetch_recent_account_snapshots,
    fetch_recent_audit_events,
    fetch_recent_broker_orders,
    fetch_recent_algo_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_recent_trade_round_trips,
    fetch_signal_decisions_for_window,
    fetch_trade_round_trips_for_range,
    fetch_trade_round_trips_for_window,
    summarize_audit_events,
)
from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db
from momentum_alpha.runtime_writes import (
    insert_account_flow,
    insert_account_snapshot,
    insert_audit_event,
    insert_algo_order,
    insert_broker_order,
    insert_daily_review_report,
    insert_position_snapshot,
    insert_signal_decision,
    insert_stop_exit_summary,
    insert_trade_fill,
    insert_trade_round_trip,
    save_notification_status,
)
from momentum_alpha.strategy_state_codec import (
    StoredStrategyState,
    deserialize_strategy_state,
    serialize_strategy_state,
)


MAX_PROCESSED_EVENT_ID_AGE_HOURS = 24


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
        updater: "Callable[[StoredStrategyState | None], StoredStrategyState]",
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

def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)
