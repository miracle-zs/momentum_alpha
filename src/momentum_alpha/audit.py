from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable

from .runtime_store import insert_audit_event


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
    runtime_db_path: Path
    source: str | None = None
    db_insert_fn: Callable = insert_audit_event

    def record(self, *, event_type: str, now: datetime, payload: dict) -> None:
        try:
            self.db_insert_fn(
                path=self.runtime_db_path,
                timestamp=now.astimezone(timezone.utc),
                event_type=event_type,
                payload=_coerce_json_value(payload),
                source=self.source,
            )
        except Exception:
            pass
