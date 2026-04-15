import sys
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class DiagnosticsTests(unittest.TestCase):
    def test_private_api_diagnostic_reports_success_summary(self) -> None:
        from momentum_alpha.diagnostics import run_private_api_diagnostic

        class FakeClient:
            def fetch_position_risk(self):
                return [{"symbol": "BTCUSDT", "positionAmt": "0.001"}]

            def fetch_open_orders(self):
                return [{"symbol": "BTCUSDT", "type": "STOP_MARKET"}]

            def create_listen_key(self):
                return {"listenKey": "abc123"}

            def close_listen_key(self, *, listen_key: str):
                self.closed = listen_key
                return {}

        lines = run_private_api_diagnostic(client=FakeClient())
        self.assertIn("position_risk_ok count=1", lines)
        self.assertIn("open_orders_ok count=1", lines)
        self.assertIn("listen_key_ok created=True closed=True", lines)

    def test_private_api_diagnostic_reports_binance_http_error_body(self) -> None:
        from momentum_alpha.binance_client import BinanceHttpError
        from momentum_alpha.diagnostics import run_private_api_diagnostic
        from urllib.error import HTTPError

        class FakeClient:
            def fetch_position_risk(self):
                raise BinanceHttpError(
                    HTTPError(
                        url="https://fapi.binance.com/fapi/v3/positionRisk",
                        code=403,
                        msg="Forbidden",
                        hdrs=None,
                        fp=None,
                    ),
                    '{"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}',
                )

        lines = run_private_api_diagnostic(client=FakeClient())
        self.assertIn("position_risk_error status=403", lines[0])
        self.assertIn("Invalid API-key, IP, or permissions", lines[0])
