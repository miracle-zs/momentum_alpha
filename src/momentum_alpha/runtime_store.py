from __future__ import annotations

from momentum_alpha.runtime_analytics import rebuild_trade_analytics
from momentum_alpha.runtime_state_store import RuntimeStateStore
from momentum_alpha.runtime_reads import (
    fetch_account_flows_since,
    fetch_account_snapshots_for_range,
    fetch_audit_event_counts,
    fetch_event_pulse_points,
    fetch_leader_history,
    fetch_daily_review_report_by_date,
    fetch_daily_review_report_dates,
    fetch_daily_review_reports_summary,
    fetch_latest_daily_review_report,
    fetch_notification_status,
    fetch_recent_account_flows,
    fetch_recent_account_snapshots,
    fetch_recent_audit_events,
    fetch_recent_broker_orders,
    fetch_recent_algo_orders,
    fetch_recent_position_snapshots,
    fetch_recent_signal_decisions,
    fetch_recent_stop_exit_summaries,
    fetch_recent_trade_fills,
    fetch_recent_trade_round_trips,
    fetch_position_snapshots_for_range,
    fetch_signal_decisions_for_window,
    fetch_trade_round_trips_for_range,
    fetch_trade_round_trips_for_window,
    summarize_audit_events,
)
from momentum_alpha.runtime_writes import (
    insert_account_flow,
    insert_account_snapshot,
    insert_audit_event,
    insert_algo_order,
    insert_broker_order,
    insert_daily_review_report,
    insert_position_snapshot,
    insert_signal_decision,
    insert_stop_exit_summary,
    insert_trade_fill,
    insert_trade_round_trip,
    save_notification_status,
)
from momentum_alpha.runtime_schema import _connect, bootstrap_runtime_db
from momentum_alpha.strategy_state_codec import (
    StoredStrategyState,
    deserialize_strategy_state,
    serialize_strategy_state,
)


MAX_PROCESSED_EVENT_ID_AGE_HOURS = 24
