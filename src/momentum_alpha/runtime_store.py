from __future__ import annotations

import json
import sqlite3
from collections import Counter
from contextlib import contextmanager
from datetime import datetime, timedelta, timezone
from pathlib import Path

from dataclasses import dataclass
from momentum_alpha.state_store import StoredStrategyState, _deserialize_state, _serialize_state


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
            )
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(_serialize_state(merged)),),
            )

def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(payload: str) -> dict:
    return json.loads(payload)


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
