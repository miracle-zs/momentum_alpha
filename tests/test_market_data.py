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
