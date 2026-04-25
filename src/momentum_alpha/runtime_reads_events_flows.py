from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _as_utc_iso, _json_loads


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


def fetch_account_flows_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
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
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC, id ASC
            """,
            (
                window_start.astimezone(timezone.utc).isoformat(),
                window_end.astimezone(timezone.utc).isoformat(),
            ),
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
