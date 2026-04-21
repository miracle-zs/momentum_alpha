from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import restore_state
from momentum_alpha.runtime_store import RuntimeStateStore, rebuild_trade_analytics
from momentum_alpha.runtime_store import insert_account_flow, insert_algo_order, insert_trade_fill
from momentum_alpha.strategy_state_codec import StoredStrategyState
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


def _build_initial_user_stream_state(
    stored_state: StoredStrategyState | None,
    current_now: datetime,
) -> UserStreamWorkerContext:
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
) -> int:
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    reconnect_sleep_fn = reconnect_sleep_fn or (lambda seconds: time.sleep(seconds))
    stream_client_factory = stream_client_factory or (lambda **kwargs: BinanceUserStreamClient(**kwargs))
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

    def _prewarm_state() -> None:
        fetch_position_risk = getattr(client, "fetch_position_risk", None)
        fetch_open_orders = getattr(client, "fetch_open_orders", None)
        if not callable(fetch_position_risk) or not callable(fetch_open_orders):
            return
        position_risk = fetch_position_risk()
        open_orders = fetch_open_orders()
        fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
        open_algo_orders = []
        if callable(fetch_open_algo_orders):
            try:
                open_algo_orders = fetch_open_algo_orders()
            except Exception:
                open_algo_orders = []
        restored_state = restore_state(
            current_day=context.state.current_day.isoformat(),
            previous_leader_symbol=context.state.previous_leader_symbol,
            position_risk=position_risk,
            open_orders=open_orders,
        )
        context.state = replace(context.state, positions=restored_state.positions)
        context.order_statuses = {
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
            save_user_stream_strategy_state_fn(
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=context.state.current_day.isoformat(),
                    previous_leader_symbol=context.state.previous_leader_symbol,
                    positions=context.state.positions,
                    processed_event_ids=context.processed_event_ids,
                    order_statuses=context.order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in context.state.recent_stop_loss_exits.items()
                    },
                ),
                now=now_provider(),
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
    try:
        while True:
            _prewarm_state()
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
                _record_position_snapshot(
                    audit_recorder=audit_recorder,
                    now=now_provider(),
                    leader_symbol=context.state.previous_leader_symbol,
                    position_count=len(context.state.positions),
                    order_status_count=len(context.order_statuses),
                    payload={"event_type": "user_stream_worker_start", "testnet": testnet},
                )
            stream_client = stream_client_factory(rest_client=client, testnet=testnet)
            try:
                listen_key = stream_client.run_forever(on_event=event_handler)
                logger(f"listen_key={listen_key}")
                return 0
            except Exception as exc:
                reconnect_attempt += 1
                sleep_seconds = min(reconnect_attempt, 5)
                logger(f"stream-error attempt={reconnect_attempt} sleep={sleep_seconds}s error={exc}")
                reconnect_sleep_fn(sleep_seconds)
    finally:
        if scheduler is not None:
            scheduler.close()
