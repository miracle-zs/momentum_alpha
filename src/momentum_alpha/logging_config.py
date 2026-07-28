from __future__ import annotations

import json
import logging
import os
import sys
import time
from datetime import datetime, timezone


class _JsonMessageFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
            "timestamp": datetime.fromtimestamp(record.created, tz=timezone.utc)
            .isoformat(timespec="milliseconds")
            .replace("+00:00", "Z"),
            "level": record.levelname,
            "logger": record.name,
            "message": record.getMessage(),
        }
        if record.exc_info is not None:
            payload["exception"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def configure_logging(*, level: str | None = None, log_format: str | None = None, stream=None) -> None:
    resolved_level_name = (level or os.environ.get("LOG_LEVEL", "INFO")).strip().upper()
    resolved_level = getattr(logging, resolved_level_name, logging.INFO)
    resolved_format = (log_format or os.environ.get("LOG_FORMAT", "kv")).strip().lower()

    handler = logging.StreamHandler(stream or sys.stderr)
    if resolved_format == "json":
        handler.setFormatter(_JsonMessageFormatter())
    else:
        formatter = logging.Formatter(
            "%(asctime)sZ %(message)s",
            datefmt="%Y-%m-%dT%H:%M:%S",
        )
        formatter.converter = time.gmtime
        handler.setFormatter(formatter)

    logging.basicConfig(level=resolved_level, handlers=[handler], force=True)
