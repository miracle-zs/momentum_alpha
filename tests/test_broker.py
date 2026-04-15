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
        from momentum_alpha.broker import BinanceBroker
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.execution import ExecutionPlan

        class FakeClient:
            def __init__(self) -> None:
                self.calls = []

            def new_order(self, **params):
                self.calls.append(params)
                return {"status": "NEW", **params}

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

    def test_broker_replaces_stop_orders(self) -> None:
        from momentum_alpha.broker import BinanceBroker

        class FakeClient:
            def __init__(self) -> None:
                self.open_order_calls = []
                self.cancel_calls = []
                self.new_order_calls = []

            def fetch_open_orders(self, **params):
                self.open_order_calls.append(params)
                return [
                    {"symbol": params["symbol"], "type": "STOP_MARKET", "orderId": 11},
                    {"symbol": params["symbol"], "type": "LIMIT", "orderId": 12},
                ]

            def cancel_order(self, **params):
                self.cancel_calls.append(params)
                return {"symbol": params["symbol"], "status": "CANCELED", "orderId": params["order_id"]}

            def new_order(self, **params):
                self.new_order_calls.append(params)
                return {"status": "NEW", **params}

        broker = BinanceBroker(client=FakeClient())
        responses = broker.replace_stop_orders(
            replacements=[("BTCUSDT", "0.010", "61000.0"), ("ETHUSDT", "0.500", "3000.0")]
        )
        self.assertEqual(len(responses), 2)
        self.assertEqual(broker.client.open_order_calls[0]["symbol"], "BTCUSDT")
        self.assertEqual(broker.client.cancel_calls[0]["order_id"], 11)
        self.assertEqual(broker.client.cancel_calls[1]["order_id"], 11)
        self.assertEqual(broker.client.new_order_calls[1]["symbol"], "ETHUSDT")
        self.assertEqual(broker.client.new_order_calls[0]["type"], "STOP_MARKET")
