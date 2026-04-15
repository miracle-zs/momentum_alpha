from __future__ import annotations

from dataclasses import dataclass, field, replace
from datetime import date, datetime
from decimal import Decimal


@dataclass(frozen=True)
class MarketSnapshot:
    symbol: str
    daily_open_price: Decimal
    latest_price: Decimal
    previous_hour_low: Decimal
    tradable: bool
    has_previous_hour_candle: bool
    current_hour_low: Decimal = Decimal("0")

    @property
    def daily_change_pct(self) -> Decimal:
        return (self.latest_price - self.daily_open_price) / self.daily_open_price


@dataclass(frozen=True)
class PositionLeg:
    symbol: str
    quantity: Decimal
    entry_price: Decimal
    stop_price: Decimal
    opened_at: datetime
    leg_type: str

    @property
    def stop_risk(self) -> Decimal:
        return self.quantity * (self.entry_price - self.stop_price)


@dataclass(frozen=True)
class Position:
    symbol: str
    stop_price: Decimal
    legs: tuple[PositionLeg, ...]

    @property
    def total_quantity(self) -> Decimal:
        total = Decimal("0")
        for leg in self.legs:
            total += leg.quantity
        return total

    def with_stop_price(self, stop_price: Decimal) -> "Position":
        updated_legs = tuple(replace(leg, stop_price=stop_price) for leg in self.legs)
        return Position(symbol=self.symbol, stop_price=stop_price, legs=updated_legs)


@dataclass(frozen=True)
class EntryIntent:
    symbol: str
    stop_price: Decimal
    leg_type: str


@dataclass(frozen=True)
class MinuteCloseDecision:
    base_entries: list[EntryIntent]
    new_previous_leader_symbol: str | None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class HourCloseDecision:
    add_on_entries: list[EntryIntent]
    updated_stop_prices: dict[str, Decimal]


@dataclass(frozen=True)
class TickDecision:
    base_entries: list[EntryIntent]
    add_on_entries: list[EntryIntent]
    updated_stop_prices: dict[str, Decimal]
    new_previous_leader_symbol: str | None
    blocked_reason: str | None = None


@dataclass(frozen=True)
class StrategyState:
    current_day: date
    previous_leader_symbol: str | None
    positions: dict[str, Position] = field(default_factory=dict)
