from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.models import MarketSnapshot, Position, PositionLeg, StrategyState, TickDecision
from momentum_alpha.orders import is_strategy_client_order_id


def _parse_day(current_day: str):
    return datetime.strptime(current_day, "%Y-%m-%d").date()


def restore_state(
    *,
    current_day: str,
    previous_leader_symbol: str | None,
    position_risk: list[dict],
    open_orders: list[dict],
) -> StrategyState:
    stop_prices: dict[str, Decimal] = {}
    fallback_stop_prices: dict[str, Decimal] = {}
    for order in open_orders:
        order_type = order.get("type") or order.get("orderType")
        raw_stop_price = order.get("stopPrice") or order.get("triggerPrice")
        if order_type != "STOP_MARKET" or raw_stop_price is None:
            continue
        symbol = order["symbol"]
        stop_price = Decimal(raw_stop_price)
        if is_strategy_client_order_id(order.get("clientOrderId") or order.get("clientAlgoId")):
            stop_prices[symbol] = stop_price
        elif symbol not in stop_prices:
            fallback_stop_prices[symbol] = stop_price
    for symbol, stop_price in fallback_stop_prices.items():
        stop_prices.setdefault(symbol, stop_price)

    positions: dict[str, Position] = {}
    for item in position_risk:
        quantity = Decimal(item["positionAmt"])
        if quantity <= 0:
            continue
        symbol = item["symbol"]
        stop_price = stop_prices.get(symbol, Decimal("0"))
        opened_at = datetime.fromtimestamp(int(item["updateTime"]) / 1000, tz=timezone.utc)
        leg = PositionLeg(
            symbol=symbol,
            quantity=quantity,
            entry_price=Decimal(item["entryPrice"]),
            stop_price=stop_price,
            opened_at=opened_at,
            leg_type="restored",
        )
        positions[symbol] = Position(symbol=symbol, stop_price=stop_price, legs=(leg,))

    return StrategyState(
        current_day=_parse_day(current_day),
        previous_leader_symbol=previous_leader_symbol,
        positions=positions,
        recent_stop_loss_exits={},
    )


def build_stop_reconciliation_plan(
    *,
    state: StrategyState,
    decision: TickDecision,
) -> list[tuple[str, Decimal]]:
    replacements: list[tuple[str, Decimal]] = []
    for symbol, target_stop_price in sorted(decision.updated_stop_prices.items()):
        position = state.positions.get(symbol)
        if position is None:
            continue
        if position.stop_price != target_stop_price:
            replacements.append((symbol, target_stop_price))
    return replacements


def build_missing_stop_reconciliation_plan(
    *,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
) -> list[tuple[str, Decimal]]:
    replacements: list[tuple[str, Decimal]] = []
    for symbol, position in sorted(state.positions.items()):
        if position.stop_price > Decimal("0"):
            continue
        snapshot = market.get(symbol)
        if snapshot is None or not snapshot.has_previous_hour_candle:
            continue
        target_stop_price = (
            snapshot.current_hour_low
            if snapshot.latest_price < snapshot.previous_hour_low
            else snapshot.previous_hour_low
        )
        if target_stop_price <= Decimal("0") or target_stop_price >= snapshot.latest_price:
            continue
        replacements.append((symbol, target_stop_price))
    return replacements


def build_stale_stop_reconciliation_plan(
    *,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
) -> list[tuple[str, Decimal]]:
    replacements: list[tuple[str, Decimal]] = []
    for symbol, position in sorted(state.positions.items()):
        if position.stop_price <= Decimal("0"):
            continue
        snapshot = market.get(symbol)
        if snapshot is None or not snapshot.has_previous_hour_candle:
            continue
        target_stop_price = snapshot.previous_hour_low
        if target_stop_price <= position.stop_price:
            continue
        if target_stop_price <= Decimal("0") or target_stop_price >= snapshot.latest_price:
            continue
        replacements.append((symbol, target_stop_price))
    return replacements
