from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.runtime_reads_events_orders import resolve_order_linkage
from momentum_alpha.runtime_schema import bootstrap_runtime_db
from momentum_alpha.runtime_store import insert_account_flow, insert_audit_event, insert_trade_fill
from momentum_alpha.structured_log import emit_structured_log


def _account_flow_exists(
    *,
    runtime_db_path: Path,
    timestamp: datetime,
    reason: str | None,
    asset: str | None,
    balance_change: str | None,
    source: str | None = None,
    reference_id: str | None = None,
) -> bool:
    if not runtime_db_path.exists():
        return False
    connection = sqlite3.connect(runtime_db_path)
    try:
        if reference_id is not None:
            rows = connection.execute(
                """
                SELECT payload_json
                FROM account_flows
                WHERE timestamp = ?
                  AND COALESCE(source, '') = COALESCE(?, '')
                """,
                (timestamp.astimezone(timezone.utc).isoformat(), source),
            ).fetchall()
            for row in rows:
                try:
                    payload = json.loads(row[0])
                except (TypeError, json.JSONDecodeError):
                    continue
                if _income_reference_id(payload) == reference_id:
                    return True
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
    income_types: list[str] | tuple[str, ...] | None = None,
    logger=print,
) -> int:
    inserted = 0
    end_time_utc = end_time.astimezone(timezone.utc)
    normalized_income_types = tuple(
        str(income_type).strip().upper() for income_type in (income_types or ("TRANSFER",)) if str(income_type).strip()
    )
    for income_type in normalized_income_types:
        window_start = start_time.astimezone(timezone.utc)
        while window_start < end_time_utc:
            window_end = min(window_start + timedelta(days=7), end_time_utc)
            incomes = client.fetch_income_history(
                income_type=income_type,
                start_time_ms=int(window_start.timestamp() * 1000),
                end_time_ms=int(window_end.timestamp() * 1000),
                limit=1000,
            )
            for income in incomes:
                timestamp_ms = income.get("time")
                if timestamp_ms in (None, ""):
                    continue
                timestamp = datetime.fromtimestamp(int(timestamp_ms) / 1000, tz=timezone.utc)
                reason = _income_reason(income)
                asset = income.get("asset")
                balance_change = str(income.get("income")) if income.get("income") not in (None, "") else None
                source = "backfill-income-history"
                if _account_flow_exists(
                    runtime_db_path=runtime_db_path,
                    timestamp=timestamp,
                    reason=reason,
                    asset=asset,
                    balance_change=balance_change,
                    source=source,
                    reference_id=_income_reference_id(income),
                ):
                    continue
                insert_account_flow(
                    path=runtime_db_path,
                    timestamp=timestamp,
                    source=source,
                    reason=reason,
                    asset=asset,
                    balance_change=balance_change,
                    payload=income,
                )
                inserted += 1
            logger(
                "backfill-account-flows "
                f"income_type={income_type} "
                f"window_start={window_start.isoformat()} window_end={window_end.isoformat()} "
                f"fetched={len(incomes)} inserted={inserted}"
            )
            window_start = window_end
    return inserted


def _income_reason(income: dict) -> str | None:
    reason = str(income.get("incomeType") or income.get("info") or "").strip().upper()
    return reason or None


def _income_reference_id(income: dict) -> str | None:
    for key in ("tranId", "tradeId"):
        value = income.get(key)
        if value not in (None, ""):
            return f"{key}:{value}"
    return None


def _trade_fill_exists(
    *,
    runtime_db_path: Path,
    symbol: str | None,
    trade_id: str | None,
) -> bool:
    if not runtime_db_path.exists() or trade_id in (None, ""):
        return False
    connection = sqlite3.connect(runtime_db_path)
    try:
        row = connection.execute(
            """
            SELECT 1
            FROM trade_fills
            WHERE COALESCE(symbol, '') = COALESCE(?, '')
              AND COALESCE(trade_id, '') = COALESCE(?, '')
            LIMIT 1
            """,
            (symbol, trade_id),
        ).fetchone()
    finally:
        connection.close()
    return row is not None


def _infer_backfill_symbols(
    *,
    runtime_db_path: Path,
    start_time: datetime,
    end_time: datetime,
) -> list[str]:
    if not runtime_db_path.exists():
        return []
    bootstrap_runtime_db(path=runtime_db_path)
    start_text = start_time.astimezone(timezone.utc).isoformat()
    end_text = end_time.astimezone(timezone.utc).isoformat()
    tables = ("broker_orders", "trade_fills", "algo_orders", "signal_decisions")
    symbols: set[str] = set()
    connection = sqlite3.connect(runtime_db_path)
    try:
        for table in tables:
            rows = connection.execute(
                f"""
                SELECT DISTINCT symbol
                FROM {table}
                WHERE timestamp >= ?
                  AND timestamp < ?
                  AND symbol IS NOT NULL
                  AND symbol != ''
                """,
                (start_text, end_text),
            ).fetchall()
            symbols.update(str(row[0]).upper() for row in rows if row[0])
    finally:
        connection.close()
    return sorted(symbols)


def _window_ranges(*, start_time: datetime, end_time: datetime, max_window: timedelta):
    window_start = start_time.astimezone(timezone.utc)
    end_time_utc = end_time.astimezone(timezone.utc)
    while window_start < end_time_utc:
        window_end = min(window_start + max_window, end_time_utc)
        yield window_start, window_end
        window_start = window_end


def _timestamp_ms(value: datetime) -> int:
    return int(value.astimezone(timezone.utc).timestamp() * 1000)


def _string_or_none(value: object) -> str | None:
    if value in (None, ""):
        return None
    return str(value)


def _trade_timestamp(trade: dict) -> datetime | None:
    raw_time = trade.get("time")
    if raw_time in (None, ""):
        return None
    return datetime.fromtimestamp(int(raw_time) / 1000, tz=timezone.utc)


def _trade_side(*, trade: dict, order: dict | None) -> str | None:
    side = trade.get("side") or (order or {}).get("side")
    if side not in (None, ""):
        return str(side).upper()
    if "buyer" in trade:
        return "BUY" if bool(trade.get("buyer")) else "SELL"
    return None


def _order_metadata_by_id(
    *,
    client,
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    logger,
) -> dict[str, dict]:
    fetch_all_orders = getattr(client, "fetch_all_orders", None)
    if not callable(fetch_all_orders):
        return {}
    try:
        orders = fetch_all_orders(
            symbol=symbol,
            start_time_ms=_timestamp_ms(window_start),
            end_time_ms=_timestamp_ms(window_end),
            limit=1000,
        )
    except Exception as exc:
        emit_structured_log(
            logger,
            service="backfill",
            event="binance-order-fetch-error",
            level="ERROR",
            symbol=symbol,
            window_start=window_start,
            window_end=window_end,
            error=str(exc),
        )
        return {}
    return {
        str(order["orderId"]): order
        for order in orders
        if order.get("orderId") not in (None, "")
    }


def _fetch_user_trades(
    *,
    client,
    symbol: str,
    window_start: datetime,
    window_end: datetime,
    logger,
    limit: int = 1000,
) -> list[dict]:
    trades = client.fetch_user_trades(
        symbol=symbol,
        start_time_ms=_timestamp_ms(window_start),
        end_time_ms=_timestamp_ms(window_end),
        limit=limit,
    )
    if len(trades) < limit or (window_end - window_start) <= timedelta(minutes=1):
        if len(trades) >= limit:
            emit_structured_log(
                logger,
                service="backfill",
                event="binance-trade-window-saturated",
                level="WARN",
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                fetched=len(trades),
            )
        return trades

    midpoint = window_start + ((window_end - window_start) / 2)
    return [
        *_fetch_user_trades(
            client=client,
            symbol=symbol,
            window_start=window_start,
            window_end=midpoint,
            logger=logger,
            limit=limit,
        ),
        *_fetch_user_trades(
            client=client,
            symbol=symbol,
            window_start=midpoint,
            window_end=window_end,
            logger=logger,
            limit=limit,
        ),
    ]


def backfill_binance_user_trades(
    *,
    client,
    runtime_db_path: Path,
    start_time: datetime,
    end_time: datetime,
    symbols: list[str] | tuple[str, ...] | None = None,
    logger=print,
) -> int:
    bootstrap_runtime_db(path=runtime_db_path)
    normalized_symbols = sorted({symbol.upper() for symbol in symbols or [] if symbol})
    if not normalized_symbols:
        normalized_symbols = _infer_backfill_symbols(
            runtime_db_path=runtime_db_path,
            start_time=start_time,
            end_time=end_time,
        )
    if not normalized_symbols:
        emit_structured_log(
            logger,
            service="backfill",
            event="binance-trades-skipped",
            reason="no_symbols",
            start_time=start_time,
            end_time=end_time,
        )
        return 0

    inserted = 0
    fetched_total = 0
    for symbol in normalized_symbols:
        for window_start, window_end in _window_ranges(
            start_time=start_time,
            end_time=end_time,
            max_window=timedelta(days=7),
        ):
            order_by_id = _order_metadata_by_id(
                client=client,
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                logger=logger,
            )
            trades = _fetch_user_trades(
                client=client,
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                logger=logger,
            )
            fetched_total += len(trades)
            window_inserted = 0
            for trade in trades:
                trade_symbol = str(trade.get("symbol") or symbol).upper()
                trade_id = _string_or_none(trade.get("id"))
                if _trade_fill_exists(runtime_db_path=runtime_db_path, symbol=trade_symbol, trade_id=trade_id):
                    continue
                timestamp = _trade_timestamp(trade)
                if timestamp is None:
                    continue
                order_id = _string_or_none(trade.get("orderId"))
                order = order_by_id.get(order_id or "")
                client_order_id = _string_or_none((order or {}).get("clientOrderId"))
                linkage = resolve_order_linkage(
                    path=runtime_db_path,
                    client_order_id=client_order_id,
                    order_id=order_id,
                )
                decision_id = None if linkage is None else linkage.get("decision_id")
                intent_id = None if linkage is None else linkage.get("intent_id")
                insert_trade_fill(
                    path=runtime_db_path,
                    timestamp=timestamp,
                    source="backfill-user-trades",
                    symbol=trade_symbol,
                    order_id=order_id,
                    trade_id=trade_id,
                    client_order_id=client_order_id,
                    decision_id=decision_id,
                    intent_id=intent_id,
                    order_status=_string_or_none((order or {}).get("status")),
                    execution_type="TRADE",
                    side=_trade_side(trade=trade, order=order),
                    order_type=_string_or_none((order or {}).get("origType") or (order or {}).get("type")),
                    quantity=trade.get("qty"),
                    cumulative_quantity=trade.get("qty"),
                    average_price=trade.get("price"),
                    last_price=trade.get("price"),
                    realized_pnl=trade.get("realizedPnl"),
                    commission=trade.get("commission"),
                    commission_asset=_string_or_none(trade.get("commissionAsset")),
                    payload={"trade": trade, "order": order or {}},
                )
                inserted += 1
                window_inserted += 1
            emit_structured_log(
                logger,
                service="backfill",
                event="binance-trades-window",
                symbol=symbol,
                window_start=window_start,
                window_end=window_end,
                fetched=len(trades),
                inserted=window_inserted,
            )

    insert_audit_event(
        path=runtime_db_path,
        timestamp=datetime.now(timezone.utc),
        event_type="binance_trade_backfill",
        source="backfill",
        payload={
            "symbols": normalized_symbols,
            "start_time": start_time.isoformat(),
            "end_time": end_time.isoformat(),
            "fetched": fetched_total,
            "inserted": inserted,
        },
    )
    return inserted
