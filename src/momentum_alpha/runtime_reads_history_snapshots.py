from __future__ import annotations

from datetime import datetime, timezone, timedelta
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _ACCOUNT_RANGE_DENSITY, _as_utc_iso, _json_loads


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
