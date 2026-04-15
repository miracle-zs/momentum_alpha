from __future__ import annotations


def run_loop(*, run_once, now_provider, sleep_fn, max_ticks: int | None = None, error_handler=None) -> None:
    last_seen_minute = None
    ticks = 0
    while max_ticks is None or ticks < max_ticks:
        now = now_provider()
        minute_key = (now.year, now.month, now.day, now.hour, now.minute)
        if minute_key != last_seen_minute:
            try:
                run_once(now)
            except Exception as exc:  # pragma: no cover - behavior verified through tests
                if error_handler is not None:
                    error_handler(exc, now)
                else:
                    raise
            last_seen_minute = minute_key
        sleep_fn(1)
        ticks += 1
