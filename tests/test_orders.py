import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BinanceOrderPayloadTests(unittest.TestCase):
    def test_builds_market_entry_payload(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.orders import build_market_entry_order

        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )

        payload = build_market_entry_order(symbol=symbol, quantity=Decimal("0.1234"))
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertEqual(payload["type"], "MARKET")
        self.assertEqual(payload["side"], "BUY")
        self.assertEqual(payload["quantity"], "0.123")

    def test_builds_market_entry_payload_with_position_side(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.orders import build_market_entry_order

        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )

        payload = build_market_entry_order(
            symbol=symbol,
            quantity=Decimal("0.1234"),
            position_side="LONG",
        )
        self.assertEqual(payload["positionSide"], "LONG")

    def test_builds_stop_market_order_payload(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.orders import build_stop_market_order

        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )

        payload = build_stop_market_order(
            symbol=symbol,
            quantity=Decimal("0.1234"),
            stop_price=Decimal("61234.567"),
        )
        self.assertEqual(payload["type"], "STOP_MARKET")
        self.assertEqual(payload["side"], "SELL")
        self.assertEqual(payload["workingType"], "CONTRACT_PRICE")
        self.assertEqual(payload["reduceOnly"], "true")
        self.assertEqual(payload["quantity"], "0.123")
        self.assertEqual(payload["stopPrice"], "61234.50")

    def test_builds_stop_market_order_payload_with_position_side(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.orders import build_stop_market_order

        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )

        payload = build_stop_market_order(
            symbol=symbol,
            quantity=Decimal("0.1234"),
            stop_price=Decimal("61234.567"),
            position_side="LONG",
        )
        self.assertEqual(payload["positionSide"], "LONG")
        self.assertNotIn("reduceOnly", payload)

    def test_order_payloads_include_client_order_id_when_provided(self) -> None:
        from momentum_alpha.binance_filters import SymbolFilters
        from momentum_alpha.exchange_info import ExchangeSymbol
        from momentum_alpha.orders import build_market_entry_order, build_stop_market_order

        symbol = ExchangeSymbol(
            symbol="BTCUSDT",
            status="TRADING",
            filters=SymbolFilters(step_size=Decimal("0.001"), min_qty=Decimal("0.001"), tick_size=Decimal("0.10")),
            min_notional=Decimal("5"),
        )

        entry_payload = build_market_entry_order(
            symbol=symbol,
            quantity=Decimal("0.1234"),
            client_order_id="ma_260415120200_BTCUSDT_b00e",
        )
        stop_payload = build_stop_market_order(
            symbol=symbol,
            quantity=Decimal("0.1234"),
            stop_price=Decimal("61234.567"),
            client_order_id="ma_260415120200_BTCUSDT_b00s",
        )

        self.assertEqual(entry_payload["newClientOrderId"], "ma_260415120200_BTCUSDT_b00e")
        self.assertEqual(stop_payload["newClientOrderId"], "ma_260415120200_BTCUSDT_b00s")
