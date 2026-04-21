from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation

from momentum_alpha.exchange_info import parse_exchange_info
from momentum_alpha.runtime import build_runtime


def _resolve_symbols(*, symbols: list[str] | None, client) -> list[str]:
    requested_symbols = [symbol for symbol in (symbols or []) if symbol]
    if requested_symbols:
        return list(dict.fromkeys(requested_symbols))
    return list(parse_exchange_info(client.fetch_exchange_info()).keys())


def _utc_midnight_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    utc_midnight = datetime(utc_now.year, utc_now.month, utc_now.day, tzinfo=timezone.utc)
    window_end = utc_midnight + timedelta(minutes=1) - timedelta(milliseconds=1)
    return int(utc_midnight.timestamp() * 1000), int(window_end.timestamp() * 1000)


def _previous_closed_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    previous_hour_start = current_hour_start - timedelta(hours=1)
    previous_hour_end = current_hour_start - timedelta(milliseconds=1)
    return int(previous_hour_start.timestamp() * 1000), int(previous_hour_end.timestamp() * 1000)


def _current_hour_window_ms(*, now: datetime) -> tuple[int, int]:
    utc_now = now.astimezone(timezone.utc)
    current_hour_start = datetime(utc_now.year, utc_now.month, utc_now.day, utc_now.hour, tzinfo=timezone.utc)
    return int(current_hour_start.timestamp() * 1000), int(utc_now.timestamp() * 1000)


def _fetch_daily_open_klines(*, client, symbol: str, now: datetime):
    day_open_start_ms, day_open_end_ms = _utc_midnight_window_ms(now=now)
    klines = client.fetch_klines(
        symbol=symbol,
        interval="1m",
        limit=1,
        start_time_ms=day_open_start_ms,
        end_time_ms=day_open_end_ms,
    )
    if klines:
        return klines
    return client.fetch_klines(
        symbol=symbol,
        interval="1m",
        limit=1,
        start_time_ms=day_open_start_ms,
        end_time_ms=int(now.astimezone(timezone.utc).timestamp() * 1000),
    )


def _fetch_previous_hour_klines(*, client, symbol: str, now: datetime):
    previous_hour_start_ms, previous_hour_end_ms = _previous_closed_hour_window_ms(now=now)
    return client.fetch_klines(
        symbol=symbol,
        interval="1h",
        limit=1,
        start_time_ms=previous_hour_start_ms,
        end_time_ms=previous_hour_end_ms,
    )


def _fetch_current_hour_klines(*, client, symbol: str, now: datetime):
    current_hour_start_ms, current_hour_end_ms = _current_hour_window_ms(now=now)
    return client.fetch_klines(
        symbol=symbol,
        interval="1h",
        limit=1,
        start_time_ms=current_hour_start_ms,
        end_time_ms=current_hour_end_ms,
    )


class LiveMarketDataCache:
    def __init__(self) -> None:
        self.exchange_symbols: dict[str, object] | None = None
        self.daily_open_day: date | None = None
        self.daily_open_prices: dict[str, Decimal] = {}
        self.previous_hour_window: tuple[int, int] | None = None
        self.previous_hour_lows: dict[str, tuple[bool, Decimal]] = {}
        self.current_hour_window: tuple[int, int] | None = None
        self.current_hour_lows: dict[str, Decimal] = {}

    def resolve_symbols(self, *, symbols: list[str] | None, client) -> list[str]:
        requested_symbols = [symbol for symbol in (symbols or []) if symbol]
        if requested_symbols:
            return list(dict.fromkeys(requested_symbols))
        return list(self._exchange_symbols(client=client).keys())

    def exchange_symbol_map(self, *, client) -> dict[str, object]:
        return self._exchange_symbols(client=client)

    def _exchange_symbols(self, *, client) -> dict[str, object]:
        if self.exchange_symbols is None:
            self.exchange_symbols = parse_exchange_info(client.fetch_exchange_info())
        return self.exchange_symbols

    def latest_prices(self, *, symbols: list[str], client) -> dict[str, Decimal]:
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
            return prices
        except AttributeError:
            prices = {}
            for symbol in symbols:
                ticker = client.fetch_ticker_price(symbol=symbol)
                try:
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
            else:
                self.previous_hour_lows[symbol] = (False, Decimal("0"))

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


def _build_live_snapshots(
    *,
    symbols: list[str],
    held_symbols: set[str],
    client,
    now: datetime,
    market_data_cache: LiveMarketDataCache | None = None,
) -> list[dict]:
    cache = market_data_cache or LiveMarketDataCache()
    latest_prices = cache.latest_prices(symbols=symbols, client=client)
    cache.ensure_daily_open_prices(symbols=symbols, client=client, now=now)

    provisional_snapshots: list[dict] = []
    for symbol in symbols:
        latest_price = latest_prices.get(symbol)
        daily_open_price = cache.daily_open_prices.get(symbol)
        if latest_price is None or daily_open_price is None:
            continue
        provisional_snapshots.append(
            {
                "symbol": symbol,
                "daily_open_price": daily_open_price,
                "latest_price": latest_price,
                "previous_hour_low": Decimal("0"),
                "tradable": True,
                "has_previous_hour_candle": False,
                "current_hour_low": Decimal("0"),
            }
        )

    if not provisional_snapshots:
        return []

    leader_runtime = build_runtime(snapshots=provisional_snapshots)
    leader_snapshot = max(leader_runtime.market.values(), key=lambda item: item.daily_change_pct, default=None)
    symbols_requiring_hour_data = set(held_symbols)
    if leader_snapshot is not None:
        symbols_requiring_hour_data.add(leader_snapshot.symbol)

    cache.ensure_previous_hour_lows(symbols=symbols_requiring_hour_data, client=client, now=now)
    current_hour_symbols = {
        symbol
        for symbol in symbols_requiring_hour_data
        if cache.previous_hour_lows.get(symbol, (False, Decimal("0")))[0]
        and latest_prices.get(symbol, Decimal("0")) < cache.previous_hour_lows[symbol][1]
    }
    cache.ensure_current_hour_lows(symbols=current_hour_symbols, client=client, now=now)

    snapshots: list[dict] = []
    for snapshot in provisional_snapshots:
        symbol = snapshot["symbol"]
        has_previous_hour_candle, previous_hour_low = cache.previous_hour_lows.get(
            symbol,
            (False, Decimal("0")),
        )
        current_hour_low = cache.current_hour_lows.get(symbol, previous_hour_low)
        snapshots.append(
            {
                **snapshot,
                "previous_hour_low": previous_hour_low,
                "has_previous_hour_candle": has_previous_hour_candle,
                "current_hour_low": current_hour_low,
            }
        )
    return snapshots


resolve_symbols = _resolve_symbols
utc_midnight_window_ms = _utc_midnight_window_ms
previous_closed_hour_window_ms = _previous_closed_hour_window_ms
current_hour_window_ms = _current_hour_window_ms
build_live_snapshots = _build_live_snapshots
