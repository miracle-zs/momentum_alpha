from __future__ import annotations

from datetime import datetime, timezone


def build_decision_id(*, now: datetime) -> str:
    resolved_now = now.astimezone(timezone.utc)
    return f"dec_{resolved_now.strftime('%y%m%d%H%M%S%f')}"


def build_order_intent_id(*, symbol: str, opened_at: datetime, leg_type: str, sequence: int) -> str:
    timestamp_token = opened_at.astimezone(timezone.utc).strftime("%y%m%d%H%M%S")
    symbol_token = "".join(ch for ch in symbol.upper() if ch.isalnum())[-10:] or "UNKNOWN"
    leg_token = "b" if leg_type == "base" else "a"
    return f"ma_{timestamp_token}_{symbol_token}_{leg_token}{sequence:02d}"


def build_intent_id_from_client_order_id(client_order_id: str | None) -> str | None:
    if not client_order_id or not client_order_id.startswith("ma_"):
        return None
    if client_order_id.endswith(("e", "s")):
        return client_order_id[:-1]
    return client_order_id
