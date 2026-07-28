from __future__ import annotations

import signal
import threading
import sqlite3
from dataclasses import dataclass, replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.binance_client import rate_limit_backoff_seconds
from momentum_alpha.models import StrategyState
from momentum_alpha.position_recovery import (
    fetch_complete_history,
    position_needs_trade_recovery,
    rebuild_position_from_trade_history,
)
from momentum_alpha.reconciliation import merge_position_history, restore_state
from momentum_alpha.runtime_store import RuntimeStateStore, rebuild_trade_analytics
from momentum_alpha.runtime_store import insert_account_flow, insert_algo_order, insert_trade_fill
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.structured_log import emit_structured_log
from momentum_alpha.telemetry import _record_broker_orders, _record_position_snapshot
from momentum_alpha.user_stream import (
    BinanceUserStreamClient,
    apply_user_stream_event_to_state,
    extract_account_flows,
    extract_algo_order_event,
    extract_algo_order_status_update,
    extract_order_status_update,
    extract_trade_fill,
    user_stream_event_id,
)

from .stream_worker_core import (
    UserStreamWorkerContext,
    _prune_processed_event_ids,
    _save_user_stream_strategy_state,
    build_user_stream_event_handler,
)
from .stream_worker_rebuild_scheduler import DebouncedRebuildScheduler


_USER_STREAM_ACTION_EVENT_TYPES = ("broker_submit", "broker_replace", "stop_replacements")


def _install_shutdown_handlers(
    *,
    shutdown_requested: threading.Event,
    active_stream_stop_event,
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

    def _request_shutdown(_signal_number, _frame) -> None:
        shutdown_requested.set()
        stream_stop_event = active_stream_stop_event()
        if stream_stop_event is not None:
            stream_stop_event.set()

    for signal_number in signal_numbers:
        signal_module.signal(signal_number, _request_shutdown)

    def _restore() -> None:
        for signal_number in signal_numbers:
            signal_module.signal(signal_number, previous_handlers[signal_number])

    return _restore


@dataclass(frozen=True)
class UserStreamWatchdogResult:
    should_reconnect: bool
    silence_seconds: int | None = None
    latest_action_event_type: str | None = None
    latest_action_timestamp: str | None = None
    latest_user_stream_event_timestamp: str | None = None


def _latest_audit_event(
    *,
    runtime_db_path: Path,
    event_types: tuple[str, ...],
    not_before: datetime | None = None,
) -> tuple[datetime, str, str] | None:
    if not runtime_db_path.exists():
        return None
    placeholders = ", ".join("?" for _ in event_types)
    params: list[str] = list(event_types)
    timestamp_filter = ""
    if not_before is not None:
        timestamp_filter = "AND timestamp >= ?"
        params.append(not_before.astimezone(timezone.utc).isoformat())
    connection = None
    try:
        connection = sqlite3.connect(runtime_db_path)
        row = connection.execute(
            f"""
            SELECT timestamp, event_type
            FROM audit_events
            WHERE event_type IN ({placeholders})
              {timestamp_filter}
            ORDER BY timestamp DESC, id DESC
            LIMIT 1
            """,
            params,
        ).fetchone()
    except sqlite3.Error:
        return None
    finally:
        if connection is not None:
            connection.close()
    if row is None or not row[0]:
        return None
    timestamp_text = str(row[0])
    return datetime.fromisoformat(timestamp_text).astimezone(timezone.utc), str(row[1]), timestamp_text


def _should_reconnect_stale_user_stream(
    *,
    runtime_db_path: Path,
    now: datetime,
    max_silence_seconds: int,
    not_before: datetime | None = None,
) -> UserStreamWatchdogResult:
    latest_action = _latest_audit_event(
        runtime_db_path=runtime_db_path,
        event_types=_USER_STREAM_ACTION_EVENT_TYPES,
        not_before=not_before,
    )
    if latest_action is None:
        return UserStreamWatchdogResult(should_reconnect=False)

    latest_action_time, latest_action_event_type, latest_action_timestamp = latest_action
    latest_event = _latest_audit_event(
        runtime_db_path=runtime_db_path,
        event_types=("user_stream_event",),
        not_before=not_before,
    )
    # An event after the action proves that the stream was alive at that point,
    # but it must not disable the watchdog forever. Continue measuring silence
    # from the latest actual stream event.
    reference_time = latest_action_time
    if latest_event is not None and latest_event[0] >= latest_action_time:
        reference_time = latest_event[0]
    silence_seconds = int(now.astimezone(timezone.utc).timestamp() - reference_time.timestamp())
    return UserStreamWatchdogResult(
        should_reconnect=silence_seconds > max_silence_seconds,
        silence_seconds=silence_seconds,
        latest_action_event_type=latest_action_event_type,
        latest_action_timestamp=latest_action_timestamp,
        latest_user_stream_event_timestamp=None if latest_event is None else latest_event[2],
    )


def _build_initial_user_stream_state(
    stored_state: StoredStrategyState | None,
    current_now: datetime,
) -> UserStreamWorkerContext:
    current_day = current_now.astimezone(timezone.utc).date()
    restore_daily_state = (
        stored_state is not None
        and stored_state.current_day == current_day.isoformat()
    )
    state = StrategyState(
        current_day=current_day,
        previous_leader_symbol=stored_state.previous_leader_symbol if stored_state is not None else None,
        positions=stored_state.positions or {} if stored_state is not None else {},
        recent_stop_loss_exits={
            symbol: datetime.fromisoformat(timestamp)
            for symbol, timestamp in (stored_state.recent_stop_loss_exits or {}).items()
        }
        if stored_state is not None
        else {},
        daily_base_signal_times={
            symbol: datetime.fromisoformat(timestamp)
            for symbol, timestamp in (stored_state.daily_base_signal_times or {}).items()
        }
        if restore_daily_state
        else {},
        daily_base_signal_counts=dict(stored_state.daily_base_signal_counts or {})
        if restore_daily_state
        else {},
    )
    processed_event_ids = dict(stored_state.processed_event_ids or {}) if stored_state is not None else {}
    order_statuses = dict(stored_state.order_statuses or {}) if stored_state is not None else {}
    return UserStreamWorkerContext(
        state=state,
        processed_event_ids=processed_event_ids,
        order_statuses=order_statuses,
    )


def run_user_stream(
    *,
    client,
    testnet: bool,
    logger,
    runtime_state_store: RuntimeStateStore | None = None,
    now_provider=None,
    stream_client_factory=None,
    reconnect_sleep_fn=None,
    runtime_db_path: Path | None = None,
    event_handler_factory=build_user_stream_event_handler,
    extract_trade_fill_fn=None,
    extract_algo_order_event_fn=None,
    extract_account_flows_fn=None,
    extract_order_status_update_fn=None,
    extract_algo_order_status_update_fn=None,
    user_stream_event_id_fn=None,
    apply_user_stream_event_to_state_fn=None,
    insert_trade_fill_fn=None,
    insert_algo_order_fn=None,
    insert_account_flow_fn=None,
    record_broker_orders_fn=None,
    record_position_snapshot_fn=None,
    save_user_stream_strategy_state_fn=None,
    prune_processed_event_ids_fn=None,
    rebuild_trade_analytics_fn=None,
    scheduler_factory=None,
    reconnect_on_stream_end: bool = False,
    max_stream_cycles: int | None = None,
    heartbeat_interval_seconds: int = 60,
    max_user_stream_silence_after_action_seconds: int = 1800,
    shutdown_requested: threading.Event | None = None,
    signal_module=signal,
    is_main_thread=None,
) -> int:
    shutdown_requested = shutdown_requested or threading.Event()
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    reconnect_sleep_fn = reconnect_sleep_fn or shutdown_requested.wait
    stream_client_factory = stream_client_factory or (lambda **kwargs: BinanceUserStreamClient(logger=logger, **kwargs))
    extract_trade_fill_fn = extract_trade_fill_fn or extract_trade_fill
    extract_algo_order_event_fn = extract_algo_order_event_fn or extract_algo_order_event
    extract_account_flows_fn = extract_account_flows_fn or extract_account_flows
    extract_order_status_update_fn = extract_order_status_update_fn or extract_order_status_update
    extract_algo_order_status_update_fn = extract_algo_order_status_update_fn or extract_algo_order_status_update
    user_stream_event_id_fn = user_stream_event_id_fn or user_stream_event_id
    apply_user_stream_event_to_state_fn = apply_user_stream_event_to_state_fn or apply_user_stream_event_to_state
    insert_trade_fill_fn = insert_trade_fill_fn or insert_trade_fill
    insert_algo_order_fn = insert_algo_order_fn or insert_algo_order
    insert_account_flow_fn = insert_account_flow_fn or insert_account_flow
    record_broker_orders_fn = record_broker_orders_fn or _record_broker_orders
    record_position_snapshot_fn = record_position_snapshot_fn or _record_position_snapshot
    save_user_stream_strategy_state_fn = save_user_stream_strategy_state_fn or _save_user_stream_strategy_state
    prune_processed_event_ids_fn = prune_processed_event_ids_fn or _prune_processed_event_ids
    rebuild_trade_analytics_fn = rebuild_trade_analytics_fn or rebuild_trade_analytics
    scheduler_factory = scheduler_factory or DebouncedRebuildScheduler

    audit_recorder = (
        AuditRecorder(runtime_db_path=runtime_db_path, source="user-stream", error_logger=logger)
        if runtime_db_path is not None
        else None
    )
    if runtime_state_store is None and runtime_db_path is not None:
        runtime_state_store = RuntimeStateStore(path=runtime_db_path)
    stored_state = runtime_state_store.load() if runtime_state_store is not None else None
    current_now = now_provider()
    context = _build_initial_user_stream_state(stored_state, current_now)
    scheduler = None
    if runtime_db_path is not None:
        scheduler = scheduler_factory(
            debounce_seconds=30,
            now_provider=now_provider,
            rebuild_fn=lambda: rebuild_trade_analytics_fn(path=runtime_db_path),
            logger=logger,
        )

    def _log(event: str, *, level: str = "INFO", **fields) -> None:
        emit_structured_log(logger, service="user-stream", event=event, level=level, **fields)

    def _record_heartbeat(*, reconnect_attempt: int) -> None:
        if audit_recorder is None:
            return
        audit_recorder.record(
            event_type="user_stream_heartbeat",
            now=now_provider(),
            payload={
                "testnet": testnet,
                "stream_active": True,
                "position_count": len(context.state.positions),
                "tracked_order_status_count": len(context.order_statuses),
                "reconnect_attempt": reconnect_attempt,
            },
        )

    def _start_heartbeat(*, reconnect_attempt: int, stream_stop_event, stream_cycle_started_at: datetime):
        if audit_recorder is None:
            return None, None
        stop_event = threading.Event()

        def _run() -> None:
            while not stop_event.is_set():
                _record_heartbeat(reconnect_attempt=reconnect_attempt)
                watchdog_result = _should_reconnect_stale_user_stream(
                    runtime_db_path=audit_recorder.runtime_db_path,
                    now=now_provider(),
                    max_silence_seconds=max_user_stream_silence_after_action_seconds,
                    not_before=stream_cycle_started_at,
                )
                if watchdog_result.should_reconnect:
                    _log(
                        "watchdog-reconnect",
                        level="WARNING",
                        silence_seconds=watchdog_result.silence_seconds,
                        latest_action_event_type=watchdog_result.latest_action_event_type,
                        latest_action_timestamp=watchdog_result.latest_action_timestamp,
                        latest_user_stream_event_timestamp=watchdog_result.latest_user_stream_event_timestamp,
                    )
                    stream_stop_event.set()
                    break
                if stop_event.wait(heartbeat_interval_seconds):
                    break

        thread = threading.Thread(target=_run, daemon=True)
        thread.start()
        return stop_event, thread

    def _prewarm_state() -> None:
        fetch_position_risk = getattr(client, "fetch_position_risk", None)
        fetch_open_orders = getattr(client, "fetch_open_orders", None)
        if not callable(fetch_position_risk) or not callable(fetch_open_orders):
            return
        previous_position_symbols = set(context.state.positions)
        previous_order_status_keys = set(context.order_statuses)
        position_risk = fetch_position_risk()
        open_orders = fetch_open_orders()
        fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
        open_algo_orders = []
        algo_order_snapshot_complete = False
        if callable(fetch_open_algo_orders):
            try:
                open_algo_orders = fetch_open_algo_orders()
                algo_order_snapshot_complete = True
            except Exception:
                open_algo_orders = []
        restored_open_orders = [*open_orders, *open_algo_orders]
        restored_state = restore_state(
            current_day=context.state.current_day.isoformat(),
            previous_leader_symbol=context.state.previous_leader_symbol,
            position_risk=position_risk,
            open_orders=restored_open_orders,
        )
        merged_positions = {
            symbol: merge_position_history(context.state.positions.get(symbol), position)
            for symbol, position in restored_state.positions.items()
        }
        fetch_user_trades = getattr(client, "fetch_user_trades", None)
        fetch_all_orders = getattr(client, "fetch_all_orders", None)
        if callable(fetch_user_trades) and callable(fetch_all_orders):
            recovery_end = now_provider().astimezone(timezone.utc)
            recovery_start = recovery_end - timedelta(days=6, hours=23)
            for symbol, position in list(merged_positions.items()):
                if not position_needs_trade_recovery(position):
                    continue
                try:
                    start_time_ms = int(recovery_start.timestamp() * 1000)
                    end_time_ms = int(recovery_end.timestamp() * 1000)
                    rebuilt = rebuild_position_from_trade_history(
                        position=position,
                        trades=fetch_complete_history(
                            fetch_user_trades,
                            symbol=symbol,
                            start_time_ms=start_time_ms,
                            end_time_ms=end_time_ms,
                        ),
                        orders=fetch_complete_history(
                            fetch_all_orders,
                            symbol=symbol,
                            start_time_ms=start_time_ms,
                            end_time_ms=end_time_ms,
                        ),
                    )
                    if rebuilt is not None:
                        merged_positions[symbol] = rebuilt
                        _log(
                            "position-trade-recovery",
                            symbol=symbol,
                            quantity=rebuilt.total_quantity,
                            leg_count=len(rebuilt.legs),
                        )
                except Exception as exc:
                    _log("position-trade-recovery-error", level="WARNING", symbol=symbol, error=str(exc))
        context.state = replace(context.state, positions=merged_positions)
        context.order_statuses = {
            str(order.get("orderId")): {
                "symbol": order.get("symbol"),
                "status": order.get("status"),
                "execution_type": None,
                "side": order.get("side"),
                "client_order_id": order.get("clientOrderId") or order.get("origClientOrderId"),
                "original_order_type": order.get("type"),
                "stop_price": order.get("stopPrice"),
                "event_time": None,
            }
            for order in open_orders
            if order.get("orderId") not in (None, "")
        }
        for algo_order in open_algo_orders:
            algo_id = algo_order.get("algoId")
            client_algo_id = algo_order.get("clientAlgoId")
            key_id = client_algo_id or algo_id
            if key_id is None:
                continue
            context.order_statuses[f"algo:{key_id}"] = {
                "symbol": algo_order.get("symbol"),
                "status": algo_order.get("algoStatus"),
                "side": algo_order.get("side"),
                "client_order_id": client_algo_id,
                "original_order_type": algo_order.get("orderType"),
                "stop_price": algo_order.get("triggerPrice"),
                "event_time": None,
            }
        if runtime_state_store is not None:
            current_order_status_keys = set(context.order_statuses)
            removed_order_status_keys = {
                key
                for key in previous_order_status_keys - current_order_status_keys
                if not key.startswith("algo:") or algo_order_snapshot_complete
            }
            save_user_stream_strategy_state_fn(
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=context.state.current_day.isoformat(),
                    previous_leader_symbol=context.state.previous_leader_symbol,
                    daily_base_signal_times={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in context.state.daily_base_signal_times.items()
                    },
                    daily_base_signal_counts=dict(context.state.daily_base_signal_counts),
                    positions=context.state.positions,
                    processed_event_ids=context.processed_event_ids,
                    order_statuses=context.order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in context.state.recent_stop_loss_exits.items()
                    },
                ),
                now=now_provider(),
                removed_position_symbols=previous_position_symbols - set(context.state.positions),
                removed_order_status_keys=removed_order_status_keys,
                prune_processed_event_ids_fn=prune_processed_event_ids_fn,
            )

    event_handler = event_handler_factory(
        logger=logger,
        runtime_state_store=runtime_state_store,
        audit_recorder=audit_recorder,
        now_provider=now_provider,
        context=context,
        extract_trade_fill_fn=extract_trade_fill_fn,
        extract_algo_order_event_fn=extract_algo_order_event_fn,
        extract_account_flows_fn=extract_account_flows_fn,
        extract_order_status_update_fn=extract_order_status_update_fn,
        extract_algo_order_status_update_fn=extract_algo_order_status_update_fn,
        user_stream_event_id_fn=user_stream_event_id_fn,
        apply_user_stream_event_to_state_fn=apply_user_stream_event_to_state_fn,
        insert_trade_fill_fn=insert_trade_fill_fn,
        insert_algo_order_fn=insert_algo_order_fn,
        insert_account_flow_fn=insert_account_flow_fn,
        record_broker_orders_fn=record_broker_orders_fn,
        record_position_snapshot_fn=record_position_snapshot_fn,
        save_user_stream_strategy_state_fn=save_user_stream_strategy_state_fn,
        on_trade_fill_persisted_fn=scheduler.notify if scheduler is not None else None,
        prune_processed_event_ids_fn=prune_processed_event_ids_fn,
    )

    reconnect_attempt = 0
    completed_stream_cycles = 0
    active_stream_stop_event: list[threading.Event | None] = [None]
    restore_shutdown_handlers = _install_shutdown_handlers(
        shutdown_requested=shutdown_requested,
        active_stream_stop_event=lambda: active_stream_stop_event[0],
        signal_module=signal_module,
        is_main_thread=is_main_thread,
    )
    try:
        while not shutdown_requested.is_set():
            try:
                _prewarm_state()
            except Exception as exc:
                if shutdown_requested.is_set():
                    break
                reconnect_attempt += 1
                sleep_seconds = rate_limit_backoff_seconds(exc, fallback_seconds=120)
                if sleep_seconds <= 0:
                    sleep_seconds = min(reconnect_attempt, 5)
                _log(
                    "prewarm-error",
                    level="ERROR",
                    attempt=reconnect_attempt,
                    sleep_seconds=sleep_seconds,
                    error=str(exc),
                )
                reconnect_sleep_fn(sleep_seconds)
                continue
            if shutdown_requested.is_set():
                break
            if audit_recorder is not None:
                audit_recorder.record(
                    event_type="user_stream_worker_start",
                    now=now_provider(),
                    payload={
                        "testnet": testnet,
                        "position_count": len(context.state.positions),
                        "tracked_order_status_count": len(context.order_statuses),
                        "reconnect_attempt": reconnect_attempt,
                    },
                )
                _log(
                    "worker-start",
                    testnet=testnet,
                    position_count=len(context.state.positions),
                    tracked_order_status_count=len(context.order_statuses),
                    reconnect_attempt=reconnect_attempt,
                )
                _record_position_snapshot(
                    audit_recorder=audit_recorder,
                    now=now_provider(),
                    leader_symbol=context.state.previous_leader_symbol,
                    decision_id=None,
                    position_count=len(context.state.positions),
                    order_status_count=len(context.order_statuses),
                    payload={"event_type": "user_stream_worker_start", "testnet": testnet},
                )
            stream_cycle_started_at = now_provider()
            stream_stop_event = threading.Event()
            active_stream_stop_event[0] = stream_stop_event
            if shutdown_requested.is_set():
                stream_stop_event.set()
                break
            stream_client = stream_client_factory(rest_client=client, testnet=testnet)
            if hasattr(stream_client, "stop_event_factory"):
                stream_client.stop_event_factory = lambda: stream_stop_event
            heartbeat_stop_event, heartbeat_thread = _start_heartbeat(
                reconnect_attempt=reconnect_attempt,
                stream_stop_event=stream_stop_event,
                stream_cycle_started_at=stream_cycle_started_at,
            )
            try:
                listen_key = stream_client.run_forever(on_event=event_handler)
                _log("stream-ended")
                if shutdown_requested.is_set():
                    break
                if not reconnect_on_stream_end:
                    return 0
                completed_stream_cycles += 1
                reconnect_attempt += 1
                if max_stream_cycles is not None and completed_stream_cycles >= max_stream_cycles:
                    _log(
                        "stream-ended",
                        attempt=reconnect_attempt,
                        max_stream_cycles=max_stream_cycles,
                    )
                    return 0
                sleep_seconds = min(reconnect_attempt, 5)
                _log("stream-ended", attempt=reconnect_attempt, sleep_seconds=sleep_seconds)
                reconnect_sleep_fn(sleep_seconds)
            except Exception as exc:
                if shutdown_requested.is_set():
                    _log("stream-ended", reason="shutdown")
                    break
                reconnect_attempt += 1
                sleep_seconds = rate_limit_backoff_seconds(exc, fallback_seconds=120)
                if sleep_seconds <= 0:
                    sleep_seconds = min(reconnect_attempt, 5)
                _log("stream-error", level="ERROR", attempt=reconnect_attempt, sleep_seconds=sleep_seconds, error=str(exc))
                reconnect_sleep_fn(sleep_seconds)
            finally:
                if heartbeat_stop_event is not None:
                    heartbeat_stop_event.set()
                if heartbeat_thread is not None:
                    heartbeat_thread.join(timeout=1)
                active_stream_stop_event[0] = None
    finally:
        active_stream_stop_event[0] = None
        restore_shutdown_handlers()
        if scheduler is not None:
            scheduler.close()
        if shutdown_requested.is_set():
            _log("shutdown-complete")
    return 0
