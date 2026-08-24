from __future__ import annotations

import threading
from datetime import date, datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.base_veto import BaseVetoFeatures, compute_base_veto_features
from momentum_alpha.exchange_info import parse_exchange_info
from momentum_alpha.runtime_sync_state import RuntimeSyncStateStore

from .market_data_klines import (
    _fetch_base_veto_klines,
    _fetch_current_hour_klines,
    _fetch_daily_open_klines,
    _fetch_previous_hour_klines,
)
from .market_data_windows import _current_hour_window_ms, _previous_closed_hour_window_ms
from .market_data_daily_open_stream import DailyOpenKlineStream, DailyOpenUpdate


class LiveMarketDataCache:
    def __init__(
        self,
        *,
        runtime_db_path: Path | None = None,
        daily_open_rest_limit_per_minute: int = 150,
        logger=None,
    ) -> None:
        self.exchange_symbols: dict[str, object] | None = None
        self.daily_open_day: date | None = None
        self.daily_open_prices: dict[str, Decimal] = {}
        self.runtime_sync_store = (
            RuntimeSyncStateStore(path=runtime_db_path)
            if runtime_db_path is not None
            else None
        )
        self.daily_open_rest_limit_per_minute = max(0, daily_open_rest_limit_per_minute)
        self.daily_open_rest_minute: int | None = None
        self.daily_open_rest_calls = 0
        self.daily_open_stream_handle = None
        self.logger = logger
        self._daily_open_lock = threading.Lock()
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

    def _load_daily_open_day(self, *, utc_day: date) -> None:
        if self.daily_open_day == utc_day:
            return
        with self._daily_open_lock:
            if self.daily_open_day == utc_day:
                return
            self.daily_open_day = utc_day
            self.daily_open_prices = (
                self.runtime_sync_store.load_daily_opens(trading_day=utc_day)
                if self.runtime_sync_store is not None
                else {}
            )

    def record_daily_open_update(self, update: DailyOpenUpdate) -> None:
        self._load_daily_open_day(utc_day=update.trading_day)
        with self._daily_open_lock:
            if self.daily_open_day != update.trading_day:
                return
            existing = self.daily_open_prices.get(update.symbol)
            if existing == update.open_price:
                return
            self.daily_open_prices[update.symbol] = update.open_price
        if self.runtime_sync_store is not None:
            self.runtime_sync_store.save_daily_open(
                trading_day=update.trading_day,
                symbol=update.symbol,
                open_price=update.open_price,
                source="websocket-kline-1d",
                observed_at=update.observed_at,
            )

    def start_daily_open_stream(
        self,
        *,
        symbols: list[str],
        testnet: bool = False,
        stream_factory=DailyOpenKlineStream,
    ) -> None:
        if self.daily_open_stream_handle is not None:
            return
        stream = stream_factory(
            symbols=tuple(symbols),
            on_update=self.record_daily_open_update,
            testnet=testnet,
            logger=self.logger,
        )
        self.daily_open_stream_handle = stream.start()

    def stop_daily_open_stream(self) -> None:
        if self.daily_open_stream_handle is None:
            return
        self.daily_open_stream_handle.stop()
        self.daily_open_stream_handle = None

    def ensure_daily_open_prices(
        self,
        *,
        symbols: list[str],
        client,
        now: datetime,
        priority_symbols: set[str] | None = None,
    ) -> None:
        utc_day = now.astimezone(timezone.utc).date()
        self._load_daily_open_day(utc_day=utc_day)
        minute = int(now.astimezone(timezone.utc).timestamp() // 60)
        if self.daily_open_rest_minute != minute:
            self.daily_open_rest_minute = minute
            self.daily_open_rest_calls = 0
        priority = set(priority_symbols or ())
        ordered_symbols = [
            *[symbol for symbol in symbols if symbol in priority],
            *[symbol for symbol in symbols if symbol not in priority],
        ]
        utc_now = now.astimezone(timezone.utc)
        seconds_since_midnight = utc_now.hour * 3600 + utc_now.minute * 60 + utc_now.second
        for symbol in ordered_symbols:
            if symbol in self.daily_open_prices:
                continue
            # Give the warm WebSocket two minutes to publish the new daily
            # candle. Held positions may still use the REST safety fallback
            # immediately. The helper can issue two kline reads for a newly
            # listed symbol, so reserve two units per symbol to keep the hard
            # request ceiling honest even when both reads are needed.
            if seconds_since_midnight < 120 and symbol not in priority:
                continue
            if self.daily_open_rest_calls + 2 > self.daily_open_rest_limit_per_minute:
                break
            self.daily_open_rest_calls += 2
            day_open_klines = _fetch_daily_open_klines(client=client, symbol=symbol, now=now)
            if not day_open_klines:
                continue
            open_price = Decimal(day_open_klines[0][1])
            update = DailyOpenUpdate(
                symbol=symbol,
                trading_day=utc_day,
                open_price=open_price,
                observed_at=now,
            )
            with self._daily_open_lock:
                self.daily_open_prices[symbol] = open_price
            if self.runtime_sync_store is not None:
                self.runtime_sync_store.save_daily_open(
                    trading_day=utc_day,
                    symbol=symbol,
                    open_price=open_price,
                    source="rest-kline-fallback",
                    observed_at=update.observed_at,
                )

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
