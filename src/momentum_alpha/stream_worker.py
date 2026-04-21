from __future__ import annotations

import time
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from pathlib import Path

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
from momentum_alpha.reconciliation import restore_state
from momentum_alpha.runtime_store import (
    MAX_PROCESSED_EVENT_ID_AGE_HOURS,
    RuntimeStateStore,
    insert_account_flow,
    insert_algo_order,
    insert_trade_fill,
)
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


def _prune_processed_event_ids(
    processed_event_ids: dict[str, str] | None,
    now: datetime,
) -> dict[str, str]:
    """Remove event IDs older than MAX_PROCESSED_EVENT_ID_AGE_HOURS."""
    if not processed_event_ids:
        return {}
    cutoff = now - timedelta(hours=MAX_PROCESSED_EVENT_ID_AGE_HOURS)
    pruned = {}
    for event_id, timestamp_str in processed_event_ids.items():
        try:
            timestamp = datetime.fromisoformat(timestamp_str)
            if timestamp >= cutoff:
                pruned[event_id] = timestamp_str
        except (ValueError, TypeError):
            pruned[event_id] = timestamp_str
    return pruned


def _save_user_stream_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
    now: datetime,
) -> None:
    """Persist user-stream-owned state changes without reverting poll-owned fields."""

    def _updater(existing: StoredStrategyState | None) -> StoredStrategyState:
        previous_leader_symbol = (
            existing.previous_leader_symbol
            if existing is not None and existing.previous_leader_symbol is not None
            else state.previous_leader_symbol
        )
        pruned_event_ids = _prune_processed_event_ids(state.processed_event_ids, now)
        return StoredStrategyState(
            current_day=state.current_day,
            previous_leader_symbol=previous_leader_symbol,
            positions=state.positions,
            processed_event_ids=pruned_event_ids,
            order_statuses=state.order_statuses,
            recent_stop_loss_exits=state.recent_stop_loss_exits,
        )

    runtime_state_store.atomic_update(_updater)


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
) -> int:
    now_provider = now_provider or (lambda: datetime.now(timezone.utc))
    reconnect_sleep_fn = reconnect_sleep_fn or (lambda seconds: time.sleep(seconds))
    audit_recorder = (
        AuditRecorder(runtime_db_path=runtime_db_path, source="user-stream", error_logger=logger)
        if runtime_db_path is not None
        else None
    )
    if runtime_state_store is None and runtime_db_path is not None:
        runtime_state_store = RuntimeStateStore(path=runtime_db_path)
    stored_state = runtime_state_store.load() if runtime_state_store is not None else None
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
    processed_event_ids = dict(stored_state.processed_event_ids or {}) if stored_state is not None else {}
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
            except Exception as exc:
                logger(
                    "trade-fill-insert-error "
                    f"symbol={trade_fill.get('symbol')} order_id={trade_fill.get('order_id')} "
                    f"trade_id={trade_fill.get('trade_id')} error={exc}"
                )
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
            except Exception as exc:
                logger(
                    "algo-order-insert-error "
                    f"symbol={algo_order.get('symbol')} algo_id={algo_order.get('algo_id')} error={exc}"
                )
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
        algo_order_status_update = extract_algo_order_status_update(event)
        if algo_order_status_update is not None:
            algo_key, algo_snapshot = algo_order_status_update
            if algo_snapshot is None:
                order_statuses.pop(algo_key, None)
            else:
                order_statuses[algo_key] = algo_snapshot
        state = apply_user_stream_event_to_state(state=state, event=event, order_statuses=order_statuses)
        if event_id is not None:
            processed_event_ids[event_id] = (event.event_time or now_provider()).isoformat()
        if runtime_state_store is not None:
            _save_user_stream_strategy_state(
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=processed_event_ids,
                    order_statuses=order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in state.recent_stop_loss_exits.items()
                    },
                ),
                now=event.event_time or now_provider(),
            )
        _record_position_snapshot(
            audit_recorder=audit_recorder,
            now=event.event_time or now_provider(),
            leader_symbol=state.previous_leader_symbol,
            position_count=len(state.positions),
            order_status_count=len(order_statuses),
            positions=state.positions,
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
        for algo_order in open_algo_orders:
            algo_id = algo_order.get("algoId")
            client_algo_id = algo_order.get("clientAlgoId")
            key_id = client_algo_id or algo_id
            if key_id is None:
                continue
            order_statuses[f"algo:{key_id}"] = {
                "symbol": algo_order.get("symbol"),
                "status": algo_order.get("algoStatus"),
                "side": algo_order.get("side"),
                "client_order_id": client_algo_id,
                "original_order_type": algo_order.get("orderType"),
                "stop_price": algo_order.get("triggerPrice"),
                "event_time": None,
            }
        if runtime_state_store is not None:
            _save_user_stream_strategy_state(
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=state.current_day.isoformat(),
                    previous_leader_symbol=state.previous_leader_symbol,
                    positions=state.positions,
                    processed_event_ids=processed_event_ids,
                    order_statuses=order_statuses,
                    recent_stop_loss_exits={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in state.recent_stop_loss_exits.items()
                    },
                ),
                now=now_provider(),
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
