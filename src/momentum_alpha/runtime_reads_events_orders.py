from __future__ import annotations

from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _json_loads
from .trace_ids import build_intent_id_from_client_order_id


def _row_to_order_linkage(row: tuple, *, matched_on: str) -> dict:
    return {
        "decision_id": row[0],
        "intent_id": row[1],
        "client_order_id": row[2],
        "client_algo_id": row[3],
        "order_id": row[4],
        "symbol": row[5],
        "timestamp": row[6],
        "matched_on": matched_on,
    }


def resolve_order_linkage(
    *,
    path: Path,
    client_order_id: str | None = None,
    client_algo_id: str | None = None,
    order_id: str | None = None,
) -> dict | None:
    if not path.exists():
        return None

    with _connect(path) as connection:
        lookup_candidates: list[tuple[str, str]] = []
        if client_order_id:
            lookup_candidates.append(("broker_orders.client_order_id", client_order_id))
            intent_id = build_intent_id_from_client_order_id(client_order_id)
            if intent_id is not None and intent_id != client_order_id:
                lookup_candidates.append(("broker_orders.intent_id", intent_id))
        if client_algo_id:
            lookup_candidates.append(("broker_orders.client_algo_id", client_algo_id))
            intent_id = build_intent_id_from_client_order_id(client_algo_id)
            if intent_id is not None and intent_id != client_algo_id:
                lookup_candidates.append(("broker_orders.intent_id", intent_id))
                lookup_candidates.append(("algo_orders.intent_id", intent_id))
        if order_id:
            lookup_candidates.append(("broker_orders.order_id", order_id))

        for column_name, value in lookup_candidates:
            table_name, bare_column_name = column_name.split(".", 1)
            row = connection.execute(
                f"""
                SELECT decision_id, intent_id, client_order_id, client_algo_id, order_id, symbol, timestamp
                FROM {table_name}
                WHERE {bare_column_name} = ?
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                (value,),
            ).fetchone()
            if row is not None:
                return _row_to_order_linkage(row, matched_on=column_name)

    return None


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
                client_algo_id,
                decision_id,
                intent_id,
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
            "client_algo_id": row[7],
            "decision_id": row[8],
            "intent_id": row[9],
            "order_status": row[10],
            "side": row[11],
            "quantity": row[12],
            "price": row[13],
            "payload": _json_loads(row[14]),
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
                decision_id,
                intent_id,
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
            "decision_id": row[6],
            "intent_id": row[7],
            "order_status": row[8],
            "execution_type": row[9],
            "side": row[10],
            "order_type": row[11],
            "quantity": row[12],
            "cumulative_quantity": row[13],
            "average_price": row[14],
            "last_price": row[15],
            "realized_pnl": row[16],
            "commission": row[17],
            "commission_asset": row[18],
            "payload": _json_loads(row[19]),
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
                decision_id,
                intent_id,
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
            "decision_id": row[5],
            "intent_id": row[6],
            "algo_status": row[7],
            "side": row[8],
            "order_type": row[9],
            "trigger_price": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]
