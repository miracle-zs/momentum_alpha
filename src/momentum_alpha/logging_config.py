from __future__ import annotations

import json
import logging
import os
import sys


class _JsonMessageFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload = {
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
        handler.setFormatter(logging.Formatter("%(message)s"))

    logging.basicConfig(level=resolved_level, handlers=[handler], force=True)

