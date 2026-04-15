from __future__ import annotations

import hashlib
import hmac
import json
import time
from dataclasses import dataclass
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen


BINANCE_FAPI_BASE_URL = "https://fapi.binance.com"
BINANCE_TESTNET_FAPI_BASE_URL = "https://testnet.binancefuture.com"
BINANCE_FSTREAM_WS_URL = "wss://fstream.binance.com/ws"
BINANCE_TESTNET_FSTREAM_WS_URL = "wss://stream.binancefuture.com/ws"


def sign_query(*, secret: str, query: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


@dataclass(frozen=True)
class BinanceRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: str | None = None


class BinanceHttpError(HTTPError):
    def __init__(
        self,
        http_error: HTTPError,
        response_body: str,
        *,
        request_method: str = "UNKNOWN",
        request_url: str = "",
    ) -> None:
        super().__init__(
            url=http_error.url,
            code=http_error.code,
            msg=http_error.msg,
            hdrs=http_error.hdrs,
            fp=None,
        )
        self.status_code = http_error.code
        self.response_body = response_body
        self.request_method = request_method
        self.request_url = request_url

    def __str__(self) -> str:
        request_label = f"{self.request_method} {self.request_url}".strip()
        if self.response_body:
            return f"HTTP Error {self.status_code}: {self.msg} request={request_label} body={self.response_body}"
        return super().__str__()


class BinanceRestClient:
    def __init__(
        self,
        *,
        api_key: str,
        api_secret: str,
        base_url: str = BINANCE_FAPI_BASE_URL,
        opener=None,
        retry_delays: tuple[float, ...] = (),
        sleep_fn=None,
        timeout_seconds: float = 10.0,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urlopen
        self.retry_delays = retry_delays
        self.sleep_fn = sleep_fn or time.sleep
        self.timeout_seconds = timeout_seconds

    def _headers(self) -> dict[str, str]:
        return {"X-MBX-APIKEY": self.api_key}

    def build_public_request(self, *, path: str, params: dict[str, str] | None = None) -> BinanceRequest:
        query = urlencode(params or {})
        suffix = f"?{query}" if query else ""
        return BinanceRequest(
            method="GET",
            url=f"{self.base_url}{path}{suffix}",
            headers=self._headers(),
        )

    def build_api_key_request(self, *, method: str, path: str, params: dict[str, str] | None = None) -> BinanceRequest:
        body = urlencode(params or {}) or None
        return BinanceRequest(
            method=method,
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            body=body,
        )

    def build_signed_request(
        self,
        *,
        method: str,
        path: str,
        params: dict[str, str],
        timestamp_ms: int | None = None,
    ) -> BinanceRequest:
        signed_params = dict(params)
        signed_params["timestamp"] = str(timestamp_ms if timestamp_ms is not None else int(time.time() * 1000))
        query = urlencode(signed_params)
        signature = sign_query(secret=self.api_secret, query=query)
        signed_query = f"{query}&signature={signature}"
        upper_method = method.upper()
        if upper_method in {"GET", "DELETE"}:
            return BinanceRequest(
                method=upper_method,
                url=f"{self.base_url}{path}?{signed_query}",
                headers=self._headers(),
                body=None,
            )
        return BinanceRequest(
            method=upper_method,
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            body=signed_query,
        )

    def new_order(self, **params: str) -> BinanceRequest:
        return self.build_signed_request(method="POST", path="/fapi/v1/order", params=params)

    def send(self, request: BinanceRequest) -> dict:
        raw_request = Request(
            url=request.url,
            headers=request.headers,
            data=request.body.encode("utf-8") if request.body is not None else None,
            method=request.method,
        )
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            try:
                try:
                    response_context = self.opener(raw_request, timeout=self.timeout_seconds)
                except TypeError:
                    response_context = self.opener(raw_request)
                with response_context as response:
                    return json.loads(response.read().decode("utf-8"))
            except HTTPError as exc:
                response_body = ""
                if exc.fp is not None:
                    response_body = exc.fp.read().decode("utf-8", errors="replace")
                raise BinanceHttpError(
                    exc,
                    response_body,
                    request_method=request.method,
                    request_url=request.url,
                ) from exc
            except URLError:
                if attempt >= len(self.retry_delays):
                    raise
                self.sleep_fn(self.retry_delays[attempt])

    def fetch_exchange_info(self) -> dict:
        return self.send(self.build_public_request(path="/fapi/v1/exchangeInfo"))

    def create_listen_key(self) -> dict:
        return self.send(self.build_api_key_request(method="POST", path="/fapi/v1/listenKey"))

    def keepalive_listen_key(self, *, listen_key: str) -> dict:
        return self.send(
            self.build_api_key_request(
                method="PUT",
                path="/fapi/v1/listenKey",
                params={"listenKey": listen_key},
            )
        )

    def close_listen_key(self, *, listen_key: str) -> dict:
        return self.send(
            self.build_api_key_request(
                method="DELETE",
                path="/fapi/v1/listenKey",
                params={"listenKey": listen_key},
            )
        )

    def fetch_ticker_price(self, *, symbol: str) -> dict:
        return self.send(
            self.build_public_request(
                path="/fapi/v1/ticker/price",
                params={"symbol": symbol},
            )
        )

    def fetch_ticker_prices(self) -> list[dict]:
        return self.send(
            self.build_public_request(
                path="/fapi/v1/ticker/price",
            )
        )

    def fetch_klines(
        self,
        *,
        symbol: str,
        interval: str,
        limit: int,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
    ) -> list:
        params = {
            "symbol": symbol,
            "interval": interval,
            "limit": str(limit),
        }
        if start_time_ms is not None:
            params["startTime"] = str(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = str(end_time_ms)
        return self.send(
            self.build_public_request(
                path="/fapi/v1/klines",
                params=params,
            )
        )

    def fetch_position_risk(self, *, symbol: str | None = None, timestamp_ms: int | None = None) -> list:
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v3/positionRisk",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_open_orders(self, *, symbol: str | None = None, timestamp_ms: int | None = None) -> list:
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/openOrders",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_account_info(self, *, timestamp_ms: int | None = None) -> dict:
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v3/account",
            params={},
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def cancel_open_orders(self, *, symbol: str, timestamp_ms: int | None = None) -> list:
        request = self.build_signed_request(
            method="DELETE",
            path="/fapi/v1/allOpenOrders",
            params={"symbol": symbol},
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def cancel_order(self, *, symbol: str, order_id: int, timestamp_ms: int | None = None) -> dict:
        request = self.build_signed_request(
            method="DELETE",
            path="/fapi/v1/order",
            params={
                "symbol": symbol,
                "orderId": str(order_id),
            },
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)
