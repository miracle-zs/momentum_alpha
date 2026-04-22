from __future__ import annotations

from decimal import Decimal

from .runtime_analytics_common import _text_to_optional_decimal
from .runtime_analytics_legs import _strategy_stop_client_order_id


def _resolve_stop_trigger_price_for_exit(
    *,
    exit_fills: list[dict],
    symbol: str,
    stop_trigger_by_client_order_id: dict[str, Decimal],
    algo_by_symbol: dict[str, list[dict]],
) -> Decimal | None:
    for exit_fill in reversed(exit_fills):
        stop_client_order_id = _strategy_stop_client_order_id(exit_fill["client_order_id"])
        if stop_client_order_id is None:
            continue
        trigger_price = stop_trigger_by_client_order_id.get(stop_client_order_id)
        if trigger_price is not None:
            return trigger_price
    for algo_row in reversed(algo_by_symbol.get(symbol, [])):
        if algo_row["timestamp"] <= exit_fills[-1]["timestamp"] and algo_row["order_type"] == "STOP_MARKET":
            trigger_price = algo_row["trigger_price"]
            if trigger_price is not None:
                return trigger_price
    return None


def _extract_stop_trigger_price_from_broker_order(
    *,
    order_type: str | None,
    price: object | None,
    payload: object | None,
) -> Decimal | None:
    if order_type != "STOP_MARKET":
        return None
    parsed_price = _text_to_optional_decimal(price)
    if parsed_price is not None:
        return parsed_price
    if not isinstance(payload, dict):
        return None
    return _text_to_optional_decimal(payload.get("stopPrice") or payload.get("price"))


def _extract_stop_trigger_price_from_signal_decision(payload: dict) -> Decimal | None:
    stop_price = payload.get("stop_price")
    if stop_price in (None, ""):
        return None
    return _text_to_optional_decimal(stop_price)
