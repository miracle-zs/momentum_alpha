from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from dataclasses import dataclass
from momentum_alpha.orders import is_strategy_client_order_id
from momentum_alpha.state_store import StoredStrategyState, _deserialize_state, _serialize_state


MAX_PROCESSED_EVENT_ID_AGE_HOURS = 24


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
    ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type_timestamp
    ON audit_events(event_type, timestamp DESC);

CREATE TABLE IF NOT EXISTS signal_decisions (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    decision_type TEXT NOT NULL,
    symbol TEXT,
    previous_leader_symbol TEXT,
    next_leader_symbol TEXT,
    position_count INTEGER,
    order_status_count INTEGER,
    broker_response_count INTEGER,
    stop_replacement_count INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_timestamp
    ON signal_decisions(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_decision_type_timestamp
    ON signal_decisions(decision_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_signal_decisions_next_leader_timestamp
    ON signal_decisions(next_leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS broker_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    action_type TEXT NOT NULL,
    order_type TEXT,
    order_id TEXT,
    client_order_id TEXT,
    order_status TEXT,
    side TEXT,
    quantity REAL,
    price REAL,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_broker_orders_timestamp
    ON broker_orders(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_broker_orders_action_type_timestamp
    ON broker_orders(action_type, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_broker_orders_symbol_timestamp
    ON broker_orders(symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_fills (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    order_id TEXT,
    trade_id TEXT,
    client_order_id TEXT,
    order_status TEXT,
    execution_type TEXT,
    side TEXT,
    order_type TEXT,
    quantity TEXT,
    cumulative_quantity TEXT,
    average_price TEXT,
    last_price TEXT,
    realized_pnl TEXT,
    commission TEXT,
    commission_asset TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_fills_timestamp
    ON trade_fills(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_fills_symbol_timestamp
    ON trade_fills(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_trade_fills_trade_id
    ON trade_fills(trade_id);

CREATE TABLE IF NOT EXISTS algo_orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    symbol TEXT,
    algo_id TEXT,
    client_algo_id TEXT,
    algo_status TEXT,
    side TEXT,
    order_type TEXT,
    trigger_price TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_algo_orders_timestamp
    ON algo_orders(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_algo_orders_symbol_timestamp
    ON algo_orders(symbol, timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_algo_orders_algo_id
    ON algo_orders(algo_id);

CREATE TABLE IF NOT EXISTS account_flows (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    reason TEXT,
    asset TEXT,
    wallet_balance TEXT,
    cross_wallet_balance TEXT,
    balance_change TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_flows_timestamp
    ON account_flows(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_account_flows_reason_timestamp
    ON account_flows(reason, timestamp DESC);

CREATE TABLE IF NOT EXISTS trade_round_trips (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    round_trip_id TEXT NOT NULL,
    symbol TEXT NOT NULL,
    opened_at TEXT NOT NULL,
    closed_at TEXT NOT NULL,
    entry_fill_count INTEGER NOT NULL,
    exit_fill_count INTEGER NOT NULL,
    total_entry_quantity TEXT,
    total_exit_quantity TEXT,
    weighted_avg_entry_price TEXT,
    weighted_avg_exit_price TEXT,
    realized_pnl TEXT,
    commission TEXT,
    net_pnl TEXT,
    exit_reason TEXT,
    duration_seconds INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_trade_round_trips_closed_at
    ON trade_round_trips(closed_at DESC);
CREATE INDEX IF NOT EXISTS idx_trade_round_trips_symbol_closed_at
    ON trade_round_trips(symbol, closed_at DESC);
CREATE UNIQUE INDEX IF NOT EXISTS idx_trade_round_trips_round_trip_id
    ON trade_round_trips(round_trip_id);

CREATE TABLE IF NOT EXISTS stop_exit_summaries (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    symbol TEXT NOT NULL,
    round_trip_id TEXT NOT NULL,
    trigger_price TEXT,
    average_exit_price TEXT,
    slippage_abs TEXT,
    slippage_pct TEXT,
    exit_quantity TEXT,
    realized_pnl TEXT,
    commission TEXT,
    net_pnl TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_stop_exit_summaries_timestamp
    ON stop_exit_summaries(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_stop_exit_summaries_symbol_timestamp
    ON stop_exit_summaries(symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS position_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    leader_symbol TEXT,
    position_count INTEGER NOT NULL,
    order_status_count INTEGER NOT NULL,
    symbol_count INTEGER,
    submit_orders INTEGER,
    restore_positions INTEGER,
    execute_stop_replacements INTEGER,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_timestamp
    ON position_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_position_snapshots_leader_timestamp
    ON position_snapshots(leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS account_snapshots (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    source TEXT,
    wallet_balance TEXT,
    available_balance TEXT,
    equity TEXT,
    unrealized_pnl TEXT,
    position_count INTEGER NOT NULL,
    open_order_count INTEGER NOT NULL,
    leader_symbol TEXT,
    payload_json TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_timestamp
    ON account_snapshots(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_account_snapshots_leader_timestamp
    ON account_snapshots(leader_symbol, timestamp DESC);

CREATE TABLE IF NOT EXISTS strategy_state (
    id INTEGER PRIMARY KEY,
    payload_json TEXT NOT NULL
);
"""
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
        return _deserialize_state(json.loads(row[0]))

    def save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(_serialize_state(state)),),
            )

    def merge_save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = _deserialize_state(json.loads(row[0])) if row else None
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
                (_json_dumps(_serialize_state(merged)),),
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
            existing = _deserialize_state(json.loads(row[0])) if row else None
            new_state = updater(existing)
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(_serialize_state(new_state)),),
            )
            return new_state

def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(payload: str) -> dict:
    return json.loads(payload)


def _trade_round_trip_row_to_dict(row: tuple) -> dict:
    return {
        "round_trip_id": row[0],
        "symbol": row[1],
        "opened_at": row[2],
        "closed_at": row[3],
        "entry_fill_count": row[4],
        "exit_fill_count": row[5],
        "total_entry_quantity": row[6],
        "total_exit_quantity": row[7],
        "weighted_avg_entry_price": row[8],
        "weighted_avg_exit_price": row[9],
        "realized_pnl": row[10],
        "commission": row[11],
        "net_pnl": row[12],
        "exit_reason": row[13],
        "duration_seconds": row[14],
        "payload": _json_loads(row[15]),
    }


def _strategy_stop_client_order_id(client_order_id: str | None) -> str | None:
    if not is_strategy_client_order_id(client_order_id):
        return None
    if client_order_id is None:
        return None
    if client_order_id.endswith("s"):
        return client_order_id
    if not client_order_id.endswith("e"):
        return None
    return f"{client_order_id[:-1]}s"


def _trade_leg_type_from_client_order_id(client_order_id: str | None, leg_index: int) -> str:
    if is_strategy_client_order_id(client_order_id) and client_order_id is not None:
        token_index = len(client_order_id) - 4
        if token_index >= 0:
            token = client_order_id[token_index]
            if token == "b":
                return "base"
            if token == "a":
                return "add_on"
    return "base" if leg_index == 1 else "add_on"


def _build_trade_round_trip_leg_payload(
    *,
    entry_fills: list[dict],
    total_entry_qty: Decimal,
    realized_total: Decimal,
    commission_total: Decimal,
    stop_trigger_by_client_order_id: dict[str, Decimal],
) -> tuple[list[dict], Decimal | None, Decimal | None]:
    legs: list[dict] = []
    cumulative_risk = Decimal("0")
    all_leg_risks_known = True

    for leg_index, item in enumerate(entry_fills, start=1):
        client_order_id = item["client_order_id"]
        stop_client_order_id = _strategy_stop_client_order_id(client_order_id)
        stop_price_at_entry = (
            stop_trigger_by_client_order_id.get(stop_client_order_id) if stop_client_order_id is not None else None
        )
        leg_type = _trade_leg_type_from_client_order_id(client_order_id, leg_index)
        leg_risk = None
        if stop_price_at_entry is not None and item["price"] is not None:
            leg_risk = max((item["price"] - stop_price_at_entry) * item["quantity"], Decimal("0"))
        if leg_risk is None:
            all_leg_risks_known = False
            cumulative_risk_after_leg = None
        else:
            cumulative_risk += leg_risk
            cumulative_risk_after_leg = cumulative_risk if all_leg_risks_known else None

        quantity_share = item["quantity"] / total_entry_qty if total_entry_qty > Decimal("0") else None
        gross_pnl_contribution = realized_total * quantity_share if quantity_share is not None else None
        fee_share = commission_total * quantity_share if quantity_share is not None else None
        net_pnl_contribution = (
            gross_pnl_contribution - fee_share
            if gross_pnl_contribution is not None and fee_share is not None
            else None
        )

        legs.append(
            {
                "leg_index": leg_index,
                "leg_type": leg_type,
                "opened_at": item["timestamp"],
                "quantity": _decimal_to_text(item["quantity"]),
                "entry_price": _decimal_to_text(item["price"]),
                "stop_price_at_entry": _decimal_to_text(stop_price_at_entry),
                "leg_risk": _decimal_to_text(leg_risk),
                "cumulative_risk_after_leg": _decimal_to_text(cumulative_risk_after_leg),
                "gross_pnl_contribution": _decimal_to_text(gross_pnl_contribution),
                "fee_share": _decimal_to_text(fee_share),
                "net_pnl_contribution": _decimal_to_text(net_pnl_contribution),
            }
        )

    base_leg_risk = _text_to_decimal(legs[0]["leg_risk"]) if legs and legs[0]["leg_risk"] is not None else None
    peak_cumulative_risk = cumulative_risk if all_leg_risks_known and legs else None
    return legs, base_leg_risk, peak_cumulative_risk


def _resolve_stop_trigger_price_for_exit(
    *,
    exit_fills: list[dict],
    symbol: str,
    stop_trigger_by_client_order_id: dict[str, Decimal],
    algo_by_symbol: dict[str, list[dict]],
) -> Decimal | None:
    for exit_fill in reversed(exit_fills):
        stop_client_order_id = _strategy_stop_client_order_id(exit_fill["client_order_id"])
        if stop_client_order_id is None:
            continue
        trigger_price = stop_trigger_by_client_order_id.get(stop_client_order_id)
        if trigger_price is not None:
            return trigger_price
    for algo_row in reversed(algo_by_symbol.get(symbol, [])):
        if algo_row["timestamp"] <= exit_fills[-1]["timestamp"] and algo_row["order_type"] == "STOP_MARKET":
            trigger_price = algo_row["trigger_price"]
            if trigger_price is not None:
                return trigger_price
    return None


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _decimal_to_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _text_to_decimal(value: object | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _text_to_optional_decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


@contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        yield connection
        connection.commit()
    finally:
        connection.close()


def bootstrap_runtime_db(*, path: Path) -> None:
    with _connect(path) as connection:
        connection.executescript(SCHEMA)


def insert_audit_event(
    *,
    path: Path,
    timestamp: datetime,
    event_type: str,
    payload: dict,
    source: str | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO audit_events(timestamp, event_type, payload_json, source) VALUES (?, ?, ?, ?)",
            (_as_utc_iso(timestamp), event_type, _json_dumps(payload), source),
        )


def insert_signal_decision(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    decision_type: str,
    symbol: str | None = None,
    previous_leader_symbol: str | None = None,
    next_leader_symbol: str | None = None,
    position_count: int | None = None,
    order_status_count: int | None = None,
    broker_response_count: int | None = None,
    stop_replacement_count: int | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_decisions(
                timestamp,
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                _json_dumps(payload or {}),
            ),
        )


def insert_broker_order(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    action_type: str,
    order_type: str | None = None,
    symbol: str | None = None,
    order_id: str | None = None,
    client_order_id: str | None = None,
    order_status: str | None = None,
    status: str | None = None,
    side: str | None = None,
    quantity: float | None = None,
    price: float | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_order_status = order_status if order_status is not None else status
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO broker_orders(
                timestamp,
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                order_status,
                side,
                quantity,
                price,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                normalized_order_status,
                side,
                quantity,
                price,
                _json_dumps(payload or {}),
            ),
        )


def insert_trade_fill(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    symbol: str | None = None,
    order_id: str | None = None,
    trade_id: str | None = None,
    client_order_id: str | None = None,
    order_status: str | None = None,
    execution_type: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    quantity: object | None = None,
    cumulative_quantity: object | None = None,
    average_price: object | None = None,
    last_price: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    commission_asset: str | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO trade_fills(
                timestamp,
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                order_status,
                execution_type,
                side,
                order_type,
                quantity,
                cumulative_quantity,
                average_price,
                last_price,
                realized_pnl,
                commission,
                commission_asset,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                order_status,
                execution_type,
                side,
                order_type,
                _decimal_to_text(quantity),
                _decimal_to_text(cumulative_quantity),
                _decimal_to_text(average_price),
                _decimal_to_text(last_price),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                commission_asset,
                _json_dumps(payload or {}),
            ),
        )


def insert_algo_order(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    symbol: str | None = None,
    algo_id: str | None = None,
    client_algo_id: str | None = None,
    algo_status: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    trigger_price: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO algo_orders(
                timestamp,
                source,
                symbol,
                algo_id,
                client_algo_id,
                algo_status,
                side,
                order_type,
                trigger_price,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                algo_id,
                client_algo_id,
                algo_status,
                side,
                order_type,
                _decimal_to_text(trigger_price),
                _json_dumps(payload or {}),
            ),
        )


def insert_account_flow(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    reason: str | None = None,
    asset: str | None = None,
    wallet_balance: object | None = None,
    cross_wallet_balance: object | None = None,
    balance_change: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO account_flows(
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                reason,
                asset,
                _decimal_to_text(wallet_balance),
                _decimal_to_text(cross_wallet_balance),
                _decimal_to_text(balance_change),
                _json_dumps(payload or {}),
            ),
        )


def insert_trade_round_trip(
    *,
    path: Path,
    round_trip_id: str,
    symbol: str,
    opened_at: datetime,
    closed_at: datetime,
    entry_fill_count: int,
    exit_fill_count: int,
    total_entry_quantity: object | None = None,
    total_exit_quantity: object | None = None,
    weighted_avg_entry_price: object | None = None,
    weighted_avg_exit_price: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    net_pnl: object | None = None,
    exit_reason: str | None = None,
    duration_seconds: int | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO trade_round_trips(
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_trip_id,
                symbol,
                _as_utc_iso(opened_at),
                _as_utc_iso(closed_at),
                entry_fill_count,
                exit_fill_count,
                _decimal_to_text(total_entry_quantity),
                _decimal_to_text(total_exit_quantity),
                _decimal_to_text(weighted_avg_entry_price),
                _decimal_to_text(weighted_avg_exit_price),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                _decimal_to_text(net_pnl),
                exit_reason,
                duration_seconds,
                _json_dumps(payload or {}),
            ),
        )


def insert_stop_exit_summary(
    *,
    path: Path,
    timestamp: datetime,
    symbol: str,
    round_trip_id: str,
    trigger_price: object | None = None,
    average_exit_price: object | None = None,
    slippage_abs: object | None = None,
    slippage_pct: object | None = None,
    exit_quantity: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    net_pnl: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO stop_exit_summaries(
                timestamp,
                symbol,
                round_trip_id,
                trigger_price,
                average_exit_price,
                slippage_abs,
                slippage_pct,
                exit_quantity,
                realized_pnl,
                commission,
                net_pnl,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                symbol,
                round_trip_id,
                _decimal_to_text(trigger_price),
                _decimal_to_text(average_exit_price),
                _decimal_to_text(slippage_abs),
                _decimal_to_text(slippage_pct),
                _decimal_to_text(exit_quantity),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                _decimal_to_text(net_pnl),
                _json_dumps(payload or {}),
            ),
        )


def insert_position_snapshot(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    leader_symbol: str | None = None,
    previous_leader_symbol: str | None = None,
    position_count: int,
    order_status_count: int,
    symbol_count: int | None = None,
    submit_orders: bool | None = None,
    restore_positions: bool | None = None,
    execute_stop_replacements: bool | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_leader_symbol = leader_symbol if leader_symbol is not None else previous_leader_symbol
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO position_snapshots(
                timestamp,
                source,
                leader_symbol,
                position_count,
                order_status_count,
                symbol_count,
                submit_orders,
                restore_positions,
                execute_stop_replacements,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                normalized_leader_symbol,
                position_count,
                order_status_count,
                symbol_count,
                _bool_to_int(submit_orders),
                _bool_to_int(restore_positions),
                _bool_to_int(execute_stop_replacements),
                _json_dumps(payload or {}),
            ),
        )


def insert_account_snapshot(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    position_count: int,
    open_order_count: int,
    leader_symbol: str | None = None,
    wallet_balance: object | None = None,
    available_balance: object | None = None,
    equity: object | None = None,
    unrealized_pnl: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO account_snapshots(
                timestamp,
                source,
                wallet_balance,
                available_balance,
                equity,
                unrealized_pnl,
                position_count,
                open_order_count,
                leader_symbol,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                _decimal_to_text(wallet_balance),
                _decimal_to_text(available_balance),
                _decimal_to_text(equity),
                _decimal_to_text(unrealized_pnl),
                position_count,
                open_order_count,
                leader_symbol,
                _json_dumps(payload or {}),
            ),
        )


def fetch_recent_audit_events(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, event_type, payload_json, source
            FROM audit_events
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "event_type": row[1],
            "payload": _json_loads(row[2]),
            "source": row[3],
        }
        for row in rows
    ]


def fetch_audit_event_counts(*, path: Path, limit: int = 1000) -> dict[str, int]:
    if not path.exists():
        return {}
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT event_type, COUNT(*)
            FROM (
                SELECT event_type
                FROM audit_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            )
            GROUP BY event_type
            """,
            (limit,),
        ).fetchall()
    return {event_type: count for event_type, count in rows}


def fetch_recent_signal_decisions(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                payload_json
            FROM signal_decisions
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "decision_type": row[2],
            "symbol": row[3],
            "previous_leader_symbol": row[4],
            "next_leader_symbol": row[5],
            "position_count": row[6],
            "order_status_count": row[7],
            "broker_response_count": row[8],
            "stop_replacement_count": row[9],
            "payload": _json_loads(row[10]),
        }
        for row in rows
    ]


def fetch_recent_broker_orders(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                order_status,
                side,
                quantity,
                price,
                payload_json
            FROM broker_orders
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "action_type": row[3],
            "order_type": row[4],
            "order_id": row[5],
            "client_order_id": row[6],
            "order_status": row[7],
            "side": row[8],
            "quantity": row[9],
            "price": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]


def fetch_recent_trade_fills(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                order_status,
                execution_type,
                side,
                order_type,
                quantity,
                cumulative_quantity,
                average_price,
                last_price,
                realized_pnl,
                commission,
                commission_asset,
                payload_json
            FROM trade_fills
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "order_id": row[3],
            "trade_id": row[4],
            "client_order_id": row[5],
            "order_status": row[6],
            "execution_type": row[7],
            "side": row[8],
            "order_type": row[9],
            "quantity": row[10],
            "cumulative_quantity": row[11],
            "average_price": row[12],
            "last_price": row[13],
            "realized_pnl": row[14],
            "commission": row[15],
            "commission_asset": row[16],
            "payload": _json_loads(row[17]),
        }
        for row in rows
    ]


def fetch_recent_algo_orders(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                algo_id,
                client_algo_id,
                algo_status,
                side,
                order_type,
                trigger_price,
                payload_json
            FROM algo_orders
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "algo_id": row[3],
            "client_algo_id": row[4],
            "algo_status": row[5],
            "side": row[6],
            "order_type": row[7],
            "trigger_price": row[8],
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]


def fetch_recent_account_flows(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            FROM account_flows
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "reason": row[2],
            "asset": row[3],
            "wallet_balance": row[4],
            "cross_wallet_balance": row[5],
            "balance_change": row[6],
            "payload": _json_loads(row[7]),
        }
        for row in rows
    ]


def fetch_account_flows_since(*, path: Path, since: datetime) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            FROM account_flows
            WHERE timestamp >= ?
            ORDER BY timestamp DESC, id DESC
            """,
            (since.astimezone(timezone.utc).isoformat(),),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "reason": row[2],
            "asset": row[3],
            "wallet_balance": row[4],
            "cross_wallet_balance": row[5],
            "balance_change": row[6],
            "payload": _json_loads(row[7]),
        }
        for row in rows
    ]


def fetch_recent_trade_round_trips(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            ORDER BY closed_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_trade_round_trip_row_to_dict(row) for row in rows]


def fetch_trade_round_trips_for_range(*, path: Path, now: datetime, range_key: str) -> list[dict]:
    if not path.exists():
        return []
    window, _bucket_seconds = _ACCOUNT_RANGE_DENSITY.get(range_key, _ACCOUNT_RANGE_DENSITY["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "" if cutoff is None else "WHERE closed_at >= ?"
    params = () if cutoff is None else (cutoff.astimezone(timezone.utc).isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            {where_clause}
            ORDER BY closed_at DESC, id DESC
            """,
            params,
        ).fetchall()
    return [_trade_round_trip_row_to_dict(row) for row in rows]


def fetch_recent_stop_exit_summaries(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                symbol,
                round_trip_id,
                trigger_price,
                average_exit_price,
                slippage_abs,
                slippage_pct,
                exit_quantity,
                realized_pnl,
                commission,
                net_pnl,
                payload_json
            FROM stop_exit_summaries
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "symbol": row[1],
            "round_trip_id": row[2],
            "trigger_price": row[3],
            "average_exit_price": row[4],
            "slippage_abs": row[5],
            "slippage_pct": row[6],
            "exit_quantity": row[7],
            "realized_pnl": row[8],
            "commission": row[9],
            "net_pnl": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]


def rebuild_trade_analytics(*, path: Path) -> None:
    if not path.exists():
        return
    with _connect(path) as connection:
        fill_rows = connection.execute(
            """
            SELECT
                timestamp,
                symbol,
                side,
                order_type,
                quantity,
                average_price,
                last_price,
                realized_pnl,
                commission,
                commission_asset,
                order_id,
                trade_id,
                client_order_id
            FROM trade_fills
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        algo_rows = connection.execute(
            """
            SELECT timestamp, symbol, trigger_price, algo_status, order_type, client_algo_id
            FROM algo_orders
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        connection.execute("DELETE FROM trade_round_trips")
        connection.execute("DELETE FROM stop_exit_summaries")

        algo_by_symbol: dict[str, list[dict]] = {}
        stop_trigger_by_client_order_id: dict[str, Decimal] = {}
        for timestamp, symbol, trigger_price, algo_status, order_type, client_algo_id in algo_rows:
            if not symbol:
                continue
            parsed_trigger_price = _text_to_optional_decimal(trigger_price)
            algo_by_symbol.setdefault(symbol, []).append(
                {
                    "timestamp": timestamp,
                    "trigger_price": parsed_trigger_price,
                    "algo_status": algo_status,
                    "order_type": order_type,
                    "client_algo_id": client_algo_id,
                }
            )
            if client_algo_id and parsed_trigger_price is not None:
                stop_trigger_by_client_order_id[client_algo_id] = parsed_trigger_price

        active_round_trips: dict[str, dict] = {}
        symbol_counters: dict[str, int] = {}

        for (
            timestamp,
            symbol,
            side,
            order_type,
            quantity,
            average_price,
            last_price,
            realized_pnl,
            commission,
            commission_asset,
            order_id,
            trade_id,
            client_order_id,
        ) in fill_rows:
            if not symbol:
                continue
            qty = _text_to_decimal(quantity)
            if qty <= Decimal("0"):
                continue
            fill_time = datetime.fromisoformat(timestamp)
            fill_price = _text_to_decimal(average_price) or _text_to_decimal(last_price)
            fill_snapshot = {
                "timestamp": timestamp,
                "time": fill_time,
                "side": side,
                "order_type": order_type,
                "quantity": qty,
                "price": fill_price,
                "realized_pnl": _text_to_decimal(realized_pnl),
                "commission": _text_to_decimal(commission),
                "commission_asset": commission_asset,
                "order_id": order_id,
                "trade_id": trade_id,
                "client_order_id": client_order_id,
            }

            round_trip = active_round_trips.get(symbol)
            if side == "BUY":
                if round_trip is None or round_trip["net_quantity"] <= Decimal("0"):
                    sequence = symbol_counters.get(symbol, 0) + 1
                    symbol_counters[symbol] = sequence
                    round_trip = {
                        "round_trip_id": f"{symbol}:{sequence}",
                        "symbol": symbol,
                        "opened_at": fill_time,
                        "entry_fills": [],
                        "exit_fills": [],
                        "net_quantity": Decimal("0"),
                    }
                    active_round_trips[symbol] = round_trip
                round_trip["entry_fills"].append(fill_snapshot)
                round_trip["net_quantity"] += qty
                continue

            if side != "SELL" or round_trip is None:
                continue

            round_trip["exit_fills"].append(fill_snapshot)
            round_trip["net_quantity"] -= qty
            if round_trip["net_quantity"] > Decimal("0"):
                continue

            entry_fills = round_trip["entry_fills"]
            exit_fills = round_trip["exit_fills"]
            total_entry_qty = sum((item["quantity"] for item in entry_fills), Decimal("0"))
            total_exit_qty = sum((item["quantity"] for item in exit_fills), Decimal("0"))
            if total_entry_qty <= Decimal("0") or total_exit_qty <= Decimal("0"):
                active_round_trips.pop(symbol, None)
                continue
            weighted_entry = sum((item["quantity"] * item["price"] for item in entry_fills), Decimal("0")) / total_entry_qty
            weighted_exit = sum((item["quantity"] * item["price"] for item in exit_fills), Decimal("0")) / total_exit_qty
            realized_total = sum((item["realized_pnl"] for item in [*entry_fills, *exit_fills]), Decimal("0"))
            commission_total = sum((item["commission"] for item in [*entry_fills, *exit_fills]), Decimal("0"))
            net_total = realized_total - commission_total
            closed_at = exit_fills[-1]["time"]
            has_stop_market_exit = any(item["order_type"] == "STOP_MARKET" for item in exit_fills)
            has_strategy_stop_client_id = any(
                is_strategy_client_order_id(item["client_order_id"]) and str(item["client_order_id"]).endswith("s")
                for item in exit_fills
            )
            has_triggered_stop_algo = any(
                algo_row["timestamp"] <= exit_fills[-1]["timestamp"]
                and algo_row["order_type"] == "STOP_MARKET"
                and algo_row["algo_status"] == "TRIGGERED"
                and is_strategy_client_order_id(algo_row["client_algo_id"])
                for algo_row in algo_by_symbol.get(symbol, [])
            )
            exit_reason = (
                "stop_loss"
                if has_stop_market_exit or has_strategy_stop_client_id or has_triggered_stop_algo
                else "sell"
            )
            duration_seconds = int((closed_at - round_trip["opened_at"]).total_seconds())
            legs, base_leg_risk, peak_cumulative_risk = _build_trade_round_trip_leg_payload(
                entry_fills=entry_fills,
                total_entry_qty=total_entry_qty,
                realized_total=realized_total,
                commission_total=commission_total,
                stop_trigger_by_client_order_id=stop_trigger_by_client_order_id,
            )
            round_trip_payload = {
                "entry_order_ids": [item["order_id"] for item in entry_fills if item["order_id"] is not None],
                "exit_order_ids": [item["order_id"] for item in exit_fills if item["order_id"] is not None],
                "entry_trade_ids": [item["trade_id"] for item in entry_fills if item["trade_id"] is not None],
                "exit_trade_ids": [item["trade_id"] for item in exit_fills if item["trade_id"] is not None],
                "leg_count": len(legs),
                "add_on_leg_count": max(len(legs) - 1, 0),
                "base_leg_risk": _decimal_to_text(base_leg_risk),
                "peak_cumulative_risk": _decimal_to_text(peak_cumulative_risk),
                "legs": legs,
            }
            connection.execute(
                """
                INSERT INTO trade_round_trips(
                    round_trip_id,
                    symbol,
                    opened_at,
                    closed_at,
                    entry_fill_count,
                    exit_fill_count,
                    total_entry_quantity,
                    total_exit_quantity,
                    weighted_avg_entry_price,
                    weighted_avg_exit_price,
                    realized_pnl,
                    commission,
                    net_pnl,
                    exit_reason,
                    duration_seconds,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_trip["round_trip_id"],
                    symbol,
                    _as_utc_iso(round_trip["opened_at"]),
                    _as_utc_iso(closed_at),
                    len(entry_fills),
                    len(exit_fills),
                    _decimal_to_text(total_entry_qty),
                    _decimal_to_text(total_exit_qty),
                    _decimal_to_text(weighted_entry),
                    _decimal_to_text(weighted_exit),
                    _decimal_to_text(realized_total),
                    _decimal_to_text(commission_total),
                    _decimal_to_text(net_total),
                    exit_reason,
                    duration_seconds,
                    _json_dumps(round_trip_payload),
                ),
            )
            if exit_reason == "stop_loss":
                trigger_price = _resolve_stop_trigger_price_for_exit(
                    exit_fills=exit_fills,
                    symbol=symbol,
                    stop_trigger_by_client_order_id=stop_trigger_by_client_order_id,
                    algo_by_symbol=algo_by_symbol,
                )
                slippage_abs = None
                slippage_pct = None
                if trigger_price is not None and trigger_price > Decimal("0"):
                    slippage_abs = max(trigger_price - weighted_exit, Decimal("0"))
                    slippage_pct = (slippage_abs / trigger_price) * Decimal("100")
                connection.execute(
                    """
                    INSERT INTO stop_exit_summaries(
                        timestamp,
                        symbol,
                        round_trip_id,
                        trigger_price,
                        average_exit_price,
                        slippage_abs,
                        slippage_pct,
                        exit_quantity,
                        realized_pnl,
                        commission,
                        net_pnl,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _as_utc_iso(closed_at),
                        symbol,
                        round_trip["round_trip_id"],
                        _decimal_to_text(trigger_price),
                        _decimal_to_text(weighted_exit),
                        _decimal_to_text(slippage_abs),
                        _decimal_to_text(slippage_pct),
                        _decimal_to_text(total_exit_qty),
                        _decimal_to_text(realized_total),
                        _decimal_to_text(commission_total),
                        _decimal_to_text(net_total),
                        _json_dumps({"entry_fill_count": len(entry_fills), "exit_fill_count": len(exit_fills)}),
                    ),
                )
            active_round_trips.pop(symbol, None)


def fetch_recent_position_snapshots(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                leader_symbol,
                position_count,
                order_status_count,
                symbol_count,
                submit_orders,
                restore_positions,
                execute_stop_replacements,
                payload_json
            FROM position_snapshots
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "leader_symbol": row[2],
            "position_count": row[3],
            "order_status_count": row[4],
            "symbol_count": row[5],
            "submit_orders": bool(row[6]) if row[6] is not None else None,
            "restore_positions": bool(row[7]) if row[7] is not None else None,
            "execute_stop_replacements": bool(row[8]) if row[8] is not None else None,
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]


def fetch_recent_account_snapshots(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                wallet_balance,
                available_balance,
                equity,
                unrealized_pnl,
                position_count,
                open_order_count,
                leader_symbol,
                payload_json
            FROM account_snapshots
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "wallet_balance": row[2],
            "available_balance": row[3],
            "equity": row[4],
            "unrealized_pnl": row[5],
            "position_count": row[6],
            "open_order_count": row[7],
            "leader_symbol": row[8],
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]


_ACCOUNT_RANGE_DENSITY: dict[str, tuple[timedelta | None, int]] = {
    "1H": (timedelta(hours=1), 60),
    "1D": (timedelta(days=1), 5 * 60),
    "1W": (timedelta(days=7), 60 * 60),
    "1M": (timedelta(days=30), 4 * 60 * 60),
    "1Y": (timedelta(days=365), 24 * 60 * 60),
    "ALL": (None, 24 * 60 * 60),
}


def fetch_account_snapshots_for_range(
    *,
    path: Path,
    now: datetime,
    range_key: str,
) -> list[dict]:
    if not path.exists():
        return []
    window, bucket_seconds = _ACCOUNT_RANGE_DENSITY.get(range_key, _ACCOUNT_RANGE_DENSITY["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "" if cutoff is None else "WHERE timestamp >= ?"
    params = () if cutoff is None else (cutoff.isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                timestamp,
                source,
                wallet_balance,
                available_balance,
                equity,
                unrealized_pnl,
                position_count,
                open_order_count,
                leader_symbol,
                payload_json
            FROM (
                SELECT
                    id,
                    timestamp,
                    source,
                    wallet_balance,
                    available_balance,
                    equity,
                    unrealized_pnl,
                    position_count,
                    open_order_count,
                    leader_symbol,
                    payload_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(strftime('%s', timestamp) / ? AS INTEGER)
                        ORDER BY timestamp DESC, id DESC
                    ) AS rn
                FROM account_snapshots
                {where_clause}
            )
            WHERE rn = 1
            ORDER BY timestamp DESC, id DESC
            """,
            (bucket_seconds, *params),
        ).fetchall()
    return [
        {
            "timestamp": row[1],
            "source": row[2],
            "wallet_balance": row[3],
            "available_balance": row[4],
            "equity": row[5],
            "unrealized_pnl": row[6],
            "position_count": row[7],
            "open_order_count": row[8],
            "leader_symbol": row[9],
            "payload": _json_loads(row[10]),
        }
        for row in rows
    ]

def fetch_leader_history(*, path: Path, limit: int = 10) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, next_leader_symbol AS symbol, 1 AS priority
            FROM signal_decisions
            WHERE next_leader_symbol IS NOT NULL
            UNION ALL
            SELECT timestamp, leader_symbol AS symbol, 0 AS priority
            FROM position_snapshots
            WHERE leader_symbol IS NOT NULL
            ORDER BY timestamp DESC, priority DESC
            LIMIT ?
            """,
            (max(limit, 100),),
        ).fetchall()

    history: list[dict] = []
    previous_symbol: str | None = None
    for timestamp, symbol, _priority in rows:
        if symbol is None or symbol == previous_symbol:
            continue
        history.append({"timestamp": timestamp, "symbol": symbol})
        previous_symbol = symbol
        if len(history) >= limit:
            break
    return history


def fetch_event_pulse_points(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    bucket_minutes: int,
    limit: int = 20,
) -> list[dict]:
    if not path.exists():
        return []
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    bucket_seconds = max(bucket_minutes, 1) * 60
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp FROM signal_decisions WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM broker_orders WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM position_snapshots WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (
                cutoff.isoformat(),
                cutoff.isoformat(),
                cutoff.isoformat(),
            ),
        ).fetchall()

    counts: dict[str, int] = {}
    for (timestamp_text,) in rows:
        timestamp = datetime.fromisoformat(timestamp_text)
        bucket_start = cutoff + timedelta(
            seconds=int((timestamp - cutoff).total_seconds() // bucket_seconds) * bucket_seconds
        )
        bucket_label = bucket_start.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
        counts[bucket_label] = counts.get(bucket_label, 0) + 1

    return [
        {"bucket": bucket, "event_count": count}
        for bucket, count in sorted(counts.items())[-limit:]
    ]


def summarize_audit_events(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    limit: int,
) -> dict:
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    recent_events = [
        event
        for event in fetch_recent_audit_events(path=path, limit=max(limit, 500))
        if datetime.fromisoformat(event["timestamp"]) >= cutoff
    ]
    counts = Counter(event["event_type"] for event in recent_events)
    return {
        "total_events": len(recent_events),
        "counts": dict(sorted(counts.items())),
        "recent_events": recent_events[:limit],
    }
