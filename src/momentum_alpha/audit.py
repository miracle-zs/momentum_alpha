from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


def _coerce_json_value(value):
    if isinstance(value, dict):
        return {str(key): _coerce_json_value(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_coerce_json_value(item) for item in value]
    if isinstance(value, datetime):
        return value.isoformat()
    if hasattr(value, "isoformat") and callable(value.isoformat):
        try:
            return value.isoformat()
        except TypeError:
            pass
    return value


@dataclass(frozen=True)
class AuditRecorder:
    path: Path

    def record(self, *, event_type: str, now: datetime, payload: dict) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        event = {
            "timestamp": now.astimezone(timezone.utc).isoformat(),
            "event_type": event_type,
            "payload": _coerce_json_value(payload),
        }
        with self.path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False))
            handle.write("\n")


def read_audit_events(*, path: Path) -> list[dict]:
    if not path.exists():
        return []
    events: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        events.append(json.loads(line))
    return events


def summarize_audit_events(*, path: Path, now: datetime, since_minutes: int, limit: int) -> dict:
    events = read_audit_events(path=path)
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    filtered = [
        event
        for event in events
        if datetime.fromisoformat(event["timestamp"]) >= cutoff
    ]
    counts = Counter(event["event_type"] for event in filtered)
    recent_events = sorted(filtered, key=lambda item: item["timestamp"], reverse=True)[:limit]
    return {
        "total_events": len(filtered),
        "counts": dict(sorted(counts.items())),
        "recent_events": recent_events,
    }
