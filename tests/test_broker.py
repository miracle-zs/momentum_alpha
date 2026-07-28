import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BrokerTests(unittest.TestCase):
    def test_replacement_stop_client_order_id_for_non_ascii_symbol_is_binance_safe(self) -> None:
        from datetime import datetime, timezone

        from momentum_alpha.broker import _build_replacement_stop_client_order_id

        client_order_id = _build_replacement_stop_client_order_id(
            "龙虾USDT",
            now=datetime(2026, 6, 16, 4, 17, 0, 123000, tzinfo=timezone.utc),
        )

        self.assertRegex(client_order_id, r"^[.A-Z:/a-z0-9_-]{1,36}$")
        self.assertNotIn("龙虾", client_order_id)

    def test_broker_submits_entry_and_stop_orders(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.new_order_calls = []
                self.new_algo_order_calls = []
                self.send_calls = []

            def new_order(self, **params):
                self.new_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                self.send_calls.append(request)
                return {
                    "status": "NEW",
                    "symbol": "BTCUSDT",
                    "type": "MARKET" if len(self.send_calls) == 1 else "STOP_MARKET",
                }

        broker = BinanceBroker(client=FakeClient())
        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )
        plan = ExecutionPlan(
            entry_orders=[{"symbol": symbol.symbol, "side": "BUY", "type": "MARKET", "quantity": "0.010"}],
            stop_orders=[{"symbol": symbol.symbol, "side": "SELL", "type": "STOP_MARKET", "quantity": "0.010", "stopPrice": "61000.0", "workingType": "CONTRACT_PRICE"}],
        )

        responses = broker.submit_execution_plan(plan)
        self.assertEqual(len(responses), 2)
        self.assertEqual(responses[0]["type"], "MARKET")
        self.assertEqual(responses[1]["type"], "STOP_MARKET")
        self.assertEqual(len(broker.client.new_order_calls), 1)
        self.assertEqual(len(broker.client.new_algo_order_calls), 1)
        self.assertEqual(len(broker.client.send_calls), 2)

    def test_broker_replaces_stop_orders(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def __init__(self) -> None:
                self.open_algo_order_calls = []
                self.cancel_algo_calls = []
                self.new_algo_order_calls = []
                self.send_calls = []

            def fetch_open_algo_orders(self, **params):
                self.open_algo_order_calls.append(params)
                symbol = params["symbol"]
                if symbol == "BTCUSDT":
                    return [
                        {"symbol": symbol, "orderType": "STOP_MARKET", "algoId": 11, "clientAlgoId": "ma_240101120000_BTCUSDT_b01s"},
                        {"symbol": symbol, "orderType": "STOP_MARKET", "algoId": 13, "clientAlgoId": "user_manual_stop"},
                        {"symbol": symbol, "orderType": "TAKE_PROFIT_MARKET", "algoId": 12},
                    ]
                else:
                    return [
                        {"symbol": symbol, "orderType": "STOP_MARKET", "algoId": 21, "clientAlgoId": "ma_240101120000_ETHUSDT_b01s"},
                        {"symbol": symbol, "orderType": "STOP_MARKET", "algoId": 23, "clientAlgoId": "another_manual"},
                    ]

            def cancel_algo_order(self, **params):
                self.cancel_algo_calls.append(params)
                return {"status": "CANCELED", "algoId": params["algo_id"]}

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                self.send_calls.append(request)
                return {"status": "NEW", "symbol": "BTCUSDT" if len(self.send_calls) == 1 else "ETHUSDT"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.replace_stop_orders(
            replacements=[("BTCUSDT", "0.010", "61000.0", None), ("ETHUSDT", "0.500", "3000.0", "LONG")]
        )
        self.assertEqual(len(responses), 2)
        self.assertEqual(broker.client.open_algo_order_calls[0]["symbol"], "BTCUSDT")
        # Only strategy-created stop orders (clientAlgoId starts with "ma_") should be cancelled
        self.assertEqual(len(broker.client.cancel_algo_calls), 2)
        self.assertEqual(broker.client.cancel_algo_calls[0]["algo_id"], 11)
        self.assertEqual(broker.client.cancel_algo_calls[1]["algo_id"], 21)
        self.assertEqual(broker.client.new_algo_order_calls[1]["symbol"], "ETHUSDT")
        self.assertEqual(broker.client.new_algo_order_calls[0]["type"], "STOP_MARKET")
        self.assertEqual(broker.client.new_algo_order_calls[0]["stopPrice"], "61000.0")
        # 单向持仓模式: positionSide=None 时不应该传递该参数
        self.assertNotIn("positionSide", broker.client.new_algo_order_calls[0])
        # 单向持仓模式的止损单应该设置 reduceOnly=true 以确保只平仓不开新仓
        self.assertEqual(broker.client.new_algo_order_calls[0]["reduceOnly"], "true")
        # 双向持仓模式不能同时传 reduceOnly 和 positionSide
        self.assertNotIn("reduceOnly", broker.client.new_algo_order_calls[1])
        self.assertTrue(broker.client.new_algo_order_calls[0]["newClientOrderId"].startswith("ma_"))
        self.assertTrue(broker.client.new_algo_order_calls[0]["newClientOrderId"].endswith("s"))
        self.assertIn("BTCUSDT", broker.client.new_algo_order_calls[0]["newClientOrderId"])
        self.assertTrue(broker.client.new_algo_order_calls[1]["newClientOrderId"].startswith("ma_"))
        self.assertTrue(broker.client.new_algo_order_calls[1]["newClientOrderId"].endswith("s"))
        self.assertIn("ETHUSDT", broker.client.new_algo_order_calls[1]["newClientOrderId"])
        # 双向持仓模式: positionSide="LONG" 时应该传递该参数
        self.assertEqual(broker.client.new_algo_order_calls[1]["positionSide"], "LONG")
        self.assertEqual(len(broker.client.send_calls), 2)

    def test_broker_creates_replacement_stop_before_canceling_old_stop(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def __init__(self) -> None:
                self.call_order = []

            def fetch_open_algo_orders(self, **params):
                self.call_order.append(("fetch", params["symbol"]))
                return [
                    {
                        "symbol": params["symbol"],
                        "orderType": "STOP_MARKET",
                        "algoId": 11,
                        "clientAlgoId": "ma_240101120000_BTCUSDT_b01s",
                    }
                ]

            def cancel_algo_order(self, **params):
                self.call_order.append(("cancel", params["client_algo_id"]))
                return {"status": "CANCELED"}

            def new_algo_order(self, **params):
                self.call_order.append(("new", params["symbol"]))
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                self.call_order.append(("send", request.body))
                return {"status": "NEW", "symbol": "BTCUSDT"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.replace_stop_orders(replacements=[("BTCUSDT", "0.010", "61000.0")])

        self.assertEqual(len(responses), 1)
        self.assertEqual(
            broker.client.call_order,
            [
                ("fetch", "BTCUSDT"),
                ("new", "BTCUSDT"),
                ("send", "symbol=BTCUSDT"),
                ("cancel", "ma_240101120000_BTCUSDT_b01s"),
            ],
        )

    def test_broker_reports_old_stop_cancellation_failure(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def fetch_open_algo_orders(self, **params):
                return [
                    {
                        "symbol": params["symbol"],
                        "orderType": "STOP_MARKET",
                        "algoId": 11,
                        "clientAlgoId": "ma_240101120000_BTCUSDT_b01s",
                    }
                ]

            def cancel_algo_order(self, **params):
                raise RuntimeError("cancel unavailable")

            def new_algo_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                return {"status": "NEW", "symbol": "BTCUSDT"}

        broker = BinanceBroker(client=FakeClient())

        responses = broker.replace_stop_orders(replacements=[("BTCUSDT", "0.010", "61000.0")])

        self.assertEqual(responses, [{"status": "NEW", "symbol": "BTCUSDT"}])
        self.assertEqual(
            broker.last_stop_replacement_failures,
            [
                {
                    "symbol": "BTCUSDT",
                    "quantity": "0.010",
                    "stop_price": "61000.0",
                    "client_algo_id": "ma_240101120000_BTCUSDT_b01s",
                    "algo_id": 11,
                    "message": "cancel unavailable",
                    "status": "STOP_CANCEL_FAILED",
                }
            ],
        )

    def test_broker_keeps_old_stop_and_continues_when_replacement_creation_fails(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def __init__(self) -> None:
                self.cancel_algo_calls = []
                self.new_algo_order_calls = []

            def fetch_open_algo_orders(self, **params):
                symbol = params["symbol"]
                return [
                    {
                        "symbol": symbol,
                        "orderType": "STOP_MARKET",
                        "algoId": 11 if symbol == "BTCUSDT" else 21,
                        "clientAlgoId": f"ma_240101120000_{symbol}_b01s",
                    }
                ]

            def cancel_algo_order(self, **params):
                self.cancel_algo_calls.append(params)
                return {"status": "CANCELED"}

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                if "symbol=BTCUSDT" in request.body:
                    raise RuntimeError("Order would immediately trigger")
                return {"status": "NEW", "symbol": "ETHUSDT"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.replace_stop_orders(
            replacements=[("BTCUSDT", "0.010", "61000.0"), ("ETHUSDT", "0.500", "3000.0")]
        )

        self.assertEqual(responses, [{"status": "NEW", "symbol": "ETHUSDT"}])
        self.assertEqual([call["symbol"] for call in broker.client.new_algo_order_calls], ["BTCUSDT", "ETHUSDT"])
        self.assertEqual([call["client_algo_id"] for call in broker.client.cancel_algo_calls], ["ma_240101120000_ETHUSDT_b01s"])
        self.assertEqual(
            broker.last_stop_replacement_failures,
            [
                {
                    "symbol": "BTCUSDT",
                    "quantity": "0.010",
                    "stop_price": "61000.0",
                    "message": "Order would immediately trigger",
                }
            ],
        )

    def test_broker_normalizes_replacement_stop_quantity_and_price_when_filters_are_available(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def __init__(self) -> None:
                self.new_algo_order_calls = []

            def fetch_exchange_info(self):
                return {
                    "symbols": [
                        {
                            "symbol": "BTCUSDT",
                            "status": "TRADING",
                            "contractType": "PERPETUAL",
                            "quoteAsset": "USDT",
                            "filters": [
                                {"filterType": "LOT_SIZE", "stepSize": "0.001", "minQty": "0.001"},
                                {"filterType": "PRICE_FILTER", "tickSize": "0.10"},
                                {"filterType": "MIN_NOTIONAL", "notional": "5"},
                            ],
                        }
                    ]
                }

            def fetch_open_algo_orders(self, **params):
                return []

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                return {"status": "NEW", "symbol": "BTCUSDT"}

        broker = BinanceBroker(client=FakeClient())

        broker.replace_stop_orders(replacements=[("BTCUSDT", "0.0109", "61000.19")])

        self.assertEqual(broker.client.new_algo_order_calls[0]["quantity"], "0.010")
        self.assertEqual(broker.client.new_algo_order_calls[0]["stopPrice"], "61000.10")

    def test_broker_exposes_stop_order_failures_after_entry_succeeds(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def new_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def new_algo_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                if "/fapi/v1/algoOrder" in request.url:
                    raise RuntimeError("Order would immediately trigger")
                return {"status": "NEW", "symbol": "BTCUSDT", "type": "MARKET"}

        broker = BinanceBroker(client=FakeClient())
        plan = ExecutionPlan(
            entry_orders=[{"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.010"}],
            stop_orders=[{"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "quantity": "0.010", "stopPrice": "61000.0"}],
        )

        responses = broker.submit_execution_plan(plan)

        self.assertEqual(responses, [{"status": "NEW", "symbol": "BTCUSDT", "type": "MARKET"}])
        self.assertEqual(len(broker.last_stop_order_failures), 1)
        self.assertEqual(broker.last_stop_order_failures[0]["status"], "STOP_SUBMIT_FAILED")

    def test_broker_turns_stop_rate_limit_into_retryable_tick_result(self) -> None:
        from urllib.error import HTTPError

        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def new_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={},
                    body=f"symbol={params['symbol']}",
                )

            def new_algo_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                if "/fapi/v1/algoOrder" in request.url:
                    raise BinanceHttpError(
                        HTTPError(
                            url=request.url,
                            code=429,
                            msg="Too Many Requests",
                            hdrs=None,
                            fp=None,
                        ),
                        '{"code":-1003,"msg":"Too many requests"}',
                    )
                return {"status": "NEW", "symbol": "BTCUSDT", "type": "MARKET"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[{"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}],
                stop_orders=[{"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "quantity": "1", "stopPrice": "90"}],
            )
        )

        self.assertEqual(len(responses), 1)
        self.assertIsNotNone(broker.last_rate_limit_error)
        self.assertEqual(broker.last_stop_order_failures[0]["status"], "STOP_SUBMIT_RATE_LIMIT")
        self.assertTrue(broker.last_stop_order_failures[0]["retryable"])

    def test_broker_turns_entry_rate_limit_into_retryable_tick_result(self) -> None:
        from urllib.error import HTTPError

        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.fetch_order_calls = 0
                self.new_order_calls = 0
                self.new_algo_order_calls = 0

            def fetch_order(self, **params):
                self.fetch_order_calls += 1
                raise BinanceHttpError(
                    HTTPError(
                        url="https://example.test/fapi/v1/order",
                        code=400,
                        msg="Bad Request",
                        hdrs=None,
                        fp=None,
                    ),
                    '{"code":-2013,"msg":"Order does not exist."}',
                )

            def new_order(self, **params):
                self.new_order_calls += 1
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={},
                    body=f"symbol={params['symbol']}",
                )

            def new_algo_order(self, **params):
                self.new_algo_order_calls += 1
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                raise BinanceHttpError(
                    HTTPError(
                        url=request.url,
                        code=429,
                        msg="Too Many Requests",
                        hdrs=None,
                        fp=None,
                    ),
                    '{"code":-1003,"msg":"Too many requests"}',
                )

        client = FakeClient()
        broker = BinanceBroker(client=client)
        responses = broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[
                    {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "MARKET",
                        "quantity": "1",
                        "newClientOrderId": "ma_260510100000_BTCUSDT_b00e",
                    },
                    {
                        "symbol": "ETHUSDT",
                        "side": "BUY",
                        "type": "MARKET",
                        "quantity": "1",
                        "newClientOrderId": "ma_260510100000_ETHUSDT_b00e",
                    },
                ],
                stop_orders=[
                    {"symbol": "BTCUSDT", "side": "SELL", "type": "STOP_MARKET", "quantity": "1", "stopPrice": "90"},
                    {"symbol": "ETHUSDT", "side": "SELL", "type": "STOP_MARKET", "quantity": "1", "stopPrice": "90"},
                ],
            )
        )

        self.assertEqual(responses, [])
        self.assertEqual(client.new_order_calls, 1)
        self.assertEqual(client.new_algo_order_calls, 0)
        self.assertIsNotNone(broker.last_rate_limit_error)
        self.assertEqual(broker.last_entry_order_failures[0]["status"], "ENTRY_SUBMIT_RATE_LIMIT")
        self.assertTrue(broker.last_entry_order_failures[0]["retryable"])

    def test_broker_skips_stop_order_when_entry_order_fails(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.new_order_calls = []
                self.new_algo_order_calls = []
                self.send_calls = []

            def new_order(self, **params):
                self.new_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                self.send_calls.append(request)
                if "symbol=BTCUSDT" in request.body:
                    raise RuntimeError("margin is insufficient")
                return {"status": "NEW", "symbol": "ETHUSDT", "type": "STOP_MARKET"}

        broker = BinanceBroker(client=FakeClient())
        plan = ExecutionPlan(
            entry_orders=[
                {"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.010"},
                {"symbol": "ETHUSDT", "side": "BUY", "type": "MARKET", "quantity": "0.100"},
            ],
            stop_orders=[
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "quantity": "0.010",
                    "stopPrice": "61000.0",
                },
                {
                    "symbol": "ETHUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "quantity": "0.100",
                    "stopPrice": "3000.0",
                },
            ],
        )

        responses = broker.submit_execution_plan(plan)

        self.assertEqual(len(broker.client.new_order_calls), 2)
        self.assertEqual(len(broker.client.new_algo_order_calls), 1)
        self.assertEqual(broker.client.new_algo_order_calls[0]["symbol"], "ETHUSDT")
        self.assertEqual(len(responses), 2)
        self.assertEqual([item["symbol"] for item in responses], ["ETHUSDT", "ETHUSDT"])

    def test_broker_recovers_entry_order_by_client_order_id_after_transient_failure(self) -> None:
        from urllib.error import URLError

        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.new_order_calls = []
                self.new_algo_order_calls = []
                self.fetch_order_calls = []

            def new_order(self, **params):
                self.new_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def fetch_order(self, **params):
                self.fetch_order_calls.append(params)
                return {
                    "status": "NEW",
                    "symbol": params["symbol"],
                    "type": "MARKET",
                    "clientOrderId": params["orig_client_order_id"],
                }

            def new_algo_order(self, **params):
                self.new_algo_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                if "/fapi/v1/order" in request.url:
                    raise URLError("temporary tls failure")
                return {"status": "NEW", "symbol": "BTCUSDT", "type": "STOP_MARKET"}

        broker = BinanceBroker(client=FakeClient())
        plan = ExecutionPlan(
            entry_orders=[
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": "0.010",
                    "newClientOrderId": "ma_260510100000_BTCUSDT_a00e",
                }
            ],
            stop_orders=[
                {
                    "symbol": "BTCUSDT",
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "quantity": "0.010",
                    "stopPrice": "61000.0",
                }
            ],
        )

        responses = broker.submit_execution_plan(plan)

        self.assertEqual([response["type"] for response in responses], ["MARKET", "STOP_MARKET"])
        self.assertEqual(broker.client.fetch_order_calls[0]["orig_client_order_id"], "ma_260510100000_BTCUSDT_a00e")
        self.assertEqual(broker.last_entry_order_failures, [])
        self.assertEqual(len(broker.client.new_algo_order_calls), 1)

    def test_broker_does_not_submit_when_preflight_order_lookup_is_unknown(self) -> None:
        from urllib.error import URLError

        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.new_order_calls = []

            def fetch_order(self, **params):
                raise URLError("status endpoint unavailable")

            def new_order(self, **params):
                self.new_order_calls.append(params)
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={},
                    body="symbol=BTCUSDT",
                )

            def send(self, request):
                return {"status": "NEW"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[
                    {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "MARKET",
                        "quantity": "0.010",
                        "newClientOrderId": "ma_260510100000_BTCUSDT_b00e",
                    }
                ],
                stop_orders=[],
            )
        )

        self.assertEqual(responses, [])
        self.assertEqual(broker.client.new_order_calls, [])
        self.assertEqual(broker.last_entry_order_failures[0]["status"], "ENTRY_STATUS_UNKNOWN")
        self.assertTrue(broker.last_entry_order_failures[0]["retryable"])

    def test_broker_does_not_resend_after_submit_error_when_follow_up_lookup_is_unknown(self) -> None:
        from urllib.error import URLError

        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.fetch_order_calls = 0
                self.new_order_calls = 0

            def fetch_order(self, **params):
                self.fetch_order_calls += 1
                if self.fetch_order_calls == 1:
                    raise BinanceHttpError(
                        __import__("urllib.error").error.HTTPError(
                            url="https://example.test/fapi/v1/order",
                            code=400,
                            msg="Bad Request",
                            hdrs=None,
                            fp=None,
                        ),
                        '{"code":-2013,"msg":"Order does not exist."}',
                    )
                raise URLError("status endpoint unavailable")

            def new_order(self, **params):
                self.new_order_calls += 1
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={},
                    body="symbol=BTCUSDT",
                )

            def send(self, request):
                raise URLError("submit response lost")

        broker = BinanceBroker(client=FakeClient(), entry_retry_delays=(0,), sleep_fn=lambda seconds: None)
        responses = broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[
                    {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "MARKET",
                        "quantity": "0.010",
                        "newClientOrderId": "ma_260510100000_BTCUSDT_b00e",
                    }
                ],
                stop_orders=[],
            )
        )

        self.assertEqual(responses, [])
        self.assertEqual(broker.client.new_order_calls, 1)
        self.assertEqual(broker.last_entry_order_failures[0]["status"], "SUBMIT_STATUS_UNKNOWN")
        self.assertTrue(broker.last_entry_order_failures[0]["retryable"])

    def test_broker_does_not_recover_zero_fill_terminal_order(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.new_order_calls = 0

            def fetch_order(self, **params):
                return {
                    "status": "CANCELED",
                    "executedQty": "0",
                    "symbol": params["symbol"],
                }

            def new_order(self, **params):
                self.new_order_calls += 1
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={},
                    body="symbol=BTCUSDT",
                )

            def send(self, request):
                return {"status": "NEW", "symbol": "BTCUSDT"}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[
                    {
                        "symbol": "BTCUSDT",
                        "side": "BUY",
                        "type": "MARKET",
                        "quantity": "0.010",
                        "newClientOrderId": "ma_260510100000_BTCUSDT_b00e",
                    }
                ],
                stop_orders=[],
            )
        )

        self.assertEqual(len(responses), 1)
        self.assertEqual(broker.client.new_order_calls, 1)

    def test_broker_retries_entry_with_same_client_order_id_when_order_was_not_created(self) -> None:
        from urllib.error import URLError

        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.send_calls = 0
                self.new_order_client_ids = []
                self.fetch_order_calls = []

            def new_order(self, **params):
                self.new_order_client_ids.append(params["newClientOrderId"])
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def fetch_order(self, **params):
                self.fetch_order_calls.append(params)
                raise BinanceHttpError(
                    __import__("urllib.error").error.HTTPError(
                        url="https://example.test/fapi/v1/order",
                        code=400,
                        msg="Bad Request",
                        hdrs=None,
                        fp=None,
                    ),
                    '{"code":-2013,"msg":"Order does not exist."}',
                )

            def new_algo_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/algoOrder",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, request):
                self.send_calls += 1
                if "/fapi/v1/order" in request.url and self.send_calls == 1:
                    raise URLError("temporary tls failure")
                if "/fapi/v1/order" in request.url:
                    return {"status": "NEW", "symbol": "BTCUSDT", "type": "MARKET", "clientOrderId": "ma_260510100000_BTCUSDT_a00e"}
                return {"status": "NEW", "symbol": "BTCUSDT", "type": "STOP_MARKET"}

        broker = BinanceBroker(client=FakeClient(), entry_retry_delays=(0,), sleep_fn=lambda seconds: None)
        plan = ExecutionPlan(
            entry_orders=[
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": "0.010",
                    "newClientOrderId": "ma_260510100000_BTCUSDT_a00e",
                }
            ],
            stop_orders=[],
        )

        responses = broker.submit_execution_plan(plan)

        self.assertEqual(responses[0]["status"], "NEW")
        self.assertEqual(broker.client.new_order_client_ids, ["ma_260510100000_BTCUSDT_a00e", "ma_260510100000_BTCUSDT_a00e"])
        self.assertEqual(len(broker.client.fetch_order_calls), 2)

    def test_broker_exposes_failed_entry_attempts_when_retries_are_exhausted(self) -> None:
        from urllib.error import URLError

        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def new_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def fetch_order(self, **params):
                raise BinanceHttpError(
                    __import__("urllib.error").error.HTTPError(
                        url="https://example.test/fapi/v1/order",
                        code=400,
                        msg="Bad Request",
                        hdrs=None,
                        fp=None,
                    ),
                    '{"code":-2013,"msg":"Order does not exist."}',
                )

            def send(self, request):
                raise URLError("temporary tls failure")

        broker = BinanceBroker(client=FakeClient(), entry_retry_delays=(0,), sleep_fn=lambda seconds: None)
        plan = ExecutionPlan(
            entry_orders=[
                {
                    "symbol": "BTCUSDT",
                    "side": "BUY",
                    "type": "MARKET",
                    "quantity": "0.010",
                    "newClientOrderId": "ma_260510100000_BTCUSDT_a00e",
                }
            ],
            stop_orders=[],
        )

        responses = broker.submit_execution_plan(plan)

        self.assertEqual(responses, [])
        self.assertEqual(len(broker.last_entry_order_failures), 1)
        failure = broker.last_entry_order_failures[0]
        self.assertEqual(failure["status"], "SUBMIT_FAILED")
        self.assertEqual(failure["symbol"], "BTCUSDT")
        self.assertEqual(failure["clientOrderId"], "ma_260510100000_BTCUSDT_a00e")
        self.assertEqual(failure["attempts"], 2)
        self.assertTrue(failure["retryable"])

    def test_broker_marks_deterministic_entry_rejection_as_not_retryable(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def new_order(self, **params):
                return BinanceRequest(
                    method="POST",
                    url="https://example.test/fapi/v1/order",
                    headers={"X-MBX-APIKEY": "key"},
                    body=f"symbol={params['symbol']}",
                )

            def send(self, _request):
                raise RuntimeError("Margin is insufficient")

        broker = BinanceBroker(client=FakeClient())
        broker.submit_execution_plan(
            ExecutionPlan(
                entry_orders=[{"symbol": "BTCUSDT", "side": "BUY", "type": "MARKET", "quantity": "1"}],
                stop_orders=[],
            )
        )

        self.assertFalse(broker.last_entry_order_failures[0]["retryable"])
