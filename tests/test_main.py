import os
import sys
import unittest
import logging
import subprocess
from datetime import datetime, timezone
from decimal import Decimal
from io import StringIO
from pathlib import Path
from contextlib import redirect_stdout
from tempfile import TemporaryDirectory
from urllib.error import HTTPError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class MainTests(unittest.TestCase):
    def test_build_runtime_from_snapshot_dicts(self) -> None:
        from momentum_alpha.main import build_runtime_from_snapshots

        runtime = build_runtime_from_snapshots(
            snapshots=[
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("60000"),
                    "latest_price": Decimal("61000"),
                    "previous_hour_low": Decimal("60500"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                }
            ]
        )
        self.assertIn("BTCUSDT", runtime.market)

    def test_load_credentials_reads_environment(self) -> None:
        from momentum_alpha.main import load_credentials_from_env

        old_key = os.environ.get("BINANCE_API_KEY")
        old_secret = os.environ.get("BINANCE_API_SECRET")
        try:
            os.environ["BINANCE_API_KEY"] = "key"
            os.environ["BINANCE_API_SECRET"] = "secret"
            creds = load_credentials_from_env()
            self.assertEqual(creds, ("key", "secret"))
        finally:
            if old_key is None:
                os.environ.pop("BINANCE_API_KEY", None)
            else:
                os.environ["BINANCE_API_KEY"] = old_key
            if old_secret is None:
                os.environ.pop("BINANCE_API_SECRET", None)
            else:
                os.environ["BINANCE_API_SECRET"] = old_secret

    def test_load_runtime_settings_reads_testnet_flag(self) -> None:
        from momentum_alpha.main import load_runtime_settings_from_env

        old_value = os.environ.get("BINANCE_USE_TESTNET")
        try:
            os.environ["BINANCE_USE_TESTNET"] = "1"
            settings = load_runtime_settings_from_env()
            self.assertEqual(settings["use_testnet"], True)
        finally:
            if old_value is None:
                os.environ.pop("BINANCE_USE_TESTNET", None)
            else:
                os.environ["BINANCE_USE_TESTNET"] = old_value

    def test_run_once_builds_preview_without_submitting_orders(self) -> None:
        from momentum_alpha.main import run_once

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

        class FakeBroker:
            def __init__(self) -> None:
                self.plans = []

            def submit_execution_plan(self, plan):
                self.plans.append(plan)
                return [{"status": "NEW"}]

        snapshots = [
            {
                "symbol": "BTCUSDT",
                "daily_open_price": Decimal("60000"),
                "latest_price": Decimal("61200"),
                "previous_hour_low": Decimal("61000"),
                "tradable": True,
                "has_previous_hour_candle": True,
            },
            {
                "symbol": "ETHUSDT",
                "daily_open_price": Decimal("3000"),
                "latest_price": Decimal("3010"),
                "previous_hour_low": Decimal("2990"),
                "tradable": True,
                "has_previous_hour_candle": True,
            },
        ]

        broker = FakeBroker()
        result = run_once(
            snapshots=snapshots,
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol="ETHUSDT",
            client=FakeClient(),
            broker=broker,
            submit_orders=False,
        )
        self.assertEqual(result.execution_plan.entry_orders[0]["symbol"], "BTCUSDT")
        self.assertEqual(broker.plans, [])

    def test_run_once_can_submit_orders(self) -> None:
        from momentum_alpha.main import run_once

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

        class FakeBroker:
            def __init__(self) -> None:
                self.plans = []

            def submit_execution_plan(self, plan):
                self.plans.append(plan)
                return [{"status": "NEW", "type": "MARKET"}, {"status": "NEW", "type": "STOP_MARKET"}]

        result = run_once(
            snapshots=[
                {
                    "symbol": "BTCUSDT",
                    "daily_open_price": Decimal("60000"),
                    "latest_price": Decimal("61200"),
                    "previous_hour_low": Decimal("61000"),
                    "tradable": True,
                    "has_previous_hour_candle": True,
                }
            ],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=True,
        )
        self.assertEqual(len(result.broker_responses), 2)
        self.assertEqual(result.broker_responses[0]["type"], "MARKET")

    def test_run_once_live_builds_snapshots_from_client_data(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "ETHUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                prices = {"BTCUSDT": {"symbol": "BTCUSDT", "price": "61200"}, "ETHUSDT": {"symbol": "ETHUSDT", "price": "3010"}}
                return prices[symbol]

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    opens = {
                        "BTCUSDT": [[0, "60000", "0", "0", "0"]],
                        "ETHUSDT": [[0, "3000", "0", "0", "0"]],
                    }
                    return opens[symbol]
                lows = {
                    "BTCUSDT": [[0, "0", "0", "61000", "0"]],
                    "ETHUSDT": [[0, "0", "0", "2990", "0"]],
                }
                return lows[symbol]

        class FakeBroker:
            def __init__(self) -> None:
                self.plans = []

            def submit_execution_plan(self, plan):
                self.plans.append(plan)
                return [{"status": "NEW"} for _ in range(len(plan.entry_orders) + len(plan.stop_orders))]

        result = run_once_live(
            symbols=["BTCUSDT", "ETHUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol="ETHUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.execution_plan.entry_orders[0]["symbol"], "BTCUSDT")
        self.assertEqual(result.runtime_result.decision.base_entries[0].symbol, "BTCUSDT")

    def test_run_once_live_uses_utc_midnight_minute_as_daily_open_source(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def __init__(self) -> None:
                self.kline_calls = []

            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

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
                if interval == "1m":
                    return [[1744675200000, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        client = FakeClient()
        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=client,
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].symbol, "BTCUSDT")
        minute_call = client.kline_calls[0]
        self.assertEqual(minute_call["interval"], "1m")
        self.assertEqual(minute_call["start_time_ms"], 1776211200000)
        self.assertEqual(minute_call["end_time_ms"], 1776211259999)

    def test_run_once_live_uses_previous_closed_hour_as_stop_source(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def __init__(self) -> None:
                self.kline_calls = []

            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

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
                if interval == "1m":
                    return [[1776211200000, "60000", "0", "0", "0"]]
                return [[1776211200000, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        client = FakeClient()
        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=client,
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].stop_price, Decimal("61000"))
        hour_call = client.kline_calls[1]
        self.assertEqual(hour_call["interval"], "1h")
        self.assertEqual(hour_call["start_time_ms"], 1776211200000)
        self.assertEqual(hour_call["end_time_ms"], 1776214799999)

    def test_run_once_live_skips_base_entry_without_previous_closed_hour(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    return [[1776211200000, "60000", "0", "0", "0"]]
                return []

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries, [])
        self.assertEqual(result.execution_plan.entry_orders, [])

    def test_run_once_live_falls_back_to_first_available_daily_minute_for_new_listing(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def __init__(self) -> None:
                self.kline_calls = []

            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "NEWUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "112"}

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
                if interval == "1m" and end_time_ms == 1776211259999:
                    return []
                if interval == "1m":
                    return [[1776213000000, "100", "0", "0", "0"]]
                return [[1776211200000, "0", "0", "105", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        client = FakeClient()
        result = run_once_live(
            symbols=["NEWUSDT"],
            now=datetime(2026, 4, 15, 1, 30, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=client,
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].symbol, "NEWUSDT")
        first_minute_call = client.kline_calls[0]
        fallback_call = client.kline_calls[1]
        self.assertEqual(first_minute_call["start_time_ms"], 1776211200000)
        self.assertEqual(first_minute_call["end_time_ms"], 1776211259999)
        self.assertEqual(fallback_call["start_time_ms"], 1776211200000)
        self.assertEqual(fallback_call["end_time_ms"], 1776216600000)

    def test_run_once_live_skips_symbol_when_daily_open_candle_is_unavailable(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "MISSUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                prices = {
                    "BTCUSDT": {"symbol": "BTCUSDT", "price": "61200"},
                    "MISSUSDT": {"symbol": "MISSUSDT", "price": "200"},
                }
                return prices[symbol]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if symbol == "MISSUSDT" and interval == "1m":
                    return []
                if interval == "1m":
                    return [[1776211200000, "60000", "0", "0", "0"]]
                lows = {
                    "BTCUSDT": [[1776211200000, "0", "0", "61000", "0"]],
                    "MISSUSDT": [[1776211200000, "0", "0", "190", "0"]],
                }
                return lows[symbol]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT", "MISSUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol="ETHUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].symbol, "BTCUSDT")
        self.assertEqual(len(result.execution_plan.entry_orders), 1)

    def test_run_once_live_skips_symbol_when_ticker_price_is_unusable(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "BADUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                prices = {
                    "BTCUSDT": {"symbol": "BTCUSDT", "price": "61200"},
                    "BADUSDT": {"symbol": "BADUSDT", "price": "NaN?"},
                }
                return prices[symbol]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    opens = {
                        "BTCUSDT": [[1776211200000, "60000", "0", "0", "0"]],
                        "BADUSDT": [[1776211200000, "100", "0", "0", "0"]],
                    }
                    return opens[symbol]
                lows = {
                    "BTCUSDT": [[1776211200000, "0", "0", "61000", "0"]],
                    "BADUSDT": [[1776211200000, "0", "0", "95", "0"]],
                }
                return lows[symbol]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT", "BADUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol="ETHUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].symbol, "BTCUSDT")
        self.assertEqual(len(result.execution_plan.entry_orders), 1)

    def test_run_once_live_uses_current_hour_low_stop_when_price_is_below_previous_hour_low(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "ETHUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "108"}

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    return [[1776211200000, "100", "0", "0", "0"]]
                if start_time_ms == 1776211200000 and end_time_ms == 1776214799999:
                    return [[1776211200000, "0", "0", "110", "0"]]
                return [[1776214800000, "0", "0", "106", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["ETHUSDT"],
            now=datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc),
            previous_leader_symbol="BTCUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(result.runtime_result.decision.base_entries[0].stop_price, Decimal("106"))

    def test_cli_main_outputs_preview_summary(self) -> None:
        from momentum_alpha.main import cli_main

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return [{"status": "NEW"}]

        out = StringIO()
        with redirect_stdout(out):
            exit_code = cli_main(
                argv=["run-once-live", "--symbols", "BTCUSDT", "--previous-leader", "ETHUSDT"],
                client_factory=lambda: FakeClient(),
                broker_factory=lambda client: FakeBroker(),
                now_provider=lambda: datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("mode=DRY_RUN", out.getvalue())
        self.assertIn("BTCUSDT", out.getvalue())

    def test_run_once_live_can_persist_previous_leader(self) -> None:
        from momentum_alpha.main import run_once_live
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState
        from momentum_alpha.models import Position, PositionLeg

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol=None,
                    positions={
                        "ETHUSDT": Position(
                            symbol="ETHUSDT",
                            stop_price=Decimal("106"),
                            legs=(
                                PositionLeg(
                                    "ETHUSDT",
                                    Decimal("2"),
                                    Decimal("108"),
                                    Decimal("106"),
                                    datetime(2026, 4, 15, 1, 5, tzinfo=timezone.utc),
                                    "stream_fill",
                                ),
                            ),
                        )
                    },
                )
            )
            result = run_once_live(
                symbols=["BTCUSDT"],
                now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                previous_leader_symbol=None,
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=False,
                state_store=store,
            )
            stored = store.load()
            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")
            self.assertEqual(stored.previous_leader_symbol, "BTCUSDT")
            self.assertIn("ETHUSDT", stored.positions)

    def test_run_once_live_uses_previous_leader_from_state_store_when_not_provided(self) -> None:
        from momentum_alpha.main import run_once_live
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT"))
            result = run_once_live(
                symbols=["BTCUSDT"],
                now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                previous_leader_symbol=None,
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=False,
                state_store=store,
            )
            self.assertEqual(result.execution_plan.entry_orders, [])
            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")

    def test_cli_main_can_use_state_file_for_previous_leader(self) -> None:
        from momentum_alpha.main import cli_main
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            state_path = Path(tmpdir) / "state.json"
            FileStateStore(path=state_path).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )
            out = StringIO()
            with redirect_stdout(out):
                exit_code = cli_main(
                    argv=["run-once-live", "--symbols", "BTCUSDT", "--state-file", str(state_path)],
                    client_factory=lambda: FakeClient(),
                    broker_factory=lambda client: FakeBroker(),
                    now_provider=lambda: datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                )
            self.assertEqual(exit_code, 0)
            self.assertIn("entry_orders=[]", out.getvalue())

    def test_cli_main_supports_poll_command(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        def fake_run_forever(**kwargs):
            calls.append(kwargs)
            return 0

        exit_code = cli_main(
            argv=["poll", "--symbols", "BTCUSDT", "--state-file", "/tmp/state.json"],
            run_forever_fn=fake_run_forever,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["symbols"], ["BTCUSDT"])

    def test_cli_main_run_once_live_passes_testnet_to_client_factory(self) -> None:
        from momentum_alpha.main import cli_main

        client_calls = []

        class FakeClient:
            def fetch_exchange_info(self):
                return {"symbols": []}

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "1"}

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                return [[0, "1", "1", "1", "1"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        def fake_client_factory(*, testnet):
            client_calls.append(testnet)
            return FakeClient()

        exit_code = cli_main(
            argv=["run-once-live", "--symbols", "BTCUSDT", "--testnet"],
            client_factory=fake_client_factory,
            broker_factory=lambda client: FakeBroker(),
            now_provider=lambda: datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(client_calls, [True])

    def test_cli_main_supports_user_stream_command(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        class FakeClient:
            pass

        def fake_client_factory(*, testnet):
            calls.append(("client", testnet))
            return FakeClient()

        def fake_run_user_stream(*, client, testnet, logger):
            calls.append(("stream", testnet, client.__class__.__name__))
            logger("user-stream-started")
            return 0

        out = StringIO()
        with redirect_stdout(out):
            exit_code = cli_main(
                argv=["user-stream", "--testnet"],
                client_factory=fake_client_factory,
                run_user_stream_fn=fake_run_user_stream,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0], ("client", True))
        self.assertEqual(calls[1], ("stream", True, "FakeClient"))
        self.assertIn("user-stream-started", out.getvalue())

    def test_module_main_invokes_cli_entrypoint(self) -> None:
        result = subprocess.run(
            [sys.executable, "-m", "momentum_alpha.main", "--help"],
            cwd=ROOT,
            env={**os.environ, "PYTHONPATH": str(SRC)},
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0)
        self.assertIn("usage:", result.stdout)

    def test_run_user_stream_persists_updated_state(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215100000,
                            "o": {
                                "s": "ETHUSDT",
                                "S": "BUY",
                                "X": "FILLED",
                                "x": "TRADE",
                                "ot": "MARKET",
                                "ap": "108",
                                "z": "2",
                                "sp": "106",
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertIn("ETHUSDT", loaded.positions)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))

    def test_run_user_stream_prewarms_state_from_rest_before_receiving_events(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore

        class FakeClient:
            def __init__(self) -> None:
                self.position_risk_calls = 0
                self.open_orders_calls = 0

            def fetch_position_risk(self):
                self.position_risk_calls += 1
                return [
                    {
                        "symbol": "ETHUSDT",
                        "positionAmt": "2",
                        "entryPrice": "108",
                        "updateTime": 1776215100000,
                    }
                ]

            def fetch_open_orders(self):
                self.open_orders_calls += 1
                return [
                    {
                        "symbol": "ETHUSDT",
                        "orderId": 123,
                        "type": "STOP_MARKET",
                        "side": "SELL",
                        "status": "NEW",
                        "stopPrice": "106",
                    }
                ]

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                return "abc"

        with TemporaryDirectory() as tmpdir:
            client = FakeClient()
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=client,
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))
            self.assertEqual(loaded.order_statuses["123"]["status"], "NEW")
            self.assertEqual(loaded.order_statuses["123"]["stop_price"], "106")
            self.assertEqual(client.position_risk_calls, 1)
            self.assertEqual(client.open_orders_calls, 1)

    def test_run_user_stream_reconnects_after_stream_failure_and_reprewarms_state(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore

        class FakeClient:
            def __init__(self) -> None:
                self.position_risk_calls = 0
                self.open_orders_calls = 0

            def fetch_position_risk(self):
                self.position_risk_calls += 1
                return [
                    {
                        "symbol": "ETHUSDT",
                        "positionAmt": "2",
                        "entryPrice": "108",
                        "updateTime": 1776215100000,
                    }
                ]

            def fetch_open_orders(self):
                self.open_orders_calls += 1
                return [
                    {
                        "symbol": "ETHUSDT",
                        "orderId": 123,
                        "type": "STOP_MARKET",
                        "side": "SELL",
                        "status": "NEW",
                        "stopPrice": "106",
                    }
                ]

        class FakeStreamClient:
            attempts = 0

            def run_forever(self, *, on_event):
                FakeStreamClient.attempts += 1
                if FakeStreamClient.attempts == 1:
                    raise RuntimeError("socket closed")
                return "abc"

        with TemporaryDirectory() as tmpdir:
            client = FakeClient()
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            logs = []
            sleep_calls = []
            exit_code = run_user_stream(
                client=client,
                testnet=True,
                logger=lambda message: logs.append(message),
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
                reconnect_sleep_fn=lambda seconds: sleep_calls.append(seconds),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(FakeStreamClient.attempts, 2)
            self.assertEqual(client.position_risk_calls, 2)
            self.assertEqual(client.open_orders_calls, 2)
            self.assertEqual(sleep_calls, [1])
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))
            self.assertTrue(any("stream-error attempt=1" in message for message in logs))

    def test_run_user_stream_persists_order_status_updates(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215100000,
                            "o": {
                                "s": "ETHUSDT",
                                "i": 123,
                                "S": "SELL",
                                "X": "NEW",
                                "x": "NEW",
                                "ot": "STOP_MARKET",
                                "sp": "106",
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.order_statuses["123"]["symbol"], "ETHUSDT")
            self.assertEqual(loaded.order_statuses["123"]["status"], "NEW")
            self.assertEqual(loaded.order_statuses["123"]["original_order_type"], "STOP_MARKET")

    def test_run_user_stream_skips_duplicate_trade_event(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        event_payload = {
            "e": "ORDER_TRADE_UPDATE",
            "T": 1776215100000,
            "o": {
                "s": "ETHUSDT",
                "S": "BUY",
                "X": "FILLED",
                "x": "TRADE",
                "ot": "MARKET",
                "ap": "108",
                "z": "2",
                "sp": "106",
                "i": 123,
                "t": 456,
            },
        }

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                event = parse_user_stream_event(event_payload)
                on_event(event)
                on_event(event)
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.processed_event_ids, ["ORDER_TRADE_UPDATE:123:trade:456"])

    def test_run_user_stream_applies_non_trade_order_status_transitions_with_same_order_id(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215100000,
                            "o": {
                                "s": "ETHUSDT",
                                "i": 123,
                                "S": "SELL",
                                "X": "NEW",
                                "x": "NEW",
                                "ot": "STOP_MARKET",
                            },
                        }
                    )
                )
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215160000,
                            "o": {
                                "s": "ETHUSDT",
                                "i": 123,
                                "S": "SELL",
                                "X": "CANCELED",
                                "x": "CANCELED",
                                "ot": "STOP_MARKET",
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.order_statuses["123"]["status"], "CANCELED")
            self.assertEqual(len(loaded.processed_event_ids), 2)

    def test_run_user_stream_account_update_can_clear_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215100000,
                            "o": {
                                "s": "ETHUSDT",
                                "i": 123,
                                "S": "BUY",
                                "X": "FILLED",
                                "x": "TRADE",
                                "ot": "MARKET",
                                "ap": "108",
                                "z": "2",
                                "sp": "106",
                                "t": 456,
                            },
                        }
                    )
                )
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776215220000,
                            "a": {
                                "m": "ORDER",
                                "P": [
                                    {
                                        "s": "ETHUSDT",
                                        "pa": "0",
                                        "ep": "0",
                                    }
                                ],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertNotIn("ETHUSDT", loaded.positions)

    def test_run_user_stream_account_update_can_restore_missing_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776215220000,
                            "a": {
                                "m": "ORDER",
                                "P": [
                                    {
                                        "s": "ETHUSDT",
                                        "pa": "2",
                                        "ep": "108",
                                    }
                                ],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("0"))

    def test_run_user_stream_account_update_can_sync_existing_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776215280000,
                            "a": {
                                "m": "ORDER",
                                "P": [
                                    {
                                        "s": "ETHUSDT",
                                        "pa": "3",
                                        "ep": "109",
                                    }
                                ],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="ETHUSDT",
                    positions={
                        "ETHUSDT": Position(
                            symbol="ETHUSDT",
                            stop_price=Decimal("106"),
                            legs=(
                                PositionLeg(
                                    "ETHUSDT",
                                    Decimal("2"),
                                    Decimal("108"),
                                    Decimal("106"),
                                    datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                                    "base",
                                ),
                            ),
                        )
                    },
                )
            )
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("3"))
            self.assertEqual(loaded.positions["ETHUSDT"].legs[0].entry_price, Decimal("109"))
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))

    def test_run_user_stream_account_update_can_restore_stop_price_from_order_statuses(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776215220000,
                            "a": {
                                "m": "ORDER",
                                "P": [
                                    {
                                        "s": "ETHUSDT",
                                        "pa": "2",
                                        "ep": "108",
                                    }
                                ],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    order_statuses={
                        "123": {
                            "symbol": "ETHUSDT",
                            "status": "NEW",
                            "side": "SELL",
                            "original_order_type": "STOP_MARKET",
                            "stop_price": "106",
                        }
                    },
                )
            )
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))
            self.assertEqual(loaded.positions["ETHUSDT"].legs[0].stop_price, Decimal("106"))

    def test_run_user_stream_account_update_ignores_canceled_stop_and_uses_active_one(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776215220000,
                            "a": {
                                "m": "ORDER",
                                "P": [
                                    {
                                        "s": "ETHUSDT",
                                        "pa": "2",
                                        "ep": "108",
                                    }
                                ],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="BTCUSDT",
                    order_statuses={
                        "123": {
                            "symbol": "ETHUSDT",
                            "status": "CANCELED",
                            "side": "SELL",
                            "original_order_type": "STOP_MARKET",
                            "stop_price": "106",
                        },
                        "124": {
                            "symbol": "ETHUSDT",
                            "status": "NEW",
                            "side": "SELL",
                            "original_order_type": "STOP_MARKET",
                            "stop_price": "107",
                        },
                    },
                )
            )
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("107"))

    def test_run_user_stream_removes_filled_stop_order_from_order_statuses(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.state_store import FileStateStore, StoredStrategyState
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ORDER_TRADE_UPDATE",
                            "T": 1776215160000,
                            "o": {
                                "s": "ETHUSDT",
                                "i": 123,
                                "S": "SELL",
                                "X": "FILLED",
                                "x": "TRADE",
                                "ot": "STOP_MARKET",
                                "ap": "106",
                                "z": "2",
                                "sp": "106",
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            store = FileStateStore(path=Path(tmpdir) / "state.json")
            store.save(
                StoredStrategyState(
                    current_day="2026-04-15",
                    previous_leader_symbol="ETHUSDT",
                    order_statuses={
                        "123": {
                            "symbol": "ETHUSDT",
                            "status": "NEW",
                            "side": "SELL",
                            "original_order_type": "STOP_MARKET",
                            "stop_price": "106",
                        }
                    },
                )
            )
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertNotIn("123", loaded.order_statuses)

    def test_cli_main_poll_prints_startup_summary(self) -> None:
        from momentum_alpha.main import cli_main

        out = StringIO()

        def fake_run_forever(**kwargs):
            return 0

        with redirect_stdout(out):
            exit_code = cli_main(
                argv=[
                    "poll",
                    "--symbols",
                    "BTCUSDT",
                    "ETHUSDT",
                    "--state-file",
                    "/tmp/state.json",
                    "--restore-positions",
                ],
                run_forever_fn=fake_run_forever,
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("starting poll", out.getvalue())
        self.assertIn("restore_positions=True", out.getvalue())

    def test_cli_main_submit_orders_reports_live_mode(self) -> None:
        from momentum_alpha.main import cli_main

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return [{"status": "NEW"} for _ in range(len(plan.entry_orders) + len(plan.stop_orders))]

        out = StringIO()
        with redirect_stdout(out):
            exit_code = cli_main(
                argv=["run-once-live", "--symbols", "BTCUSDT", "--submit-orders"],
                client_factory=lambda: FakeClient(),
                broker_factory=lambda client: FakeBroker(),
                now_provider=lambda: datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            )
        self.assertEqual(exit_code, 0)
        self.assertIn("mode=LIVE", out.getvalue())

    def test_cli_main_poll_passes_runtime_flags(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        def fake_run_forever(**kwargs):
            calls.append(kwargs)
            return 0

        exit_code = cli_main(
            argv=[
                "poll",
                "--symbols",
                "BTCUSDT",
                "--state-file",
                "/tmp/state.json",
                "--restore-positions",
                "--execute-stop-replacements",
                "--submit-orders",
                "--max-ticks",
                "5",
            ],
            run_forever_fn=fake_run_forever,
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(calls[0]["restore_positions"])
        self.assertTrue(calls[0]["execute_stop_replacements"])
        self.assertTrue(calls[0]["submit_orders"])
        self.assertEqual(calls[0]["max_ticks"], 5)

    def test_run_forever_passes_flags_to_run_once_live(self) -> None:
        from momentum_alpha.main import run_forever

        recorded = []

        def fake_run_once_live(**kwargs):
            recorded.append(kwargs)

        times = iter([datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc)])
        exit_code = run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=True,
            state_store=None,
            client_factory=lambda: object(),
            broker_factory=lambda client: object(),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            logger=lambda message: None,
            max_ticks=1,
            run_once_live_fn=fake_run_once_live,
            restore_positions=True,
            execute_stop_replacements=True,
        )
        self.assertEqual(exit_code, 0)
        self.assertTrue(recorded[0]["submit_orders"])
        self.assertTrue(recorded[0]["restore_positions"])
        self.assertTrue(recorded[0]["execute_stop_replacements"])

    def test_run_forever_discovers_all_usdt_perpetual_symbols_when_symbols_missing(self) -> None:
        from momentum_alpha.main import run_forever

        recorded = []

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                            ],
                        },
                        {
                            "symbol": "ETHUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                            ],
                        },
                        {
                            "symbol": "BTCUSD_PERP",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USD",
                            "status": "TRADING",
                            "filters": [],
                        },
                    ]
                }

        def fake_run_once_live(**kwargs):
            recorded.append(kwargs)

        times = iter([datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc)])
        exit_code = run_forever(
            symbols=[],
            previous_leader_symbol=None,
            submit_orders=False,
            state_store=None,
            client_factory=lambda: FakeClient(),
            broker_factory=lambda client: object(),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            logger=lambda message: None,
            max_ticks=1,
            run_once_live_fn=fake_run_once_live,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(recorded[0]["symbols"], ["BTCUSDT", "ETHUSDT"])

    def test_run_forever_applies_rate_limit_backoff_after_http_429(self) -> None:
        from momentum_alpha.main import run_forever

        calls = []
        logs = []

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                            ],
                        }
                    ]
                }

        def fake_run_once_live(**kwargs):
            calls.append(kwargs)
            if len(calls) == 1:
                raise HTTPError(
                    url="https://fapi.binance.com/fapi/v1/ticker/price",
                    code=429,
                    msg="Too Many Requests",
                    hdrs=None,
                    fp=None,
                )

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 3, 0, tzinfo=timezone.utc),
            ]
        )
        exit_code = run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=True,
            state_store=None,
            client_factory=lambda: FakeClient(),
            broker_factory=lambda client: object(),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            logger=lambda message: logs.append(message),
            max_ticks=3,
            run_once_live_fn=fake_run_once_live,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(len(calls), 2)
        self.assertTrue(any("rate-limit-backoff" in message for message in logs))

    def test_run_forever_logs_and_uses_sleep_function(self) -> None:
        from momentum_alpha.main import run_forever
        from momentum_alpha.state_store import FileStateStore

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 1, 30, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
            ]
        )
        sleeps = []
        logs = []

        with TemporaryDirectory() as tmpdir:
            exit_code = run_forever(
                symbols=["BTCUSDT"],
                previous_leader_symbol=None,
                submit_orders=False,
                state_store=FileStateStore(path=Path(tmpdir) / "state.json"),
                client_factory=lambda: FakeClient(),
                broker_factory=lambda client: FakeBroker(),
                now_provider=lambda: next(times),
                sleep_fn=lambda seconds: sleeps.append(seconds),
                logger=lambda message: logs.append(message),
                max_ticks=3,
            )
        self.assertEqual(exit_code, 0)
        self.assertEqual(sleeps, [1, 1, 1])
        self.assertTrue(any("tick" in message for message in logs))

    def test_run_forever_logs_exceptions_and_continues(self) -> None:
        from momentum_alpha.main import run_forever

        class FakeClient:
            pass

        class FakeBroker:
            pass

        times = iter(
            [
                datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc),
                datetime(2026, 4, 15, 1, 2, 0, tzinfo=timezone.utc),
            ]
        )
        logs = []
        calls = {"count": 0}

        def fake_runner(**kwargs):
            calls["count"] += 1
            if calls["count"] == 1:
                raise RuntimeError("broken")
            return None

        exit_code = run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=False,
            state_store=None,
            client_factory=lambda: FakeClient(),
            broker_factory=lambda client: FakeBroker(),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            logger=lambda message: logs.append(message),
            max_ticks=2,
            run_once_live_fn=fake_runner,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls["count"], 2)
        self.assertTrue(any("broken" in message for message in logs))

    def test_run_forever_accepts_logging_logger(self) -> None:
        from momentum_alpha.main import run_forever

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        logger = logging.getLogger("momentum_alpha_test")
        stream = StringIO()
        handler = logging.StreamHandler(stream)
        logger.handlers = [handler]
        logger.setLevel(logging.INFO)
        logger.propagate = False

        times = iter([datetime(2026, 4, 15, 1, 1, 0, tzinfo=timezone.utc)])
        exit_code = run_forever(
            symbols=["BTCUSDT"],
            previous_leader_symbol=None,
            submit_orders=False,
            state_store=None,
            client_factory=lambda: FakeClient(),
            broker_factory=lambda client: FakeBroker(),
            now_provider=lambda: next(times),
            sleep_fn=lambda seconds: None,
            logger=logger,
            max_ticks=1,
        )
        self.assertEqual(exit_code, 0)
        self.assertIn("tick", stream.getvalue())

    def test_run_once_live_restores_existing_position_state(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": "0.010",
                        "entryPrice": "61100",
                        "updateTime": 1700000000000,
                    }
                ]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "type": "STOP_MARKET",
                        "stopPrice": "60900",
                    }
                ]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
            restore_positions=True,
        )
        self.assertIn("BTCUSDT", result.runtime_result.next_state.positions)
        self.assertEqual(result.runtime_result.next_state.positions["BTCUSDT"].stop_price, Decimal("60900"))

    def test_run_once_live_discovers_all_usdt_perpetual_symbols_when_symbols_missing(self) -> None:
        from momentum_alpha.main import run_once_live

        seen_symbols = []

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "ETHUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "BNBUSD_PERP",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USD",
                            "status": "TRADING",
                            "filters": [],
                        },
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                seen_symbols.append(symbol)
                prices = {
                    "BTCUSDT": {"symbol": "BTCUSDT", "price": "61200"},
                    "ETHUSDT": {"symbol": "ETHUSDT", "price": "3020"},
                }
                return prices[symbol]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    opens = {"BTCUSDT": "60000", "ETHUSDT": "3000"}
                    return [[0, opens[symbol], "0", "0", "0"]]
                lows = {"BTCUSDT": "61000", "ETHUSDT": "2990"}
                return [[0, "0", "0", lows[symbol], "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=[],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol=None,
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
        )
        self.assertEqual(seen_symbols, ["BTCUSDT", "ETHUSDT"])

    def test_run_once_live_uses_restored_positions_to_avoid_duplicate_base_entry(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                        {
                            "symbol": "ETHUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.01"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                prices = {"BTCUSDT": {"symbol": "BTCUSDT", "price": "61200"}, "ETHUSDT": {"symbol": "ETHUSDT", "price": "3010"}}
                return prices[symbol]

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    opens = {
                        "BTCUSDT": [[0, "60000", "0", "0", "0"]],
                        "ETHUSDT": [[0, "3000", "0", "0", "0"]],
                    }
                    return opens[symbol]
                lows = {
                    "BTCUSDT": [[0, "0", "0", "61000", "0"]],
                    "ETHUSDT": [[0, "0", "0", "2990", "0"]],
                }
                return lows[symbol]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": "0.010",
                        "entryPrice": "61100",
                        "updateTime": 1700000000000,
                    }
                ]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "type": "STOP_MARKET",
                        "stopPrice": "60900",
                    }
                ]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT", "ETHUSDT"],
            now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
            previous_leader_symbol="ETHUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
            restore_positions=True,
        )
        self.assertEqual(result.execution_plan.entry_orders, [])
        self.assertIn("BTCUSDT", result.runtime_result.next_state.positions)

    def test_run_once_live_reports_stop_replacements_from_restored_state(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "positionAmt": "0.010",
                        "entryPrice": "61100",
                        "updateTime": 1700000000000,
                    }
                ]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "type": "STOP_MARKET",
                        "stopPrice": "60900",
                    }
                ]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 2, 0, tzinfo=timezone.utc),
            previous_leader_symbol="BTCUSDT",
            client=FakeClient(),
            broker=FakeBroker(),
            submit_orders=False,
            restore_positions=True,
        )
        self.assertEqual(result.stop_replacements, [("BTCUSDT", Decimal("61000"))])

    def test_run_once_live_can_execute_stop_replacements(self) -> None:
        from momentum_alpha.main import run_once_live

        class FakeClient:
            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "status": "TRADING",
                            "filters": [
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_ticker_price(self, *, symbol):
                return {"symbol": symbol, "price": "61200"}

            def fetch_klines(self, *, symbol, interval, limit):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "positionAmt": "0.010", "entryPrice": "61100", "updateTime": 1700000000000}]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "type": "STOP_MARKET", "stopPrice": "60900"}]

        class FakeBroker:
            def __init__(self) -> None:
                self.replacements = []

            def submit_execution_plan(self, plan):
                return []

            def replace_stop_orders(self, *, replacements):
                self.replacements.append(replacements)
                return [{"status": "NEW", "type": "STOP_MARKET"}]

        broker = FakeBroker()
        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 2, 0, tzinfo=timezone.utc),
            previous_leader_symbol="BTCUSDT",
            client=FakeClient(),
            broker=broker,
            submit_orders=False,
            restore_positions=True,
            execute_stop_replacements=True,
        )
        self.assertEqual(result.stop_replacements, [("BTCUSDT", Decimal("61000"))])
        self.assertEqual(broker.replacements[0], [("BTCUSDT", "0.010", "61000")])
