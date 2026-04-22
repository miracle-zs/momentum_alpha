from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.audit import AuditRecorder

from momentum_alpha.runtime_store import RuntimeStateStore


def resolve_runtime_db_path(*, explicit_path: str | None, default_dir: Path | None = None) -> Path | None:
    """Resolve the runtime database path.

    Priority:
    1. Explicit path provided
    2. RUNTIME_DB_FILE environment variable
    3. default_dir/runtime.db if default_dir is provided
    """
    if explicit_path:
        return Path(os.path.abspath(explicit_path))
    env_path = os.environ.get("RUNTIME_DB_FILE")
    if env_path:
        return Path(os.path.abspath(env_path))
    if default_dir is not None:
        return default_dir / "runtime.db"
    return None


def _require_runtime_db_path(*, parser: argparse.ArgumentParser, command: str, explicit_path: str | None) -> Path:
    runtime_db_path = resolve_runtime_db_path(explicit_path=explicit_path)
    if runtime_db_path is None:
        parser.error(f"{command} requires --runtime-db-file or RUNTIME_DB_FILE")
    return runtime_db_path


def _build_audit_recorder(
    *,
    runtime_db_path: Path | None,
    source: str | None = None,
    error_logger=None,
) -> AuditRecorder | None:
    if runtime_db_path is None:
        return None
    return AuditRecorder(runtime_db_path=runtime_db_path, source=source, error_logger=error_logger)


def _build_runtime_state_store(*, runtime_db_path: Path | None) -> RuntimeStateStore | None:
    """Build a RuntimeStateStore for state persistence."""
    if runtime_db_path is None:
        return None
    return RuntimeStateStore(path=runtime_db_path)


def load_credentials_from_env() -> tuple[str, str]:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    return api_key, api_secret


def load_runtime_settings_from_env() -> dict[str, bool]:
    raw_testnet = os.environ.get("BINANCE_USE_TESTNET", "")
    return {"use_testnet": raw_testnet.strip().lower() in {"1", "true", "yes", "on"}}


def _parse_cli_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _build_client_from_factory(*, client_factory, testnet: bool):
    try:
        return client_factory(testnet=testnet)
    except TypeError:
        return client_factory()
