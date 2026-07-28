from __future__ import annotations

from datetime import datetime, timezone

from momentum_alpha.models import Position


def parse_runtime_timestamp(value: object) -> datetime | None:
    if value in (None, ""):
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    return parsed if parsed.tzinfo is not None else parsed.replace(tzinfo=timezone.utc)


def position_has_leg_opened_after(position: Position, timestamp: object) -> bool:
    """Return whether a position contains a leg opened after a removal marker."""

    cutoff = parse_runtime_timestamp(timestamp)
    if cutoff is None:
        return False
    cutoff = cutoff.astimezone(timezone.utc)
    for leg in position.legs:
        opened_at = leg.opened_at
        if opened_at.tzinfo is None:
            opened_at = opened_at.replace(tzinfo=timezone.utc)
        elif opened_at.tzinfo is not None:
            opened_at = opened_at.astimezone(timezone.utc)
        if opened_at > cutoff:
            return True
    return False


def position_has_leg_opened_after_position(candidate: Position, reference: Position) -> bool:
    """Return whether candidate contains a leg newer than reference's latest leg."""

    if not reference.legs:
        return bool(candidate.legs)
    latest_reference_opened_at = max(
        (
            leg.opened_at.replace(tzinfo=timezone.utc)
            if leg.opened_at.tzinfo is None
            else leg.opened_at.astimezone(timezone.utc)
        )
        for leg in reference.legs
    )
    return any(
        (
            leg.opened_at.replace(tzinfo=timezone.utc)
            if leg.opened_at.tzinfo is None
            else leg.opened_at.astimezone(timezone.utc)
        )
        > latest_reference_opened_at
        for leg in candidate.legs
    )


def position_has_newer_version(candidate: Position, reference: Position) -> bool:
    """Return whether candidate is a changed position, not just a stop update."""

    if candidate == reference:
        return False
    if candidate.total_quantity != reference.total_quantity:
        return True
    if len(candidate.legs) != len(reference.legs):
        return True
    if position_has_leg_opened_after_position(candidate, reference):
        return True
    for candidate_leg, reference_leg in zip(candidate.legs, reference.legs):
        if (
            candidate_leg.entry_price != reference_leg.entry_price
            or candidate_leg.quantity != reference_leg.quantity
            or candidate_leg.entry_order_id != reference_leg.entry_order_id
            or candidate_leg.leg_type != reference_leg.leg_type
        ):
            return True
    return False
