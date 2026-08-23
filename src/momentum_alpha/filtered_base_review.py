from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.daily_review import DISPLAY_TIMEZONE, build_daily_review_window
from momentum_alpha.runtime_store import fetch_signal_decisions_for_window


@dataclass(frozen=True)
class FilteredBaseReviewRow:
    """One entry sample that the original strategy would have opened.

    Every row is replayed independently.  Rows are never removed or re-labeled
    because another sample for the same symbol happens to cover the same time.
    The resulting PnL is a sample outcome, not a portfolio return.
    """

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
) -> FilteredBaseReviewReport:
    """Build the independent-sample review without touching the daily report."""

    window = build_daily_review_window(now=now)
    signal_decisions = fetch_signal_decisions_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    rows, summary = _build_filtered_base_rows(
        signal_decisions=signal_decisions,
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
    rows: list[FilteredBaseReviewRow] = []
    seen_sample_ids: set[str] = set()
    for signal in filtered_signals:
        payload = signal.get("payload") or {}
        sample_id = str(
            payload.get("shadow_opportunity_id")
            or signal.get("intent_id")
            or f"base_veto_{signal.get('timestamp') or 'unknown'}_{signal.get('symbol') or 'unknown'}"
        )
        if sample_id in seen_sample_ids:
            continue
        seen_sample_ids.add(sample_id)

        result = replay_by_id.get(sample_id)
        status, outcome = _filtered_base_status(result)
        result_pnl = _safe_decimal_text(getattr(result, "net_pnl", None)) if result is not None else None
        result_mark_pnl = (
            _safe_decimal_text(getattr(result, "mark_to_market_net_pnl", None))
            if result is not None
            else None
        )
        warnings = list(getattr(result, "warnings", ()) or ()) if result is not None else []
        if status == "pending_replay":
            warnings.append("replay_not_available")
        closed_pnl = _parse_optional_decimal(result_pnl) if status == "closed" else None
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
    open_mtm_pnl = sum(
        (_parse_optional_decimal(row.mark_to_market_net_pnl) or Decimal("0") for row in open_rows),
        Decimal("0"),
    )
    summary: dict[str, object] = {
        "candidate_count": len(rows),
        "replayed_count": sum(1 for row in rows if row.status != "pending_replay"),
        "resolved_count": len(closed_rows) + len(open_rows),
        "closed_count": len(closed_rows),
        "open_count": len(open_rows),
        "unresolved_count": sum(1 for row in rows if row.status == "unresolved"),
        "pending_count": sum(1 for row in rows if row.status == "pending_replay"),
        "win_count": len(positive_pnl),
        "loss_count": len(negative_pnl),
        "missed_profit_sum": str(sum(positive_pnl, Decimal("0"))),
        "avoided_loss_sum": str(abs(sum(negative_pnl, Decimal("0")))),
        "closed_sample_pnl_sum": str(closed_sample_pnl),
        "open_mtm_pnl_sum": str(open_mtm_pnl),
        "tail_50u_count": sum(1 for row in closed_rows if row.is_long_tail_50u),
        "replay_warnings": list(getattr(replay_report, "warnings", ()) or ()),
        "fetch_errors": bool(getattr(replay_report, "had_fetch_errors", False)),
    }
    return rows, summary


def _filtered_base_status(result: object | None) -> tuple[str, str]:
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
