from __future__ import annotations

import json
from datetime import datetime, timezone


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _decimal_to_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)
