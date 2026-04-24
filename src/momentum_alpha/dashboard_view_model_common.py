from __future__ import annotations

from collections.abc import Mapping
from datetime import timedelta, timezone
from decimal import Decimal


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def _object_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)
