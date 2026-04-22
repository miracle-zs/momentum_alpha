from __future__ import annotations

from datetime import datetime, timedelta, timezone


def _utc_midnight_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    utc_midnight = datetime(utc_now.year, utc_now.month, utc_now.day, tzinfo=timezone.utc)
    window_end = utc_midnight + timedelta(minutes=1) - timedelta(milliseconds=1)
    return int(utc_midnight.timestamp() * 1000), int(window_end.timestamp() * 1000)


def _previous_closed_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    previous_hour_start = current_hour_start - timedelta(hours=1)
    previous_hour_end = current_hour_start - timedelta(milliseconds=1)
    return int(previous_hour_start.timestamp() * 1000), int(previous_hour_end.timestamp() * 1000)


def _current_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    return int(current_hour_start.timestamp() * 1000), int(utc_now.timestamp() * 1000)
