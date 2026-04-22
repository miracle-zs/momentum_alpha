from __future__ import annotations

from collections import Counter
from collections.abc import Mapping
from datetime import datetime, timedelta, timezone

from momentum_alpha.dashboard_common import ACCOUNT_RANGE_WINDOWS


def _account_flow_since(*, now: datetime, range_key: str) -> datetime:
    window = ACCOUNT_RANGE_WINDOWS.get(range_key)
    if window is None:
        return datetime(1970, 1, 1, tzinfo=timezone.utc)
    return now.astimezone(timezone.utc) - window


def _select_latest_timestamp(events: list[dict], event_type: str) -> str | None:
    for event in events:
        if event.get("event_type") == event_type:
            return event.get("timestamp")
    return None


def _normalize_events(events: list[dict]) -> list[dict]:
    normalized: list[dict] = []
    for event in events:
        normalized.append(
            {
                "timestamp": event.get("timestamp"),
                "event_type": event.get("event_type"),
                "payload": event.get("payload") or {},
                "source": event.get("source") or "unknown",
            }
        )
    return normalized


def _build_source_counts(events: list[dict]) -> dict[str, int]:
    return dict(sorted(Counter(event.get("source") or "unknown" for event in events).items()))


def _build_leader_history(events: list[dict], limit: int = 8) -> list[dict]:
    leader_history: list[dict] = []
    seen: set[tuple[str, str]] = set()
    for event in events:
        if event.get("event_type") != "tick_result":
            continue
        payload = event.get("payload") or {}
        symbol = payload.get("next_previous_leader_symbol") or payload.get("previous_leader_symbol")
        if not symbol:
            continue
        key = (event.get("timestamp") or "", str(symbol))
        if key in seen:
            continue
        seen.add(key)
        leader_history.append({"timestamp": event.get("timestamp"), "symbol": str(symbol)})
        if len(leader_history) >= limit:
            break
    return leader_history


def _build_pulse_points(events: list[dict], *, now: datetime, minutes: int = 10) -> list[dict]:
    utc_now = now.astimezone(timezone.utc)
    buckets = []
    bucket_counts: Counter[str] = Counter()
    for offset in range(minutes - 1, -1, -1):
        bucket_dt = (utc_now - timedelta(minutes=offset)).replace(second=0, microsecond=0)
        bucket_key = bucket_dt.isoformat()
        buckets.append(bucket_key)
    bucket_set = set(buckets)
    for event in events:
        timestamp = event.get("timestamp")
        if not timestamp:
            continue
        bucket_key = (
            datetime.fromisoformat(timestamp)
            .astimezone(timezone.utc)
            .replace(second=0, microsecond=0)
            .isoformat()
        )
        if bucket_key in bucket_set:
            bucket_counts[bucket_key] += 1
    return [{"bucket": bucket, "event_count": bucket_counts.get(bucket, 0)} for bucket in buckets]


def _runtime_summary_from_sources(
    *,
    state_payload: dict,
    latest_account_snapshot: dict | None,
    latest_position_snapshot: dict | None,
    latest_signal_decision: dict | None,
) -> tuple[str | None, int, int]:
    if latest_position_snapshot is not None:
        return (
            latest_position_snapshot.get("leader_symbol"),
            int(latest_position_snapshot.get("position_count") or 0),
            int(latest_position_snapshot.get("order_status_count") or 0),
        )
    if latest_signal_decision is not None:
        return (
            latest_signal_decision.get("next_leader_symbol") or latest_signal_decision.get("symbol"),
            int(latest_signal_decision.get("position_count") or 0),
            int(latest_signal_decision.get("order_status_count") or 0),
        )
    if latest_account_snapshot is not None:
        return (
            latest_account_snapshot.get("leader_symbol"),
            int(latest_account_snapshot.get("position_count") or 0),
            len(state_payload.get("order_statuses") or {}),
        )
    positions = state_payload.get("positions") or {}
    order_statuses = state_payload.get("order_statuses") or {}
    return (
        state_payload.get("previous_leader_symbol"),
        len(positions),
        len(order_statuses),
    )


_EXTERNAL_ACCOUNT_FLOW_REASONS = {
    "DEPOSIT",
    "WITHDRAW",
    "WITHDRAW_REJECT",
    "ADMIN_DEPOSIT",
    "TRANSFER",
    "ASSET_TRANSFER",
    "MARGIN_TRANSFER",
    "INTERNAL_TRANSFER",
    "FUNDING_TRANSFER",
    "OPTIONS_TRANSFER",
}


def _is_external_account_flow(flow: dict) -> bool:
    reason = str(flow.get("reason") or "").upper()
    return reason in _EXTERNAL_ACCOUNT_FLOW_REASONS
