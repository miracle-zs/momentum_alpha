from __future__ import annotations

from datetime import datetime, timezone

from .market_data_windows import _current_hour_window_ms, _previous_closed_hour_window_ms, _utc_midnight_window_ms


def _fetch_daily_open_klines(*, client, symbol: str, now: datetime):
    day_open_start_ms, day_open_end_ms = _utc_midnight_window_ms(now=now)
    klines = client.fetch_klines(
        symbol=symbol,
        interval="1m",
        limit=1,
        start_time_ms=day_open_start_ms,
        end_time_ms=day_open_end_ms,
    )
    if klines:
        return klines
    return client.fetch_klines(
        symbol=symbol,
        interval="1m",
        limit=1,
        start_time_ms=day_open_start_ms,
        end_time_ms=int(now.astimezone(timezone.utc).timestamp() * 1000),
    )


def _fetch_previous_hour_klines(*, client, symbol: str, now: datetime):
    previous_hour_start_ms, previous_hour_end_ms = _previous_closed_hour_window_ms(now=now)
    return client.fetch_klines(
        symbol=symbol,
        interval="1h",
        limit=1,
        start_time_ms=previous_hour_start_ms,
        end_time_ms=previous_hour_end_ms,
    )


def _fetch_current_hour_klines(*, client, symbol: str, now: datetime):
    current_hour_start_ms, current_hour_end_ms = _current_hour_window_ms(now=now)
    return client.fetch_klines(
        symbol=symbol,
        interval="1h",
        limit=1,
        start_time_ms=current_hour_start_ms,
        end_time_ms=current_hour_end_ms,
    )


def _fetch_base_veto_klines(*, client, symbol: str, now: datetime, limit: int = 90):
    """Fetch a short 1m history; the feature calculator removes open candles."""

    resolved_now = (
        now.replace(tzinfo=timezone.utc)
        if now.tzinfo is None
        else now.astimezone(timezone.utc)
    )
    signal_ms = int(resolved_now.timestamp() * 1000)
    end_time_ms = signal_ms - 1
    current_minute_start_ms = (signal_ms // 60_000) * 60_000
    start_time_ms = current_minute_start_ms - limit * 60_000
    return client.fetch_klines(
        symbol=symbol,
        interval="1m",
        limit=limit,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
    )
