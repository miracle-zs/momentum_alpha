from __future__ import annotations

from collections.abc import Mapping
from decimal import Decimal


def _object_field(value: object, field_name: str) -> object | None:
    if isinstance(value, Mapping):
        return value.get(field_name)
    return getattr(value, field_name, None)


def _parse_decimal(value: object | None) -> Decimal | None:
    if value is None or value == "":
        return None
    try:
        return Decimal(str(value))
    except Exception:
        return None


def compute_position_risk(position: object) -> Decimal | None:
    if not isinstance(position, Mapping) and not hasattr(position, "__dict__") and not hasattr(type(position), "__dataclass_fields__"):
        return None

    direction = str(_object_field(position, "side") or _object_field(position, "direction") or "LONG").upper()
    legs = _object_field(position, "legs") or []
    stop_price = _parse_decimal(_object_field(position, "stop_price"))
    if stop_price is not None and stop_price <= 0:
        stop_price = None

    total_quantity = Decimal("0")
    weighted_entry_sum = Decimal("0")
    weighted_stop_sum = Decimal("0")
    leg_stop_values_known = True
    leg_seen = False

    if isinstance(legs, (list, tuple)) and legs:
        for leg in legs:
            if not isinstance(leg, Mapping) and not hasattr(leg, "__dict__") and not hasattr(type(leg), "__dataclass_fields__"):
                continue
            qty = _parse_decimal(_object_field(leg, "quantity"))
            entry = _parse_decimal(_object_field(leg, "entry_price"))
            leg_stop = _parse_decimal(_object_field(leg, "stop_price"))
            if leg_stop is None:
                leg_stop = stop_price
            if qty is None or entry is None:
                continue
            leg_seen = True
            total_quantity += qty
            weighted_entry_sum += qty * entry
            if leg_stop is None:
                leg_stop_values_known = False
            else:
                weighted_stop_sum += qty * leg_stop
        if leg_seen and leg_stop_values_known and total_quantity > 0:
            if direction == "SHORT":
                return max(weighted_stop_sum - weighted_entry_sum, Decimal("0"))
            return max(weighted_entry_sum - weighted_stop_sum, Decimal("0"))

    if stop_price is None:
        return None

    if total_quantity <= 0:
        total_quantity = _parse_decimal(_object_field(position, "total_quantity")) or Decimal("0")
    avg_entry = _parse_decimal(_object_field(position, "weighted_avg_entry_price"))
    if avg_entry is None:
        avg_entry = _parse_decimal(_object_field(position, "entry_price"))
    if total_quantity <= 0 or avg_entry is None:
        return None

    if direction == "SHORT":
        return max(total_quantity * (stop_price - avg_entry), Decimal("0"))
    return max(total_quantity * (avg_entry - stop_price), Decimal("0"))


def build_position_risk_series(position_snapshots: list[dict]) -> list[dict]:
    series: list[dict] = []
    for snapshot in sorted(position_snapshots, key=lambda item: item.get("timestamp") or ""):
        timestamp = snapshot.get("timestamp")
        payload = snapshot.get("payload") or {}
        positions = payload.get("positions") or {}
        if not timestamp or not isinstance(positions, Mapping):
            continue

        snapshot_risk = Decimal("0")
        snapshot_has_risk = False
        for position in positions.values():
            risk = compute_position_risk(position)
            if risk is None:
                continue
            snapshot_risk += risk
            snapshot_has_risk = True
        if snapshot_has_risk:
            series.append({"timestamp": timestamp, "open_risk": float(snapshot_risk)})
    return series
