from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _ACCOUNT_RANGE_DENSITY, _as_utc_iso, _json_loads


def fetch_recent_position_snapshots(*, path: Path, limit: int = 20, require_positions: bool = False) -> list[dict]:
    if not path.exists():
        return []
    where_clause = "WHERE json_type(payload_json, '$.positions') IS NOT NULL" if require_positions else ""
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                timestamp,
                source,
                leader_symbol,
                decision_id,
                intent_id,
                position_count,
                order_status_count,
                symbol_count,
                submit_orders,
                restore_positions,
                execute_stop_replacements,
                payload_json
            FROM position_snapshots
            {where_clause}
            ORDER BY timestamp DESC, id DESC
            LIMIT :limit
            """,
            {"limit": limit},
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "leader_symbol": row[2],
            "decision_id": row[3],
            "intent_id": row[4],
            "position_count": row[5],
            "order_status_count": row[6],
            "symbol_count": row[7],
            "submit_orders": bool(row[8]) if row[8] is not None else None,
            "restore_positions": bool(row[9]) if row[9] is not None else None,
            "execute_stop_replacements": bool(row[10]) if row[10] is not None else None,
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]


def fetch_position_snapshots_for_range(
    *,
    path: Path,
    now: datetime,
    range_key: str,
    require_positions: bool = False,
) -> list[dict]:
    if not path.exists():
        return []
    window, bucket_seconds = _ACCOUNT_RANGE_DENSITY.get(range_key, _ACCOUNT_RANGE_DENSITY["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "WHERE json_type(payload_json, '$.positions') IS NOT NULL" if require_positions else ""
    if cutoff is not None:
        where_clause = f"{where_clause} {'AND' if where_clause else 'WHERE'} timestamp >= ?"
    params = () if cutoff is None else (cutoff.isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                timestamp,
                source,
                leader_symbol,
                decision_id,
                intent_id,
                position_count,
                order_status_count,
                symbol_count,
                submit_orders,
                restore_positions,
                execute_stop_replacements,
                payload_json
            FROM (
                SELECT
                    id,
                    timestamp,
                    source,
                    leader_symbol,
                    decision_id,
                    intent_id,
                    position_count,
                    order_status_count,
                    symbol_count,
                    submit_orders,
                    restore_positions,
                    execute_stop_replacements,
                    payload_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(strftime('%s', timestamp) / ? AS INTEGER)
                        ORDER BY timestamp DESC, id DESC
                    ) AS rn
                FROM position_snapshots
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
            "leader_symbol": row[3],
            "decision_id": row[4],
            "intent_id": row[5],
            "position_count": row[6],
            "order_status_count": row[7],
            "symbol_count": row[8],
            "submit_orders": bool(row[9]) if row[9] is not None else None,
            "restore_positions": bool(row[10]) if row[10] is not None else None,
            "execute_stop_replacements": bool(row[11]) if row[11] is not None else None,
            "payload": _json_loads(row[12]),
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
                decision_id,
                intent_id,
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
            "decision_id": row[2],
            "intent_id": row[3],
            "wallet_balance": row[4],
            "available_balance": row[5],
            "equity": row[6],
            "unrealized_pnl": row[7],
            "position_count": row[8],
            "open_order_count": row[9],
            "leader_symbol": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]


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
                decision_id,
                intent_id,
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
                    decision_id,
                    intent_id,
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
            "decision_id": row[3],
            "intent_id": row[4],
            "wallet_balance": row[5],
            "available_balance": row[6],
            "equity": row[7],
            "unrealized_pnl": row[8],
            "position_count": row[9],
            "open_order_count": row[10],
            "leader_symbol": row[11],
            "payload": _json_loads(row[12]),
        }
        for row in rows
    ]
