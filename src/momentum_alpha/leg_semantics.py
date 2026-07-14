from __future__ import annotations

from typing import Literal

from momentum_alpha.trace_ids import build_intent_id_from_client_order_id


LegType = Literal["base", "add_on"]
LegSource = Literal[
    "strategy_fill",
    "user_stream",
    "rest_restore",
    "account_update",
    "reconciliation",
    "legacy",
]


def infer_leg_type_from_client_order_id(client_order_id: str | None) -> LegType | None:
    intent_id = build_intent_id_from_client_order_id(client_order_id)
    if intent_id is None:
        return None
    token = intent_id.rsplit("_", 1)[-1]
    if token.startswith("b"):
        return "base"
    if token.startswith("a"):
        return "add_on"
    return None


def normalize_legacy_leg_type(
    raw_leg_type: str | None,
    *,
    entry_order_id: str | None,
    leg_index: int,
) -> LegType:
    inferred = infer_leg_type_from_client_order_id(entry_order_id)
    if inferred is not None:
        return inferred
    if raw_leg_type == "add_on":
        return "add_on"
    if raw_leg_type == "base":
        return "base"
    if raw_leg_type == "restored_reconciliation":
        return "add_on"
    return "base" if leg_index == 0 else "add_on"


def normalize_legacy_leg_source(
    raw_leg_type: str | None,
    explicit_source: str | None,
) -> LegSource:
    allowed_sources = {
        "strategy_fill",
        "user_stream",
        "rest_restore",
        "account_update",
        "reconciliation",
        "legacy",
    }
    if explicit_source in allowed_sources:
        return explicit_source  # type: ignore[return-value]
    if raw_leg_type == "stream_fill":
        return "user_stream"
    if raw_leg_type == "restored":
        return "rest_restore"
    if raw_leg_type in {"account_update_restored", "account_update_synced"}:
        return "account_update"
    if raw_leg_type == "restored_reconciliation":
        return "reconciliation"
    return "legacy"


def is_add_on_leg(*, leg_type: str, entry_order_id: str | None) -> bool:
    return leg_type == "add_on" or infer_leg_type_from_client_order_id(entry_order_id) == "add_on"
