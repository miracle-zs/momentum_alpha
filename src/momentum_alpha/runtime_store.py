from __future__ import annotations

import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_analytics import rebuild_trade_analytics
from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db
from momentum_alpha.runtime_writes import (
    insert_account_flow,
    insert_account_snapshot,
    insert_audit_event,
    insert_algo_order,
    insert_broker_order,
    insert_daily_review_report,
    insert_position_snapshot,
    insert_signal_decision,
    insert_stop_exit_summary,
    insert_trade_fill,
    insert_trade_round_trip,
    save_notification_status,
)
from momentum_alpha.strategy_state_codec import (
    StoredStrategyState,
    deserialize_strategy_state,
    serialize_strategy_state,
)


MAX_PROCESSED_EVENT_ID_AGE_HOURS = 24


@dataclass(frozen=True)
class RuntimeStateStore:
    path: Path

    def load(self) -> StoredStrategyState | None:
        if not self.path.exists():
            return None
        with _connect(self.path) as connection:
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
        if not row:
            return None
        return deserialize_strategy_state(json.loads(row[0]))

    def save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(state)),),
            )

    def merge_save(self, state: StoredStrategyState) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = deserialize_strategy_state(json.loads(row[0])) if row else None
            merged = StoredStrategyState(
                current_day=state.current_day,
                previous_leader_symbol=state.previous_leader_symbol,
                positions=state.positions if state.positions is not None else (existing.positions if existing is not None else None),
                processed_event_ids=(
                    state.processed_event_ids
                    if state.processed_event_ids is not None
                    else (existing.processed_event_ids if existing is not None else None)
                ),
                order_statuses=(
                    state.order_statuses
                    if state.order_statuses is not None
                    else (existing.order_statuses if existing is not None else None)
                ),
                recent_stop_loss_exits=(
                    state.recent_stop_loss_exits
                    if state.recent_stop_loss_exits is not None
                    else (existing.recent_stop_loss_exits if existing is not None else None)
                ),
            )
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(merged)),),
            )

    def atomic_update(
        self,
        updater: "Callable[[StoredStrategyState | None], StoredStrategyState]",
    ) -> StoredStrategyState:
        """Atomically update state within a single transaction.

        This method ensures that the read-modify-write operation is atomic,
        preventing race conditions between poll and user-stream processes.

        Args:
            updater: A function that takes the current state and returns the new state.
                     The function should merge its changes with the existing state.

        Returns:
            The new state after update.
        """
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute("SELECT payload_json FROM strategy_state WHERE id = 1").fetchone()
            existing = deserialize_strategy_state(json.loads(row[0])) if row else None
            new_state = updater(existing)
            connection.execute(
                "INSERT OR REPLACE INTO strategy_state(id, payload_json) VALUES (1, ?)",
                (_json_dumps(serialize_strategy_state(new_state)),),
            )
            return new_state

def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(payload: str) -> dict:
    return json.loads(payload)


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _trade_round_trip_row_to_dict(row: tuple) -> dict:
    return {
        "round_trip_id": row[0],
        "symbol": row[1],
        "opened_at": row[2],
        "closed_at": row[3],
        "entry_fill_count": row[4],
        "exit_fill_count": row[5],
        "total_entry_quantity": row[6],
        "total_exit_quantity": row[7],
        "weighted_avg_entry_price": row[8],
        "weighted_avg_exit_price": row[9],
        "realized_pnl": row[10],
        "commission": row[11],
        "net_pnl": row[12],
        "exit_reason": row[13],
        "duration_seconds": row[14],
        "payload": _json_loads(row[15]),
    }


def fetch_notification_status(*, path: Path, status_key: str) -> dict | None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        row = connection.execute(
            "SELECT status, updated_at FROM notification_statuses WHERE status_key = ?",
            (status_key,),
        ).fetchone()
    if row is None:
        return None
    return {"status": row[0], "updated_at": row[1]}


def fetch_recent_audit_events(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT timestamp, event_type, payload_json, source
            FROM audit_events
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "event_type": row[1],
            "payload": _json_loads(row[2]),
            "source": row[3],
        }
        for row in rows
    ]


def fetch_audit_event_counts(*, path: Path, limit: int = 1000) -> dict[str, int]:
    if not path.exists():
        return {}
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT event_type, COUNT(*)
            FROM (
                SELECT event_type
                FROM audit_events
                ORDER BY timestamp DESC, id DESC
                LIMIT ?
            )
            GROUP BY event_type
            """,
            (limit,),
        ).fetchall()
    return {event_type: count for event_type, count in rows}


def fetch_recent_signal_decisions(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                payload_json
            FROM signal_decisions
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "decision_type": row[2],
            "symbol": row[3],
            "previous_leader_symbol": row[4],
            "next_leader_symbol": row[5],
            "position_count": row[6],
            "order_status_count": row[7],
            "broker_response_count": row[8],
            "stop_replacement_count": row[9],
            "payload": _json_loads(row[10]),
        }
        for row in rows
    ]


def fetch_signal_decisions_for_window(*, path: Path, window_start: datetime, window_end: datetime) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                payload_json
            FROM signal_decisions
            WHERE timestamp >= ? AND timestamp < ?
            ORDER BY timestamp DESC, id DESC
            """,
            (
                _as_utc_iso(window_start),
                _as_utc_iso(window_end),
            ),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "decision_type": row[2],
            "symbol": row[3],
            "previous_leader_symbol": row[4],
            "next_leader_symbol": row[5],
            "position_count": row[6],
            "order_status_count": row[7],
            "broker_response_count": row[8],
            "stop_replacement_count": row[9],
            "payload": _json_loads(row[10]),
        }
        for row in rows
    ]


def fetch_recent_broker_orders(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                order_status,
                side,
                quantity,
                price,
                payload_json
            FROM broker_orders
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "action_type": row[3],
            "order_type": row[4],
            "order_id": row[5],
            "client_order_id": row[6],
            "order_status": row[7],
            "side": row[8],
            "quantity": row[9],
            "price": row[10],
            "payload": _json_loads(row[11]),
        }
        for row in rows
    ]


def fetch_recent_trade_fills(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                order_status,
                execution_type,
                side,
                order_type,
                quantity,
                cumulative_quantity,
                average_price,
                last_price,
                realized_pnl,
                commission,
                commission_asset,
                payload_json
            FROM trade_fills
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "order_id": row[3],
            "trade_id": row[4],
            "client_order_id": row[5],
            "order_status": row[6],
            "execution_type": row[7],
            "side": row[8],
            "order_type": row[9],
            "quantity": row[10],
            "cumulative_quantity": row[11],
            "average_price": row[12],
            "last_price": row[13],
            "realized_pnl": row[14],
            "commission": row[15],
            "commission_asset": row[16],
            "payload": _json_loads(row[17]),
        }
        for row in rows
    ]


def fetch_recent_algo_orders(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                symbol,
                algo_id,
                client_algo_id,
                algo_status,
                side,
                order_type,
                trigger_price,
                payload_json
            FROM algo_orders
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "symbol": row[2],
            "algo_id": row[3],
            "client_algo_id": row[4],
            "algo_status": row[5],
            "side": row[6],
            "order_type": row[7],
            "trigger_price": row[8],
            "payload": _json_loads(row[9]),
        }
        for row in rows
    ]


def fetch_recent_account_flows(*, path: Path, limit: int = 20) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            FROM account_flows
            ORDER BY timestamp DESC, id DESC
            LIMIT ?
            """,
            (limit,),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "reason": row[2],
            "asset": row[3],
            "wallet_balance": row[4],
            "cross_wallet_balance": row[5],
            "balance_change": row[6],
            "payload": _json_loads(row[7]),
        }
        for row in rows
    ]


def fetch_account_flows_since(*, path: Path, since: datetime) -> list[dict]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            FROM account_flows
            WHERE timestamp >= ?
            ORDER BY timestamp DESC, id DESC
            """,
            (since.astimezone(timezone.utc).isoformat(),),
        ).fetchall()
    return [
        {
            "timestamp": row[0],
            "source": row[1],
            "reason": row[2],
            "asset": row[3],
            "wallet_balance": row[4],
            "cross_wallet_balance": row[5],
            "balance_change": row[6],
            "payload": _json_loads(row[7]),
        }
        for row in rows
    ]


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


_ACCOUNT_RANGE_DENSITY: dict[str, tuple[timedelta | None, int]] = {
    "1H": (timedelta(hours=1), 60),
    "1D": (timedelta(days=1), 5 * 60),
    "1W": (timedelta(days=7), 60 * 60),
    "1M": (timedelta(days=30), 4 * 60 * 60),
    "1Y": (timedelta(days=365), 24 * 60 * 60),
    "ALL": (None, 24 * 60 * 60),
}


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
