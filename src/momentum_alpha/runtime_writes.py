from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _bool_to_int(value: bool | None) -> int | None:
    if value is None:
        return None
    return 1 if value else 0


def _decimal_to_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def save_notification_status(*, path: Path, status_key: str, status: str, timestamp: datetime) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO notification_statuses(status_key, status, updated_at)
            VALUES (?, ?, ?)
            ON CONFLICT(status_key) DO UPDATE SET
                status = excluded.status,
                updated_at = excluded.updated_at
            """,
            (status_key, status, _as_utc_iso(timestamp)),
        )


def insert_audit_event(
    *,
    path: Path,
    timestamp: datetime,
    event_type: str,
    payload: dict,
    source: str | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            "INSERT INTO audit_events(timestamp, event_type, payload_json, source) VALUES (?, ?, ?, ?)",
            (_as_utc_iso(timestamp), event_type, _json_dumps(payload), source),
        )


def insert_signal_decision(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    decision_type: str,
    symbol: str | None = None,
    previous_leader_symbol: str | None = None,
    next_leader_symbol: str | None = None,
    position_count: int | None = None,
    order_status_count: int | None = None,
    broker_response_count: int | None = None,
    stop_replacement_count: int | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO signal_decisions(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                decision_type,
                symbol,
                previous_leader_symbol,
                next_leader_symbol,
                position_count,
                order_status_count,
                broker_response_count,
                stop_replacement_count,
                _json_dumps(payload or {}),
            ),
        )


def insert_broker_order(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    action_type: str,
    order_type: str | None = None,
    symbol: str | None = None,
    order_id: str | None = None,
    client_order_id: str | None = None,
    order_status: str | None = None,
    status: str | None = None,
    side: str | None = None,
    quantity: float | None = None,
    price: float | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_order_status = order_status if order_status is not None else status
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO broker_orders(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                action_type,
                order_type,
                order_id,
                client_order_id,
                normalized_order_status,
                side,
                quantity,
                price,
                _json_dumps(payload or {}),
            ),
        )


def insert_trade_fill(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    symbol: str | None = None,
    order_id: str | None = None,
    trade_id: str | None = None,
    client_order_id: str | None = None,
    order_status: str | None = None,
    execution_type: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    quantity: object | None = None,
    cumulative_quantity: object | None = None,
    average_price: object | None = None,
    last_price: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    commission_asset: str | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO trade_fills(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                order_id,
                trade_id,
                client_order_id,
                order_status,
                execution_type,
                side,
                order_type,
                _decimal_to_text(quantity),
                _decimal_to_text(cumulative_quantity),
                _decimal_to_text(average_price),
                _decimal_to_text(last_price),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                commission_asset,
                _json_dumps(payload or {}),
            ),
        )


def insert_algo_order(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    symbol: str | None = None,
    algo_id: str | None = None,
    client_algo_id: str | None = None,
    algo_status: str | None = None,
    side: str | None = None,
    order_type: str | None = None,
    trigger_price: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO algo_orders(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                symbol,
                algo_id,
                client_algo_id,
                algo_status,
                side,
                order_type,
                _decimal_to_text(trigger_price),
                _json_dumps(payload or {}),
            ),
        )


def insert_account_flow(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    reason: str | None = None,
    asset: str | None = None,
    wallet_balance: object | None = None,
    cross_wallet_balance: object | None = None,
    balance_change: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO account_flows(
                timestamp,
                source,
                reason,
                asset,
                wallet_balance,
                cross_wallet_balance,
                balance_change,
                payload_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                reason,
                asset,
                _decimal_to_text(wallet_balance),
                _decimal_to_text(cross_wallet_balance),
                _decimal_to_text(balance_change),
                _json_dumps(payload or {}),
            ),
        )


def insert_trade_round_trip(
    *,
    path: Path,
    round_trip_id: str,
    symbol: str,
    opened_at: datetime,
    closed_at: datetime,
    entry_fill_count: int,
    exit_fill_count: int,
    total_entry_quantity: object | None = None,
    total_exit_quantity: object | None = None,
    weighted_avg_entry_price: object | None = None,
    weighted_avg_exit_price: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    net_pnl: object | None = None,
    exit_reason: str | None = None,
    duration_seconds: int | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO trade_round_trips(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                round_trip_id,
                symbol,
                _as_utc_iso(opened_at),
                _as_utc_iso(closed_at),
                entry_fill_count,
                exit_fill_count,
                _decimal_to_text(total_entry_quantity),
                _decimal_to_text(total_exit_quantity),
                _decimal_to_text(weighted_avg_entry_price),
                _decimal_to_text(weighted_avg_exit_price),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                _decimal_to_text(net_pnl),
                exit_reason,
                duration_seconds,
                _json_dumps(payload or {}),
            ),
        )


def insert_daily_review_report(
    *,
    path: Path,
    report_date: str,
    window_start: str,
    window_end: str,
    generated_at: str,
    status: str,
    trade_count: int,
    actual_total_pnl: str,
    counterfactual_total_pnl: str,
    pnl_delta: str,
    replayed_add_on_count: int,
    stop_budget_usdt: str,
    entry_start_hour_utc: int,
    entry_end_hour_utc: int,
    warnings: list[str],
    payload: dict,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO daily_review_reports(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(report_date) DO UPDATE SET
                window_start=excluded.window_start,
                window_end=excluded.window_end,
                generated_at=excluded.generated_at,
                status=excluded.status,
                trade_count=excluded.trade_count,
                actual_total_pnl=excluded.actual_total_pnl,
                counterfactual_total_pnl=excluded.counterfactual_total_pnl,
                pnl_delta=excluded.pnl_delta,
                replayed_add_on_count=excluded.replayed_add_on_count,
                stop_budget_usdt=excluded.stop_budget_usdt,
                entry_start_hour_utc=excluded.entry_start_hour_utc,
                entry_end_hour_utc=excluded.entry_end_hour_utc,
                warning_json=excluded.warning_json,
                payload_json=excluded.payload_json
            """,
            (
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
                _json_dumps(warnings),
                _json_dumps(payload),
            ),
        )


def insert_stop_exit_summary(
    *,
    path: Path,
    timestamp: datetime,
    symbol: str,
    round_trip_id: str,
    trigger_price: object | None = None,
    average_exit_price: object | None = None,
    slippage_abs: object | None = None,
    slippage_pct: object | None = None,
    exit_quantity: object | None = None,
    realized_pnl: object | None = None,
    commission: object | None = None,
    net_pnl: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO stop_exit_summaries(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                symbol,
                round_trip_id,
                _decimal_to_text(trigger_price),
                _decimal_to_text(average_exit_price),
                _decimal_to_text(slippage_abs),
                _decimal_to_text(slippage_pct),
                _decimal_to_text(exit_quantity),
                _decimal_to_text(realized_pnl),
                _decimal_to_text(commission),
                _decimal_to_text(net_pnl),
                _json_dumps(payload or {}),
            ),
        )


def insert_position_snapshot(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    leader_symbol: str | None = None,
    previous_leader_symbol: str | None = None,
    position_count: int,
    order_status_count: int,
    symbol_count: int | None = None,
    submit_orders: bool | None = None,
    restore_positions: bool | None = None,
    execute_stop_replacements: bool | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    normalized_leader_symbol = leader_symbol if leader_symbol is not None else previous_leader_symbol
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO position_snapshots(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                normalized_leader_symbol,
                position_count,
                order_status_count,
                symbol_count,
                _bool_to_int(submit_orders),
                _bool_to_int(restore_positions),
                _bool_to_int(execute_stop_replacements),
                _json_dumps(payload or {}),
            ),
        )


def insert_account_snapshot(
    *,
    path: Path,
    timestamp: datetime,
    source: str | None,
    position_count: int,
    open_order_count: int,
    leader_symbol: str | None = None,
    wallet_balance: object | None = None,
    available_balance: object | None = None,
    equity: object | None = None,
    unrealized_pnl: object | None = None,
    payload: dict | None = None,
) -> None:
    bootstrap_runtime_db(path=path)
    with _connect(path) as connection:
        connection.execute(
            """
            INSERT INTO account_snapshots(
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
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                _as_utc_iso(timestamp),
                source,
                _decimal_to_text(wallet_balance),
                _decimal_to_text(available_balance),
                _decimal_to_text(equity),
                _decimal_to_text(unrealized_pnl),
                position_count,
                open_order_count,
                leader_symbol,
                _json_dumps(payload or {}),
            ),
        )
