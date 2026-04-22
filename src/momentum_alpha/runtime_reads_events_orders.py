from __future__ import annotations

from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _json_loads


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
