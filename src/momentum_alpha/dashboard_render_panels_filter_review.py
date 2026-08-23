from __future__ import annotations

from decimal import Decimal
from html import escape

from .dashboard_render_utils import (
    _build_dashboard_room_href,
    _format_datetime_review,
    _format_decimal_metric,
    _parse_decimal,
    _parse_numeric,
)


def render_filtered_base_review_panel(report: dict | None) -> str:
    if report is None:
        return (
            "<section class='chart-card filter-review-panel'>"
            "<div class='filter-review-empty'>"
            "<strong>暂无过滤复盘</strong>"
            "<span>生成独立样本回放后，这里会显示被规则拦截的开仓结果。</span>"
            "</div>"
            "</section>"
        )

    payload = report.get("payload") or {}
    summary = payload.get("summary") or payload.get("filtered_base_summary") or {}
    rows_data = sorted(
        payload.get("rows") or payload.get("filtered_base_rows") or [],
        key=lambda row: (row.get("vetoed_at") or "", row.get("symbol") or ""),
        reverse=True,
    )
    closed_rows = [row for row in rows_data if str(row.get("status") or "") == "closed"]
    open_rows = [row for row in rows_data if str(row.get("status") or "") == "open"]
    legacy_unreplayed_rows = [
        row
        for row in rows_data
        if str(row.get("status") or "") not in {"closed", "open", "pending_replay", "unresolved"}
    ]

    positive_values = [
        value
        for row in closed_rows
        if (value := _parse_decimal(row.get("net_pnl"))) is not None and value > 0
    ]
    negative_values = [
        value
        for row in closed_rows
        if (value := _parse_decimal(row.get("net_pnl"))) is not None and value < 0
    ]
    candidate_count = int(_parse_numeric(summary.get("candidate_count")) or len(rows_data))
    closed_count = int(_parse_numeric(summary.get("closed_count")) or len(closed_rows))
    open_count = int(_parse_numeric(summary.get("open_count")) or len(open_rows))
    pending_count = int(_parse_numeric(summary.get("pending_count")) or 0) + len(legacy_unreplayed_rows)
    missed_profit = _parse_decimal(summary.get("missed_profit_sum"))
    if missed_profit is None:
        missed_profit = sum(positive_values, Decimal("0"))
    avoided_loss = _parse_decimal(summary.get("avoided_loss_sum"))
    if avoided_loss is None:
        avoided_loss = abs(sum(negative_values, Decimal("0")))
    sample_net_pnl = _parse_decimal(summary.get("closed_sample_pnl_sum"))
    if sample_net_pnl is None:
        sample_net_pnl = missed_profit - avoided_loss
    win_count = int(_parse_numeric(summary.get("win_count")) or len(positive_values))
    loss_count = int(_parse_numeric(summary.get("loss_count")) or len(negative_values))

    if candidate_count == 0:
        verdict_state = "neutral"
        verdict_label = "本周期没有被过滤的开仓样本"
        verdict_value = "0 samples"
    elif closed_count == 0:
        verdict_state = "pending"
        verdict_label = f"{candidate_count} 个样本等待独立回放"
        verdict_value = f"{open_count} open · {pending_count} pending"
    elif sample_net_pnl < 0:
        verdict_state = "helped"
        verdict_label = f"过滤规则净避免 {_format_decimal_metric(abs(sample_net_pnl))} U"
        verdict_value = "独立样本结果偏负"
    elif sample_net_pnl > 0:
        verdict_state = "missed"
        verdict_label = f"过滤规则净错过 {_format_decimal_metric(sample_net_pnl)} U"
        verdict_value = "独立样本结果偏正"
    else:
        verdict_state = "neutral"
        verdict_label = "过滤样本净结果持平"
        verdict_value = "0.00 U"

    stat_items = [
        ("被过滤样本", str(candidate_count), "", "原策略本来会开 Base"),
        ("已完成", str(closed_count), "", f"{open_count} 进行中 · {pending_count} 待回放"),
        ("避免亏损", _format_decimal_metric(avoided_loss), "helped", f"{loss_count} 个亏损样本"),
        ("错过盈利", _format_decimal_metric(missed_profit), "missed", f"{win_count} 个盈利样本"),
        ("样本净结果", _format_decimal_metric(sample_net_pnl, signed=True), _sample_tone(sample_net_pnl), "不代表组合收益"),
    ]
    stats_html = "".join(
        (
            f"<div class='filter-review-stat {escape(tone)}'>"
            f"<span>{escape(label)}</span>"
            f"<strong>{escape(value)}</strong>"
            f"<small>{escape(note)}</small>"
            "</div>"
        )
        for label, value, tone, note in stat_items
    )

    rule_counts: dict[str, int] = {}
    for row in rows_data:
        for token in _veto_rule_tokens(row.get("veto_rule")):
            rule_counts[token] = rule_counts.get(token, 0) + 1
    rule_mix_html = "".join(
        (
            f"<span class='filter-review-rule daily-review-rule-{escape(_veto_rule_slug(token))}'>"
            f"<b>{escape(_veto_rule_label(token))}</b><strong>{count}</strong>"
            "</span>"
        )
        for token, count in sorted(rule_counts.items(), key=lambda item: (-item[1], item[0]))
    )
    if not rule_mix_html:
        rule_mix_html = "<span class='filter-review-rule-empty'>暂无规则命中</span>"

    rows_html = "".join(_render_sample_row(row) for row in rows_data)
    table_html = (
        "<div class='filter-review-table'>"
        "<div class='filter-review-table-head'>"
        "<span>过滤 / 结束</span><span>样本</span><span>触发规则</span><span>结果</span><span>样本收益</span><span>加仓</span>"
        "</div>"
        f"{rows_html}"
        "</div>"
        if rows_html
        else (
            "<div class='filter-review-empty filter-review-empty-inline'>"
            "<strong>本周期没有样本</strong>"
            "<span>仅收录关闭过滤规则后，原策略本来会真实开 Base 的信号。</span>"
            "</div>"
        )
    )

    date_toolbar = _render_date_toolbar(report)
    return (
        "<section class='chart-card filter-review-panel'>"
        f"{date_toolbar}"
        f"<div class='filter-review-verdict {escape(verdict_state)}'>"
        "<div>"
        "<span class='filter-review-kicker'>本日结论</span>"
        f"<h2>{escape(verdict_label)}</h2>"
        "</div>"
        f"<strong>{escape(verdict_value)}</strong>"
        "</div>"
        f"<div class='filter-review-stats'>{stats_html}</div>"
        "<div class='filter-review-evidence-head'>"
        "<div><span class='filter-review-kicker'>样本证据</span><h3>逐笔查看规则拦截后的结果</h3></div>"
        f"<div class='filter-review-rule-mix'><span>规则命中</span>{rule_mix_html}</div>"
        "</div>"
        f"{table_html}"
        "<details class='filter-review-method'>"
        "<summary>计算口径与规则</summary>"
        "<div class='filter-review-method-body'>"
        "<p>只收录原策略已满足开仓条件、但被 Base veto 拦截的信号。每个样本独立回放原策略的加仓与退出；样本之间不互斥，汇总值不代表可执行组合收益。</p>"
        "<div class='filter-review-method-rules'>"
        "<span>A · ATR ≥ 3%</span><span>B · TC ≤ 1 + R/V ≤ 0.5</span><span>C · TC ≤ 0.75</span>"
        "<span>D · TB ≤ 50% + EFF ≤ 0.15</span><span>E · EFF ≤ 0.45 + RX ≥ 1.50×</span>"
        "<span>BO · Breakout ≥ 0.50% + PB ≤ 1.25%</span>"
        "</div>"
        "</div>"
        "</details>"
        "</section>"
    )


def _render_date_toolbar(report: dict) -> str:
    selected_date = str(report.get("selected_report_date") or report.get("report_date") or "n/a")
    dates = [str(item) for item in (report.get("available_report_dates") or []) if item]
    selected_index = dates.index(selected_date) if selected_date in dates else -1
    previous_date = dates[selected_index - 1] if selected_index > 0 else None
    next_date = dates[selected_index + 1] if selected_index >= 0 and selected_index < len(dates) - 1 else None
    latest_date = dates[-1] if dates else selected_date
    options = "".join(
        f"<option value='{escape(date)}'{' selected' if date == selected_date else ''}>{escape(date)}</option>"
        for date in dates
    )
    links = [
        _date_link("上一日", previous_date),
        f"<span class='daily-review-nav-current'>{escape(selected_date)}</span>",
        _date_link("下一日", next_date),
        (
            "<a class='daily-review-nav-link daily-review-nav-link-latest' "
            f"href='{escape(_build_dashboard_room_href(room='review', account_range_key='1D', review_view='filtered'))}'>"
            f"最新 {escape(latest_date)}</a>"
        ),
    ]
    return (
        "<div class='filter-review-toolbar'>"
        "<div>"
        "<span class='filter-review-kicker'>独立样本复盘</span>"
        "<form class='daily-review-date-form' method='get' action='.'>"
        "<input type='hidden' name='room' value='review'>"
        "<input type='hidden' name='range' value='1D'>"
        "<input type='hidden' name='review_view' value='filtered'>"
        "<label class='daily-review-date-label' for='filtered-review-date-select'>日期</label>"
        f"<select id='filtered-review-date-select' name='report_date' class='daily-review-date-select' onchange='this.form.submit()'>{options}</select>"
        "</form>"
        "</div>"
        f"<div class='daily-review-nav'>{''.join(links)}</div>"
        "</div>"
    )


def _date_link(label: str, report_date: str | None) -> str:
    if report_date is None:
        return f"<span class='daily-review-nav-link daily-review-nav-link-disabled'>{escape(label)}</span>"
    href = _build_dashboard_room_href(
        room="review",
        account_range_key="1D",
        review_view="filtered",
        extra_query={"report_date": report_date},
    )
    return f"<a class='daily-review-nav-link' href='{escape(href)}'>{escape(label)}</a>"


def _render_sample_row(row: dict) -> str:
    raw_status = str(row.get("status") or "pending_replay")
    status = raw_status if raw_status in {"closed", "open", "pending_replay", "unresolved"} else "pending_replay"
    outcome = str(row.get("outcome") or "pending")
    label = {
        "pending_replay": "待回放",
        "closed": "已结束 · 盈利" if outcome == "win" else "已结束 · 亏损" if outcome == "loss" else "已结束 · 持平",
        "open": "进行中",
        "unresolved": "数据不足",
    }.get(status, "待回放")
    tone = "win" if status == "closed" and outcome == "win" else "loss" if status == "closed" and outcome == "loss" else "pending" if status == "pending_replay" else "neutral"
    rule_chips = "".join(
        f"<span class='daily-review-filter-chip daily-review-rule-chip daily-review-rule-{escape(_veto_rule_slug(token))}'>{escape(_veto_rule_label(token))}</span>"
        for token in _veto_rule_tokens(row.get("veto_rule"))
    ) or "<span class='daily-review-rule-empty'>—</span>"
    features = (
        f"ATR {_format_pct(row.get('atr_15m_pct'))} · "
        f"TC {_format_ratio(row.get('trade_count_ratio_30m'))} · "
        f"R/V {_format_ratio(row.get('return_to_vol_15m'))}"
    )
    pnl_source = row.get("net_pnl") if status == "closed" else row.get("mark_to_market_net_pnl")
    pnl = _parse_decimal(pnl_source)
    pnl_tone = "daily-review-impact-positive" if pnl is not None and pnl > 0 else "daily-review-impact-negative" if pnl is not None and pnl < 0 else ""
    sample_id = str(row.get("sample_id") or row.get("shadow_opportunity_id") or "")
    warnings = (
        ", ".join(str(item) for item in (row.get("warnings") or []))
        if status != "pending_replay"
        else ""
    ) or "no warnings"
    return (
        "<div class='filter-review-table-row'>"
        "<div class='daily-review-counterfactual-time'>"
        f"<span>{escape(_format_datetime_review(row.get('vetoed_at')))}</span>"
        f"<small>{escape(str(row.get('exit_at') and _format_datetime_review(row.get('exit_at')) or '—'))}</small>"
        "</div>"
        "<div class='daily-review-counterfactual-symbol'>"
        f"<strong>{escape(str(row.get('symbol') or 'n/a'))}</strong><small>{escape(sample_id)}</small>"
        "</div>"
        f"<div class='filter-review-rules'><div>{rule_chips}</div><small>{escape(features)}</small></div>"
        f"<div><span class='daily-review-outcome daily-review-outcome-{tone}' title='{escape(warnings)}'>{escape(label)}</span>"
        f"{'<span class=\"daily-review-tail-badge\">≥50U 长尾</span>' if row.get('is_long_tail_50u') else ''}</div>"
        f"<div class='daily-review-counterfactual-pnl {pnl_tone}'><strong>{escape(_format_decimal_metric(pnl, signed=True))}</strong><small>{'已实现' if status == 'closed' else 'MTM' if status == 'open' else ''}</small></div>"
        f"<div class='daily-review-counterfactual-addons'>{escape(str(row.get('add_on_count', 0)))} <small>次</small></div>"
        "</div>"
    )


def _sample_tone(value: Decimal) -> str:
    if value < 0:
        return "helped"
    if value > 0:
        return "missed"
    return "neutral"


def _format_pct(value: object | None) -> str:
    numeric = _parse_numeric(value)
    return "—" if numeric is None else f"{numeric:,.2f}%"


def _format_ratio(value: object | None) -> str:
    numeric = _parse_numeric(value)
    return "—" if numeric is None else f"{numeric:,.2f}"


_VETO_RULE_LABELS = {
    "A": "A · ATR",
    "B": "B · FLOW",
    "C": "C · LOW TC",
    "D": "D · SELL IMBALANCE",
    "E": "E · RANGE / PATH",
    "BREAKOUT": "BO · BREAKOUT",
}


def _veto_rule_tokens(value: object | None) -> tuple[str, ...]:
    normalized = str(value or "").strip()
    if not normalized or normalized == "-":
        return ()
    if normalized == "A_OR_B":
        return ("A", "B")
    return tuple(token.strip().upper() for token in normalized.replace(" OR ", "+").split("+") if token.strip())


def _veto_rule_label(token: str) -> str:
    return _VETO_RULE_LABELS.get(token, token)


def _veto_rule_slug(token: str) -> str:
    return {
        "A": "a",
        "B": "b",
        "C": "c",
        "D": "d",
        "E": "e",
        "BREAKOUT": "breakout",
    }.get(token, "other")
