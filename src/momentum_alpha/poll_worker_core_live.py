from __future__ import annotations

from dataclasses import replace
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.broker import BinanceBroker
from momentum_alpha.config import StrategyConfig
from momentum_alpha.market_data import LiveMarketDataCache, _build_live_snapshots, _resolve_symbols
from momentum_alpha.models import Position, StrategyState
from momentum_alpha.orders import is_strategy_client_order_id
from momentum_alpha.reconciliation import (
    build_stop_coverage_reconciliation_plan,
    build_missing_stop_reconciliation_plan,
    build_stale_stop_reconciliation_plan,
    build_stop_reconciliation_plan,
    merge_position_history,
    restore_state,
)
from momentum_alpha.runtime_store import RuntimeStateStore
from momentum_alpha.strategy_state_codec import StoredStrategyState
from momentum_alpha.structured_log import emit_structured_log
from momentum_alpha.telemetry import (
    _build_market_context_payloads,
    _build_snapshot_market_context_payload,
    _record_account_snapshot,
    _record_broker_orders,
    _record_position_snapshot,
    _record_signal_decision,
)
from momentum_alpha.trace_ids import build_decision_id, build_intent_id_from_client_order_id, build_order_intent_id

from .poll_worker_core_execution import RunOnceResult, build_runtime_from_snapshots, run_once
from .poll_worker_core_state import _save_strategy_state


def _has_strategy_stop_evidence(
    *,
    symbol: str,
    position: Position,
    order_statuses: dict[str, dict] | None,
) -> bool:
    if position.stop_price > Decimal("0"):
        return True
    active_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING"}
    for snapshot in (order_statuses or {}).values():
        if snapshot is None or snapshot.get("symbol") != symbol:
            continue
        if snapshot.get("status") not in active_statuses:
            continue
        order_type = snapshot.get("original_order_type") or snapshot.get("type") or snapshot.get("orderType")
        client_order_id = (
            snapshot.get("client_order_id")
            or snapshot.get("clientOrderId")
            or snapshot.get("clientAlgoId")
        )
        if order_type == "STOP_MARKET" and is_strategy_client_order_id(client_order_id) and str(client_order_id).endswith("s"):
            return True
    return False


def _apply_restored_stop_loss_cooldowns(
    *,
    restored_state: StrategyState,
    stored_state: StoredStrategyState | None,
    now: datetime,
) -> StrategyState:
    if stored_state is None or not stored_state.positions:
        return restored_state

    recent_stop_loss_exits = dict(restored_state.recent_stop_loss_exits)
    current_symbols = set(restored_state.positions)
    for symbol, previous_position in stored_state.positions.items():
        if symbol in current_symbols or symbol in recent_stop_loss_exits:
            continue
        if _has_strategy_stop_evidence(
            symbol=symbol,
            position=previous_position,
            order_statuses=stored_state.order_statuses,
        ):
            recent_stop_loss_exits[symbol] = now

    if recent_stop_loss_exits == restored_state.recent_stop_loss_exits:
        return restored_state
    return replace(restored_state, recent_stop_loss_exits=recent_stop_loss_exits)


def _prefer_position_history(existing: Position | None, candidate: Position) -> Position:
    """Keep richer leg history when restored data would collapse a position."""
    return merge_position_history(existing, candidate)


def _is_add_on_client_order_id(client_order_id: str | None) -> bool:
    intent_id = build_intent_id_from_client_order_id(client_order_id)
    return bool(intent_id and intent_id.rsplit("_", 1)[-1].startswith("a"))


def _release_rejected_base_entries(*, result: RunOnceResult, submit_orders: bool) -> RunOnceResult:
    """Allow a later leader rotation after a locally skipped or rejected base order."""

    if not submit_orders:
        return result
    base_symbols = {intent.symbol for intent in result.runtime_result.decision.base_entries}
    if not base_symbols:
        return result

    planned_base_symbols = {
        order.get("symbol")
        for order in result.execution_plan.entry_orders
        if not _is_add_on_client_order_id(order.get("newClientOrderId"))
    }
    released_symbols = base_symbols - planned_base_symbols
    for failure in result.entry_order_failures:
        client_order_id = failure.get("clientOrderId") or failure.get("client_order_id")
        symbol = failure.get("symbol")
        if (
            symbol in base_symbols
            and not _is_add_on_client_order_id(client_order_id)
            and failure.get("retryable") is False
        ):
            released_symbols.add(symbol)
    if not released_symbols:
        return result

    next_state = result.runtime_result.next_state
    daily_signal_times = dict(next_state.daily_base_signal_times)
    daily_signal_counts = dict(next_state.daily_base_signal_counts)
    for symbol in released_symbols:
        daily_signal_times.pop(symbol, None)
        daily_signal_counts.pop(symbol, None)
    return replace(
        result,
        runtime_result=replace(
            result.runtime_result,
            next_state=replace(
                next_state,
                daily_base_signal_times=daily_signal_times,
                daily_base_signal_counts=daily_signal_counts,
            ),
        ),
    )


def _repair_failed_stop_coverage(
    *,
    client,
    broker: BinanceBroker,
    failed_stop_orders: list[dict],
    runtime_market: dict,
    current_day: datetime,
    previous_leader_symbol: str | None,
    position_side: str | None,
) -> tuple[list[tuple[str, Decimal]], list[dict], list[dict]]:
    failed_symbols = {failure.get("symbol") for failure in failed_stop_orders if failure.get("symbol")}
    if not failed_symbols:
        return [], [], []
    fetch_position_risk = getattr(client, "fetch_position_risk", None)
    fetch_open_orders = getattr(client, "fetch_open_orders", None)
    if not callable(fetch_position_risk) or not callable(fetch_open_orders):
        return [], [], []

    open_orders = list(fetch_open_orders())
    fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
    if callable(fetch_open_algo_orders):
        open_orders.extend(fetch_open_algo_orders())
    recovered_state = restore_state(
        current_day=current_day.date().isoformat(),
        previous_leader_symbol=previous_leader_symbol,
        position_risk=fetch_position_risk(),
        open_orders=open_orders,
    )
    replacements = [
        replacement
        for replacement in build_stop_coverage_reconciliation_plan(
            state=recovered_state,
            market=runtime_market,
            open_orders=open_orders,
        )
        if replacement[0] in failed_symbols
    ]
    if not replacements:
        return [], [], []
    responses = broker.replace_stop_orders(
        replacements=[
            (symbol, str(recovered_state.positions[symbol].total_quantity), str(stop_price))
            if position_side is None
            else (symbol, str(recovered_state.positions[symbol].total_quantity), str(stop_price), position_side)
            for symbol, stop_price in replacements
        ]
    )
    return replacements, responses, list(getattr(broker, "last_stop_replacement_failures", []) or [])


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
    runtime_state_store: RuntimeStateStore | None = None,
    market_data_cache: LiveMarketDataCache | None = None,
    audit_recorder: AuditRecorder | None = None,
    last_add_on_hour: int | None = None,
    logger: object | None = None,
) -> RunOnceResult:
    stored_state = runtime_state_store.load() if runtime_state_store is not None else None
    current_day = now.astimezone(timezone.utc).date()
    stored_daily_base_signal_times = {}
    stored_daily_base_signal_counts = {}
    if stored_state is not None and stored_state.current_day == current_day.isoformat():
        stored_daily_base_signal_times = {
            symbol: datetime.fromisoformat(timestamp)
            for symbol, timestamp in (stored_state.daily_base_signal_times or {}).items()
        }
        stored_daily_base_signal_counts = dict(stored_state.daily_base_signal_counts or {})

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
    if previous_leader_symbol is None and stored_state is not None:
        previous_leader_symbol = stored_state.previous_leader_symbol

    initial_state = StrategyState(
        current_day=current_day,
        previous_leader_symbol=previous_leader_symbol,
        daily_base_signal_times=stored_daily_base_signal_times,
        daily_base_signal_counts=stored_daily_base_signal_counts,
    )
    removed_positions: dict[str, Position] = {}
    restored_open_orders: list[dict] = []
    if restore_positions:
        open_orders = client.fetch_open_orders()
        fetch_open_algo_orders = getattr(client, "fetch_open_algo_orders", None)
        if callable(fetch_open_algo_orders):
            open_orders = [*open_orders, *fetch_open_algo_orders()]
        restored_open_orders = open_orders
        initial_state = restore_state(
            current_day=f"{now.year:04d}-{now.month:02d}-{now.day:02d}",
            previous_leader_symbol=previous_leader_symbol,
            position_risk=client.fetch_position_risk(),
            open_orders=open_orders,
        )
        initial_state = replace(
            initial_state,
            daily_base_signal_times=stored_daily_base_signal_times,
            daily_base_signal_counts=stored_daily_base_signal_counts,
        )
        if stored_state is not None:
            removed_positions = {
                symbol: position
                for symbol, position in (stored_state.positions or {}).items()
                if symbol not in initial_state.positions
            }
            merged_restored_positions = {
                symbol: _prefer_position_history(stored_state.positions.get(symbol), candidate)
                for symbol, candidate in initial_state.positions.items()
            }
            initial_state = replace(
                initial_state,
                positions=merged_restored_positions,
                recent_stop_loss_exits={
                    symbol: datetime.fromisoformat(timestamp)
                    for symbol, timestamp in (stored_state.recent_stop_loss_exits or {}).items()
                },
            )
            initial_state = _apply_restored_stop_loss_cooldowns(
                restored_state=initial_state,
                stored_state=stored_state,
                now=now,
            )

    resolved_symbols = (
        market_data_cache.resolve_symbols(symbols=symbols, client=client)
        if market_data_cache is not None
        else _resolve_symbols(symbols=symbols, client=client)
    )
    held_symbols = set(initial_state.positions)
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
    stop_replacement_failures: list[dict] = []
    runtime_market = build_runtime_from_snapshots(snapshots=snapshots).market
    if restore_positions and initial_state is not None:
        stop_replacements = build_stop_reconciliation_plan(
            state=initial_state,
            decision=result.runtime_result.decision,
        )
        missing_stop_replacements = build_missing_stop_reconciliation_plan(
            state=initial_state,
            market=runtime_market,
        )
        stale_stop_replacements = build_stale_stop_reconciliation_plan(
            state=initial_state,
            market=runtime_market,
        )
        uncovered_stop_replacements = build_stop_coverage_reconciliation_plan(
            state=initial_state,
            market=runtime_market,
            open_orders=restored_open_orders,
        )
        merged_replacements = {symbol: stop_price for symbol, stop_price in stop_replacements}
        for symbol, stop_price in stale_stop_replacements:
            merged_replacements.setdefault(symbol, stop_price)
        for symbol, stop_price in missing_stop_replacements:
            merged_replacements.setdefault(symbol, stop_price)
        for symbol, stop_price in uncovered_stop_replacements:
            merged_replacements[symbol] = stop_price
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
                stop_replacement_failures = list(getattr(broker, "last_stop_replacement_failures", []) or [])
            except Exception as exc:
                if logger is not None:
                    emit_structured_log(
                        logger,
                        service="poll",
                        event="stop-replacement-failed",
                        level="ERROR",
                        error=str(exc),
                    )
                else:
                    print(f"stop replacement failed: {exc}")
    broker_responses: list[dict] = []
    entry_order_failures: list[dict] = []
    stop_order_failures: list[dict] = []
    if submit_orders:
        broker_responses = broker.submit_execution_plan(result.execution_plan)
        entry_order_failures = list(getattr(broker, "last_entry_order_failures", []) or [])
        stop_order_failures = list(getattr(broker, "last_stop_order_failures", []) or [])
        result = replace(
            result,
            broker_responses=broker_responses,
            entry_order_failures=entry_order_failures,
            stop_order_failures=stop_order_failures,
        )
        result = _release_rejected_base_entries(result=result, submit_orders=submit_orders)
        if stop_order_failures:
            try:
                repaired_replacements, repaired_responses, repaired_failures = _repair_failed_stop_coverage(
                    client=client,
                    broker=broker,
                    failed_stop_orders=stop_order_failures,
                    runtime_market=runtime_market,
                    current_day=now,
                    previous_leader_symbol=previous_leader_symbol,
                    position_side=position_side,
                )
                stop_replacements = sorted({*stop_replacements, *repaired_replacements})
                stop_replacement_responses.extend(repaired_responses)
                stop_replacement_failures.extend(repaired_failures)
            except Exception as exc:
                if logger is not None:
                    emit_structured_log(
                        logger,
                        service="poll",
                        event="failed-stop-coverage-repair-failed",
                        level="ERROR",
                        error=str(exc),
                    )
    if runtime_state_store is not None:
        stored_state = runtime_state_store.load()
        merged_positions = {}
        for symbol, candidate_position in result.runtime_result.next_state.positions.items():
            merged_positions[symbol] = _prefer_position_history(
                None if stored_state is None or not stored_state.positions else stored_state.positions.get(symbol),
                candidate_position,
            )
        merged_next_state = replace(result.runtime_result.next_state, positions=merged_positions)
        result = replace(result, runtime_result=replace(result.runtime_result, next_state=merged_next_state))
        merged_state = StoredStrategyState(
            current_day=result.runtime_result.next_state.current_day.isoformat(),
            previous_leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            daily_base_signal_times={
                symbol: timestamp.isoformat()
                for symbol, timestamp in result.runtime_result.next_state.daily_base_signal_times.items()
            },
            daily_base_signal_counts=dict(result.runtime_result.next_state.daily_base_signal_counts),
            positions=result.runtime_result.next_state.positions,
            recent_stop_loss_exits={
                symbol: timestamp.isoformat()
                for symbol, timestamp in result.runtime_result.next_state.recent_stop_loss_exits.items()
            },
            processed_event_ids=stored_state.processed_event_ids if stored_state is not None else {},
            order_statuses=stored_state.order_statuses if stored_state is not None else {},
        )
        _save_strategy_state(
            runtime_state_store=runtime_state_store,
            state=merged_state,
            removed_positions=removed_positions,
        )
    if audit_recorder is not None:
        skipped_base_symbols = [
            item.symbol
            for item in result.runtime_result.decision.skipped_base_entries
        ]
        fetch_account_info = getattr(client, "fetch_account_info", None)
        account_info = fetch_account_info() if callable(fetch_account_info) else None
        market_payloads, leader_gap_pct = _build_market_context_payloads(
            snapshots=snapshots,
            exchange_symbols=(
                market_data_cache.exchange_symbol_map(client=client) if market_data_cache is not None else None
            ),
        )
        decision_id = build_decision_id(now=now)
        audit_recorder.record(
            event_type="tick_result",
            now=now,
            decision_id=decision_id,
            payload={
                "decision_id": decision_id,
                "symbol_count": len(snapshots),
                "base_entry_symbols": [intent.symbol for intent in result.runtime_result.decision.base_entries],
                "skipped_base_symbols": skipped_base_symbols,
                "add_on_symbols": [intent.symbol for intent in result.runtime_result.decision.add_on_entries],
                "updated_stop_symbols": sorted(result.runtime_result.decision.updated_stop_prices),
                "previous_leader_symbol": previous_leader_symbol,
                "next_previous_leader_symbol": result.runtime_result.next_state.previous_leader_symbol,
                "broker_response_count": len(result.broker_responses),
                "entry_order_failure_count": len(entry_order_failures),
                "stop_order_failure_count": len(stop_order_failures),
                "stop_replacement_count": len(stop_replacements),
                "stop_replacement_failure_count": len(stop_replacement_failures),
            },
        )
        position_count = len(result.runtime_result.next_state.positions)
        order_status_count = 0
        signal_records: list[tuple[str, str | None, str | None, dict]] = []
        stop_budget_usdt = StrategyConfig().stop_budget_usdt
        for sequence, intent in enumerate([*result.runtime_result.decision.base_entries, *result.runtime_result.decision.add_on_entries]):
            signal_records.append(
                (
                    "base_entry" if intent.leg_type == "base" else "add_on",
                    intent.symbol,
                    build_order_intent_id(symbol=intent.symbol, opened_at=now, leg_type=intent.leg_type, sequence=sequence),
                    {
                        "leg_type": intent.leg_type,
                        "stop_price": str(intent.stop_price),
                        **{key: value for key, value in market_payloads.get(intent.symbol, {}).items() if value is not None},
                    },
                )
            )
        signal_records.extend(
            (
                "base_entry_skipped",
                skipped.symbol,
                skipped.shadow_opportunity_id,
                {
                    "leg_type": "base",
                    "blocked_reason": skipped.reason,
                    "base_signal_sequence": skipped.base_signal_sequence,
                    "first_base_signal_at": skipped.first_base_signal_at.isoformat(),
                    "shadow_opportunity_id": skipped.shadow_opportunity_id,
                    "stop_price": str(skipped.stop_price),
                    "stop_budget_usdt": str(stop_budget_usdt),
                    **{
                        key: value
                        for key, value in market_payloads.get(skipped.symbol, {}).items()
                        if value is not None
                    },
                },
            )
            for skipped in result.runtime_result.decision.skipped_base_entries
        )
        signal_records.extend(
            (
                "add_on_skipped",
                skipped.symbol,
                None,
                {
                    "leg_type": "add_on",
                    "blocked_reason": skipped.reason,
                    "stop_price": str(skipped.stop_price),
                    "would_add_on_under_previous_strategy": True,
                    **(
                        {"base_opened_at": skipped.base_opened_at.isoformat()}
                        if skipped.base_opened_at is not None
                        else {}
                    ),
                    **(
                        {"base_age_minutes": str(skipped.base_age_minutes)}
                        if skipped.base_age_minutes is not None
                        else {}
                    ),
                    **{key: value for key, value in market_payloads.get(skipped.symbol, {}).items() if value is not None},
                },
            )
            for skipped in result.runtime_result.decision.skipped_add_ons
        )
        signal_records.extend(
            (
                "stop_update",
                symbol,
                None,
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
                    None,
                    (
                        {"blocked_reason": result.runtime_result.decision.blocked_reason}
                        if result.runtime_result.decision.blocked_reason is not None
                        else {}
                    ),
                )
            )
        for decision_type, symbol, intent_id, payload in signal_records:
            _record_signal_decision(
                audit_recorder=audit_recorder,
                now=now,
                decision_id=decision_id,
                intent_id=intent_id,
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
        market_context = _build_snapshot_market_context_payload(
            leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            market_payloads=market_payloads,
            leader_gap_pct=leader_gap_pct,
        )
        _record_position_snapshot(
            audit_recorder=audit_recorder,
            now=now,
            leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            decision_id=decision_id,
            position_count=position_count,
            order_status_count=order_status_count,
            symbol_count=len(snapshots),
            submit_orders=submit_orders,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
            positions=result.runtime_result.next_state.positions,
            market_payloads=market_payloads,
            market_context=market_context,
            payload={
                "decision_id": decision_id,
                "base_entry_symbols": [intent.symbol for intent in result.runtime_result.decision.base_entries],
                "skipped_base_symbols": skipped_base_symbols,
                "add_on_symbols": [intent.symbol for intent in result.runtime_result.decision.add_on_entries],
                "updated_stop_symbols": sorted(result.runtime_result.decision.updated_stop_prices),
            },
        )
        _record_account_snapshot(
            audit_recorder=audit_recorder,
            now=now,
            leader_symbol=result.runtime_result.next_state.previous_leader_symbol,
            decision_id=decision_id,
            position_count=position_count,
            open_order_count=order_status_count,
            account_info=account_info,
            payload={
                "decision_id": decision_id,
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
                decision_id=decision_id,
                payload={"responses": result.broker_responses, "decision_id": decision_id},
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=now,
                responses=result.broker_responses,
                action_type="submit_order",
                decision_id=decision_id,
            )
        order_submit_failures = [*entry_order_failures, *stop_order_failures]
        if order_submit_failures:
            audit_recorder.record(
                event_type="broker_submit_failures",
                now=now,
                decision_id=decision_id,
                payload={"failures": order_submit_failures, "decision_id": decision_id},
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=now,
                responses=order_submit_failures,
                action_type="submit_order_failed",
                decision_id=decision_id,
            )
        if stop_replacement_responses:
            audit_recorder.record(
                event_type="broker_replace",
                now=now,
                decision_id=decision_id,
                payload={"responses": stop_replacement_responses, "decision_id": decision_id},
            )
            _record_broker_orders(
                audit_recorder=audit_recorder,
                now=now,
                responses=stop_replacement_responses,
                action_type="replace_stop_order",
                decision_id=decision_id,
            )
        if stop_replacements:
            audit_recorder.record(
                event_type="stop_replacements",
                now=now,
                decision_id=decision_id,
                payload={
                    "replacements": [(symbol, str(stop_price)) for symbol, stop_price in stop_replacements],
                    "decision_id": decision_id,
                },
            )
        if stop_replacement_failures:
            audit_recorder.record(
                event_type="stop_replacement_failures",
                now=now,
                decision_id=decision_id,
                payload={"failures": stop_replacement_failures, "decision_id": decision_id},
            )
    return RunOnceResult(
        runtime_result=result.runtime_result,
        broker_responses=result.broker_responses,
        stop_replacements=stop_replacements,
        entry_order_failures=entry_order_failures,
        stop_order_failures=stop_order_failures,
    )
