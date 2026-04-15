from __future__ import annotations

import json
import sqlite3
from contextlib import contextmanager
from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path


SCHEMA = """
CREATE TABLE IF NOT EXISTS audit_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT
);
CREATE INDEX IF NOT EXISTS idx_audit_events_timestamp
    ON audit_events(timestamp DESC);
CREATE INDEX IF NOT EXISTS idx_audit_events_event_type_timestamp
    ON audit_events(event_type, timestamp DESC);
"""


@contextmanager
def _connect(path: Path):
    path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(path)
    try:
        connection.execute("PRAGMA journal_mode=WAL")
        connection.execute("PRAGMA synchronous=NORMAL")
        yield connection
        connection.commit()
    finally:
        connection.close()


def bootstrap_runtime_db(*, path: Path) -> None:
    with _connect(path) as connection:
        connection.executescript(SCHEMA)


def insert_audit_event(
    *,
    path: Path,
    timestamp: datetime,
    event_type: str,
    payload: dict,
    source: str | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO audit_events(timestamp, event_type, payload_json, source) VALUES (?, ?, ?, ?)",
            (
                timestamp.astimezone(timezone.utc).isoformat(),
                event_type,
                json.dumps(payload, ensure_ascii=False),
                source,
            ),
        )


def fetch_recent_audit_events(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, event_type, payload_json, source
            FROM audit_events
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "event_type": row[1],
            "payload": json.loads(row[2]),
            "source": row[3],
        }
        for row in rows
    ]


def fetch_audit_event_counts(*, path: Path, limit: int = 1000) -> dict[str, int]:
    if not path.exists():
        return {}
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT event_type, COUNT(*)
            FROM (
                SELECT event_type
                FROM audit_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            )
            GROUP BY event_type
            """,
            (limit,),
        ).fetchall()
    return {event_type: count for event_type, count in rows}


def summarize_audit_events(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    limit: int,
) -> dict:
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    recent_events = [
        event
        for event in fetch_recent_audit_events(path=path, limit=max(limit, 500))
        if datetime.fromisoformat(event["timestamp"]) >= cutoff
    ]
    counts = Counter(event["event_type"] for event in recent_events)
    return {
        "total_events": len(recent_events),
        "counts": dict(sorted(counts.items())),
        "recent_events": recent_events[:limit],
    }
