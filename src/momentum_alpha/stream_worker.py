from __future__ import annotations

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

from .stream_worker_core import _prune_processed_event_ids as _core_prune_processed_event_ids
from .stream_worker_core import _save_user_stream_strategy_state as _core_save_user_stream_strategy_state
from .stream_worker_loop import run_user_stream as _run_user_stream_impl


_prune_processed_event_ids = _core_prune_processed_event_ids


def _save_user_stream_strategy_state(
    *,
    runtime_state_store: RuntimeStateStore,
    state: StoredStrategyState,
    now,
    prune_processed_event_ids_fn=None,
) -> None:
    _core_save_user_stream_strategy_state(
        runtime_state_store=runtime_state_store,
        state=state,
        now=now,
        prune_processed_event_ids_fn=(
            _prune_processed_event_ids if prune_processed_event_ids_fn is None else prune_processed_event_ids_fn
        ),
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
    runtime_db_path=None,
) -> int:
    return _run_user_stream_impl(
        client=client,
        testnet=testnet,
        logger=logger,
        runtime_state_store=runtime_state_store,
        now_provider=now_provider,
        stream_client_factory=stream_client_factory,
        reconnect_sleep_fn=reconnect_sleep_fn,
        runtime_db_path=runtime_db_path,
        extract_trade_fill_fn=extract_trade_fill,
        extract_algo_order_event_fn=extract_algo_order_event,
        extract_account_flows_fn=extract_account_flows,
        extract_order_status_update_fn=extract_order_status_update,
        extract_algo_order_status_update_fn=extract_algo_order_status_update,
        user_stream_event_id_fn=user_stream_event_id,
        apply_user_stream_event_to_state_fn=apply_user_stream_event_to_state,
        insert_trade_fill_fn=insert_trade_fill,
        insert_algo_order_fn=insert_algo_order,
        insert_account_flow_fn=insert_account_flow,
        record_broker_orders_fn=_record_broker_orders,
        record_position_snapshot_fn=_record_position_snapshot,
        save_user_stream_strategy_state_fn=_save_user_stream_strategy_state,
        prune_processed_event_ids_fn=_prune_processed_event_ids,
    )
