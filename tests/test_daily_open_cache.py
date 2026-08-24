from __future__ import annotations

import sys
import unittest
from datetime import datetime, timezone
from decimal import Decimal
from pathlib import Path
from tempfile import TemporaryDirectory


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DailyOpenCacheTests(unittest.TestCase):
    def test_websocket_daily_open_is_persisted_and_restored_after_restart(self) -> None:
        from momentum_alpha.market_data_cache import LiveMarketDataCache
        from momentum_alpha.market_data_daily_open_stream import DailyOpenUpdate

        observed_at = datetime(2026, 8, 24, 0, 0, 1, tzinfo=timezone.utc)
        with TemporaryDirectory() as tmpdir:
            path = Path(tmpdir) / "runtime.db"
            first = LiveMarketDataCache(runtime_db_path=path)
            first.record_daily_open_update(
                DailyOpenUpdate(
                    symbol="BTCUSDT",
                    trading_day=observed_at.date(),
                    open_price=Decimal("123.45"),
                    observed_at=observed_at,
                )
            )
            restored = LiveMarketDataCache(runtime_db_path=path)
            restored.ensure_daily_open_prices(
                symbols=["BTCUSDT"],
                client=object(),
                now=observed_at,
            )

        self.assertEqual(restored.daily_open_prices["BTCUSDT"], Decimal("123.45"))

    def test_rest_fallback_is_hard_limited_per_minute_and_prioritizes_positions(self) -> None:
        from momentum_alpha.market_data_cache import LiveMarketDataCache

        class Client:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def fetch_klines(self, **kwargs):
                self.calls.append(kwargs["symbol"])
                return [[0, "100", "101", "99", "100"]]

        now = datetime(2026, 8, 24, 0, 3, tzinfo=timezone.utc)
        client = Client()
        cache = LiveMarketDataCache(daily_open_rest_limit_per_minute=4)
        cache.ensure_daily_open_prices(
            symbols=["AUSDT", "BUSDT", "CUSDT"],
            priority_symbols={"CUSDT"},
            client=client,
            now=now,
        )
        cache.ensure_daily_open_prices(
            symbols=["AUSDT", "BUSDT", "CUSDT"],
            priority_symbols={"CUSDT"},
            client=client,
            now=now,
        )

        self.assertEqual(client.calls, ["CUSDT", "AUSDT"])
        self.assertEqual(set(cache.daily_open_prices), {"CUSDT", "AUSDT"})

    def test_new_day_gives_websocket_a_grace_period_before_universe_fallback(self) -> None:
        from momentum_alpha.market_data_cache import LiveMarketDataCache

        class Client:
            def __init__(self) -> None:
                self.calls: list[str] = []

            def fetch_klines(self, **kwargs):
                self.calls.append(kwargs["symbol"])
                return [[0, "100", "101", "99", "100"]]

        client = Client()
        cache = LiveMarketDataCache(daily_open_rest_limit_per_minute=150)
        cache.ensure_daily_open_prices(
            symbols=["BTCUSDT", "ETHUSDT"],
            priority_symbols=set(),
            client=client,
            now=datetime(2026, 8, 24, 0, 0, 30, tzinfo=timezone.utc),
        )

        self.assertEqual(client.calls, [])

    def test_stream_ignores_pre_midnight_candle_during_warmup(self) -> None:
        from momentum_alpha.market_data_daily_open_stream import DailyOpenKlineStream

        updates = []
        messages = [
            {
                "e": "kline",
                "E": 1787529599000,
                "s": "BTCUSDT",
                "k": {"i": "1d", "t": 1787443200000, "o": "100"},
            },
            {
                "e": "kline",
                "E": 1787529601000,
                "s": "BTCUSDT",
                "k": {"i": "1d", "t": 1787529600000, "o": "101"},
            },
        ]

        class StopEvent:
            def __init__(self) -> None:
                self.stopped = False

            def is_set(self):
                return self.stopped

            def wait(self, _seconds):
                self.stopped = True
                return True

        def runner(**kwargs):
            for message in messages:
                kwargs["on_message"](message)

        stream = DailyOpenKlineStream(
            symbols=("BTCUSDT",),
            on_update=updates.append,
            now_provider=lambda: datetime(2026, 8, 23, 23, 58, tzinfo=timezone.utc),
            websocket_runner=runner,
        )
        stream.run_forever(stop_event=StopEvent())

        self.assertEqual(len(updates), 1)
        self.assertEqual(updates[0].open_price, Decimal("101"))


if __name__ == "__main__":
    unittest.main()
