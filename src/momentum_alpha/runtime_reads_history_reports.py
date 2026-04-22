from __future__ import annotations

from decimal import Decimal
from pathlib import Path

from momentum_alpha.runtime_schema import _connect

from .runtime_reads_common import _json_loads


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


def fetch_daily_review_report_by_date(*, path: Path, report_date: str) -> dict | None:
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
            WHERE report_date = ?
            ORDER BY generated_at DESC, id DESC
            LIMIT 1
            """,
            (report_date,),
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


def fetch_daily_review_report_dates(*, path: Path) -> list[str]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT report_date
            FROM daily_review_reports
            ORDER BY report_date ASC, id ASC
            """
        ).fetchall()
    return [str(row[0]) for row in rows]


def fetch_daily_review_reports_summary(*, path: Path) -> dict:
    if not path.exists():
        return {
            "report_count": 0,
            "trade_count": 0,
            "actual_total_pnl": "0",
            "counterfactual_total_pnl": "0",
            "filter_impact": "0",
            "replayed_add_on_count": 0,
        }
    with _connect(path) as connection:
        rows = connection.execute(
            """
            SELECT
                trade_count,
                actual_total_pnl,
                counterfactual_total_pnl,
                replayed_add_on_count
            FROM daily_review_reports
            ORDER BY report_date ASC, id ASC
            """
        ).fetchall()
    report_count = len(rows)
    trade_count = sum(int(row[0] or 0) for row in rows)
    actual_total_pnl = sum((Decimal(str(row[1] or "0")) for row in rows), Decimal("0"))
    counterfactual_total_pnl = sum((Decimal(str(row[2] or "0")) for row in rows), Decimal("0"))
    replayed_add_on_count = sum(int(row[3] or 0) for row in rows)
    filter_impact = actual_total_pnl - counterfactual_total_pnl
    return {
        "report_count": report_count,
        "trade_count": trade_count,
        "actual_total_pnl": str(actual_total_pnl),
        "counterfactual_total_pnl": str(counterfactual_total_pnl),
        "filter_impact": str(filter_impact),
        "replayed_add_on_count": replayed_add_on_count,
    }
