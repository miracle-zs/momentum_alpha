from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_store import insert_account_flow


def _account_flow_exists(
    *,
    runtime_db_path: Path,
    timestamp: datetime,
    reason: str | None,
    asset: str | None,
    balance_change: str | None,
) -> bool:
    if not runtime_db_path.exists():
        return False
    connection = sqlite3.connect(runtime_db_path)
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM account_flows
            WHERE timestamp = ?
              AND COALESCE(reason, '') = COALESCE(?, '')
              AND COALESCE(asset, '') = COALESCE(?, '')
              AND COALESCE(balance_change, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (timestamp.astimezone(timezone.utc).isoformat(), reason, asset, balance_change),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def backfill_account_flows(
    *,
    client,
    runtime_db_path: Path,
    start_time: datetime,
    end_time: datetime,
    logger=print,
) -> int:
    inserted = 0
    window_start = start_time.astimezone(timezone.utc)
    end_time_utc = end_time.astimezone(timezone.utc)
    while window_start < end_time_utc:
        window_end = min(window_start + timedelta(days=7), end_time_utc)
        incomes = client.fetch_income_history(
            income_type="TRANSFER",
            start_time_ms=int(window_start.timestamp() * 1000),
            end_time_ms=int(window_end.timestamp() * 1000),
            limit=1000,
        )
        for income in incomes:
            timestamp_ms = income.get("time")
            if timestamp_ms in (None, ""):
                continue
            timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
            reason = str(income.get("info") or income.get("incomeType") or "").upper() or None
            asset = income.get("asset")
            balance_change = str(income.get("income")) if income.get("income") not in (None, "") else None
            if _account_flow_exists(
                runtime_db_path=runtime_db_path,
                timestamp=timestamp,
                reason=reason,
                asset=asset,
                balance_change=balance_change,
            ):
                continue
            insert_account_flow(
                path=runtime_db_path,
                timestamp=timestamp,
                source="backfill-income-history",
                reason=reason,
                asset=asset,
                balance_change=balance_change,
                payload=income,
            )
            inserted += 1
        logger(
            "backfill-account-flows "
            f"window_start={window_start.isoformat()} window_end={window_end.isoformat()} "
            f"fetched={len(incomes)} inserted={inserted}"
        )
        window_start = window_end
    return inserted
