from __future__ import annotations

from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _json_dumps


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
