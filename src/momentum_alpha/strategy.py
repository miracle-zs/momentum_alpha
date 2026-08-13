from __future__ import annotations

from datetime import datetime, timedelta, timezone
from decimal import Decimal

from momentum_alpha.leg_semantics import is_add_on_leg
from momentum_alpha.models import (
    EntryIntent,
    HourCloseDecision,
    MarketSnapshot,
    MinuteCloseDecision,
    SkippedAddOn,
    SkippedBaseEntry,
    StrategyState,
    TickDecision,
)
from momentum_alpha.trace_ids import build_shadow_opportunity_id


def _leader_symbol(market: dict[str, MarketSnapshot]) -> str | None:
    candidates = [snapshot for snapshot in market.values() if snapshot.tradable and snapshot.daily_open_price > 0]
    if not candidates:
        return None
    ordered = sorted(candidates, key=lambda item: (-item.daily_change_pct, item.symbol))
    return ordered[0].symbol


def _in_entry_window(now: datetime, *, start_hour_utc: int = 1, end_hour_utc: int = 23) -> bool:
    if start_hour_utc <= end_hour_utc:
        return start_hour_utc <= now.hour <= end_hour_utc
    return now.hour >= start_hour_utc or now.hour <= end_hour_utc


def _blocked_beijing_hour(now: datetime, *, blocked_hours: tuple[int, ...]) -> int | None:
    beijing = timezone(timedelta(hours=8))
    local_hour = now.astimezone(beijing).hour
    return local_hour if local_hour in blocked_hours else None


def _as_utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _entry_stop_price(snapshot: MarketSnapshot) -> Decimal:
    if snapshot.latest_price < snapshot.previous_hour_low:
        return snapshot.current_hour_low
    return snapshot.previous_hour_low


def evaluate_minute_close(
    *,
    now: datetime,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    blocked_base_entry_hours_beijing: tuple[int, ...] = (9, 10),
) -> MinuteCloseDecision:
    daily_base_signal_times = dict(state.daily_base_signal_times)
    daily_base_signal_counts = dict(state.daily_base_signal_counts)
    leader = _leader_symbol(market)
    if leader is None:
        return MinuteCloseDecision(
            base_entries=[],
            new_previous_leader_symbol=state.previous_leader_symbol,
            blocked_reason="no_tradable_leader",
            new_daily_base_signal_times=daily_base_signal_times,
            new_daily_base_signal_counts=daily_base_signal_counts,
        )

    entries: list[EntryIntent] = []
    skipped_base_entries: list[SkippedBaseEntry] = []
    snapshot = market[leader]
    leader_changed = leader != state.previous_leader_symbol
    stop_price = _entry_stop_price(snapshot)
    cooldown_expires_at = state.recent_stop_loss_exits.get(leader)
    blocked_beijing_hour = _blocked_beijing_hour(
        now,
        blocked_hours=blocked_base_entry_hours_beijing,
    )
    blocked_reason: str | None = None
    if not _in_entry_window(now, start_hour_utc=entry_start_hour_utc, end_hour_utc=entry_end_hour_utc):
        blocked_reason = "outside_entry_window"
    elif not leader_changed:
        blocked_reason = "leader_unchanged"
    elif cooldown_expires_at is not None and now < cooldown_expires_at + STOP_LOSS_COOLDOWN:
        blocked_reason = "stop_loss_cooldown"
    elif leader in state.positions:
        blocked_reason = "already_holding"
    elif not snapshot.has_previous_hour_candle:
        blocked_reason = "missing_previous_hour_candle"
    elif stop_price >= snapshot.latest_price:
        blocked_reason = "invalid_stop_price"

    if blocked_reason is None:
        sequence = daily_base_signal_counts.get(leader, 0) + 1
        first_signal_at = daily_base_signal_times.get(leader)
        if first_signal_at is not None:
            daily_base_signal_counts[leader] = sequence
            blocked_reason = "daily_repeat_base"
            skipped_base_entries.append(
                SkippedBaseEntry(
                    symbol=leader,
                    stop_price=stop_price,
                    reason=blocked_reason,
                    base_signal_sequence=sequence,
                    first_base_signal_at=first_signal_at,
                    shadow_opportunity_id=build_shadow_opportunity_id(
                        symbol=leader,
                        signal_at=now,
                        sequence=sequence,
                    ),
                )
            )
        elif blocked_beijing_hour is not None:
            blocked_reason = f"beijing_{blocked_beijing_hour:02d}_base_block"
            skipped_base_entries.append(
                SkippedBaseEntry(
                    symbol=leader,
                    stop_price=stop_price,
                    reason=blocked_reason,
                    base_signal_sequence=sequence,
                    first_base_signal_at=now,
                    shadow_opportunity_id=build_shadow_opportunity_id(
                        symbol=leader,
                        signal_at=now,
                        sequence=sequence,
                    ),
                )
            )
        else:
            daily_base_signal_counts[leader] = sequence
            daily_base_signal_times[leader] = now
            entries.append(EntryIntent(symbol=leader, stop_price=stop_price, leg_type="base"))
    else:
        blocked_reason = blocked_reason if leader_changed else None

    return MinuteCloseDecision(
        base_entries=entries,
        new_previous_leader_symbol=leader,
        blocked_reason=blocked_reason,
        skipped_base_entries=skipped_base_entries,
        new_daily_base_signal_times=daily_base_signal_times,
        new_daily_base_signal_counts=daily_base_signal_counts,
    )


def evaluate_hour_close(
    *,
    now: datetime,
    state: StrategyState,
    latest_hour_lows: dict[str, Decimal],
    latest_prices: dict[str, Decimal] | None = None,
    current_leader_symbol: str | None,
    first_add_on_min_hold_minutes: int = 30,
) -> HourCloseDecision:
    add_on_entries: list[EntryIntent] = []
    skipped_add_ons: list[SkippedAddOn] = []
    updated_stop_prices: dict[str, Decimal] = {}
    for symbol in sorted(state.positions):
        if symbol not in latest_hour_lows:
            continue
        position = state.positions[symbol]
        stop_price = max(latest_hour_lows[symbol], position.stop_price)
        latest_price = None if latest_prices is None else latest_prices.get(symbol)
        if latest_price is not None and stop_price >= latest_price:
            skipped_add_ons.append(
                SkippedAddOn(symbol=symbol, stop_price=stop_price, reason="invalid_stop_price")
            )
            continue
        if stop_price > position.stop_price:
            updated_stop_prices[symbol] = stop_price
        if symbol != current_leader_symbol:
            skipped_add_ons.append(
                SkippedAddOn(symbol=symbol, stop_price=stop_price, reason="not_current_leader")
            )
            continue
        has_add_on = any(
            is_add_on_leg(leg_type=leg.leg_type, entry_order_id=leg.entry_order_id)
            for leg in position.legs
        )
        base_legs = [
            leg
            for leg in position.legs
            if not is_add_on_leg(leg_type=leg.leg_type, entry_order_id=leg.entry_order_id)
        ]
        base_opened_at = min((leg.opened_at for leg in base_legs), default=None)
        if not has_add_on and base_opened_at is not None:
            base_age = _as_utc(now) - _as_utc(base_opened_at)
            minimum_age = timedelta(minutes=first_add_on_min_hold_minutes)
            if base_age < minimum_age:
                skipped_add_ons.append(
                    SkippedAddOn(
                        symbol=symbol,
                        stop_price=stop_price,
                        reason="first_add_on_before_30m",
                        base_opened_at=base_opened_at,
                        base_age_minutes=Decimal(str(base_age.total_seconds())) / Decimal("60"),
                    )
                )
                continue
        add_on_entries.append(EntryIntent(symbol=symbol, stop_price=stop_price, leg_type="add_on"))
    return HourCloseDecision(
        add_on_entries=add_on_entries,
        updated_stop_prices=updated_stop_prices,
        skipped_add_ons=skipped_add_ons,
    )


def process_clock_tick(
    *,
    now: datetime,
    state: StrategyState,
    market: dict[str, MarketSnapshot],
    last_add_on_hour: int | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    blocked_base_entry_hours_beijing: tuple[int, ...] = (9, 10),
    first_add_on_min_hold_minutes: int = 30,
) -> TickDecision:
    minute_close = evaluate_minute_close(
        now=now,
        state=state,
        market=market,
        entry_start_hour_utc=entry_start_hour_utc,
        entry_end_hour_utc=entry_end_hour_utc,
        blocked_base_entry_hours_beijing=blocked_base_entry_hours_beijing,
    )
    add_on_entries: list[EntryIntent] = []
    skipped_add_ons: list[SkippedAddOn] = []
    updated_stop_prices: dict[str, Decimal] = {}
    new_last_add_on_hour = last_add_on_hour
    current_hour = now.hour
    should_execute_add_on = (
        last_add_on_hour is not None
        and current_hour != last_add_on_hour
    )
    if should_execute_add_on:
        latest_hour_lows = {
            symbol: snapshot.previous_hour_low
            for symbol, snapshot in market.items()
            if symbol in state.positions
        }
        latest_prices = {
            symbol: snapshot.latest_price
            for symbol, snapshot in market.items()
            if symbol in state.positions
        }
        hour_close = evaluate_hour_close(
            now=now,
            state=state,
            latest_hour_lows=latest_hour_lows,
            latest_prices=latest_prices,
            current_leader_symbol=minute_close.new_previous_leader_symbol,
            first_add_on_min_hold_minutes=first_add_on_min_hold_minutes,
        )
        add_on_entries = hour_close.add_on_entries
        skipped_add_ons = hour_close.skipped_add_ons
        updated_stop_prices = hour_close.updated_stop_prices
        new_last_add_on_hour = current_hour

    return TickDecision(
        base_entries=minute_close.base_entries,
        add_on_entries=add_on_entries,
        updated_stop_prices=updated_stop_prices,
        new_previous_leader_symbol=minute_close.new_previous_leader_symbol,
        new_last_add_on_hour=new_last_add_on_hour,
        blocked_reason=minute_close.blocked_reason,
        skipped_add_ons=skipped_add_ons,
        skipped_base_entries=minute_close.skipped_base_entries,
        new_daily_base_signal_times=minute_close.new_daily_base_signal_times,
        new_daily_base_signal_counts=minute_close.new_daily_base_signal_counts,
    )
STOP_LOSS_COOLDOWN = timedelta(minutes=60)
