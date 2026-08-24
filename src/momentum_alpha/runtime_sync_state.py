from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import date, datetime, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db
from momentum_alpha.runtime_writes_common import _json_dumps


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _iso(value: datetime) -> str:
    return _utc(value).isoformat()


def _parse_datetime(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return _utc(parsed)


@dataclass(frozen=True)
class DirtySymbol:
    symbol: str
    first_dirty_at: datetime
    last_dirty_at: datetime
    reasons: tuple[str, ...]
    version: int


@dataclass(frozen=True)
class RuntimeControlRequest:
    key: str
    requested_at: datetime
    reason: str | None


@dataclass(frozen=True)
class RuntimeSyncStateStore:
    """Persist synchronization state behind one small SQLite-backed interface."""

    path: Path

    def load_daily_opens(self, *, trading_day: date) -> dict[str, Decimal]:
        if not self.path.exists():
            return {}
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT symbol, open_price
                FROM daily_open_prices
                WHERE trading_day = ?
                ORDER BY symbol
                """,
                (trading_day.isoformat(),),
            ).fetchall()
        return {str(symbol): Decimal(str(open_price)) for symbol, open_price in rows}

    def save_daily_open(
        self,
        *,
        trading_day: date,
        symbol: str,
        open_price: Decimal,
        source: str,
        observed_at: datetime,
    ) -> None:
        if open_price <= Decimal("0"):
            return
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO daily_open_prices(
                    trading_day, symbol, open_price, source, observed_at
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(trading_day, symbol) DO UPDATE SET
                    open_price = excluded.open_price,
                    source = excluded.source,
                    observed_at = excluded.observed_at
                """,
                (
                    trading_day.isoformat(),
                    symbol.upper(),
                    str(open_price),
                    source,
                    _iso(observed_at),
                ),
            )

    def get_cursor(self, *, kind: str, symbol: str | None = None) -> datetime | None:
        if not self.path.exists():
            return None
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            row = connection.execute(
                """
                SELECT cursor_at
                FROM trade_sync_cursors
                WHERE cursor_kind = ? AND symbol = ?
                """,
                (kind, (symbol or "").upper()),
            ).fetchone()
        return None if row is None else _parse_datetime(row[0])

    def save_cursor(
        self,
        *,
        kind: str,
        cursor_at: datetime,
        updated_at: datetime,
        symbol: str | None = None,
    ) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO trade_sync_cursors(
                    cursor_kind, symbol, cursor_at, updated_at
                ) VALUES (?, ?, ?, ?)
                ON CONFLICT(cursor_kind, symbol) DO UPDATE SET
                    cursor_at = excluded.cursor_at,
                    updated_at = excluded.updated_at
                """,
                (kind, (symbol or "").upper(), _iso(cursor_at), _iso(updated_at)),
            )

    def delete_cursor(self, *, kind: str, symbol: str | None = None) -> bool:
        if not self.path.exists():
            return False
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM trade_sync_cursors
                WHERE cursor_kind = ? AND symbol = ?
                """,
                (kind, (symbol or "").upper()),
            )
        return cursor.rowcount > 0

    def mark_dirty(self, *, symbol: str, reason: str, observed_at: datetime) -> None:
        normalized_symbol = symbol.strip().upper()
        normalized_reason = reason.strip().lower()
        if not normalized_symbol:
            return
        bootstrap_runtime_db(path=self.path)
        observed_text = _iso(observed_at)
        with _connect(self.path) as connection:
            # Serialize read/merge/write so a poll order and a User Stream
            # event cannot move last_dirty_at backwards or lose a reason.
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT first_dirty_at, reasons_json
                FROM trade_sync_dirty_symbols
                WHERE symbol = ?
                """,
                (normalized_symbol,),
            ).fetchone()
            if row is None:
                reasons = [normalized_reason] if normalized_reason else []
                connection.execute(
                    """
                    INSERT INTO trade_sync_dirty_symbols(
                        symbol, first_dirty_at, last_dirty_at, reasons_json, dirty_version
                    ) VALUES (?, ?, ?, ?, 1)
                    """,
                    (normalized_symbol, observed_text, observed_text, _json_dumps(reasons)),
                )
                return
            try:
                reasons = {str(item) for item in json.loads(row[1])}
            except (TypeError, ValueError):
                reasons = set()
            if normalized_reason:
                reasons.add(normalized_reason)
            connection.execute(
                """
                UPDATE trade_sync_dirty_symbols
                SET last_dirty_at = CASE
                        WHEN last_dirty_at >= ? THEN last_dirty_at
                        ELSE ?
                    END,
                    reasons_json = ?,
                    dirty_version = dirty_version + 1
                WHERE symbol = ?
                """,
                (
                    observed_text,
                    observed_text,
                    _json_dumps(sorted(reasons)),
                    normalized_symbol,
                ),
            )

    def dirty_symbols(self, *, limit: int | None = None) -> list[DirtySymbol]:
        if not self.path.exists():
            return []
        bootstrap_runtime_db(path=self.path)
        sql = """
            SELECT symbol, first_dirty_at, last_dirty_at, reasons_json, dirty_version
            FROM trade_sync_dirty_symbols
            ORDER BY first_dirty_at, symbol
        """
        params: tuple[object, ...] = ()
        if limit is not None:
            sql += " LIMIT ?"
            params = (max(0, int(limit)),)
        with _connect(self.path) as connection:
            rows = connection.execute(sql, params).fetchall()
        result: list[DirtySymbol] = []
        for symbol, first_dirty_at, last_dirty_at, reasons_json, dirty_version in rows:
            first = _parse_datetime(first_dirty_at)
            last = _parse_datetime(last_dirty_at)
            if first is None or last is None:
                continue
            try:
                reasons = tuple(sorted(str(item) for item in json.loads(reasons_json)))
            except (TypeError, ValueError):
                reasons = ()
            result.append(
                DirtySymbol(
                    symbol=str(symbol),
                    first_dirty_at=first,
                    last_dirty_at=last,
                    reasons=reasons,
                    version=int(dirty_version),
                )
            )
        return result

    def clear_dirty(self, *, symbol: str, observed_version: int) -> bool:
        """Clear only the version synchronized; concurrent stream events remain dirty."""

        if not self.path.exists():
            return False
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM trade_sync_dirty_symbols
                WHERE symbol = ? AND dirty_version = ?
                """,
                (symbol.upper(), int(observed_version)),
            )
        return cursor.rowcount > 0

    def save_synced_order(
        self,
        *,
        symbol: str,
        order_id: str,
        update_time: datetime | None,
        synced_at: datetime,
        payload: dict,
    ) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO trade_sync_orders(
                    symbol, order_id, update_time, synced_at, payload_json
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(symbol, order_id) DO UPDATE SET
                    update_time = excluded.update_time,
                    synced_at = excluded.synced_at,
                    payload_json = excluded.payload_json
                """,
                (
                    symbol.upper(),
                    str(order_id),
                    None if update_time is None else _iso(update_time),
                    _iso(synced_at),
                    _json_dumps(payload),
                ),
            )

    def request_control(self, *, key: str, requested_at: datetime, reason: str | None = None) -> None:
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            connection.execute(
                """
                INSERT INTO runtime_control_requests(request_key, requested_at, reason)
                VALUES (?, ?, ?)
                ON CONFLICT(request_key) DO UPDATE SET
                    requested_at = excluded.requested_at,
                    reason = excluded.reason
                WHERE excluded.requested_at >= runtime_control_requests.requested_at
                """,
                (key, _iso(requested_at), reason),
            )

    def control_requests(self) -> list[RuntimeControlRequest]:
        if not self.path.exists():
            return []
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            rows = connection.execute(
                """
                SELECT request_key, requested_at, reason
                FROM runtime_control_requests
                ORDER BY requested_at, request_key
                """
            ).fetchall()
        result = []
        for key, requested_at, reason in rows:
            parsed = _parse_datetime(requested_at)
            if parsed is not None:
                result.append(RuntimeControlRequest(str(key), parsed, reason))
        return result

    def clear_control(self, *, key: str, requested_at: datetime) -> bool:
        if not self.path.exists():
            return False
        bootstrap_runtime_db(path=self.path)
        with _connect(self.path) as connection:
            cursor = connection.execute(
                """
                DELETE FROM runtime_control_requests
                WHERE request_key = ? AND requested_at = ?
                """,
                (key, _iso(requested_at)),
            )
        return cursor.rowcount > 0
