from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from momentum_alpha.audit import AuditRecorder
from momentum_alpha.runtime_store import (
    insert_account_snapshot,
    insert_broker_order,
    insert_position_snapshot,
    insert_signal_decision,
)


def _serialize_snapshot_position(position) -> dict:
    legs = []
    for leg in getattr(position, "legs", ()) or ():
        legs.append(
            {
                "symbol": leg.symbol,
                "quantity": str(leg.quantity),
                "entry_price": str(leg.entry_price),
                "stop_price": str(leg.stop_price),
                "opened_at": leg.opened_at.isoformat(),
                "leg_type": leg.leg_type,
                "entry_order_id": leg.entry_order_id,
            }
        )
    payload = {
        "symbol": getattr(position, "symbol", None),
        "stop_price": str(getattr(position, "stop_price", None)),
        "legs": legs,
    }
    total_quantity = getattr(position, "total_quantity", None)
    if total_quantity is not None:
        payload["total_quantity"] = str(total_quantity)
    return payload


def _build_snapshot_market_context_payload(
    *,
    leader_symbol: str | None,
    market_payloads: dict[str, dict] | None,
    leader_gap_pct: Decimal | None,
) -> dict:
    return {
        "leader_symbol": leader_symbol,
        "leader_gap_pct": str(leader_gap_pct) if leader_gap_pct is not None else None,
        "candidates": list((market_payloads or {}).values())[:5],
    }


def _record_position_snapshot(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    leader_symbol: str | None,
    position_count: int,
    order_status_count: int,
    symbol_count: int | None = None,
    submit_orders: bool | None = None,
    restore_positions: bool | None = None,
    execute_stop_replacements: bool | None = None,
    positions: dict[str, object] | None = None,
    market_payloads: dict[str, dict] | None = None,
    market_context: dict | None = None,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    try:
        snapshot_payload = dict(payload or {})
        snapshot_positions: dict[str, dict] = {}
        for symbol, position in (positions or {}).items():
            position_payload = _serialize_snapshot_position(position)
            if market_payloads is not None and symbol in market_payloads:
                position_payload.update(market_payloads[symbol])
            snapshot_positions[symbol] = position_payload
        if snapshot_positions:
            snapshot_payload["positions"] = snapshot_positions
        if market_context is not None:
            snapshot_payload["market_context"] = market_context
        insert_position_snapshot(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            leader_symbol=leader_symbol,
            position_count=position_count,
            order_status_count=order_status_count,
            symbol_count=symbol_count,
            submit_orders=submit_orders,
            restore_positions=restore_positions,
            execute_stop_replacements=execute_stop_replacements,
            payload=snapshot_payload,
        )
    except Exception:
        pass


def _record_signal_decision(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    decision_type: str,
    symbol: str | None,
    previous_leader_symbol: str | None,
    next_leader_symbol: str | None,
    position_count: int,
    order_status_count: int,
    broker_response_count: int,
    stop_replacement_count: int,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    try:
        insert_signal_decision(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            decision_type=decision_type,
            symbol=symbol,
            previous_leader_symbol=previous_leader_symbol,
            next_leader_symbol=next_leader_symbol,
            position_count=position_count,
            order_status_count=order_status_count,
            broker_response_count=broker_response_count,
            stop_replacement_count=stop_replacement_count,
            payload=payload or {},
        )
    except Exception:
        pass


def _build_market_context_payloads(
    *,
    snapshots: list[dict],
    exchange_symbols: dict[str, object] | None = None,
) -> tuple[dict[str, dict], Decimal | None]:
    ordered = sorted(
        [
            {
                "symbol": snapshot["symbol"],
                "daily_change_pct": (snapshot["latest_price"] - snapshot["daily_open_price"]) / snapshot["daily_open_price"],
                "latest_price": snapshot["latest_price"],
                "daily_open_price": snapshot["daily_open_price"],
                "previous_hour_low": snapshot["previous_hour_low"],
                "current_hour_low": snapshot.get("current_hour_low", snapshot["previous_hour_low"]),
            }
            for snapshot in snapshots
            if snapshot.get("daily_open_price") not in (None, Decimal("0"))
        ],
        key=lambda item: item["daily_change_pct"],
        reverse=True,
    )
    leader_gap_pct = None
    if len(ordered) >= 2:
        leader_gap_pct = ordered[0]["daily_change_pct"] - ordered[1]["daily_change_pct"]
    payloads: dict[str, dict] = {}
    for item in ordered:
        exchange_symbol = None if exchange_symbols is None else exchange_symbols.get(item["symbol"])
        symbol_filters = getattr(exchange_symbol, "filters", None)
        payloads[item["symbol"]] = {
            "latest_price": str(item["latest_price"]),
            "daily_open_price": str(item["daily_open_price"]),
            "daily_change_pct": str(item["daily_change_pct"]),
            "previous_hour_low": str(item["previous_hour_low"]),
            "current_hour_low": str(item["current_hour_low"]),
            "leader_gap_pct": str(leader_gap_pct) if item["symbol"] == ordered[0]["symbol"] and leader_gap_pct is not None else None,
            "step_size": str(symbol_filters.step_size) if symbol_filters is not None else None,
            "min_qty": str(symbol_filters.min_qty) if symbol_filters is not None else None,
            "tick_size": str(symbol_filters.tick_size) if symbol_filters is not None else None,
        }
    return payloads, leader_gap_pct


def _record_broker_orders(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    responses: list[dict],
    action_type: str,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None:
        return
    for response in responses:
        try:
            quantity = response.get("quantity")
            price = response.get("price") or response.get("stopPrice")
            insert_broker_order(
                path=audit_recorder.runtime_db_path,
                timestamp=now,
                source=audit_recorder.source,
                action_type=action_type,
                symbol=response.get("symbol"),
                order_id=str(response.get("orderId")) if response.get("orderId") is not None else None,
                client_order_id=response.get("clientOrderId"),
                order_status=response.get("status"),
                side=response.get("side"),
                quantity=float(quantity) if quantity not in (None, "") else None,
                price=float(price) if price not in (None, "") else None,
                payload=response,
            )
        except Exception:
            pass


def _record_account_snapshot(
    *,
    audit_recorder: AuditRecorder | None,
    now: datetime,
    leader_symbol: str | None,
    position_count: int,
    open_order_count: int,
    account_info: dict | None,
    payload: dict | None = None,
) -> None:
    if audit_recorder is None or audit_recorder.runtime_db_path is None or account_info is None:
        return
    try:
        insert_account_snapshot(
            path=audit_recorder.runtime_db_path,
            timestamp=now,
            source=audit_recorder.source,
            wallet_balance=account_info.get("totalWalletBalance"),
            available_balance=account_info.get("availableBalance"),
            equity=account_info.get("totalMarginBalance"),
            unrealized_pnl=account_info.get("totalUnrealizedProfit"),
            position_count=position_count,
            open_order_count=open_order_count,
            leader_symbol=leader_symbol,
            payload=payload or account_info,
        )
    except Exception:
        pass


build_snapshot_market_context_payload = _build_snapshot_market_context_payload
build_market_context_payloads = _build_market_context_payloads
record_position_snapshot = _record_position_snapshot
record_signal_decision = _record_signal_decision
record_broker_orders = _record_broker_orders
record_account_snapshot = _record_account_snapshot
