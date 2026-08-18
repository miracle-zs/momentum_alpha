from __future__ import annotations

import json
import os
import sqlite3
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable


@dataclass(frozen=True)
class ReplaySeed:
    shadow_opportunity_id: str
    symbol: str
    signal_at: datetime
    base_signal_sequence: int
    first_base_signal_at: datetime
    latest_price: Decimal | None
    stop_price: Decimal | None
    stop_budget_usdt: Decimal | None
    step_size: Decimal | None
    min_qty: Decimal | None
    tick_size: Decimal | None
    warnings: tuple[str, ...] = ()
    blocked_reason: str | None = None


@dataclass(frozen=True)
class ReplayCandle:
    open_time: datetime
    close_time: datetime
    open_price: Decimal
    high_price: Decimal
    low_price: Decimal
    close_price: Decimal


class KlineFetchError(RuntimeError):
    def __init__(self, *, symbol: str, day: date, cause: Exception):
        self.symbol = symbol
        self.day = day
        self.cause = cause
        super().__init__(f"kline_fetch_failed symbol={symbol} day={day.isoformat()} error={cause}")


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _parse_datetime(value: object, *, fallback: datetime) -> tuple[datetime, str | None]:
    try:
        parsed = datetime.fromisoformat(str(value))
        return _as_utc(parsed), None
    except (TypeError, ValueError):
        return fallback, f"invalid_datetime:{value}"


def _parse_decimal(value: object, *, field: str) -> tuple[Decimal | None, str | None]:
    if value in (None, ""):
        return None, f"missing_{field}"
    try:
        return Decimal(str(value)), None
    except (InvalidOperation, ValueError):
        return None, f"invalid_{field}:{value}"


def load_replay_inputs(
    *,
    runtime_db_path: Path,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: set[str] | None = None,
    blocked_reasons: set[str] | None = None,
) -> tuple[list[ReplaySeed], dict[datetime, str], list[str], datetime | None]:
    if not runtime_db_path.exists():
        raise FileNotFoundError(runtime_db_path)

    start_utc = _as_utc(start_time) if start_time is not None else None
    end_utc = _as_utc(end_time) if end_time is not None else None
    with sqlite3.connect(f"file:{runtime_db_path}?mode=ro", uri=True) as connection:
        rows = connection.execute(
            """
            SELECT
                id,
                timestamp,
                intent_id,
                decision_type,
                symbol,
                next_leader_symbol,
                payload_json
            FROM signal_decisions
            ORDER BY timestamp, id
            """
        ).fetchall()

    seeds: list[ReplaySeed] = []
    leaders: dict[datetime, str] = {}
    warnings: list[str] = []
    cutoff: datetime | None = None
    for row_id, timestamp_raw, intent_id, decision_type, symbol, next_leader, payload_raw in rows:
        signal_at = _as_utc(datetime.fromisoformat(timestamp_raw))
        if start_utc is not None and signal_at < start_utc:
            continue
        if end_utc is not None and signal_at > end_utc:
            continue
        cutoff = signal_at if cutoff is None or signal_at > cutoff else cutoff

        if next_leader:
            minute = signal_at.replace(second=0, microsecond=0)
            previous = leaders.get(minute)
            if previous is not None and previous != next_leader:
                warnings.append(
                    f"conflicting_leader minute={minute.isoformat()} previous={previous} next={next_leader}"
                )
            leaders[minute] = str(next_leader)

        if decision_type != "base_entry_skipped":
            continue
        if not symbol or (symbols is not None and symbol not in symbols):
            continue
        try:
            payload = json.loads(payload_raw or "{}")
        except json.JSONDecodeError:
            payload = {}
            warnings.append(f"invalid_payload_json row_id={row_id}")

        blocked_reason = payload.get("blocked_reason")
        if blocked_reasons is not None and str(blocked_reason or "") not in blocked_reasons:
            continue

        seed_warnings: list[str] = []
        sequence_raw = payload.get("base_signal_sequence")
        try:
            sequence = int(sequence_raw)
        except (TypeError, ValueError):
            sequence = 0
            seed_warnings.append(f"invalid_base_signal_sequence:{sequence_raw}")

        first_at, warning = _parse_datetime(
            payload.get("first_base_signal_at"),
            fallback=signal_at,
        )
        if warning is not None:
            seed_warnings.append(warning)

        decimal_values: dict[str, Decimal | None] = {}
        for field in (
            "latest_price",
            "stop_price",
            "stop_budget_usdt",
            "step_size",
            "min_qty",
            "tick_size",
        ):
            parsed, warning = _parse_decimal(payload.get(field), field=field)
            decimal_values[field] = parsed
            if warning is not None:
                seed_warnings.append(warning)

        shadow_id = str(
            payload.get("shadow_opportunity_id")
            or intent_id
            or f"unresolved_{row_id}_{symbol}"
        )
        seed = ReplaySeed(
            shadow_opportunity_id=shadow_id,
            symbol=str(symbol),
            signal_at=signal_at,
            base_signal_sequence=sequence,
            first_base_signal_at=first_at,
            latest_price=decimal_values["latest_price"],
            stop_price=decimal_values["stop_price"],
            stop_budget_usdt=decimal_values["stop_budget_usdt"],
            step_size=decimal_values["step_size"],
            min_qty=decimal_values["min_qty"],
            tick_size=decimal_values["tick_size"],
            warnings=tuple(seed_warnings),
            blocked_reason=(str(blocked_reason) if blocked_reason else None),
        )
        seeds.append(seed)
        warnings.extend(
            f"seed={shadow_id} {item}"
            for item in seed_warnings
        )

    return seeds, leaders, warnings, cutoff


def request_json(*, url: str, proxy: str | None, timeout: float) -> object:
    handlers = []
    if proxy:
        handlers.append(urllib.request.ProxyHandler({"http": proxy, "https": proxy}))
    opener = urllib.request.build_opener(*handlers)
    with opener.open(url, timeout=timeout) as response:
        return json.loads(response.read().decode("utf-8"))


class BinanceKlineCache:
    def __init__(
        self,
        *,
        cache_path: Path,
        proxy: str | None = None,
        request_json: Callable[..., object] = request_json,
        timeout: float = 20.0,
        max_attempts: int = 3,
        retry_sleep_seconds: float = 0.25,
        now_provider: Callable[[], datetime] | None = None,
    ):
        self.cache_path = cache_path
        self.proxy = proxy
        self.request_json = request_json
        self.timeout = timeout
        self.max_attempts = max(1, max_attempts)
        self.retry_sleep_seconds = retry_sleep_seconds
        self.now_provider = now_provider or (lambda: datetime.now(timezone.utc))
        self._cache = self._load_cache()

    def _load_cache(self) -> dict[str, list]:
        if not self.cache_path.exists():
            return {}
        try:
            payload = json.loads(self.cache_path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return payload if isinstance(payload, dict) else {}

    def _save_cache(self) -> None:
        self.cache_path.parent.mkdir(parents=True, exist_ok=True)
        temporary_path = self.cache_path.with_name(f".{self.cache_path.name}.tmp")
        temporary_path.write_text(
            json.dumps(self._cache, separators=(",", ":"), sort_keys=True),
            encoding="utf-8",
        )
        os.replace(temporary_path, self.cache_path)

    def _fetch_day(self, *, symbol: str, day: date) -> list:
        day_start = datetime.combine(day, datetime_time.min, tzinfo=timezone.utc)
        next_day = day_start + timedelta(days=1)
        query = urllib.parse.urlencode(
            {
                "symbol": symbol,
                "interval": "1m",
                "startTime": int(day_start.timestamp() * 1000),
                "endTime": int(next_day.timestamp() * 1000) - 1,
                "limit": 1440,
            }
        )
        url = f"https://fapi.binance.com/fapi/v1/klines?{query}"
        last_error: Exception | None = None
        for attempt in range(self.max_attempts):
            try:
                payload = self.request_json(
                    url=url,
                    proxy=self.proxy,
                    timeout=self.timeout,
                )
                if not isinstance(payload, list):
                    raise ValueError("unexpected kline payload")
                return payload
            except Exception as exc:
                last_error = exc
                if attempt + 1 < self.max_attempts:
                    time.sleep(self.retry_sleep_seconds * (attempt + 1))
        assert last_error is not None
        raise KlineFetchError(symbol=symbol, day=day, cause=last_error)

    @staticmethod
    def _to_candle(row: list) -> ReplayCandle:
        return ReplayCandle(
            open_time=datetime.fromtimestamp(int(row[0]) / 1000, tz=timezone.utc),
            close_time=datetime.fromtimestamp(int(row[6]) / 1000, tz=timezone.utc),
            open_price=Decimal(str(row[1])),
            high_price=Decimal(str(row[2])),
            low_price=Decimal(str(row[3])),
            close_price=Decimal(str(row[4])),
        )

    def load_range(
        self,
        *,
        symbol: str,
        start_time: datetime,
        end_time: datetime,
        refresh: bool = False,
    ) -> list[ReplayCandle]:
        start_utc = _as_utc(start_time)
        end_utc = _as_utc(end_time)
        if end_utc < start_utc:
            raise ValueError("end_time must not be before start_time")

        rows: list[list] = []
        current_day = start_utc.date()
        current_utc_date = _as_utc(self.now_provider()).date()
        while current_day <= end_utc.date():
            cache_key = f"{symbol}:{current_day.isoformat()}"
            is_current_day = current_day == current_utc_date
            if refresh or cache_key not in self._cache or is_current_day:
                day_rows = self._fetch_day(symbol=symbol, day=current_day)
                # Binance returns only completed minutes for the current day.
                # Never persist that partial response as an immutable day cache.
                if not is_current_day:
                    self._cache[cache_key] = day_rows
                    self._save_cache()
            else:
                day_rows = self._cache[cache_key]
            rows.extend(day_rows)
            current_day += timedelta(days=1)

        candles = [
            self._to_candle(row)
            for row in rows
            if len(row) >= 7
        ]
        return sorted(
            [
                candle
                for candle in candles
                if candle.open_time >= start_utc and candle.close_time <= end_utc
            ],
            key=lambda candle: candle.open_time,
        )
