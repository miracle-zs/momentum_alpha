from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_reads_common import _as_utc_iso, _json_loads

def fetch_notification_status(*, path: Path, status_key: str) -> dict | None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM notification_statuses WHERE status_key = ?",
            (status_key,),
        ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "updated_at": row[1]}
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
def fetch_signal_decisions_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
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
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp DESC, id DESC
            """,
            (
                _as_utc_iso(window_start),
                _as_utc_iso(window_end),
            ),
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
