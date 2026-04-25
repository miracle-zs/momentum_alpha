from __future__ import annotations

import time
from datetime import timedelta
from urllib.error import HTTPError

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.market_data import LiveMarketDataCache
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.scheduler import run_loop
from momentum_alpha.structured_log import emit_structured_log
from momentum_alpha.telemetry import _record_position_snapshot

from .poll_worker_core import run_once_live

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
    client = client_factory()
    broker = broker_factory(client)
    market_data_cache = LiveMarketDataCache()
    resolved_symbols = market_data_cache.resolve_symbols(symbols=symbols, client=client)
    rate_limited_until = None
    last_add_on_hour: int | None = None

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
        if rate_limited_until is not None and now < rate_limited_until:
            _log("rate-limit-backoff", level="WARN", until=rate_limited_until)
            return
        if last_add_on_hour is None:
            last_add_on_hour = now.hour
        _log("tick", now=now, last_add_on_hour=last_add_on_hour)
        try:
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
                )
            except TypeError:
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
                    last_add_on_hour=last_add_on_hour,
                )
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
        _log("error", level="ERROR", now=now, error=str(exc))
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
