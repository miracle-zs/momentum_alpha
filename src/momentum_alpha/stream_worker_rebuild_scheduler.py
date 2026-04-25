from __future__ import annotations

import threading
from datetime import datetime, timedelta
from typing import Callable

from momentum_alpha.structured_log import emit_structured_log


class DebouncedRebuildScheduler:
    def __init__(
        self,
        *,
        debounce_seconds: int,
        now_provider: Callable[[], datetime],
        rebuild_fn: Callable[[], None],
        logger: Callable[[str], None],
        start_worker: bool = True,
    ) -> None:
        self._debounce = timedelta(seconds=debounce_seconds)
        self._now_provider = now_provider
        self._rebuild_fn = rebuild_fn
        self._logger = logger
        self._condition = threading.Condition()
        self._pending = False
        self._deadline: datetime | None = None
        self._closed = False
        self._worker_thread: threading.Thread | None = None
        if start_worker:
            self._worker_thread = threading.Thread(target=self._worker_loop, name="debounced-rebuild", daemon=True)
            self._worker_thread.start()

    def notify(self) -> None:
        with self._condition:
            if self._closed:
                return
            self._deadline = self._now_provider() + self._debounce
            self._pending = True
            self._condition.notify_all()

    def flush_for_test(self) -> None:
        while True:
            with self._condition:
                if self._closed or not self._pending:
                    return
                self._deadline = self._now_provider()
            if not self._run_pending_once(force=True):
                return

    def close(self) -> None:
        with self._condition:
            self._closed = True
            self._condition.notify_all()
        if self._worker_thread is not None:
            self._worker_thread.join(timeout=5)

    def _worker_loop(self) -> None:
        while True:
            with self._condition:
                while not self._closed and not self._pending:
                    self._condition.wait()
                if self._closed:
                    return
                while not self._closed and self._pending:
                    if self._deadline is None:
                        self._condition.wait()
                        continue
                    now = self._now_provider()
                    remaining = (self._deadline - now).total_seconds()
                    if remaining > 0:
                        self._condition.wait(timeout=remaining)
                        continue
                    break
                if self._closed:
                    return
            self._run_pending_once(force=False)

    def _run_pending_once(self, *, force: bool) -> bool:
        with self._condition:
            if self._closed or not self._pending:
                return False
            if not force:
                if self._deadline is None:
                    return False
                now = self._now_provider()
                if now < self._deadline:
                    return False
            self._pending = False
        try:
            self._rebuild_fn()
        except Exception as exc:  # pragma: no cover - error path verified in tests
            emit_structured_log(
                self._logger,
                service="user-stream",
                event="rebuild-trade-analytics-error",
                level="ERROR",
                error=str(exc),
            )
        finally:
            with self._condition:
                self._condition.notify_all()
        return True
