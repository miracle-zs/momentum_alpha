from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso, _decimal_to_text, _json_dumps


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
