from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso, _bool_to_int, _decimal_to_text, _json_dumps


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
