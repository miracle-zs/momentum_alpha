from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(payload: str) -> dict:
    return json.loads(payload)


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _decimal_to_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _text_to_decimal(value: object | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _text_to_optional_decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None
