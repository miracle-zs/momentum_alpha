from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _as_utc_iso, _json_loads


def fetch_recent_signal_decisions(*, path: Path, limit: int = 20) -> list[dict]:
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
            "decision_id": row[2],
            "intent_id": row[3],
            "decision_type": row[4],
            "symbol": row[5],
            "previous_leader_symbol": row[6],
            "next_leader_symbol": row[7],
            "position_count": row[8],
            "order_status_count": row[9],
            "broker_response_count": row[10],
            "stop_replacement_count": row[11],
            "payload": _json_loads(row[12]),
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
            "decision_id": row[2],
            "intent_id": row[3],
            "decision_type": row[4],
            "symbol": row[5],
            "previous_leader_symbol": row[6],
            "next_leader_symbol": row[7],
            "position_count": row[8],
            "order_status_count": row[9],
            "broker_response_count": row[10],
            "stop_replacement_count": row[11],
            "payload": _json_loads(row[12]),
        }
        for row in rows
    ]
