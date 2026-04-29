from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from .user_stream_event_model import UserStreamEvent


def _parse_decimal(value):
    try:
        if value in (None, ""):
            return None
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


def _first_present(*values):
    for value in values:
        if value not in (None, ""):
            return value
    return None


def parse_user_stream_event(payload: dict) -> UserStreamEvent:
    event_type = payload.get("e", "UNKNOWN")
    order_payload = payload.get("o", {})
    if not isinstance(order_payload, dict):
        order_payload = {}
    symbol = order_payload.get("s") or payload.get("s")
    event_time_ms = payload.get("T") or payload.get("E") or payload.get("t")
    algo_status = _first_present(payload.get("algoStatus"), order_payload.get("algoStatus"), order_payload.get("X"))

    return UserStreamEvent(
        event_type=event_type,
        payload=payload,
        symbol=symbol,
        order_status=_first_present(order_payload.get("X"), payload.get("X"), algo_status),
        execution_type=order_payload.get("x"),
        side=order_payload.get("S") or payload.get("S"),
        average_price=_parse_decimal(order_payload.get("ap")),
        filled_quantity=_parse_decimal(order_payload.get("z")),
        last_filled_price=_parse_decimal(order_payload.get("L")),
        last_filled_quantity=_parse_decimal(order_payload.get("l")),
        realized_pnl=_parse_decimal(order_payload.get("rp")),
        commission=_parse_decimal(order_payload.get("n")),
        commission_asset=order_payload.get("N"),
        stop_price=_parse_decimal(order_payload.get("sp")),
        original_order_type=_first_present(order_payload.get("ot"), payload.get("orderType"), order_payload.get("o")),
        event_time=datetime.fromtimestamp(int(event_time_ms) / 1000, tz=timezone.utc) if event_time_ms is not None else None,
        order_id=_first_present(order_payload.get("i"), order_payload.get("ai")),
        trade_id=order_payload.get("t"),
        client_order_id=order_payload.get("c"),
        account_update_reason=(payload.get("a") or {}).get("m"),
        # Algo order fields
        algo_id=_first_present(payload.get("algoId"), order_payload.get("algoId"), order_payload.get("aid")),
        client_algo_id=_first_present(
            payload.get("clientAlgoId"),
            order_payload.get("clientAlgoId"),
            order_payload.get("caid"),
        ),
        algo_status=algo_status,
        trigger_price=_parse_decimal(
            _first_present(payload.get("triggerPrice"), order_payload.get("triggerPrice"), order_payload.get("tp"))
        ),
    )
