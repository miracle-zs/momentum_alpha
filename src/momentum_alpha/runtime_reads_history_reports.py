from __future__ import annotations

import sqlite3
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


def fetch_latest_filtered_base_review_report(*, path: Path) -> dict | None:
    return _fetch_filtered_base_review_report(path=path, report_date=None)


def fetch_filtered_base_review_report_by_date(*, path: Path, report_date: str) -> dict | None:
    return _fetch_filtered_base_review_report(path=path, report_date=report_date)


def fetch_filtered_base_review_report_dates(*, path: Path) -> list[str]:
    if not path.exists():
        return []
    try:
        with _connect(path) as connection:
            rows = connection.execute(
                """
                SELECT report_date
                FROM filtered_base_review_reports
                ORDER BY report_date ASC, id ASC
                """
            ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [str(row[0]) for row in rows]


def _fetch_filtered_base_review_report(*, path: Path, report_date: str | None) -> dict | None:
    if not path.exists():
        return None
    where_clause = "WHERE report_date = ?" if report_date is not None else ""
    parameters = (report_date,) if report_date is not None else ()
    try:
        with _connect(path) as connection:
            row = connection.execute(
                f"""
                SELECT
                    report_date,
                    window_start,
                    window_end,
                    generated_at,
                    status,
                    warning_json,
                    payload_json
                FROM filtered_base_review_reports
                {where_clause}
                ORDER BY generated_at DESC, id DESC
                LIMIT 1
                """,
                parameters,
            ).fetchone()
    except sqlite3.OperationalError:
        return None
    if row is None:
        return None
    return {
        "report_date": row[0],
        "window_start": row[1],
        "window_end": row[2],
        "generated_at": row[3],
        "status": row[4],
        "warnings": _json_loads(row[5]),
        "payload": _json_loads(row[6]),
    }


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


def fetch_filtered_base_review_reports_summary(*, path: Path) -> dict:
    """Aggregate the independently stored filtered-base review reports.

    The filtered review is a counterfactual study, so its history must be
    summed from the filtered report table rather than inferred from daily
    review PnL.  The fallback keeps older databases readable when filtered
    samples were still embedded in daily review payloads.
    """
    empty_summary = _empty_filtered_base_review_reports_summary()
    if not path.exists():
        return _serialize_filtered_base_review_reports_summary(empty_summary)

    try:
        with _connect(path) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM filtered_base_review_reports
                ORDER BY report_date ASC, id ASC
                """
            ).fetchall()
    except (OSError, sqlite3.Error):
        rows = []

    if not rows:
        rows = _fetch_embedded_filtered_review_payloads(path)
    if not rows:
        return _serialize_filtered_base_review_reports_summary(empty_summary)

    summary = _empty_filtered_base_review_reports_summary()
    summary["report_count"] = len(rows)
    for row in rows:
        payload = _safe_json_dict(row[0])
        report_summary = payload.get("summary") or payload.get("filtered_base_summary") or {}
        if not isinstance(report_summary, dict):
            report_summary = {}
        report_rows = payload.get("rows") or payload.get("filtered_base_rows") or []
        if not isinstance(report_rows, list):
            report_rows = []

        closed_rows = [item for item in report_rows if isinstance(item, dict) and item.get("status") == "closed"]
        open_rows = [item for item in report_rows if isinstance(item, dict) and item.get("status") == "open"]
        unresolved_rows = [
            item
            for item in report_rows
            if isinstance(item, dict) and item.get("status") in {"unresolved", "pending_replay"}
        ]
        suppressed_rows = [
            item for item in report_rows if isinstance(item, dict) and item.get("status") == "suppressed"
        ]
        closed_deltas = [
            value
            for item in closed_rows
            if (
                value := _payload_decimal(
                    item,
                    "strategy_pnl_delta",
                    "net_pnl",
                )
            )
            is not None
        ]

        candidate_count = _payload_int(report_summary, "candidate_count", "accepted_count")
        if candidate_count == 0 and not _payload_has_any(report_summary, "candidate_count", "accepted_count"):
            candidate_count = len(closed_rows) + len(open_rows) + len(unresolved_rows)
        closed_count = _payload_int(report_summary, "closed_count")
        if closed_count == 0 and not _payload_has_any(report_summary, "closed_count"):
            closed_count = len(closed_rows)
        open_count = _payload_int(report_summary, "open_count")
        if open_count == 0 and not _payload_has_any(report_summary, "open_count"):
            open_count = len(open_rows)
        unresolved_count = _payload_int(report_summary, "unresolved_count")
        if unresolved_count == 0 and not _payload_has_any(report_summary, "unresolved_count"):
            unresolved_count = len(unresolved_rows)
        pending_count = _payload_int(report_summary, "pending_count")

        missed_profit = _payload_decimal(report_summary, "missed_profit_sum")
        if missed_profit is None:
            missed_profit = sum((value for value in closed_deltas if value > 0), Decimal("0"))
        avoided_loss = _payload_decimal(report_summary, "avoided_loss_sum")
        if avoided_loss is None:
            avoided_loss = abs(sum((value for value in closed_deltas if value < 0), Decimal("0")))
        strategy_delta = _payload_decimal(report_summary, "strategy_pnl_delta")
        if strategy_delta is None:
            strategy_delta = sum(closed_deltas, Decimal("0"))
        counterfactual_pnl = _payload_decimal(
            report_summary,
            "counterfactual_trade_pnl_sum",
            "closed_sample_pnl_sum",
        )
        if counterfactual_pnl is None:
            counterfactual_pnl = sum(
                (
                    value
                    for item in closed_rows
                    if (value := _payload_decimal(item, "net_pnl")) is not None
                ),
                Decimal("0"),
            )
        actual_replaced_pnl = _payload_decimal(report_summary, "actual_replaced_pnl_sum")
        if actual_replaced_pnl is None:
            actual_replaced_pnl = sum(
                (
                    value
                    for item in closed_rows
                    if item.get("actual_trade_id")
                    and (value := _payload_decimal(item, "actual_trade_net_pnl")) is not None
                ),
                Decimal("0"),
            )

        replayed_add_on_count = _payload_int(report_summary, "replayed_add_on_count")
        if not _payload_has_any(report_summary, "replayed_add_on_count"):
            replayed_add_on_count = sum(
                _payload_int(item, "add_on_count")
                for item in (*closed_rows, *open_rows)
            )
        suppressed_count = _payload_int(report_summary, "suppressed_count")
        if not _payload_has_any(report_summary, "suppressed_count"):
            suppressed_count = len(suppressed_rows)
        tail_50u_count = _payload_int(report_summary, "tail_50u_count")
        if not _payload_has_any(report_summary, "tail_50u_count"):
            tail_50u_count = sum(1 for item in report_rows if item.get("is_long_tail_50u"))

        summary["candidate_count"] += candidate_count
        summary["closed_count"] += closed_count
        summary["open_count"] += open_count
        summary["unresolved_count"] += unresolved_count
        summary["pending_count"] += pending_count
        summary["suppressed_count"] += suppressed_count
        win_count = _payload_int(report_summary, "win_count")
        if not _payload_has_any(report_summary, "win_count"):
            win_count = sum(1 for value in closed_deltas if value > 0)
        loss_count = _payload_int(report_summary, "loss_count")
        if not _payload_has_any(report_summary, "loss_count"):
            loss_count = sum(1 for value in closed_deltas if value < 0)

        summary["win_count"] += win_count
        summary["loss_count"] += loss_count
        summary["missed_profit_sum"] += missed_profit
        summary["avoided_loss_sum"] += avoided_loss
        summary["counterfactual_trade_pnl_sum"] += counterfactual_pnl
        summary["actual_replaced_pnl_sum"] += actual_replaced_pnl
        summary["strategy_pnl_delta"] += strategy_delta
        summary["replayed_add_on_count"] += replayed_add_on_count
        summary["tail_50u_count"] += tail_50u_count

    return _serialize_filtered_base_review_reports_summary(summary)


def _serialize_filtered_base_review_reports_summary(summary: dict) -> dict:
    for key in (
        "missed_profit_sum",
        "avoided_loss_sum",
        "counterfactual_trade_pnl_sum",
        "actual_replaced_pnl_sum",
        "strategy_pnl_delta",
    ):
        summary[key] = str(summary[key])
    return summary


def _empty_filtered_base_review_reports_summary() -> dict:
    return {
        "report_count": 0,
        "candidate_count": 0,
        "closed_count": 0,
        "open_count": 0,
        "unresolved_count": 0,
        "pending_count": 0,
        "suppressed_count": 0,
        "win_count": 0,
        "loss_count": 0,
        "missed_profit_sum": Decimal("0"),
        "avoided_loss_sum": Decimal("0"),
        "counterfactual_trade_pnl_sum": Decimal("0"),
        "actual_replaced_pnl_sum": Decimal("0"),
        "strategy_pnl_delta": Decimal("0"),
        "replayed_add_on_count": 0,
        "tail_50u_count": 0,
    }


def _fetch_embedded_filtered_review_payloads(path: Path) -> list[tuple]:
    try:
        with _connect(path) as connection:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM daily_review_reports
                ORDER BY report_date ASC, id ASC
                """
            ).fetchall()
    except (OSError, sqlite3.Error):
        return []
    return [row for row in rows if _payload_contains_filtered_review(row[0])]


def _payload_contains_filtered_review(raw_payload: str) -> bool:
    payload = _safe_json_dict(raw_payload)
    return "filtered_base_summary" in payload or "filtered_base_rows" in payload


def _safe_json_dict(raw_payload: str) -> dict:
    try:
        payload = _json_loads(raw_payload)
    except (TypeError, ValueError):
        return {}
    return payload if isinstance(payload, dict) else {}


def _payload_has_any(payload: dict, *keys: str) -> bool:
    return any(key in payload and payload.get(key) is not None for key in keys)


def _payload_int(payload: dict, *keys: str) -> int:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return int(Decimal(str(value)))
        except (ArithmeticError, TypeError, ValueError):
            continue
    return 0


def _payload_decimal(payload: dict, *keys: str) -> Decimal | None:
    for key in keys:
        value = payload.get(key)
        if value is None or value == "":
            continue
        try:
            return Decimal(str(value))
        except (ArithmeticError, TypeError, ValueError):
            continue
    return None
