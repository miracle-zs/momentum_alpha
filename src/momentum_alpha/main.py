from __future__ import annotations

import os
import argparse
import sqlite3
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from urllib.error import HTTPError

from momentum_alpha.audit import AuditRecorder, summarize_audit_events
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceRestClient
from momentum_alpha.dashboard import run_dashboard_server
from momentum_alpha.exchange_info import parse_exchange_info
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import (
    build_missing_stop_reconciliation_plan,
    build_stop_reconciliation_plan,
    restore_state,
)
from momentum_alpha.scheduler import run_loop
from momentum_alpha.runtime import Runtime, build_runtime
from momentum_alpha.runtime import RuntimeTickResult, process_runtime_tick
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    insert_account_flow,
    insert_account_snapshot,
    insert_algo_order,
    insert_broker_order,
    insert_position_snapshot,
    insert_signal_decision,
    insert_trade_fill,
    rebuild_trade_analytics,
)
from momentum_alpha.state_store import FileStateStore, StoredStrategyState
from momentum_alpha.user_stream import (
    BinanceUserStreamClient,
    apply_user_stream_event_to_state,
    extract_account_flows,
    extract_algo_order_event,
    extract_algo_order_status_update,
    extract_trade_fill,
    extract_order_status_update,
    user_stream_event_id,
)


@dataclass(frozen=True)
class RunOnceResult:
    runtime_result: RuntimeTickResult
    broker_responses: list[dict]
    stop_replacements: list[tuple[str, Decimal]]

    @property
    def execution_plan(self):
        return self.runtime_result.execution_plan


def resolve_audit_log_path(*, explicit_path: str | None, state_store) -> Path | None:
    if explicit_path:
        return Path(os.path.abspath(explicit_path))
    env_path = os.environ.get("AUDIT_LOG_FILE")
    if env_path:
        return Path(os.path.abspath(env_path))
    if state_store is not None:
        return state_store.path.parent / "audit.jsonl"
    return None


def resolve_runtime_db_path(*, explicit_path: str | None, state_store, audit_log_path: Path | None = None) -> Path | None:
    if explicit_path:
        return Path(os.path.abspath(explicit_path))
    env_path = os.environ.get("RUNTIME_DB_FILE")
    if env_path:
        return Path(os.path.abspath(env_path))
    if audit_log_path is not None:
        return audit_log_path.parent / "runtime.db"
    if state_store is not None:
        return state_store.path.parent / "runtime.db"
    return None


def _build_audit_recorder(
    *,
    explicit_path: str | None,
    explicit_runtime_db_path: str | None,
    state_store,
    source: str | None = None,
) -> AuditRecorder | None:
    path = resolve_audit_log_path(explicit_path=explicit_path, state_store=state_store)
    runtime_db_path = resolve_runtime_db_path(
        explicit_path=explicit_runtime_db_path,
        state_store=state_store,
        audit_log_path=path,
    )
    if path is None and runtime_db_path is None:
        return None
    return AuditRecorder(path=path, runtime_db_path=runtime_db_path, source=source)


def _build_runtime_state_store(*, audit_recorder: AuditRecorder | None) -> RuntimeStateStore | None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return None
    return RuntimeStateStore(path=audit_recorder.runtime_db_path)


def _merge_save_strategy_state(
    *,
    state_store,
    runtime_state_store: RuntimeStateStore | None,
    state: StoredStrategyState,
) -> None:
    if state_store is not None:
        state_store.merge_save(state)
    if runtime_state_store is not None:
        runtime_state_store.merge_save(state)


def _record_position_snapshot(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    leader_symbol: str | None,
    position_count: int,
    order_status_count: int,
    symbol_count: int | None = None,
    submit_orders: bool | None = None,
    restore_positions: bool | None = None,
    execute_stop_replacements: bool | None = None,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    try:
        insert_position_snapshot(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            leader_symbol=leader_symbol,
            position_count=position_count,
            order_status_count=order_status_count,
            symbol_count=symbol_count,
            submit_orders=submit_orders,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
            payload=payload or {},
        )
    except Exception:
        pass


def _record_signal_decision(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    decision_type: str,
    symbol: str | None,
    previous_leader_symbol: str | None,
    next_leader_symbol: str | None,
    position_count: int,
    order_status_count: int,
    broker_response_count: int,
    stop_replacement_count: int,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    try:
        insert_signal_decision(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            decision_type=decision_type,
            symbol=symbol,
            previous_leader_symbol=previous_leader_symbol,
            next_leader_symbol=next_leader_symbol,
            position_count=position_count,
            order_status_count=order_status_count,
            broker_response_count=broker_response_count,
            stop_replacement_count=stop_replacement_count,
            payload=payload or {},
        )
    except Exception:
        pass


def _build_market_context_payloads(*, snapshots: list[dict]) -> tuple[dict[str, dict], Decimal | None]:
    ordered = sorted(
        [
            {
                "symbol": snapshot["symbol"],
                "daily_change_pct": (snapshot["latest_price"] - snapshot["daily_open_price"]) / snapshot["daily_open_price"],
                "latest_price": snapshot["latest_price"],
                "daily_open_price": snapshot["daily_open_price"],
                "previous_hour_low": snapshot["previous_hour_low"],
                "current_hour_low": snapshot.get("current_hour_low", snapshot["previous_hour_low"]),
            }
            for snapshot in snapshots
            if snapshot.get("daily_open_price") not in (None, Decimal("0"))
        ],
        key=lambda item: item["daily_change_pct"],
        reverse=True,
    )
    leader_gap_pct = None
    if len(ordered) >= 2:
        leader_gap_pct = ordered[0]["daily_change_pct"] - ordered[1]["daily_change_pct"]
    payloads: dict[str, dict] = {}
    for item in ordered:
        payloads[item["symbol"]] = {
            "latest_price": str(item["latest_price"]),
            "daily_open_price": str(item["daily_open_price"]),
            "daily_change_pct": str(item["daily_change_pct"]),
            "previous_hour_low": str(item["previous_hour_low"]),
            "current_hour_low": str(item["current_hour_low"]),
            "leader_gap_pct": str(leader_gap_pct) if item["symbol"] == ordered[0]["symbol"] and leader_gap_pct is not None else None,
        }
    return payloads, leader_gap_pct


def _record_broker_orders(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    responses: list[dict],
    action_type: str,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    for response in responses:
        try:
            quantity = response.get("quantity")
            price = response.get("price") or response.get("stopPrice")
            insert_broker_order(
                path=audit_recorder.runtime_db_path,
                timestamp=now,
                source=audit_recorder.source,
                action_type=action_type,
                symbol=response.get("symbol"),
                order_id=str(response.get("orderId")) if response.get("orderId") is not None else None,
                client_order_id=response.get("clientOrderId"),
                order_status=response.get("status"),
                side=response.get("side"),
                quantity=float(quantity) if quantity not in (None, "") else None,
                price=float(price) if price not in (None, "") else None,
                payload=response,
            )
        except Exception:
            pass


def _record_account_snapshot(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    leader_symbol: str | None,
    position_count: int,
    open_order_count: int,
    account_info: dict | None,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None or account_info is None:
        return
    try:
        insert_account_snapshot(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            wallet_balance=account_info.get("totalWalletBalance"),
            available_balance=account_info.get("availableBalance"),
            equity=account_info.get("totalMarginBalance"),
            unrealized_pnl=account_info.get("totalUnrealizedProfit"),
            position_count=position_count,
            open_order_count=open_order_count,
            leader_symbol=leader_symbol,
            payload=payload or account_info,
        )
    except Exception:
        pass


def load_credentials_from_env() -> tuple[str, str]:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    return api_key, api_secret


def load_runtime_settings_from_env() -> dict[str, bool]:
    raw_testnet = os.environ.get("BINANCE_USE_TESTNET", "")
    return {"use_testnet": raw_testnet.strip().lower() in {"1", "true", "yes", "on"}}


def _parse_cli_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


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
    with sqlite3.connect(runtime_db_path) as connection:
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


def _build_client_from_factory(*, client_factory, testnet: bool):
    try:
        return client_factory(testnet=testnet)
    except TypeError:
        return client_factory()


def build_runtime_from_snapshots(*, snapshots: list[dict]) -> Runtime:
    return build_runtime(snapshots=snapshots)


def _resolve_symbols(*, symbols: list[str] | None, client) -> list[str]:
    requested_symbols = [symbol for symbol in (symbols or []) if symbol]
    if requested_symbols:
        return list(dict.fromkeys(requested_symbols))
    return list(parse_exchange_info(client.fetch_exchange_info()).keys())


def run_once(
    *,
    snapshots: list[dict],
    now: datetime,
    previous_leader_symbol: str | None,
    client,
    broker: BinanceBroker,
    submit_orders: bool,
    initial_state: StrategyState | None = None,
    exchange_symbols: dict | None = None,
    position_side: str | None = None,
    last_add_on_hour: int | None = None,
) -> RunOnceResult:
    runtime = build_runtime_from_snapshots(snapshots=snapshots).with_exchange_symbols(
        exchange_symbols if exchange_symbols is not None else parse_exchange_info(client.fetch_exchange_info())
    )
    state = initial_state or StrategyState(
        current_day=date(now.year, now.month, now.day),
        previous_leader_symbol=previous_leader_symbol,
        positions={},
        recent_stop_loss_exits={},
    )
    runtime_result = process_runtime_tick(runtime=runtime, state=state, now=now, position_side=position_side, last_add_on_hour=last_add_on_hour)
    broker_responses = broker.submit_execution_plan(runtime_result.execution_plan) if submit_orders else []
    return RunOnceResult(
        runtime_result=runtime_result,
        broker_responses=broker_responses,
        stop_replacements=[],
    )


def _utc_midnight_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    utc_midnight = datetime(utc_now.year, utc_now.month, utc_now.day, tzinfo=timezone.utc)
    window_end = utc_midnight + timedelta(minutes=1) - timedelta(milliseconds=1)
    return int(utc_midnight.timestamp() * 1000), int(window_end.timestamp() * 1000)


def _previous_closed_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    previous_hour_start = current_hour_start - timedelta(hours=1)
    previous_hour_end = current_hour_start - timedelta(milliseconds=1)
    return int(previous_hour_start.timestamp() * 1000), int(previous_hour_end.timestamp() * 1000)


def _current_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    return int(current_hour_start.timestamp() * 1000), int(utc_now.timestamp() * 1000)


def _fetch_daily_open_klines(*, client, symbol: str, now: datetime):
    day_open_start_ms, day_open_end_ms = _utc_midnight_window_ms(now=now)
    try:
        klines = client.fetch_klines(
            symbol=symbol,
            interval="1m",
            limit=1,
            start_time_ms=day_open_start_ms,
            end_time_ms=day_open_end_ms,
        )
        if klines:
            return klines
        return client.fetch_klines(
            symbol=symbol,
            interval="1m",
            limit=1,
            start_time_ms=day_open_start_ms,
            end_time_ms=int(now.astimezone(timezone.utc).timestamp() * 1000),
        )
    except TypeError:
        # Backward-compatible for simple test doubles that still expose the old signature.
        return client.fetch_klines(symbol=symbol, interval="1m", limit=1)


def _fetch_previous_hour_klines(*, client, symbol: str, now: datetime):
    previous_hour_start_ms, previous_hour_end_ms = _previous_closed_hour_window_ms(now=now)
    try:
        return client.fetch_klines(
            symbol=symbol,
            interval="1h",
            limit=1,
            start_time_ms=previous_hour_start_ms,
            end_time_ms=previous_hour_end_ms,
        )
    except TypeError:
        return client.fetch_klines(symbol=symbol, interval="1h", limit=1)


def _fetch_current_hour_klines(*, client, symbol: str, now: datetime):
    current_hour_start_ms, current_hour_end_ms = _current_hour_window_ms(now=now)
    try:
        return client.fetch_klines(
            symbol=symbol,
            interval="1h",
            limit=1,
            start_time_ms=current_hour_start_ms,
            end_time_ms=current_hour_end_ms,
        )
    except TypeError:
        return client.fetch_klines(symbol=symbol, interval="1h", limit=1)


class LiveMarketDataCache:
    def __init__(self) -> None:
        self.exchange_symbols: dict[str, object] | None = None
        self.daily_open_day: date | None = None
        self.daily_open_prices: dict[str, Decimal] = {}
        self.previous_hour_window: tuple[int, int] | None = None
        self.previous_hour_lows: dict[str, tuple[bool, Decimal]] = {}
        self.current_hour_window: tuple[int, int] | None = None
        self.current_hour_lows: dict[str, Decimal] = {}

    def resolve_symbols(self, *, symbols: list[str] | None, client) -> list[str]:
        requested_symbols = [symbol for symbol in (symbols or []) if symbol]
        if requested_symbols:
            return list(dict.fromkeys(requested_symbols))
        return list(self._exchange_symbols(client=client).keys())

    def exchange_symbol_map(self, *, client) -> dict[str, object]:
        return self._exchange_symbols(client=client)

    def _exchange_symbols(self, *, client) -> dict[str, object]:
        if self.exchange_symbols is None:
            self.exchange_symbols = parse_exchange_info(client.fetch_exchange_info())
        return self.exchange_symbols

    def latest_prices(self, *, symbols: list[str], client) -> dict[str, Decimal]:
        try:
            tickers = client.fetch_ticker_prices()
            prices: dict[str, Decimal] = {}
            for ticker in tickers:
                symbol = ticker.get("symbol")
                if symbol not in symbols:
                    continue
                try:
                    prices[symbol] = Decimal(ticker["price"])
                except (KeyError, InvalidOperation, TypeError):
                    continue
            return prices
        except AttributeError:
            prices = {}
            for symbol in symbols:
                ticker = client.fetch_ticker_price(symbol=symbol)
                try:
                    prices[symbol] = Decimal(ticker["price"])
                except (KeyError, InvalidOperation, TypeError):
                    continue
            return prices

    def ensure_daily_open_prices(self, *, symbols: list[str], client, now: datetime) -> None:
        utc_day = now.astimezone(timezone.utc).date()
        if self.daily_open_day != utc_day:
            self.daily_open_day = utc_day
            self.daily_open_prices = {}
        for symbol in symbols:
            if symbol in self.daily_open_prices:
                continue
            day_open_klines = _fetch_daily_open_klines(client=client, symbol=symbol, now=now)
            if not day_open_klines:
                continue
            self.daily_open_prices[symbol] = Decimal(day_open_klines[0][1])

    def ensure_previous_hour_lows(self, *, symbols: set[str], client, now: datetime) -> None:
        window = _previous_closed_hour_window_ms(now=now)
        if self.previous_hour_window != window:
            self.previous_hour_window = window
            self.previous_hour_lows = {}
        for symbol in symbols:
            if symbol in self.previous_hour_lows:
                continue
            hour_klines = _fetch_previous_hour_klines(client=client, symbol=symbol, now=now)
            if hour_klines:
                self.previous_hour_lows[symbol] = (True, Decimal(hour_klines[0][3]))
            else:
                self.previous_hour_lows[symbol] = (False, Decimal("0"))

    def ensure_current_hour_lows(self, *, symbols: set[str], client, now: datetime) -> None:
        window = _current_hour_window_ms(now=now)
        if self.current_hour_window != window:
            self.current_hour_window = window
            self.current_hour_lows = {}
        for symbol in symbols:
            if symbol in self.current_hour_lows:
                continue
            current_hour_klines = _fetch_current_hour_klines(client=client, symbol=symbol, now=now)
            if current_hour_klines:
                self.current_hour_lows[symbol] = Decimal(current_hour_klines[0][3])


def _build_live_snapshots(
    *,
    symbols: list[str],
    held_symbols: set[str],
    client,
    now: datetime,
    market_data_cache: LiveMarketDataCache | None = None,
) -> list[dict]:
    cache = market_data_cache or LiveMarketDataCache()
    latest_prices = cache.latest_prices(symbols=symbols, client=client)
    cache.ensure_daily_open_prices(symbols=symbols, client=client, now=now)

    provisional_snapshots: list[dict] = []
    for symbol in symbols:
        latest_price = latest_prices.get(symbol)
        daily_open_price = cache.daily_open_prices.get(symbol)
        if latest_price is None or daily_open_price is None:
            continue
        provisional_snapshots.append(
            {
                "symbol": symbol,
                "daily_open_price": daily_open_price,
                "latest_price": latest_price,
                "previous_hour_low": Decimal("0"),
                "tradable": True,
                "has_previous_hour_candle": False,
                "current_hour_low": Decimal("0"),
            }
        )

    if not provisional_snapshots:
        return []

    leader_runtime = build_runtime_from_snapshots(snapshots=provisional_snapshots)
    leader_snapshot = max(leader_runtime.market.values(), key=lambda item: item.daily_change_pct, default=None)
    symbols_requiring_hour_data = set(held_symbols)
    if leader_snapshot is not None:
        symbols_requiring_hour_data.add(leader_snapshot.symbol)

    cache.ensure_previous_hour_lows(symbols=symbols_requiring_hour_data, client=client, now=now)
    current_hour_symbols = {
        symbol
        for symbol in symbols_requiring_hour_data
        if cache.previous_hour_lows.get(symbol, (False, Decimal("0")))[0]
        and latest_prices.get(symbol, Decimal("0")) < cache.previous_hour_lows[symbol][1]
    }
    cache.ensure_current_hour_lows(symbols=current_hour_symbols, client=client, now=now)

    snapshots: list[dict] = []
    for snapshot in provisional_snapshots:
        symbol = snapshot["symbol"]
        has_previous_hour_candle, previous_hour_low = cache.previous_hour_lows.get(
            symbol,
            (False, Decimal("0")),
        )
        current_hour_low = cache.current_hour_lows.get(symbol, previous_hour_low)
        snapshots.append(
            {
                **snapshot,
                "previous_hour_low": previous_hour_low,
                "has_previous_hour_candle": has_previous_hour_candle,
                "current_hour_low": current_hour_low,
            }
        )
    return snapshots


def run_once_live(
    *,
    symbols: list[str] | None,
    now: datetime,
    previous_leader_symbol: str | None,
    client,
    broker: BinanceBroker,
    submit_orders: bool,
    restore_positions: bool = False,
    execute_stop_replacements: bool = False,
    state_store=None,
    market_data_cache: LiveMarketDataCache | None = None,
    audit_recorder: AuditRecorder | None = None,
    last_add_on_hour: int | None = None,
) -> RunOnceResult:
    runtime_state_store = _build_runtime_state_store(audit_recorder=audit_recorder)
    position_side: str | None = None
    fetch_position_mode = getattr(client, "fetch_position_mode", None)
    if callable(fetch_position_mode):
        try:
            position_mode = fetch_position_mode()
        except Exception:
            position_mode = None
        dual_side = None if position_mode is None else position_mode.get("dualSidePosition")
        if dual_side in (True, "true", "TRUE", "True"):
            position_side = "LONG"
    if previous_leader_symbol is None and state_store is not None:
        stored_state = state_store.load()
        if stored_state is not None:
            previous_leader_symbol = stored_state.previous_leader_symbol

    initial_state = None
    if restore_positions:
        open_orders = client.fetch_open_orders()
        fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
        if callable(fetch_open_algo_orders):
            open_orders = [*open_orders, *fetch_open_algo_orders()]
        initial_state = restore_state(
            current_day=f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
            previous_leader_symbol=previous_leader_symbol,
            position_risk=client.fetch_position_risk(),
            open_orders=open_orders,
        )
        if state_store is not None:
            stored_state = state_store.load()
            if stored_state is not None:
                initial_state = replace(
                    initial_state,
                    recent_stop_loss_exits={
                        symbol: datetime.fromisoformat(timestamp)
                        for symbol, timestamp in (stored_state.recent_stop_loss_exits or {}).items()
                    },
                )

    resolved_symbols = (
        market_data_cache.resolve_symbols(symbols=symbols, client=client)
        if market_data_cache is not None
        else _resolve_symbols(symbols=symbols, client=client)
    )
    held_symbols = set(initial_state.positions) if initial_state is not None else set()
    snapshots = _build_live_snapshots(
        symbols=resolved_symbols,
        held_symbols=held_symbols,
        client=client,
        now=now,
        market_data_cache=market_data_cache,
    )

    result = run_once(
        snapshots=snapshots,
        now=now,
        previous_leader_symbol=previous_leader_symbol,
        client=client,
        broker=broker,
        submit_orders=False,
        initial_state=initial_state,
        exchange_symbols=(
            market_data_cache.exchange_symbol_map(client=client) if market_data_cache is not None else None
        ),
        position_side=position_side,
        last_add_on_hour=last_add_on_hour,
    )
    stop_replacements: list[tuple[str, Decimal]] = []
    stop_replacement_responses: list[dict] = []
    if restore_positions and initial_state is not None:
        stop_replacements = build_stop_reconciliation_plan(
            state=initial_state,
            decision=result.runtime_result.decision,
        )
        runtime_market = build_runtime_from_snapshots(snapshots=snapshots).market
        missing_stop_replacements = build_missing_stop_reconciliation_plan(
            state=initial_state,
            market=runtime_market,
        )
        merged_replacements = {symbol: stop_price for symbol, stop_price in stop_replacements}
        for symbol, stop_price in missing_stop_replacements:
            merged_replacements.setdefault(symbol, stop_price)
        stop_replacements = sorted(merged_replacements.items())
        if execute_stop_replacements and stop_replacements:
            try:
                stop_replacement_responses = broker.replace_stop_orders(
                    replacements=[
                        (
                            symbol,
                            str(initial_state.positions[symbol].total_quantity),
                            str(stop_price),
                        )
                        if position_side is None
                        else (
                            symbol,
                            str(initial_state.positions[symbol].total_quantity),
                            str(stop_price),
                            position_side,
                        )
                        for symbol, stop_price in stop_replacements
                        if symbol in initial_state.positions
                    ]
                )
            except Exception as exc:
                print(f"stop replacement failed: {exc}")
    broker_responses: list[dict] = []
    if submit_orders:
        broker_responses = broker.submit_execution_plan(result.execution_plan)
        result = replace(result, broker_responses=broker_responses)
    if state_store is not None:
        _merge_save_strategy_state(
            state_store=state_store,
            runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
                    previous_leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in result.runtime_result.next_state.recent_stop_loss_exits.items()
                    },
                ),
            )
    if audit_recorder is not None:
        fetch_account_info = getattr(client, "fetch_account_info", None)
        account_info = fetch_account_info() if callable(fetch_account_info) else None
        market_payloads, _leader_gap_pct = _build_market_context_payloads(snapshots=snapshots)
        audit_recorder.record(
            event_type="tick_result",
            now=now,
            payload={
                "symbol_count": len(snapshots),
                "base_entry_symbols": [intent.symbol for intent in result.runtime_result.decision.base_entries],
                "add_on_symbols": [intent.symbol for intent in result.runtime_result.decision.add_on_entries],
                "updated_stop_symbols": sorted(result.runtime_result.decision.updated_stop_prices),
                "previous_leader_symbol": previous_leader_symbol,
                "next_previous_leader_symbol": result.runtime_result.next_state.previous_leader_symbol,
                "broker_response_count": len(result.broker_responses),
                "stop_replacement_count": len(stop_replacements),
            },
        )
        position_count = len(result.runtime_result.next_state.positions)
        order_status_count = 0
        signal_records = []
        signal_records.extend(
            (
                "base_entry",
                intent.symbol,
                {
                    "leg_type": intent.leg_type,
                    "stop_price": str(intent.stop_price),
                    **{key: value for key, value in market_payloads.get(intent.symbol, {}).items() if value is not None},
                },
            )
            for intent in result.runtime_result.decision.base_entries
        )
        signal_records.extend(
            (
                "add_on",
                intent.symbol,
                {
                    "leg_type": intent.leg_type,
                    "stop_price": str(intent.stop_price),
                    **{key: value for key, value in market_payloads.get(intent.symbol, {}).items() if value is not None},
                },
            )
            for intent in result.runtime_result.decision.add_on_entries
        )
        signal_records.extend(
            (
                "stop_update",
                symbol,
                {
                    "stop_price": str(stop_price),
                    **{key: value for key, value in market_payloads.get(symbol, {}).items() if value is not None},
                },
            )
            for symbol, stop_price in sorted(result.runtime_result.decision.updated_stop_prices.items())
        )
        if not signal_records:
            signal_records.append(
                (
                    "no_action",
                    result.runtime_result.next_state.previous_leader_symbol,
                    (
                        {"blocked_reason": result.runtime_result.decision.blocked_reason}
                        if result.runtime_result.decision.blocked_reason is not None
                        else {}
                    ),
                )
            )
        for decision_type, symbol, payload in signal_records:
            _record_signal_decision(
                audit_recorder=audit_recorder,
                now=now,
                decision_type=decision_type,
                symbol=symbol,
                previous_leader_symbol=previous_leader_symbol,
                next_leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
                position_count=position_count,
                order_status_count=order_status_count,
                broker_response_count=len(result.broker_responses),
                stop_replacement_count=len(stop_replacements),
                payload=payload,
            )
        _record_position_snapshot(
            audit_recorder=audit_recorder,
            now=now,
            leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            position_count=position_count,
            order_status_count=order_status_count,
            symbol_count=len(snapshots),
            submit_orders=submit_orders,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
            payload={
                "base_entry_symbols": [intent.symbol for intent in result.runtime_result.decision.base_entries],
                "add_on_symbols": [intent.symbol for intent in result.runtime_result.decision.add_on_entries],
                "updated_stop_symbols": sorted(result.runtime_result.decision.updated_stop_prices),
            },
        )
        _record_account_snapshot(
            audit_recorder=audit_recorder,
            now=now,
            leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            position_count=position_count,
            open_order_count=order_status_count,
            account_info=account_info,
            payload={
                "symbol_count": len(snapshots),
                "base_entry_symbols": [intent.symbol for intent in result.runtime_result.decision.base_entries],
                "add_on_symbols": [intent.symbol for intent in result.runtime_result.decision.add_on_entries],
                "updated_stop_symbols": sorted(result.runtime_result.decision.updated_stop_prices),
            },
        )
        if result.broker_responses:
            audit_recorder.record(
                event_type="broker_submit",
                now=now,
                payload={"responses": result.broker_responses},
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=now,
                responses=result.broker_responses,
                action_type="submit_order",
            )
        if stop_replacement_responses:
            audit_recorder.record(
                event_type="broker_replace",
                now=now,
                payload={"responses": stop_replacement_responses},
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=now,
                responses=stop_replacement_responses,
                action_type="replace_stop_order",
            )
        if stop_replacements:
            audit_recorder.record(
                event_type="stop_replacements",
                now=now,
                payload={"replacements": [(symbol, str(stop_price)) for symbol, stop_price in stop_replacements]},
            )
    return RunOnceResult(
        runtime_result=result.runtime_result,
        broker_responses=result.broker_responses,
        stop_replacements=stop_replacements,
    )


def run_user_stream(
    *,
    client,
    testnet: bool,
    logger,
    state_store=None,
    now_provider=None,
    stream_client_factory=None,
    reconnect_sleep_fn=None,
    audit_recorder_path: Path | None = None,
    runtime_db_path: Path | None = None,
) -> int:
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    reconnect_sleep_fn = reconnect_sleep_fn or (lambda seconds: time.sleep(seconds))
    audit_recorder = (
        AuditRecorder(path=audit_recorder_path, runtime_db_path=runtime_db_path, source="user-stream")
        if audit_recorder_path is not None
        else None
    )
    runtime_state_store = _build_runtime_state_store(audit_recorder=audit_recorder)
    stored_state = state_store.load() if state_store is not None else None
    current_now = now_provider()
    state = StrategyState(
        current_day=current_now.date(),
        previous_leader_symbol=stored_state.previous_leader_symbol if stored_state is not None else None,
        positions=stored_state.positions or {} if stored_state is not None else {},
        recent_stop_loss_exits={
            symbol: datetime.fromisoformat(timestamp)
            for symbol, timestamp in (stored_state.recent_stop_loss_exits or {}).items()
        }
        if stored_state is not None
        else {},
    )
    processed_event_ids = set(stored_state.processed_event_ids or []) if stored_state is not None else set()
    order_statuses = dict(stored_state.order_statuses or {}) if stored_state is not None else {}
    stream_client_factory = stream_client_factory or (lambda **kwargs: BinanceUserStreamClient(**kwargs))

    def _on_event(event) -> None:
        nonlocal state, processed_event_ids, order_statuses
        logger(f"event={event.event_type} symbol={event.symbol}")
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="user_stream_event",
                now=event.event_time or now_provider(),
                payload={
                    "event_type": event.event_type,
                    "symbol": event.symbol,
                    "order_status": event.order_status,
                    "execution_type": event.execution_type,
                    "side": event.side,
                    "order_id": event.order_id,
                    "trade_id": event.trade_id,
                },
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=event.event_time or now_provider(),
                responses=[
                    {
                        "symbol": event.symbol,
                        "status": event.order_status,
                        "side": event.side,
                        "type": event.original_order_type,
                        "orderId": event.order_id,
                        "tradeId": event.trade_id,
                    }
                ],
                action_type="stream_order_update",
            )
        event_id = user_stream_event_id(event)
        if event_id is not None and event_id in processed_event_ids:
            return
        trade_fill = extract_trade_fill(event)
        if trade_fill is not None and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            try:
                insert_trade_fill(
                    path=audit_recorder.runtime_db_path,
                    timestamp=event.event_time or now_provider(),
                    source=audit_recorder.source,
                    symbol=trade_fill.get("symbol"),
                    order_id=trade_fill.get("order_id"),
                    trade_id=trade_fill.get("trade_id"),
                    client_order_id=trade_fill.get("client_order_id"),
                    order_status=trade_fill.get("order_status"),
                    execution_type=trade_fill.get("execution_type"),
                    side=trade_fill.get("side"),
                    order_type=trade_fill.get("order_type"),
                    quantity=trade_fill.get("quantity"),
                    cumulative_quantity=trade_fill.get("cumulative_quantity"),
                    average_price=trade_fill.get("average_price"),
                    last_price=trade_fill.get("last_price"),
                    realized_pnl=trade_fill.get("realized_pnl"),
                    commission=trade_fill.get("commission"),
                    commission_asset=trade_fill.get("commission_asset"),
                    payload=event.payload,
                )
                rebuild_trade_analytics(path=audit_recorder.runtime_db_path)
            except Exception:
                pass
        algo_order = extract_algo_order_event(event)
        if algo_order is not None and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            try:
                insert_algo_order(
                    path=audit_recorder.runtime_db_path,
                    timestamp=event.event_time or now_provider(),
                    source=audit_recorder.source,
                    symbol=algo_order.get("symbol"),
                    algo_id=algo_order.get("algo_id"),
                    client_algo_id=algo_order.get("client_algo_id"),
                    algo_status=algo_order.get("algo_status"),
                    side=algo_order.get("side"),
                    order_type=algo_order.get("order_type"),
                    trigger_price=algo_order.get("trigger_price"),
                    payload=event.payload,
                )
            except Exception:
                pass
        account_flows = extract_account_flows(event)
        if account_flows and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            for flow in account_flows:
                try:
                    insert_account_flow(
                        path=audit_recorder.runtime_db_path,
                        timestamp=event.event_time or now_provider(),
                        source=audit_recorder.source,
                        reason=flow.get("reason"),
                        asset=flow.get("asset"),
                        wallet_balance=flow.get("wallet_balance"),
                        cross_wallet_balance=flow.get("cross_wallet_balance"),
                        balance_change=flow.get("balance_change"),
                        payload=event.payload,
                    )
                except Exception as exc:
                    logger(
                        "account-flow-insert-error "
                        f"reason={flow.get('reason')} asset={flow.get('asset')} error={exc}"
                    )
                    if audit_recorder is not None:
                        audit_recorder.record(
                            event_type="account_flow_insert_error",
                            now=event.event_time or now_provider(),
                            payload={
                                "reason": flow.get("reason"),
                                "asset": flow.get("asset"),
                                "balance_change": str(flow.get("balance_change")),
                                "error": str(exc),
                            },
                        )
        order_status_update = extract_order_status_update(event)
        if order_status_update is not None:
            order_id, order_snapshot = order_status_update
            if order_snapshot is None:
                order_statuses.pop(order_id, None)
            else:
                order_statuses[order_id] = order_snapshot
        # Also process algo order status updates (for stop-loss orders)
        algo_order_status_update = extract_algo_order_status_update(event)
        if algo_order_status_update is not None:
            algo_key, algo_snapshot = algo_order_status_update
            if algo_snapshot is None:
                order_statuses.pop(algo_key, None)
            else:
                order_statuses[algo_key] = algo_snapshot
        state = apply_user_stream_event_to_state(state=state, event=event, order_statuses=order_statuses)
        if event_id is not None:
            processed_event_ids.add(event_id)
        if state_store is not None:
            _merge_save_strategy_state(
                state_store=state_store,
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=sorted(processed_event_ids),
                    order_statuses=order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in state.recent_stop_loss_exits.items()
                    },
                ),
            )
        _record_position_snapshot(
            audit_recorder=audit_recorder,
            now=event.event_time or now_provider(),
            leader_symbol=state.previous_leader_symbol,
            position_count=len(state.positions),
            order_status_count=len(order_statuses),
            payload={"event_type": event.event_type, "symbol": event.symbol},
        )

    def _prewarm_state() -> None:
        nonlocal state, order_statuses
        fetch_position_risk = getattr(client, "fetch_position_risk", None)
        fetch_open_orders = getattr(client, "fetch_open_orders", None)
        if not callable(fetch_position_risk) or not callable(fetch_open_orders):
            return
        position_risk = fetch_position_risk()
        open_orders = fetch_open_orders()
        # Also fetch open algo orders for stop-loss tracking
        fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
        open_algo_orders = []
        if callable(fetch_open_algo_orders):
            try:
                open_algo_orders = fetch_open_algo_orders()
            except Exception:
                open_algo_orders = []
        restored_state = restore_state(
            current_day=state.current_day.isoformat(),
            previous_leader_symbol=state.previous_leader_symbol,
            position_risk=position_risk,
            open_orders=open_orders,
        )
        state = replace(state, positions=restored_state.positions)
        order_statuses = {
            str(order.get("orderId")): {
                "symbol": order.get("symbol"),
                "status": order.get("status"),
                "execution_type": None,
                "side": order.get("side"),
                "original_order_type": order.get("type"),
                "stop_price": order.get("stopPrice"),
                "event_time": None,
            }
            for order in open_orders
            if order.get("orderId") not in (None, "")
        }
        # Add algo orders to order_statuses with "algo:" prefix
        for algo_order in open_algo_orders:
            algo_id = algo_order.get("algoId")
            if algo_id is None:
                continue
            order_statuses[f"algo:{algo_id}"] = {
                "symbol": algo_order.get("symbol"),
                "status": algo_order.get("algoStatus"),
                "side": algo_order.get("side"),
                "client_order_id": algo_order.get("clientAlgoId"),
                "original_order_type": algo_order.get("orderType"),
                "stop_price": algo_order.get("triggerPrice"),
                "event_time": None,
            }
        if state_store is not None:
            _merge_save_strategy_state(
                state_store=state_store,
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=sorted(processed_event_ids),
                    order_statuses=order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in state.recent_stop_loss_exits.items()
                    },
                ),
            )

    reconnect_attempt = 0
    while True:
        _prewarm_state()
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="user_stream_worker_start",
                now=now_provider(),
                payload={
                    "testnet": testnet,
                    "position_count": len(state.positions),
                    "tracked_order_status_count": len(order_statuses),
                    "reconnect_attempt": reconnect_attempt,
                },
            )
            _record_position_snapshot(
                audit_recorder=audit_recorder,
                now=now_provider(),
                leader_symbol=state.previous_leader_symbol,
                position_count=len(state.positions),
                order_status_count=len(order_statuses),
                payload={"event_type": "user_stream_worker_start", "testnet": testnet},
            )
        stream_client = stream_client_factory(rest_client=client, testnet=testnet)
        try:
            listen_key = stream_client.run_forever(on_event=_on_event)
            logger(f"listen_key={listen_key}")
            return 0
        except Exception as exc:
            reconnect_attempt += 1
            sleep_seconds = min(reconnect_attempt, 5)
            logger(f"stream-error attempt={reconnect_attempt} sleep={sleep_seconds}s error={exc}")
            reconnect_sleep_fn(sleep_seconds)


def cli_main(
    *,
    argv: list[str] | None = None,
    client_factory=None,
    broker_factory=None,
    now_provider=None,
    run_forever_fn=None,
    run_user_stream_fn=None,
    run_dashboard_fn=None,
    backfill_account_flows_fn=None,
) -> int:
    parser = argparse.ArgumentParser(prog="momentum_alpha")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_once_live_parser = subparsers.add_parser("run-once-live")
    run_once_live_parser.add_argument("--symbols", nargs="+")
    run_once_live_parser.add_argument("--previous-leader")
    run_once_live_parser.add_argument("--state-file")
    run_once_live_parser.add_argument("--testnet", action="store_true")
    run_once_live_parser.add_argument("--submit-orders", action="store_true")
    run_once_live_parser.add_argument("--audit-log-file")
    run_once_live_parser.add_argument("--runtime-db-file")
    poll_parser = subparsers.add_parser("poll")
    poll_parser.add_argument("--symbols", nargs="+")
    poll_parser.add_argument("--previous-leader")
    poll_parser.add_argument("--state-file")
    poll_parser.add_argument("--testnet", action="store_true")
    poll_parser.add_argument("--submit-orders", action="store_true")
    poll_parser.add_argument("--restore-positions", action="store_true")
    poll_parser.add_argument("--execute-stop-replacements", action="store_true")
    poll_parser.add_argument("--max-ticks", type=int)
    poll_parser.add_argument("--audit-log-file")
    poll_parser.add_argument("--runtime-db-file")
    user_stream_parser = subparsers.add_parser("user-stream")
    user_stream_parser.add_argument("--testnet", action="store_true")
    user_stream_parser.add_argument("--state-file")
    user_stream_parser.add_argument("--audit-log-file")
    user_stream_parser.add_argument("--runtime-db-file")
    healthcheck_parser = subparsers.add_parser("healthcheck")
    healthcheck_parser.add_argument("--state-file", required=True)
    healthcheck_parser.add_argument("--poll-log-file", required=True)
    healthcheck_parser.add_argument("--user-stream-log-file", required=True)
    healthcheck_parser.add_argument("--runtime-db-file", required=True)
    healthcheck_parser.add_argument("--audit-log-file")
    healthcheck_parser.add_argument("--max-state-age-seconds", type=int, default=3600)
    healthcheck_parser.add_argument("--max-poll-log-age-seconds", type=int, default=180)
    healthcheck_parser.add_argument("--max-user-stream-log-age-seconds", type=int, default=1800)
    healthcheck_parser.add_argument("--max-runtime-db-age-seconds", type=int, default=1800)
    healthcheck_parser.add_argument("--max-audit-log-age-seconds", type=int, default=1800)
    audit_report_parser = subparsers.add_parser("audit-report")
    audit_report_parser.add_argument("--audit-log-file")
    audit_report_parser.add_argument("--runtime-db-file")
    audit_report_parser.add_argument("--since-minutes", type=int, default=1440)
    audit_report_parser.add_argument("--limit", type=int, default=20)
    backfill_account_flows_parser = subparsers.add_parser("backfill-account-flows")
    backfill_account_flows_parser.add_argument("--runtime-db-file", required=True)
    backfill_account_flows_parser.add_argument("--start-time", required=True)
    backfill_account_flows_parser.add_argument("--end-time", required=True)
    backfill_account_flows_parser.add_argument("--testnet", action="store_true")
    dashboard_parser = subparsers.add_parser("dashboard")
    dashboard_parser.add_argument("--host", default="127.0.0.1")
    dashboard_parser.add_argument("--port", type=int, default=8080)
    dashboard_parser.add_argument("--state-file", required=True)
    dashboard_parser.add_argument("--poll-log-file", required=True)
    dashboard_parser.add_argument("--user-stream-log-file", required=True)
    dashboard_parser.add_argument("--audit-log-file")
    dashboard_parser.add_argument("--runtime-db-file")

    args = parser.parse_args(argv)
    def _default_client_factory(*, testnet: bool = False):
        api_key, api_secret = load_credentials_from_env()
        runtime_settings = load_runtime_settings_from_env()
        base_url = BINANCE_TESTNET_FAPI_BASE_URL if (testnet or runtime_settings["use_testnet"]) else None
        kwargs = {"api_key": api_key, "api_secret": api_secret}
        if base_url is not None:
            kwargs["base_url"] = base_url
        return BinanceRestClient(**kwargs)

    client_factory = client_factory or _default_client_factory
    broker_factory = broker_factory or (lambda client: BinanceBroker(client=client))
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    run_forever_fn = run_forever_fn or run_forever
    run_user_stream_fn = run_user_stream_fn or run_user_stream
    run_dashboard_fn = run_dashboard_fn or run_dashboard_server
    backfill_account_flows_fn = backfill_account_flows_fn or backfill_account_flows

    if args.command == "run-once-live":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        broker = broker_factory(client)
        state_store = FileStateStore(path=Path(os.path.abspath(args.state_file))) if args.state_file else None
        audit_recorder = _build_audit_recorder(
            explicit_path=args.audit_log_file,
            explicit_runtime_db_path=args.runtime_db_file,
            state_store=state_store,
            source="run-once-live",
        )
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        result = run_once_live(
            symbols=args.symbols,
            now=now_provider(),
            previous_leader_symbol=args.previous_leader,
            client=client,
            broker=broker,
            submit_orders=args.submit_orders,
            state_store=state_store,
            audit_recorder=audit_recorder,
        )
        entry_symbols = [order["symbol"] for order in result.execution_plan.entry_orders]
        print(f"mode={mode}")
        print(f"testnet={use_testnet}")
        print(f"entry_orders={entry_symbols}")
        print(f"broker_responses={len(result.broker_responses)}")
        return 0

    if args.command == "poll":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        state_store = FileStateStore(path=Path(os.path.abspath(args.state_file))) if args.state_file else None
        audit_recorder = _build_audit_recorder(
            explicit_path=args.audit_log_file,
            explicit_runtime_db_path=args.runtime_db_file,
            state_store=state_store,
            source="poll",
        )
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        print(
            "starting poll "
            f"mode={mode} symbols={args.symbols or 'AUTO'} "
            f"testnet={use_testnet} "
            f"restore_positions={args.restore_positions} "
            f"execute_stop_replacements={args.execute_stop_replacements} "
            f"max_ticks={args.max_ticks}"
        )
        return run_forever_fn(
            symbols=args.symbols,
            previous_leader_symbol=args.previous_leader,
            submit_orders=args.submit_orders,
            state_store=state_store,
            client_factory=lambda: _build_client_from_factory(client_factory=client_factory, testnet=use_testnet),
            broker_factory=broker_factory,
            now_provider=now_provider,
            restore_positions=args.restore_positions,
            execute_stop_replacements=args.execute_stop_replacements,
            max_ticks=args.max_ticks,
            audit_recorder=audit_recorder,
        )

    if args.command == "user-stream":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        state_store = FileStateStore(path=Path(os.path.abspath(args.state_file))) if args.state_file else None
        audit_path = resolve_audit_log_path(explicit_path=args.audit_log_file, state_store=state_store)
        runtime_db_path = resolve_runtime_db_path(
            explicit_path=args.runtime_db_file,
            state_store=state_store,
            audit_log_path=audit_path,
        )
        print(f"starting user-stream testnet={use_testnet}")
        try:
            return run_user_stream_fn(
                client=client,
                testnet=use_testnet,
                logger=print,
                state_store=state_store,
                audit_recorder_path=audit_path,
                runtime_db_path=runtime_db_path,
            )
        except TypeError:
            return run_user_stream_fn(client=client, testnet=use_testnet, logger=print)

    if args.command == "healthcheck":
        report = build_runtime_health_report(
            now=now_provider(),
            state_file=Path(os.path.abspath(args.state_file)),
            poll_log_file=Path(os.path.abspath(args.poll_log_file)),
            user_stream_log_file=Path(os.path.abspath(args.user_stream_log_file)),
            runtime_db_file=Path(os.path.abspath(args.runtime_db_file)),
            audit_log_file=Path(os.path.abspath(args.audit_log_file)) if args.audit_log_file else None,
            max_state_age_seconds=args.max_state_age_seconds,
            max_poll_log_age_seconds=args.max_poll_log_age_seconds,
            max_user_stream_log_age_seconds=args.max_user_stream_log_age_seconds,
            max_runtime_db_age_seconds=args.max_runtime_db_age_seconds,
            max_audit_log_age_seconds=args.max_audit_log_age_seconds,
        )
        print(f"overall={report.overall_status}")
        for item in report.items:
            print(f"{item.name} status={item.status} {item.message}")
        return 0 if report.overall_status == "OK" else 1

    if args.command == "audit-report":
        if args.runtime_db_file:
            from momentum_alpha.runtime_store import summarize_audit_events as summarize_runtime_db_events

            summary = summarize_runtime_db_events(
                path=Path(os.path.abspath(args.runtime_db_file)),
                now=now_provider(),
                since_minutes=args.since_minutes,
                limit=args.limit,
            )
        else:
            summary = summarize_audit_events(
                path=Path(os.path.abspath(args.audit_log_file)),
                now=now_provider(),
                since_minutes=args.since_minutes,
                limit=args.limit,
            )
        print(f"total_events={summary['total_events']}")
        for event_type, count in summary["counts"].items():
            print(f"{event_type}={count}")
        for event in summary["recent_events"]:
            print(f"recent timestamp={event['timestamp']} event_type={event['event_type']} payload={event['payload']}")
        return 0

    if args.command == "backfill-account-flows":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        inserted = backfill_account_flows_fn(
            client=client,
            runtime_db_path=Path(os.path.abspath(args.runtime_db_file)),
            start_time=_parse_cli_datetime(args.start_time),
            end_time=_parse_cli_datetime(args.end_time),
            logger=print,
        )
        print(f"backfilled_account_flows={inserted}")
        return 0

    if args.command == "dashboard":
        runtime_settings = load_runtime_settings_from_env()
        submit_orders_env = os.environ.get("SUBMIT_ORDERS", "").strip().lower() in {"1", "true", "yes", "on"}
        return run_dashboard_fn(
            host=args.host,
            port=args.port,
            state_file=Path(os.path.abspath(args.state_file)),
            poll_log_file=Path(os.path.abspath(args.poll_log_file)),
            user_stream_log_file=Path(os.path.abspath(args.user_stream_log_file)),
            audit_log_file=Path(os.path.abspath(args.audit_log_file)) if args.audit_log_file else Path(os.path.abspath(args.runtime_db_file)).with_name("audit.jsonl"),
            runtime_db_file=resolve_runtime_db_path(
                explicit_path=args.runtime_db_file,
                state_store=None,
                audit_log_path=Path(os.path.abspath(args.audit_log_file)) if args.audit_log_file else None,
            ),
            now_provider=now_provider,
            stop_budget_usdt=os.environ.get("STOP_BUDGET_USDT", "20"),
            testnet=runtime_settings["use_testnet"],
            submit_orders=submit_orders_env,
        )

    return 1


def run_forever(
    *,
    symbols: list[str] | None,
    previous_leader_symbol: str | None,
    submit_orders: bool,
    state_store,
    client_factory,
    broker_factory,
    now_provider,
    sleep_fn=time.sleep,
    logger=print,
    max_ticks: int | None = None,
    run_once_live_fn=run_once_live,
    restore_positions: bool = False,
    execute_stop_replacements: bool = False,
    audit_recorder: AuditRecorder | None = None,
) -> int:
    client = client_factory()
    broker = broker_factory(client)
    market_data_cache = LiveMarketDataCache()
    resolved_symbols = market_data_cache.resolve_symbols(symbols=symbols, client=client)
    rate_limited_until = None
    last_add_on_hour: int | None = None

    def _log(message: str) -> None:
        if hasattr(logger, "info"):
            logger.info(message)
        else:
            logger(message)

    _log(f"tracking symbols={resolved_symbols}")
    if audit_recorder is not None:
        audit_recorder.record(
            event_type="poll_worker_start",
            now=now_provider(),
            payload={
                "symbol_count": len(resolved_symbols),
                "submit_orders": submit_orders,
                "restore_positions": restore_positions,
                "execute_stop_replacements": execute_stop_replacements,
            },
        )
        _record_position_snapshot(
            audit_recorder=audit_recorder,
            now=now_provider(),
            leader_symbol=previous_leader_symbol,
            position_count=0,
            order_status_count=0,
            symbol_count=len(resolved_symbols),
            submit_orders=submit_orders,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
            payload={"event_type": "poll_worker_start"},
        )

    def _run_once(now):
        nonlocal rate_limited_until, last_add_on_hour
        if rate_limited_until is not None and now < rate_limited_until:
            _log(f"rate-limit-backoff until={rate_limited_until.isoformat()}")
            return
        # Initialize last_add_on_hour on first tick to skip add-on
        if last_add_on_hour is None:
            last_add_on_hour = now.hour
        _log(f"tick {now.isoformat()}")
        try:
            try:
                result = run_once_live_fn(
                    symbols=resolved_symbols,
                    now=now,
                    previous_leader_symbol=previous_leader_symbol,
                    client=client,
                    broker=broker,
                    submit_orders=submit_orders,
                    state_store=state_store,
                    restore_positions=restore_positions,
                    execute_stop_replacements=execute_stop_replacements,
                    market_data_cache=market_data_cache,
                    audit_recorder=audit_recorder,
                    last_add_on_hour=last_add_on_hour,
                )
            except TypeError:
                result = run_once_live_fn(
                    symbols=resolved_symbols,
                    now=now,
                    previous_leader_symbol=previous_leader_symbol,
                    client=client,
                    broker=broker,
                    submit_orders=submit_orders,
                    state_store=state_store,
                    restore_positions=restore_positions,
                    execute_stop_replacements=execute_stop_replacements,
                    last_add_on_hour=last_add_on_hour,
                )
            # Update last_add_on_hour from result
            new_hour = result.runtime_result.decision.new_last_add_on_hour
            if new_hour is not None and new_hour != last_add_on_hour:
                last_add_on_hour = new_hour
        except HTTPError as exc:
            if exc.code == 429:
                rate_limited_until = now + timedelta(minutes=2)
            raise
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="poll_tick",
                now=now,
                payload={"symbol_count": len(resolved_symbols), "rate_limited_until": rate_limited_until},
            )

    def _handle_error(exc, now):
        _log(f"error at {now.isoformat()}: {exc}")
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="poll_error",
                now=now,
                payload={"message": str(exc)},
            )

    run_loop(
        run_once=_run_once,
        now_provider=now_provider,
        sleep_fn=sleep_fn,
        max_ticks=max_ticks,
        error_handler=_handle_error,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(cli_main())
