from __future__ import annotations

from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation

from momentum_alpha.base_veto import BaseVetoFeatures, compute_base_veto_features
from momentum_alpha.exchange_info import parse_exchange_info

from .market_data_klines import (
    _fetch_base_veto_klines,
    _fetch_current_hour_klines,
    _fetch_daily_open_klines,
    _fetch_previous_hour_klines,
)
from .market_data_windows import _current_hour_window_ms, _previous_closed_hour_window_ms


class LiveMarketDataCache:
    def __init__(self) -> None:
        self.exchange_symbols: dict[str, object] | None = None
        self.daily_open_day: date | None = None
        self.daily_open_prices: dict[str, Decimal] = {}
        self.previous_hour_window: tuple[int, int] | None = None
        self.previous_hour_lows: dict[str, tuple[bool, Decimal]] = {}
        self.current_hour_window: tuple[int, int] | None = None
        self.current_hour_lows: dict[str, Decimal] = {}
        self.base_veto_minute: int | None = None
        self.base_veto_features: dict[str, BaseVetoFeatures] = {}

    def resolve_symbols(self, *, symbols: list[str] | None, client) -> list[str]:
        requested_symbols = [symbol for symbol in (symbols or []) if symbol]
        if requested_symbols:
            return list(dict.fromkeys(requested_symbols))
        return list(self._exchange_symbols(client=client).keys())

    def exchange_symbol_map(self, *, client) -> dict[str, object]:
        return self._exchange_symbols(client=client)

    def refresh_exchange_symbols(self, *, client) -> dict[str, object]:
        self.exchange_symbols = parse_exchange_info(client.fetch_exchange_info())
        return self.exchange_symbols

    def _exchange_symbols(self, *, client) -> dict[str, object]:
        if self.exchange_symbols is None:
            self.exchange_symbols = parse_exchange_info(client.fetch_exchange_info())
        return self.exchange_symbols

    def latest_prices(
        self,
        *,
        symbols: list[str],
        client,
        fallback_symbols: set[str] | None = None,
    ) -> dict[str, Decimal]:
        try:
            tickers = client.fetch_ticker_prices()
            prices: dict[str, Decimal] = {}
            for ticker in tickers:
                symbol = ticker.get("symbol")
                if symbol not in symbols:
                    continue
                try:
                    prices[symbol] = Decimal(ticker["price"])
                except (KeyError, InvalidOperation, TypeError):
                    continue
            fetch_ticker_price = getattr(client, "fetch_ticker_price", None)
            if callable(fetch_ticker_price):
                symbols_to_fallback = set(fallback_symbols or ()) & (set(symbols) - set(prices))
                for symbol in sorted(symbols_to_fallback):
                    try:
                        ticker = fetch_ticker_price(symbol=symbol)
                        prices[symbol] = Decimal(ticker["price"])
                    except (KeyError, InvalidOperation, TypeError):
                        continue
            return prices
        except AttributeError:
            prices = {}
            for symbol in symbols:
                try:
                    ticker = client.fetch_ticker_price(symbol=symbol)
                    prices[symbol] = Decimal(ticker["price"])
                except (KeyError, InvalidOperation, TypeError):
                    continue
            return prices

    def ensure_daily_open_prices(self, *, symbols: list[str], client, now: datetime) -> None:
        utc_day = now.astimezone(timezone.utc).date()
        if self.daily_open_day != utc_day:
            self.daily_open_day = utc_day
            self.daily_open_prices = {}
        for symbol in symbols:
            if symbol in self.daily_open_prices:
                continue
            day_open_klines = _fetch_daily_open_klines(client=client, symbol=symbol, now=now)
            if not day_open_klines:
                continue
            self.daily_open_prices[symbol] = Decimal(day_open_klines[0][1])

    def ensure_previous_hour_lows(self, *, symbols: set[str], client, now: datetime) -> None:
        window = _previous_closed_hour_window_ms(now=now)
        if self.previous_hour_window != window:
            self.previous_hour_window = window
            self.previous_hour_lows = {}
        for symbol in symbols:
            if symbol in self.previous_hour_lows:
                continue
            hour_klines = _fetch_previous_hour_klines(client=client, symbol=symbol, now=now)
            if hour_klines:
                self.previous_hour_lows[symbol] = (True, Decimal(hour_klines[0][3]))

    def ensure_current_hour_lows(self, *, symbols: set[str], client, now: datetime) -> None:
        window = _current_hour_window_ms(now=now)
        if self.current_hour_window != window:
            self.current_hour_window = window
            self.current_hour_lows = {}
        for symbol in symbols:
            if symbol in self.current_hour_lows:
                continue
            current_hour_klines = _fetch_current_hour_klines(client=client, symbol=symbol, now=now)
            if current_hour_klines:
                self.current_hour_lows[symbol] = Decimal(current_hour_klines[0][3])

    def ensure_base_veto_features(self, *, symbols: set[str], client, now: datetime) -> None:
        """Cache causal Base-veto features for the current poll minute."""

        minute = int(now.astimezone(timezone.utc).timestamp() // 60)
        if self.base_veto_minute != minute:
            self.base_veto_minute = minute
            self.base_veto_features = {}
        for symbol in symbols:
            if symbol in self.base_veto_features:
                continue
            try:
                klines = _fetch_base_veto_klines(client=client, symbol=symbol, now=now)
                self.base_veto_features[symbol] = compute_base_veto_features(
                    klines=klines,
                    signal_at=now,
                )
            except Exception as exc:
                self.base_veto_features[symbol] = BaseVetoFeatures(
                    unavailable_reason=f"feature_fetch_failed:{type(exc).__name__}",
                )
