from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone
import logging
from pathlib import Path
import sqlite3
import threading
from time import monotonic

from momentum_alpha.dashboard_common import normalize_account_range
from momentum_alpha.dashboard_render_utils import normalize_dashboard_room

logger = logging.getLogger(__name__)

DEFAULT_READ_MODEL_TTL_SECONDS = 2.0


class OperationalReadModel:
    """Dedicated in-memory operational read model (CQRS Read Projection).

    Solves two major performance bottlenecks:
    1. Read-write separation with zero database lock contention:
       Incoming HTTP requests read directly from in-memory pre-aggregated state
       without opening SQLite connections or acquiring SQLite locks on the critical path.
    2. State lazy loading (按需懒加载):
       Splits the operational model into hot operational state (live room, health,
       recent signals/fills) and cold state (review reports, multi-day replays,
       full historical trade round trips), only loading cold slices on demand.
    """

    def __init__(
        self,
        *,
        runtime_db_file: Path,
        ttl_seconds: float = DEFAULT_READ_MODEL_TTL_SECONDS,
        now_provider: Callable[[], datetime] | None = None,
        stop_budget_usdt: str | None = None,
        entry_start_hour_utc: int = 1,
        entry_end_hour_utc: int = 23,
        testnet: bool = False,
        submit_orders: bool = False,
    ) -> None:
        self.runtime_db_file = Path(runtime_db_file)
        self.ttl_seconds = max(0.1, float(ttl_seconds))
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self.stop_budget_usdt = stop_budget_usdt
        self.entry_start_hour_utc = entry_start_hour_utc
        self.entry_end_hour_utc = entry_end_hour_utc
        self.testnet = testnet
        self.submit_orders = submit_orders

        self._lock = threading.RLock()
        self._snapshots: dict[tuple[str, str, str | None], tuple[float, dict]] = {}
        self._version = 0
        self._db_signature: tuple[tuple[int, int] | None, ...] | None = None

        # Background updater attributes
        self._stop_event = threading.Event()
        self._updater_thread: threading.Thread | None = None

    @property
    def version(self) -> int:
        with self._lock:
            return self._version

    def _file_signature(self) -> tuple[tuple[int, int] | None, ...]:
        signature: list[tuple[int, int] | None] = []
        for suffix in ("", "-wal"):
            candidate = self.runtime_db_file if not suffix else Path(f"{self.runtime_db_file}{suffix}")
            try:
                stat = candidate.stat()
            except OSError:
                signature.append(None)
            else:
                signature.append((stat.st_mtime_ns, stat.st_size))
        return tuple(signature)

    def is_fresh(
        self,
        *,
        room: str = "live",
        account_range_key: str = "1D",
        report_date: str | None = None,
    ) -> bool:
        normalized_room = normalize_dashboard_room(room)
        normalized_range = normalize_account_range(account_range_key)
        key = (normalized_room, normalized_range, report_date)
        now = monotonic()
        with self._lock:
            cached = self._snapshots.get(key)
            if cached is None:
                return False
            created_at, _ = cached
            return (now - created_at) < self.ttl_seconds

    def get_snapshot(
        self,
        *,
        room: str = "live",
        account_range_key: str = "1D",
        report_date: str | None = None,
        force_refresh: bool = False,
        loader: Callable[[], dict] | None = None,
    ) -> dict:
        """Retrieve the snapshot from the in-memory read model.

        If fresh, returns immediately from memory with zero database reads.
        If stale or missing, fetches and aggregates the state atomically.
        """
        normalized_room = normalize_dashboard_room(room)
        normalized_range = normalize_account_range(account_range_key)
        key = (normalized_room, normalized_range, report_date)
        now = monotonic()

        with self._lock:
            cached = self._snapshots.get(key)
            if not force_refresh and cached is not None:
                created_at, snapshot = cached
                if (now - created_at) < self.ttl_seconds:
                    return snapshot

            # Cache miss or stale: execute load
            if loader is not None:
                snapshot = loader()
            else:
                snapshot = self._load_from_db(
                    room=normalized_room,
                    account_range_key=normalized_range,
                    report_date=report_date,
                )

            self._snapshots[key] = (monotonic(), snapshot)
            self._version += 1
            return snapshot

    def _load_from_db(
        self,
        *,
        room: str,
        account_range_key: str,
        report_date: str | None,
    ) -> dict:
        from momentum_alpha.dashboard_data_loader import (
            load_dashboard_live_snapshot,
            load_dashboard_snapshot,
        )

        now = self.now_provider().astimezone()
        if room == "live":
            # Fast-path for live room: lightweight projection
            return load_dashboard_live_snapshot(
                now=now,
                runtime_db_file=self.runtime_db_file,
                stop_budget_usdt=self.stop_budget_usdt,
                entry_start_hour_utc=self.entry_start_hour_utc,
                entry_end_hour_utc=self.entry_end_hour_utc,
                testnet=self.testnet,
                submit_orders=self.submit_orders,
                account_range_key=account_range_key,
                report_date=report_date,
            )

        # Lazy room-aware load
        return load_dashboard_snapshot(
            now=now,
            runtime_db_file=self.runtime_db_file,
            stop_budget_usdt=self.stop_budget_usdt,
            entry_start_hour_utc=self.entry_start_hour_utc,
            entry_end_hour_utc=self.entry_end_hour_utc,
            testnet=self.testnet,
            submit_orders=self.submit_orders,
            account_range_key=account_range_key,
            report_date=report_date,
            room=room,
        )

    def refresh(
        self,
        *,
        room: str = "live",
        account_range_key: str = "1D",
        report_date: str | None = None,
    ) -> dict:
        """Force an immediate refresh of the read model for the specified room."""
        return self.get_snapshot(
            room=room,
            account_range_key=account_range_key,
            report_date=report_date,
            force_refresh=True,
        )

    def invalidate(self) -> None:
        """Clear all in-memory snapshot caches."""
        with self._lock:
            self._snapshots.clear()
            self._version += 1

    def start_background_updater(self, interval_seconds: float = 1.5) -> None:
        """Start a background daemon thread that periodically refreshes the hot read model."""
        with self._lock:
            if self._updater_thread is not None and self._updater_thread.is_alive():
                return
            self._stop_event.clear()
            self._updater_thread = threading.Thread(
                target=self._background_loop,
                args=(max(0.01, float(interval_seconds)),),
                name="OperationalReadModelUpdater",
                daemon=True,
            )
            self._updater_thread.start()

    def stop_background_updater(self) -> None:
        """Stop the background updater thread cleanly."""
        self._stop_event.set()
        thread = self._updater_thread
        if thread is not None and thread.is_alive():
            thread.join(timeout=2.0)
        with self._lock:
            self._updater_thread = None

    def _background_loop(self, interval: float) -> None:
        while not self._stop_event.is_set():
            try:
                # Pre-warm hot operational state for live room immediately
                self.refresh(room="live", account_range_key="1D")
            except (OSError, sqlite3.Error) as exc:
                logger.debug("background read model refresh skipped: %s", exc)
            except Exception:
                logger.exception("unexpected error in read model updater loop")
            if self._stop_event.wait(interval):
                break

    def __enter__(self) -> OperationalReadModel:
        return self

    def __exit__(self, exc_type, exc_val, exc_tb) -> None:
        self.stop_background_updater()
