from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone

_ACCOUNT_RANGE_DENSITY: dict[str, tuple[timedelta | None, int]] = {
    "1H": (timedelta(hours=1), 60),
    "1D": (timedelta(days=1), 5 * 60),
    "1W": (timedelta(days=7), 60 * 60),
    "1M": (timedelta(days=30), 4 * 60 * 60),
    "1Y": (timedelta(days=365), 24 * 60 * 60),
    "ALL": (None, 24 * 60 * 60),
}

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
