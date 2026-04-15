from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal

from momentum_alpha.models import Position, PositionLeg, StrategyState, TickDecision


def _parse_day(current_day: str):
    return datetime.strptime(current_day, "%Y-%m-%d").date()


def restore_state(
    *,
    current_day: str,
    previous_leader_symbol: str | None,
    position_risk: list[dict],
    open_orders: list[dict],
) -> StrategyState:
    stop_prices = {
        order["symbol"]: Decimal(order["stopPrice"])
        for order in open_orders
        if order.get("type") == "STOP_MARKET" and order.get("stopPrice") is not None
    }

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
