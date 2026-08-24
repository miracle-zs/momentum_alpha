from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.models import Position, StrategyState
from momentum_alpha.reconciliation import merge_position_history
from momentum_alpha.runtime_state_merge import (
    position_has_leg_opened_after,
    position_has_newer_version,
)
from momentum_alpha.runtime_store import (
    MAX_PROCESSED_EVENT_ID_AGE_HOURS,
    RuntimeStateStore,
    insert_account_flow,
    insert_algo_order,
    insert_trade_fill,
)
from momentum_alpha.runtime_reads_events_orders import resolve_order_linkage
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.structured_log import emit_log_line
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


def _parse_state_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def _merge_latest_timestamp_map(
    existing: dict[str, str] | None,
    candidate: dict[str, str] | None,
) -> dict[str, str]:
    merged = dict(existing or {})
    for key, candidate_value in (candidate or {}).items():
        if key not in merged:
            merged[key] = candidate_value
            continue
        existing_timestamp = _parse_state_timestamp(merged[key])
        candidate_timestamp = _parse_state_timestamp(candidate_value)
        if existing_timestamp is None and candidate_timestamp is not None:
            merged[key] = candidate_value
        elif (
            existing_timestamp is not None
            and candidate_timestamp is not None
            and candidate_timestamp >= existing_timestamp
        ):
            merged[key] = candidate_value
    return merged


def _merge_order_statuses(
    existing: dict[str, dict] | None,
    candidate: dict[str, dict] | None,
    removed_keys: set[str] | None = None,
) -> dict[str, dict]:
    """Merge stream snapshots without overwriting newer REST snapshots."""

    merged = dict(existing or {})
    for key in removed_keys or set():
        merged.pop(key, None)
    for key, candidate_snapshot in (candidate or {}).items():
        existing_snapshot = merged.get(key)
        if existing_snapshot is None:
            merged[key] = candidate_snapshot
            continue
        existing_timestamp = _parse_state_timestamp(existing_snapshot.get("event_time"))
        candidate_timestamp = _parse_state_timestamp(candidate_snapshot.get("event_time"))
        if existing_timestamp is None or candidate_timestamp is None or candidate_timestamp >= existing_timestamp:
            merged[key] = candidate_snapshot
    return merged


def _save_user_stream_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
    now: datetime,
    trade_fill: dict[str, Any] | None = None,
    removed_position_symbols: set[str] | None = None,
    removed_positions: dict[str, Position] | None = None,
    removed_order_status_keys: set[str] | None = None,
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
        positions = dict(existing.positions or {}) if existing is not None else {}
        position_removal_timestamps = (
            {}
            if existing is None or existing.position_removal_timestamps is None
            else dict(existing.position_removal_timestamps)
        )
        for symbol, position in (state.positions or {}).items():
            removal_timestamp = position_removal_timestamps.get(symbol)
            if removal_timestamp is not None:
                if not position_has_leg_opened_after(position, removal_timestamp):
                    continue
                position_removal_timestamps.pop(symbol, None)
            positions[symbol] = merge_position_history(positions.get(symbol), position)
        for symbol in removed_position_symbols or set():
            expected_position = (removed_positions or {}).get(symbol)
            current_position = positions.get(symbol)
            if (
                expected_position is not None
                and current_position is not None
                and position_has_newer_version(current_position, expected_position)
            ):
                continue
            positions.pop(symbol, None)
            position_removal_timestamps[symbol] = now.astimezone(timezone.utc).isoformat()
        recent_stop_loss_exits = _merge_latest_timestamp_map(
            existing.recent_stop_loss_exits if existing is not None else {},
            state.recent_stop_loss_exits,
        )
        return StoredStrategyState(
            current_day=existing.current_day if existing is not None else state.current_day,
            previous_leader_symbol=previous_leader_symbol,
            daily_base_signal_times=(
                dict(existing.daily_base_signal_times or {})
                if existing is not None
                else {}
            ),
            daily_base_signal_counts=(
                dict(existing.daily_base_signal_counts or {})
                if existing is not None
                else {}
            ),
            positions=positions,
            processed_event_ids=pruned_event_ids,
            order_statuses=_merge_order_statuses(
                existing.order_statuses if existing is not None else {},
                state.order_statuses,
                removed_order_status_keys,
            ),
            recent_stop_loss_exits=recent_stop_loss_exits,
            position_removal_timestamps=position_removal_timestamps,
            last_add_on_hour=(
                existing.last_add_on_hour
                if existing is not None and existing.last_add_on_hour is not None
                else state.last_add_on_hour
            ),
        )

    if trade_fill is None:
        runtime_state_store.atomic_update(_updater)
    else:
        runtime_state_store.atomic_update_with_trade_fill(_updater, trade_fill=trade_fill)


def build_user_stream_event_handler(
    *,
    logger: Callable[[str], None] | object,
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
    on_trade_fill_persisted_fn: Callable[[], None] | None = None,
    mark_dirty_symbol_fn: Callable[[str, str, datetime], None] | None = None,
    request_runtime_control_fn: Callable[[str, datetime, str], None] | None = None,
    prune_processed_event_ids_fn: Callable[
        [dict[str, str] | None, datetime],
        dict[str, str],
    ] = _prune_processed_event_ids,
) -> Callable[[UserStreamEvent], None]:
    def _on_event(event: UserStreamEvent) -> None:
        event_id = user_stream_event_id_fn(event)
        if event_id is not None and event_id in context.processed_event_ids:
            return
        emit_log_line(logger, f"event={event.event_type} symbol={event.symbol}")
        timestamp = event.event_time or now_provider()
        linkage = None
        if audit_recorder is not None and audit_recorder.runtime_db_path is not None:
            linkage = resolve_order_linkage(
                path=audit_recorder.runtime_db_path,
                client_order_id=event.client_order_id,
                client_algo_id=event.client_algo_id,
                order_id=str(event.order_id) if event.order_id is not None else None,
            )
        decision_id = None if linkage is None else linkage.get("decision_id")
        intent_id = None if linkage is None else linkage.get("intent_id")
        if audit_recorder is not None:
            audit_recorder.record(
                event_type="user_stream_event",
                now=timestamp,
                decision_id=decision_id,
                intent_id=intent_id,
                payload={
                    "decision_id": decision_id,
                    "intent_id": intent_id,
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
                        "clientOrderId": event.client_order_id,
                        "clientAlgoId": event.client_algo_id,
                        "decision_id": decision_id,
                        "intent_id": intent_id,
                    }
                ],
                action_type="stream_order_update",
                decision_id=decision_id,
            )
        trade_fill = extract_trade_fill_fn(event)
        use_atomic_trade_fill = trade_fill is not None and runtime_state_store is not None
        durable_projection_succeeded = True
        if (
            trade_fill is not None
            and audit_recorder is not None
            and audit_recorder.runtime_db_path is not None
            and not use_atomic_trade_fill
        ):
            try:
                insert_trade_fill_fn(
                    path=audit_recorder.runtime_db_path,
                    timestamp=timestamp,
                    source=audit_recorder.source,
                    symbol=trade_fill.get("symbol"),
                    order_id=trade_fill.get("order_id"),
                    trade_id=trade_fill.get("trade_id"),
                    client_order_id=trade_fill.get("client_order_id"),
                    decision_id=decision_id,
                    intent_id=intent_id,
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
                if on_trade_fill_persisted_fn is not None:
                    on_trade_fill_persisted_fn()
            except Exception as exc:
                durable_projection_succeeded = False
                emit_log_line(
                    logger,
                    "trade-fill-insert-error "
                    f"symbol={trade_fill.get('symbol')} order_id={trade_fill.get('order_id')} "
                    f"trade_id={trade_fill.get('trade_id')} error={exc}",
                    level="ERROR",
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
                    decision_id=decision_id,
                    intent_id=intent_id,
                    algo_status=algo_order.get("algo_status"),
                    side=algo_order.get("side"),
                    order_type=algo_order.get("order_type"),
                    trigger_price=algo_order.get("trigger_price"),
                    payload=event.payload,
                )
            except Exception as exc:
                durable_projection_succeeded = False
                emit_log_line(
                    logger,
                    "algo-order-insert-error "
                    f"symbol={algo_order.get('symbol')} algo_id={algo_order.get('algo_id')} error={exc}",
                    level="ERROR",
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
                    durable_projection_succeeded = False
                    emit_log_line(
                        logger,
                        "account-flow-insert-error "
                        f"reason={flow.get('reason')} asset={flow.get('asset')} error={exc}",
                        level="ERROR",
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
        dirty_symbols: set[str] = set()
        if event.event_type in {"ORDER_TRADE_UPDATE", "ALGO_UPDATE"} and event.symbol:
            dirty_symbols.add(event.symbol.upper())
        if event.event_type == "ACCOUNT_UPDATE":
            account_payload = event.payload.get("a")
            if isinstance(account_payload, dict):
                positions = account_payload.get("P")
                if isinstance(positions, list):
                    dirty_symbols.update(
                        str(position.get("s") or "").upper()
                        for position in positions
                        if isinstance(position, dict) and position.get("s")
                    )
        if mark_dirty_symbol_fn is not None:
            for symbol in sorted(dirty_symbols):
                try:
                    mark_dirty_symbol_fn(symbol, event.event_type.lower(), timestamp)
                except Exception as exc:
                    durable_projection_succeeded = False
                    emit_log_line(
                        logger,
                        f"dirty-symbol-persist-error symbol={symbol} event={event.event_type} error={exc}",
                        level="ERROR",
                    )
        if event.event_type == "ACCOUNT_CONFIG_UPDATE" and request_runtime_control_fn is not None:
            try:
                request_runtime_control_fn(
                    "position_mode_refresh",
                    timestamp,
                    "user_stream_account_config_update",
                )
            except Exception as exc:
                durable_projection_succeeded = False
                emit_log_line(
                    logger,
                    f"runtime-control-persist-error key=position_mode_refresh error={exc}",
                    level="ERROR",
                )
        candidate_order_statuses = dict(context.order_statuses)
        removed_order_status_keys: set[str] = set()
        order_status_update = extract_order_status_update_fn(event)
        if order_status_update is not None:
            order_id, order_snapshot = order_status_update
            if order_snapshot is None:
                candidate_order_statuses.pop(order_id, None)
                removed_order_status_keys.add(order_id)
            else:
                if decision_id is not None or intent_id is not None:
                    order_snapshot = {**order_snapshot, "decision_id": decision_id, "intent_id": intent_id}
                candidate_order_statuses[order_id] = order_snapshot
        algo_order_status_update = extract_algo_order_status_update_fn(event)
        if algo_order_status_update is not None:
            algo_key, algo_snapshot = algo_order_status_update
            if algo_snapshot is None:
                candidate_order_statuses.pop(algo_key, None)
                removed_order_status_keys.add(algo_key)
            else:
                if decision_id is not None or intent_id is not None:
                    algo_snapshot = {**algo_snapshot, "decision_id": decision_id, "intent_id": intent_id}
                candidate_order_statuses[algo_key] = algo_snapshot
        candidate_state = apply_user_stream_event_to_state_fn(
            state=context.state,
            event=event,
            order_statuses=candidate_order_statuses,
        )
        candidate_processed_event_ids = dict(context.processed_event_ids)
        if event_id is not None and durable_projection_succeeded:
            candidate_processed_event_ids[event_id] = timestamp.isoformat()
        removed_position_symbols = set(context.state.positions) - set(candidate_state.positions)
        if runtime_state_store is not None:
            save_user_stream_strategy_state_fn(
                runtime_state_store=runtime_state_store,
                state=StoredStrategyState(
                    current_day=candidate_state.current_day.isoformat(),
                    previous_leader_symbol=candidate_state.previous_leader_symbol,
                    daily_base_signal_times={
                        symbol: timestamp.isoformat()
                        for symbol, timestamp in candidate_state.daily_base_signal_times.items()
                    },
                    daily_base_signal_counts=dict(candidate_state.daily_base_signal_counts),
                    positions=candidate_state.positions,
                    processed_event_ids=candidate_processed_event_ids,
                    order_statuses=candidate_order_statuses,
                    recent_stop_loss_exits={
                        symbol: exit_time.isoformat()
                        for symbol, exit_time in candidate_state.recent_stop_loss_exits.items()
                    },
                ),
                now=timestamp,
                removed_position_symbols=removed_position_symbols,
                removed_positions={
                    symbol: context.state.positions[symbol]
                    for symbol in removed_position_symbols
                    if symbol in context.state.positions
                },
                removed_order_status_keys=removed_order_status_keys,
                trade_fill=(
                    None
                    if not use_atomic_trade_fill
                    else {
                        "timestamp": timestamp,
                        "source": None if audit_recorder is None else audit_recorder.source,
                        "symbol": trade_fill.get("symbol"),
                        "order_id": trade_fill.get("order_id"),
                        "trade_id": trade_fill.get("trade_id"),
                        "client_order_id": trade_fill.get("client_order_id"),
                        "decision_id": decision_id,
                        "intent_id": intent_id,
                        "order_status": trade_fill.get("order_status"),
                        "execution_type": trade_fill.get("execution_type"),
                        "side": trade_fill.get("side"),
                        "order_type": trade_fill.get("order_type"),
                        "quantity": trade_fill.get("quantity"),
                        "cumulative_quantity": trade_fill.get("cumulative_quantity"),
                        "average_price": trade_fill.get("average_price"),
                        "last_price": trade_fill.get("last_price"),
                        "realized_pnl": trade_fill.get("realized_pnl"),
                        "commission": trade_fill.get("commission"),
                        "commission_asset": trade_fill.get("commission_asset"),
                        "payload": event.payload,
                    }
                ),
                prune_processed_event_ids_fn=prune_processed_event_ids_fn,
            )
            if use_atomic_trade_fill and on_trade_fill_persisted_fn is not None:
                on_trade_fill_persisted_fn()
        context.state = candidate_state
        context.order_statuses = candidate_order_statuses
        context.processed_event_ids = candidate_processed_event_ids
        record_position_snapshot_fn(
            audit_recorder=audit_recorder,
            now=timestamp,
            leader_symbol=None,
            decision_id=decision_id,
            intent_id=intent_id,
            position_count=len(context.state.positions),
            order_status_count=len(context.order_statuses),
            positions=context.state.positions,
            payload={"event_type": event.event_type, "symbol": event.symbol, "decision_id": decision_id, "intent_id": intent_id},
        )

    return _on_event
