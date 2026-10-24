from __future__ import annotations

import argparse
import os
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Callable
from urllib.request import urlopen

from momentum_alpha.runtime_store import (
    fetch_notification_status,
    fetch_recent_account_snapshots,
    save_notification_status,
)
from momentum_alpha.serverchan import _send_notification


STATUS_KEY = "available_balance_below_threshold"


def _as_decimal(value: object) -> Decimal | None:
    if value is None:
        return None
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed.is_finite() else None


def _format_amount(value: object) -> str:
    parsed = _as_decimal(value)
    return "未知" if parsed is None else f"{parsed:.2f} USDT"


def process_available_balance_notification(
    *,
    sendkey: str,
    runtime_db_path: Path,
    threshold_usdt: Decimal = Decimal("100"),
    now: datetime,
    hostname: str,
    opener=urlopen,
) -> dict:
    snapshots = fetch_recent_account_snapshots(path=runtime_db_path, limit=1)
    if not snapshots:
        return {"status": "UNKNOWN", "notified": False, "available_balance": None}

    snapshot = snapshots[0]
    available_balance = _as_decimal(snapshot.get("available_balance"))
    if available_balance is None:
        return {"status": "UNKNOWN", "notified": False, "available_balance": None}

    current_status = "LOW" if available_balance < threshold_usdt else "OK"
    previous = fetch_notification_status(path=runtime_db_path, status_key=STATUS_KEY)
    previous_status = None if previous is None else previous.get("status")
    notified = False

    if current_status == "LOW" and previous_status != "LOW":
        title = f"Momentum Alpha 可用保证金低于阈值 @ {hostname}"
        body = (
            f"可用保证金: {_format_amount(available_balance)}\n"
            f"告警阈值: {_format_amount(threshold_usdt)}\n"
            f"钱包余额: {_format_amount(snapshot.get('wallet_balance'))}\n"
            f"账户权益: {_format_amount(snapshot.get('equity'))}\n"
            f"持仓数: {snapshot.get('position_count', '未知')}\n"
            f"快照时间: {snapshot.get('timestamp', '未知')}\n"
        )
        _send_notification(sendkey=sendkey, title=title, body=body, opener=opener)
        notified = True

    if current_status != previous_status:
        save_notification_status(
            path=runtime_db_path,
            status_key=STATUS_KEY,
            status=current_status,
            timestamp=now,
        )

    return {
        "status": current_status,
        "previous_status": previous_status,
        "notified": notified,
        "available_balance": available_balance,
        "snapshot_timestamp": snapshot.get("timestamp"),
    }


def cli_main(
    *,
    argv: list[str] | None = None,
    now_provider: Callable[[], datetime] | None = None,
    opener=urlopen,
    stdout=None,
) -> int:
    parser = argparse.ArgumentParser(prog="momentum_alpha.available_balance_alert")
    parser.add_argument("--sendkey", default=os.environ.get("SERVERCHAN_SENDKEY"))
    parser.add_argument("--runtime-db-file", default=os.environ.get("RUNTIME_DB_FILE"))
    parser.add_argument(
        "--threshold-usdt",
        type=Decimal,
        default=Decimal(os.environ.get("AVAILABLE_BALANCE_ALERT_THRESHOLD_USDT", "100")),
    )
    parser.add_argument("--hostname", default=os.uname().nodename)
    args = parser.parse_args(argv)
    if not args.sendkey:
        parser.error("SERVERCHAN_SENDKEY is required")
    if not args.runtime_db_file:
        parser.error("RUNTIME_DB_FILE is required")

    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    stdout = stdout or __import__("sys").stdout
    result = process_available_balance_notification(
        sendkey=args.sendkey,
        runtime_db_path=Path(os.path.abspath(args.runtime_db_file)),
        threshold_usdt=args.threshold_usdt,
        now=now_provider(),
        hostname=args.hostname,
        opener=opener,
    )
    available = result["available_balance"]
    available_text = "unknown" if available is None else f"{available:.2f}"
    stdout.write(
        f"status={result['status']} available_balance={available_text} "
        f"notified={'yes' if result['notified'] else 'no'}\n"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
