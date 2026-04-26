from __future__ import annotations

from html import escape


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
