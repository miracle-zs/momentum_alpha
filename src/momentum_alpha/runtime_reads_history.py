from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _ACCOUNT_RANGE_DENSITY, _as_utc_iso, _json_loads, _trade_round_trip_row_to_dict
from .runtime_reads_events import fetch_recent_audit_events

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
def fetch_latest_daily_review_report(*, path: Path) -> dict | None:
    if not path.exists():
        return None
    with _connect(path) as connection:
        row = connection.execute(
            """
            SELECT
                report_date,
                window_start,
                window_end,
                generated_at,
                status,
                trade_count,
                actual_total_pnl,
                counterfactual_total_pnl,
                pnl_delta,
                replayed_add_on_count,
                stop_budget_usdt,
                entry_start_hour_utc,
                entry_end_hour_utc,
                warning_json,
                payload_json
            FROM daily_review_reports
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """
        ).fetchone()
    if row is None:
        return None
    return {
        "report_date": row[0],
        "window_start": row[1],
        "window_end": row[2],
        "generated_at": row[3],
        "status": row[4],
        "trade_count": row[5],
        "actual_total_pnl": row[6],
        "counterfactual_total_pnl": row[7],
        "pnl_delta": row[8],
        "replayed_add_on_count": row[9],
        "stop_budget_usdt": row[10],
        "entry_start_hour_utc": row[11],
        "entry_end_hour_utc": row[12],
        "warnings": _json_loads(row[13]),
        "payload": _json_loads(row[14]),
    }
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
def fetch_recent_position_snapshots(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                leader_symbol,
                position_count,
                order_status_count,
                symbol_count,
                submit_orders,
                restore_positions,
                execute_stop_replacements,
                payload_json
            FROM position_snapshots
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "leader_symbol": row[2],
            "position_count": row[3],
            "order_status_count": row[4],
            "symbol_count": row[5],
            "submit_orders": bool(row[6]) if row[6] is not None else None,
            "restore_positions": bool(row[7]) if row[7] is not None else None,
            "execute_stop_replacements": bool(row[8]) if row[8] is not None else None,
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]
def fetch_recent_account_snapshots(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                wallet_balance,
                available_balance,
                equity,
                unrealized_pnl,
                position_count,
                open_order_count,
                leader_symbol,
                payload_json
            FROM account_snapshots
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "wallet_balance": row[2],
            "available_balance": row[3],
            "equity": row[4],
            "unrealized_pnl": row[5],
            "position_count": row[6],
            "open_order_count": row[7],
            "leader_symbol": row[8],
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]
def fetch_account_snapshots_for_range(
    *,
    path: Path,
    now: datetime,
    range_key: str,
) -> list[dict]:
    if not path.exists():
        return []
    window, bucket_seconds = _ACCOUNT_RANGE_DENSITY.get(range_key, _ACCOUNT_RANGE_DENSITY["1D"])
    cutoff = None if window is None else now.astimezone(timezone.utc) - window
    where_clause = "" if cutoff is None else "WHERE timestamp >= ?"
    params = () if cutoff is None else (cutoff.isoformat(),)
    with _connect(path) as connection:
        rows = connection.execute(
            f"""
            SELECT
                id,
                timestamp,
                source,
                wallet_balance,
                available_balance,
                equity,
                unrealized_pnl,
                position_count,
                open_order_count,
                leader_symbol,
                payload_json
            FROM (
                SELECT
                    id,
                    timestamp,
                    source,
                    wallet_balance,
                    available_balance,
                    equity,
                    unrealized_pnl,
                    position_count,
                    open_order_count,
                    leader_symbol,
                    payload_json,
                    ROW_NUMBER() OVER (
                        PARTITION BY CAST(strftime('%s', timestamp) / ? AS INTEGER)
                        ORDER BY timestamp DESC, id DESC
                    ) AS rn
                FROM account_snapshots
                {where_clause}
            )
            WHERE rn = 1
            ORDER BY timestamp DESC, id DESC
            """,
            (bucket_seconds, *params),
        ).fetchall()
    return [
        {
            "timestamp": row[1],
            "source": row[2],
            "wallet_balance": row[3],
            "available_balance": row[4],
            "equity": row[5],
            "unrealized_pnl": row[6],
            "position_count": row[7],
            "open_order_count": row[8],
            "leader_symbol": row[9],
            "payload": _json_loads(row[10]),
        }
        for row in rows
    ]
def fetch_leader_history(*, path: Path, limit: int = 10) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, next_leader_symbol AS symbol, 1 AS priority
            FROM signal_decisions
            WHERE next_leader_symbol IS NOT NULL
            UNION ALL
            SELECT timestamp, leader_symbol AS symbol, 0 AS priority
            FROM position_snapshots
            WHERE leader_symbol IS NOT NULL
            ORDER BY timestamp DESC, priority DESC
            LIMIT ?
            """,
            (max(limit, 100),),
        ).fetchall()

    history: list[dict] = []
    previous_symbol: str | None = None
    for timestamp, symbol, _priority in rows:
        if symbol is None or symbol == previous_symbol:
            continue
        history.append({"timestamp": timestamp, "symbol": symbol})
        previous_symbol = symbol
        if len(history) >= limit:
            break
    return history
def fetch_event_pulse_points(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    bucket_minutes: int,
    limit: int = 20,
) -> list[dict]:
    if not path.exists():
        return []
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    bucket_seconds = max(bucket_minutes, 1) * 60
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp FROM signal_decisions WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM broker_orders WHERE timestamp >= ?
            UNION ALL
            SELECT timestamp FROM position_snapshots WHERE timestamp >= ?
            ORDER BY timestamp ASC
            """,
            (
                cutoff.isoformat(),
                cutoff.isoformat(),
                cutoff.isoformat(),
            ),
        ).fetchall()

    counts: dict[str, int] = {}
    for (timestamp_text,) in rows:
        timestamp = datetime.fromisoformat(timestamp_text)
        bucket_start = cutoff + timedelta(
            seconds=int((timestamp - cutoff).total_seconds() // bucket_seconds) * bucket_seconds
        )
        bucket_label = bucket_start.astimezone(timezone.utc).replace(second=0, microsecond=0).isoformat()
        counts[bucket_label] = counts.get(bucket_label, 0) + 1

    return [
        {"bucket": bucket, "event_count": count}
        for bucket, count in sorted(counts.items())[-limit:]
    ]
def summarize_audit_events(
    *,
    path: Path,
    now: datetime,
    since_minutes: int,
    limit: int,
) -> dict:
    cutoff = now.astimezone(timezone.utc) - timedelta(minutes=since_minutes)
    recent_events = [
        event
        for event in fetch_recent_audit_events(path=path, limit=max(limit, 500))
        if datetime.fromisoformat(event["timestamp"]) >= cutoff
    ]
    counts = Counter(event["event_type"] for event in recent_events)
    return {
        "total_events": len(recent_events),
        "counts": dict(sorted(counts.items())),
        "recent_events": recent_events[:limit],
    }
