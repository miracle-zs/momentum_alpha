from __future__ import annotations

import signal
import threading
import time
from dataclasses import replace
from datetime import timedelta, timezone
from urllib.error import HTTPError

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.binance_client import rate_limit_backoff_seconds
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.config import StrategyConfig
from momentum_alpha.market_data import LiveMarketDataCache
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.scheduler import run_loop
from momentum_alpha.structured_log import emit_structured_log
from momentum_alpha.telemetry import _record_position_snapshot
from momentum_alpha.trace_ids import build_intent_id_from_client_order_id

from .poll_worker_core import run_once_live


AUTO_SYMBOL_REFRESH_INTERVAL = timedelta(hours=1)


def _install_shutdown_handlers(
    *,
    shutdown_requested: threading.Event,
    signal_module=signal,
    is_main_thread=None,
):
    if is_main_thread is None:
        is_main_thread = lambda: threading.current_thread() is threading.main_thread()
    if not is_main_thread():
        return lambda: None

    signal_numbers = (signal_module.SIGTERM, signal_module.SIGINT)
    previous_handlers = {
        signal_number: signal_module.getsignal(signal_number)
        for signal_number in signal_numbers
    }

    def _request_shutdown(signal_number, _frame) -> None:
        shutdown_requested.set()

    for signal_number in signal_numbers:
        signal_module.signal(signal_number, _request_shutdown)

    def _restore() -> None:
        for signal_number in signal_numbers:
            signal_module.signal(signal_number, previous_handlers[signal_number])

    return _restore


def _is_add_on_client_order_id(client_order_id: str | None) -> bool:
    intent_id = build_intent_id_from_client_order_id(client_order_id)
    if intent_id is None:
        return False
    leg_token = intent_id.rsplit("_", 1)[-1]
    return leg_token.startswith("a")


def _has_retryable_add_on_entry_failure(result) -> bool:
    if not result.runtime_result.decision.add_on_entries:
        return False
    for failure in getattr(result, "entry_order_failures", []) or []:
        client_order_id = failure.get("clientOrderId") or failure.get("client_order_id")
        if _is_add_on_client_order_id(client_order_id) and failure.get("retryable", True):
            return True
    return False


def run_forever(
    *,
    symbols: list[str] | None,
    previous_leader_symbol: str | None,
    submit_orders: bool,
    runtime_state_store: RuntimeStateStore | None,
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
    strategy_config = StrategyConfig.from_env()
    client = client_factory()
    broker = broker_factory(client)
    market_data_cache = LiveMarketDataCache()
    resolved_symbols = market_data_cache.resolve_symbols(symbols=symbols, client=client)
    rate_limited_until = None
    last_add_on_hour: int | None = None
    last_auto_symbol_refresh_at = None

    def _log(event: str, *, level: str = "INFO", **fields) -> None:
        emit_structured_log(logger, service="poll", event=event, level=level, **fields)

    _log("tracking", symbols=resolved_symbols)
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
        nonlocal last_auto_symbol_refresh_at
        nonlocal resolved_symbols, previous_leader_symbol
        if rate_limited_until is not None and now < rate_limited_until:
            _log("rate-limit-backoff", level="WARN", until=rate_limited_until)
            return
        if last_add_on_hour is None:
            persisted_state = runtime_state_store.load() if runtime_state_store is not None else None
            if (
                persisted_state is not None
                and persisted_state.current_day == now.astimezone(timezone.utc).date().isoformat()
                and persisted_state.last_add_on_hour == now.hour
            ):
                last_add_on_hour = persisted_state.last_add_on_hour
            else:
                last_add_on_hour = (now.hour - 1) % 24 if now.minute == 0 else now.hour
        if symbols is None:
            if last_auto_symbol_refresh_at is None:
                last_auto_symbol_refresh_at = now
            elif now - last_auto_symbol_refresh_at >= AUTO_SYMBOL_REFRESH_INTERVAL:
                market_data_cache.refresh_exchange_symbols(client=client)
                last_auto_symbol_refresh_at = now
            resolved_symbols = list(market_data_cache.exchange_symbol_map(client=client).keys())
        _log("tick", now=now, last_add_on_hour=last_add_on_hour)
        try:
            result = run_once_live_fn(
                symbols=resolved_symbols,
                now=now,
                previous_leader_symbol=previous_leader_symbol,
                client=client,
                broker=broker,
                submit_orders=submit_orders,
                runtime_state_store=runtime_state_store,
                restore_positions=restore_positions,
                execute_stop_replacements=execute_stop_replacements,
                market_data_cache=market_data_cache,
                audit_recorder=audit_recorder,
                last_add_on_hour=last_add_on_hour,
                logger=logger,
                strategy_config=strategy_config,
            )
            new_hour = result.runtime_result.decision.new_last_add_on_hour
            if new_hour is not None and new_hour != last_add_on_hour and not _has_retryable_add_on_entry_failure(result):
                last_add_on_hour = new_hour
            previous_leader_symbol = result.runtime_result.next_state.previous_leader_symbol
            if result.rate_limit_error is not None:
                rate_limited_until = now + timedelta(
                    seconds=rate_limit_backoff_seconds(result.rate_limit_error, fallback_seconds=120),
                )
            if runtime_state_store is not None and last_add_on_hour is not None:
                effective_last_add_on_hour = last_add_on_hour

                def _persist_scheduler_state(existing: StoredStrategyState | None) -> StoredStrategyState:
                    if existing is None:
                        return StoredStrategyState(
                            current_day=now.astimezone(timezone.utc).date().isoformat(),
                            previous_leader_symbol=previous_leader_symbol,
                            last_add_on_hour=effective_last_add_on_hour,
                        )
                    return replace(existing, last_add_on_hour=effective_last_add_on_hour)

                runtime_state_store.atomic_update(_persist_scheduler_state)
        except HTTPError as exc:
            if exc.code in {418, 429}:
                rate_limited_until = now + timedelta(
                    seconds=rate_limit_backoff_seconds(exc, fallback_seconds=120),
                )
            raise
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="poll_tick",
                now=now,
                payload={"symbol_count": len(resolved_symbols), "rate_limited_until": rate_limited_until},
            )

    def _handle_error(exc, now):
        _log("error", level="ERROR", now=now, error=str(exc))
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="poll_error",
                now=now,
                payload={"message": str(exc)},
            )

    shutdown_requested = threading.Event()
    restore_shutdown_handlers = _install_shutdown_handlers(
        shutdown_requested=shutdown_requested,
    )
    try:
        run_loop(
            run_once=_run_once,
            now_provider=now_provider,
            sleep_fn=sleep_fn,
            max_ticks=max_ticks,
            error_handler=_handle_error,
            stop_requested=shutdown_requested.is_set,
        )
    finally:
        restore_shutdown_handlers()
        if shutdown_requested.is_set():
            _log("shutdown-complete")
    return 0
