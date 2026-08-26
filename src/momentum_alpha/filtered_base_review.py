from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.daily_review import (
    DISPLAY_TIMEZONE,
    DailyReviewWindow,
    build_daily_review_window,
)
from momentum_alpha.runtime_store import (
    fetch_signal_decisions_for_window,
    fetch_trade_round_trips_for_window,
)


@dataclass(frozen=True)
class FilteredBaseReviewRow:
    """One Base-veto sample and its continuous counterfactual outcome."""

    sample_id: str
    symbol: str
    vetoed_at: str
    veto_rule: str | None
    atr_15m_pct: str | None
    trade_count_ratio_30m: str | None
    return_to_vol_15m: str | None
    entry_price: str | None
    stop_price: str | None
    status: str
    outcome: str
    exit_at: str | None
    exit_price: str | None
    net_pnl: str | None
    mark_to_market_net_pnl: str | None
    duration_minutes: str | None
    add_on_count: int
    is_long_tail_50u: bool
    warnings: tuple[str, ...]
    taker_buy_share_15m: str | None = None
    efficiency_15m: str | None = None
    range_expansion_15m: str | None = None
    breakout_5m_pct: str | None = None
    pullback_5m_pct: str | None = None
    veto_a_triggered: bool | None = None
    veto_b_triggered: bool | None = None
    veto_c_triggered: bool | None = None
    veto_d_triggered: bool | None = None
    veto_e_triggered: bool | None = None
    veto_breakout_triggered: bool | None = None
    actual_trade_id: str | None = None
    actual_trade_opened_at: str | None = None
    actual_trade_closed_at: str | None = None
    actual_trade_net_pnl: str | None = None
    strategy_pnl_delta: str | None = None
    strategy_outcome: str = "pending"
    comparison_type: str = "additional_counterfactual_base"


@dataclass(frozen=True)
class FilteredBaseReviewReport:
    report_date: str
    window_start: str
    window_end: str
    generated_at: str
    status: str
    warnings: tuple[str, ...]
    summary: dict[str, object]
    rows: tuple[FilteredBaseReviewRow, ...]


def build_filtered_base_review_report(
    *,
    path: Path,
    now: datetime,
    replay_report: object | None,
    review_window: DailyReviewWindow | None = None,
    replay_cutoff: datetime | None = None,
) -> FilteredBaseReviewReport:
    """Build the unfiltered Base counterfactual without touching daily PnL."""

    window = review_window or build_daily_review_window(now=now)
    trade_window_end = replay_cutoff or window.window_end
    signal_decisions = fetch_signal_decisions_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    trade_round_trips = fetch_trade_round_trips_for_window(
        path=path,
        window_start=window.window_start,
        window_end=trade_window_end,
    )
    rows, summary = _build_filtered_base_rows(
        signal_decisions=signal_decisions,
        trade_round_trips=trade_round_trips,
        replay_report=replay_report,
    )
    warnings = tuple(dict.fromkeys(str(item) for item in summary.get("replay_warnings", [])))
    return FilteredBaseReviewReport(
        report_date=window.report_date,
        window_start=window.window_start.isoformat(),
        window_end=window.window_end.isoformat(),
        generated_at=now.astimezone(DISPLAY_TIMEZONE).isoformat(),
        status="warning" if warnings or summary.get("fetch_errors") else "ok",
        warnings=warnings,
        summary=summary,
        rows=tuple(rows),
    )


def _build_filtered_base_rows(
    *,
    signal_decisions: list[dict],
    trade_round_trips: list[dict],
    replay_report: object | None,
) -> tuple[list[FilteredBaseReviewRow], dict[str, object]]:
    filtered_signals = sorted(
        (
            decision
            for decision in signal_decisions
            if decision.get("decision_type") == "base_entry_skipped"
            and str((decision.get("payload") or {}).get("blocked_reason") or "") == "base_veto"
        ),
        key=lambda row: (row.get("timestamp") or "", row.get("id") or ""),
    )
    replay_by_id = {
        str(getattr(result, "shadow_opportunity_id", "")): result
        for result in (getattr(replay_report, "opportunities", ()) or ())
        if getattr(result, "shadow_opportunity_id", None)
    }
    if replay_report is not None:
        filtered_signals = [
            signal
            for signal in filtered_signals
            if _filtered_signal_sample_id(signal) in replay_by_id
        ]
    suppressed_by_id = {
        str(getattr(item, "shadow_opportunity_id", "")): item
        for item in (getattr(replay_report, "suppressed", ()) or ())
        if getattr(item, "shadow_opportunity_id", None)
    }
    suppressed_by_id.update(
        {
            str(getattr(item, "shadow_opportunity_id", "")): item
            for item in (getattr(replay_report, "overlaps", ()) or ())
            if getattr(item, "shadow_opportunity_id", None)
        }
    )
    rows: list[FilteredBaseReviewRow] = []
    seen_sample_ids: set[str] = set()
    consumed_actual_trade_ids: set[str] = set()
    for signal in filtered_signals:
        payload = signal.get("payload") or {}
        sample_id = _filtered_signal_sample_id(signal)
        if sample_id in seen_sample_ids:
            continue
        seen_sample_ids.add(sample_id)

        result = replay_by_id.get(sample_id)
        suppression = suppressed_by_id.get(sample_id)
        status, outcome = _filtered_base_status(result, suppression=suppression)
        actual_trade, comparison_type = _find_displaced_actual_trade(
            symbol=str(signal.get("symbol") or "n/a"),
            signal_at=signal.get("timestamp"),
            result=result,
            trade_round_trips=trade_round_trips,
            consumed_actual_trade_ids=consumed_actual_trade_ids,
        )
        if actual_trade is not None:
            consumed_actual_trade_ids.add(str(actual_trade.get("round_trip_id") or ""))
        result_pnl = _safe_decimal_text(getattr(result, "net_pnl", None)) if result is not None else None
        result_mark_pnl = (
            _safe_decimal_text(getattr(result, "mark_to_market_net_pnl", None))
            if result is not None
            else None
        )
        warnings = list(getattr(result, "warnings", ()) or ()) if result is not None else []
        if suppression is not None:
            suppression_reason = getattr(
                suppression,
                "reason",
                getattr(suppression, "status", "unknown"),
            )
            warnings.append(f"replay_suppressed:{suppression_reason}")
        if status == "pending_replay":
            warnings.append("replay_not_available")
        closed_pnl = _parse_optional_decimal(result_pnl) if status == "closed" else None
        actual_trade_pnl = (
            _safe_decimal_text(actual_trade.get("net_pnl"))
            if actual_trade is not None
            else None
        )
        strategy_pnl_delta = _strategy_pnl_delta(
            status=status,
            counterfactual_pnl=closed_pnl,
            actual_trade=actual_trade,
            actual_trade_pnl=actual_trade_pnl,
        )
        strategy_outcome = _strategy_outcome(strategy_pnl_delta)
        rows.append(
            FilteredBaseReviewRow(
                sample_id=sample_id,
                symbol=str(signal.get("symbol") or "n/a"),
                vetoed_at=str(signal.get("timestamp") or ""),
                veto_rule=_payload_text(payload, "base_veto_rule"),
                atr_15m_pct=_payload_text(payload, "atr_15m_pct", "base_veto_atr_15m_pct"),
                trade_count_ratio_30m=_payload_text(
                    payload,
                    "trade_count_ratio_30m",
                    "base_veto_trade_count_ratio_30m",
                ),
                return_to_vol_15m=_payload_text(
                    payload,
                    "return_to_vol_15m",
                    "base_veto_return_to_vol_15m",
                ),
                entry_price=(
                    _safe_decimal_text(getattr(result, "base_entry_price", None))
                    if result is not None
                    else _payload_text(payload, "latest_price")
                ),
                stop_price=(
                    _safe_decimal_text(getattr(result, "initial_stop_price", None))
                    if result is not None
                    else _payload_text(payload, "stop_price")
                ),
                status=status,
                outcome=outcome,
                exit_at=_datetime_text(getattr(result, "exit_at", None)) if result is not None else None,
                exit_price=_safe_decimal_text(getattr(result, "exit_price", None)) if result is not None else None,
                net_pnl=result_pnl,
                mark_to_market_net_pnl=result_mark_pnl,
                duration_minutes=(
                    _safe_decimal_text(getattr(result, "duration_minutes", None))
                    if result is not None
                    else None
                ),
                add_on_count=int(getattr(result, "add_on_count", 0) or 0) if result is not None else 0,
                is_long_tail_50u=bool(closed_pnl is not None and closed_pnl >= Decimal("50")),
                warnings=tuple(dict.fromkeys(str(item) for item in warnings)),
                taker_buy_share_15m=_payload_text(
                    payload,
                    "taker_buy_share_15m",
                    "base_veto_taker_buy_share_15m",
                ),
                efficiency_15m=_payload_text(
                    payload,
                    "efficiency_15m",
                    "base_veto_efficiency_15m",
                ),
                range_expansion_15m=_payload_text(
                    payload,
                    "range_expansion_15m",
                    "base_veto_range_expansion_15m",
                ),
                breakout_5m_pct=_payload_text(
                    payload,
                    "breakout_5m_pct",
                    "base_veto_breakout_5m_pct",
                ),
                pullback_5m_pct=_payload_text(
                    payload,
                    "pullback_5m_pct",
                    "base_veto_pullback_5m_pct",
                ),
                veto_a_triggered=_payload_bool(payload, "base_veto_a_triggered", "base_veto_atr_triggered"),
                veto_b_triggered=_payload_bool(payload, "base_veto_b_triggered", "base_veto_composite_triggered"),
                veto_c_triggered=_payload_bool(payload, "base_veto_c_triggered"),
                veto_d_triggered=_payload_bool(payload, "base_veto_d_triggered"),
                veto_e_triggered=_payload_bool(payload, "base_veto_e_triggered"),
                veto_breakout_triggered=_payload_bool(payload, "base_veto_breakout_triggered"),
                actual_trade_id=(
                    str(actual_trade.get("round_trip_id"))
                    if actual_trade is not None and actual_trade.get("round_trip_id")
                    else None
                ),
                actual_trade_opened_at=(
                    _datetime_text(actual_trade.get("opened_at"))
                    if actual_trade is not None
                    else None
                ),
                actual_trade_closed_at=(
                    _datetime_text(actual_trade.get("closed_at"))
                    if actual_trade is not None
                    else None
                ),
                actual_trade_net_pnl=actual_trade_pnl,
                strategy_pnl_delta=(
                    str(strategy_pnl_delta)
                    if strategy_pnl_delta is not None
                    else None
                ),
                strategy_outcome=strategy_outcome,
                comparison_type=comparison_type,
            )
        )

    closed_rows = [row for row in rows if row.status == "closed" and row.net_pnl is not None]
    open_rows = [row for row in rows if row.status == "open"]
    positive_pnl = [
        value
        for row in closed_rows
        if (value := _parse_optional_decimal(row.net_pnl)) is not None and value > 0
    ]
    negative_pnl = [
        value
        for row in closed_rows
        if (value := _parse_optional_decimal(row.net_pnl)) is not None and value < 0
    ]
    closed_sample_pnl = sum(positive_pnl, Decimal("0")) + sum(negative_pnl, Decimal("0"))
    closed_strategy_rows = [
        row
        for row in closed_rows
        if row.strategy_pnl_delta is not None
    ]
    positive_strategy_delta = [
        value
        for row in closed_strategy_rows
        if (value := _parse_optional_decimal(row.strategy_pnl_delta)) is not None and value > 0
    ]
    negative_strategy_delta = [
        value
        for row in closed_strategy_rows
        if (value := _parse_optional_decimal(row.strategy_pnl_delta)) is not None and value < 0
    ]
    actual_replaced_pnl = sum(
        (
            _parse_optional_decimal(row.actual_trade_net_pnl) or Decimal("0")
            for row in closed_strategy_rows
            if row.actual_trade_id is not None
        ),
        Decimal("0"),
    )
    strategy_pnl_delta = (
        sum(positive_strategy_delta, Decimal("0"))
        + sum(negative_strategy_delta, Decimal("0"))
    )
    open_mtm_pnl = sum(
        (_parse_optional_decimal(row.mark_to_market_net_pnl) or Decimal("0") for row in open_rows),
        Decimal("0"),
    )
    accepted_count = sum(1 for row in rows if row.status in {"closed", "open", "unresolved"})
    summary: dict[str, object] = {
        # Only samples that survive the original strategy state and are then
        # blocked by Base veto belong in this user-facing report.
        "candidate_count": accepted_count,
        "replayed_count": accepted_count,
        "accepted_count": accepted_count,
        "replay_mode": str(getattr(replay_report, "replay_mode", "independent") or "independent"),
        "resolved_count": len(closed_rows) + len(open_rows),
        "closed_count": len(closed_rows),
        "open_count": len(open_rows),
        "unresolved_count": sum(1 for row in rows if row.status == "unresolved"),
        "pending_count": sum(1 for row in rows if row.status == "pending_replay"),
        "win_count": len(positive_strategy_delta),
        "loss_count": len(negative_strategy_delta),
        "missed_profit_sum": str(sum(positive_strategy_delta, Decimal("0"))),
        "avoided_loss_sum": str(abs(sum(negative_strategy_delta, Decimal("0")))),
        "closed_sample_pnl_sum": str(closed_sample_pnl),
        "counterfactual_trade_pnl_sum": str(closed_sample_pnl),
        "actual_replaced_pnl_sum": str(actual_replaced_pnl),
        "strategy_pnl_delta": str(strategy_pnl_delta),
        "replaced_actual_trade_count": sum(
            1 for row in closed_strategy_rows if row.actual_trade_id is not None
        ),
        "realized_net_pnl": str(strategy_pnl_delta),
        "open_mtm_pnl_sum": str(open_mtm_pnl),
        "mark_to_market_net_pnl": str(open_mtm_pnl),
        "tail_50u_count": sum(1 for row in closed_rows if row.is_long_tail_50u),
        "replay_warnings": list(getattr(replay_report, "warnings", ()) or ()),
        "fetch_errors": bool(getattr(replay_report, "had_fetch_errors", False)),
    }
    return rows, summary


def _find_displaced_actual_trade(
    *,
    symbol: str,
    signal_at: object | None,
    result: object | None,
    trade_round_trips: list[dict],
    consumed_actual_trade_ids: set[str],
) -> tuple[dict | None, str]:
    signal_time = _parse_datetime_utc(signal_at)
    if result is None or signal_time is None:
        return None, "additional_counterfactual_base"

    shadow_status = str(getattr(result, "status", "unresolved") or "unresolved")
    shadow_exit_time = _parse_datetime_utc(getattr(result, "exit_at", None))
    matches: list[tuple[datetime, dict, str]] = []
    for trade in trade_round_trips:
        round_trip_id = str(trade.get("round_trip_id") or "")
        if not round_trip_id or round_trip_id in consumed_actual_trade_ids:
            continue
        if str(trade.get("symbol") or "") != symbol:
            continue
        actual_opened_at = _parse_datetime_utc(trade.get("opened_at"))
        if actual_opened_at is None or actual_opened_at <= signal_time:
            continue

        same_utc_day = actual_opened_at.date() == signal_time.date()
        overlaps_shadow = (
            shadow_status == "open"
            or (
                shadow_status == "closed"
                and shadow_exit_time is not None
                and actual_opened_at < shadow_exit_time
            )
        )
        if not same_utc_day and not overlaps_shadow:
            continue
        comparison_type = (
            "replaced_later_actual_base"
            if overlaps_shadow
            else "replaced_same_day_actual_base"
        )
        matches.append((actual_opened_at, trade, comparison_type))

    if not matches:
        return None, "additional_counterfactual_base"
    _opened_at, trade, comparison_type = min(matches, key=lambda item: item[0])
    return trade, comparison_type


def _strategy_pnl_delta(
    *,
    status: str,
    counterfactual_pnl: Decimal | None,
    actual_trade: dict | None,
    actual_trade_pnl: str | None,
) -> Decimal | None:
    if status != "closed" or counterfactual_pnl is None:
        return None
    if actual_trade is None:
        return counterfactual_pnl
    parsed_actual_pnl = _parse_optional_decimal(actual_trade_pnl)
    if parsed_actual_pnl is None:
        return None
    return counterfactual_pnl - parsed_actual_pnl


def _strategy_outcome(strategy_pnl_delta: Decimal | None) -> str:
    if strategy_pnl_delta is None:
        return "pending"
    if strategy_pnl_delta > 0:
        return "improved"
    if strategy_pnl_delta < 0:
        return "worsened"
    return "flat"


def _filtered_base_status(
    result: object | None,
    *,
    suppression: object | None = None,
) -> tuple[str, str]:
    if suppression is not None:
        return "suppressed", "not_opened"
    if result is None:
        return "pending_replay", "pending"
    status = str(getattr(result, "status", "unresolved") or "unresolved")
    if status == "closed":
        pnl = _parse_optional_decimal(getattr(result, "net_pnl", None))
        if pnl is None or pnl == 0:
            return "closed", "flat"
        return "closed", "win" if pnl > 0 else "loss"
    if status == "open":
        return "open", "open"
    return "unresolved", "unresolved"


def _filtered_signal_sample_id(signal: dict) -> str:
    payload = signal.get("payload") or {}
    return str(
        payload.get("shadow_opportunity_id")
        or signal.get("intent_id")
        or f"base_veto_{signal.get('timestamp') or 'unknown'}_{signal.get('symbol') or 'unknown'}"
    )


def _payload_text(payload: dict, *keys: str) -> str | None:
    for key in keys:
        value = payload.get(key)
        if value not in (None, ""):
            return str(value)
    return None


def _payload_bool(payload: dict, *keys: str) -> bool | None:
    for key in keys:
        value = payload.get(key)
        if isinstance(value, bool):
            return value
        if value in (None, ""):
            continue
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    return None


def _safe_decimal_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(Decimal(str(value)))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _parse_optional_decimal(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _datetime_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _parse_datetime_utc(value: object | None) -> datetime | None:
    if value in (None, ""):
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        try:
            parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
        except ValueError:
            return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)
