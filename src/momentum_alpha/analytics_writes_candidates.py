from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from momentum_alpha.analytics_schema import bootstrap_leader_candidates_db, connect_leader_candidates_db


_SOURCE_PRECEDENCE = {
    "position-snapshot-replay": 0,
    "poll": 1,
    "kline-backfill": 2,
}


def _as_utc_iso(value: datetime | str) -> str:
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    return value


def _json_dumps(value: dict | None) -> str:
    return json.dumps(value or {}, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _text_or_none(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _source_precedence(source: str | None) -> int:
    return _SOURCE_PRECEDENCE.get((source or "").strip(), 0)


def insert_leader_candidate_snapshots_bulk(*, path: Path, rows: Iterable[dict]) -> int:
    materialized_rows = list(rows)
    bootstrap_leader_candidates_db(path=path)
    changed = 0
    with connect_leader_candidates_db(path) as connection:
        for row in materialized_rows:
            timestamp = _as_utc_iso(row["timestamp"])
            source = str(row["source"])
            symbol = str(row["symbol"]).upper()
            rank = int(row["rank"])
            current = connection.execute(
                """
                SELECT source
                FROM leader_candidate_snapshots
                WHERE timestamp = ? AND symbol = ?
                """,
                (timestamp, symbol),
            ).fetchone()
            if current is not None and _source_precedence(source) < _source_precedence(current[0]):
                continue
            connection.execute(
                """
                DELETE FROM leader_candidate_snapshots
                WHERE timestamp = ? AND symbol = ?
                """,
                (timestamp, symbol),
            )
            connection.execute(
                """
                INSERT INTO leader_candidate_snapshots(
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
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    timestamp,
                    source,
                    symbol,
                    rank,
                    _text_or_none(row.get("daily_open_price")),
                    _text_or_none(row.get("latest_price")),
                    _text_or_none(row.get("daily_change_pct")),
                    _text_or_none(row.get("previous_hour_low")),
                    _text_or_none(row.get("current_hour_low")),
                    _text_or_none(row.get("leader_gap_pct")),
                    _json_dumps(row.get("payload")),
                ),
            )
            changed += 1
    return changed
