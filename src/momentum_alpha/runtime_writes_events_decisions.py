from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso, _json_dumps


def insert_signal_decision(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    decision_id: str | None = None,
    intent_id: str | None = None,
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
                decision_id,
                intent_id,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                decision_id,
                intent_id,
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
