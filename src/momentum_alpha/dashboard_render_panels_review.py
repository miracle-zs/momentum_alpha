from __future__ import annotations

from decimal import Decimal
from html import escape

from .dashboard_render_utils import (
    _build_dashboard_room_href,
    _daily_review_impact,
    _daily_review_win_rate,
    _format_datetime_review,
    _format_decimal_metric,
    _parse_decimal,
    _parse_numeric,
)


def render_daily_review_panel(report: dict | None) -> str:
    if report is None:
        return (
            "<section class='chart-card daily-review-panel'>"
            "<div style='font-size:0.7rem;color:var(--fg-muted);margin-bottom:8px;'>每日复盘</div>"
            "<div class='trade-history-empty'>No daily review report</div>"
            "</section>"
        )

    selected_report_date = str(report.get("selected_report_date") or report.get("report_date") or "n/a")
    available_report_dates = [str(item) for item in (report.get("available_report_dates") or []) if item]
    selected_index = available_report_dates.index(selected_report_date) if selected_report_date in available_report_dates else -1
    previous_report_date = available_report_dates[selected_index - 1] if selected_index > 0 else None
    next_report_date = available_report_dates[selected_index + 1] if selected_index >= 0 and selected_index < len(available_report_dates) - 1 else None
    latest_report_date = available_report_dates[-1] if available_report_dates else selected_report_date
    history_summary = report.get("history_summary") or {}
    history_total_actual = _parse_decimal(history_summary.get("actual_total_pnl"))
    history_total_replay = _parse_decimal(history_summary.get("counterfactual_total_pnl"))
    history_filter_impact = _daily_review_impact(
        actual=history_summary.get("actual_total_pnl"),
        replay=history_summary.get("counterfactual_total_pnl"),
    )
    history_summary_items = [
        ("Total Reports", str(history_summary.get("report_count", "n/a"))),
        ("Total Trades", str(history_summary.get("trade_count", "n/a"))),
        ("Cumulative Actual PnL", _format_decimal_metric(history_total_actual, signed=True)),
        ("Cumulative Replay PnL", _format_decimal_metric(history_total_replay, signed=True)),
        ("Cumulative Filter Impact", _format_decimal_metric(history_filter_impact, signed=True)),
        ("Historical Replayed Add-Ons", str(history_summary.get("replayed_add_on_count", "n/a"))),
    ]
    history_summary_html = "".join(
        (
            "<div class='daily-review-kpi daily-review-history-kpi'>"
            f"<div class='decision-label'>{escape(label)}</div>"
            f"<div class='decision-value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in history_summary_items
    )
    date_options = "".join(
        (
            "<option "
            f"value='{escape(date)}'"
            f"{' selected' if date == selected_report_date else ''}>"
            f"{escape(date)}"
            "</option>"
        )
        for date in available_report_dates
    )
    navigation_items = []
    if previous_report_date is None:
        navigation_items.append("<span class='daily-review-nav-link daily-review-nav-link-disabled'>Prev</span>")
    else:
        navigation_items.append(
            (
                "<a class='daily-review-nav-link' "
                f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily', extra_query={'report_date': previous_report_date}))}'>"
                "Prev"
                "</a>"
            )
        )
    navigation_items.append(
        f"<span class='daily-review-nav-current'>{escape(selected_report_date)}</span>"
    )
    if next_report_date is None:
        navigation_items.append("<span class='daily-review-nav-link daily-review-nav-link-disabled'>Next</span>")
    else:
        navigation_items.append(
            (
                "<a class='daily-review-nav-link' "
                f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily', extra_query={'report_date': next_report_date}))}'>"
                "Next"
                "</a>"
            )
        )
    navigation_items.append(
        (
            "<a class='daily-review-nav-link daily-review-nav-link-latest' "
            f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='daily'))}'>"
            f"Latest {escape(latest_report_date)}"
            "</a>"
        )
    )

    rows = []
    rows_data = sorted(
        report.get("payload", {}).get("rows", []) or [],
        key=lambda row: (
            row.get("closed_at") or "",
            row.get("round_trip_id") or "",
            row.get("symbol") or "",
        ),
        reverse=True,
    )
    actual_total = _parse_decimal(report.get("actual_total_pnl"))
    replay_total = _parse_decimal(report.get("counterfactual_total_pnl"))
    total_impact = _daily_review_impact(
        actual=report.get("actual_total_pnl"),
        replay=report.get("counterfactual_total_pnl"),
    )
    total_impact_abs = abs(total_impact) if total_impact is not None else None
    if total_impact is None:
        impact_state = ""
        impact_headline = "Filter impact unavailable"
        impact_support = "Daily report is missing actual or replay PnL."
    elif total_impact > 0:
        impact_state = "positive"
        impact_headline = f"Filter helped by {_format_decimal_metric(total_impact_abs)}"
        impact_support = "Actual strategy outperformed the unconditional hourly add-on replay."
    elif total_impact < 0:
        impact_state = "negative"
        impact_headline = f"Filter dragged by {_format_decimal_metric(total_impact_abs)}"
        impact_support = "The unconditional hourly add-on replay outperformed the actual strategy."
    else:
        impact_state = "neutral"
        impact_headline = "Filter impact flat"
        impact_support = "Actual and replay PnL matched for this report."

    actual_values: list[Decimal] = []
    replay_values: list[Decimal] = []
    row_impacts: list[Decimal] = []
    affected_trade_count = 0
    for row in rows_data:
        actual_value = _parse_decimal(row.get("actual_net_pnl"))
        replay_value = _parse_decimal(row.get("counterfactual_net_pnl"))
        if actual_value is not None:
            actual_values.append(actual_value)
        if replay_value is not None:
            replay_values.append(replay_value)
        row_impact = _daily_review_impact(
            actual=row.get("actual_net_pnl"),
            replay=row.get("counterfactual_net_pnl"),
        )
        if row_impact is not None:
            row_impacts.append(row_impact)
        replayed_add_on_count = int(_parse_numeric(row.get("replayed_add_on_count")) or 0)
        if replayed_add_on_count > 0 or (row_impact is not None and row_impact != 0):
            affected_trade_count += 1
        warnings_text = ", ".join(str(item) for item in (row.get("warnings") or [])) or "n/a"
        status_label = "WARN" if warnings_text != "n/a" else "OK"
        status_class = "warn" if status_label == "WARN" else "ok"
        impact_class = ""
        if row_impact is not None and row_impact > 0:
            impact_class = "daily-review-impact-positive"
        elif row_impact is not None and row_impact < 0:
            impact_class = "daily-review-impact-negative"
        rows.append(
            "<div class='analytics-row daily-review-row daily-review-grid'>"
            f"<span title='{escape(str(row.get('closed_at', 'n/a')))}'>{escape(_format_datetime_review(row.get('closed_at')))}</span>"
            f"<span class='analytics-main'><b>{escape(str(row.get('symbol', 'n/a')))}</b></span>"
            f"<span title='{escape(str(row.get('opened_at', 'n/a')))}'>{escape(_format_datetime_review(row.get('opened_at')))}</span>"
            f"<span>{escape(_format_decimal_metric(actual_value, signed=True))}</span>"
            f"<span>{escape(_format_decimal_metric(replay_value, signed=True))}</span>"
            f"<span class='{impact_class}'>{escape(_format_decimal_metric(row_impact, signed=True))}</span>"
            f"<span>{escape(str(replayed_add_on_count))}</span>"
            f"<span><span class='daily-review-status daily-review-status-{status_class}' title='{escape(warnings_text)}'>{status_label}</span></span>"
            "</div>"
        )
    actual_win_rate = _daily_review_win_rate(actual_values)
    replay_win_rate = _daily_review_win_rate(replay_values)
    trade_count = _parse_decimal(report.get("trade_count")) or Decimal(len(rows_data) or 0)
    avg_impact = total_impact / trade_count if total_impact is not None and trade_count else None
    positive_impacts = [impact for impact in row_impacts if impact > 0]
    negative_impacts = [impact for impact in row_impacts if impact < 0]
    best_filter_save = max(positive_impacts) if positive_impacts else Decimal("0")
    worst_filter_drag = min(negative_impacts) if negative_impacts else Decimal("0")
    kpi_items = [
        ("Report Date", str(report.get("report_date", "n/a"))),
        ("Actual PnL", _format_decimal_metric(actual_total, signed=True)),
        ("Trades", str(report.get("trade_count", "n/a"))),
        ("Actual Win Rate", _format_decimal_metric(actual_win_rate, suffix="%")),
        ("Affected Trades", str(affected_trade_count)),
        ("Best Filter Save", _format_decimal_metric(best_filter_save, signed=True)),
        ("Filter Impact", _format_decimal_metric(total_impact, signed=True)),
        ("Replay PnL", _format_decimal_metric(replay_total, signed=True)),
        ("Replayed Add-Ons", str(report.get("replayed_add_on_count", "n/a"))),
        ("Replay Win Rate", _format_decimal_metric(replay_win_rate, suffix="%")),
        ("Avg Impact / Trade", _format_decimal_metric(avg_impact, signed=True)),
        ("Worst Filter Drag", _format_decimal_metric(worst_filter_drag, signed=True)),
    ]
    kpi_html = "".join(
        (
            "<div class='daily-review-kpi'>"
            f"<div class='decision-label'>{escape(label)}</div>"
            f"<div class='decision-value'>{escape(value)}</div>"
            "</div>"
        )
        for label, value in kpi_items
    )
    rows_html = (
        "<div class='analytics-table daily-review-table'>"
        "<div class='analytics-row analytics-row-header daily-review-row-header daily-review-grid'>"
        "<span>CLOSED AT</span><span class='analytics-main'>SYMBOL</span><span>OPENED AT</span><span>ACTUAL</span><span>REPLAY</span><span>FILTER IMPACT</span><span>ADD-ONS</span><span>STATUS</span>"
        "</div>"
        f"{''.join(rows) if rows else '<div class=\"trade-history-empty\">No trade rows</div>'}"
        "</div>"
    )
    return (
        "<section class='chart-card daily-review-panel'>"
        "<div class='daily-review-toolbar'>"
        "<div class='daily-review-toolbar-left'>"
        "<div class='daily-review-eyebrow'>HISTORY</div>"
        "<form class='daily-review-date-form' method='get' action='?room=review&range=1D&review_view=daily'>"
        "<label class='daily-review-date-label' for='daily-review-date-select'>Jump to date</label>"
        f"<select id='daily-review-date-select' name='report_date' class='daily-review-date-select' onchange='this.form.submit()'>{date_options}</select>"
        "</form>"
        f"<div class='daily-review-nav'>{''.join(navigation_items)}</div>"
        "</div>"
        "<div class='daily-review-toolbar-note'>Historical Filter Impact is aggregated across every stored daily review.</div>"
        "</div>"
        "<div class='daily-review-history-summary'>"
        "<div class='daily-review-history-summary-head'>"
        "<div class='daily-review-eyebrow'>HISTORICAL SUMMARY</div>"
        "<div class='daily-review-history-title'>Cumulative Filter Impact</div>"
        "</div>"
        f"<div class='daily-review-kpi-grid daily-review-history-grid'>{history_summary_html}</div>"
        "</div>"
        f"<div class='daily-review-headline {impact_state}'>"
        "<div>"
        "<div class='daily-review-eyebrow'>每日复盘</div>"
        f"<div class='daily-review-title'>{escape(impact_headline)}</div>"
        f"<div class='daily-review-support'>{escape(impact_support)}</div>"
        "</div>"
        "</div>"
        f"<div class='daily-review-kpi-grid'>{kpi_html}</div>"
        f"{rows_html}"
        "</section>"
    )
