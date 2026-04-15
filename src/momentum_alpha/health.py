from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
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


def build_runtime_health_report(
    *,
    now: datetime,
    state_file: Path,
    poll_log_file: Path,
    user_stream_log_file: Path,
    audit_log_file: Path,
    max_state_age_seconds: int = 3600,
    max_poll_log_age_seconds: int = 180,
    max_user_stream_log_age_seconds: int = 1800,
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
        _check_file_freshness(name="audit_log", path=audit_log_file, now=now, max_age_seconds=max_audit_log_age_seconds),
    ]
    return RuntimeHealthReport(items=items)
