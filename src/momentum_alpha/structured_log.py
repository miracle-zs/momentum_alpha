from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal
from typing import Callable


def _format_log_value(value: object) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, datetime):
        return value.astimezone(timezone.utc).isoformat()
    if isinstance(value, (int, float, Decimal)):
        return str(value)
    if isinstance(value, (list, tuple, dict)):
        return json.dumps(value, ensure_ascii=False, sort_keys=isinstance(value, dict), separators=(",", ":"))
    return str(value)


def format_structured_log(*, service: str, event: str, level: str = "INFO", **fields: object) -> str:
    parts = [f"service={service}", f"level={level}", f"event={event}"]
    for key, value in fields.items():
        if value is None:
            continue
        parts.append(f"{key}={_format_log_value(value)}")
    return " ".join(parts)


def emit_structured_log(
    logger: Callable[[str], None] | object,
    *,
    service: str,
    event: str,
    level: str = "INFO",
    **fields: object,
) -> None:
    line = format_structured_log(service=service, event=event, level=level, **fields)
    logger_method = level.lower()
    if hasattr(logger, logger_method):
        getattr(logger, logger_method)(line)
        return
    if hasattr(logger, "info"):
        getattr(logger, "info")(line)
        return
    logger(line)  # type: ignore[misc]
