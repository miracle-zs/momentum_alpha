from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.analytics_schema import bootstrap_leader_candidates_db
from momentum_alpha.analytics_writes_candidates import insert_leader_candidate_snapshots_bulk
from momentum_alpha.exchange_info import parse_exchange_info


DEFAULT_LEADER_CANDIDATES_DB_PATH = Path("local_analytics/leader_candidates.db")


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _candidate_row_from_replay(
    *,
    timestamp: str,
    rank: int,
    candidate: dict,
    leader_symbol: str | None = None,
) -> dict | None:
    symbol = candidate.get("symbol")
    if symbol in (None, "") and rank == 1:
        symbol = leader_symbol
    if symbol in (None, ""):
        return None
    return {
        "timestamp": timestamp,
        "source": "position-snapshot-replay",
        "symbol": str(symbol).upper(),
        "rank": rank,
        "daily_open_price": candidate.get("daily_open_price"),
        "latest_price": candidate.get("latest_price"),
        "daily_change_pct": candidate.get("daily_change_pct"),
        "previous_hour_low": candidate.get("previous_hour_low"),
        "current_hour_low": candidate.get("current_hour_low"),
        "leader_gap_pct": candidate.get("leader_gap_pct"),
        "payload": dict(candidate),
    }


def replay_position_snapshot_candidates(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    logger=print,
) -> int:
    if not runtime_db_path.exists():
        logger(f"leader-candidate-replay runtime_db_missing path={runtime_db_path}")
        return 0
    connection = sqlite3.connect(runtime_db_path)
    try:
        rows = connection.execute(
            """
            SELECT timestamp, leader_symbol, payload_json
            FROM position_snapshots
            WHERE json_type(payload_json, '$.market_context.candidates') IS NOT NULL
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
    finally:
        connection.close()

    candidate_rows: list[dict] = []
    for timestamp, leader_symbol, payload_json in rows:
        payload = _json_loads(payload_json)
        market_context = payload.get("market_context") or {}
        candidates = market_context.get("candidates") or []
        if not isinstance(candidates, list):
            continue
        resolved_leader_symbol = leader_symbol or market_context.get("leader_symbol")
        for rank, candidate in enumerate(candidates, start=1):
            if not isinstance(candidate, dict):
                continue
            candidate_row = _candidate_row_from_replay(
                timestamp=timestamp,
                rank=rank,
                candidate=candidate,
                leader_symbol=resolved_leader_symbol,
            )
            if candidate_row is not None:
                candidate_rows.append(candidate_row)

    inserted = insert_leader_candidate_snapshots_bulk(path=leader_candidates_db_path, rows=candidate_rows)
    logger(
        "leader-candidate-replay "
        f"runtime_db={runtime_db_path} analytics_db={leader_candidates_db_path} "
        f"snapshots={len(rows)} candidates={len(candidate_rows)} inserted={inserted}"
    )
    return inserted


_INTERVAL_SECONDS = {
    "1m": 60,
    "3m": 180,
    "5m": 300,
    "15m": 900,
    "30m": 1800,
    "1h": 3600,
}


def _timestamp_ms(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _datetime_from_ms(value: int) -> datetime:
    return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)


def _decimal_text(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _decimal_from_value(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _fetch_symbol_klines(
    *,
    client,
    symbol: str,
    interval: str,
    start_time: datetime,
    end_time: datetime,
) -> list[list]:
    return client.fetch_klines(
        symbol=symbol,
        interval=interval,
        limit=1500,
        start_time_ms=_timestamp_ms(start_time),
        end_time_ms=_timestamp_ms(end_time),
    )


def _utc_midnight(value: datetime) -> datetime:
    utc_value = value.astimezone(timezone.utc)
    return datetime(utc_value.year, utc_value.month, utc_value.day, tzinfo=timezone.utc)


def _iter_utc_days(*, start_time: datetime, end_time: datetime):
    current_day = _utc_midnight(start_time)
    end_day = _utc_midnight(end_time)
    while current_day <= end_day:
        yield current_day
        current_day += timedelta(days=1)


def _rows_for_symbol_day_klines(
    *,
    symbol: str,
    klines: list[list],
    day_start: datetime,
    output_start: datetime,
    output_end: datetime,
) -> list[dict]:
    parsed = sorted(klines, key=lambda item: int(item[0]))
    if not parsed:
        return []

    daily_open_price: Decimal | None = None
    current_hour_start: datetime | None = None
    current_hour_low: Decimal | None = None
    completed_hour_lows: dict[datetime, Decimal] = {}
    rows: list[dict] = []

    for item in parsed:
        timestamp = _datetime_from_ms(int(item[0]))
        hour_start = datetime(timestamp.year, timestamp.month, timestamp.day, timestamp.hour, tzinfo=timezone.utc)
        open_price = _decimal_from_value(item[1])
        low_price = _decimal_from_value(item[3])
        close_price = _decimal_from_value(item[4])
        if low_price is None or close_price is None:
            continue

        if current_hour_start is None:
            current_hour_start = hour_start
            current_hour_low = low_price
        elif hour_start != current_hour_start:
            if current_hour_low is not None:
                completed_hour_lows[current_hour_start] = current_hour_low
            current_hour_start = hour_start
            current_hour_low = low_price
        else:
            current_hour_low = low_price if current_hour_low is None else min(current_hour_low, low_price)

        if timestamp < day_start:
            continue
        if timestamp < output_start:
            continue
        if timestamp >= output_end:
            continue

        if daily_open_price is None:
            if open_price is None:
                continue
            daily_open_price = open_price
        if daily_open_price <= Decimal("0"):
            continue

        daily_change_pct = (close_price - daily_open_price) / daily_open_price
        rows.append(
            {
                "timestamp": timestamp,
                "source": "kline-backfill",
                "symbol": symbol.upper(),
                "daily_open_price": daily_open_price,
                "latest_price": close_price,
                "daily_change_pct": daily_change_pct,
                "previous_hour_low": completed_hour_lows.get(hour_start - timedelta(hours=1)),
                "current_hour_low": current_hour_low,
                "payload": {
                    "symbol": symbol.upper(),
                    "timestamp": timestamp.isoformat(),
                    "interval_source": "kline",
                },
            }
        )

    return rows


def _rank_candidate_rows(*, symbol_rows: list[dict], top_n: int) -> list[dict]:
    by_timestamp: dict[datetime, list[dict]] = {}
    for row in symbol_rows:
        by_timestamp.setdefault(row["timestamp"], []).append(row)

    ranked_rows: list[dict] = []
    for timestamp in sorted(by_timestamp):
        ordered = sorted(
            by_timestamp[timestamp],
            key=lambda item: (-item["daily_change_pct"], item["symbol"]),
        )[:top_n]
        leader_gap_pct = None
        if len(ordered) >= 2:
            leader_gap_pct = ordered[0]["daily_change_pct"] - ordered[1]["daily_change_pct"]
        for rank, row in enumerate(ordered, start=1):
            ranked_rows.append(
                {
                    "timestamp": timestamp,
                    "source": row["source"],
                    "symbol": row["symbol"],
                    "rank": rank,
                    "daily_open_price": _decimal_text(row["daily_open_price"]),
                    "latest_price": _decimal_text(row["latest_price"]),
                    "daily_change_pct": _decimal_text(row["daily_change_pct"]),
                    "previous_hour_low": _decimal_text(row["previous_hour_low"]),
                    "current_hour_low": _decimal_text(row["current_hour_low"]),
                    "leader_gap_pct": _decimal_text(leader_gap_pct) if rank == 1 else None,
                    "payload": {
                        **(row.get("payload") or {}),
                        "rank": rank,
                        "leader_gap_pct": _decimal_text(leader_gap_pct) if rank == 1 else None,
                    },
                }
            )
    return ranked_rows


def backfill_leader_candidates_from_klines(
    *,
    client,
    leader_candidates_db_path: Path,
    start_time: datetime,
    end_time: datetime,
    symbols: list[str] | tuple[str, ...],
    interval: str = "5m",
    top_n: int = 50,
    logger=print,
) -> int:
    if interval not in _INTERVAL_SECONDS:
        raise ValueError(f"unsupported interval: {interval}")
    normalized_symbols = sorted({symbol.upper() for symbol in symbols if symbol})
    if not normalized_symbols:
        bootstrap_leader_candidates_db(path=leader_candidates_db_path)
        return 0

    symbol_rows: list[dict] = []
    failed_symbols: list[str] = []
    request_start = start_time.astimezone(timezone.utc)
    request_end = end_time.astimezone(timezone.utc)
    for day_start in _iter_utc_days(start_time=request_start, end_time=request_end - timedelta(microseconds=1)):
        day_end = min(day_start + timedelta(days=1), request_end)
        fetch_start = day_start - timedelta(hours=1)
        for symbol in normalized_symbols:
            try:
                klines = _fetch_symbol_klines(
                    client=client,
                    symbol=symbol,
                    interval=interval,
                    start_time=fetch_start,
                    end_time=day_end,
                )
            except Exception:
                failed_symbols.append(symbol)
                continue
            symbol_rows.extend(
                _rows_for_symbol_day_klines(
                    symbol=symbol,
                    klines=klines,
                    day_start=day_start,
                    output_start=request_start,
                    output_end=request_end,
                )
            )

    ranked_rows = _rank_candidate_rows(symbol_rows=symbol_rows, top_n=top_n)
    inserted = insert_leader_candidate_snapshots_bulk(path=leader_candidates_db_path, rows=ranked_rows)
    logger(
        "leader-candidate-kline-backfill "
        f"analytics_db={leader_candidates_db_path} symbols={len(normalized_symbols)} "
        f"failed_symbols={len(set(failed_symbols))} candidates={len(ranked_rows)} inserted={inserted}"
    )
    return inserted


def _resolve_backfill_symbols(*, client) -> list[str]:
    exchange_info = client.fetch_exchange_info()
    return sorted(parse_exchange_info(exchange_info))


def backfill_leader_candidates(
    *,
    leader_candidates_db_path: Path,
    runtime_db_path: Path | None = None,
    replay_position_snapshots: bool = False,
    client=None,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    interval: str = "5m",
    top_n: int = 50,
    logger=print,
) -> int:
    if replay_position_snapshots:
        if runtime_db_path is None:
            raise ValueError("runtime_db_path is required for replay")
        return replay_position_snapshot_candidates(
            runtime_db_path=runtime_db_path,
            leader_candidates_db_path=leader_candidates_db_path,
            logger=logger,
        )
    if client is None:
        raise ValueError("client is required for kline backfill")
    if start_time is None or end_time is None:
        raise ValueError("start_time and end_time are required for kline backfill")
    resolved_symbols = list(symbols or _resolve_backfill_symbols(client=client))
    return backfill_leader_candidates_from_klines(
        client=client,
        leader_candidates_db_path=leader_candidates_db_path,
        start_time=start_time,
        end_time=end_time,
        symbols=resolved_symbols,
        interval=interval,
        top_n=top_n,
        logger=logger,
    )
