from __future__ import annotations

from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_reads_common import _json_loads


def fetch_notification_status(*, path: Path, status_key: str) -> dict | None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM notification_statuses WHERE status_key = ?",
            (status_key,),
        ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "updated_at": row[1]}


def fetch_recent_audit_events(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, event_type, payload_json, source, decision_id, intent_id
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
            "payload": _json_loads(row[2]),
            "source": row[3],
            "decision_id": row[4],
            "intent_id": row[5],
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
