from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.analytics_schema import connect_leader_candidates_db


def _as_utc_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _row_to_dict(row: tuple) -> dict:
    return {
        "timestamp": row[0],
        "source": row[1],
        "symbol": row[2],
        "rank": row[3],
        "daily_open_price": row[4],
        "latest_price": row[5],
        "daily_change_pct": row[6],
        "previous_hour_low": row[7],
        "current_hour_low": row[8],
        "leader_gap_pct": row[9],
        "payload": _json_loads(row[10]),
    }


def fetch_leader_candidate_snapshots_for_window(
    *,
    path: Path,
    window_start: datetime,
    window_end: datetime,
) -> list[dict]:
    if not path.exists():
        return []
    with connect_leader_candidates_db(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                rank,
                daily_open_price,
                latest_price,
                daily_change_pct,
                previous_hour_low,
                current_hour_low,
                leader_gap_pct,
                payload_json
            FROM leader_candidate_snapshots
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp ASC, rank ASC, symbol ASC
            """,
            (_as_utc_iso(window_start), _as_utc_iso(window_end)),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]


def fetch_top_leader_candidates_for_window(
    *,
    path: Path,
    window_start: datetime,
    window_end: datetime,
    top_n: int,
) -> list[dict]:
    if not path.exists():
        return []
    with connect_leader_candidates_db(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                rank,
                daily_open_price,
                latest_price,
                daily_change_pct,
                previous_hour_low,
                current_hour_low,
                leader_gap_pct,
                payload_json
            FROM leader_candidate_snapshots
            WHERE timestamp >= ? AND timestamp < ? AND rank <= ?
            ORDER BY timestamp ASC, rank ASC, symbol ASC
            """,
            (_as_utc_iso(window_start), _as_utc_iso(window_end), top_n),
        ).fetchall()
    return [_row_to_dict(row) for row in rows]
