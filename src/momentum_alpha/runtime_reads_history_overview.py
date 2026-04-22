from __future__ import annotations

from collections import Counter
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_events import fetch_recent_audit_events


def fetch_leader_history(*, path: Path, limit: int = 10) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, next_leader_symbol AS symbol, 1 AS priority
            FROM signal_decisions
            WHERE next_leader_symbol IS NOT NULL
            UNION ALL
            SELECT timestamp, leader_symbol AS symbol, 0 AS priority
            FROM position_snapshots
            WHERE leader_symbol IS NOT NULL
            ORDER BY timestamp DESC, priority DESC
            LIMIT ?
            """,
            (max(limit, 100),),
        ).fetchall()

    history: list[dict] = []
    previous_symbol: str | None = None
    for timestamp, symbol, _priority in rows:
        if symbol is None or symbol == previous_symbol:
            continue
        history.append({"timestamp": timestamp, "symbol": symbol})
        previous_symbol = symbol
        if len(history) >= limit:
            break
    return history


def fetch_event_pulse_points(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    bucket_minutes: int,
    limit: int = 20,
) -> list[dict]:
    if not path.exists():
        return []
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    bucket_seconds = max(bucket_minutes, 1) * 60
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp FROM signal_decisions WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM broker_orders WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM position_snapshots WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (
                cutoff.isoformat(),
                cutoff.isoformat(),
                cutoff.isoformat(),
            ),
        ).fetchall()

    counts: dict[str, int] = {}
    for (timestamp_text,) in rows:
        timestamp = datetime.fromisoformat(timestamp_text)
        bucket_start = cutoff + timedelta(
            seconds=int((timestamp - cutoff).total_seconds() // bucket_seconds) * bucket_seconds
        )
        bucket_label = bucket_start.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
        counts[bucket_label] = counts.get(bucket_label, 0) + 1

    return [
        {"bucket": bucket, "event_count": count}
        for bucket, count in sorted(counts.items())[-limit:]
    ]


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
