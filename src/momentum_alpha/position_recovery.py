from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from momentum_alpha.leg_semantics import infer_leg_type_from_client_order_id
from momentum_alpha.models import Position, PositionLeg
from momentum_alpha.orders import is_strategy_client_order_id


@dataclass
class _OrderFillGroup:
    client_order_id: str
    quantity: Decimal
    notional: Decimal
    opened_at: datetime


def _decimal(value: object) -> Decimal | None:
    try:
        parsed = Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None


def _trade_time(trade: dict) -> datetime | None:
    raw_time = trade.get("time")
    try:
        return datetime.fromtimestamp(int(raw_time) / 1000, tz=timezone.utc)
    except (TypeError, ValueError, OSError):
        return None


def _trade_side(trade: dict) -> str | None:
    side = str(trade.get("side") or "").upper()
    if side in {"BUY", "SELL"}:
        return side
    if trade.get("buyer") is True:
        return "BUY"
    if trade.get("buyer") is False:
        return "SELL"
    return None


def fetch_complete_history(
    fetch_fn,
    *,
    symbol: str,
    start_time_ms: int,
    end_time_ms: int,
    limit: int = 1000,
) -> list[dict]:
    """Fetch a bounded Binance history range without silently truncating it."""
    rows = fetch_fn(
        symbol=symbol,
        start_time_ms=start_time_ms,
        end_time_ms=end_time_ms,
        limit=limit,
    )
    if len(rows) < limit or end_time_ms - start_time_ms <= 1:
        return rows
    midpoint = start_time_ms + ((end_time_ms - start_time_ms) // 2)
    left = fetch_complete_history(
        fetch_fn,
        symbol=symbol,
        start_time_ms=start_time_ms,
        end_time_ms=midpoint,
        limit=limit,
    )
    right = fetch_complete_history(
        fetch_fn,
        symbol=symbol,
        start_time_ms=midpoint + 1,
        end_time_ms=end_time_ms,
        limit=limit,
    )
    seen: set[tuple[object, object]] = set()
    complete: list[dict] = []
    for row in [*left, *right]:
        identity = (row.get("id", row.get("orderId")), row.get("time", row.get("updateTime")))
        if identity in seen:
            continue
        seen.add(identity)
        complete.append(row)
    return complete


def rebuild_position_from_trade_history(
    *,
    position: Position,
    trades: list[dict],
    orders: list[dict],
) -> Position | None:
    """Rebuild the current long position only when trade history explains it exactly."""

    order_clients = {
        str(order.get("orderId")): str(order.get("clientOrderId"))
        for order in orders
        if order.get("orderId") not in (None, "")
        and is_strategy_client_order_id(order.get("clientOrderId"))
        and str(order.get("side") or "BUY").upper() == "BUY"
    }
    needed_quantity = position.total_quantity
    selected: list[tuple[dict, Decimal, Decimal, datetime, str]] = []
    sorted_trades = sorted(
        trades,
        key=lambda trade: (int(trade.get("time") or 0), int(trade.get("id") or 0)),
        reverse=True,
    )
    for trade in sorted_trades:
        quantity = _decimal(trade.get("qty"))
        side = _trade_side(trade)
        if quantity is None or side is None:
            continue
        if side == "SELL":
            needed_quantity += quantity
            continue

        order_id = str(trade.get("orderId"))
        client_order_id = order_clients.get(order_id)
        price = _decimal(trade.get("price"))
        opened_at = _trade_time(trade)
        if quantity > needed_quantity or client_order_id is None or price is None or opened_at is None:
            return None
        selected.append((trade, quantity, price, opened_at, client_order_id))
        needed_quantity -= quantity
        if needed_quantity == 0:
            break

    if needed_quantity != 0 or not selected:
        return None

    grouped: dict[str, _OrderFillGroup] = {}
    for trade, quantity, price, opened_at, client_order_id in selected:
        order_id = str(trade.get("orderId"))
        existing = grouped.get(order_id)
        if existing is None:
            grouped[order_id] = _OrderFillGroup(
                client_order_id=client_order_id,
                quantity=quantity,
                notional=quantity * price,
                opened_at=opened_at,
            )
            continue
        existing.quantity += quantity
        existing.notional += quantity * price
        existing.opened_at = min(existing.opened_at, opened_at)

    legs: list[PositionLeg] = []
    for group in sorted(grouped.values(), key=lambda item: item.opened_at):
        leg_type = infer_leg_type_from_client_order_id(group.client_order_id)
        if leg_type is None:
            return None
        legs.append(
            PositionLeg(
                symbol=position.symbol,
                quantity=group.quantity,
                entry_price=group.notional / group.quantity,
                stop_price=position.stop_price,
                opened_at=group.opened_at,
                leg_type=leg_type,
                entry_order_id=group.client_order_id,
                leg_source="trade_recovery",
            )
        )

    rebuilt = Position(symbol=position.symbol, stop_price=position.stop_price, legs=tuple(legs))
    return rebuilt if rebuilt.total_quantity == position.total_quantity else None


def position_needs_trade_recovery(position: Position) -> bool:
    synthetic_sources = {"rest_restore", "account_update", "reconciliation"}
    entry_order_ids = [leg.entry_order_id for leg in position.legs if leg.entry_order_id is not None]
    return any(leg.leg_source in synthetic_sources for leg in position.legs) or len(entry_order_ids) != len(set(entry_order_ids))
