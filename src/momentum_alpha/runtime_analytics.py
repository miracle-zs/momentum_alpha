from __future__ import annotations

import json
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.orders import is_strategy_client_order_id
from momentum_alpha.runtime_schema import _connect


def _json_dumps(payload: dict) -> str:
    return json.dumps(payload, ensure_ascii=False)


def _json_loads(payload: str) -> dict:
    return json.loads(payload)


def _as_utc_iso(timestamp: datetime) -> str:
    return timestamp.astimezone(timezone.utc).isoformat()


def _decimal_to_text(value: object | None) -> str | None:
    if value is None:
        return None
    return str(value)


def _text_to_decimal(value: object | None) -> Decimal:
    if value in (None, ""):
        return Decimal("0")
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return Decimal("0")


def _text_to_optional_decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError):
        return None


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


def rebuild_trade_analytics(*, path: Path) -> None:
    if not path.exists():
        return
    with _connect(path) as connection:
        fill_rows = connection.execute(
            """
            SELECT
                timestamp,
                symbol,
                side,
                order_type,
                quantity,
                average_price,
                last_price,
                realized_pnl,
                commission,
                commission_asset,
                order_id,
                trade_id,
                client_order_id
            FROM trade_fills
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        algo_rows = connection.execute(
            """
            SELECT timestamp, symbol, trigger_price, algo_status, order_type, client_algo_id
            FROM algo_orders
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        signal_rows = connection.execute(
            """
            SELECT timestamp, symbol, decision_type, payload_json
            FROM signal_decisions
            WHERE decision_type IN ('base_entry', 'add_on', 'stop_update')
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        broker_rows = connection.execute(
            """
            SELECT timestamp, symbol, order_type, client_order_id, price, payload_json
            FROM broker_orders
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        connection.execute("DELETE FROM trade_round_trips")
        connection.execute("DELETE FROM stop_exit_summaries")

        algo_by_symbol: dict[str, list[dict]] = {}
        stop_trigger_by_client_order_id: dict[str, Decimal] = {}
        for timestamp, symbol, trigger_price, algo_status, order_type, client_algo_id in algo_rows:
            if not symbol:
                continue
            parsed_trigger_price = _text_to_optional_decimal(trigger_price)
            algo_by_symbol.setdefault(symbol, []).append(
                {
                    "timestamp": timestamp,
                    "trigger_price": parsed_trigger_price,
                    "algo_status": algo_status,
                    "order_type": order_type,
                    "client_algo_id": client_algo_id,
                }
            )
            if client_algo_id and parsed_trigger_price is not None:
                stop_trigger_by_client_order_id[client_algo_id] = parsed_trigger_price
        signal_stop_price_by_symbol: dict[str, list[dict]] = {}
        for timestamp, symbol, decision_type, payload_json in signal_rows:
            if not symbol:
                continue
            payload = _json_loads(payload_json)
            parsed_stop_price = _extract_stop_trigger_price_from_signal_decision(payload)
            if parsed_stop_price is None:
                continue
            signal_stop_price_by_symbol.setdefault(symbol, []).append(
                {
                    "timestamp": datetime.fromisoformat(timestamp),
                    "decision_type": decision_type,
                    "leg_type": payload.get("leg_type"),
                    "stop_price": parsed_stop_price,
                }
            )
        for timestamp, symbol, order_type, client_order_id, price, payload_json in broker_rows:
            if not symbol or not client_order_id:
                continue
            trigger_price = _extract_stop_trigger_price_from_broker_order(
                order_type=order_type,
                price=price,
                payload=_json_loads(payload_json),
            )
            if trigger_price is None:
                continue
            stop_trigger_by_client_order_id.setdefault(client_order_id, trigger_price)
            if is_strategy_client_order_id(client_order_id):
                stop_client_order_id = _strategy_stop_client_order_id(client_order_id)
                if stop_client_order_id is not None:
                    stop_trigger_by_client_order_id.setdefault(stop_client_order_id, trigger_price)

        active_round_trips: dict[str, dict] = {}
        symbol_counters: dict[str, int] = {}

        for (
            timestamp,
            symbol,
            side,
            order_type,
            quantity,
            average_price,
            last_price,
            realized_pnl,
            commission,
            commission_asset,
            order_id,
            trade_id,
            client_order_id,
        ) in fill_rows:
            if not symbol:
                continue
            qty = _text_to_decimal(quantity)
            if qty <= Decimal("0"):
                continue
            fill_time = datetime.fromisoformat(timestamp)
            fill_price = _text_to_decimal(average_price) or _text_to_decimal(last_price)
            fill_snapshot = {
                "timestamp": timestamp,
                "time": fill_time,
                "side": side,
                "order_type": order_type,
                "quantity": qty,
                "price": fill_price,
                "realized_pnl": _text_to_decimal(realized_pnl),
                "commission": _text_to_decimal(commission),
                "commission_asset": commission_asset,
                "order_id": order_id,
                "trade_id": trade_id,
                "client_order_id": client_order_id,
            }

            round_trip = active_round_trips.get(symbol)
            if side == "BUY":
                if round_trip is None or round_trip["net_quantity"] <= Decimal("0"):
                    sequence = symbol_counters.get(symbol, 0) + 1
                    symbol_counters[symbol] = sequence
                    round_trip = {
                        "round_trip_id": f"{symbol}:{sequence}",
                        "symbol": symbol,
                        "opened_at": fill_time,
                        "entry_fills": [],
                        "exit_fills": [],
                        "net_quantity": Decimal("0"),
                    }
                    active_round_trips[symbol] = round_trip
                round_trip["entry_fills"].append(fill_snapshot)
                round_trip["net_quantity"] += qty
                continue

            if side != "SELL" or round_trip is None:
                continue

            round_trip["exit_fills"].append(fill_snapshot)
            round_trip["net_quantity"] -= qty
            if round_trip["net_quantity"] > Decimal("0"):
                continue

            entry_fills = round_trip["entry_fills"]
            exit_fills = round_trip["exit_fills"]
            total_entry_qty = sum((item["quantity"] for item in entry_fills), Decimal("0"))
            total_exit_qty = sum((item["quantity"] for item in exit_fills), Decimal("0"))
            if total_entry_qty <= Decimal("0") or total_exit_qty <= Decimal("0"):
                active_round_trips.pop(symbol, None)
                continue
            weighted_entry = sum((item["quantity"] * item["price"] for item in entry_fills), Decimal("0")) / total_entry_qty
            weighted_exit = sum((item["quantity"] * item["price"] for item in exit_fills), Decimal("0")) / total_exit_qty
            realized_total = sum((item["realized_pnl"] for item in [*entry_fills, *exit_fills]), Decimal("0"))
            commission_total = sum((item["commission"] for item in [*entry_fills, *exit_fills]), Decimal("0"))
            net_total = realized_total - commission_total
            closed_at = exit_fills[-1]["time"]
            has_stop_market_exit = any(item["order_type"] == "STOP_MARKET" for item in exit_fills)
            has_strategy_stop_client_id = any(
                is_strategy_client_order_id(item["client_order_id"]) and str(item["client_order_id"]).endswith("s")
                for item in exit_fills
            )
            has_triggered_stop_algo = any(
                algo_row["timestamp"] <= exit_fills[-1]["timestamp"]
                and algo_row["order_type"] == "STOP_MARKET"
                and algo_row["algo_status"] == "TRIGGERED"
                and is_strategy_client_order_id(algo_row["client_algo_id"])
                for algo_row in algo_by_symbol.get(symbol, [])
            )
            exit_reason = (
                "stop_loss"
                if has_stop_market_exit or has_strategy_stop_client_id or has_triggered_stop_algo
                else "sell"
            )
            duration_seconds = int((closed_at - round_trip["opened_at"]).total_seconds())
            legs, base_leg_risk, peak_cumulative_risk = _build_trade_round_trip_leg_payload(
                entry_fills=entry_fills,
                total_entry_qty=total_entry_qty,
                weighted_exit_price=weighted_exit,
                commission_total=commission_total,
                stop_trigger_by_client_order_id=stop_trigger_by_client_order_id,
                signal_stop_price_candidates=signal_stop_price_by_symbol.get(symbol, []),
            )
            round_trip_payload = {
                "entry_order_ids": [item["order_id"] for item in entry_fills if item["order_id"] is not None],
                "exit_order_ids": [item["order_id"] for item in exit_fills if item["order_id"] is not None],
                "entry_trade_ids": [item["trade_id"] for item in entry_fills if item["trade_id"] is not None],
                "exit_trade_ids": [item["trade_id"] for item in exit_fills if item["trade_id"] is not None],
                "leg_count": len(legs),
                "add_on_leg_count": max(len(legs) - 1, 0),
                "base_leg_risk": _decimal_to_text(base_leg_risk),
                "peak_cumulative_risk": _decimal_to_text(peak_cumulative_risk),
                "legs": legs,
            }
            connection.execute(
                """
                INSERT INTO trade_round_trips(
                    round_trip_id,
                    symbol,
                    opened_at,
                    closed_at,
                    entry_fill_count,
                    exit_fill_count,
                    total_entry_quantity,
                    total_exit_quantity,
                    weighted_avg_entry_price,
                    weighted_avg_exit_price,
                    realized_pnl,
                    commission,
                    net_pnl,
                    exit_reason,
                    duration_seconds,
                    payload_json
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    round_trip["round_trip_id"],
                    symbol,
                    _as_utc_iso(round_trip["opened_at"]),
                    _as_utc_iso(closed_at),
                    len(entry_fills),
                    len(exit_fills),
                    _decimal_to_text(total_entry_qty),
                    _decimal_to_text(total_exit_qty),
                    _decimal_to_text(weighted_entry),
                    _decimal_to_text(weighted_exit),
                    _decimal_to_text(realized_total),
                    _decimal_to_text(commission_total),
                    _decimal_to_text(net_total),
                    exit_reason,
                    duration_seconds,
                    _json_dumps(round_trip_payload),
                ),
            )
            if exit_reason == "stop_loss":
                trigger_price = _resolve_stop_trigger_price_for_exit(
                    exit_fills=exit_fills,
                    symbol=symbol,
                    stop_trigger_by_client_order_id=stop_trigger_by_client_order_id,
                    algo_by_symbol=algo_by_symbol,
                )
                slippage_abs = None
                slippage_pct = None
                if trigger_price is not None and trigger_price > Decimal("0"):
                    slippage_abs = max(trigger_price - weighted_exit, Decimal("0"))
                    slippage_pct = (slippage_abs / trigger_price) * Decimal("100")
                connection.execute(
                    """
                    INSERT INTO stop_exit_summaries(
                        timestamp,
                        symbol,
                        round_trip_id,
                        trigger_price,
                        average_exit_price,
                        slippage_abs,
                        slippage_pct,
                        exit_quantity,
                        realized_pnl,
                        commission,
                        net_pnl,
                        payload_json
                    ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                    """,
                    (
                        _as_utc_iso(closed_at),
                        symbol,
                        round_trip["round_trip_id"],
                        _decimal_to_text(trigger_price),
                        _decimal_to_text(weighted_exit),
                        _decimal_to_text(slippage_abs),
                        _decimal_to_text(slippage_pct),
                        _decimal_to_text(total_exit_qty),
                        _decimal_to_text(realized_total),
                        _decimal_to_text(commission_total),
                        _decimal_to_text(net_total),
                        _json_dumps({"entry_fill_count": len(entry_fills), "exit_fill_count": len(exit_fills)}),
                    ),
                )
            active_round_trips.pop(symbol, None)
