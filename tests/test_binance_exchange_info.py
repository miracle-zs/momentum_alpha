import sys
import unittest
from decimal import Decimal
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BinanceExchangeInfoTests(unittest.TestCase):
    def test_parses_perpetual_usdt_symbol_filters(self) -> None:
        from momentum_alpha.exchange_info import parse_exchange_info

        payload = {
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

        symbols = parse_exchange_info(payload)
        btc = symbols["BTCUSDT"]
        self.assertEqual(btc.filters.tick_size, Decimal("0.10"))
        self.assertEqual(btc.filters.step_size, Decimal("0.001"))
        self.assertEqual(btc.filters.min_qty, Decimal("0.001"))
        self.assertEqual(btc.min_notional, Decimal("5"))

    def test_ignores_non_usdt_or_non_perpetual_symbols(self) -> None:
        from momentum_alpha.exchange_info import parse_exchange_info

        payload = {
            "symbols": [
                {
                    "symbol": "BTCUSD_PERP",
                    "contractType": "PERPETUAL",
                    "quoteAsset": "USD",
                    "status": "TRADING",
                    "filters": [],
                },
                {
                    "symbol": "BTCUSDT_260625",
                    "contractType": "CURRENT_QUARTER",
                    "quoteAsset": "USDT",
                    "status": "TRADING",
                    "filters": [],
                },
            ]
        }

        self.assertEqual(parse_exchange_info(payload), {})
