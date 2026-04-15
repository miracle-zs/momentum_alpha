import sys
import unittest
from pathlib import Path
import json
from io import BytesIO
from urllib.error import HTTPError, URLError


ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))


class BinanceClientTests(unittest.TestCase):
    def test_signed_query_uses_hmac_sha256_signature(self) -> None:
        from momentum_alpha.binance_client import sign_query

        query = "symbol=BTCUSDT&timestamp=1700000000000"
        signature = sign_query(secret="secret", query=query)
        self.assertEqual(signature, "6244d11c958f45ac56733152cb3cb1831d23a2b3709b3a88b8b42a072aceb410")

    def test_public_request_builds_expected_url(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        client = BinanceRestClient(api_key="key", api_secret="secret")
        request = client.build_public_request(path="/fapi/v1/exchangeInfo")
        self.assertEqual(request.url, "https://fapi.binance.com/fapi/v1/exchangeInfo")
        self.assertEqual(request.headers["X-MBX-APIKEY"], "key")

    def test_testnet_client_uses_testnet_base_url(self) -> None:
        from momentum_alpha.binance_client import BINANCE_TESTNET_FAPI_BASE_URL, BinanceRestClient

        client = BinanceRestClient(api_key="key", api_secret="secret", base_url=BINANCE_TESTNET_FAPI_BASE_URL)
        request = client.build_public_request(path="/fapi/v1/exchangeInfo")
        self.assertEqual(request.url, "https://testnet.binancefuture.com/fapi/v1/exchangeInfo")

    def test_signed_request_appends_timestamp_and_signature(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        client = BinanceRestClient(api_key="key", api_secret="secret")
        request = client.build_signed_request(
            method="POST",
            path="/fapi/v1/order",
            params={"symbol": "BTCUSDT", "side": "BUY"},
            timestamp_ms=1700000000000,
        )
        self.assertIn("timestamp=1700000000000", request.body)
        self.assertIn("signature=", request.body)
        self.assertEqual(request.method, "POST")

    def test_send_parses_json_response(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest, BinanceRestClient

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return json.dumps({"serverTime": 1700000000000}).encode("utf-8")

        class FakeOpener:
            def __call__(self, request):
                self.request = request
                return FakeResponse()

        opener = FakeOpener()
        client = BinanceRestClient(api_key="key", api_secret="secret", opener=opener)
        response = client.send(
            BinanceRequest(
                method="GET",
                url="https://fapi.binance.com/fapi/v1/time",
                headers={"X-MBX-APIKEY": "key"},
            )
        )
        self.assertEqual(response["serverTime"], 1700000000000)
        self.assertEqual(opener.request.full_url, "https://fapi.binance.com/fapi/v1/time")

    def test_fetch_exchange_info_uses_public_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {"symbols": []}

        client = FakeClient()
        payload = client.fetch_exchange_info()
        self.assertEqual(payload, {"symbols": []})
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/exchangeInfo")

    def test_send_retries_after_url_error(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest, BinanceRestClient

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return json.dumps({"ok": True}).encode("utf-8")

        class FlakyOpener:
            def __init__(self) -> None:
                self.calls = 0

            def __call__(self, request):
                self.calls += 1
                if self.calls == 1:
                    raise URLError("temporary")
                return FakeResponse()

        sleeps = []
        opener = FlakyOpener()
        client = BinanceRestClient(
            api_key="key",
            api_secret="secret",
            opener=opener,
            retry_delays=(0.5,),
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        payload = client.send(
            BinanceRequest(
                method="GET",
                url="https://fapi.binance.com/fapi/v1/time",
                headers={"X-MBX-APIKEY": "key"},
            )
        )
        self.assertEqual(payload["ok"], True)
        self.assertEqual(opener.calls, 2)
        self.assertEqual(sleeps, [0.5])

    def test_send_passes_timeout_to_opener(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest, BinanceRestClient

        class FakeResponse:
            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self) -> bytes:
                return json.dumps({"ok": True}).encode("utf-8")

        class TimeoutCapturingOpener:
            def __call__(self, request, timeout=None):
                self.timeout = timeout
                return FakeResponse()

        opener = TimeoutCapturingOpener()
        client = BinanceRestClient(
            api_key="key",
            api_secret="secret",
            opener=opener,
            timeout_seconds=12.5,
        )
        payload = client.send(
            BinanceRequest(
                method="GET",
                url="https://fapi.binance.com/fapi/v1/time",
                headers={"X-MBX-APIKEY": "key"},
            )
        )
        self.assertEqual(payload["ok"], True)
        self.assertEqual(opener.timeout, 12.5)

    def test_send_raises_after_retry_budget_exhausted(self) -> None:
        from momentum_alpha.binance_client import BinanceRequest, BinanceRestClient

        class AlwaysFailOpener:
            def __call__(self, request):
                raise URLError("down")

        sleeps = []
        client = BinanceRestClient(
            api_key="key",
            api_secret="secret",
            opener=AlwaysFailOpener(),
            retry_delays=(0.1, 0.2),
            sleep_fn=lambda seconds: sleeps.append(seconds),
        )
        with self.assertRaises(URLError):
            client.send(
                BinanceRequest(
                    method="GET",
                    url="https://fapi.binance.com/fapi/v1/time",
                    headers={"X-MBX-APIKEY": "key"},
                )
            )
        self.assertEqual(sleeps, [0.1, 0.2])

    def test_send_raises_binance_http_error_with_response_body(self) -> None:
        from momentum_alpha.binance_client import BinanceHttpError, BinanceRequest, BinanceRestClient

        class HttpFailOpener:
            def __call__(self, request, timeout=None):
                raise HTTPError(
                    url=request.full_url,
                    code=403,
                    msg="Forbidden",
                    hdrs=None,
                    fp=BytesIO(b'{"code":-2015,"msg":"Invalid API-key, IP, or permissions for action."}'),
                )

        client = BinanceRestClient(
            api_key="key",
            api_secret="secret",
            opener=HttpFailOpener(),
        )
        with self.assertRaises(BinanceHttpError) as context:
            client.send(
                BinanceRequest(
                    method="GET",
                    url="https://fapi.binance.com/fapi/v3/positionRisk",
                    headers={"X-MBX-APIKEY": "key"},
                )
            )
        self.assertEqual(context.exception.status_code, 403)
        self.assertIn("Invalid API-key", context.exception.response_body)
        self.assertIn("/fapi/v3/positionRisk", str(context.exception))

    def test_fetch_ticker_price_uses_symbol_query(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {"symbol": "BTCUSDT", "price": "61234.56"}

        client = FakeClient()
        payload = client.fetch_ticker_price(symbol="BTCUSDT")
        self.assertEqual(payload["symbol"], "BTCUSDT")
        self.assertIn("symbol=BTCUSDT", client.requests[0].url)

    def test_fetch_ticker_prices_without_symbol_uses_batch_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [{"symbol": "BTCUSDT", "price": "61234.56"}]

        client = FakeClient()
        payload = client.fetch_ticker_prices()
        self.assertEqual(payload[0]["symbol"], "BTCUSDT")
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/ticker/price")

    def test_fetch_klines_uses_interval_and_limit(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [[1700000000000, "60000", "62000", "59000", "61000"]]

        client = FakeClient()
        payload = client.fetch_klines(symbol="BTCUSDT", interval="1h", limit=2)
        self.assertEqual(payload[0][3], "59000")
        self.assertIn("interval=1h", client.requests[0].url)
        self.assertIn("limit=2", client.requests[0].url)

    def test_fetch_klines_supports_start_and_end_time(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [[1744675200000, "60000", "62000", "59000", "61000"]]

        client = FakeClient()
        payload = client.fetch_klines(
            symbol="BTCUSDT",
            interval="1m",
            limit=1,
            start_time_ms=1744675200000,
            end_time_ms=1744675259999,
        )
        self.assertEqual(payload[0][0], 1744675200000)
        self.assertIn("startTime=1744675200000", client.requests[0].url)
        self.assertIn("endTime=1744675259999", client.requests[0].url)

    def test_fetch_position_risk_uses_signed_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [{"symbol": "BTCUSDT", "positionAmt": "1"}]

        client = FakeClient()
        payload = client.fetch_position_risk(symbol="BTCUSDT", timestamp_ms=1700000000000)
        self.assertEqual(payload[0]["symbol"], "BTCUSDT")
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v3/positionRisk")
        self.assertIn("symbol=BTCUSDT", client.requests[0].body)
        self.assertIn("signature=", client.requests[0].body)

    def test_fetch_open_orders_uses_signed_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [{"symbol": "BTCUSDT", "type": "STOP_MARKET"}]

        client = FakeClient()
        payload = client.fetch_open_orders(symbol="BTCUSDT", timestamp_ms=1700000000000)
        self.assertEqual(payload[0]["type"], "STOP_MARKET")
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/openOrders")
        self.assertIn("timestamp=1700000000000", client.requests[0].body)

    def test_cancel_open_orders_uses_delete_signed_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return [{"symbol": "BTCUSDT", "status": "CANCELED"}]

        client = FakeClient()
        payload = client.cancel_open_orders(symbol="BTCUSDT", timestamp_ms=1700000000000)
        self.assertEqual(payload[0]["status"], "CANCELED")
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/allOpenOrders")
        self.assertEqual(client.requests[0].method, "DELETE")

    def test_cancel_order_uses_delete_signed_endpoint_with_order_id(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {"symbol": "BTCUSDT", "status": "CANCELED", "orderId": 123}

        client = FakeClient()
        payload = client.cancel_order(symbol="BTCUSDT", order_id=123, timestamp_ms=1700000000000)
        self.assertEqual(payload["orderId"], 123)
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/order")
        self.assertEqual(client.requests[0].method, "DELETE")
        self.assertIn("orderId=123", client.requests[0].body)

    def test_create_listen_key_uses_api_key_endpoint(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {"listenKey": "abc"}

        client = FakeClient()
        payload = client.create_listen_key()
        self.assertEqual(payload["listenKey"], "abc")
        self.assertEqual(client.requests[0].url, "https://fapi.binance.com/fapi/v1/listenKey")
        self.assertEqual(client.requests[0].method, "POST")
        self.assertEqual(client.requests[0].headers["X-MBX-APIKEY"], "key")

    def test_keepalive_listen_key_uses_put(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {}

        client = FakeClient()
        client.keepalive_listen_key(listen_key="abc")
        self.assertEqual(client.requests[0].method, "PUT")
        self.assertIn("listenKey=abc", client.requests[0].body)

    def test_close_listen_key_uses_delete(self) -> None:
        from momentum_alpha.binance_client import BinanceRestClient

        class FakeClient(BinanceRestClient):
            def __init__(self) -> None:
                super().__init__(api_key="key", api_secret="secret")
                self.requests = []

            def send(self, request):
                self.requests.append(request)
                return {}

        client = FakeClient()
        client.close_listen_key(listen_key="abc")
        self.assertEqual(client.requests[0].method, "DELETE")
        self.assertIn("listenKey=abc", client.requests[0].body)
