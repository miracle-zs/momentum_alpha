from __future__ import annotations

from decimal import Decimal, InvalidOperation

from momentum_alpha.orders import is_strategy_client_order_id

from .user_stream_event_model import UserStreamEvent


def extract_flat_position_symbols(event: UserStreamEvent) -> tuple[str, ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    flat_symbols: list[str] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount == Decimal("0"):
            flat_symbols.append(symbol)
    return tuple(flat_symbols)


def extract_positive_account_positions(event: UserStreamEvent) -> tuple[tuple[str, Decimal, Decimal], ...]:
    if event.event_type != "ACCOUNT_UPDATE":
        return ()
    account_payload = event.payload.get("a", {})
    positive_positions: list[tuple[str, Decimal, Decimal]] = []
    for position_payload in account_payload.get("P", []):
        symbol = position_payload.get("s")
        if symbol in (None, ""):
            continue
        try:
            position_amount = Decimal(str(position_payload.get("pa", "")))
            entry_price = Decimal(str(position_payload.get("ep", "")))
        except (InvalidOperation, TypeError):
            continue
        if position_amount > Decimal("0"):
            positive_positions.append((symbol, position_amount, entry_price))
    return tuple(positive_positions)


def resolve_stop_price_from_order_statuses(*, symbol: str, order_statuses: dict[str, dict] | None) -> Decimal | None:
    if not order_statuses:
        return None
    # Active statuses include both regular order statuses and algo order statuses
    active_statuses = {"NEW", "PARTIALLY_FILLED", "PENDING"}
    fallback_stop_price: Decimal | None = None
    for order_snapshot in order_statuses.values():
        if order_snapshot.get("symbol") != symbol:
            continue
        if order_snapshot.get("side") != "SELL":
            continue
        if order_snapshot.get("original_order_type") != "STOP_MARKET":
            continue
        if order_snapshot.get("status") not in active_statuses:
            continue
        stop_price = order_snapshot.get("stop_price")
        if stop_price in (None, ""):
            continue
        try:
            parsed = Decimal(str(stop_price))
        except (InvalidOperation, TypeError):
            continue
        if is_strategy_client_order_id(order_snapshot.get("client_order_id")):
            return parsed
        if fallback_stop_price is None:
            fallback_stop_price = parsed
    return fallback_stop_price
