from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso


def save_notification_status(*, path: Path, status_key: str, status: str, timestamp: datetime) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO notification_statuses(status_key, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(status_key) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (status_key, status, _as_utc_iso(timestamp)),
        )
