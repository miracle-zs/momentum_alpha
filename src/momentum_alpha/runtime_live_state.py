from __future__ import annotations

from datetime import datetime, timedelta, timezone
import json
import sqlite3
from typing import Any


LIVE_SERIES_RETENTION = timedelta(days=8)
_LIVE_SERIES_WINDOWS = {
    "1H": timedelta(hours=1),
    "1D": timedelta(days=1),
    "1W": timedelta(days=7),
}


def _parse_timestamp(value: object) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value
    elif value in (None, ""):
        return None
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _timestamp_text(value: object) -> str | None:
    parsed = _parse_timestamp(value)
    return parsed.isoformat() if parsed is not None else None


def _bucket_timestamp(value: object) -> str | None:
    parsed = _parse_timestamp(value)
    if parsed is None:
        return None
    return parsed.replace(second=0, microsecond=0).isoformat()


def _json_text(payload: Any) -> str:
    return json.dumps(payload if payload is not None else {}, ensure_ascii=False)


def _json_payload(value: object) -> dict:
    try:
        payload = json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return payload if isinstance(payload, dict) else {}


def upsert_dashboard_live_state(
    *,
    connection: sqlite3.Connection,
    state_key: str,
    timestamp: object,
    payload: dict,
) -> None:
    timestamp_text = _timestamp_text(timestamp)
    if timestamp_text is None:
        return
    connection.execute(
        """
        INSERT INTO dashboard_live_state(state_key, timestamp, payload_json)
        VALUES (?, ?, ?)
        ON CONFLICT(state_key) DO UPDATE SET
            timestamp = excluded.timestamp,
            payload_json = excluded.payload_json
        WHERE excluded.timestamp >= dashboard_live_state.timestamp
        """,
        (state_key, timestamp_text, _json_text(payload)),
    )


def upsert_dashboard_live_series(
    *,
    connection: sqlite3.Connection,
    series_type: str,
    timestamp: object,
    payload: dict,
) -> None:
    bucket_timestamp = _bucket_timestamp(timestamp)
    parsed_timestamp = _parse_timestamp(timestamp)
    if bucket_timestamp is None or parsed_timestamp is None:
        return
    connection.execute(
        """
        INSERT INTO dashboard_live_series(series_type, bucket_timestamp, payload_json)
        VALUES (?, ?, ?)
        ON CONFLICT(series_type, bucket_timestamp) DO UPDATE SET
            payload_json = excluded.payload_json
        WHERE COALESCE(json_extract(excluded.payload_json, '$.timestamp'), excluded.bucket_timestamp)
              >= COALESCE(json_extract(dashboard_live_series.payload_json, '$.timestamp'), dashboard_live_series.bucket_timestamp)
        """,
        (series_type, bucket_timestamp, _json_text(payload)),
    )
    cutoff = (parsed_timestamp - LIVE_SERIES_RETENTION).isoformat()
    connection.execute(
        """
        DELETE FROM dashboard_live_series
        WHERE series_type = ? AND bucket_timestamp < ?
        """,
        (series_type, cutoff),
    )


def read_dashboard_live_state(*, connection: sqlite3.Connection) -> dict[str, dict]:
    try:
        rows = connection.execute(
            """
            SELECT state_key, timestamp, payload_json
            FROM dashboard_live_state
            ORDER BY timestamp DESC
            """
        ).fetchall()
    except sqlite3.OperationalError:
        return {}
    return {
        str(state_key): {
            **_json_payload(payload_json),
            "timestamp": timestamp,
        }
        for state_key, timestamp, payload_json in rows
    }


def read_dashboard_live_series(
    *,
    connection: sqlite3.Connection,
    now: datetime,
    range_key: str,
) -> dict[str, list[dict]]:
    utc_now = now.astimezone(timezone.utc)
    window = _LIVE_SERIES_WINDOWS.get(range_key, LIVE_SERIES_RETENTION)
    cutoff = (utc_now - window).isoformat()
    try:
        rows = connection.execute(
            """
            SELECT series_type, bucket_timestamp, payload_json
            FROM dashboard_live_series
            WHERE bucket_timestamp >= ?
            ORDER BY bucket_timestamp ASC
            """,
            (cutoff,),
        ).fetchall()
    except sqlite3.OperationalError:
        return {"account": [], "position": []}

    series = {"account": [], "position": []}
    for series_type, bucket_timestamp, payload_json in rows:
        if series_type not in series:
            continue
        payload = _json_payload(payload_json)
        payload.setdefault("timestamp", bucket_timestamp)
        series[series_type].append(payload)
    return series


def _latest_snapshot(snapshot: dict, *, runtime_key: str, list_key: str) -> dict | None:
    runtime = snapshot.get("runtime") or {}
    latest = runtime.get(runtime_key)
    if isinstance(latest, dict):
        return latest
    rows = snapshot.get(list_key) or []
    return rows[0] if rows and isinstance(rows[0], dict) else None


def _hydrate_state_if_missing(
    *,
    connection: sqlite3.Connection,
    state: dict[str, dict],
    state_key: str,
    payload: dict | None,
) -> None:
    if state_key in state or not isinstance(payload, dict):
        return
    upsert_dashboard_live_state(
        connection=connection,
        state_key=state_key,
        timestamp=payload.get("timestamp"),
        payload=payload,
    )


def hydrate_dashboard_live_snapshot(*, connection: sqlite3.Connection, snapshot: dict) -> None:
    """Seed the live projection from a full dashboard read exactly once per key/window."""
    try:
        state = read_dashboard_live_state(connection=connection)
        series_types = {
            str(row[0])
            for row in connection.execute(
                "SELECT DISTINCT series_type FROM dashboard_live_series"
            ).fetchall()
        }
    except sqlite3.OperationalError:
        return

    runtime = snapshot.get("runtime") or {}
    state_candidates = {
        "latest_account_snapshot": _latest_snapshot(
            snapshot,
            runtime_key="latest_account_snapshot",
            list_key="recent_account_snapshots",
        ),
        "latest_position_snapshot": _latest_snapshot(
            snapshot,
            runtime_key="latest_position_snapshot",
            list_key="recent_position_snapshots",
        ),
        "latest_signal_decision": runtime.get("latest_signal_decision"),
        "latest_broker_order": runtime.get("latest_broker_order"),
        "latest_trade_fill": (snapshot.get("recent_trade_fills") or [None])[0],
        "latest_algo_order": (snapshot.get("recent_algo_orders") or [None])[0],
        "latest_stop_exit_summary": (snapshot.get("recent_stop_exit_summaries") or [None])[0],
    }
    for state_key, payload in state_candidates.items():
        _hydrate_state_if_missing(
            connection=connection,
            state=state,
            state_key=state_key,
            payload=payload,
        )

    if "account" not in series_types:
        account_rows = sorted(
            (row for row in snapshot.get("recent_account_snapshots") or [] if isinstance(row, dict)),
            key=lambda row: row.get("timestamp") or "",
        )
        for row in account_rows:
            if isinstance(row, dict):
                upsert_dashboard_live_series(
                    connection=connection,
                    series_type="account",
                    timestamp=row.get("timestamp"),
                    payload=row,
                )
    if "position" not in series_types:
        position_rows = sorted(
            (
                row
                for row in (snapshot.get("recent_position_risk_snapshots") or snapshot.get("recent_position_snapshots") or [])
                if isinstance(row, dict)
            ),
            key=lambda row: row.get("timestamp") or "",
        )
        for row in position_rows:
            if isinstance(row, dict):
                upsert_dashboard_live_series(
                    connection=connection,
                    series_type="position",
                    timestamp=row.get("timestamp"),
                    payload=row,
                )
