from __future__ import annotations

from datetime import datetime, timedelta
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso


DEFAULT_AUDIT_RETENTION_DAYS = 30
DEFAULT_SNAPSHOT_RETENTION_DAYS = 7


def _delete_older_than(*, connection, table_name: str, cutoff: datetime) -> int:
    row = connection.execute(
        f"DELETE FROM {table_name} WHERE timestamp < ?",
        (_as_utc_iso(cutoff),),
    )
    return row.rowcount or 0


def prune_runtime_db(
    *,
    path: Path,
    now: datetime,
    audit_retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS,
    snapshot_retention_days: int = DEFAULT_SNAPSHOT_RETENTION_DAYS,
) -> dict[str, object]:
    if not path.exists():
        return {
            "audit_cutoff": None,
            "snapshot_cutoff": None,
            "audit_events_deleted": 0,
            "position_snapshots_deleted": 0,
            "account_snapshots_deleted": 0,
        }

    bootstrap_runtime_db(path=path)
    audit_cutoff = now - timedelta(days=audit_retention_days)
    snapshot_cutoff = now - timedelta(days=snapshot_retention_days)

    with _connect(path) as connection:
        audit_events_deleted = _delete_older_than(
            connection=connection,
            table_name="audit_events",
            cutoff=audit_cutoff,
        )
        position_snapshots_deleted = _delete_older_than(
            connection=connection,
            table_name="position_snapshots",
            cutoff=snapshot_cutoff,
        )
        account_snapshots_deleted = _delete_older_than(
            connection=connection,
            table_name="account_snapshots",
            cutoff=snapshot_cutoff,
        )

    return {
        "audit_cutoff": _as_utc_iso(audit_cutoff),
        "snapshot_cutoff": _as_utc_iso(snapshot_cutoff),
        "audit_events_deleted": audit_events_deleted,
        "position_snapshots_deleted": position_snapshots_deleted,
        "account_snapshots_deleted": account_snapshots_deleted,
    }
