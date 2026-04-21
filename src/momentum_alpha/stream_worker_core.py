from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta
from typing import Any

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import StrategyState
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
    UserStreamEvent,
    apply_user_stream_event_to_state,
    extract_account_flows,
    extract_algo_order_event,
    extract_algo_order_status_update,
    extract_order_status_update,
    extract_trade_fill,
    user_stream_event_id,
)


@dataclass
class UserStreamWorkerContext:
    state: StrategyState
    processed_event_ids: dict[str, str]
    order_statuses: dict[str, dict[str, Any]]


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
    prune_processed_event_ids_fn: Callable[
        [dict[str, str] | None, datetime],
        dict[str, str],
    ] = _prune_processed_event_ids,
) -> None:
    """Persist user-stream-owned state changes without reverting poll-owned fields."""

    def _updater(existing: StoredStrategyState | None) -> StoredStrategyState:
        previous_leader_symbol = (
            existing.previous_leader_symbol
            if existing is not None and existing.previous_leader_symbol is not None
            else state.previous_leader_symbol
        )
        pruned_event_ids = prune_processed_event_ids_fn(state.processed_event_ids, now)
        return StoredStrategyState(
            current_day=state.current_day,
            previous_leader_symbol=previous_leader_symbol,
            positions=state.positions,
            processed_event_ids=pruned_event_ids,
            order_statuses=state.order_statuses,
            recent_stop_loss_exits=state.recent_stop_loss_exits,
        )

    runtime_state_store.atomic_update(_updater)


def build_user_stream_event_handler(
    *,
    logger: Callable[[str], None],
    runtime_state_store: RuntimeStateStore | None,
    audit_recorder: AuditRecorder | None,
    now_provider: Callable[[], datetime],
    context: UserStreamWorkerContext,
    extract_trade_fill_fn: Callable[[UserStreamEvent], dict[str, Any] | None] = extract_trade_fill,
    extract_algo_order_event_fn: Callable[[UserStreamEvent], dict[str, Any] | None] = extract_algo_order_event,
    extract_account_flows_fn: Callable[[UserStreamEvent], list[dict[str, Any]]] = extract_account_flows,
    extract_order_status_update_fn: Callable[[UserStreamEvent], tuple[str, dict[str, Any] | None] | None] = extract_order_status_update,
    extract_algo_order_status_update_fn: Callable[[UserStreamEvent], tuple[str, dict[str, Any] | None] | None] = extract_algo_order_status_update,
    user_stream_event_id_fn: Callable[[UserStreamEvent], str | None] = user_stream_event_id,
    apply_user_stream_event_to_state_fn: Callable[..., StrategyState] = apply_user_stream_event_to_state,
    insert_trade_fill_fn: Callable[..., None] = insert_trade_fill,
    insert_algo_order_fn: Callable[..., None] = insert_algo_order,
    insert_account_flow_fn: Callable[..., None] = insert_account_flow,
    record_broker_orders_fn: Callable[..., None] = _record_broker_orders,
    record_position_snapshot_fn: Callable[..., None] = _record_position_snapshot,
    save_user_stream_strategy_state_fn: Callable[..., None] = _save_user_stream_strategy_state,
    prune_processed_event_ids_fn: Callable[
        [dict[str, str] | None, datetime],
        dict[str, str],
    ] = _prune_processed_event_ids,
) -> Callable[[UserStreamEvent], None]:
    def _on_event(event: UserStreamEvent) -> None:
        logger(f"event={event.event_type} symbol={event.symbol}")
        timestamp = event.event_time or now_provider()
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="user_stream_event",
                now=timestamp,
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
            record_broker_orders_fn(
                audit_recorder=audit_recorder,
                now=timestamp,
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
        event_id = user_stream_event_id_fn(event)
        if event_id is not None and event_id in context.processed_event_ids:
            return
        trade_fill = extract_trade_fill_fn(event)
        if trade_fill is not None and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            try:
                insert_trade_fill_fn(
                    path=audit_recorder.runtime_db_path,
                    timestamp=timestamp,
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
        algo_order = extract_algo_order_event_fn(event)
        if algo_order is not None and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            try:
                insert_algo_order_fn(
                    path=audit_recorder.runtime_db_path,
                    timestamp=timestamp,
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
        account_flows = extract_account_flows_fn(event)
        if account_flows and audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            for flow in account_flows:
                try:
                    insert_account_flow_fn(
                        path=audit_recorder.runtime_db_path,
                        timestamp=timestamp,
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
                            now=timestamp,
                            payload={
                                "reason": flow.get("reason"),
                                "asset": flow.get("asset"),
                                "balance_change": str(flow.get("balance_change")),
                                "error": str(exc),
                            },
                        )
        order_status_update = extract_order_status_update_fn(event)
        if order_status_update is not None:
            order_id, order_snapshot = order_status_update
            if order_snapshot is None:
                context.order_statuses.pop(order_id, None)
            else:
                context.order_statuses[order_id] = order_snapshot
        algo_order_status_update = extract_algo_order_status_update_fn(event)
        if algo_order_status_update is not None:
            algo_key, algo_snapshot = algo_order_status_update
            if algo_snapshot is None:
                context.order_statuses.pop(algo_key, None)
            else:
                context.order_statuses[algo_key] = algo_snapshot
        context.state = apply_user_stream_event_to_state_fn(
            state=context.state,
            event=event,
            order_statuses=context.order_statuses,
        )
        if event_id is not None:
            context.processed_event_ids[event_id] = timestamp.isoformat()
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
                        symbol: exit_time.isoformat()
                        for symbol, exit_time in context.state.recent_stop_loss_exits.items()
                    },
                ),
                now=timestamp,
                prune_processed_event_ids_fn=prune_processed_event_ids_fn,
            )
        record_position_snapshot_fn(
            audit_recorder=audit_recorder,
            now=timestamp,
            leader_symbol=context.state.previous_leader_symbol,
            position_count=len(context.state.positions),
            order_status_count=len(context.order_statuses),
            positions=context.state.positions,
            payload={"event_type": event.event_type, "symbol": event.symbol},
        )

    return _on_event
