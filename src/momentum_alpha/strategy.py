from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from momentum_alpha.models import (
    EntryIntent,
    HourCloseDecision,
    MarketSnapshot,
    MinuteCloseDecision,
    StrategyState,
    TickDecision,
)


def _leader_symbol(market: dict[str, MarketSnapshot]) -> str | None:
    candidates = [snapshot for snapshot in market.values() if snapshot.tradable and snapshot.daily_open_price > 0]
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda item: (-item.daily_change_pct, item.symbol))
    return ordered[0].symbol


def _in_entry_window(now: datetime) -> bool:
    return now.hour >= 1


def _entry_stop_price(snapshot: MarketSnapshot) -> Decimal:
    if snapshot.latest_price < snapshot.previous_hour_low:
        return snapshot.current_hour_low
    return snapshot.previous_hour_low


def evaluate_minute_close(
    *,
    now: datetime,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
) -> MinuteCloseDecision:
    leader = _leader_symbol(market)
    if leader is None:
        return MinuteCloseDecision(base_entries=[], new_previous_leader_symbol=None, blocked_reason="no_tradable_leader")

    entries: list[EntryIntent] = []
    snapshot = market[leader]
    leader_changed = leader != state.previous_leader_symbol
    stop_price = _entry_stop_price(snapshot)
    blocked_reason: str | None = None
    if not _in_entry_window(now):
        blocked_reason = "outside_entry_window"
    elif not leader_changed:
        blocked_reason = "leader_unchanged"
    elif leader in state.positions:
        blocked_reason = "already_holding"
    elif not snapshot.has_previous_hour_candle:
        blocked_reason = "missing_previous_hour_candle"
    elif stop_price >= snapshot.latest_price:
        blocked_reason = "invalid_stop_price"

    can_enter = blocked_reason is None
    if can_enter:
        entries.append(EntryIntent(symbol=leader, stop_price=stop_price, leg_type="base"))
    else:
        blocked_reason = blocked_reason if leader_changed else None

    return MinuteCloseDecision(base_entries=entries, new_previous_leader_symbol=leader, blocked_reason=blocked_reason)


def evaluate_hour_close(
    *,
    now: datetime,
    state: StrategyState,
    latest_hour_lows: dict[str, Decimal],
) -> HourCloseDecision:
    _ = now
    add_on_entries: list[EntryIntent] = []
    updated_stop_prices: dict[str, Decimal] = {}
    for symbol in sorted(state.positions):
        if symbol not in latest_hour_lows:
            continue
        stop_price = latest_hour_lows[symbol]
        updated_stop_prices[symbol] = stop_price
        add_on_entries.append(EntryIntent(symbol=symbol, stop_price=stop_price, leg_type="add_on"))
    return HourCloseDecision(add_on_entries=add_on_entries, updated_stop_prices=updated_stop_prices)


def process_clock_tick(
    *,
    now: datetime,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
) -> TickDecision:
    minute_close = evaluate_minute_close(now=now, state=state, market=market)
    add_on_entries: list[EntryIntent] = []
    updated_stop_prices: dict[str, Decimal] = {}
    if now.minute == 0:
        latest_hour_lows = {
            symbol: snapshot.previous_hour_low
            for symbol, snapshot in market.items()
            if symbol in state.positions
        }
        hour_close = evaluate_hour_close(now=now, state=state, latest_hour_lows=latest_hour_lows)
        add_on_entries = hour_close.add_on_entries
        updated_stop_prices = hour_close.updated_stop_prices

    return TickDecision(
        base_entries=minute_close.base_entries,
        add_on_entries=add_on_entries,
        updated_stop_prices=updated_stop_prices,
        new_previous_leader_symbol=minute_close.new_previous_leader_symbol,
        blocked_reason=minute_close.blocked_reason,
    )
