from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
import sqlite3
from pathlib import Path


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
        if any(item.status == "WARN" for item in self.items):
            return "WARN"
        return "OK"


def _check_runtime_db_freshness(*, path: Path, now: datetime, max_age_seconds: int) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem(name="runtime_db", status="FAIL", message="missing runtime_db")
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                "SELECT timestamp FROM audit_events ORDER BY timestamp DESC, id DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return HealthCheckItem(name="runtime_db", status="FAIL", message=f"invalid runtime_db error={exc}")
    if row is None or not row[0]:
        return HealthCheckItem(name="runtime_db", status="WARN", message="empty runtime_db")
    latest_timestamp = datetime.fromisoformat(row[0]).astimezone(timezone.utc)
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - latest_timestamp.timestamp())
    if age_seconds > max_age_seconds:
        return HealthCheckItem(
            name="runtime_db",
            status="FAIL",
            message=f"stale age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name="runtime_db", status="OK", message=f"fresh age_seconds={age_seconds}")


def _check_strategy_state_freshness(*, path: Path, now: datetime, max_age_seconds: int) -> HealthCheckItem:
    """Check freshness of strategy state in runtime database."""
    if not path.exists():
        return HealthCheckItem(name="strategy_state", status="FAIL", message=f"missing path={path}")
    try:
        connection = sqlite3.connect(path)
        try:
            # Check if strategy_state table exists and has data
            row = connection.execute(
                "SELECT 1 FROM strategy_state LIMIT 1"
            ).fetchone()
            if row is None:
                return HealthCheckItem(name="strategy_state", status="WARN", message=f"empty strategy_state table")
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return HealthCheckItem(name="strategy_state", status="FAIL", message=f"invalid path={path} error={exc}")
    # Check audit_events for latest activity as proxy for state freshness
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                "SELECT timestamp FROM audit_events ORDER BY timestamp DESC, id DESC LIMIT 1"
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error:
        return HealthCheckItem(name="strategy_state", status="OK", message="state exists but audit check failed")
    if row is None or not row[0]:
        return HealthCheckItem(name="strategy_state", status="WARN", message="no audit events")
    latest_timestamp = datetime.fromisoformat(row[0]).astimezone(timezone.utc)
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - latest_timestamp.timestamp())
    if age_seconds > max_age_seconds:
        return HealthCheckItem(
            name="strategy_state",
            status="FAIL",
            message=f"stale age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name="strategy_state", status="OK", message=f"fresh age_seconds={age_seconds}")


def _check_audit_event_freshness(
    *,
    name: str,
    path: Path,
    now: datetime,
    max_age_seconds: int,
    event_types: tuple[str, ...],
    stale_status: str = "FAIL",
) -> HealthCheckItem:
    if not path.exists():
        return HealthCheckItem(name=name, status="FAIL", message=f"missing path={path}")
    placeholders = ", ".join("?" for _ in event_types)
    try:
        connection = sqlite3.connect(path)
        try:
            row = connection.execute(
                f"""
                SELECT timestamp
                FROM audit_events
                WHERE event_type IN ({placeholders})
                ORDER BY timestamp DESC, id DESC
                LIMIT 1
                """,
                event_types,
            ).fetchone()
        finally:
            connection.close()
    except sqlite3.Error as exc:
        return HealthCheckItem(name=name, status="FAIL", message=f"invalid path={path} error={exc}")
    if row is None or not row[0]:
        return HealthCheckItem(name=name, status="WARN", message=f"no events event_types={','.join(event_types)}")
    latest_timestamp = datetime.fromisoformat(row[0]).astimezone(timezone.utc)
    age_seconds = int(now.astimezone(timezone.utc).timestamp() - latest_timestamp.timestamp())
    if age_seconds > max_age_seconds:
        status = stale_status if stale_status in {"FAIL", "WARN"} else "FAIL"
        stale_label = "stale" if status == "FAIL" else "inactive"
        return HealthCheckItem(
            name=name,
            status=status,
            message=f"{stale_label} age_seconds={age_seconds} max_age_seconds={max_age_seconds}",
        )
    return HealthCheckItem(name=name, status="OK", message=f"fresh age_seconds={age_seconds}")


def build_runtime_health_report(
    *,
    now: datetime,
    runtime_db_file: Path,
    max_poll_event_age_seconds: int = 180,
    max_user_stream_event_age_seconds: int = 1800,
    max_runtime_db_age_seconds: int = 1800,
    max_state_age_seconds: int = 3600,
) -> RuntimeHealthReport:
    items = [
        _check_strategy_state_freshness(path=runtime_db_file, now=now, max_age_seconds=max_state_age_seconds),
        _check_audit_event_freshness(
            name="poll_events",
            path=runtime_db_file,
            now=now,
            max_age_seconds=max_poll_event_age_seconds,
            event_types=("poll_tick", "poll_worker_start", "tick_result"),
        ),
        _check_audit_event_freshness(
            name="user_stream_events",
            path=runtime_db_file,
            now=now,
            max_age_seconds=max_user_stream_event_age_seconds,
            event_types=("user_stream_worker_start", "user_stream_event"),
            stale_status="WARN",
        ),
        _check_runtime_db_freshness(path=runtime_db_file, now=now, max_age_seconds=max_runtime_db_age_seconds),
    ]
    return RuntimeHealthReport(items=items)
