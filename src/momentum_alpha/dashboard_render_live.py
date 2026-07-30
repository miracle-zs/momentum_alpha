from __future__ import annotations

from html import escape


def _render_live_support_card(*, title: str, summary: str, content_html: str) -> str:
    support_key = title.lower().replace(" ", "-")
    return (
        f"<details class='live-support-card' data-live-support-card='{escape(support_key)}'>"
        "<summary class='live-support-summary'>"
        f"<span class='live-support-title'>{escape(title)}</span>"
        f"<span class='live-support-status'>{escape(summary)}</span>"
        "</summary>"
        f"<div class='live-support-body'>{content_html}</div>"
        "</details>"
    )


def render_dashboard_live_room(
    *,
    account_risk_html: str,
    core_lines_html: str,
    active_signal_html: str,
    active_signal_summary: str,
    leader_rotation_html: str,
    leader_rotation_summary: str,
    positions_html: str,
    positions_summary: str,
    execution_flow_html: str,
    execution_flow_summary: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="live">'
        "<section class='section-frame live-control-frame'>"
        f"<div class='live-risk-band'>{account_risk_html}</div>"
        f"<div class='live-core-lines-band'>{core_lines_html}</div>"
        "<div class='live-support-grid'>"
        + _render_live_support_card(
            title="ACTIVE SIGNAL",
            summary=active_signal_summary,
            content_html=active_signal_html,
        )
        + _render_live_support_card(
            title="LEADER ROTATION",
            summary=leader_rotation_summary,
            content_html=leader_rotation_html,
        )
        + _render_live_support_card(
            title="ACTIVE POSITIONS",
            summary=positions_summary,
            content_html=positions_html,
        )
        + _render_live_support_card(
            title="ORDER FLOW",
            summary=execution_flow_summary,
            content_html=execution_flow_html,
        )
        + "</div>"
        "</section>"
        "</div>"
    )


def render_dashboard_overview_tab(
    *,
    account_risk_html: str,
    core_lines_html: str,
    active_signal_html: str,
    active_signal_summary: str,
    leader_rotation_html: str,
    leader_rotation_summary: str,
    positions_html: str,
    positions_summary: str,
    execution_flow_html: str,
    execution_flow_summary: str,
) -> str:
    return render_dashboard_live_room(
        account_risk_html=account_risk_html,
        core_lines_html=core_lines_html,
        active_signal_html=active_signal_html,
        active_signal_summary=active_signal_summary,
        leader_rotation_html=leader_rotation_html,
        leader_rotation_summary=leader_rotation_summary,
        positions_html=positions_html,
        positions_summary=positions_summary,
        execution_flow_html=execution_flow_html,
        execution_flow_summary=execution_flow_summary,
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
