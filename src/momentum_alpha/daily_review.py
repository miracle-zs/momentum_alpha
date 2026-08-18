from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path

from momentum_alpha.binance_filters import SymbolFilters
from momentum_alpha.runtime_store import (
    fetch_account_flows_for_window,
    fetch_account_snapshots_for_window,
    fetch_signal_decisions_for_window,
    fetch_trade_round_trips_for_window,
)
from momentum_alpha.sizing import size_from_stop_budget


DISPLAY_TIMEZONE = timezone(timedelta(hours=8))
DAILY_REVIEW_CUTOFF_HOUR = 8
DAILY_REVIEW_CUTOFF_MINUTE = 30
BACKFILL_INCOME_SOURCE = "backfill-income-history"
ACCOUNT_PNL_REASONS = frozenset({"REALIZED_PNL", "COMMISSION", "FUNDING_FEE"})
ACCOUNT_TRANSFER_REASONS = frozenset({"TRANSFER", "INTERNAL_TRANSFER", "DEPOSIT", "WITHDRAW"})


@dataclass(frozen=True)
class DailyReviewWindow:
    report_date: str
    window_start: datetime
    window_end: datetime


@dataclass(frozen=True)
class DailyReviewTradeRow:
    round_trip_id: str
    symbol: str
    opened_at: str
    closed_at: str
    actual_net_pnl: str
    counterfactual_net_pnl: str
    pnl_delta: str
    leg_count: int
    replayed_add_on_count: int
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class DailyReviewFilteredBaseRow:
    """One Base candidate blocked by the live Base veto.

    ``net_pnl`` is populated for a closed shadow position.  For an open
    shadow position the dashboard should use ``mark_to_market_net_pnl`` and
    label it as observed rather than realised.  Keeping both values avoids
    accidentally mixing a live mark with closed-trade PnL in reports.
    """

    shadow_opportunity_id: str
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


@dataclass(frozen=True)
class DailyReviewAccountReconciliation:
    income_total_pnl: str
    income_realized_pnl: str
    income_commission: str
    income_funding_fee: str
    income_other: str
    income_transfer_total: str
    trade_vs_income_delta: str
    wallet_balance_start: str | None
    wallet_balance_end: str | None
    wallet_balance_delta: str | None
    equity_start: str | None
    equity_end: str | None
    equity_delta: str | None
    flow_count: int


@dataclass(frozen=True)
class DailyReviewReport:
    report_date: str
    window_start: str
    window_end: str
    generated_at: str
    status: str
    trade_count: int
    actual_total_pnl: str
    counterfactual_total_pnl: str
    pnl_delta: str
    replayed_add_on_count: int
    stop_budget_usdt: str
    entry_start_hour_utc: int
    entry_end_hour_utc: int
    warnings: tuple[str, ...]
    account_reconciliation: DailyReviewAccountReconciliation
    rows: tuple[DailyReviewTradeRow, ...]
    filtered_base_summary: dict[str, object] = field(default_factory=dict)
    filtered_base_rows: tuple[DailyReviewFilteredBaseRow, ...] = ()


def build_daily_review_window(*, now: datetime) -> DailyReviewWindow:
    local_now = now.astimezone(DISPLAY_TIMEZONE)
    window_end = local_now.replace(
        hour=DAILY_REVIEW_CUTOFF_HOUR,
        minute=DAILY_REVIEW_CUTOFF_MINUTE,
        second=0,
        microsecond=0,
    )
    if local_now < window_end:
        window_end -= timedelta(days=1)
    window_start = window_end - timedelta(days=1)
    return DailyReviewWindow(
        report_date=window_end.date().isoformat(),
        window_start=window_start,
        window_end=window_end,
    )


def build_daily_review_report(
    *,
    path: Path,
    now: datetime,
    stop_budget_usdt: Decimal,
    entry_start_hour_utc: int,
    entry_end_hour_utc: int,
    filtered_base_replay_report: object | None = None,
) -> DailyReviewReport:
    window = build_daily_review_window(now=now)
    trade_round_trips = fetch_trade_round_trips_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    signal_decisions = fetch_signal_decisions_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    account_flows = fetch_account_flows_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    account_snapshots = fetch_account_snapshots_for_window(
        path=path,
        window_start=window.window_start,
        window_end=window.window_end,
    )
    rows, warnings = _build_daily_review_rows(
        trade_round_trips=trade_round_trips,
        signal_decisions=signal_decisions,
        stop_budget_usdt=stop_budget_usdt,
    )
    filtered_base_rows, filtered_base_summary = _build_filtered_base_rows(
        signal_decisions=signal_decisions,
        replay_report=filtered_base_replay_report,
    )
    actual_total_pnl = sum((Decimal(row.actual_net_pnl) for row in rows), Decimal("0"))
    counterfactual_total_pnl = sum((Decimal(row.counterfactual_net_pnl) for row in rows), Decimal("0"))
    account_reconciliation = _build_account_reconciliation(
        account_flows=account_flows,
        account_snapshots=account_snapshots,
        trade_total_pnl=actual_total_pnl,
    )
    report = DailyReviewReport(
        report_date=window.report_date,
        window_start=window.window_start.isoformat(),
        window_end=window.window_end.isoformat(),
        generated_at=now.astimezone(DISPLAY_TIMEZONE).isoformat(),
        # Keep the original daily-review status independent from the optional
        # filtered-Base replay.  Replay health lives in the filtered summary.
        status="warning" if warnings else "ok",
        trade_count=len(rows),
        actual_total_pnl=str(actual_total_pnl),
        counterfactual_total_pnl=str(counterfactual_total_pnl),
        pnl_delta=str(counterfactual_total_pnl - actual_total_pnl),
        replayed_add_on_count=sum(row.replayed_add_on_count for row in rows),
        stop_budget_usdt=str(stop_budget_usdt),
        entry_start_hour_utc=entry_start_hour_utc,
        entry_end_hour_utc=entry_end_hour_utc,
        warnings=tuple(dict.fromkeys(warnings)),
        account_reconciliation=account_reconciliation,
        rows=tuple(rows),
        filtered_base_summary=filtered_base_summary,
        filtered_base_rows=tuple(filtered_base_rows),
    )
    return report


def _build_filtered_base_rows(
    *,
    signal_decisions: list[dict],
    replay_report: object | None,
) -> tuple[list[DailyReviewFilteredBaseRow], dict[str, object]]:
    """Join live Base-veto telemetry with its optional causal replay.

    The signal row is the decision-time truth.  The replay result is only a
    later observation, so missing replay data remains explicitly ``pending``
    instead of being treated as a zero-PnL outcome.
    """

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
    rows: list[DailyReviewFilteredBaseRow] = []
    seen_shadow_ids: set[str] = set()
    for signal in filtered_signals:
        payload = signal.get("payload") or {}
        shadow_id = str(
            payload.get("shadow_opportunity_id")
            or signal.get("intent_id")
            or f"base_veto_{signal.get('timestamp') or 'unknown'}_{signal.get('symbol') or 'unknown'}"
        )
        if shadow_id in seen_shadow_ids:
            continue
        seen_shadow_ids.add(shadow_id)

        result = replay_by_id.get(shadow_id)
        status, outcome = _filtered_base_status(result=result, shadow_id=shadow_id, replay_report=replay_report)
        result_pnl = _safe_decimal_text(getattr(result, "net_pnl", None)) if result is not None else None
        result_mark_pnl = (
            _safe_decimal_text(getattr(result, "mark_to_market_net_pnl", None))
            if result is not None
            else None
        )
        if status == "closed":
            observed_pnl = _parse_optional_decimal(result_pnl)
        elif status == "open":
            observed_pnl = _parse_optional_decimal(result_mark_pnl)
        else:
            observed_pnl = None
        warnings = list(getattr(result, "warnings", ()) or ()) if result is not None else []
        if status == "pending_replay":
            warnings.append("replay_not_available")
        elif status == "overlap":
            warnings.append("overlap_existing_shadow")
        rows.append(
            DailyReviewFilteredBaseRow(
                shadow_opportunity_id=shadow_id,
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
                duration_minutes=_safe_decimal_text(getattr(result, "duration_minutes", None))
                if result is not None
                else None,
                add_on_count=int(getattr(result, "add_on_count", 0) or 0) if result is not None else 0,
                is_long_tail_50u=bool(observed_pnl is not None and observed_pnl >= Decimal("50")),
                warnings=tuple(dict.fromkeys(str(item) for item in warnings)),
            )
        )

    closed_rows = [row for row in rows if row.status == "closed" and row.net_pnl is not None]
    open_rows = [row for row in rows if row.status == "open"]
    pending_count = sum(1 for row in rows if row.status == "pending_replay")
    closed_pnl = sum((_parse_optional_decimal(row.net_pnl) or Decimal("0") for row in closed_rows), Decimal("0"))
    observed_pnl = closed_pnl + sum(
        (_parse_optional_decimal(row.mark_to_market_net_pnl) or Decimal("0") for row in open_rows),
        Decimal("0"),
    )
    summary: dict[str, object] = {
        "candidate_count": len(rows),
        "resolved_count": len(closed_rows) + len(open_rows),
        "closed_count": len(closed_rows),
        "open_count": len(open_rows),
        "pending_count": pending_count,
        "win_count": sum(
            1
            for row in closed_rows
            if (_parse_optional_decimal(row.net_pnl) or Decimal("0")) > 0
        ),
        "loss_count": sum(
            1
            for row in closed_rows
            if (_parse_optional_decimal(row.net_pnl) or Decimal("0")) < 0
        ),
        "closed_net_pnl": str(closed_pnl),
        "observed_net_pnl": str(observed_pnl),
        "tail_50u_count": sum(1 for row in rows if row.is_long_tail_50u),
        "replay_warnings": list(getattr(replay_report, "warnings", ()) or ()),
        "fetch_errors": bool(getattr(replay_report, "had_fetch_errors", False)),
    }
    return rows, summary


def _filtered_base_status(
    *,
    result: object | None,
    shadow_id: str,
    replay_report: object | None,
) -> tuple[str, str]:
    if result is None:
        if shadow_id in {
            str(getattr(overlap, "shadow_opportunity_id", ""))
            for overlap in (getattr(replay_report, "overlaps", ()) or ())
        }:
            return "overlap", "overlap"
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


def _safe_decimal_text(value: object | None) -> str | None:
    if value in (None, ""):
        return None
    try:
        return str(_parse_decimal(value))
    except (InvalidOperation, TypeError, ValueError):
        return None


def _datetime_text(value: object | None) -> str | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _build_daily_review_rows(
    *,
    trade_round_trips: list[dict],
    signal_decisions: list[dict],
    stop_budget_usdt: Decimal,
) -> tuple[list[DailyReviewTradeRow], list[str]]:
    sorted_trades = sorted(
        trade_round_trips,
        key=lambda row: (
            row.get("closed_at") or "",
            row.get("round_trip_id") or "",
        ),
        reverse=True,
    )
    sorted_signals = sorted(
        [decision for decision in signal_decisions if decision.get("decision_type") == "add_on_skipped"],
        key=lambda row: row.get("timestamp") or "",
    )
    rows: list[DailyReviewTradeRow] = []
    warnings: list[str] = []
    for trade in sorted_trades:
        row, row_warnings = _build_daily_review_row(
            trade_round_trip=trade,
            skipped_add_on_signals=sorted_signals,
            stop_budget_usdt=stop_budget_usdt,
        )
        rows.append(row)
        warnings.extend(row_warnings)
    return rows, warnings


def _build_daily_review_row(
    *,
    trade_round_trip: dict,
    skipped_add_on_signals: list[dict],
    stop_budget_usdt: Decimal,
) -> tuple[DailyReviewTradeRow, list[str]]:
    warnings: list[str] = []
    opened_at = _parse_datetime(trade_round_trip["opened_at"])
    closed_at = _parse_datetime(trade_round_trip["closed_at"])
    symbol = str(trade_round_trip["symbol"])
    actual_net_pnl = _parse_decimal(trade_round_trip.get("net_pnl") or trade_round_trip.get("realized_pnl") or "0")
    trade_payload = trade_round_trip.get("payload") or {}
    actual_exit_price_raw = trade_round_trip.get("weighted_avg_exit_price")
    if actual_exit_price_raw in (None, ""):
        actual_exit_price_raw = trade_payload.get("weighted_avg_exit_price")
    if actual_exit_price_raw in (None, ""):
        actual_exit_price_raw = trade_payload.get("actual_exit_price")
    invalid_exit_price = False
    try:
        actual_exit_price = _parse_optional_decimal(actual_exit_price_raw)
    except (InvalidOperation, TypeError, ValueError):
        actual_exit_price = None
        invalid_exit_price = True
    if actual_exit_price is not None and actual_exit_price <= Decimal("0"):
        actual_exit_price = None
        invalid_exit_price = True
    if invalid_exit_price:
        warnings.append(
            f"invalid_actual_exit_price symbol={symbol} round_trip_id={trade_round_trip['round_trip_id']}"
        )
    if actual_exit_price is None:
        warnings.append(
            f"missing_actual_exit_price symbol={symbol} round_trip_id={trade_round_trip['round_trip_id']}"
        )
    total_entry_quantity = _parse_decimal(trade_round_trip.get("total_entry_quantity") or "0")
    actual_commission = _parse_decimal(trade_round_trip.get("commission") or "0")
    fee_per_quantity = (
        actual_commission / total_entry_quantity if total_entry_quantity > Decimal("0") else Decimal("0")
    )

    counterfactual_net_pnl = actual_net_pnl
    replayed_add_on_count = 0
    replayed_hour_keys: set[tuple[str, datetime]] = set()
    for signal in (skipped_add_on_signals if actual_exit_price is not None else ()):
        if str(signal.get("symbol")) != symbol:
            continue
        signal_timestamp = _parse_datetime(signal["timestamp"])
        if signal_timestamp < opened_at or signal_timestamp > closed_at:
            continue
        replay_hour_key = (symbol, _hour_bucket(signal_timestamp))
        if replay_hour_key in replayed_hour_keys:
            continue
        replayed_hour_keys.add(replay_hour_key)
        payload = signal.get("payload") or {}
        replay_inputs = _extract_replay_inputs(payload=payload, symbol=symbol, signal_timestamp=signal_timestamp)
        if replay_inputs is None:
            warnings.append(
                f"missing_replay_inputs symbol={symbol} timestamp={signal_timestamp.isoformat()} round_trip_id={trade_round_trip['round_trip_id']}"
            )
            continue
        entry_price, stop_price, filters = replay_inputs
        quantity = size_from_stop_budget(
            entry_price=entry_price,
            stop_price=stop_price,
            stop_budget=stop_budget_usdt,
            filters=filters,
        )
        if quantity is None:
            warnings.append(
                f"invalid_replay_quantity symbol={symbol} timestamp={signal_timestamp.isoformat()} round_trip_id={trade_round_trip['round_trip_id']}"
            )
            continue
        gross_pnl = (actual_exit_price - entry_price) * quantity
        fee_share = fee_per_quantity * quantity
        counterfactual_net_pnl += gross_pnl - fee_share
        replayed_add_on_count += 1

    row = DailyReviewTradeRow(
        round_trip_id=str(trade_round_trip["round_trip_id"]),
        symbol=symbol,
        opened_at=opened_at.isoformat(),
        closed_at=closed_at.isoformat(),
        actual_net_pnl=str(actual_net_pnl),
        counterfactual_net_pnl=str(counterfactual_net_pnl),
        pnl_delta=str(counterfactual_net_pnl - actual_net_pnl),
        leg_count=len(trade_payload.get("legs") or []),
        replayed_add_on_count=replayed_add_on_count,
        warnings=tuple(warnings),
    )
    return row, warnings


def _extract_replay_inputs(
    *,
    payload: dict,
    symbol: str,
    signal_timestamp: datetime,
) -> tuple[Decimal, Decimal, SymbolFilters] | None:
    try:
        latest_price = _parse_decimal(payload["latest_price"])
        stop_price = _parse_decimal(payload["stop_price"])
        filters = SymbolFilters(
            step_size=_parse_decimal(payload["step_size"]),
            min_qty=_parse_decimal(payload["min_qty"]),
            tick_size=_parse_decimal(payload["tick_size"]),
        )
    except (KeyError, InvalidOperation, TypeError):
        return None
    return latest_price, stop_price, filters


def _build_account_reconciliation(
    *,
    account_flows: list[dict],
    account_snapshots: list[dict],
    trade_total_pnl: Decimal,
) -> DailyReviewAccountReconciliation:
    realized_pnl = _sum_preferred_income_flows(account_flows, reasons={"REALIZED_PNL"})
    commission = _sum_preferred_income_flows(account_flows, reasons={"COMMISSION"})
    funding_fee = _sum_preferred_income_flows(account_flows, reasons={"FUNDING_FEE"})
    transfer_total = _sum_preferred_income_flows(account_flows, reasons=ACCOUNT_TRANSFER_REASONS)
    income_other = _sum_account_flows(
        [
            flow
            for flow in account_flows
            if str(flow.get("source") or "") == BACKFILL_INCOME_SOURCE
            and str(flow.get("reason") or "").upper() not in ACCOUNT_PNL_REASONS
            and str(flow.get("reason") or "").upper() not in ACCOUNT_TRANSFER_REASONS
        ],
        reasons=None,
    )
    income_total_pnl = realized_pnl + commission + funding_fee + income_other
    wallet_start, wallet_end, wallet_delta = _snapshot_delta(account_snapshots, field="wallet_balance")
    equity_start, equity_end, equity_delta = _snapshot_delta(account_snapshots, field="equity")
    return DailyReviewAccountReconciliation(
        income_total_pnl=str(income_total_pnl),
        income_realized_pnl=str(realized_pnl),
        income_commission=str(commission),
        income_funding_fee=str(funding_fee),
        income_other=str(income_other),
        income_transfer_total=str(transfer_total),
        trade_vs_income_delta=str(income_total_pnl - trade_total_pnl),
        wallet_balance_start=wallet_start,
        wallet_balance_end=wallet_end,
        wallet_balance_delta=wallet_delta,
        equity_start=equity_start,
        equity_end=equity_end,
        equity_delta=equity_delta,
        flow_count=len(account_flows),
    )


def _sum_preferred_income_flows(account_flows: list[dict], *, reasons: set[str] | frozenset[str]) -> Decimal:
    backfill_flows = [
        flow
        for flow in account_flows
        if str(flow.get("source") or "") == BACKFILL_INCOME_SOURCE and str(flow.get("reason") or "").upper() in reasons
    ]
    if backfill_flows:
        return _sum_account_flows(backfill_flows, reasons=reasons)
    return _sum_account_flows(account_flows, reasons=reasons)


def _sum_account_flows(account_flows: list[dict], *, reasons: set[str] | frozenset[str] | None) -> Decimal:
    total = Decimal("0")
    for flow in account_flows:
        reason = str(flow.get("reason") or "").upper()
        if reasons is not None and reason not in reasons:
            continue
        balance_change = _parse_optional_decimal(flow.get("balance_change"))
        if balance_change is not None:
            total += balance_change
    return total


def _snapshot_delta(account_snapshots: list[dict], *, field: str) -> tuple[str | None, str | None, str | None]:
    if not account_snapshots:
        return None, None, None
    start_value = _parse_optional_decimal(account_snapshots[0].get(field))
    end_value = _parse_optional_decimal(account_snapshots[-1].get(field))
    if start_value is None or end_value is None:
        return (
            None if start_value is None else str(start_value),
            None if end_value is None else str(end_value),
            None,
        )
    return str(start_value), str(end_value), str(end_value - start_value)


def _parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _hour_bucket(value: datetime) -> datetime:
    return value.astimezone(timezone.utc).replace(minute=0, second=0, microsecond=0)


def _parse_decimal(value: object) -> Decimal:
    if isinstance(value, Decimal):
        return value
    return Decimal(str(value))


def _parse_optional_decimal(value: object) -> Decimal | None:
    if value in (None, ""):
        return None
    return _parse_decimal(value)
