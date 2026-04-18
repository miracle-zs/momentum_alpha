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
from unittest.mock import patch
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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

    def test_run_once_live_persists_structured_runtime_records(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import run_once_live
        from momentum_alpha.runtime_store import (
            RuntimeStateStore,
            fetch_recent_account_snapshots,
            fetch_recent_broker_orders,
            fetch_recent_position_snapshots,
            fetch_recent_signal_decisions,
        )
        from momentum_alpha.runtime_store import RuntimeStateStore

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

            def fetch_ticker_prices(self):
                return [{"symbol": "BTCUSDT", "price": "61200"}]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_account_info(self, *, timestamp_ms=None):
                return {
                    "availableBalance": "1200.00",
                    "totalWalletBalance": "1234.56",
                    "totalMarginBalance": "1260.12",
                    "totalUnrealizedProfit": "25.56",
                }

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return [
                    {"symbol": "BTCUSDT", "status": "NEW", "type": "MARKET", "side": "BUY", "orderId": 101},
                    {"symbol": "BTCUSDT", "status": "NEW", "type": "STOP_MARKET", "side": "SELL", "orderId": 102},
                ]

            def replace_stop_orders(self, replacements):
                return []

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            result = run_once_live(
                symbols=["BTCUSDT"],
                now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                previous_leader_symbol="ETHUSDT",
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=True,
                runtime_state_store=RuntimeStateStore(path=runtime_db_path),
                audit_recorder=AuditRecorder(runtime_db_path=runtime_db_path, source="poll"),
            )

            signal_decisions = fetch_recent_signal_decisions(path=runtime_db_path, limit=10)
            broker_orders = fetch_recent_broker_orders(path=runtime_db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=10)
            account_snapshots = fetch_recent_account_snapshots(path=runtime_db_path, limit=10)

            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")
            self.assertEqual(signal_decisions[0]["decision_type"], "base_entry")
            self.assertEqual(signal_decisions[0]["symbol"], "BTCUSDT")
            self.assertEqual(signal_decisions[0]["next_leader_symbol"], "BTCUSDT")
            self.assertEqual(len(broker_orders), 2)
            self.assertEqual(broker_orders[0]["symbol"], "BTCUSDT")
            self.assertEqual(snapshots[0]["leader_symbol"], "BTCUSDT")
            self.assertEqual(account_snapshots[0]["wallet_balance"], "1234.56")
            self.assertEqual(account_snapshots[0]["available_balance"], "1200.00")
            self.assertEqual(account_snapshots[0]["equity"], "1260.12")
            self.assertEqual(account_snapshots[0]["open_order_count"], 0)
            mirrored_state = RuntimeStateStore(path=runtime_db_path).load()
            self.assertEqual(mirrored_state.previous_leader_symbol, "BTCUSDT")

    def test_run_once_live_records_blocked_reason_when_leader_switch_does_not_open_position(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import run_once_live
        from momentum_alpha.runtime_store import fetch_recent_position_snapshots, fetch_recent_signal_decisions

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
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MARKET_LOT_SIZE", "minQty": "0.001", "stepSize": "0.001"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        },
                    ]
                }

            def fetch_ticker_prices(self):
                return [
                    {"symbol": "BTCUSDT", "price": "61200"},
                    {"symbol": "ETHUSDT", "price": "60000"},
                ]

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                if symbol == "BTCUSDT":
                    return [[0, "0", "0", "62000", "0"]]
                return [[0, "0", "0", "59000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

            def replace_stop_orders(self, replacements):
                return []

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            result = run_once_live(
                symbols=["BTCUSDT", "ETHUSDT"],
                now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                previous_leader_symbol="ETHUSDT",
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=True,
                audit_recorder=AuditRecorder(runtime_db_path=runtime_db_path, source="poll"),
            )

            signal_decisions = fetch_recent_signal_decisions(path=runtime_db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=10)

            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")
            self.assertEqual(result.runtime_result.decision.base_entries, [])
            self.assertEqual(signal_decisions[0]["decision_type"], "no_action")
            self.assertEqual(signal_decisions[0]["payload"]["blocked_reason"], "invalid_stop_price")
            self.assertNotIn("positions", snapshots[0]["payload"])

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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
                if interval == "1m":
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
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
                runtime_state_store=store,
            )
            stored = store.load()
            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")
            self.assertEqual(stored.previous_leader_symbol, "BTCUSDT")
            self.assertIn("ETHUSDT", stored.positions)

    def test_run_once_live_uses_previous_leader_from_state_store_when_not_provided(self) -> None:
        from momentum_alpha.main import run_once_live
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState

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
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            store.save(StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT"))
            result = run_once_live(
                symbols=["BTCUSDT"],
                now=datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                previous_leader_symbol=None,
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=False,
                runtime_state_store=store,
            )
            self.assertEqual(result.execution_plan.entry_orders, [])
            self.assertEqual(result.runtime_result.next_state.previous_leader_symbol, "BTCUSDT")

    def test_cli_main_can_use_state_file_for_previous_leader(self) -> None:
        from momentum_alpha.main import cli_main
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState

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
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

        class FakeBroker:
            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            RuntimeStateStore(path=runtime_db_path).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )
            out = StringIO()
            with redirect_stdout(out):
                exit_code = cli_main(
                    argv=["run-once-live", "--symbols", "BTCUSDT", "--runtime-db-file", str(runtime_db_path)],
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
            argv=["poll", "--symbols", "BTCUSDT", "--runtime-db-file", "/tmp/runtime.db"],
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

        def fake_run_user_stream(**kwargs):
            calls.append(("stream", kwargs.get("testnet"), kwargs.get("client").__class__.__name__))
            kwargs.get("logger")("user-stream-started")
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

    def test_cli_main_supports_healthcheck_command(self) -> None:
        from momentum_alpha.main import cli_main
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState, insert_audit_event

        with TemporaryDirectory() as tmpdir:
            root = Path(tmpdir)
            poll_log = root / "momentum-alpha.log"
            user_stream_log = root / "momentum-alpha-user-stream.log"
            runtime_db = root / "runtime.db"
            for path in (poll_log, user_stream_log):
                path.write_text("x", encoding="utf-8")
            now = datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc)
            timestamp = now.timestamp()
            for path in (poll_log, user_stream_log):
                os.utime(path, (timestamp, timestamp))

            # Save strategy state to database
            RuntimeStateStore(path=runtime_db).save(
                StoredStrategyState(current_day="2026-04-15", previous_leader_symbol="BTCUSDT")
            )

            insert_audit_event(
                path=runtime_db,
                timestamp=now,
                event_type="poll_tick",
                payload={"symbol_count": 538},
                source="poll",
            )

            out = StringIO()
            with redirect_stdout(out):
                exit_code = cli_main(
                    argv=[
                        "healthcheck",
                        "--poll-log-file",
                        str(poll_log),
                        "--user-stream-log-file",
                        str(user_stream_log),
                        "--runtime-db-file",
                        str(runtime_db),
                    ],
                    now_provider=lambda: now,
                )
            self.assertEqual(exit_code, 0)
            self.assertIn("overall=OK", out.getvalue())

    def test_cli_main_supports_audit_report_command(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import cli_main

        with TemporaryDirectory() as tmpdir:
            db_path = Path(tmpdir) / "runtime.db"
            recorder = AuditRecorder(runtime_db_path=db_path, source="poll")
            recorder.record(
                event_type="tick_result",
                now=datetime(2026, 4, 15, 14, 0, tzinfo=timezone.utc),
                payload={"base_entry_symbols": ["BTCUSDT"]},
            )

            out = StringIO()
            with redirect_stdout(out):
                exit_code = cli_main(
                    argv=["audit-report", "--runtime-db-file", str(db_path), "--since-minutes", "60", "--limit", "5"],
                    now_provider=lambda: datetime(2026, 4, 15, 14, 30, tzinfo=timezone.utc),
                )
            self.assertEqual(exit_code, 0)
            self.assertIn("total_events=1", out.getvalue())
            self.assertIn("tick_result=1", out.getvalue())

    def test_cli_main_supports_dashboard_command(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        def fake_run_dashboard(**kwargs):
            calls.append(kwargs)
            return 0

        exit_code = cli_main(
            argv=[
                "dashboard",
                "--host",
                "127.0.0.1",
                "--port",
                "8080",
                "--poll-log-file",
                "/tmp/poll.log",
                "--user-stream-log-file",
                "/tmp/user-stream.log",
                "--runtime-db-file",
                "/tmp/runtime.db",
            ],
            run_dashboard_fn=fake_run_dashboard,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0]["host"], "127.0.0.1")
        self.assertEqual(calls[0]["port"], 8080)
        self.assertEqual(str(calls[0]["runtime_db_file"]), "/tmp/runtime.db")

    def test_backfill_account_flows_writes_transfer_income_rows(self) -> None:
        from momentum_alpha.main import backfill_account_flows
        from momentum_alpha.runtime_store import fetch_recent_account_flows

        class FakeClient:
            def fetch_income_history(self, **kwargs):
                self.kwargs = kwargs
                return [
                    {
                        "time": 1776207600000,
                        "asset": "USDT",
                        "incomeType": "TRANSFER",
                        "income": "300.00",
                        "info": "TRANSFER",
                        "tranId": "abc123",
                    }
                ]

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            inserted = backfill_account_flows(
                client=FakeClient(),
                runtime_db_path=runtime_db_path,
                start_time=datetime(2026, 4, 14, 23, 0, tzinfo=timezone.utc),
                end_time=datetime(2026, 4, 15, 1, 0, tzinfo=timezone.utc),
                logger=lambda _message: None,
            )
            flows = fetch_recent_account_flows(path=runtime_db_path, limit=10)

        self.assertEqual(inserted, 1)
        self.assertEqual(flows[0]["reason"], "TRANSFER")
        self.assertEqual(flows[0]["asset"], "USDT")
        self.assertEqual(flows[0]["balance_change"], "300.00")
        self.assertEqual(flows[0]["payload"]["tranId"], "abc123")

    def test_cli_main_supports_backfill_account_flows_command(self) -> None:
        from momentum_alpha.main import cli_main

        calls = []

        class FakeClient:
            pass

        def fake_client_factory(*, testnet):
            calls.append(("client", testnet))
            return FakeClient()

        def fake_backfill_account_flows(**kwargs):
            calls.append(kwargs)
            return 12

        exit_code = cli_main(
            argv=[
                "backfill-account-flows",
                "--runtime-db-file",
                "/tmp/runtime.db",
                "--start-time",
                "2026-04-15T00:00:00+00:00",
                "--end-time",
                "2026-04-16T00:00:00+00:00",
            ],
            client_factory=fake_client_factory,
            backfill_account_flows_fn=fake_backfill_account_flows,
        )
        self.assertEqual(exit_code, 0)
        self.assertEqual(calls[0], ("client", False))
        self.assertEqual(calls[1]["runtime_db_path"], Path("/tmp/runtime.db"))
        self.assertEqual(calls[1]["start_time"].isoformat(), "2026-04-15T00:00:00+00:00")
        self.assertEqual(calls[1]["end_time"].isoformat(), "2026-04-16T00:00:00+00:00")
        self.assertEqual(calls[1]["client"].__class__.__name__, "FakeClient")

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
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertIn("ETHUSDT", loaded.positions)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))

    def test_run_user_stream_writes_audit_events(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import (
            fetch_recent_audit_events,
            fetch_recent_broker_orders,
            fetch_recent_position_snapshots,
            fetch_recent_trade_fills,
        )
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
                                "L": "108.5",
                                "l": "0.75",
                                "rp": "3.25",
                                "n": "0.02",
                                "N": "USDT",
                                "sp": "106",
                                "i": 123,
                                "t": 456,
                                "c": "ma_foo",
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
                runtime_db_path=runtime_db_path,
            )
            db_events = fetch_recent_audit_events(path=runtime_db_path, limit=10)
            broker_orders = fetch_recent_broker_orders(path=runtime_db_path, limit=10)
            trade_fills = fetch_recent_trade_fills(path=runtime_db_path, limit=10)
            self.assertEqual(exit_code, 0)
            self.assertEqual(db_events[0]["event_type"], "user_stream_worker_start")
            self.assertEqual(db_events[0]["payload"]["testnet"], True)
            snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=10)
            self.assertNotIn("market_context", snapshots[0]["payload"])
            self.assertNotIn("positions", snapshots[0]["payload"])
            self.assertEqual(broker_orders[0]["symbol"], "ETHUSDT")
            self.assertEqual(broker_orders[0]["order_status"], "FILLED")
            self.assertEqual(trade_fills[0]["symbol"], "ETHUSDT")
            self.assertEqual(trade_fills[0]["trade_id"], "456")

    def test_run_user_stream_persists_account_flows_from_account_update(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import fetch_recent_account_flows
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776248675941,
                            "a": {
                                "m": "DEPOSIT",
                                "B": [
                                    {
                                        "a": "USDT",
                                        "wb": "953.04663933",
                                        "cw": "953.04663933",
                                        "bc": "500.00",
                                    }
                                ],
                                "P": [],
                            },
                        }
                    )
                )
                return "abc"

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=False,
                logger=lambda message: None,
                now_provider=lambda: datetime(2026, 4, 16, 15, 45, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
                runtime_db_path=runtime_db_path,
            )
            account_flows = fetch_recent_account_flows(path=runtime_db_path, limit=10)

        self.assertEqual(exit_code, 0)
        self.assertEqual(len(account_flows), 1)
        self.assertEqual(account_flows[0]["reason"], "DEPOSIT")
        self.assertEqual(account_flows[0]["asset"], "USDT")
        self.assertEqual(account_flows[0]["balance_change"], "500.00")

    def test_run_user_stream_logs_account_flow_insert_failures(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import fetch_recent_audit_events
        from momentum_alpha.user_stream import parse_user_stream_event

        class FakeClient:
            pass

        class FakeStreamClient:
            def run_forever(self, *, on_event):
                on_event(
                    parse_user_stream_event(
                        {
                            "e": "ACCOUNT_UPDATE",
                            "E": 1776248675941,
                            "a": {
                                "m": "DEPOSIT",
                                "B": [
                                    {
                                        "a": "USDT",
                                        "wb": "953.04663933",
                                        "cw": "953.04663933",
                                        "bc": "500.00",
                                    }
                                ],
                                "P": [],
                            },
                        }
                    )
                )
                return "abc"

        messages = []
        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            with patch("momentum_alpha.main.insert_account_flow", side_effect=RuntimeError("db write failed")):
                exit_code = run_user_stream(
                    client=FakeClient(),
                    testnet=False,
                    logger=lambda message: messages.append(message),
                    now_provider=lambda: datetime(2026, 4, 16, 15, 45, tzinfo=timezone.utc),
                    stream_client_factory=lambda **kwargs: FakeStreamClient(),
                    runtime_db_path=runtime_db_path,
                )
            events = fetch_recent_audit_events(path=runtime_db_path, limit=10)

        self.assertEqual(exit_code, 0)
        self.assertTrue(any("account-flow-insert-error" in message for message in messages))
        self.assertTrue(any(event["event_type"] == "account_flow_insert_error" for event in events))

    def test_run_user_stream_prewarms_state_from_rest_before_receiving_events(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore

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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=client,
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
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
        from momentum_alpha.runtime_store import RuntimeStateStore

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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            logs = []
            sleep_calls = []
            exit_code = run_user_stream(
                client=client,
                testnet=True,
                logger=lambda message: logs.append(message),
                runtime_state_store=store,
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
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
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
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.processed_event_ids, ["ORDER_TRADE_UPDATE:123:trade:456"])

    def test_run_user_stream_applies_non_trade_order_status_transitions_with_same_order_id(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.order_statuses["123"]["status"], "CANCELED")
            self.assertEqual(len(loaded.processed_event_ids), 2)

    def test_run_user_stream_account_update_can_clear_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertNotIn("ETHUSDT", loaded.positions)

    def test_run_user_stream_account_update_can_restore_missing_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
            exit_code = run_user_stream(
                client=FakeClient(),
                testnet=True,
                logger=lambda message: None,
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].total_quantity, Decimal("2"))
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("0"))

    def test_run_user_stream_account_update_can_sync_existing_local_position(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
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
                runtime_state_store=store,
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
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
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
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("106"))
            self.assertEqual(loaded.positions["ETHUSDT"].legs[0].stop_price, Decimal("106"))

    def test_run_user_stream_account_update_ignores_canceled_stop_and_uses_active_one(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
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
                runtime_state_store=store,
                now_provider=lambda: datetime(2026, 4, 15, 1, 10, tzinfo=timezone.utc),
                stream_client_factory=lambda **kwargs: FakeStreamClient(),
            )
            loaded = store.load()
            self.assertEqual(exit_code, 0)
            self.assertEqual(loaded.positions["ETHUSDT"].stop_price, Decimal("107"))

    def test_run_user_stream_removes_filled_stop_order_from_order_statuses(self) -> None:
        from momentum_alpha.main import run_user_stream
        from momentum_alpha.runtime_store import RuntimeStateStore, StoredStrategyState
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
            store = RuntimeStateStore(path=Path(tmpdir) / "runtime.db")
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
                runtime_state_store=store,
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
                    "--runtime-db-file",
                    "/tmp/runtime.db",
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
                "--runtime-db-file",
                "/tmp/runtime.db",
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
            runtime_state_store=None,
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
            runtime_state_store=None,
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
            runtime_state_store=None,
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

    def test_run_forever_writes_startup_audit_event_before_first_tick(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import run_forever
        from momentum_alpha.runtime_store import fetch_recent_audit_events, fetch_recent_position_snapshots

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

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            exit_code = run_forever(
                symbols=["BTCUSDT"],
                previous_leader_symbol=None,
                submit_orders=True,
                runtime_state_store=None,
                client_factory=lambda: FakeClient(),
                broker_factory=lambda client: object(),
                now_provider=lambda: datetime(2026, 4, 15, 1, 1, tzinfo=timezone.utc),
                sleep_fn=lambda seconds: None,
                logger=lambda message: None,
                max_ticks=0,
                audit_recorder=AuditRecorder(runtime_db_path=runtime_db_path, source="poll"),
            )
            db_events = fetch_recent_audit_events(path=runtime_db_path, limit=10)
            snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=10)
            self.assertEqual(exit_code, 0)
            self.assertEqual(db_events[0]["event_type"], "poll_worker_start")
            self.assertEqual(db_events[0]["payload"]["symbol_count"], 1)
            self.assertEqual(db_events[0]["payload"]["submit_orders"], True)
            self.assertEqual(snapshots[0]["leader_symbol"], None)
            self.assertEqual(snapshots[0]["symbol_count"], 1)
            self.assertNotIn("market_context", snapshots[0]["payload"])
            self.assertNotIn("positions", snapshots[0]["payload"])

    def test_record_position_snapshot_persists_live_market_context(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import _build_market_context_payloads, _build_snapshot_market_context_payload, _record_position_snapshot
        from momentum_alpha.models import Position, PositionLeg
        from momentum_alpha.runtime_store import fetch_recent_position_snapshots

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"
            market_payloads, leader_gap_pct = _build_market_context_payloads(
                snapshots=[
                    {
                        "symbol": "BASEUSDT",
                        "latest_price": Decimal("108"),
                        "daily_open_price": Decimal("100"),
                        "previous_hour_low": Decimal("98"),
                        "current_hour_low": Decimal("99"),
                    },
                    {
                        "symbol": "ALTUSDT",
                        "latest_price": Decimal("206"),
                        "daily_open_price": Decimal("200"),
                        "previous_hour_low": Decimal("195"),
                        "current_hour_low": Decimal("197"),
                    },
                ]
            )
            _record_position_snapshot(
                audit_recorder=AuditRecorder(runtime_db_path=runtime_db_path, source="poll"),
                now=datetime(2026, 4, 17, 0, 4, tzinfo=timezone.utc),
                leader_symbol="BASEUSDT",
                position_count=1,
                order_status_count=0,
                positions={
                    "BASEUSDT": Position(
                        symbol="BASEUSDT",
                        stop_price=Decimal("0.15"),
                        legs=(
                            PositionLeg(
                                symbol="BASEUSDT",
                                quantity=Decimal("3.5"),
                                entry_price=Decimal("0.17"),
                                stop_price=Decimal("0.15"),
                                opened_at=datetime(2026, 4, 16, 23, 30, tzinfo=timezone.utc),
                                leg_type="base",
                            ),
                        ),
                    )
                },
                payload={},
                market_payloads=market_payloads,
                market_context=_build_snapshot_market_context_payload(
                    leader_symbol="BASEUSDT",
                    market_payloads=market_payloads,
                    leader_gap_pct=leader_gap_pct,
                ),
            )

            snapshots = fetch_recent_position_snapshots(path=runtime_db_path, limit=1)
            payload = snapshots[0]["payload"]
            self.assertEqual(payload["positions"]["BASEUSDT"]["symbol"], "BASEUSDT")
            self.assertEqual(payload["positions"]["BASEUSDT"]["stop_price"], "0.15")
            self.assertEqual(payload["positions"]["BASEUSDT"]["total_quantity"], "3.5")
            self.assertEqual(payload["positions"]["BASEUSDT"]["legs"][0]["quantity"], "3.5")
            self.assertEqual(payload["positions"]["BASEUSDT"]["latest_price"], "108")
            self.assertEqual(payload["positions"]["BASEUSDT"]["daily_change_pct"], "0.08")
            self.assertEqual(payload["market_context"]["leader_symbol"], "BASEUSDT")
            self.assertEqual(payload["market_context"]["leader_gap_pct"], "0.05")
            self.assertEqual(payload["market_context"]["candidates"][0]["latest_price"], "108")
            self.assertEqual(payload["market_context"]["candidates"][0]["daily_change_pct"], "0.08")

    def test_run_forever_logs_and_uses_sleep_function(self) -> None:
        from momentum_alpha.main import run_forever
        from momentum_alpha.runtime_store import RuntimeStateStore

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
                runtime_state_store=RuntimeStateStore(path=Path(tmpdir) / "runtime.db"),
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
            runtime_state_store=None,
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
            runtime_state_store=None,
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
            last_add_on_hour=1,
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
            last_add_on_hour=1,
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
            last_add_on_hour=1,
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

            def fetch_klines(self, *, symbol, interval, limit, start_time_ms=None, end_time_ms=None):
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
            last_add_on_hour=1,
        )
        self.assertEqual(result.stop_replacements, [("BTCUSDT", Decimal("61000"))])
        self.assertEqual(broker.replacements[0], [("BTCUSDT", "0.010", "61000")])

    def test_run_once_live_records_executed_stop_replacement_responses(self) -> None:
        from momentum_alpha.audit import AuditRecorder
        from momentum_alpha.main import run_once_live
        from momentum_alpha.runtime_store import fetch_recent_audit_events, fetch_recent_broker_orders

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
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "positionAmt": "0.010", "entryPrice": "61100", "updateTime": 1700000000000}]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "type": "STOP_MARKET", "stopPrice": "60900"}]

        class FakeBroker:
            def replace_stop_orders(self, *, replacements):
                return [
                    {
                        "symbol": "BTCUSDT",
                        "status": "NEW",
                        "side": "SELL",
                        "type": "STOP_MARKET",
                        "algoId": 11,
                        "clientAlgoId": "ma_260415020000_BTCUSDT_b00s",
                        "quantity": "0.010",
                        "triggerPrice": "61000",
                    }
                ]

            def submit_execution_plan(self, plan):
                return []

        with TemporaryDirectory() as tmpdir:
            runtime_db_path = Path(tmpdir) / "runtime.db"

            run_once_live(
                symbols=["BTCUSDT"],
                now=datetime(2026, 4, 15, 2, 0, tzinfo=timezone.utc),
                previous_leader_symbol="BTCUSDT",
                client=FakeClient(),
                broker=FakeBroker(),
                submit_orders=False,
                restore_positions=True,
                execute_stop_replacements=True,
                last_add_on_hour=1,
                audit_recorder=AuditRecorder(runtime_db_path=runtime_db_path, source="poll"),
            )

            audit_events = fetch_recent_audit_events(path=runtime_db_path, limit=10)
            broker_orders = fetch_recent_broker_orders(path=runtime_db_path, limit=10)

            self.assertTrue(any(event["event_type"] == "broker_replace" for event in audit_events))
            self.assertEqual(broker_orders[0]["action_type"], "replace_stop_order")
            self.assertEqual(broker_orders[0]["symbol"], "BTCUSDT")

    def test_run_once_live_replaces_missing_stop_for_restored_position_outside_hour_boundary(self) -> None:
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
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "positionAmt": "0.010", "entryPrice": "61100", "updateTime": 1700000000000}]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return []

            def fetch_open_algo_orders(self, *, symbol=None, timestamp_ms=None):
                return []

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
            now=datetime(2026, 4, 15, 2, 5, tzinfo=timezone.utc),
            previous_leader_symbol="BTCUSDT",
            client=FakeClient(),
            broker=broker,
            submit_orders=False,
            restore_positions=True,
            execute_stop_replacements=True,
        )

        self.assertEqual(result.stop_replacements, [("BTCUSDT", Decimal("61000"))])
        self.assertEqual(broker.replacements[0], [("BTCUSDT", "0.010", "61000")])

    def test_run_once_live_executes_hourly_stop_replacement_before_add_on_orders(self) -> None:
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
                    return [[0, "60000", "0", "0", "0"]]
                return [[0, "0", "0", "61000", "0"]]

            def fetch_position_risk(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "positionAmt": "0.010", "entryPrice": "61100", "updateTime": 1700000000000}]

            def fetch_open_orders(self, *, symbol=None, timestamp_ms=None):
                return [{"symbol": "BTCUSDT", "type": "STOP_MARKET", "stopPrice": "60900"}]

        class FakeBroker:
            def __init__(self) -> None:
                self.call_order = []
                self.replacements = []
                self.submitted_plans = []

            def submit_execution_plan(self, plan):
                self.call_order.append("submit")
                self.submitted_plans.append(plan)
                return [{"status": "NEW", "type": "MARKET"}, {"status": "NEW", "type": "STOP_MARKET"}]

            def replace_stop_orders(self, *, replacements):
                self.call_order.append("replace")
                self.replacements.append(replacements)
                return [{"status": "NEW", "type": "STOP_MARKET"}]

        broker = FakeBroker()
        result = run_once_live(
            symbols=["BTCUSDT"],
            now=datetime(2026, 4, 15, 2, 0, tzinfo=timezone.utc),
            previous_leader_symbol="BTCUSDT",
            client=FakeClient(),
            broker=broker,
            submit_orders=True,
            restore_positions=True,
            execute_stop_replacements=True,
            last_add_on_hour=1,
        )

        self.assertEqual(result.stop_replacements, [("BTCUSDT", Decimal("61000"))])
        self.assertEqual(broker.call_order, ["replace", "submit"])
        self.assertEqual(broker.replacements[0], [("BTCUSDT", "0.010", "61000")])
        self.assertEqual(len(broker.submitted_plans[0].entry_orders), 1)
        self.assertEqual(len(broker.submitted_plans[0].stop_orders), 1)
