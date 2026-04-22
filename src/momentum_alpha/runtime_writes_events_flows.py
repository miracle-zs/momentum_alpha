from __future__ import annotations

from datetime import datetime
from pathlib import Path

from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db

from .runtime_writes_common import _as_utc_iso, _decimal_to_text, _json_dumps


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
