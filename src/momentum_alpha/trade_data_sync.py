from __future__ import annotations

import sqlite3
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

from momentum_alpha.cli_backfill import (
    _infer_backfill_symbols,
    persist_account_income_rows,
    persist_binance_user_trade_rows,
)
from momentum_alpha.request_weight_budget import RequestWeightBudget
from momentum_alpha.runtime_schema import bootstrap_runtime_db
from momentum_alpha.runtime_store import insert_audit_event
from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore
from momentum_alpha.structured_log import emit_structured_log


INCOME_REQUEST_WEIGHT = 30
SYMBOL_ORDERS_REQUEST_WEIGHT = 5
SYMBOL_TRADES_REQUEST_WEIGHT = 5
DEFAULT_MAX_REQUEST_WEIGHT = 100
DEFAULT_OVERLAP_MINUTES = 20
DEFAULT_BOOTSTRAP_LOOKBACK_HOURS = 36
DAILY_VALIDATION_LOOKBACK_HOURS = 48
SYNC_INCOME_TYPES = frozenset(
    {"REALIZED_PNL", "COMMISSION", "FUNDING_FEE", "TRANSFER"}
)


@dataclass(frozen=True)
class TradeDataSyncResult:
    request_weight: int
    income_fetched: int = 0
    income_inserted: int = 0
    dirty_symbols: tuple[str, ...] = ()
    synced_symbols: tuple[str, ...] = ()
    deferred_symbols: tuple[str, ...] = ()
    orders_fetched: int = 0
    trades_fetched: int = 0
    trades_inserted: int = 0
    rate_limited: bool = False
    live_priority_deferred: bool = False
    errors: tuple[str, ...] = ()
    weight_entries: tuple[tuple[str, int], ...] = ()


@dataclass
class _MutableSyncResult:
    income_fetched: int = 0
    income_inserted: int = 0
    dirty_symbols: list[str] = field(default_factory=list)
    synced_symbols: list[str] = field(default_factory=list)
    deferred_symbols: list[str] = field(default_factory=list)
    orders_fetched: int = 0
    trades_fetched: int = 0
    trades_inserted: int = 0
    rate_limited: bool = False
    live_priority_deferred: bool = False
    errors: list[str] = field(default_factory=list)


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _milliseconds(value: datetime) -> int:
    return int(_utc(value).timestamp() * 1000)


def _timestamp_from_ms(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        return datetime.fromtimestamp(int(value) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OverflowError):
        return None


def _is_rate_limit_error(exc: Exception) -> bool:
    status_code = getattr(exc, "status_code", getattr(exc, "code", None))
    try:
        return int(status_code) in {418, 429}
    except (TypeError, ValueError):
        return False


def _call_read_once(client, method_name: str, **kwargs):
    """Issue one low-priority read attempt so 429 cannot hide behind retries."""

    method = getattr(client, method_name)
    retry_sentinel = object()
    previous_retry_delays = getattr(client, "retry_delays", retry_sentinel)
    previous_read_retry_delays = getattr(client, "read_retry_delays", retry_sentinel)
    try:
        if previous_retry_delays is not retry_sentinel:
            client.retry_delays = ()
        if previous_read_retry_delays is not retry_sentinel:
            client.read_retry_delays = ()
        return method(**kwargs)
    finally:
        if previous_retry_delays is not retry_sentinel:
            client.retry_delays = previous_retry_delays
        if previous_read_retry_delays is not retry_sentinel:
            client.read_retry_delays = previous_read_retry_delays


def _cursor_window_start(
    *,
    cursor: datetime | None,
    now: datetime,
    overlap: timedelta,
    bootstrap_lookback: timedelta,
    force_bootstrap: bool,
    missing_cursor_start: datetime | None = None,
) -> datetime:
    bootstrap_start = now - bootstrap_lookback
    if force_bootstrap:
        return bootstrap_start
    if cursor is None:
        if missing_cursor_start is None:
            return bootstrap_start
        return max(bootstrap_start, min(now, _utc(missing_cursor_start)))
    normalized_cursor = _utc(cursor)
    if normalized_cursor > now + timedelta(minutes=5):
        return bootstrap_start
    # Binance's time-bounded history APIs accept at most seven days. A cursor
    # older than that is treated as damaged and repaired with the explicit
    # bootstrap window rather than issuing an unbounded history pull.
    if normalized_cursor < now - timedelta(days=7):
        return bootstrap_start
    return max(now - timedelta(days=7), normalized_cursor - overlap)


def _response_cursor(
    *,
    rows: list[dict],
    end_time: datetime,
    timestamp_keys: tuple[str, ...],
    limit: int,
) -> tuple[datetime, bool]:
    saturated = len(rows) >= limit
    if not saturated:
        return end_time, False
    timestamps: list[datetime] = []
    for row in rows:
        for key in timestamp_keys:
            timestamp = _timestamp_from_ms(row.get(key))
            if timestamp is not None:
                timestamps.append(timestamp)
                break
    return (max(timestamps) if timestamps else end_time), True


def _persist_orders(
    *,
    store: RuntimeSyncStateStore,
    symbol: str,
    orders: list[dict],
    synced_at: datetime,
) -> None:
    for order in orders:
        order_id = order.get("orderId")
        if order_id in (None, ""):
            continue
        update_time = _timestamp_from_ms(order.get("updateTime") or order.get("time"))
        store.save_synced_order(
            symbol=symbol,
            order_id=str(order_id),
            update_time=update_time,
            synced_at=synced_at,
            payload=order,
        )


def _recent_validation_symbols(*, runtime_db_path: Path, since: datetime) -> list[str]:
    if not runtime_db_path.exists():
        return []
    bootstrap_runtime_db(path=runtime_db_path)
    symbols: set[str] = set()
    with sqlite3.connect(runtime_db_path) as connection:
        for table in ("broker_orders", "trade_fills", "algo_orders"):
            rows = connection.execute(
                f"""
                SELECT DISTINCT symbol
                FROM {table}
                WHERE timestamp >= ?
                  AND symbol IS NOT NULL
                  AND symbol != ''
                """,
                (_utc(since).isoformat(),),
            ).fetchall()
            symbols.update(str(row[0]).upper() for row in rows if row[0])
    return sorted(symbols)


def _schedule_daily_validation(
    *,
    store: RuntimeSyncStateStore,
    runtime_db_path: Path,
    now: datetime,
) -> None:
    local_now = now.astimezone(ZoneInfo("Asia/Shanghai"))
    if not 2 <= local_now.hour < 5:
        return
    previous = store.get_cursor(kind="daily_validation")
    if previous is not None and previous.astimezone(ZoneInfo("Asia/Shanghai")).date() == local_now.date():
        return
    for symbol in _recent_validation_symbols(
        runtime_db_path=runtime_db_path,
        since=now - timedelta(hours=DAILY_VALIDATION_LOOKBACK_HOURS),
    ):
        store.mark_dirty(symbol=symbol, reason="daily_validation_48h", observed_at=now)
    store.save_cursor(kind="daily_validation", cursor_at=now, updated_at=now)


def _schedule_initial_bootstrap(
    *,
    store: RuntimeSyncStateStore,
    runtime_db_path: Path,
    now: datetime,
    bootstrap_lookback: timedelta,
) -> None:
    if store.get_cursor(kind="sync_bootstrap") is not None:
        return
    for symbol in _recent_validation_symbols(
        runtime_db_path=runtime_db_path,
        since=now - bootstrap_lookback,
    ):
        store.mark_dirty(symbol=symbol, reason="initial_cursor_bootstrap", observed_at=now)
    store.save_cursor(kind="sync_bootstrap", cursor_at=now, updated_at=now)


def _prepare_full_repair(
    *,
    store: RuntimeSyncStateStore,
    runtime_db_path: Path,
    now: datetime,
    symbols: list[str] | tuple[str, ...] | None,
    bootstrap_lookback: timedelta,
) -> None:
    repair_symbols = sorted({str(symbol).upper() for symbol in symbols or () if symbol})
    if not repair_symbols:
        repair_symbols = _infer_backfill_symbols(
            runtime_db_path=runtime_db_path,
            start_time=now - bootstrap_lookback,
            end_time=now,
        )
    for symbol in repair_symbols:
        store.delete_cursor(kind="orders", symbol=symbol)
        store.delete_cursor(kind="trades", symbol=symbol)
        store.mark_dirty(symbol=symbol, reason="manual_full_repair", observed_at=now)


def _finish_result(
    *,
    mutable: _MutableSyncResult,
    budget: RequestWeightBudget,
) -> TradeDataSyncResult:
    return TradeDataSyncResult(
        request_weight=budget.used,
        income_fetched=mutable.income_fetched,
        income_inserted=mutable.income_inserted,
        dirty_symbols=tuple(mutable.dirty_symbols),
        synced_symbols=tuple(mutable.synced_symbols),
        deferred_symbols=tuple(dict.fromkeys(mutable.deferred_symbols)),
        orders_fetched=mutable.orders_fetched,
        trades_fetched=mutable.trades_fetched,
        trades_inserted=mutable.trades_inserted,
        rate_limited=mutable.rate_limited,
        live_priority_deferred=mutable.live_priority_deferred,
        errors=tuple(mutable.errors),
        weight_entries=tuple(budget.entries),
    )


def _record_result(
    *,
    runtime_db_path: Path,
    now: datetime,
    result: TradeDataSyncResult,
) -> None:
    insert_audit_event(
        path=runtime_db_path,
        timestamp=now,
        event_type="incremental_trade_data_sync",
        source="trade-data-sync",
        payload=asdict(result),
    )


def _live_order_priority_active(
    *,
    store: RuntimeSyncStateStore,
    now: datetime,
    max_age: timedelta = timedelta(minutes=5),
) -> bool:
    for request in store.control_requests():
        if request.key != "live_order_priority":
            continue
        age = now - request.requested_at
        if timedelta(0) <= age <= max_age:
            return True
        if age > max_age:
            store.clear_control(key=request.key, requested_at=request.requested_at)
    return False


def run_incremental_trade_data_sync(
    *,
    client,
    runtime_db_path: Path,
    now: datetime,
    logger=print,
    max_request_weight: int = DEFAULT_MAX_REQUEST_WEIGHT,
    overlap_minutes: int = DEFAULT_OVERLAP_MINUTES,
    bootstrap_lookback_hours: int = DEFAULT_BOOTSTRAP_LOOKBACK_HOURS,
    full_repair: bool = False,
    repair_symbols: list[str] | tuple[str, ...] | None = None,
) -> TradeDataSyncResult:
    """Synchronize account history within a hard per-run request-weight budget."""

    if max_request_weight < INCOME_REQUEST_WEIGHT:
        raise ValueError("trade sync request-weight limit must allow the income request")
    if max_request_weight > DEFAULT_MAX_REQUEST_WEIGHT:
        raise ValueError(f"trade sync request-weight limit cannot exceed {DEFAULT_MAX_REQUEST_WEIGHT}")

    now = _utc(now)
    overlap = timedelta(minutes=max(10, min(30, overlap_minutes)))
    bootstrap_lookback = timedelta(hours=max(1, min(36, bootstrap_lookback_hours)))
    bootstrap_runtime_db(path=runtime_db_path)
    store = RuntimeSyncStateStore(path=runtime_db_path)
    budget = RequestWeightBudget(limit=max_request_weight)
    mutable = _MutableSyncResult()

    _schedule_initial_bootstrap(
        store=store,
        runtime_db_path=runtime_db_path,
        now=now,
        bootstrap_lookback=bootstrap_lookback,
    )

    if full_repair:
        _prepare_full_repair(
            store=store,
            runtime_db_path=runtime_db_path,
            now=now,
            symbols=repair_symbols,
            bootstrap_lookback=bootstrap_lookback,
        )
    else:
        _schedule_daily_validation(store=store, runtime_db_path=runtime_db_path, now=now)

    if _live_order_priority_active(store=store, now=now):
        mutable.live_priority_deferred = True
        result = _finish_result(mutable=mutable, budget=budget)
        _record_result(runtime_db_path=runtime_db_path, now=now, result=result)
        return result

    income_cursor = store.get_cursor(kind="income")
    income_start = _cursor_window_start(
        cursor=income_cursor,
        now=now,
        overlap=overlap,
        bootstrap_lookback=bootstrap_lookback,
        force_bootstrap=full_repair,
    )
    budget.spend(INCOME_REQUEST_WEIGHT, operation="income")
    try:
        incomes = list(
            _call_read_once(
                client,
                "fetch_income_history",
                income_type=None,
                start_time_ms=_milliseconds(income_start),
                end_time_ms=_milliseconds(now),
                limit=1000,
            )
            or []
        )
    except Exception as exc:
        mutable.rate_limited = _is_rate_limit_error(exc)
        mutable.errors.append(f"income:{exc}")
        result = _finish_result(mutable=mutable, budget=budget)
        _record_result(runtime_db_path=runtime_db_path, now=now, result=result)
        return result

    mutable.income_fetched = len(incomes)
    mutable.income_inserted = persist_account_income_rows(
        runtime_db_path=runtime_db_path,
        incomes=incomes,
        allowed_income_types=set(SYNC_INCOME_TYPES),
        source="trade-data-sync",
    )
    next_income_cursor, _income_saturated = _response_cursor(
        rows=incomes,
        end_time=now,
        timestamp_keys=("time",),
        limit=1000,
    )
    store.save_cursor(kind="income", cursor_at=next_income_cursor, updated_at=now)

    per_symbol_weight = SYMBOL_ORDERS_REQUEST_WEIGHT + SYMBOL_TRADES_REQUEST_WEIGHT
    symbol_limit = budget.remaining // per_symbol_weight
    dirty_snapshot = store.dirty_symbols()
    selected = dirty_snapshot[:symbol_limit]
    mutable.dirty_symbols = [item.symbol for item in selected]
    mutable.deferred_symbols = [item.symbol for item in dirty_snapshot[symbol_limit:]]

    for dirty in selected:
        if _live_order_priority_active(store=store, now=now):
            mutable.live_priority_deferred = True
            mutable.deferred_symbols.extend(
                item.symbol
                for item in selected
                if item.symbol not in mutable.synced_symbols
            )
            break
        symbol = dirty.symbol
        order_cursor = store.get_cursor(kind="orders", symbol=symbol)
        trade_cursor = store.get_cursor(kind="trades", symbol=symbol)
        bootstrap_reasons = {"initial_cursor_bootstrap", "manual_full_repair"}
        order_start = _cursor_window_start(
            cursor=order_cursor,
            now=now,
            overlap=overlap,
            bootstrap_lookback=bootstrap_lookback,
            force_bootstrap=(
                full_repair
                or (order_cursor is None and bool(bootstrap_reasons & set(dirty.reasons)))
            ),
            missing_cursor_start=dirty.first_dirty_at - overlap,
        )
        trade_start = _cursor_window_start(
            cursor=trade_cursor,
            now=now,
            overlap=overlap,
            bootstrap_lookback=bootstrap_lookback,
            force_bootstrap=(
                full_repair
                or (trade_cursor is None and bool(bootstrap_reasons & set(dirty.reasons)))
            ),
            missing_cursor_start=dirty.first_dirty_at - overlap,
        )

        budget.spend(SYMBOL_ORDERS_REQUEST_WEIGHT, operation=f"allOrders:{symbol}")
        try:
            orders = list(
                _call_read_once(
                    client,
                    "fetch_all_orders",
                    symbol=symbol,
                    start_time_ms=_milliseconds(order_start),
                    end_time_ms=_milliseconds(now),
                    limit=1000,
                )
                or []
            )
        except Exception as exc:
            mutable.rate_limited = _is_rate_limit_error(exc)
            mutable.errors.append(f"allOrders:{symbol}:{exc}")
            if mutable.rate_limited:
                break
            continue

        mutable.orders_fetched += len(orders)
        _persist_orders(store=store, symbol=symbol, orders=orders, synced_at=now)
        next_order_cursor, orders_saturated = _response_cursor(
            rows=orders,
            end_time=now,
            timestamp_keys=("updateTime", "time"),
            limit=1000,
        )
        store.save_cursor(kind="orders", symbol=symbol, cursor_at=next_order_cursor, updated_at=now)

        if _live_order_priority_active(store=store, now=now):
            mutable.live_priority_deferred = True
            mutable.deferred_symbols.extend(
                item.symbol
                for item in selected
                if item.symbol not in mutable.synced_symbols
            )
            break

        budget.spend(SYMBOL_TRADES_REQUEST_WEIGHT, operation=f"userTrades:{symbol}")
        try:
            trades = list(
                _call_read_once(
                    client,
                    "fetch_user_trades",
                    symbol=symbol,
                    start_time_ms=_milliseconds(trade_start),
                    end_time_ms=_milliseconds(now),
                    limit=1000,
                )
                or []
            )
        except Exception as exc:
            mutable.rate_limited = _is_rate_limit_error(exc)
            mutable.errors.append(f"userTrades:{symbol}:{exc}")
            if mutable.rate_limited:
                break
            continue

        mutable.trades_fetched += len(trades)
        mutable.trades_inserted += persist_binance_user_trade_rows(
            runtime_db_path=runtime_db_path,
            symbol=symbol,
            trades=trades,
            orders=orders,
            source="trade-data-sync",
        )
        next_trade_cursor, trades_saturated = _response_cursor(
            rows=trades,
            end_time=now,
            timestamp_keys=("time",),
            limit=1000,
        )
        store.save_cursor(kind="trades", symbol=symbol, cursor_at=next_trade_cursor, updated_at=now)

        if not orders_saturated and not trades_saturated:
            store.clear_dirty(symbol=symbol, observed_version=dirty.version)
            mutable.synced_symbols.append(symbol)

    result = _finish_result(mutable=mutable, budget=budget)
    _record_result(runtime_db_path=runtime_db_path, now=now, result=result)
    emit_structured_log(
        logger,
        service="trade-data-sync",
        event="complete",
        request_weight=result.request_weight,
        income_fetched=result.income_fetched,
        income_inserted=result.income_inserted,
        dirty_symbols=list(result.dirty_symbols),
        synced_symbols=list(result.synced_symbols),
        deferred_symbols=list(result.deferred_symbols),
        orders_fetched=result.orders_fetched,
        trades_fetched=result.trades_fetched,
        trades_inserted=result.trades_inserted,
        rate_limited=result.rate_limited,
        live_priority_deferred=result.live_priority_deferred,
        errors=list(result.errors),
    )
    return result
