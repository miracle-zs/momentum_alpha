from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from momentum_alpha.runtime import build_runtime

from .market_data_cache import LiveMarketDataCache


def _build_live_snapshots(
    *,
    symbols: list[str],
    held_symbols: set[str],
    client,
    now: datetime,
    market_data_cache: LiveMarketDataCache | None = None,
    base_veto_enabled: bool = False,
    previous_leader_symbol: str | None = None,
) -> list[dict]:
    cache = market_data_cache or LiveMarketDataCache()
    tracked_symbols = list(dict.fromkeys([*symbols, *sorted(held_symbols)]))
    latest_prices = cache.latest_prices(
        symbols=tracked_symbols,
        client=client,
        fallback_symbols=held_symbols,
    )
    cache.ensure_daily_open_prices(
        symbols=tracked_symbols,
        client=client,
        now=now,
        priority_symbols=held_symbols,
    )

    provisional_snapshots: list[dict] = []
    for symbol in tracked_symbols:
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
    leader_snapshot = min(
        leader_runtime.market.values(),
        key=lambda item: (-item.daily_change_pct, item.symbol),
        default=None,
    )
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
    leader_symbol = leader_snapshot.symbol if leader_snapshot is not None else None
    base_veto_candidate = bool(
        base_veto_enabled
        and leader_symbol is not None
        and leader_symbol != previous_leader_symbol
        and leader_symbol not in held_symbols
    )
    if base_veto_candidate:
        cache.ensure_base_veto_features(
            symbols={leader_symbol},
            client=client,
            now=now,
        )

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
                "base_veto_features": (
                    cache.base_veto_features.get(symbol)
                    if base_veto_candidate and symbol == leader_symbol
                    else None
                ),
            }
        )
    return snapshots
