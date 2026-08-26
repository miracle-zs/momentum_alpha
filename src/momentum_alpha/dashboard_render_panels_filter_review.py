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
            "<span>生成连续策略回放后，这里会显示关闭过滤器时原策略的开仓与收益结果。</span>"
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
        if str(row.get("status") or "") not in {"closed", "open", "pending_replay", "unresolved", "suppressed"}
    ]

    strategy_values = [
        value
        for row in closed_rows
        if (
            value := _parse_decimal(
                row.get("strategy_pnl_delta")
                if row.get("strategy_pnl_delta") is not None
                else row.get("net_pnl")
            )
        )
        is not None
    ]
    positive_values = [value for value in strategy_values if value > 0]
    negative_values = [value for value in strategy_values if value < 0]
    candidate_count = int(_parse_numeric(summary.get("candidate_count")) or 0)
    accepted_count = int(
        _parse_numeric(summary.get("accepted_count"))
        or sum(
            1
            for row in rows_data
            if str(row.get("status") or "") in {"closed", "open", "unresolved"}
        )
    )
    closed_count = int(_parse_numeric(summary.get("closed_count")) or len(closed_rows))
    open_count = int(_parse_numeric(summary.get("open_count")) or len(open_rows))
    pending_count = int(_parse_numeric(summary.get("pending_count")) or 0) + len(legacy_unreplayed_rows)
    missed_profit = _parse_decimal(summary.get("missed_profit_sum"))
    if missed_profit is None:
        missed_profit = sum(positive_values, Decimal("0"))
    avoided_loss = _parse_decimal(summary.get("avoided_loss_sum"))
    if avoided_loss is None:
        avoided_loss = abs(sum(negative_values, Decimal("0")))
    strategy_pnl_delta = _parse_decimal(summary.get("strategy_pnl_delta"))
    if strategy_pnl_delta is None:
        strategy_pnl_delta = _parse_decimal(summary.get("closed_sample_pnl_sum"))
    if strategy_pnl_delta is None:
        strategy_pnl_delta = missed_profit - avoided_loss
    counterfactual_pnl = _parse_decimal(summary.get("counterfactual_trade_pnl_sum"))
    if counterfactual_pnl is None:
        counterfactual_pnl = _parse_decimal(summary.get("closed_sample_pnl_sum")) or strategy_pnl_delta
    actual_replaced_pnl = _parse_decimal(summary.get("actual_replaced_pnl_sum")) or Decimal("0")
    win_count = int(_parse_numeric(summary.get("win_count")) or len(positive_values))
    loss_count = int(_parse_numeric(summary.get("loss_count")) or len(negative_values))

    if candidate_count == 0:
        verdict_state = "neutral"
        verdict_label = "本周期没有被过滤的开仓样本"
        verdict_value = "0 samples"
    elif closed_count == 0:
        verdict_state = "pending"
        verdict_label = f"{accepted_count} 个原策略 Base 等待回放"
        verdict_value = f"{open_count} open · {pending_count} pending"
    elif strategy_pnl_delta < 0:
        verdict_state = "helped"
        verdict_label = f"关闭过滤器后：策略收益变化 {_format_decimal_metric(strategy_pnl_delta, signed=True)} U"
        verdict_value = f"过滤规则相对避免 {_format_decimal_metric(abs(strategy_pnl_delta))} U"
    elif strategy_pnl_delta > 0:
        verdict_state = "missed"
        verdict_label = f"关闭过滤器后：策略收益变化 {_format_decimal_metric(strategy_pnl_delta, signed=True)} U"
        verdict_value = f"过滤规则相对错过 {_format_decimal_metric(strategy_pnl_delta)} U"
    else:
        verdict_state = "neutral"
        verdict_label = "关闭过滤器后：策略收益变化 0.00 U"
        verdict_value = "过滤规则相对无变化"

    stat_items = [
        ("被过滤候选", str(candidate_count), "", "原策略本来会开 Base"),
        ("已完成", str(closed_count), "", f"{open_count} 进行中 · {pending_count} 待回放"),
        ("避免亏损", _format_decimal_metric(avoided_loss), "helped", f"{loss_count} 个负贡献候选"),
        ("错过盈利", _format_decimal_metric(missed_profit), "missed", f"{win_count} 个正贡献候选"),
        (
            "策略净差异",
            _format_decimal_metric(strategy_pnl_delta, signed=True),
            _sample_tone(strategy_pnl_delta),
            f"无过滤 {_format_decimal_metric(counterfactual_pnl, signed=True)} · 被替代实盘 {_format_decimal_metric(actual_replaced_pnl, signed=True)}",
        ),
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
        "<span>过滤 / 结束</span><span>样本</span><span>触发规则</span><span>结果</span><span>策略差异 / 当前 MTM</span><span>加仓</span>"
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
        "<p>只展示原策略状态已经通过、仅被 Base veto 拦截的候选。连续回放遵守同一 UTC 日同一品种只允许一次 Base；因已有持仓、同日重复等原策略状态未通过的记录不计入本页。若过滤后同品种稍后真实开仓，无过滤路径会替代该实盘交易，因此策略差异按“无过滤回放收益 − 被替代实盘收益”计算；已接受的 Base 仍按生产策略执行小时止损上移和 add-on。</p>"
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
        "<span class='filter-review-kicker'>连续策略回放</span>"
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
    status = raw_status if raw_status in {"closed", "open", "pending_replay", "unresolved", "suppressed"} else "pending_replay"
    counterfactual_pnl = _parse_decimal(
        row.get("net_pnl") if status == "closed" else row.get("mark_to_market_net_pnl")
    )
    strategy_pnl_delta = (
        _parse_decimal(row.get("strategy_pnl_delta"))
        if status == "closed"
        else None
    )
    if status == "closed" and strategy_pnl_delta is None:
        strategy_pnl_delta = counterfactual_pnl
    strategy_outcome = str(row.get("strategy_outcome") or "")
    if strategy_outcome not in {"improved", "worsened", "flat", "pending"}:
        strategy_outcome = (
            "improved"
            if strategy_pnl_delta is not None and strategy_pnl_delta > 0
            else "worsened"
            if strategy_pnl_delta is not None and strategy_pnl_delta < 0
            else "flat"
            if strategy_pnl_delta is not None
            else "pending"
        )
    suppression_reason = " ".join(str(item) for item in (row.get("warnings") or []))
    label = {
        "pending_replay": "待回放",
        "closed": (
            "关闭过滤 · 改善"
            if strategy_outcome == "improved"
            else "关闭过滤 · 恶化"
            if strategy_outcome == "worsened"
            else "关闭过滤 · 持平"
        ),
        "open": "进行中 · 未结算",
        "unresolved": "数据不足",
        "suppressed": "未开 · " + ("同日重复" if "daily_repeat" in suppression_reason else "持仓重叠"),
    }.get(status, "待回放")
    tone = "win" if status == "closed" and strategy_outcome == "improved" else "loss" if status == "closed" and strategy_outcome == "worsened" else "pending" if status == "pending_replay" else "neutral"
    rule_chips = "".join(
        f"<span class='daily-review-filter-chip daily-review-rule-chip daily-review-rule-{escape(_veto_rule_slug(token))}'>{escape(_veto_rule_label(token))}</span>"
        for token in _veto_rule_tokens(row.get("veto_rule"))
    ) or "<span class='daily-review-rule-empty'>—</span>"
    features = (
        f"ATR {_format_pct(row.get('atr_15m_pct'))} · "
        f"TC {_format_ratio(row.get('trade_count_ratio_30m'))} · "
        f"R/V {_format_ratio(row.get('return_to_vol_15m'))}"
    )
    pnl = (
        strategy_pnl_delta
        if status == "closed"
        else counterfactual_pnl
        if status == "open"
        else None
    )
    pnl_tone = (
        "daily-review-impact-positive"
        if status == "closed" and pnl is not None and pnl > 0
        else "daily-review-impact-negative"
        if status == "closed" and pnl is not None and pnl < 0
        else ""
    )
    actual_trade_pnl = _parse_decimal(row.get("actual_trade_net_pnl"))
    actual_baseline_pnl = actual_trade_pnl if row.get("actual_trade_id") else Decimal("0")
    pnl_detail = (
        f"无过滤 {_format_decimal_metric(counterfactual_pnl, signed=True)} · 实盘 {_format_decimal_metric(actual_baseline_pnl, signed=True)}"
        if status == "closed"
        else "当前 MTM · 未结算"
        if status == "open"
        else ""
    )
    sample_id = str(row.get("sample_id") or row.get("shadow_opportunity_id") or "")
    warnings = (
        ", ".join(str(item) for item in (row.get("warnings") or []))
        if status != "pending_replay"
        else ""
    ) or "no warnings"
    actual_trade_id = str(row.get("actual_trade_id") or "")
    if actual_trade_id:
        warnings = f"{warnings}; replaces {actual_trade_id}"
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
        f"<div class='daily-review-counterfactual-pnl {pnl_tone}'><strong>{escape(_format_decimal_metric(pnl, signed=True))}</strong><small>{escape(pnl_detail)}</small></div>"
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
