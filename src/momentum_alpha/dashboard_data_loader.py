from __future__ import annotations

from collections import Counter
from datetime import datetime
from functools import wraps
from pathlib import Path
import sqlite3

from momentum_alpha.dashboard_common import build_strategy_config, normalize_account_range
from momentum_alpha.health import build_runtime_health_report
from momentum_alpha.runtime_live_state import (
    hydrate_dashboard_live_snapshot,
    read_dashboard_live_series,
    read_dashboard_live_state,
)
from momentum_alpha.runtime_schema import _connect, _get_reused_runtime_connection, _reuse_runtime_connection
from momentum_alpha.runtime_store import (
    RuntimeStateStore,
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_daily_review_report_by_date,
    fetch_daily_review_report_dates,
    fetch_daily_review_reports_summary,
    fetch_filtered_base_review_report_by_date,
    fetch_filtered_base_review_report_dates,
    fetch_filtered_base_review_reports_summary,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_latest_daily_review_report,
    fetch_latest_filtered_base_review_report,
    fetch_position_snapshots_for_range,
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


_DASHBOARD_REQUIRED_TABLES = frozenset(
    {
        "audit_events",
        "signal_decisions",
        "broker_orders",
        "trade_fills",
        "algo_orders",
        "account_flows",
        "trade_round_trips",
        "stop_exit_summaries",
        "position_snapshots",
        "account_snapshots",
        "daily_review_reports",
    }
)


def _runtime_db_is_readable(path: Path) -> bool:
    reused_connection = _get_reused_runtime_connection(path)
    if reused_connection is not None:
        try:
            rows = reused_connection.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table'"
            ).fetchall()
        except (OSError, sqlite3.Error):
            return False
        return _DASHBOARD_REQUIRED_TABLES.issubset({str(row[0]) for row in rows})

    connection = None
    try:
        connection = sqlite3.connect(path)
        rows = connection.execute(
            "SELECT name FROM sqlite_master WHERE type = 'table'"
        ).fetchall()
    except (OSError, sqlite3.Error):
        return False
    finally:
        if connection is not None:
            connection.close()
    return _DASHBOARD_REQUIRED_TABLES.issubset({str(row[0]) for row in rows})


def _with_dashboard_runtime_connection(function):
    @wraps(function)
    def wrapper(*args, **kwargs):
        runtime_db_file = kwargs.get("runtime_db_file")
        if runtime_db_file is None:
            return function(*args, **kwargs)
        runtime_db_path = Path(runtime_db_file)
        if not runtime_db_path.exists():
            return function(*args, **kwargs)

        connection_context = _connect(runtime_db_path)
        try:
            connection = connection_context.__enter__()
        except (OSError, sqlite3.Error):
            return function(*args, **kwargs)

        try:
            with _reuse_runtime_connection(path=runtime_db_path, connection=connection):
                result = function(*args, **kwargs)
        except BaseException as exc:
            connection_context.__exit__(type(exc), exc, exc.__traceback__)
            raise
        else:
            connection_context.__exit__(None, None, None)
            return result

    return wrapper


@_with_dashboard_runtime_connection
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
    database_readable = runtime_db_file.exists() and _runtime_db_is_readable(runtime_db_file)
    if runtime_db_file.exists() and not database_readable:
        warnings.append(f"runtime database unavailable for dashboard reads path={runtime_db_file}")

    if database_readable:
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
    filtered_review_report: dict | None = None
    daily_review_report_dates: list[str] = []
    filtered_review_report_dates: list[str] = []
    daily_review_history_summary: dict | None = None
    filtered_review_history_summary: dict | None = None

    if database_readable:
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
        recent_position_risk_snapshots = fetch_position_snapshots_for_range(
            path=runtime_db_file,
            now=now,
            range_key=account_range_key,
            require_positions=True,
        )
        recent_account_snapshots = fetch_account_snapshots_for_range(path=runtime_db_file, now=now, range_key=account_range_key)
        daily_review_report_dates = fetch_daily_review_report_dates(path=runtime_db_file)
        daily_review_history_summary = fetch_daily_review_reports_summary(path=runtime_db_file)
        filtered_review_report_dates = fetch_filtered_base_review_report_dates(path=runtime_db_file)
        filtered_review_history_summary = fetch_filtered_base_review_reports_summary(path=runtime_db_file)
        if report_date is not None:
            daily_review_report = fetch_daily_review_report_by_date(path=runtime_db_file, report_date=report_date)
            if daily_review_report is None:
                warnings.append(f"daily review report missing for report_date={report_date}")
                daily_review_report = fetch_latest_daily_review_report(path=runtime_db_file)
            filtered_review_report = fetch_filtered_base_review_report_by_date(
                path=runtime_db_file,
                report_date=report_date,
            )
        else:
            daily_review_report = fetch_latest_daily_review_report(path=runtime_db_file)
            filtered_review_report = fetch_latest_filtered_base_review_report(path=runtime_db_file)
    else:
        events_for_metrics = []
    recent_events = events_for_metrics[:recent_limit]
    event_counts = dict(sorted(Counter(event.get("event_type") for event in events_for_metrics if event.get("event_type")).items()))
    source_counts = _build_source_counts(events_for_metrics)
    if database_readable:
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
        stored_payload = daily_review_report.get("payload") or {}
        if filtered_review_report is None and (
            "filtered_base_summary" in stored_payload or "filtered_base_rows" in stored_payload
        ):
            filtered_review_report = {
                "report_date": daily_review_report.get("report_date"),
                "window_start": daily_review_report.get("window_start"),
                "window_end": daily_review_report.get("window_end"),
                "generated_at": daily_review_report.get("generated_at"),
                "status": "warning"
                if (stored_payload.get("filtered_base_summary") or {}).get("fetch_errors")
                else "ok",
                "warnings": (stored_payload.get("filtered_base_summary") or {}).get("replay_warnings") or [],
                "requested_report_date": report_date,
                "selected_report_date": daily_review_report.get("report_date"),
                "available_report_dates": daily_review_report_dates,
                "history_summary": filtered_review_history_summary or {},
                "payload": {
                    "summary": stored_payload.get("filtered_base_summary") or {},
                    "rows": stored_payload.get("filtered_base_rows") or [],
                },
            }
        daily_payload = {
            key: value
            for key, value in stored_payload.items()
            if key not in {"filtered_base_summary", "filtered_base_rows"}
        }
        daily_review_report = {
            **daily_review_report,
            "payload": daily_payload,
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

    if filtered_review_report is not None and "selected_report_date" not in filtered_review_report:
        filtered_review_report = {
            **filtered_review_report,
            "requested_report_date": report_date,
            "selected_report_date": filtered_review_report.get("report_date"),
            "available_report_dates": filtered_review_report_dates,
            "history_summary": filtered_review_history_summary or filtered_review_report.get("history_summary") or {},
        }

    snapshot = {
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
        "filtered_review_report": filtered_review_report,
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
    reused_connection = _get_reused_runtime_connection(runtime_db_file)
    if database_readable and reused_connection is not None:
        hydrate_dashboard_live_snapshot(connection=reused_connection, snapshot=snapshot)
    return snapshot


@_with_dashboard_runtime_connection
def load_dashboard_live_snapshot(
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
    """Load only the current dashboard room and short live projections.

    The normal dashboard loader intentionally reads the full review and system
    history.  The live room refreshes every few seconds, so it uses the
    write-maintained projection and bounded recent queries instead.
    """
    account_range_key = normalize_account_range(account_range_key)
    health_report = build_runtime_health_report(
        now=now,
        runtime_db_file=runtime_db_file,
    )
    warnings: list[str] = []
    state_payload: dict = {}
    live_state: dict[str, dict] = {}
    live_series = {"account": [], "position": []}
    database_readable = runtime_db_file.exists() and _runtime_db_is_readable(runtime_db_file)
    if runtime_db_file.exists() and not database_readable:
        warnings.append(f"runtime database unavailable for dashboard reads path={runtime_db_file}")

    if database_readable:
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

    if database_readable:
        reused_connection = _get_reused_runtime_connection(runtime_db_file)
        if reused_connection is not None:
            live_state = read_dashboard_live_state(connection=reused_connection)
            live_series = read_dashboard_live_series(
                connection=reused_connection,
                now=now,
                range_key=account_range_key,
            )
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
        live_range_key = account_range_key if account_range_key in {"1H", "1D", "1W"} else "1D"
        recent_trade_round_trips = fetch_trade_round_trips_for_range(
            path=runtime_db_file,
            now=now,
            range_key=live_range_key,
        )
        recent_stop_exit_summaries = fetch_recent_stop_exit_summaries(path=runtime_db_file, limit=20)
        recent_position_snapshots = fetch_recent_position_snapshots(path=runtime_db_file, limit=8)
        recent_account_snapshots = list(live_series.get("account") or [])
        if not recent_account_snapshots:
            recent_account_snapshots = fetch_account_snapshots_for_range(
                path=runtime_db_file,
                now=now,
                range_key=account_range_key,
            )
        recent_position_risk_snapshots = list(live_series.get("position") or [])
        if not recent_position_risk_snapshots:
            recent_position_risk_snapshots = fetch_position_snapshots_for_range(
                path=runtime_db_file,
                now=now,
                range_key=account_range_key,
                require_positions=True,
            )
    else:
        events_for_metrics = []

    recent_events = events_for_metrics[:recent_limit]
    event_counts = dict(sorted(Counter(event.get("event_type") for event in events_for_metrics if event.get("event_type")).items()))
    source_counts = _build_source_counts(events_for_metrics)

    if database_readable:
        leader_history = fetch_leader_history(path=runtime_db_file, limit=8)
        if not leader_history:
            leader_history = _build_leader_history(events_for_metrics)
        pulse_points = fetch_event_pulse_points(path=runtime_db_file, now=now, since_minutes=10, bucket_minutes=1, limit=10)
        if not pulse_points:
            pulse_points = _build_pulse_points(events_for_metrics, now=now)
    else:
        leader_history = _build_leader_history(events_for_metrics)
        pulse_points = _build_pulse_points(events_for_metrics, now=now)

    latest_position_snapshot = live_state.get("latest_position_snapshot") or (
        recent_position_snapshots[0] if recent_position_snapshots else None
    )
    latest_signal_decision = live_state.get("latest_signal_decision") or (
        recent_signal_decisions[0] if recent_signal_decisions else None
    )
    latest_broker_order = live_state.get("latest_broker_order") or (
        recent_broker_orders[0] if recent_broker_orders else None
    )
    latest_account_snapshot = live_state.get("latest_account_snapshot") or (
        recent_account_snapshots[-1] if recent_account_snapshots else None
    )
    if latest_account_snapshot is not None and not recent_account_snapshots:
        recent_account_snapshots = [latest_account_snapshot]
    if latest_position_snapshot is not None and not recent_position_risk_snapshots:
        recent_position_risk_snapshots = [latest_position_snapshot]
    previous_leader_symbol, position_count, order_status_count = _runtime_summary_from_sources(
        state_payload=state_payload,
        latest_account_snapshot=latest_account_snapshot,
        latest_position_snapshot=latest_position_snapshot,
        latest_signal_decision=latest_signal_decision,
    )

    snapshot = {
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
        "daily_review_report": None,
        "filtered_review_report": None,
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
    reused_connection = _get_reused_runtime_connection(runtime_db_file)
    if database_readable and reused_connection is not None:
        hydrate_dashboard_live_snapshot(connection=reused_connection, snapshot=snapshot)
    return snapshot
