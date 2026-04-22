from __future__ import annotations

from decimal import Decimal

from momentum_alpha.orders import is_strategy_client_order_id

from .runtime_analytics_common import _decimal_to_text, _text_to_decimal


def _strategy_stop_client_order_id(client_order_id: str | None) -> str | None:
    if not is_strategy_client_order_id(client_order_id):
        return None
    if client_order_id is None:
        return None
    if client_order_id.endswith("s"):
        return client_order_id
    if not client_order_id.endswith("e"):
        return None
    return f"{client_order_id[:-1]}s"


def _trade_leg_type_from_client_order_id(client_order_id: str | None, leg_index: int) -> str:
    if is_strategy_client_order_id(client_order_id) and client_order_id is not None:
        token_index = len(client_order_id) - 4
        if token_index >= 0:
            token = client_order_id[token_index]
            if token == "b":
                return "base"
            if token == "a":
                return "add_on"
    return "base" if leg_index == 1 else "add_on"


def _build_trade_round_trip_leg_payload(
    *,
    entry_fills: list[dict],
    total_entry_qty: Decimal,
    weighted_exit_price: Decimal | None,
    commission_total: Decimal,
    stop_trigger_by_client_order_id: dict[str, Decimal],
    signal_stop_price_candidates: list[dict],
) -> tuple[list[dict], Decimal | None, Decimal | None]:
    grouped_entry_fills: list[dict] = []
    grouped_index_by_key: dict[str, int] = {}
    for item in entry_fills:
        group_key = str(item.get("client_order_id") or item.get("order_id") or item.get("timestamp") or len(grouped_entry_fills))
        group_index = grouped_index_by_key.get(group_key)
        if group_index is None:
            grouped_index_by_key[group_key] = len(grouped_entry_fills)
            grouped_entry_fills.append(
                {
                    "timestamp": item["timestamp"],
                    "time": item["time"],
                    "client_order_id": item["client_order_id"],
                    "quantity": item["quantity"],
                    "price": item["price"],
                }
            )
            continue
        grouped = grouped_entry_fills[group_index]
        grouped["quantity"] += item["quantity"]
        if item["price"] is not None and item["quantity"] is not None:
            grouped["price"] = (
                (grouped["price"] * (grouped["quantity"] - item["quantity"])) + (item["price"] * item["quantity"])
            ) / grouped["quantity"]
        if item["time"] < grouped["time"]:
            grouped["time"] = item["time"]
            grouped["timestamp"] = item["timestamp"]

    legs: list[dict] = []
    cumulative_risk = Decimal("0")
    all_leg_risks_known = True

    for leg_index, item in enumerate(grouped_entry_fills, start=1):
        client_order_id = item["client_order_id"]
        stop_client_order_id = _strategy_stop_client_order_id(client_order_id)
        leg_type = _trade_leg_type_from_client_order_id(client_order_id, leg_index)
        stop_price_at_entry = (
            stop_trigger_by_client_order_id.get(stop_client_order_id) if stop_client_order_id is not None else None
        )
        if stop_price_at_entry is None and signal_stop_price_candidates:
            leg_time = item["time"]
            same_type_candidates = [
                candidate
                for candidate in signal_stop_price_candidates
                if candidate["timestamp"] <= leg_time and candidate["leg_type"] == leg_type
            ]
            fallback_candidates = [
                candidate for candidate in signal_stop_price_candidates if candidate["timestamp"] <= leg_time
            ]
            chosen_candidate = (
                same_type_candidates[-1] if same_type_candidates else (fallback_candidates[-1] if fallback_candidates else None)
            )
            if chosen_candidate is not None:
                stop_price_at_entry = chosen_candidate["stop_price"]
        leg_risk = None
        if stop_price_at_entry is not None and item["price"] is not None:
            leg_risk = max((item["price"] - stop_price_at_entry) * item["quantity"], Decimal("0"))
        if leg_risk is None:
            all_leg_risks_known = False
            cumulative_risk_after_leg = None
        else:
            cumulative_risk += leg_risk
            cumulative_risk_after_leg = cumulative_risk if all_leg_risks_known else None

        gross_pnl_contribution = None
        if weighted_exit_price is not None and item["price"] is not None:
            gross_pnl_contribution = (weighted_exit_price - item["price"]) * item["quantity"]
        quantity_share = item["quantity"] / total_entry_qty if total_entry_qty > Decimal("0") else None
        fee_share = commission_total * quantity_share if quantity_share is not None else None
        net_pnl_contribution = (
            gross_pnl_contribution - fee_share
            if gross_pnl_contribution is not None and fee_share is not None
            else None
        )

        legs.append(
            {
                "leg_index": leg_index,
                "leg_type": leg_type,
                "opened_at": item["timestamp"],
                "quantity": _decimal_to_text(item["quantity"]),
                "entry_price": _decimal_to_text(item["price"]),
                "stop_price_at_entry": _decimal_to_text(stop_price_at_entry),
                "leg_risk": _decimal_to_text(leg_risk),
                "cumulative_risk_after_leg": _decimal_to_text(cumulative_risk_after_leg),
                "gross_pnl_contribution": _decimal_to_text(gross_pnl_contribution),
                "fee_share": _decimal_to_text(fee_share),
                "net_pnl_contribution": _decimal_to_text(net_pnl_contribution),
            }
        )

    base_leg_risk = _text_to_decimal(legs[0]["leg_risk"]) if legs and legs[0]["leg_risk"] is not None else None
    peak_cumulative_risk = cumulative_risk if all_leg_risks_known and legs else None
    return legs, base_leg_risk, peak_cumulative_risk
