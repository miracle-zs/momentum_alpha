from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso, _decimal_to_text, _json_dumps
from .trace_ids import build_intent_id_from_client_order_id


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
    client_algo_id: str | None = None,
    decision_id: str | None = None,
    intent_id: str | None = None,
    order_status: str | None = None,
    status: str | None = None,
    side: str | None = None,
    quantity: float | None = None,
    price: float | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_order_status = order_status if order_status is not None else status
    normalized_intent_id = intent_id or build_intent_id_from_client_order_id(client_order_id or client_algo_id)
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
                client_algo_id,
                decision_id,
                intent_id,
                order_status,
                side,
                quantity,
                price,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                client_algo_id,
                decision_id,
                normalized_intent_id,
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
    decision_id: str | None = None,
    intent_id: str | None = None,
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
    normalized_intent_id = intent_id or build_intent_id_from_client_order_id(client_order_id)
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                decision_id,
                normalized_intent_id,
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
    decision_id: str | None = None,
    intent_id: str | None = None,
    algo_status: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    trigger_price: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_intent_id = intent_id or build_intent_id_from_client_order_id(client_algo_id)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO algo_orders(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                algo_id,
                client_algo_id,
                decision_id,
                normalized_intent_id,
                algo_status,
                side,
                order_type,
                _decimal_to_text(trigger_price),
                _json_dumps(payload or {}),
            ),
        )
