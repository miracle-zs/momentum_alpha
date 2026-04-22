from __future__ import annotations

from collections import Counter
from datetime import datetime
from pathlib import Path

from momentum_alpha.dashboard_common import build_strategy_config, normalize_account_range
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_daily_review_report_by_date,
    fetch_daily_review_report_dates,
    fetch_daily_review_reports_summary,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_latest_daily_review_report,
    fetch_recent_account_flows,
    fetch_recent_algo_orders,
    fetch_recent_audit_events,
    fetch_recent_broker_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_trade_round_trips_for_range,
)

from .dashboard_data_common import (
    _account_flow_since,
    _build_leader_history,
    _build_pulse_points,
    _build_source_counts,
    _normalize_events,
    _runtime_summary_from_sources,
    _select_latest_timestamp,
)


def load_dashboard_snapshot(
    *,
    now: datetime,
    poll_log_file: Path | None = None,
    user_stream_log_file: Path | None = None,
    runtime_db_file: Path,
    recent_limit: int = 20,
    stop_budget_usdt: str | None = None,
    entry_start_hour_utc: int = 1,
    entry_end_hour_utc: int = 23,
    testnet: bool = False,
    submit_orders: bool = False,
    account_range_key: str = "1D",
    report_date: str | None = None,
) -> dict:
    account_range_key = normalize_account_range(account_range_key)
    health_report = build_runtime_health_report(
        now=now,
        runtime_db_file=runtime_db_file,
    )
    warnings: list[str] = []
    state_payload: dict = {}

    if runtime_db_file.exists():
        try:
            runtime_state = RuntimeStateStore(path=runtime_db_file).load()
        except Exception as exc:
            warnings.append(f"runtime state unavailable path={runtime_db_file} error={exc}")
            runtime_state = None
        if runtime_state is not None:
            state_payload = {
                "current_day": runtime_state.current_day,
                "previous_leader_symbol": runtime_state.previous_leader_symbol,
                "positions": runtime_state.positions or {},
                "processed_event_ids": runtime_state.processed_event_ids or {},
                "order_statuses": runtime_state.order_statuses or {},
                "recent_stop_loss_exits": runtime_state.recent_stop_loss_exits or {},
            }

    recent_signal_decisions: list[dict] = []
    recent_broker_orders: list[dict] = []
    recent_trade_fills: list[dict] = []
    recent_algo_orders: list[dict] = []
    recent_account_flows: list[dict] = []
    account_metric_flows: list[dict] = []
    recent_trade_round_trips: list[dict] = []
    recent_stop_exit_summaries: list[dict] = []
    recent_position_snapshots: list[dict] = []
    recent_position_risk_snapshots: list[dict] = []
    recent_account_snapshots: list[dict] = []
    daily_review_report: dict | None = None
    daily_review_report_dates: list[str] = []
    daily_review_history_summary: dict | None = None

    if runtime_db_file.exists():
        events_for_metrics = _normalize_events(fetch_recent_audit_events(path=runtime_db_file, limit=max(recent_limit, 300)))
        recent_signal_decisions = fetch_recent_signal_decisions(path=runtime_db_file, limit=8)
        recent_broker_orders = fetch_recent_broker_orders(path=runtime_db_file, limit=8)
        recent_trade_fills = fetch_recent_trade_fills(path=runtime_db_file, limit=20)
        recent_algo_orders = fetch_recent_algo_orders(path=runtime_db_file, limit=20)
        recent_account_flows = fetch_recent_account_flows(path=runtime_db_file, limit=20)
        account_metric_flows = fetch_account_flows_since(
            path=runtime_db_file,
            since=_account_flow_since(now=now, range_key=account_range_key),
        )
        recent_trade_round_trips = fetch_trade_round_trips_for_range(
            path=runtime_db_file,
            now=now,
            range_key="ALL",
        )
        recent_stop_exit_summaries = fetch_recent_stop_exit_summaries(path=runtime_db_file, limit=20)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_position_risk_snapshots = fetch_recent_position_snapshots(
            path=runtime_db_file,
            limit=8,
            require_positions=True,
        )
        recent_account_snapshots = fetch_account_snapshots_for_range(path=runtime_db_file, now=now, range_key=account_range_key)
        daily_review_report_dates = fetch_daily_review_report_dates(path=runtime_db_file)
        daily_review_history_summary = fetch_daily_review_reports_summary(path=runtime_db_file)
        if report_date is not None:
            daily_review_report = fetch_daily_review_report_by_date(path=runtime_db_file, report_date=report_date)
            if daily_review_report is None:
                warnings.append(f"daily review report missing for report_date={report_date}")
                daily_review_report = fetch_latest_daily_review_report(path=runtime_db_file)
        else:
            daily_review_report = fetch_latest_daily_review_report(path=runtime_db_file)
    else:
        events_for_metrics = []
    recent_events = events_for_metrics[:recent_limit]
    event_counts = dict(sorted(Counter(event.get("event_type") for event in events_for_metrics if event.get("event_type")).items()))
    source_counts = _build_source_counts(events_for_metrics)
    if runtime_db_file.exists():
        leader_history = fetch_leader_history(path=runtime_db_file, limit=8)
        if not leader_history:
            leader_history = _build_leader_history(events_for_metrics)
        pulse_points = fetch_event_pulse_points(path=runtime_db_file, now=now, since_minutes=10, bucket_minutes=1, limit=10)
        if not pulse_points:
            pulse_points = _build_pulse_points(events_for_metrics, now=now)
    else:
        leader_history = _build_leader_history(events_for_metrics)
        pulse_points = _build_pulse_points(events_for_metrics, now=now)
    latest_position_snapshot = recent_position_snapshots[0] if recent_position_snapshots else None
    latest_signal_decision = recent_signal_decisions[0] if recent_signal_decisions else None
    latest_broker_order = recent_broker_orders[0] if recent_broker_orders else None
    latest_account_snapshot = recent_account_snapshots[0] if recent_account_snapshots else None
    previous_leader_symbol, position_count, order_status_count = _runtime_summary_from_sources(
        state_payload=state_payload,
        latest_account_snapshot=latest_account_snapshot,
        latest_position_snapshot=latest_position_snapshot,
        latest_signal_decision=latest_signal_decision,
    )

    if daily_review_report is not None:
        daily_review_report = {
            **daily_review_report,
            "requested_report_date": report_date,
            "selected_report_date": daily_review_report.get("report_date"),
            "available_report_dates": daily_review_report_dates,
            "history_summary": daily_review_history_summary or {
                "report_count": 0,
                "trade_count": 0,
                "actual_total_pnl": "0",
                "counterfactual_total_pnl": "0",
                "filter_impact": "0",
                "replayed_add_on_count": 0,
            },
        }

    return {
        "runtime_db_file": str(runtime_db_file),
        "health": {
            "overall_status": health_report.overall_status,
            "items": [
                {"name": item.name, "status": item.status, "message": item.message}
                for item in health_report.items
            ],
        },
        "runtime": {
            "previous_leader_symbol": previous_leader_symbol,
            "position_count": position_count,
            "order_status_count": order_status_count,
            "latest_tick_timestamp": _select_latest_timestamp(recent_events, "poll_tick"),
            "latest_tick_result_timestamp": _select_latest_timestamp(recent_events, "tick_result"),
            "latest_poll_worker_start_timestamp": _select_latest_timestamp(recent_events, "poll_worker_start"),
            "latest_user_stream_start_timestamp": _select_latest_timestamp(recent_events, "user_stream_worker_start"),
            "latest_signal_decision": latest_signal_decision,
            "latest_broker_order": latest_broker_order,
            "latest_position_snapshot": latest_position_snapshot,
            "latest_account_snapshot": latest_account_snapshot,
        },
        "event_counts": event_counts,
        "source_counts": source_counts,
        "leader_history": leader_history,
        "pulse_points": pulse_points,
        "recent_signal_decisions": recent_signal_decisions,
        "recent_broker_orders": recent_broker_orders,
        "recent_trade_fills": recent_trade_fills,
        "recent_algo_orders": recent_algo_orders,
        "recent_account_flows": recent_account_flows,
        "account_metric_flows": account_metric_flows,
        "recent_trade_round_trips": recent_trade_round_trips,
        "recent_stop_exit_summaries": recent_stop_exit_summaries,
        "recent_position_snapshots": recent_position_snapshots,
        "recent_position_risk_snapshots": recent_position_risk_snapshots,
        "recent_account_snapshots": recent_account_snapshots,
        "daily_review_report": daily_review_report,
        "recent_events": recent_events,
        "warnings": warnings,
        "strategy_config": build_strategy_config(
            stop_budget_usdt=stop_budget_usdt,
            entry_start_hour_utc=entry_start_hour_utc,
            entry_end_hour_utc=entry_end_hour_utc,
            testnet=testnet,
            submit_orders=submit_orders,
        ),
    }
