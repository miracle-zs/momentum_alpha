from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class MarketDataTests(unittest.TestCase):
    def test_market_data_split_modules_export_key_entrypoints(self) -> None:
        from momentum_alpha import (
            market_data_cache,
            market_data_klines,
            market_data_snapshots,
            market_data_symbols,
            market_data_windows,
        )

        self.assertTrue(callable(market_data_symbols._resolve_symbols))
        self.assertTrue(callable(market_data_windows._utc_midnight_window_ms))
        self.assertTrue(callable(market_data_klines._fetch_daily_open_klines))
        self.assertTrue(callable(market_data_snapshots._build_live_snapshots))
        self.assertTrue(callable(market_data_cache.LiveMarketDataCache))

    def test_utc_midnight_window_targets_first_utc_minute(self) -> None:
        from momentum_alpha.market_data import utc_midnight_window_ms

        start_ms, end_ms = utc_midnight_window_ms(
            now=datetime(2026, 4, 21, 9, 30, tzinfo=timezone.utc)
        )

        self.assertEqual(start_ms, 1776729600000)
        self.assertEqual(end_ms, 1776729659999)

    def test_live_market_data_cache_deduplicates_requested_symbols(self) -> None:
        from momentum_alpha.market_data import LiveMarketDataCache

        class Client:
            def fetch_exchange_info(self):
                raise AssertionError("explicit symbols should not fetch exchange info")

        cache = LiveMarketDataCache()

        self.assertEqual(
            cache.resolve_symbols(symbols=["BTCUSDT", "ETHUSDT", "BTCUSDT"], client=Client()),
            ["BTCUSDT", "ETHUSDT"],
        )

    def test_build_live_snapshots_skips_unusable_prices(self) -> None:
        from momentum_alpha.market_data import build_live_snapshots

        class Client:
            def fetch_ticker_prices(self):
                return [
                    {"symbol": "BTCUSDT", "price": "105"},
                    {"symbol": "BADUSDT", "price": "not-a-number"},
                ]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if symbol == "BTCUSDT" and interval == "1m":
                    return [[0, "100", "106", "99", "105", "1", 0, "1", 1, "1", "1", "0"]]
                if symbol == "BTCUSDT" and interval == "1h":
                    return [[0, "100", "106", "95", "105", "1", 0, "1", 1, "1", "1", "0"]]
                return []

        snapshots = build_live_snapshots(
            symbols=["BTCUSDT", "BADUSDT"],
            held_symbols=set(),
            client=Client(),
            now=datetime(2026, 4, 21, 2, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([item["symbol"] for item in snapshots], ["BTCUSDT"])
        self.assertEqual(snapshots[0]["daily_open_price"], Decimal("100"))
        self.assertEqual(snapshots[0]["latest_price"], Decimal("105"))
        self.assertEqual(snapshots[0]["previous_hour_low"], Decimal("95"))

    def test_build_live_snapshots_uses_first_available_minute_for_new_listing_open(self) -> None:
        from momentum_alpha.market_data import build_live_snapshots

        class Client:
            def __init__(self) -> None:
                self.kline_calls = []

            def fetch_ticker_prices(self):
                return [{"symbol": "NEWUSDT", "price": "135"}]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                self.kline_calls.append(
                    {
                        "symbol": symbol,
                        "interval": interval,
                        "limit": limit,
                        "start_time_ms": start_time_ms,
                        "end_time_ms": end_time_ms,
                    }
                )
                if interval == "1m" and start_time_ms == 1776211200000 and end_time_ms == 1776211259999:
                    return []
                if interval == "1m" and start_time_ms == 0:
                    return [[1776258000000, "100", "136", "99", "135", "1", 0, "1", 1, "1", "1", "0"]]
                if interval == "1h":
                    return [[1776254400000, "105", "136", "104", "135", "1", 0, "1", 1, "1", "1", "0"]]
                return []

        client = Client()

        snapshots = build_live_snapshots(
            symbols=["NEWUSDT"],
            held_symbols=set(),
            client=client,
            now=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
        )

        self.assertEqual([item["symbol"] for item in snapshots], ["NEWUSDT"])
        self.assertEqual(snapshots[0]["daily_open_price"], Decimal("100"))
        self.assertEqual(client.kline_calls[1]["limit"], 1)
        self.assertEqual(client.kline_calls[1]["start_time_ms"], 0)
