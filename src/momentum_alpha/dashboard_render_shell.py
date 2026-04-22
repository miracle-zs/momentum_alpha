from __future__ import annotations

from html import escape

from .dashboard_assets import render_dashboard_head, render_dashboard_scripts
from .dashboard_common import normalize_account_range
from .dashboard_data import build_dashboard_timeseries_payload, build_trade_leg_count_aggregates, build_trade_leg_index_aggregates
from .dashboard_render_panels import (
    _build_account_metrics_panel,
    _build_account_snapshot_panel,
    _build_execution_flow_panel,
    _build_live_account_risk_panel,
    _build_live_core_lines_panel,
    _build_overview_home_command,
    _render_timeline_svg,
    render_cosmic_identity_panel,
    render_daily_review_panel,
)
from .dashboard_render_tables import (
    render_closed_trades_table,
    render_position_cards,
    render_stop_slippage_table,
    render_trade_history_table,
    render_trade_leg_count_aggregate_table,
    render_trade_leg_index_aggregate_table,
)
from .dashboard_render_utils import (
    DASHBOARD_ROOMS,
    DISPLAY_TIMEZONE,
    DISPLAY_TIMEZONE_NAME,
    LEGACY_DASHBOARD_TAB_TO_ROOM,
    REVIEW_VIEWS,
    _build_dashboard_room_href,
    _format_duration_seconds,
    _format_metric,
    format_timestamp_for_display,
    normalize_dashboard_room,
    normalize_review_view,
)
from .dashboard_view_model import _compute_account_range_stats, build_position_details, build_trader_summary_metrics


def _build_execution_mode(config: dict) -> tuple[str, str]:
    venue = "TESTNET" if config.get("testnet") else "PROD"
    order_mode = "LIVE" if config.get("submit_orders") else "DRY RUN"
    state = "danger" if venue == "PROD" and order_mode == "LIVE" else "warning"
    return f"{venue} {order_mode}", state


_RECENT_SIGNAL_ACTION_TYPES = {"base_entry", "add_on", "add_on_skipped", "stop_update"}
_RECENT_AUDIT_ACTION_TYPES = {
    "broker_submit",
    "broker_replace",
    "user_stream_event",
    "account_flow_insert_error",
    "poll_error",
}


def _build_recent_action_detail(event_type: str, payload: dict, *, source: str | None = None) -> str:
    parts: list[str] = []
    source_label = str(source or "").strip()
    if source_label:
        parts.append(source_label)
    if event_type in {"broker_submit", "broker_replace"}:
        responses = payload.get("responses")
        if isinstance(responses, list):
            parts.append(f"responses={len(responses)}")
        return " · ".join(parts) if parts else "broker action"
    if event_type == "user_stream_event":
        symbol = payload.get("symbol")
        status = payload.get("order_status") or payload.get("execution_type") or payload.get("event_type")
        if symbol:
            parts.append(str(symbol))
        if status:
            parts.append(str(status))
        return " · ".join(parts) if parts else "user stream event"
    if event_type == "account_flow_insert_error":
        error = payload.get("error") or payload.get("message")
        if error:
            parts.append(str(error))
        return " · ".join(parts) if parts else "account flow error"
    if event_type == "poll_error":
        error = payload.get("error") or payload.get("message")
        if error:
            parts.append(str(error))
        return " · ".join(parts) if parts else "poll error"
    symbol = payload.get("symbol")
    stop_price = payload.get("stop_price")
    blocked_reason = payload.get("blocked_reason")
    if symbol:
        parts.append(str(symbol))
    if stop_price is not None:
        parts.append(f"stop={stop_price}")
    if blocked_reason:
        parts.append(str(blocked_reason))
    return " · ".join(parts) if parts else "action"


def _build_recent_action_events_html(*, recent_signal_decisions: list[dict], recent_events: list[dict]) -> str:
    action_events: list[dict] = []
    for decision in recent_signal_decisions:
        decision_type = str(decision.get("decision_type") or "")
        if decision_type not in _RECENT_SIGNAL_ACTION_TYPES:
            continue
        payload = decision.get("payload") or {}
        action_events.append(
            {
                "timestamp": decision.get("timestamp"),
                "event_type": decision_type,
                "detail": _build_recent_action_detail(decision_type, payload, source=decision.get("source")),
            }
        )
    for event in recent_events:
        event_type = str(event.get("event_type") or "")
        if event_type not in _RECENT_AUDIT_ACTION_TYPES:
            continue
        payload = event.get("payload") or {}
        action_events.append(
            {
                "timestamp": event.get("timestamp"),
                "event_type": event_type,
                "detail": _build_recent_action_detail(event_type, payload, source=event.get("source")),
            }
        )
    action_events.sort(key=lambda item: item.get("timestamp") or "", reverse=True)
    rendered_events = action_events[:12]
    return "".join(
        f"<div class='event-item'>"
        f"<span class='event-type'>{escape(str(event['event_type']))}</span>"
        f"<span class='event-time'>{escape(format_timestamp_for_display(event['timestamp']))}</span>"
        f"<span class='event-detail'>{escape(str(event['detail']) if event.get('detail') else '-')}</span></div>"
        for event in rendered_events
    ) or "<div class='event-item empty'>No recent action events</div>"


def normalize_dashboard_tab(value: str | None) -> str:
    room = normalize_dashboard_room(value)
    return {"live": "overview", "review": "performance", "system": "system"}[room]


def render_dashboard_room_nav(
    active_room: str,
    *,
    account_range_key: str = "1D",
    review_view: str = "overview",
) -> str:
    active_room = normalize_dashboard_room(active_room)
    review_view = normalize_review_view(review_view)
    labels = {
        "live": "实时监控室",
        "review": "复盘室",
        "system": "系统状态室",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if room == active_room else ""}" '
            f'data-dashboard-room="{room}" href="{_build_dashboard_room_href(room=room, account_range_key=account_range_key, review_view=review_view)}">{escape(labels[room])}</a>'
        )
        for room in DASHBOARD_ROOMS
    )
    return (
        '<nav class="dashboard-tabs" data-dashboard-section="room-nav" aria-label="Dashboard rooms">'
        f"{links}"
        "</nav>"
    )


def render_dashboard_tab_bar(active_tab: str, *, account_range_key: str = "1D") -> str:
    return render_dashboard_room_nav(normalize_dashboard_room(active_tab), account_range_key=account_range_key)


def render_dashboard_live_room(
    *,
    account_risk_html: str,
    core_lines_html: str,
    top_metrics_html: str,
    hero_html: str,
    positions_html: str,
    home_command_html: str,
    execution_flow_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        "<section class='section-frame live-control-frame'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>实时监控室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Use the cockpit to read risk, trend, and action surface in one pass.</div>"
        "</div>"
        "</div>"
        f"<div class='live-risk-band'>{account_risk_html}</div>"
        f"<div class='live-core-lines-band'>{core_lines_html}</div>"
        f"<div class='live-signal-band'>{hero_html}</div>"
        "<div class='live-decision-grid'>"
        "<section class='dashboard-section active-positions-panel live-card-shell'>"
        "<div class='section-header'>ACTIVE POSITIONS</div>"
        f"{positions_html}"
        "</section>"
        f"<div class='live-decision-side'>{execution_flow_html}</div>"
        "</div>"
        f"<div class='live-command-band'>{home_command_html}</div>"
        f"<div class='metrics-grid live-metrics-grid' data-live-metrics-panel>{top_metrics_html}</div>"
        "</div>"
    )


def render_dashboard_overview_tab(
    *,
    account_risk_html: str,
    core_lines_html: str,
    top_metrics_html: str,
    hero_html: str,
    positions_html: str,
    home_command_html: str,
    execution_flow_html: str,
) -> str:
    return render_dashboard_live_room(
        account_risk_html=account_risk_html,
        core_lines_html=core_lines_html,
        top_metrics_html=top_metrics_html,
        hero_html=hero_html,
        positions_html=positions_html,
        home_command_html=home_command_html,
        execution_flow_html=execution_flow_html,
    )


def render_dashboard_execution_tab(*, execution_flow_html: str, execution_summary_html: str, trade_history_html: str, stop_slippage_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        f"{execution_flow_html}"
        "<section class='section-frame' data-collapsible-section='execution'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>EXECUTION QUALITY</div>"
        "<button type='button' class='section-toggle' data-section-toggle='execution'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        "<div class='analytics-grid'>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Execution Summary</div>"
        f"{execution_summary_html}"
        "</div>"
        "<div class='chart-card'>"
        "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>Recent Fills</div>"
        f"<div class='table-scroll'>{trade_history_html}</div>"
        "</div>"
        "<div class='chart-card'>"
        "<div class='section-header' style='margin-bottom:10px;'>STOP SLIPPAGE ANALYSIS</div>"
        f"<div class='table-scroll'>{stop_slippage_html}</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_performance_tab(
    *,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="review">'
        "<section class='section-frame' data-collapsible-section='review'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>复盘室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Trade review analysis starts with the summary strip, then drills into trade detail and evidence tables.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body review-analysis-shell'>"
        "<div class='review-summary-strip'>"
        "<div class='review-summary-ribbon'>"
        "<div class='review-summary-copy-block'>"
        "<div class='section-header review-summary-kicker'>TRADE REVIEW SUMMARY</div>"
        "<div class='review-summary-copy'>High-level read on closed-trade quality before drilling into the ledger.</div>"
        "</div>"
        f"<div class='review-summary-ribbon-items'>{performance_summary_html}</div>"
        "</div>"
        "</div>"
        "<div class='review-analysis-main-row'>"
        "<div class='chart-card review-analysis-main'>"
        "<div class='review-section-label'>Closed Trade Detail</div>"
        f"<div class='table-scroll'>{round_trip_detail_html}</div>"
        "</div>"
        "</div>"
        "<div class='review-analysis-evidence-grid'>"
        "<div class='chart-card review-analysis-card'>"
        "<div class='review-section-label'>By Total Leg Count</div>"
        f"<div class='table-scroll'>{leg_count_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card review-analysis-card'>"
        "<div class='review-section-label'>By Leg Index</div>"
        f"<div class='table-scroll'>{leg_index_aggregate_html}</div>"
        "</div>"
        "<div class='chart-card review-analysis-card'>"
        "<div class='review-section-label'>Stop Slippage Analysis</div>"
        f"<div class='table-scroll'>{stop_slippage_html}</div>"
        "</div>"
        "</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_review_tabs(active_review_view: str, *, account_range_key: str = "1D") -> str:
    active_review_view = normalize_review_view(active_review_view)
    labels = {
        "overview": "总体复盘",
        "daily": "每日复盘",
    }
    links = "".join(
        (
            f'<a class="dashboard-tab{" is-active" if view == active_review_view else ""}" '
            f'data-dashboard-review-view="{view}" href="{_build_dashboard_room_href(room="review", account_range_key=account_range_key, review_view=view)}">{escape(labels[view])}</a>'
        )
        for view in REVIEW_VIEWS
    )
    return (
        '<nav class="dashboard-tabs review-tabs" data-dashboard-section="review-tabs" aria-label="Review views">'
        f"{links}"
        "</nav>"
    )


def render_daily_review_room(*, daily_review_html: str) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-review-view-content="daily">'
        "<section class='section-frame' data-collapsible-section='review-daily'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>每日复盘</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>UTC+8 08:30 to UTC+8 08:30 trading window.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review-daily'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body'>"
        f"{daily_review_html}"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_review_room(
    *,
    active_review_view: str,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
    daily_review_html: str,
) -> str:
    active_review_view = normalize_review_view(active_review_view)
    if active_review_view == "daily":
        body_html = render_daily_review_room(daily_review_html=daily_review_html)
    else:
        body_html = render_dashboard_performance_tab(
            performance_summary_html=performance_summary_html,
            round_trip_detail_html=round_trip_detail_html,
            leg_count_aggregate_html=leg_count_aggregate_html,
            leg_index_aggregate_html=leg_index_aggregate_html,
            stop_slippage_html=stop_slippage_html,
        )
    return f"{render_dashboard_review_tabs(active_review_view)}{body_html}"


def render_dashboard_system_room(
    *,
    diagnostics_html: str,
    warning_list_html: str,
    config_html: str,
    health_items_html: str,
    recent_events_html: str,
    runtime_db_path_display: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="system">'
        "<section class='section-frame' data-collapsible-section='system'>"
        "<div class='section-topbar'>"
        "<div class='section-header'>系统状态室</div>"
        "<button type='button' class='section-toggle' data-section-toggle='system'>Collapse</button>"
        "</div>"
        "<div class='dashboard-section section-body system-analysis-shell'>"
        "<div class='system-summary-strip'>"
        "<div class='system-summary-head'>"
        "<div class='section-header system-summary-kicker'>SYSTEM DIAGNOSTICS</div>"
        "<div class='system-summary-copy'>Watch runtime freshness, warnings, and config state before inspecting the event stream.</div>"
        "</div>"
        f"{diagnostics_html}"
        f"{warning_list_html}"
        "</div>"
        "<div class='system-console-grid'>"
        "<div class='chart-card system-health-panel'>"
        "<div class='section-header'>SYSTEM HEALTH</div>"
        "<div class='system-health-path'>"
        f"Runtime DB: {escape(str(runtime_db_path_display or 'n/a'))}"
        "</div>"
        f"<div class='health-grid'>{health_items_html}</div>"
        "</div>"
        "<div class='chart-card system-console-card'>"
        "<div class='section-header'>SYSTEM CONFIG</div>"
        f"{config_html}"
        "</div>"
        "</div>"
        "<div class='chart-card system-console-events'>"
        "<div class='section-header'>RECENT EVENTS</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Actions only. Poll heartbeats are filtered out.</div>"
        f"<div class='event-list' style='max-height:320px;overflow-y:auto;'>{recent_events_html}</div>"
        "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_system_tab(
    *,
    diagnostics_html: str,
    warning_list_html: str,
    config_html: str,
    health_items_html: str,
    recent_events_html: str,
    runtime_db_path_display: str,
) -> str:
    return render_dashboard_system_room(
        diagnostics_html=diagnostics_html,
        warning_list_html=warning_list_html,
        config_html=config_html,
        health_items_html=health_items_html,
        recent_events_html=recent_events_html,
        runtime_db_path_display=runtime_db_path_display,
    )


def render_dashboard_shell(
    *,
    health_status: str,
    latest_update_display: str | None,
    execution_mode_label: str,
    execution_mode_state: str,
    active_room: str,
    room_nav_html: str,
    room_content_html: str,
) -> str:
    return (
        "<body>"
        "<div class='app'>"
        "<div class='app-shell'>"
        "<header class='header'>"
        "<div class='header-left'>"
        "<div class='logo'>M</div>"
        "<div class='title-group'>"
        "<h1>Momentum Alpha</h1>"
        "<p>Leader Rotation Strategy · Real-time Trading Monitor</p>"
        "</div>"
        "</div>"
        "<div class='header-status' data-dashboard-section='status'>"
        f"<div class='mode-badge {escape(execution_mode_state)}'>{escape(execution_mode_label)}</div>"
        f"<div class='status-badge {'ok' if health_status == 'OK' else 'fail'}'>{escape(health_status)}</div>"
        "</div>"
        "</header>"
        "<div class='toolbar' data-dashboard-section='toolbar'>"
        f"<div class='status-line'>Last update <strong id='last-updated-text'>{escape(format_timestamp_for_display(latest_update_display))}</strong></div>"
        "<div class='status-line'>Auto refresh 5s</div>"
        "<div class='toolbar-spacer'></div>"
        "<button type='button' class='action-button' id='manual-refresh-button'>MANUAL REFRESH</button>"
        "</div>"
        f"{room_nav_html}"
        f"<div class='dashboard-tab-shell' data-dashboard-active-room='{active_room}'>{room_content_html}</div>"
        "</div>"
        "</div>"
    )


def render_dashboard_document(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    return (
        "<!doctype html>\n"
        '<html lang="zh-CN">\n'
        f"{render_dashboard_head()}\n"
        f"{render_dashboard_body(snapshot, strategy_config=strategy_config, active_room=active_room, active_tab=active_tab, review_view=review_view, account_range_key=account_range_key)}"
        f"{render_dashboard_scripts()}"
    )


def render_dashboard_body(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    active_room = normalize_dashboard_room(active_room if active_room is not None else active_tab)
    review_view = normalize_review_view(review_view)
    account_range_key = normalize_account_range(account_range_key)
    timeseries = build_dashboard_timeseries_payload(snapshot)
    runtime = snapshot["runtime"]
    latest_signal = runtime.get("latest_signal_decision") or {}
    latest_position_snapshot = runtime.get("latest_position_snapshot") or {}
    latest_account_snapshot = runtime.get("latest_account_snapshot") or {}
    latest_signal_payload = latest_signal.get("payload") or {}
    blocked_reason = latest_signal_payload.get("blocked_reason")
    decision_status = latest_signal.get("decision_type") or "none"
    latest_signal_symbol = latest_signal.get("symbol") or "none"
    latest_signal_time = format_timestamp_for_display(latest_signal.get("timestamp"))
    config = strategy_config or snapshot.get("strategy_config") or {}
    execution_mode_label, execution_mode_state = _build_execution_mode(config)
    account_range_stats = _compute_account_range_stats(timeseries["account"])
    event_counts = snapshot.get("event_counts", {})
    decision_counts = {k: v for k, v in event_counts.items() if "decision" in k.lower() or "entry" in k.lower() or "signal" in k.lower()} or event_counts
    leader_history = list(reversed(snapshot.get("leader_history", [])))
    timeline_chart = _render_timeline_svg(events=leader_history)
    health_status = snapshot["health"]["overall_status"]
    recent_events = snapshot.get("recent_events") or []
    equity_value = latest_account_snapshot.get("equity")
    position_details = build_position_details(latest_position_snapshot, equity_value=equity_value)
    trader_metrics = build_trader_summary_metrics(
        snapshot,
        position_details=position_details,
        range_key=account_range_key,
    )
    review_metrics = build_trader_summary_metrics(
        snapshot,
        position_details=position_details,
        range_key="ALL",
    )
    account_risk_html = _build_live_account_risk_panel(
        trader_metrics=trader_metrics,
        account_range_stats=account_range_stats,
    )
    core_lines_html = _build_live_core_lines_panel(timeseries["account"], timeseries["position_risk"])
    home_command_html = _build_overview_home_command(
        position_details=position_details,
        trader_metrics=trader_metrics,
        account_range_stats=account_range_stats,
        health_status=health_status,
        account_range_key=account_range_key,
    )
    trade_fills = snapshot.get("recent_trade_fills") or []
    recent_signal_decisions = snapshot.get("recent_signal_decisions") or []
    recent_events = snapshot.get("recent_events") or []
    recent_broker_orders = snapshot.get("recent_broker_orders") or []
    recent_algo_orders = snapshot.get("recent_algo_orders") or []
    recent_stop_exit_summaries = snapshot.get("recent_stop_exit_summaries") or []
    trade_history_html = render_trade_history_table(trade_fills)
    recent_trade_round_trips = snapshot.get("recent_trade_round_trips") or []
    closed_trades_html = render_closed_trades_table(recent_trade_round_trips)
    leg_count_aggregate_html = render_trade_leg_count_aggregate_table(build_trade_leg_count_aggregates(recent_trade_round_trips))
    leg_index_aggregate_html = render_trade_leg_index_aggregate_table(build_trade_leg_index_aggregates(recent_trade_round_trips))
    stop_slippage_html = render_stop_slippage_table(recent_stop_exit_summaries)
    execution_flow_html = _build_execution_flow_panel(
        recent_broker_orders=recent_broker_orders,
        recent_algo_orders=recent_algo_orders,
        recent_trade_fills=trade_fills,
        recent_stop_exit_summaries=recent_stop_exit_summaries,
    )
    config_html = (
        f"<div class='config-panel'>"
        f"<div class='config-row'><span class='config-label'>Stop Budget</span><span>{escape(str(config.get('stop_budget_usdt') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Entry Window</span><span>{escape(str(config.get('entry_window') or 'n/a'))}</span></div>"
        f"<div class='config-row'><span class='config-label'>Testnet</span><span class='{'config-value-true' if config.get('testnet') else 'config-value-false'}'>{'Yes' if config.get('testnet') else 'No'}</span></div>"
        f"<div class='config-row'><span class='config-label'>Submit Orders</span><span class='{'config-value-true' if config.get('submit_orders') else 'config-value-false'}'>{'Yes' if config.get('submit_orders') else 'No'}</span></div>"
        f"</div>"
    )
    runtime_db_path_display = snapshot.get("runtime_db_file") or "n/a"
    recent_events_html = _build_recent_action_events_html(
        recent_signal_decisions=recent_signal_decisions,
        recent_events=recent_events,
    )
    latest_update_display = max(
        [
            timestamp
            for timestamp in (
                runtime.get("latest_tick_result_timestamp"),
                latest_signal.get("timestamp"),
                recent_events[0].get("timestamp") if recent_events else None,
            )
            if timestamp
        ],
        default=None,
    )
    health_items_html = "".join(
        f"<div class='health-item status-{escape(item['status'].lower())}'>"
        f"<span class='health-status-dot'></span>"
        f"<span class='health-name'>{escape(item['name'])}</span>"
        f"<span class='health-status'>{escape(item['status'])}</span>"
        f"<span class='health-msg'>{escape(item['message'])}</span></div>"
        for item in snapshot["health"]["items"]
    )
    warnings = snapshot.get("warnings", [])
    diagnostics_html = (
        "<div class='dashboard-section system-diagnostics-panel section-body'>"
        "<div class='section-header'>SYSTEM DIAGNOSTICS</div>"
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Health Status</div><div class='decision-value'>{escape(str(health_status))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Data Freshness</div><div class='decision-value'>{escape(format_timestamp_for_display(latest_update_display))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Warning Count</div><div class='decision-value'>{escape(str(len(warnings)))}</div></div>"
        "</div>"
        "</div>"
    )
    warning_list_html = (
        "<div class='dashboard-section system-warning-panel section-body'>"
        "<div class='section-header'>ACTIVE WARNINGS</div>"
        "<div class='system-warning-list'>"
        + "".join(f"<div class='system-warning-item'>{escape(str(warning))}</div>" for warning in warnings[:5])
        + "</div>"
        "</div>"
        if warnings
        else ""
    )

    def _format_pct(value: float | None, *, signed: bool = False) -> str:
        if value is None:
            return "n/a"
        if signed and float(value) == 0:
            return "0.00%"
        return f"{value:+,.2f}%" if signed else f"{value:,.2f}%"

    performance_win_rate = review_metrics["performance"].get("win_rate")
    health_metric_state = "danger" if health_status != "OK" else ""
    blocked_reason_counts = trader_metrics["signals"].get("blocked_reason_counts", {})
    blocked_reason_summary = ", ".join(
        f"{reason}: {count}"
        for reason, count in blocked_reason_counts.items()
    ) or "No blocked signals"
    blocked_reason_breakdown_html = (
        "<div class='signal-breakdown'>"
        + "".join(
            f"<div class='signal-breakdown-item'><span class='signal-breakdown-label'>{escape(str(reason))}</span><span class='signal-breakdown-count'>{escape(str(count))}</span></div>"
            for reason, count in blocked_reason_counts.items()
        )
        + "</div>"
        if blocked_reason_counts
        else "<div class='signal-breakdown-empty compact'>No blocked signals</div>"
    )
    recent_leader_sequence = [str(item.get("symbol") or "-") for item in leader_history[:5]]
    recent_leader_sequence_html = (
        " \u2192 ".join(recent_leader_sequence)
        if len(recent_leader_sequence) >= 2
        else "insufficient history"
    )
    open_risk_pct = trader_metrics["account"].get("open_risk_pct")
    if open_risk_pct is None:
        open_risk_state = ""
    elif open_risk_pct > 60:
        open_risk_state = "danger"
    elif open_risk_pct >= 30:
        open_risk_state = "warning"
    else:
        open_risk_state = "normal"
    top_metric_cards = [
        (
            "EQUITY",
            _format_metric(trader_metrics["account"].get("current_equity")),
            "Latest account snapshot",
            "",
        ),
        (
            "TODAY NET PNL",
            _format_metric(trader_metrics["account"].get("today_net_pnl"), signed=True),
            "Adjusted equity delta across visible account history",
            "",
        ),
        (
            "OPEN RISK / EQUITY",
            _format_pct(trader_metrics["account"].get("open_risk_pct")),
            f"{_format_metric(trader_metrics['account'].get('open_risk'))} USDT at risk",
            open_risk_state,
        ),
        (
            "SYSTEM HEALTH",
            escape(health_status),
            f"Last update {format_timestamp_for_display(latest_update_display)}",
            health_metric_state,
        ),
    ]
    live_metrics_html = "".join(
        (
            f"<div class='metric {metric_state}'>"
            f"<div class='metric-label'>{label}</div>"
            f"<div class='metric-value {'negative' if str(value).startswith('-') else 'positive' if str(value).startswith('+') else ''}'>{escape(str(value))}</div>"
            f"<div class='metric-sub'>{escape(subtext)}</div>"
            "</div>"
        )
        for label, value, subtext, metric_state in top_metric_cards
    )
    execution_summary_html = (
        "<div class='decision-grid'>"
        f"<div class='decision-item'><div class='decision-label'>Avg Slippage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['execution'].get('avg_slippage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Max Slippage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['execution'].get('max_slippage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Stop Exits</div><div class='decision-value'>{escape(str(trader_metrics['execution'].get('stop_exit_count') or 0))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Fee Total</div><div class='decision-value'>{escape(_format_metric(trader_metrics['execution'].get('fee_total')))}</div></div>"
        "</div>"
    )
    performance_summary_items = [
        ("Win Rate", _format_pct(performance_win_rate * 100) if performance_win_rate is not None else "n/a"),
        ("Profit Factor", _format_metric(review_metrics["performance"].get("profit_factor"))),
        ("Expectancy", _format_metric(review_metrics["performance"].get("expectancy"), signed=True)),
        ("Avg Hold", _format_duration_seconds(review_metrics["performance"].get("avg_hold_time_seconds"))),
        ("Closed Trades", str(review_metrics["performance"].get("trade_count") or 0)),
        ("Current Streak", str((review_metrics["performance"].get("current_streak") or {}).get("label") or "n/a")),
        ("Avg Win", _format_metric(review_metrics["performance"].get("avg_win"))),
        ("Avg Loss", _format_metric(review_metrics["performance"].get("avg_loss"), signed=True)),
    ]
    performance_summary_html = "".join(
        (
            "<div class='review-summary-ribbon-item'>"
            f"<div class='review-summary-ribbon-label'>{escape(label)}</div>"
            f"<div class='review-summary-ribbon-value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in performance_summary_items
    )
    risk_overview_html = (
        "<div class='decision-grid decision-grid-stack'>"
        f"<div class='decision-item'><div class='decision-label'>Available Balance</div><div class='decision-value'>{escape(_format_metric(trader_metrics['account'].get('current_available_balance')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Margin Usage</div><div class='decision-value'>{escape(_format_pct(trader_metrics['account'].get('margin_usage_pct')))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Current Drawdown</div><div class='decision-value'>{escape(_format_metric(account_range_stats.get('drawdown_abs'), signed=True))}</div><div class='decision-support'>{escape(_format_pct(account_range_stats.get('drawdown_pct'), signed=True))}</div></div>"
        f"<div class='decision-item'><div class='decision-label'>Positions / Orders</div><div class='decision-value'>{escape(str(trader_metrics['account'].get('current_positions') or 0))} / {escape(str(trader_metrics['account'].get('current_orders') or 0))}</div></div>"
        "</div>"
    )
    hero_html = (
        "<section class='hero-grid'>"
        "<div class='hero-card hero-card-wide'>"
        "<div class='hero-eyebrow'>LIVE OVERVIEW</div>"
        "<div class='hero-title'>ACTIVE SIGNAL</div>"
        "<div class='hero-copy'>Keep the current decision, rotation context, and blocked reasons in one glance before drilling into execution details.</div>"
        "<div class='decision-grid'>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Decision Type</div>"
        f"<div class='decision-value'>{escape(str(decision_status))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Target Symbol</div>"
        f"<div class='decision-value'>{escape(str(latest_signal_symbol))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Blocked Reason</div>"
        f"<div class='decision-value'>{escape(str(blocked_reason or 'None'))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Decision Time</div>"
        f"<div class='decision-value'>{escape(latest_signal_time)}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Rotation Count</div>"
        f"<div class='decision-value'>{escape(str(trader_metrics['signals'].get('rotation_count') or 0))}</div>"
        "</div>"
        "<div class='decision-item'>"
        "<div class='decision-label'>Blocked Reasons</div>"
        f"{f'<div class=\"decision-value\" style=\"margin-bottom:8px;\">{escape(blocked_reason_summary)}</div>' if blocked_reason_counts else ''}"
        f"{blocked_reason_breakdown_html}"
        "</div>"
        "</div>"
        "</div>"
        "<div class='hero-card hero-card-compact'>"
        "<div class='hero-eyebrow'>RISK &amp; DEPLOYMENT</div>"
        "<div class='hero-title'>Capital Pressure</div>"
        "<div class='hero-copy'>Balance available capital against live drawdown and deployed risk before the next tick updates the book.</div>"
        f"{risk_overview_html}"
        "</div>"
        "<div class='hero-card hero-card-compact'>"
        "<div class='hero-eyebrow'>LEADER ROTATION</div>"
        "<div class='hero-title'>Sequence Monitor</div>"
        f"<div class='chart-container'>{timeline_chart}</div>"
        "<div class='rotation-summary'>"
        "<div class='rotation-summary-label'>Recent Sequence</div>"
        f"<div class='rotation-summary-value'>{escape(recent_leader_sequence_html)}</div>"
        "</div>"
        "</div>"
        "</section>"
    )
    room_nav_html = render_dashboard_room_nav(
        active_room,
        account_range_key=account_range_key,
        review_view=review_view,
    )
    daily_review_html = render_daily_review_panel(snapshot.get("daily_review_report"))
    room_content_html = {
        "live": render_dashboard_live_room(
            account_risk_html=account_risk_html,
            core_lines_html=core_lines_html,
            top_metrics_html=live_metrics_html,
            hero_html=hero_html,
            positions_html=render_position_cards(position_details),
            home_command_html=home_command_html,
            execution_flow_html=execution_flow_html,
        ),
        "review": render_dashboard_review_room(
            active_review_view=review_view if active_room == "review" else "overview",
            daily_review_html=daily_review_html,
            performance_summary_html=performance_summary_html,
            round_trip_detail_html=closed_trades_html,
            leg_count_aggregate_html=leg_count_aggregate_html,
            leg_index_aggregate_html=leg_index_aggregate_html,
            stop_slippage_html=stop_slippage_html,
        ),
        "system": render_dashboard_system_room(
            diagnostics_html=diagnostics_html,
            warning_list_html=warning_list_html,
            config_html=config_html,
            health_items_html=health_items_html,
            recent_events_html=recent_events_html,
            runtime_db_path_display=runtime_db_path_display,
        ),
    }[active_room]

    return (
        "<!-- render_dashboard_shell -->"
        + " "
        + render_dashboard_shell(
            health_status=health_status,
            latest_update_display=latest_update_display,
            execution_mode_label=execution_mode_label,
            execution_mode_state=execution_mode_state,
            active_room=active_room,
            room_nav_html=room_nav_html,
            room_content_html=room_content_html,
        )
        + f"  <div class=\"refresh-indicator {'error' if health_status != 'OK' else ''}\" id=\"refresh-indicator\">\n"
        + "    <div class=\"refresh-dot\"></div>\n"
        + f"    <span id=\"refresh-indicator-text\">{'Unable to refresh' if health_status != 'OK' else 'Auto refresh: 5s'}</span>\n"
        + "  </div>\n"
    )


def render_dashboard_html(
    snapshot: dict,
    strategy_config: dict | None = None,
    active_room: str | None = None,
    active_tab: str | None = None,
    review_view: str | None = None,
    account_range_key: str = "1D",
) -> str:
    return render_dashboard_document(
        snapshot,
        strategy_config=strategy_config,
        active_room=active_room,
        active_tab=active_tab,
        review_view=review_view,
        account_range_key=account_range_key,
    )
