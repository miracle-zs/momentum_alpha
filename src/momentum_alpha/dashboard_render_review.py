from __future__ import annotations

from html import escape

from .dashboard_render_utils import REVIEW_VIEWS, _build_dashboard_room_href, normalize_review_view


def render_dashboard_performance_tab(
    *,
    performance_summary_html: str,
    round_trip_detail_html: str,
    leg_count_aggregate_html: str,
    leg_index_aggregate_html: str,
    stop_slippage_html: str,
) -> str:
    return (
        '<div class="dashboard-tab-panel" data-dashboard-room-content="review" data-ui-redesign-page="review-overview">'
        "<section class='section-frame review-overview-frame' data-collapsible-section='review'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>复盘室</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>Trade review analysis starts with the summary strip, then drills into trade detail and evidence tables.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review'>Collapse</button>"
        "</div>"
        "<div class='review-command-bar'>"
        "<div class='review-command-pill'>Range · ALL</div>"
        "<div class='review-command-pill'>Closed lifecycle ledger</div>"
        "<div class='review-command-pill review-command-pill-muted'>Export-ready review surface</div>"
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
        "<div class='chart-card review-analysis-main review-ledger-card'>"
        "<div class='review-section-label'>Closed Trade Detail</div>"
        f"<div class='table-scroll'>{round_trip_detail_html}</div>"
        "</div>"
        "</div>"
        "<div class='review-analysis-evidence-grid review-evidence-deck'>"
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
        '<div class="dashboard-tab-panel" data-dashboard-review-view-content="daily" data-ui-redesign-page="daily-review">'
        "<section class='section-frame daily-review-frame daily-review-board' data-collapsible-section='review-daily'>"
        "<div class='section-topbar'>"
        "<div>"
        "<div class='section-header'>每日复盘</div>"
        "<div class='section-subtitle' style='margin-top:4px;color:var(--fg-muted);font-size:0.72rem;'>UTC+8 08:30 to UTC+8 08:30 trading window.</div>"
        "</div>"
        "<button type='button' class='section-toggle' data-section-toggle='review-daily'>Collapse</button>"
        "</div>"
        "<div class='daily-room-command-strip'>"
        "<div class='daily-command-pill'>UTC+8 review window</div>"
        "<div class='daily-command-pill'>Selected report workflow</div>"
        "<div class='daily-command-pill daily-command-pill-ok'>Completed / stored report</div>"
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
