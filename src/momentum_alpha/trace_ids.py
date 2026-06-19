from __future__ import annotations

import hashlib
from datetime import datetime, timezone
from string import ascii_uppercase, digits


_SYMBOL_TOKEN_CHARS = set(ascii_uppercase + digits)


def build_symbol_token(symbol: str, *, max_length: int) -> str:
    upper_symbol = symbol.upper()
    ascii_token = "".join(ch for ch in upper_symbol if ch in _SYMBOL_TOKEN_CHARS)
    removed_non_ascii = ascii_token != upper_symbol
    if not removed_non_ascii:
        return ascii_token[-max_length:] or "UNKNOWN"

    digest = hashlib.blake2s(symbol.encode("utf-8"), digest_size=3).hexdigest().upper()
    prefix_length = max(0, max_length - len(digest))
    prefix = ascii_token[-prefix_length:] if prefix_length else ""
    return (prefix + digest)[-max_length:] or digest[-max_length:]


def build_decision_id(*, now: datetime) -> str:
    resolved_now = now.astimezone(timezone.utc)
    return f"dec_{resolved_now.strftime('%y%m%d%H%M%S%f')}"


def build_order_intent_id(*, symbol: str, opened_at: datetime, leg_type: str, sequence: int) -> str:
    resolved_opened_at = opened_at.astimezone(timezone.utc)
    if leg_type == "add_on":
        resolved_opened_at = resolved_opened_at.replace(minute=0, second=0, microsecond=0)
    timestamp_token = resolved_opened_at.strftime("%y%m%d%H%M%S")
    symbol_token = build_symbol_token(symbol, max_length=10)
    leg_token = "b" if leg_type == "base" else "a"
    return f"ma_{timestamp_token}_{symbol_token}_{leg_token}{sequence:02d}"


def build_shadow_opportunity_id(*, symbol: str, signal_at: datetime, sequence: int) -> str:
    resolved_signal_at = signal_at.astimezone(timezone.utc)
    timestamp_token = resolved_signal_at.strftime("%y%m%d%H%M%S")
    symbol_token = build_symbol_token(symbol, max_length=12)
    return f"shadow_{timestamp_token}_{symbol_token}_{sequence:02d}"


def build_intent_id_from_client_order_id(client_order_id: str | None) -> str | None:
    if not client_order_id or not client_order_id.startswith("ma_"):
        return None
    if client_order_id.endswith(("e", "s")):
        return client_order_id[:-1]
    return client_order_id
