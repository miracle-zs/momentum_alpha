from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal
from time import sleep as default_sleep
from typing import Callable
from urllib.error import URLError

from momentum_alpha.binance_client import BinanceHttpError
from momentum_alpha.execution import ExecutionPlan
from momentum_alpha.exchange_info import ExchangeSymbol, parse_exchange_info
from momentum_alpha.orders import build_stop_market_order, is_strategy_client_order_id
from momentum_alpha.trace_ids import build_symbol_token

logger = logging.getLogger(__name__)


def _build_replacement_stop_client_order_id(symbol: str, *, now: datetime | None = None) -> str:
    resolved_now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    timestamp_token = resolved_now.strftime("%y%m%d%H%M%S") + f"{resolved_now.microsecond // 1000:03d}"
    symbol_token = build_symbol_token(symbol, max_length=10)
    return f"ma_{timestamp_token}_{symbol_token}_r00s"


def _is_order_not_found_error(exc: Exception) -> bool:
    if not isinstance(exc, BinanceHttpError):
        return False
    try:
        payload = json.loads(exc.response_body or "{}")
    except json.JSONDecodeError:
        return False
    return payload.get("code") == -2013


def _is_transient_entry_error(exc: Exception) -> bool:
    if isinstance(exc, (URLError, TimeoutError)):
        return True
    if isinstance(exc, BinanceHttpError):
        return exc.status_code in {408, 500, 502, 503, 504}
    return False


def _is_rate_limit_error(exc: Exception) -> bool:
    return isinstance(exc, BinanceHttpError) and exc.status_code in {418, 429}


@dataclass
class BinanceBroker:
    client: object
    entry_retry_delays: tuple[float, ...] = (0.2, 0.5)
    sleep_fn: Callable[[float], None] = default_sleep
    last_stop_replacement_failures: list[dict[str, str]] = field(default_factory=list, init=False)
    last_entry_order_failures: list[dict[str, object]] = field(default_factory=list, init=False)
    last_stop_order_failures: list[dict[str, object]] = field(default_factory=list, init=False)
    _exchange_symbols: dict[str, ExchangeSymbol] | None = field(default=None, init=False, repr=False)

    def submit_execution_plan(self, plan: ExecutionPlan) -> list[dict]:
        responses: list[dict] = []
        submitted_entry_symbols: list[str | None] = []
        self.last_entry_order_failures = []
        self.last_stop_order_failures = []
        for order in plan.entry_orders:
            response = self._submit_entry_order(order)
            if response is not None:
                responses.append(response)
                submitted_entry_symbols.append(order.get("symbol"))
            else:
                submitted_entry_symbols.append(None)
        for index, order in enumerate(plan.stop_orders):
            if index < len(submitted_entry_symbols) and submitted_entry_symbols[index] is None:
                continue
            try:
                responses.append(self.client.send(self.client.new_algo_order(**order)))
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise
                logger.error(f"stop order failed for {order.get('symbol')}: {exc}")
                self.last_stop_order_failures.append(self._order_failure_payload(order, exc, "STOP_SUBMIT_FAILED"))
        return responses

    def _submit_entry_order(self, order: dict[str, str]) -> dict | None:
        attempts = len(self.entry_retry_delays) + 1
        last_error: Exception | None = None
        for attempt in range(attempts):
            try:
                return self.client.send(self.client.new_order(**order))
            except Exception as exc:
                last_error = exc
                if _is_rate_limit_error(exc):
                    raise
                if not _is_transient_entry_error(exc):
                    logger.error(f"entry order failed for {order.get('symbol')}: {exc}")
                    self.last_entry_order_failures.append(self._order_failure_payload(order, exc, "SUBMIT_FAILED", attempt + 1))
                    return None
                recovered = self._fetch_existing_entry_order(order)
                if recovered is not None:
                    recovered.setdefault("recoveredAfterSubmitError", True)
                    return recovered
                if attempt < len(self.entry_retry_delays):
                    self.sleep_fn(self.entry_retry_delays[attempt])
                    continue
                logger.error(f"entry order failed for {order.get('symbol')}: {exc}")
        if last_error is not None:
            self.last_entry_order_failures.append(self._order_failure_payload(order, last_error, "SUBMIT_FAILED", attempts))
        return None

    def _fetch_existing_entry_order(self, order: dict[str, str]) -> dict | None:
        fetch_order = getattr(self.client, "fetch_order", None)
        client_order_id = order.get("newClientOrderId")
        symbol = order.get("symbol")
        if not callable(fetch_order) or client_order_id is None or symbol is None:
            return None
        try:
            return fetch_order(symbol=symbol, orig_client_order_id=client_order_id)
        except Exception as exc:
            if _is_order_not_found_error(exc):
                return None
            logger.warning(f"entry order status lookup failed for {symbol}: {exc}")
            return None

    @staticmethod
    def _order_failure_payload(
        order: dict[str, str],
        exc: Exception,
        status: str,
        attempts: int | None = None,
    ) -> dict[str, object]:
        return {
            "symbol": order.get("symbol"),
            "side": order.get("side"),
            "type": order.get("type"),
            "quantity": order.get("quantity"),
            "clientOrderId": order.get("newClientOrderId"),
            "status": status,
            "error": str(exc),
            "errorType": type(exc).__name__,
            "attempts": attempts,
        }

    def _exchange_symbol_for_replacement(self, symbol: str) -> ExchangeSymbol | None:
        if self._exchange_symbols is None:
            fetch_exchange_info = getattr(self.client, "fetch_exchange_info", None)
            if not callable(fetch_exchange_info):
                return None
            self._exchange_symbols = parse_exchange_info(fetch_exchange_info())
        return self._exchange_symbols.get(symbol)

    def replace_stop_orders(self, *, replacements: list[tuple[str, str, str] | tuple[str, str, str, str | None]]) -> list[dict]:
        responses: list[dict] = []
        self.last_stop_replacement_failures = []
        for replacement in replacements:
            if len(replacement) == 3:
                symbol, quantity, stop_price = replacement
                position_side = None
            else:
                symbol, quantity, stop_price, position_side = replacement
            open_orders = self.client.fetch_open_algo_orders(symbol=symbol)
            strategy_stop_orders = []
            for order in open_orders:
                order_type = order.get("type") or order.get("orderType")
                client_algo_id = order.get("clientAlgoId")
                if order_type == "STOP_MARKET" and is_strategy_client_order_id(client_algo_id):
                    strategy_stop_orders.append(order)
            client_order_id = _build_replacement_stop_client_order_id(symbol)
            exchange_symbol = self._exchange_symbol_for_replacement(symbol)
            if exchange_symbol is None:
                order_params = {
                    "symbol": symbol,
                    "side": "SELL",
                    "type": "STOP_MARKET",
                    "quantity": quantity,
                    "stopPrice": stop_price,
                    "workingType": "CONTRACT_PRICE",
                    "newClientOrderId": client_order_id,
                }
                if position_side is not None:
                    order_params["positionSide"] = position_side
                else:
                    order_params["reduceOnly"] = "true"
            else:
                try:
                    order_params = build_stop_market_order(
                        symbol=exchange_symbol,
                        quantity=Decimal(str(quantity)),
                        stop_price=Decimal(str(stop_price)),
                        client_order_id=client_order_id,
                        position_side=position_side,
                    )
                except Exception as exc:
                    logger.error(f"replacement stop order build failed for {symbol}: {exc}")
                    self.last_stop_replacement_failures.append(
                        {
                            "symbol": symbol,
                            "quantity": quantity,
                            "stop_price": stop_price,
                            "message": str(exc),
                        }
                    )
                    continue
            try:
                responses.append(
                    self.client.send(self.client.new_algo_order(**order_params))
                )
            except Exception as exc:
                if _is_rate_limit_error(exc):
                    raise
                logger.error(f"replacement stop order failed for {symbol}: {exc}")
                self.last_stop_replacement_failures.append(
                    {
                        "symbol": symbol,
                        "quantity": quantity,
                        "stop_price": stop_price,
                        "message": str(exc),
                    }
                )
                continue
            for order in strategy_stop_orders:
                client_algo_id = order.get("clientAlgoId")
                try:
                    self.client.cancel_algo_order(
                        algo_id=order.get("algoId"),
                        client_algo_id=client_algo_id,
                    )
                except Exception as exc:
                    logger.error(f"old stop cancellation failed for {symbol}: {exc}")
        return responses
