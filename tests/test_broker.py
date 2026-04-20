import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BrokerTests(unittest.TestCase):
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
        # 止损单应该设置 reduceOnly=true 以确保只平仓不开新仓
        self.assertEqual(broker.client.new_algo_order_calls[0]["reduceOnly"], "true")
        self.assertEqual(broker.client.new_algo_order_calls[1]["reduceOnly"], "true")
        # 双向持仓模式: positionSide="LONG" 时应该传递该参数
        self.assertEqual(broker.client.new_algo_order_calls[1]["positionSide"], "LONG")
        self.assertEqual(len(broker.client.send_calls), 2)

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
