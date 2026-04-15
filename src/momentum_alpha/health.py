from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
import sqlite3


@dataclass(frozen=True)
class HealthCheckItem:
    name: str
    status: str
    message: str


@dataclass(frozen=True)
class RuntimeHealthReport:
    items: list[HealthCheckItem]

    @property
    def overall_status(self) -> str:
        if any(item.status == "FAIL" for item in self.items):
            return "FAIL"
        if any(item.status == "WARN" and item.name != "audit_log" for item in self.items):
            return "WARN"
        return "OK"


def _check_file_freshness(*, name: str, path: Path, now: datetime, max_age_seconds: int) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem(name=name, status="FAIL", message=f"missing path={path}")
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - path.stat().st_mtime)
    if age_seconds > max_age_seconds:
        return HealthCheckItem(
            name=name,
            status="FAIL",
            message=f"stale path={path} age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name=name, status="OK", message=f"fresh path={path} age_seconds={age_seconds}")


def _check_runtime_db_freshness(*, path: Path, now: datetime, max_age_seconds: int) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem(name="runtime_db", status="FAIL", message=f"missing path={path}")
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                "SELECT timestamp FROM audit_events ORDER BY timestamp DESC, id DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return HealthCheckItem(name="runtime_db", status="FAIL", message=f"invalid path={path} error={exc}")
    if row is None or not row[0]:
        return HealthCheckItem(name="runtime_db", status="WARN", message=f"empty path={path}")
    latest_timestamp = datetime.fromisoformat(row[0]).astimezone(timezone.utc)
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - latest_timestamp.timestamp())
    if age_seconds > max_age_seconds:
        return HealthCheckItem(
            name="runtime_db",
            status="FAIL",
            message=f"stale path={path} age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name="runtime_db", status="OK", message=f"fresh path={path} age_seconds={age_seconds}")


def build_runtime_health_report(
    *,
    now: datetime,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    runtime_db_file: Path | None = None,
    audit_log_file: Path | None = None,
    max_state_age_seconds: int = 3600,
    max_poll_log_age_seconds: int = 180,
    max_user_stream_log_age_seconds: int = 1800,
    max_runtime_db_age_seconds: int = 1800,
    max_audit_log_age_seconds: int = 1800,
) -> RuntimeHealthReport:
    items = [
        _check_file_freshness(name="state_file", path=state_file, now=now, max_age_seconds=max_state_age_seconds),
        _check_file_freshness(name="poll_log", path=poll_log_file, now=now, max_age_seconds=max_poll_log_age_seconds),
        _check_file_freshness(
            name="user_stream_log",
            path=user_stream_log_file,
            now=now,
            max_age_seconds=max_user_stream_log_age_seconds,
        ),
    ]
    if runtime_db_file is not None:
        items.append(
            _check_runtime_db_freshness(path=runtime_db_file, now=now, max_age_seconds=max_runtime_db_age_seconds)
        )
    if audit_log_file is not None:
        audit_item = _check_file_freshness(
            name="audit_log",
            path=audit_log_file,
            now=now,
            max_age_seconds=max_audit_log_age_seconds,
        )
        if audit_item.status == "FAIL":
            audit_item = HealthCheckItem(name=audit_item.name, status="WARN", message=audit_item.message)
        items.append(audit_item)
    return RuntimeHealthReport(items=items)
