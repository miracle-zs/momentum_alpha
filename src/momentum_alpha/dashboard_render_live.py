from __future__ import annotations


def render_dashboard_live_room(
    *,
    account_risk_html: str,
    core_lines_html: str,
    hero_html: str,
    positions_html: str,
    execution_flow_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        "<section class='section-frame live-control-frame'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>实时监控室</div>"
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
        "</div>"
    )

def render_dashboard_overview_tab(
    *,
    account_risk_html: str,
    core_lines_html: str,
    hero_html: str,
    positions_html: str,
    execution_flow_html: str,
) -> str:
    return render_dashboard_live_room(
        account_risk_html=account_risk_html,
        core_lines_html=core_lines_html,
        hero_html=hero_html,
        positions_html=positions_html,
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
