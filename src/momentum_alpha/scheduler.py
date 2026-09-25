from __future__ import annotations

from collections.abc import Callable
from datetime import datetime, timezone


def _minute_difference(
    previous: tuple[int, int, int, int, int],
    current: tuple[int, int, int, int, int],
) -> int:
    prev_dt = datetime(*previous, tzinfo=timezone.utc)
    curr_dt = datetime(*current, tzinfo=timezone.utc)
    return int((curr_dt - prev_dt).total_seconds() // 60)


def run_loop(
    *,
    run_once: Callable[[datetime], None],
    now_provider: Callable[[], datetime],
    sleep_fn: Callable[[float], None],
    max_ticks: int | None = None,
    error_handler: Callable[[Exception, datetime], None] | None = None,
    stop_requested: Callable[[], bool] | None = None,
    max_delay_seconds: int = 20,
    on_tick: Callable[[datetime, float], None] | None = None,
    on_missed_tick: Callable[[int, tuple[int, int, int, int, int], tuple[int, int, int, int, int]], None] | None = None,
) -> None:
    last_seen_minute: tuple[int, int, int, int, int] | None = None
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        if stop_requested is not None and stop_requested():
            break
        now = now_provider()
        minute_key = (now.year, now.month, now.day, now.hour, now.minute)
        if minute_key != last_seen_minute:
            if last_seen_minute is not None:
                gap = _minute_difference(last_seen_minute, minute_key)
                if gap > 1 and on_missed_tick is not None:
                    on_missed_tick(gap - 1, last_seen_minute, minute_key)

            if now.second <= max_delay_seconds:
                delay_seconds = float(now.second) + float(now.microsecond) / 1_000_000.0
                if on_tick is not None:
                    on_tick(now, delay_seconds)
                try:
                    run_once(now)
                except Exception as exc:  # pragma: no cover - behavior verified through tests
                    if error_handler is not None:
                        error_handler(exc, now)
                    else:
                        raise
                last_seen_minute = minute_key
                ticks += 1
            else:
                # Outside the acceptable startup/recovery window for this minute;
                # mark minute as seen to wait for the next boundary without re-triggering mid-minute.
                if last_seen_minute is not None and on_missed_tick is not None:
                    on_missed_tick(1, last_seen_minute, minute_key)
                last_seen_minute = minute_key

        if stop_requested is not None and stop_requested():
            break
        sleep_fn(1)
