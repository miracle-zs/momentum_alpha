from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
import sqlite3

from momentum_alpha.runtime_schema import _connect, begin_immediate_with_retry, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso


DEFAULT_AUDIT_RETENTION_DAYS = 30
DEFAULT_SNAPSHOT_RETENTION_DAYS = 7


def _table_exists(connection: sqlite3.Connection, table_name: str, schema_prefix: str = "main") -> bool:
    row = connection.execute(
        f"SELECT 1 FROM {schema_prefix}.sqlite_master WHERE type = 'table' AND name = ?",
        (table_name,),
    ).fetchone()
    return row is not None


def backup_runtime_db(
    *,
    source_path: Path,
    backup_dir: Path | None = None,
    max_backups: int = 7,
    now: datetime | None = None,
) -> Path | None:
    """Create a point-in-time full SQLite snapshot using the online backup API."""
    if not source_path.exists():
        return None
    target_dir = backup_dir or (source_path.parent / "backups")
    target_dir.mkdir(parents=True, exist_ok=True)
    now_utc = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp_str = now_utc.strftime("%Y%m%d_%H%M%S")
    target_path = target_dir / f"{source_path.stem}_backup_{timestamp_str}.db"

    with _connect(source_path, readonly=True) as src_conn:
        dest_conn = sqlite3.connect(target_path)
        try:
            src_conn.backup(dest_conn)
        finally:
            dest_conn.close()

    # Rotate old backups keeping newest `max_backups`
    if max_backups > 0:
        existing_backups = sorted(
            target_dir.glob(f"{source_path.stem}_backup_*.db"),
            key=lambda p: p.stat().st_mtime,
        )
        if len(existing_backups) > max_backups:
            for old_backup in existing_backups[:-max_backups]:
                try:
                    old_backup.unlink()
                except OSError:
                    pass

    return target_path


def _archive_and_delete_older_than(
    *,
    connection: sqlite3.Connection,
    table_name: str,
    cutoff: datetime,
    time_column: str = "timestamp",
    has_archive: bool = False,
) -> tuple[int, int]:
    if not _table_exists(connection, table_name, schema_prefix="main"):
        return 0, 0

    cutoff_text = _as_utc_iso(cutoff)
    archived_count = 0

    if has_archive and _table_exists(connection, table_name, schema_prefix="archive_db"):
        # Atomically transfuse records into attached archive database
        archive_row = connection.execute(
            f"INSERT OR IGNORE INTO archive_db.{table_name} SELECT * FROM main.{table_name} WHERE {time_column} < ?",
            (cutoff_text,),
        )
        archived_count = archive_row.rowcount if archive_row.rowcount > 0 else 0

    del_row = connection.execute(
        f"DELETE FROM main.{table_name} WHERE {time_column} < ?",
        (cutoff_text,),
    )
    deleted_count = del_row.rowcount or 0
    return deleted_count, archived_count


def prune_runtime_db(
    *,
    path: Path,
    now: datetime,
    audit_retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS,
    snapshot_retention_days: int = DEFAULT_SNAPSHOT_RETENTION_DAYS,
    signal_decision_retention_days: int = DEFAULT_AUDIT_RETENTION_DAYS,
    live_series_retention_days: int = DEFAULT_SNAPSHOT_RETENTION_DAYS,
    archive_path: Path | None = None,
    backup_before_prune: bool = False,
    backup_dir: Path | None = None,
    max_backups: int = 7,
) -> dict[str, object]:
    if not path.exists():
        return {
            "backup_file": None,
            "archive_path": None,
            "audit_cutoff": None,
            "snapshot_cutoff": None,
            "signal_decision_cutoff": None,
            "live_series_cutoff": None,
            "audit_events_deleted": 0,
            "position_snapshots_deleted": 0,
            "account_snapshots_deleted": 0,
            "signal_decisions_deleted": 0,
            "live_series_deleted": 0,
            "total_archived": 0,
        }

    bootstrap_runtime_db(path=path)

    # 1. Take a hot snapshot backup if requested
    backup_file: Path | None = None
    if backup_before_prune:
        backup_file = backup_runtime_db(
            source_path=path,
            backup_dir=backup_dir,
            max_backups=max_backups,
            now=now,
        )

    # 2. Prepare archive database if specified
    has_archive = False
    resolved_archive_path: Path | None = None
    if archive_path is not None:
        resolved_archive_path = Path(archive_path).resolve()
        bootstrap_runtime_db(path=resolved_archive_path)
        has_archive = True

    audit_cutoff = now - timedelta(days=audit_retention_days)
    snapshot_cutoff = now - timedelta(days=snapshot_retention_days)
    signal_decision_cutoff = now - timedelta(days=signal_decision_retention_days)
    live_series_cutoff = now - timedelta(days=live_series_retention_days)

    total_archived = 0

    with _connect(path) as connection:
        if has_archive and resolved_archive_path is not None:
            connection.execute("ATTACH DATABASE ? AS archive_db", (str(resolved_archive_path),))

        try:
            begin_immediate_with_retry(connection)

            audit_del, audit_arch = _archive_and_delete_older_than(
                connection=connection,
                table_name="audit_events",
                cutoff=audit_cutoff,
                has_archive=has_archive,
            )
            pos_del, pos_arch = _archive_and_delete_older_than(
                connection=connection,
                table_name="position_snapshots",
                cutoff=snapshot_cutoff,
                has_archive=has_archive,
            )
            acct_del, acct_arch = _archive_and_delete_older_than(
                connection=connection,
                table_name="account_snapshots",
                cutoff=snapshot_cutoff,
                has_archive=has_archive,
            )
            sig_del, sig_arch = _archive_and_delete_older_than(
                connection=connection,
                table_name="signal_decisions",
                cutoff=signal_decision_cutoff,
                has_archive=has_archive,
            )
            live_del, live_arch = _archive_and_delete_older_than(
                connection=connection,
                table_name="dashboard_live_series",
                cutoff=live_series_cutoff,
                time_column="bucket_timestamp",
                has_archive=has_archive,
            )
            total_archived = audit_arch + pos_arch + acct_arch + sig_arch + live_arch
            connection.execute("PRAGMA optimize")
        finally:
            if has_archive:
                try:
                    connection.execute("DETACH DATABASE archive_db")
                except sqlite3.OperationalError:
                    pass

    return {
        "backup_file": str(backup_file) if backup_file else None,
        "archive_path": str(resolved_archive_path) if resolved_archive_path else None,
        "audit_cutoff": _as_utc_iso(audit_cutoff),
        "snapshot_cutoff": _as_utc_iso(snapshot_cutoff),
        "signal_decision_cutoff": _as_utc_iso(signal_decision_cutoff),
        "live_series_cutoff": _as_utc_iso(live_series_cutoff),
        "audit_events_deleted": audit_del,
        "position_snapshots_deleted": pos_del,
        "account_snapshots_deleted": acct_del,
        "signal_decisions_deleted": sig_del,
        "live_series_deleted": live_del,
        "total_archived": total_archived,
    }
