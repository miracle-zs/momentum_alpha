from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from decimal import Decimal

from .dashboard_common import _parse_numeric
from .dashboard_position_risk import compute_position_risk
from .dashboard_view_model_common import _object_field, _parse_decimal


def build_position_details(position_snapshot: dict, equity_value: object | None = None) -> list[dict]:
    """Extract position details with leg breakdown from position snapshot payload."""
    payload = position_snapshot.get("payload") or {}
    positions = payload.get("positions") or {}
    if not positions or not isinstance(positions, Mapping):
        return []

    equity_decimal = _parse_decimal(equity_value)
    details: list[dict] = []
    for symbol, position in positions.items():
        if not isinstance(position, Mapping) and not hasattr(position, "__dict__") and not hasattr(type(position), "__dataclass_fields__"):
            continue
        legs = _object_field(position, "legs") or []
        stop_price = _parse_decimal(_object_field(position, "stop_price"))
        if stop_price is not None and stop_price <= 0:
            stop_price = None
        latest_price = _parse_numeric(_object_field(position, "latest_price"))
        direction = str(_object_field(position, "side") or _object_field(position, "direction") or "LONG").upper()
        total_quantity = Decimal("0")
        weighted_sum = Decimal("0")
        weighted_stop_sum = Decimal("0")
        leg_stop_values_known = True
        leg_info: list[dict] = []
        valid_leg_opened_ats: list[str] = []
        if isinstance(legs, (list, tuple)) and legs:
            for leg in legs:
                if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                    continue
                qty = _parse_decimal(_object_field(leg, "quantity")) or Decimal("0")
                entry = _parse_decimal(_object_field(leg, "entry_price")) or Decimal("0")
                leg_stop = _parse_decimal(_object_field(leg, "stop_price"))
                total_quantity += qty
                weighted_sum += qty * entry
                if leg_stop is None:
                    leg_stop_values_known = False
                else:
                    weighted_stop_sum += qty * leg_stop
                leg_opened_at = _object_field(leg, "opened_at")
                if leg_opened_at is not None:
                    valid_leg_opened_ats.append(str(leg_opened_at))
                leg_info.append({
                    "type": _object_field(leg, "leg_type") or "unknown",
                    "time": str(leg_opened_at) if leg_opened_at is not None else "",
                })
        else:
            total_quantity = _parse_decimal(_object_field(position, "total_quantity")) or Decimal("0")
            avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
            if avg_entry is None:
                avg_entry = _parse_decimal(_object_field(position, "entry_price"))
            if total_quantity > 0 and avg_entry is not None:
                weighted_sum = total_quantity * avg_entry

        if total_quantity <= 0:
            continue
        if weighted_sum <= 0 and not leg_info:
            avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
            if avg_entry is None:
                avg_entry = _parse_decimal(_object_field(position, "entry_price"))
            if avg_entry is None:
                continue
            weighted_sum = total_quantity * avg_entry

        avg_entry = weighted_sum / total_quantity if total_quantity > 0 else Decimal("0")
        risk = compute_position_risk(position)
        opened_at = _object_field(position, "opened_at")
        if not opened_at:
            parsed_leg_opened_ats: list[tuple[datetime, str]] = []
            for leg_opened_at in valid_leg_opened_ats:
                try:
                    parsed_leg_opened_ats.append((datetime.fromisoformat(str(leg_opened_at)), str(leg_opened_at)))
                except ValueError:
                    continue
            if parsed_leg_opened_ats:
                opened_at = min(parsed_leg_opened_ats, key=lambda item: item[0])[1]
            elif valid_leg_opened_ats:
                opened_at = valid_leg_opened_ats[0]
        risk_pct_of_equity = None
        if risk is not None and equity_decimal not in (None, Decimal("0")):
            risk_pct_of_equity = f"{((risk / equity_decimal) * Decimal('100')):.2f}"
        notional_exposure = None
        mtm_pnl = None
        pnl_pct = None
        distance_to_stop_pct = None
        r_multiple = None
        if latest_price is not None:
            notional_exposure = float(total_quantity * Decimal(str(latest_price)))
            if direction == "SHORT":
                mtm_pnl = float((avg_entry - Decimal(str(latest_price))) * total_quantity)
            else:
                mtm_pnl = float((Decimal(str(latest_price)) - avg_entry) * total_quantity)
            entry_notional = total_quantity * avg_entry
            if entry_notional not in (None, Decimal("0")):
                pnl_pct = float((Decimal(str(mtm_pnl)) / entry_notional) * Decimal("100"))
            if risk not in (None, Decimal("0")):
                r_multiple = float(Decimal(str(mtm_pnl)) / risk)
            effective_stop_price = stop_price
            if leg_info and leg_stop_values_known and total_quantity > 0:
                effective_stop_price = weighted_stop_sum / total_quantity
            if effective_stop_price is not None and latest_price > 0:
                if direction == "SHORT":
                    distance_to_stop_pct = float(((effective_stop_price - Decimal(str(latest_price))) / Decimal(str(latest_price))) * Decimal("100"))
                else:
                    distance_to_stop_pct = float(((Decimal(str(latest_price)) - effective_stop_price) / Decimal(str(latest_price))) * Decimal("100"))

        details.append({
            "symbol": symbol,
            "direction": direction,
            "total_quantity": str(total_quantity),
            "entry_price": f"{avg_entry:.2f}",
            "stop_price": str(stop_price) if stop_price is not None else None,
            "risk": f"{risk:.2f}" if risk is not None else None,
            "risk_pct_of_equity": risk_pct_of_equity,
            "leg_count": len(leg_info),
            "opened_at": opened_at,
            "latest_price": latest_price,
            "mtm_pnl": mtm_pnl,
            "pnl_pct": pnl_pct,
            "distance_to_stop_pct": distance_to_stop_pct,
            "notional_exposure": notional_exposure,
            "r_multiple": r_multiple,
            "legs": leg_info,
        })

    return details
