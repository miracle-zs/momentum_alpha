from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from momentum_alpha.orders import is_strategy_client_order_id
from momentum_alpha.runtime_schema import _connect

from .runtime_analytics_common import _as_utc_iso, _decimal_to_text, _json_dumps, _json_loads, _text_to_decimal, _text_to_optional_decimal
from .runtime_analytics_legs import _build_trade_round_trip_leg_payload, _strategy_stop_client_order_id
from .runtime_analytics_stops import (
    _extract_stop_trigger_price_from_broker_order,
    _extract_stop_trigger_price_from_signal_decision,
    _resolve_stop_trigger_price_for_exit,
)


def _snapshot_position_risk(position: object) -> Decimal | None:
    if not isinstance(position, Mapping):
        return None
    legs = position.get("legs") or []
    if not isinstance(legs, (list, tuple)) or not legs:
        return None
    direction = str(position.get("side") or position.get("direction") or "LONG").upper()
    stop_price = _snapshot_position_stop_price(position)
    if stop_price is None:
        return None
    return _position_net_risk(legs=legs, stop_price=stop_price, direction=direction)


def _snapshot_position_stop_price(position: object) -> Decimal | None:
    if not isinstance(position, Mapping):
        return None
    stop_price = _text_to_optional_decimal(position.get("stop_price"))
    if stop_price is not None and stop_price > Decimal("0"):
        return stop_price
    legs = position.get("legs") or []
    if not isinstance(legs, (list, tuple)) or not legs:
        return None
    candidate_stop_prices: list[Decimal] = []
    for leg in legs:
        if not isinstance(leg, Mapping):
            continue
        leg_stop = _text_to_optional_decimal(leg.get("stop_price"))
        if leg_stop is None or leg_stop <= Decimal("0"):
            continue
        candidate_stop_prices.append(leg_stop)
    if not candidate_stop_prices:
        return None
    first_stop = candidate_stop_prices[0]
    if any(leg_stop != first_stop for leg_stop in candidate_stop_prices[1:]):
        return None
    return first_stop


def _position_net_risk(
    *,
    legs: list[Mapping],
    stop_price: Decimal,
    direction: str,
) -> Decimal | None:
    net_pnl_at_stop = Decimal("0")
    known = False
    for leg in legs:
        if not isinstance(leg, Mapping):
            continue
        qty = _text_to_decimal(leg.get("quantity"))
        entry = _text_to_optional_decimal(leg.get("entry_price"))
        if qty is None or entry is None:
            return None
        known = True
        if direction == "SHORT":
            net_pnl_at_stop += (entry - stop_price) * qty
        else:
            net_pnl_at_stop += (stop_price - entry) * qty
    if not known:
        return None
    return max(-net_pnl_at_stop, Decimal("0"))


def _snapshot_position_has_valid_stop(position: object) -> bool:
    if not isinstance(position, Mapping):
        return False
    stop_price = _text_to_optional_decimal(position.get("stop_price"))
    if stop_price is not None and stop_price > Decimal("0"):
        return True
    legs = position.get("legs") or []
    if not isinstance(legs, (list, tuple)):
        return False
    for leg in legs:
        if not isinstance(leg, Mapping):
            continue
        leg_stop = _text_to_optional_decimal(leg.get("stop_price"))
        if leg_stop is not None and leg_stop > Decimal("0"):
            return True
    return False


def _timeline_peak_cumulative_risk(
    *,
    legs: list[dict],
    opened_at: datetime,
    closed_at: datetime,
    trade_side: str | None,
    stop_events: list[tuple[datetime, Decimal]],
) -> Decimal | None:
    if not legs:
        return None

    normalized_legs: list[dict] = []
    for leg in legs:
        leg_opened_at = datetime.fromisoformat(str(leg.get("opened_at") or ""))
        if leg_opened_at < opened_at or leg_opened_at > closed_at:
            continue
        quantity = _text_to_optional_decimal(leg.get("quantity"))
        entry_price = _text_to_optional_decimal(leg.get("entry_price"))
        stop_price_at_entry = _text_to_optional_decimal(leg.get("stop_price_at_entry"))
        if quantity is None or entry_price is None:
            return None
        normalized_legs.append(
            {
                "opened_at": leg_opened_at,
                "quantity": quantity,
                "entry_price": entry_price,
                "stop_price_at_entry": stop_price_at_entry,
            }
        )

    if not normalized_legs:
        return None

    timeline_points = sorted(
        {
            *(leg["opened_at"] for leg in normalized_legs),
            *(timestamp for timestamp, _ in stop_events if opened_at <= timestamp <= closed_at),
        }
    )
    if not timeline_points:
        return None

    peak_risk: Decimal | None = None
    current_stop: Decimal | None = None
    stop_index = 0
    for timeline_point in timeline_points:
        while stop_index < len(stop_events) and stop_events[stop_index][0] <= timeline_point:
            current_stop = stop_events[stop_index][1]
            stop_index += 1

        active_legs = [leg for leg in normalized_legs if leg["opened_at"] <= timeline_point]
        if not active_legs:
            continue

        effective_stop = current_stop
        if effective_stop is None:
            stop_candidates = [leg["stop_price_at_entry"] for leg in active_legs if leg["stop_price_at_entry"] is not None and leg["stop_price_at_entry"] > Decimal("0")]
            if stop_candidates:
                if trade_side == "SELL":
                    effective_stop = min(stop_candidates)
                else:
                    effective_stop = max(stop_candidates)
        if effective_stop is None:
            continue

        direction = "SHORT" if trade_side == "SELL" else "LONG"
        risk = _position_net_risk(
            legs=[
                {
                    "quantity": _decimal_to_text(leg["quantity"]),
                    "entry_price": _decimal_to_text(leg["entry_price"]),
                }
                for leg in active_legs
            ],
            stop_price=effective_stop,
            direction=direction,
        )
        if risk is None:
            continue
        if peak_risk is None or risk > peak_risk:
            peak_risk = risk

    return peak_risk


def _snapshot_peak_cumulative_risk(
    *,
    snapshot_rows: list[tuple[str, str | None]],
    symbol: str,
    opened_at: datetime,
    closed_at: datetime,
) -> Decimal | None:
    peak_risk: Decimal | None = None
    current_timestamp_text: str | None = None
    current_timestamp_risk: Decimal | None = None
    for timestamp_text, payload_json in snapshot_rows:
        snapshot_time = datetime.fromisoformat(timestamp_text)
        if snapshot_time < opened_at or snapshot_time > closed_at:
            continue
        if current_timestamp_text is not None and timestamp_text != current_timestamp_text:
            if current_timestamp_risk is not None and (peak_risk is None or current_timestamp_risk > peak_risk):
                peak_risk = current_timestamp_risk
            current_timestamp_risk = None
        current_timestamp_text = timestamp_text
        payload = _json_loads(payload_json or "{}")
        positions = payload.get("positions") or {}
        if not isinstance(positions, Mapping):
            continue
        position = positions.get(symbol)
        if not _snapshot_position_has_valid_stop(position):
            continue
        risk = _snapshot_position_risk(position)
        if risk is None:
            continue
        current_timestamp_risk = risk
    if current_timestamp_risk is not None and (peak_risk is None or current_timestamp_risk > peak_risk):
        peak_risk = current_timestamp_risk
    return peak_risk


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
        snapshot_rows = connection.execute(
            """
            SELECT timestamp, payload_json
            FROM position_snapshots
            ORDER BY timestamp ASC, id ASC
            """
        ).fetchall()
        connection.execute("DELETE FROM trade_round_trips")
        connection.execute("DELETE FROM stop_exit_summaries")

        algo_by_symbol: dict[str, list[dict]] = {}
        stop_trigger_by_client_order_id: dict[str, Decimal] = {}
        stop_events_by_symbol: dict[str, list[tuple[datetime, Decimal]]] = {}
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
            payload = _json_loads(payload_json)
            if not symbol or not client_order_id:
                client_order_id = payload.get("clientAlgoId") or payload.get("clientOrderId")
            if not symbol or not client_order_id:
                continue
            trigger_price = _extract_stop_trigger_price_from_broker_order(
                order_type=order_type,
                price=price,
                payload=payload,
            )
            if trigger_price is None:
                continue
            stop_events_by_symbol.setdefault(symbol, []).append((datetime.fromisoformat(timestamp), trigger_price))
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
            stop_events = stop_events_by_symbol.get(symbol, [])
            if stop_events:
                trade_side = str(entry_fills[0]["side"] or "").upper() if entry_fills else None
                timeline_peak_cumulative_risk = _timeline_peak_cumulative_risk(
                    legs=legs,
                    opened_at=round_trip["opened_at"],
                    closed_at=closed_at,
                    trade_side=trade_side,
                    stop_events=stop_events,
                )
                if timeline_peak_cumulative_risk is not None:
                    peak_cumulative_risk = timeline_peak_cumulative_risk
                else:
                    snapshot_peak_cumulative_risk = _snapshot_peak_cumulative_risk(
                        snapshot_rows=snapshot_rows,
                        symbol=symbol,
                        opened_at=round_trip["opened_at"],
                        closed_at=closed_at,
                    )
                    if snapshot_peak_cumulative_risk is not None:
                        peak_cumulative_risk = snapshot_peak_cumulative_risk
            else:
                snapshot_peak_cumulative_risk = _snapshot_peak_cumulative_risk(
                    snapshot_rows=snapshot_rows,
                    symbol=symbol,
                    opened_at=round_trip["opened_at"],
                    closed_at=closed_at,
                )
                if snapshot_peak_cumulative_risk is not None:
                    peak_cumulative_risk = snapshot_peak_cumulative_risk
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
