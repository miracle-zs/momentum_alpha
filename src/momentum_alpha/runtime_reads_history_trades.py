from __future__ import annotations

from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _ACCOUNT_RANGE_DENSITY, _as_utc_iso, _json_loads, _trade_round_trip_row_to_dict


def fetch_recent_trade_round_trips(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            ORDER BY closed_at DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [_trade_round_trip_row_to_dict(row) for row in rows]


def fetch_trade_round_trips_for_range(*, path: Path, now: datetime, range_key: str) -> list[dict]:
    if not path.exists():
        return []
    window, _bucket_seconds = _ACCOUNT_RANGE_DENSITY.get(range_key, _ACCOUNT_RANGE_DENSITY["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "" if cutoff is None else "WHERE closed_at >= ?"
    params = () if cutoff is None else (cutoff.astimezone(timezone.utc).isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            {where_clause}
            ORDER BY closed_at DESC, id DESC
            """,
            params,
        ).fetchall()
    return [_trade_round_trip_row_to_dict(row) for row in rows]


def fetch_trade_round_trips_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                round_trip_id,
                symbol,
                opened_at,
                closed_at,
                entry_fill_count,
                exit_fill_count,
                total_entry_quantity,
                total_exit_quantity,
                weighted_avg_entry_price,
                weighted_avg_exit_price,
                realized_pnl,
                commission,
                net_pnl,
                exit_reason,
                duration_seconds,
                payload_json
            FROM trade_round_trips
            WHERE closed_at >= ? AND closed_at < ?
            ORDER BY closed_at DESC, id DESC
            """,
            (
                _as_utc_iso(window_start),
                _as_utc_iso(window_end),
            ),
        ).fetchall()
    return [_trade_round_trip_row_to_dict(row) for row in rows]


def fetch_recent_stop_exit_summaries(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                symbol,
                round_trip_id,
                trigger_price,
                average_exit_price,
                slippage_abs,
                slippage_pct,
                exit_quantity,
                realized_pnl,
                commission,
                net_pnl,
                payload_json
            FROM stop_exit_summaries
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "symbol": row[1],
            "round_trip_id": row[2],
            "trigger_price": row[3],
            "average_exit_price": row[4],
            "slippage_abs": row[5],
            "slippage_pct": row[6],
            "exit_quantity": row[7],
            "realized_pnl": row[8],
            "commission": row[9],
            "net_pnl": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]
