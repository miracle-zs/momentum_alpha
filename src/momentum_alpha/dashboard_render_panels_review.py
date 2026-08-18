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
            "<div class='daily-review-empty-hero'>"
            "<div class='daily-review-eyebrow'>DECISION JOURNAL</div>"
            "<div class='daily-review-title'>每日复盘</div>"
            "</div>"
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

    payload = report.get("payload") or {}
    rows_data = sorted(
        payload.get("rows", []) or [],
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

    filtered_summary = payload.get("filtered_base_summary") or {}
    filtered_rows_data = sorted(
        payload.get("filtered_base_rows", []) or [],
        key=lambda row: (
            row.get("vetoed_at") or "",
            row.get("symbol") or "",
        ),
        reverse=True,
    )
    filtered_candidate_count = int(_parse_numeric(filtered_summary.get("candidate_count")) or len(filtered_rows_data))
    filtered_resolved_count = int(_parse_numeric(filtered_summary.get("resolved_count")) or 0)
    filtered_tail_count = int(_parse_numeric(filtered_summary.get("tail_50u_count")) or 0)
    filtered_observed_pnl = _parse_decimal(filtered_summary.get("observed_net_pnl"))
    filtered_win_count = int(_parse_numeric(filtered_summary.get("win_count")) or 0)
    filtered_loss_count = int(_parse_numeric(filtered_summary.get("loss_count")) or 0)
    filtered_pending_count = int(_parse_numeric(filtered_summary.get("pending_count")) or 0)
    filtered_pnl_class = "positive" if filtered_observed_pnl is not None and filtered_observed_pnl > 0 else "negative" if filtered_observed_pnl is not None and filtered_observed_pnl < 0 else "neutral"
    filtered_status_note = (
        f"{filtered_resolved_count} resolved · {filtered_pending_count} pending"
        if filtered_candidate_count
        else "No Base veto candidates recorded in this window"
    )
    filtered_stat_items = [
        ("VETOED BASES", str(filtered_candidate_count), ""),
        ("RESOLVED", str(filtered_resolved_count), ""),
        ("CLOSED WINS", str(filtered_win_count), "positive"),
        ("CLOSED LOSSES", str(filtered_loss_count), "negative"),
        ("OBSERVED PNL", _format_decimal_metric(filtered_observed_pnl, signed=True), filtered_pnl_class),
        ("≥50U TAILS", str(filtered_tail_count), "tail"),
    ]
    filtered_stats_html = "".join(
        (
            f"<div class='daily-review-counterfactual-stat {escape(tone)}'>"
            f"<span>{escape(label)}</span><strong>{escape(value)}</strong>"
            "</div>"
        )
        for label, value, tone in filtered_stat_items
    )

    filtered_rows = []
    for row in filtered_rows_data:
        status = str(row.get("status") or "pending_replay")
        outcome = str(row.get("outcome") or "pending")
        status_label = {
            "pending_replay": "PENDING",
            "closed": f"CLOSED {outcome.upper()}",
            "open": "OPEN MTM",
            "unresolved": "UNRESOLVED",
            "overlap": "OVERLAP",
        }.get(status, status.upper())
        status_tone = "win" if outcome == "win" else "loss" if outcome == "loss" else "pending" if status == "pending_replay" else "neutral"
        rule = str(row.get("veto_rule") or "-")
        rule_label = {"A": "A · ATR", "B": "B · FLOW", "A_OR_B": "A + B"}.get(rule, rule)
        features = (
            f"ATR {_format_review_pct(row.get('atr_15m_pct'))}"
            f" · TC {_format_review_ratio(row.get('trade_count_ratio_30m'))}"
            f" · R/V {_format_review_ratio(row.get('return_to_vol_15m'))}"
        )
        pnl_source = row.get("net_pnl") if status == "closed" else row.get("mark_to_market_net_pnl")
        pnl_value = _parse_decimal(pnl_source)
        pnl_class = "daily-review-impact-positive" if pnl_value is not None and pnl_value > 0 else "daily-review-impact-negative" if pnl_value is not None and pnl_value < 0 else ""
        pnl_caption = "REALIZED" if status == "closed" else "MTM" if status == "open" else ""
        tail_html = "<span class='daily-review-tail-badge'>≥50U tail</span>" if row.get("is_long_tail_50u") else ""
        warning_text = ", ".join(str(item) for item in (row.get("warnings") or [])) or "no warnings"
        filtered_rows.append(
            "<div class='daily-review-counterfactual-row'>"
            "<div class='daily-review-counterfactual-time'>"
            f"<span>{escape(_format_datetime_review(row.get('vetoed_at')))}</span>"
            f"<small>{escape(str(row.get('exit_at') and _format_datetime_review(row.get('exit_at')) or '—'))}</small>"
            "</div>"
            "<div class='daily-review-counterfactual-symbol'>"
            f"<strong>{escape(str(row.get('symbol') or 'n/a'))}</strong>"
            f"<small>{escape(str(row.get('shadow_opportunity_id') or ''))}</small>"
            "</div>"
            f"<div><span class='daily-review-filter-chip'>{escape(rule_label)}</span><span class='daily-review-feature-pills'>{escape(features)}</span></div>"
            f"<div><span class='daily-review-outcome daily-review-outcome-{status_tone}' title='{escape(warning_text)}'>{escape(status_label)}</span>{tail_html}</div>"
            f"<div class='daily-review-counterfactual-pnl {pnl_class}'><strong>{escape(_format_decimal_metric(pnl_value, signed=True))}</strong><small>{escape(pnl_caption)}</small></div>"
            f"<div class='daily-review-counterfactual-addons'>{escape(str(row.get('add_on_count', 0)))} <small>add-ons</small></div>"
            "</div>"
        )
    filtered_empty_html = (
        "<div class='daily-review-empty'>"
        "<strong>No filtered Base outcomes yet.</strong>"
        "<span>Run the daily report with filtered-Base replay enabled to see what each vetoed candidate did next.</span>"
        "</div>"
    )
    filtered_rows_html = (
        "<div class='daily-review-counterfactual-table'>"
        "<div class='daily-review-counterfactual-header'><span>VETOED / EXITED</span><span>SYMBOL</span><span>VETO EVIDENCE</span><span>WHAT HAPPENED</span><span>PNL</span><span>LEGS</span></div>"
        f"{''.join(filtered_rows) if filtered_rows else filtered_empty_html}"
        "</div>"
    )

    rows = []
    for row in rows_data:
        actual_value = _parse_decimal(row.get("actual_net_pnl"))
        replay_value = _parse_decimal(row.get("counterfactual_net_pnl"))
        row_impact = _daily_review_impact(
            actual=row.get("actual_net_pnl"),
            replay=row.get("counterfactual_net_pnl"),
        )
        warnings_text = ", ".join(str(item) for item in (row.get("warnings") or [])) or "n/a"
        status_label = "WARN" if warnings_text != "n/a" else "OK"
        status_class = "warn" if status_label == "WARN" else "ok"
        impact_class = ""
        if row_impact is not None and row_impact > 0:
            impact_class = "daily-review-impact-positive"
        elif row_impact is not None and row_impact < 0:
            impact_class = "daily-review-impact-negative"
        replayed_add_on_count = int(_parse_numeric(row.get("replayed_add_on_count")) or 0)
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
    empty_rows_html = '<div class="trade-history-empty">No trade rows</div>'
    rows_html = (
        "<div class='analytics-table daily-review-table'>"
        "<div class='analytics-row analytics-row-header daily-review-row-header daily-review-grid'>"
        "<span>CLOSED AT</span><span class='analytics-main'>SYMBOL</span><span>OPENED AT</span><span>ACTUAL</span><span>REPLAY</span><span>FILTER IMPACT</span><span>ADD-ONS</span><span>STATUS</span>"
        "</div>"
        f"{''.join(rows) if rows else empty_rows_html}"
        "</div>"
    )
    return (
        "<section class='chart-card daily-review-panel daily-review-panel-redesign'>"
        "<div class='daily-review-toolbar'>"
        "<div class='daily-review-toolbar-left'>"
        "<div class='daily-review-eyebrow'>DECISION JOURNAL / FILTER LAB</div>"
        "<form class='daily-review-date-form' method='get' action='.'>"
        "<input type='hidden' name='room' value='review'>"
        "<input type='hidden' name='range' value='1D'>"
        "<input type='hidden' name='review_view' value='daily'>"
        "<label class='daily-review-date-label' for='daily-review-date-select'>Jump to date</label>"
        f"<select id='daily-review-date-select' name='report_date' class='daily-review-date-select' onchange='this.form.submit()'>{date_options}</select>"
        "</form>"
        f"<div class='daily-review-nav'>{''.join(navigation_items)}</div>"
        "</div>"
        "<div class='daily-review-toolbar-note'>真实成交是结果；被 Base veto 的候选是实验组。每天复盘一次，持续监控过滤是否误伤长尾。</div>"
        "</div>"
        "<div class='daily-review-hero'>"
        "<div class='daily-review-hero-copy'>"
        "<div class='daily-review-eyebrow'>THE DAY IN ONE LINE</div>"
        "<div class='daily-review-hero-title'>真实仓位之外，<em>被过滤的机会</em>后来发生了什么？</div>"
        f"<div class='daily-review-support'>{escape(impact_support)}</div>"
        "</div>"
        f"<div class='daily-review-hero-impact {impact_state}'>"
        "<span>FILTER IMPACT</span>"
        f"<strong>{escape(impact_headline.replace('Filter ', ''))}</strong>"
        f"<small>{escape(str(report.get('status') or 'ok').upper())} · {escape(str(report.get('report_date') or 'n/a'))}</small>"
        "</div>"
        "</div>"
        "<section class='daily-review-module daily-review-original-block' data-daily-review-module='original'>"
        "<div class='daily-review-module-head'>"
        "<div><div class='daily-review-eyebrow'>ORIGINAL DAILY REVIEW</div><h3>原有日报：真实成交与 add-on 反事实</h3></div>"
        "<div class='daily-review-section-note'>沿用原有历史汇总、Filter Impact、Actual / Replay 口径；不读取被过滤 Base 的回放结果。</div>"
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
        "<section class='daily-review-ledger'>"
        "<div class='daily-review-section-head'><div><div class='daily-review-eyebrow'>EXECUTED LEDGER</div><h3>真实成交与 add-on 反事实</h3></div><div class='daily-review-section-note'>Actual / Replay / Filter Impact</div></div>"
        f"{rows_html}"
        "</section>"
        "</section>"
        "<section class='daily-review-module daily-review-filtered-base-block' data-daily-review-module='filtered-base'>"
        "<div class='daily-review-module-head'>"
        "<div><div class='daily-review-eyebrow'>FILTERED BASE / SHADOW REPLAY</div><h3>新增实验：被过滤的 Base，后来如果开仓会怎样？</h3></div>"
        f"<div class='daily-review-section-note'>{escape(filtered_status_note)} · 这一部分独立统计，不改变上面的原有日报。</div>"
        "</div>"
        "<section class='daily-review-counterfactual-block'>"
        "<div class='daily-review-section-head'>"
        "<div><div class='daily-review-eyebrow'>COUNTERFACTUAL TRACKING</div><h3>过滤候选的后续路径</h3></div>"
        "<div class='daily-review-section-note'>A/B 规则只用开仓当时已完成的 1m 数据</div>"
        "</div>"
        f"<div class='daily-review-counterfactual-stats'>{filtered_stats_html}</div>"
        "<div class='daily-review-filter-explainer'><span class='daily-review-filter-chip'>A · ATR ≥ 3%</span><span class='daily-review-filter-chip'>B · TC ≤ 1 + R/V ≤ 0.5</span><span>绿色代表过滤掉的候选后来为正；红色代表避免了亏损；OPEN MTM 不是已实现收益。</span></div>"
        f"{filtered_rows_html}"
        "</section>"
        "</section>"
        "</section>"
    )


def _format_review_pct(value: object | None) -> str:
    numeric = _parse_numeric(value)
    return "—" if numeric is None else f"{numeric:,.2f}%"


def _format_review_ratio(value: object | None) -> str:
    numeric = _parse_numeric(value)
    return "—" if numeric is None else f"{numeric:,.2f}"
