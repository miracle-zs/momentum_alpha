from __future__ import annotations

import hashlib
import logging
import hmac
import json
import re
import time
from dataclasses import dataclass
from typing import Callable
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from momentum_alpha.structured_log import emit_structured_log


BINANCE_FAPI_BASE_URL = "https://fapi.binance.com"
BINANCE_TESTNET_FAPI_BASE_URL = "https://testnet.binancefuture.com"
BINANCE_FSTREAM_WS_URL = "wss://fstream.binance.com/private/ws"
BINANCE_TESTNET_FSTREAM_WS_URL = "wss://stream.binancefuture.com/ws"
_RETRYABLE_HTTP_STATUS_CODES = {418, 429, 500, 502, 503, 504}
_BAN_UNTIL_RE = re.compile(r"banned until (\d+)", re.IGNORECASE)


def sign_query(*, secret: str, query: str) -> str:
    return hmac.new(secret.encode("utf-8"), query.encode("utf-8"), hashlib.sha256).hexdigest()


_SENSITIVE_QUERY_KEYS = {
    "apikey",
    "api_key",
    "authorization",
    "listenkey",
    "secret",
    "signature",
    "token",
}


def _sanitize_url_for_logs(url: str) -> str:
    parts = urlsplit(url)
    if not parts.query:
        return url
    filtered_params = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if key.lower() not in _SENSITIVE_QUERY_KEYS
    ]
    if not filtered_params:
        return urlunsplit((parts.scheme, parts.netloc, parts.path, "", parts.fragment))
    return urlunsplit((parts.scheme, parts.netloc, parts.path, urlencode(filtered_params), parts.fragment))


@dataclass(frozen=True)
class BinanceRequest:
    method: str
    url: str
    headers: dict[str, str]
    body: str | None = None
    refresh: Callable[[], "BinanceRequest"] | None = None


class BinanceHttpError(HTTPError):
    def __init__(
        self,
        http_error: HTTPError,
        response_body: str,
        *,
        request_method: str = "UNKNOWN",
        request_url: str = "",
    ) -> None:
        url = request_url or http_error.__dict__.get("url") or http_error.__dict__.get("filename") or ""
        super().__init__(
            url=url,
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
        request_label = f"{self.request_method} {_sanitize_url_for_logs(self.request_url)}".strip()
        if self.response_body:
            return f"HTTP Error {self.status_code}: {self.msg} request={request_label} body={self.response_body}"
        return super().__str__()


def _retry_sleep_seconds(*, response_body: str, fallback_seconds: float) -> float:
    match = _BAN_UNTIL_RE.search(response_body or "")
    if match is None:
        return fallback_seconds
    try:
        banned_until_ms = int(match.group(1))
    except ValueError:
        return fallback_seconds
    now_ms = int(time.time() * 1000)
    ban_sleep_seconds = (banned_until_ms - now_ms) / 1000.0
    if ban_sleep_seconds <= 0:
        return fallback_seconds
    return max(fallback_seconds, ban_sleep_seconds + 1.0)


def rate_limit_backoff_seconds(exc: Exception, *, fallback_seconds: float = 120.0) -> float:
    status_code = getattr(exc, "status_code", getattr(exc, "code", None))
    if status_code not in {418, 429}:
        return 0.0
    return _retry_sleep_seconds(
        response_body=getattr(exc, "response_body", ""),
        fallback_seconds=fallback_seconds,
    )


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
        logger: object | None = None,
    ) -> None:
        self.api_key = api_key
        self.api_secret = api_secret
        self.base_url = base_url.rstrip("/")
        self.opener = opener or urlopen
        self.retry_delays = retry_delays
        self.sleep_fn = sleep_fn or time.sleep
        self.timeout_seconds = timeout_seconds
        self.logger = logger or logging.getLogger(__name__)

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
        refresh = (
            None
            if timestamp_ms is not None
            else lambda: self.build_signed_request(method=method, path=path, params=params)
        )
        if upper_method in {"GET", "DELETE"}:
            return BinanceRequest(
                method=upper_method,
                url=f"{self.base_url}{path}?{signed_query}",
                headers=self._headers(),
                body=None,
                refresh=refresh,
            )
        return BinanceRequest(
            method=upper_method,
            url=f"{self.base_url}{path}",
            headers=self._headers(),
            body=signed_query,
            refresh=refresh,
        )

    def new_order(self, **params: str) -> BinanceRequest:
        return self.build_signed_request(method="POST", path="/fapi/v1/order", params=params)

    def new_algo_order(self, **params: str) -> BinanceRequest:
        algo_params = dict(params)
        algo_params["algoType"] = algo_params.get("algoType", "CONDITIONAL")
        if "stopPrice" in algo_params:
            algo_params["triggerPrice"] = algo_params.pop("stopPrice")
        if "newClientOrderId" in algo_params:
            algo_params["clientAlgoId"] = algo_params.pop("newClientOrderId")
        return self.build_signed_request(method="POST", path="/fapi/v1/algoOrder", params=algo_params)

    def send(self, request: BinanceRequest) -> dict:
        attempts = len(self.retry_delays) + 1
        for attempt in range(attempts):
            attempt_request = request if attempt == 0 or request.refresh is None else request.refresh()
            raw_request = Request(
                url=attempt_request.url,
                headers=attempt_request.headers,
                data=attempt_request.body.encode("utf-8") if attempt_request.body is not None else None,
                method=attempt_request.method,
            )
            attempt_started_at = time.perf_counter()
            try:
                try:
                    response_context = self.opener(raw_request, timeout=self.timeout_seconds)
                except TypeError:
                    response_context = self.opener(raw_request)
                with response_context as response:
                    payload = json.loads(response.read().decode("utf-8"))
                    elapsed_ms = int((time.perf_counter() - attempt_started_at) * 1000)
                    emit_structured_log(
                        self.logger,
                        service="binance-client",
                        event="request",
                        method=attempt_request.method,
                        endpoint=urlsplit(attempt_request.url).path,
                        attempt=attempt + 1,
                        retries=attempt,
                        elapsed_ms=elapsed_ms,
                        status_code=getattr(response, "status", getattr(response, "code", None)),
                    )
                    return payload
            except HTTPError as exc:
                response_body = ""
                if exc.fp is not None:
                    response_body = exc.fp.read().decode("utf-8", errors="replace")
                elapsed_ms = int((time.perf_counter() - attempt_started_at) * 1000)
                if exc.code in _RETRYABLE_HTTP_STATUS_CODES and attempt < len(self.retry_delays):
                    sleep_seconds = self.retry_delays[attempt]
                    if exc.code in {418, 429}:
                        sleep_seconds = _retry_sleep_seconds(
                            response_body=response_body,
                            fallback_seconds=sleep_seconds,
                        )
                    emit_structured_log(
                        self.logger,
                        service="binance-client",
                        event="request-retry",
                        level="WARNING",
                        method=attempt_request.method,
                        endpoint=urlsplit(attempt_request.url).path,
                        attempt=attempt + 1,
                        retries=len(self.retry_delays),
                        elapsed_ms=elapsed_ms,
                        status_code=exc.code,
                        response_body=response_body,
                        sleep_seconds=sleep_seconds,
                    )
                    self.sleep_fn(sleep_seconds)
                    continue
                emit_structured_log(
                    self.logger,
                    service="binance-client",
                    event="request-failed",
                    level="ERROR",
                    method=attempt_request.method,
                    endpoint=urlsplit(attempt_request.url).path,
                    attempt=attempt + 1,
                    retries=len(self.retry_delays),
                    elapsed_ms=elapsed_ms,
                    status_code=exc.code,
                    response_body=response_body,
                )
                raise BinanceHttpError(
                    exc,
                    response_body,
                    request_method=attempt_request.method,
                    request_url=attempt_request.url,
                ) from exc
            except URLError as exc:
                elapsed_ms = int((time.perf_counter() - attempt_started_at) * 1000)
                if attempt >= len(self.retry_delays):
                    emit_structured_log(
                        self.logger,
                        service="binance-client",
                        event="request-failed",
                        level="ERROR",
                        method=attempt_request.method,
                        endpoint=urlsplit(attempt_request.url).path,
                        attempt=attempt + 1,
                        retries=len(self.retry_delays),
                        elapsed_ms=elapsed_ms,
                        error=str(exc),
                    )
                    raise
                emit_structured_log(
                    self.logger,
                    service="binance-client",
                    event="request-retry",
                    level="WARNING",
                    method=attempt_request.method,
                    endpoint=urlsplit(attempt_request.url).path,
                    attempt=attempt + 1,
                    retries=len(self.retry_delays),
                    elapsed_ms=elapsed_ms,
                    error=str(exc),
                    sleep_seconds=self.retry_delays[attempt],
                )
                self.sleep_fn(self.retry_delays[attempt])

    def fetch_exchange_info(self) -> dict:
        return self.send(self.build_public_request(path="/fapi/v1/exchangeInfo"))

    def create_listen_key(self) -> dict:
        return self.send(self.build_api_key_request(method="POST", path="/fapi/v1/listenKey"))

    def keepalive_listen_key(self, *, listen_key: str) -> dict:
        _ = listen_key
        return self.send(
            self.build_api_key_request(
                method="PUT",
                path="/fapi/v1/listenKey",
            )
        )

    def close_listen_key(self, *, listen_key: str) -> dict:
        _ = listen_key
        return self.send(
            self.build_api_key_request(
                method="DELETE",
                path="/fapi/v1/listenKey",
            )
        )

    def fetch_ticker_price(self, *, symbol: str) -> dict:
        return self.send(
            self.build_public_request(
                path="/fapi/v2/ticker/price",
                params={"symbol": symbol},
            )
        )

    def fetch_ticker_prices(self) -> list[dict]:
        return self.send(
            self.build_public_request(
                path="/fapi/v2/ticker/price",
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

    def fetch_order(
        self,
        *,
        symbol: str,
        order_id: int | str | None = None,
        orig_client_order_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> dict:
        params: dict[str, str] = {"symbol": symbol}
        if order_id is not None:
            params["orderId"] = str(order_id)
        if orig_client_order_id is not None:
            params["origClientOrderId"] = orig_client_order_id
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/order",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_open_algo_orders(self, *, symbol: str | None = None, timestamp_ms: int | None = None) -> list:
        params: dict[str, str] = {}
        if symbol is not None:
            params["symbol"] = symbol
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/openAlgoOrders",
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

    def fetch_income_history(
        self,
        *,
        income_type: str | None = None,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int | None = None,
        timestamp_ms: int | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {}
        if income_type is not None:
            params["incomeType"] = income_type
        if start_time_ms is not None:
            params["startTime"] = str(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = str(end_time_ms)
        if limit is not None:
            params["limit"] = str(limit)
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/income",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_user_trades(
        self,
        *,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        from_id: int | None = None,
        limit: int | None = None,
        timestamp_ms: int | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {"symbol": symbol}
        if start_time_ms is not None:
            params["startTime"] = str(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = str(end_time_ms)
        if from_id is not None:
            params["fromId"] = str(from_id)
        if limit is not None:
            params["limit"] = str(limit)
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/userTrades",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_all_orders(
        self,
        *,
        symbol: str,
        start_time_ms: int | None = None,
        end_time_ms: int | None = None,
        limit: int | None = None,
        timestamp_ms: int | None = None,
    ) -> list[dict]:
        params: dict[str, str] = {"symbol": symbol}
        if start_time_ms is not None:
            params["startTime"] = str(start_time_ms)
        if end_time_ms is not None:
            params["endTime"] = str(end_time_ms)
        if limit is not None:
            params["limit"] = str(limit)
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/allOrders",
            params=params,
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

    def cancel_algo_order(
        self,
        *,
        algo_id: int | None = None,
        client_algo_id: str | None = None,
        timestamp_ms: int | None = None,
    ) -> dict:
        params: dict[str, str] = {}
        if algo_id is not None:
            params["algoId"] = str(algo_id)
        if client_algo_id is not None:
            params["clientAlgoId"] = client_algo_id
        request = self.build_signed_request(
            method="DELETE",
            path="/fapi/v1/algoOrder",
            params=params,
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)

    def fetch_position_mode(self, *, timestamp_ms: int | None = None) -> dict:
        request = self.build_signed_request(
            method="GET",
            path="/fapi/v1/positionSide/dual",
            params={},
            timestamp_ms=timestamp_ms,
        )
        return self.send(request)
