from __future__ import annotations

import os
import argparse
import time
from dataclasses import dataclass, replace
from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.broker import BinanceBroker
from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceRestClient
from momentum_alpha.exchange_info import parse_exchange_info
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import build_stop_reconciliation_plan, restore_state
from momentum_alpha.scheduler import run_loop
from momentum_alpha.runtime import Runtime, build_runtime
from momentum_alpha.runtime import RuntimeTickResult, process_runtime_tick
from momentum_alpha.state_store import FileStateStore, StoredStrategyState
from momentum_alpha.user_stream import (
    BinanceUserStreamClient,
    apply_user_stream_event_to_state,
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


def load_credentials_from_env() -> tuple[str, str]:
    api_key = os.environ["BINANCE_API_KEY"]
    api_secret = os.environ["BINANCE_API_SECRET"]
    return api_key, api_secret


def load_runtime_settings_from_env() -> dict[str, bool]:
    raw_testnet = os.environ.get("BINANCE_USE_TESTNET", "")
    return {"use_testnet": raw_testnet.strip().lower() in {"1", "true", "yes", "on"}}


def _build_client_from_factory(*, client_factory, testnet: bool):
    try:
        return client_factory(testnet=testnet)
    except TypeError:
        return client_factory()


def build_runtime_from_snapshots(*, snapshots: list[dict]) -> Runtime:
    return build_runtime(snapshots=snapshots)


def run_once(
    *,
    snapshots: list[dict],
    now: datetime,
    previous_leader_symbol: str | None,
    client,
    broker: BinanceBroker,
    submit_orders: bool,
    initial_state: StrategyState | None = None,
) -> RunOnceResult:
    runtime = build_runtime_from_snapshots(snapshots=snapshots).with_exchange_symbols(
        parse_exchange_info(client.fetch_exchange_info())
    )
    state = initial_state or StrategyState(
        current_day=date(now.year, now.month, now.day),
        previous_leader_symbol=previous_leader_symbol,
        positions={},
    )
    runtime_result = process_runtime_tick(runtime=runtime, state=state, now=now)
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


def _build_live_snapshots(*, symbols: list[str], client, now: datetime) -> list[dict]:
    snapshots: list[dict] = []
    for symbol in symbols:
        ticker = client.fetch_ticker_price(symbol=symbol)
        try:
            latest_price = Decimal(ticker["price"])
        except (KeyError, InvalidOperation, TypeError):
            continue
        day_open_klines = _fetch_daily_open_klines(client=client, symbol=symbol, now=now)
        if not day_open_klines:
            continue
        hour_klines = _fetch_previous_hour_klines(client=client, symbol=symbol, now=now)
        current_hour_klines = _fetch_current_hour_klines(client=client, symbol=symbol, now=now)
        has_previous_hour_candle = len(hour_klines) > 0
        previous_hour_low = Decimal(hour_klines[0][3]) if has_previous_hour_candle else Decimal("0")
        current_hour_low = Decimal(current_hour_klines[0][3]) if current_hour_klines else previous_hour_low
        snapshots.append(
            {
                "symbol": symbol,
                "daily_open_price": Decimal(day_open_klines[0][1]),
                "latest_price": latest_price,
                "previous_hour_low": previous_hour_low,
                "tradable": True,
                "has_previous_hour_candle": has_previous_hour_candle,
                "current_hour_low": current_hour_low,
            }
        )
    return snapshots


def run_once_live(
    *,
    symbols: list[str],
    now: datetime,
    previous_leader_symbol: str | None,
    client,
    broker: BinanceBroker,
    submit_orders: bool,
    restore_positions: bool = False,
    execute_stop_replacements: bool = False,
    state_store=None,
) -> RunOnceResult:
    if previous_leader_symbol is None and state_store is not None:
        stored_state = state_store.load()
        if stored_state is not None:
            previous_leader_symbol = stored_state.previous_leader_symbol

    snapshots = _build_live_snapshots(symbols=symbols, client=client, now=now)
    initial_state = None
    if restore_positions:
        initial_state = restore_state(
            current_day=f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
            previous_leader_symbol=previous_leader_symbol,
            position_risk=client.fetch_position_risk(),
            open_orders=client.fetch_open_orders(),
        )

    result = run_once(
        snapshots=snapshots,
        now=now,
        previous_leader_symbol=previous_leader_symbol,
        client=client,
        broker=broker,
        submit_orders=submit_orders,
        initial_state=initial_state,
    )
    stop_replacements: list[tuple[str, Decimal]] = []
    if restore_positions and initial_state is not None:
        stop_replacements = build_stop_reconciliation_plan(
            state=initial_state,
            decision=result.runtime_result.decision,
        )
        if execute_stop_replacements and stop_replacements:
            broker.replace_stop_orders(
                replacements=[
                    (
                        symbol,
                        str(initial_state.positions[symbol].total_quantity),
                        str(stop_price),
                    )
                    for symbol, stop_price in stop_replacements
                    if symbol in initial_state.positions
                ]
            )
    if state_store is not None:
        state_store.merge_save(
            StoredStrategyState(
                current_day=f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
                previous_leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            )
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
) -> int:
    now_provider = now_provider or (lambda: datetime.utcnow().replace(tzinfo=timezone.utc))
    reconnect_sleep_fn = reconnect_sleep_fn or (lambda seconds: time.sleep(seconds))
    stored_state = state_store.load() if state_store is not None else None
    current_now = now_provider()
    state = StrategyState(
        current_day=current_now.date(),
        previous_leader_symbol=stored_state.previous_leader_symbol if stored_state is not None else None,
        positions=stored_state.positions or {} if stored_state is not None else {},
    )
    processed_event_ids = set(stored_state.processed_event_ids or []) if stored_state is not None else set()
    order_statuses = dict(stored_state.order_statuses or {}) if stored_state is not None else {}
    stream_client_factory = stream_client_factory or (lambda **kwargs: BinanceUserStreamClient(**kwargs))

    def _on_event(event) -> None:
        nonlocal state, processed_event_ids, order_statuses
        logger(f"event={event.event_type} symbol={event.symbol}")
        event_id = user_stream_event_id(event)
        if event_id is not None and event_id in processed_event_ids:
            return
        order_status_update = extract_order_status_update(event)
        if order_status_update is not None:
            order_id, order_snapshot = order_status_update
            if order_snapshot is None:
                order_statuses.pop(order_id, None)
            else:
                order_statuses[order_id] = order_snapshot
        state = apply_user_stream_event_to_state(state=state, event=event, order_statuses=order_statuses)
        if event_id is not None:
            processed_event_ids.add(event_id)
        if state_store is not None:
            state_store.merge_save(
                StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=sorted(processed_event_ids),
                    order_statuses=order_statuses,
                )
            )

    def _prewarm_state() -> None:
        nonlocal state, order_statuses
        fetch_position_risk = getattr(client, "fetch_position_risk", None)
        fetch_open_orders = getattr(client, "fetch_open_orders", None)
        if not callable(fetch_position_risk) or not callable(fetch_open_orders):
            return
        position_risk = fetch_position_risk()
        open_orders = fetch_open_orders()
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
        if state_store is not None:
            state_store.merge_save(
                StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=sorted(processed_event_ids),
                    order_statuses=order_statuses,
                )
            )

    reconnect_attempt = 0
    while True:
        _prewarm_state()
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
) -> int:
    parser = argparse.ArgumentParser(prog="momentum_alpha")
    subparsers = parser.add_subparsers(dest="command", required=True)
    run_once_live_parser = subparsers.add_parser("run-once-live")
    run_once_live_parser.add_argument("--symbols", nargs="+", required=True)
    run_once_live_parser.add_argument("--previous-leader")
    run_once_live_parser.add_argument("--state-file")
    run_once_live_parser.add_argument("--testnet", action="store_true")
    run_once_live_parser.add_argument("--submit-orders", action="store_true")
    poll_parser = subparsers.add_parser("poll")
    poll_parser.add_argument("--symbols", nargs="+", required=True)
    poll_parser.add_argument("--previous-leader")
    poll_parser.add_argument("--state-file")
    poll_parser.add_argument("--testnet", action="store_true")
    poll_parser.add_argument("--submit-orders", action="store_true")
    poll_parser.add_argument("--restore-positions", action="store_true")
    poll_parser.add_argument("--execute-stop-replacements", action="store_true")
    poll_parser.add_argument("--max-ticks", type=int)
    user_stream_parser = subparsers.add_parser("user-stream")
    user_stream_parser.add_argument("--testnet", action="store_true")

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
    now_provider = now_provider or (lambda: datetime.utcnow())
    run_forever_fn = run_forever_fn or run_forever
    run_user_stream_fn = run_user_stream_fn or run_user_stream

    if args.command == "run-once-live":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        broker = broker_factory(client)
        state_store = FileStateStore(path=Path(os.path.abspath(args.state_file))) if args.state_file else None
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        result = run_once_live(
            symbols=args.symbols,
            now=now_provider(),
            previous_leader_symbol=args.previous_leader,
            client=client,
            broker=broker,
            submit_orders=args.submit_orders,
            state_store=state_store,
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
        mode = "LIVE" if args.submit_orders else "DRY_RUN"
        print(
            "starting poll "
            f"mode={mode} symbols={args.symbols} "
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
        )

    if args.command == "user-stream":
        runtime_settings = load_runtime_settings_from_env()
        use_testnet = args.testnet or runtime_settings["use_testnet"]
        client = _build_client_from_factory(client_factory=client_factory, testnet=use_testnet)
        print(f"starting user-stream testnet={use_testnet}")
        return run_user_stream_fn(client=client, testnet=use_testnet, logger=print)

    return 1


def run_forever(
    *,
    symbols: list[str],
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
) -> int:
    client = client_factory()
    broker = broker_factory(client)

    def _log(message: str) -> None:
        if hasattr(logger, "info"):
            logger.info(message)
        else:
            logger(message)

    def _run_once(now):
        _log(f"tick {now.isoformat()}")
        run_once_live_fn(
            symbols=symbols,
            now=now,
            previous_leader_symbol=previous_leader_symbol,
            client=client,
            broker=broker,
            submit_orders=submit_orders,
            state_store=state_store,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
        )

    def _handle_error(exc, now):
        _log(f"error at {now.isoformat()}: {exc}")

    run_loop(
        run_once=_run_once,
        now_provider=now_provider,
        sleep_fn=sleep_fn,
        max_ticks=max_ticks,
        error_handler=_handle_error,
    )
    return 0
