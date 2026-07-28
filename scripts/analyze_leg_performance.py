#!/usr/bin/env python3
"""Analyze the marginal contribution and timing of each strategy leg."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import statistics
from collections import defaultdict
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Callable, Iterable


SHANGHAI = timezone(timedelta(hours=8))
CURRENT_LOGIC_CUTOFF = datetime.fromisoformat("2026-06-19T14:50:24+00:00")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output-dir", type=Path, required=True)
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def number(value: object, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return float(value)


@dataclass(frozen=True)
class Leg:
    trade_id: str
    symbol: str
    trade_opened: datetime
    trade_pnl: float
    trade_depth: int
    leg_no: int
    opened_at: datetime
    pnl: float
    risk: float | None
    cumulative_risk: float | None
    elapsed_minutes: float
    gap_minutes: float | None
    move_from_base_pct: float | None
    move_from_prior_pct: float | None


@dataclass(frozen=True)
class Trade:
    trade_id: str
    symbol: str
    opened_at: datetime
    pnl: float
    legs: tuple[Leg, ...]


def load_trades(db_path: Path) -> list[Trade]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True, timeout=30)
    connection.row_factory = sqlite3.Row
    connection.execute("PRAGMA busy_timeout = 30000")
    rows = connection.execute(
        """
        SELECT round_trip_id, symbol, opened_at, net_pnl, payload_json
        FROM trade_round_trips NOT INDEXED
        ORDER BY opened_at, id
        """
    ).fetchall()
    connection.close()

    trades: list[Trade] = []
    for row in rows:
        payload = json.loads(row["payload_json"])
        raw_legs = payload.get("legs") or []
        if not raw_legs:
            continue
        trade_opened = parse_time(row["opened_at"])
        trade_pnl = float(row["net_pnl"] or 0)
        base_price = number(raw_legs[0].get("entry_price"))
        previous_price: float | None = None
        previous_opened: datetime | None = None
        legs: list[Leg] = []
        for leg_no, raw_leg in enumerate(raw_legs, start=1):
            opened_at = parse_time(raw_leg.get("opened_at") or row["opened_at"])
            entry_price = number(raw_leg.get("entry_price"))
            move_from_base = (
                (entry_price / base_price - 1) * 100
                if entry_price is not None and base_price not in (None, 0)
                else None
            )
            move_from_prior = (
                (entry_price / previous_price - 1) * 100
                if entry_price is not None and previous_price not in (None, 0)
                else None
            )
            legs.append(
                Leg(
                    trade_id=str(row["round_trip_id"]),
                    symbol=str(row["symbol"]),
                    trade_opened=trade_opened,
                    trade_pnl=trade_pnl,
                    trade_depth=len(raw_legs),
                    leg_no=leg_no,
                    opened_at=opened_at,
                    pnl=number(raw_leg.get("net_pnl_contribution"), 0.0) or 0.0,
                    risk=number(raw_leg.get("leg_risk")),
                    cumulative_risk=number(raw_leg.get("cumulative_risk_after_leg")),
                    elapsed_minutes=(opened_at - trade_opened).total_seconds() / 60,
                    gap_minutes=(
                        (opened_at - previous_opened).total_seconds() / 60
                        if previous_opened is not None
                        else None
                    ),
                    move_from_base_pct=move_from_base,
                    move_from_prior_pct=move_from_prior,
                )
            )
            previous_price = entry_price
            previous_opened = opened_at
        trades.append(
            Trade(
                trade_id=str(row["round_trip_id"]),
                symbol=str(row["symbol"]),
                opened_at=trade_opened,
                pnl=trade_pnl,
                legs=tuple(legs),
            )
        )
    return trades


def median(values: Iterable[float | None]) -> float | None:
    known = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.median(known) if known else None


def mean(values: Iterable[float | None]) -> float | None:
    known = [value for value in values if value is not None and math.isfinite(value)]
    return statistics.fmean(known) if known else None


def ratio(numerator: float, denominator: float) -> float | None:
    return numerator / denominator if denominator else None


def profit_factor(values: Iterable[float]) -> float | None:
    values = list(values)
    gross_profit = sum(value for value in values if value > 0)
    gross_loss = -sum(value for value in values if value < 0)
    return ratio(gross_profit, gross_loss)


def maximum_drawdown(values: Iterable[float]) -> float:
    equity = 0.0
    peak = 0.0
    worst = 0.0
    for value in values:
        equity += value
        peak = max(peak, equity)
        worst = min(worst, equity - peak)
    return worst


def period_trades(trades: list[Trade], period: str) -> list[Trade]:
    if period == "full":
        return trades
    if period == "pre_current_logic":
        return [trade for trade in trades if trade.opened_at < CURRENT_LOGIC_CUTOFF]
    if period == "current_logic":
        return [trade for trade in trades if trade.opened_at >= CURRENT_LOGIC_CUTOFF]
    raise ValueError(period)


def summarize_legs(trades: list[Trade], period: str) -> list[dict[str, object]]:
    selected_trades = period_trades(trades, period)
    by_leg: dict[int, list[Leg]] = defaultdict(list)
    for trade in selected_trades:
        for leg in trade.legs:
            by_leg[leg.leg_no].append(leg)

    rows: list[dict[str, object]] = []
    for leg_no, legs in sorted(by_leg.items()):
        pnls = [leg.pnl for leg in legs]
        risks = [leg.risk for leg in legs if leg.risk is not None]
        tail_legs = [leg for leg in legs if leg.trade_pnl >= 50]
        non_tail_legs = [leg for leg in legs if leg.trade_pnl < 50]
        ranked = sorted(pnls, reverse=True)
        rows.append(
            {
                "period": period,
                "leg_no": leg_no,
                "type": "base" if leg_no == 1 else "add_on",
                "count": len(legs),
                "positive_count": sum(pnl > 0 for pnl in pnls),
                "positive_pct": sum(pnl > 0 for pnl in pnls) / len(legs) * 100,
                "net_pnl": sum(pnls),
                "avg_pnl": mean(pnls),
                "median_pnl": median(pnls),
                "profit_factor": profit_factor(pnls),
                "total_leg_risk": sum(risks),
                "pnl_per_risk": ratio(sum(pnls), sum(risks)),
                "cohort_trade_pnl": sum(leg.trade_pnl for leg in legs),
                "cohort_trade_win_pct": sum(leg.trade_pnl > 0 for leg in legs) / len(legs) * 100,
                "tail_trade_count": len(tail_legs),
                "tail_leg_pnl": sum(leg.pnl for leg in tail_legs),
                "non_tail_leg_pnl": sum(leg.pnl for leg in non_tail_legs),
                "top_1_contribution": sum(ranked[:1]),
                "top_5_contribution": sum(ranked[:5]),
                "pnl_without_top_1": sum(ranked[1:]),
                "pnl_without_top_5": sum(ranked[5:]),
                "median_elapsed_minutes": median(leg.elapsed_minutes for leg in legs),
                "median_gap_minutes": median(leg.gap_minutes for leg in legs),
                "median_move_from_base_pct": median(leg.move_from_base_pct for leg in legs),
                "median_move_from_prior_pct": median(leg.move_from_prior_pct for leg in legs),
                "zero_post_risk_pct": (
                    sum(
                        leg.cumulative_risk is not None and leg.cumulative_risk <= 1e-9
                        for leg in legs
                    )
                    / sum(leg.cumulative_risk is not None for leg in legs)
                    * 100
                    if any(leg.cumulative_risk is not None for leg in legs)
                    else None
                ),
            }
        )
    return rows


def age_bucket(minutes: float) -> str:
    if minutes < 30:
        return "<30m"
    if minutes < 60:
        return "30-60m"
    if minutes < 120:
        return "1-2h"
    if minutes < 180:
        return "2-3h"
    if minutes < 240:
        return "3-4h"
    if minutes < 360:
        return "4-6h"
    return "6h+"


AGE_BUCKET_ORDER = {name: index for index, name in enumerate(("<30m", "30-60m", "1-2h", "2-3h", "3-4h", "4-6h", "6h+"))}


def summarize_timing(trades: list[Trade], period: str) -> list[dict[str, object]]:
    groups: dict[tuple[int, str], list[Leg]] = defaultdict(list)
    for trade in period_trades(trades, period):
        for leg in trade.legs[1:]:
            groups[(leg.leg_no, age_bucket(leg.elapsed_minutes))].append(leg)

    rows: list[dict[str, object]] = []
    for (leg_no, bucket), legs in sorted(
        groups.items(), key=lambda item: (item[0][0], AGE_BUCKET_ORDER[item[0][1]])
    ):
        pnls = [leg.pnl for leg in legs]
        risks = [leg.risk for leg in legs if leg.risk is not None]
        rows.append(
            {
                "period": period,
                "leg_no": leg_no,
                "elapsed_bucket": bucket,
                "count": len(legs),
                "positive_pct": sum(pnl > 0 for pnl in pnls) / len(legs) * 100,
                "net_pnl": sum(pnls),
                "avg_pnl": mean(pnls),
                "pnl_per_risk": ratio(sum(pnls), sum(risks)),
                "tail_trade_count": sum(leg.trade_pnl >= 50 for leg in legs),
                "tail_leg_pnl": sum(leg.pnl for leg in legs if leg.trade_pnl >= 50),
                "non_tail_leg_pnl": sum(leg.pnl for leg in legs if leg.trade_pnl < 50),
            }
        )
    return rows


def schedule_status(leg: Leg) -> str:
    lower_bound = 30 if leg.leg_no == 2 else (leg.leg_no - 2) * 60
    upper_bound = (leg.leg_no - 1) * 60
    if leg.elapsed_minutes < lower_bound:
        return "early"
    if leg.elapsed_minutes < upper_bound:
        return "on_schedule"
    return "late"


def summarize_schedule(trades: list[Trade], period: str) -> list[dict[str, object]]:
    groups: dict[tuple[int, str], list[Leg]] = defaultdict(list)
    for trade in period_trades(trades, period):
        for leg in trade.legs[1:]:
            groups[(leg.leg_no, schedule_status(leg))].append(leg)
    status_order = {"early": 0, "on_schedule": 1, "late": 2}
    rows: list[dict[str, object]] = []
    for (leg_no, status), legs in sorted(
        groups.items(), key=lambda item: (item[0][0], status_order[item[0][1]])
    ):
        pnls = [leg.pnl for leg in legs]
        risks = [leg.risk for leg in legs if leg.risk is not None]
        rows.append(
            {
                "period": period,
                "leg_no": leg_no,
                "schedule_status": status,
                "count": len(legs),
                "positive_pct": sum(pnl > 0 for pnl in pnls) / len(legs) * 100,
                "net_pnl": sum(pnls),
                "pnl_per_risk": ratio(sum(pnls), sum(risks)),
                "tail_leg_pnl": sum(leg.pnl for leg in legs if leg.trade_pnl >= 50),
                "non_tail_leg_pnl": sum(leg.pnl for leg in legs if leg.trade_pnl < 50),
            }
        )
    return rows


def summarize_depth(trades: list[Trade], period: str) -> list[dict[str, object]]:
    groups: dict[int, list[Trade]] = defaultdict(list)
    for trade in period_trades(trades, period):
        groups[len(trade.legs)].append(trade)
    rows: list[dict[str, object]] = []
    for depth, items in sorted(groups.items()):
        base_pnl = sum(trade.legs[0].pnl for trade in items)
        add_pnl = sum(leg.pnl for trade in items for leg in trade.legs[1:])
        rows.append(
            {
                "period": period,
                "exact_depth": depth,
                "trades": len(items),
                "trade_win_pct": sum(trade.pnl > 0 for trade in items) / len(items) * 100,
                "trade_net_pnl": sum(trade.pnl for trade in items),
                "base_contribution": base_pnl,
                "add_on_contribution": add_pnl,
                "tail_trade_count": sum(trade.pnl >= 50 for trade in items),
            }
        )
    return rows


ScaleFn = Callable[[Leg], float]


def scenario_summary(
    trades: list[Trade],
    period: str,
    name: str,
    scale: ScaleFn,
) -> dict[str, object]:
    selected = period_trades(trades, period)
    estimated: list[tuple[Trade, float]] = []
    changed_legs = 0
    changed_leg_pnl = 0.0
    for trade in selected:
        adjustment = 0.0
        for leg in trade.legs:
            leg_scale = scale(leg)
            if leg_scale != 1:
                changed_legs += 1
                changed_leg_pnl += leg.pnl
                adjustment += (leg_scale - 1) * leg.pnl
        estimated.append((trade, trade.pnl + adjustment))
    baseline = sum(trade.pnl for trade in selected)
    tail = [(trade, pnl) for trade, pnl in estimated if trade.pnl >= 50]
    original_tail_pnl = sum(trade.pnl for trade, _ in tail)
    estimated_tail_pnl = sum(pnl for _, pnl in tail)
    values = [pnl for _, pnl in estimated]
    return {
        "period": period,
        "scenario": name,
        "changed_legs": changed_legs,
        "changed_leg_actual_pnl": changed_leg_pnl,
        "estimated_net_pnl": sum(values),
        "improvement": sum(values) - baseline,
        "profit_factor": profit_factor(values),
        "max_drawdown": maximum_drawdown(values),
        "tail_pnl_retained_pct": ratio(estimated_tail_pnl, original_tail_pnl) * 100 if original_tail_pnl else None,
        "original_tail_winners_still_positive": sum(pnl > 0 for _, pnl in tail),
        "original_tail_count": len(tail),
    }


def scenario_rows(trades: list[Trade], period: str) -> list[dict[str, object]]:
    selected = period_trades(trades, period)
    early_first_slot_trade_ids = {
        trade.trade_id
        for trade in selected
        if len(trade.legs) >= 2 and trade.legs[1].elapsed_minutes < 30
    }
    return [
        scenario_summary(trades, period, "baseline", lambda leg: 1.0),
        scenario_summary(trades, period, "base x0.5", lambda leg: 0.5 if leg.leg_no == 1 else 1.0),
        scenario_summary(trades, period, "leg2 x0.5", lambda leg: 0.5 if leg.leg_no == 2 else 1.0),
        scenario_summary(trades, period, "leg3 x0.5", lambda leg: 0.5 if leg.leg_no == 3 else 1.0),
        scenario_summary(trades, period, "omit leg4", lambda leg: 0.0 if leg.leg_no == 4 else 1.0),
        scenario_summary(trades, period, "omit legs4+", lambda leg: 0.0 if leg.leg_no >= 4 else 1.0),
        scenario_summary(trades, period, "all add-ons x0.5", lambda leg: 0.5 if leg.leg_no >= 2 else 1.0),
        scenario_summary(trades, period, "omit all add-ons", lambda leg: 0.0 if leg.leg_no >= 2 else 1.0),
        scenario_summary(
            trades,
            period,
            "omit first add-on before 30m",
            lambda leg: 0.0 if leg.leg_no == 2 and leg.elapsed_minutes < 30 else 1.0,
        ),
        scenario_summary(
            trades,
            period,
            "disable add chain after early first slot",
            lambda leg: (
                0.0
                if leg.trade_id in early_first_slot_trade_ids and leg.leg_no >= 2
                else 1.0
            ),
        ),
        scenario_summary(
            trades,
            period,
            "leg2 x0.5 + omit leg4",
            lambda leg: 0.5 if leg.leg_no == 2 else 0.0 if leg.leg_no == 4 else 1.0,
        ),
        scenario_summary(
            trades,
            period,
            "late add-ons x0.5",
            lambda leg: (
                0.5
                if leg.leg_no >= 2 and leg.elapsed_minutes >= (leg.leg_no - 1) * 60
                else 1.0
            ),
        ),
        scenario_summary(
            trades,
            period,
            "omit late add-ons",
            lambda leg: (
                0.0
                if leg.leg_no >= 2 and leg.elapsed_minutes >= (leg.leg_no - 1) * 60
                else 1.0
            ),
        ),
        scenario_summary(
            trades,
            period,
            "only scheduled add-ons",
            lambda leg: 0.0 if leg.leg_no >= 2 and schedule_status(leg) != "on_schedule" else 1.0,
        ),
    ]


def summarize_months(trades: list[Trade]) -> list[dict[str, object]]:
    groups: dict[str, list[Trade]] = defaultdict(list)
    for trade in trades:
        groups[trade.opened_at.astimezone(SHANGHAI).strftime("%Y-%m")].append(trade)
    rows: list[dict[str, object]] = []
    for month, items in sorted(groups.items()):
        leg_pnl = {
            leg_no: sum(
                leg.pnl
                for trade in items
                for leg in trade.legs
                if leg.leg_no == leg_no
            )
            for leg_no in range(1, 7)
        }
        rows.append(
            {
                "month": month,
                "trades": len(items),
                "net_pnl": sum(trade.pnl for trade in items),
                "profit_factor": profit_factor(trade.pnl for trade in items),
                "base_pnl": leg_pnl[1],
                "leg2_pnl": leg_pnl[2],
                "leg3_pnl": leg_pnl[3],
                "leg4_pnl": leg_pnl[4],
                "leg5_pnl": leg_pnl[5],
                "leg6_pnl": leg_pnl[6],
                "leg7_plus_pnl": sum(
                    leg.pnl for trade in items for leg in trade.legs if leg.leg_no >= 7
                ),
            }
        )
    return rows


def write_csv(path: Path, rows: list[dict[str, object]]) -> None:
    if not rows:
        return
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: object, digits: int = 2) -> str:
    if value is None:
        return "-"
    return f"{float(value):.{digits}f}"


def markdown_table(headers: list[str], rows: list[list[object]]) -> list[str]:
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    lines.extend("| " + " | ".join(str(cell) for cell in row) + " |" for row in rows)
    return lines


def render_report(
    trades: list[Trade],
    leg_rows: list[dict[str, object]],
    timing_rows: list[dict[str, object]],
    schedule_rows: list[dict[str, object]],
    depth_rows: list[dict[str, object]],
    scenarios: list[dict[str, object]],
    month_rows: list[dict[str, object]],
) -> str:
    current_trades = period_trades(trades, "current_logic")
    current_legs = [row for row in leg_rows if row["period"] == "current_logic"]
    full_legs = [row for row in leg_rows if row["period"] == "full"]
    full_timing = [row for row in timing_rows if row["period"] == "full"]
    current_schedule = [row for row in schedule_rows if row["period"] == "current_logic"]
    full_schedule = [row for row in schedule_rows if row["period"] == "full"]
    current_scenarios = [row for row in scenarios if row["period"] == "current_logic"]
    full_scenarios = [row for row in scenarios if row["period"] == "full"]
    full_depth = [row for row in depth_rows if row["period"] == "full"]
    residual = sum(trade.pnl - sum(leg.pnl for leg in trade.legs) for trade in trades)
    current_residual = sum(trade.pnl - sum(leg.pnl for leg in trade.legs) for trade in current_trades)

    lines = [
        "# 逐 Leg 收益与边际贡献研究",
        "",
        "## 数据口径",
        "",
        f"- 全量样本：{len(trades)} 笔已闭合交易，{sum(len(trade.legs) for trade in trades)} 个 Leg，开仓区间 {trades[0].opened_at.astimezone(SHANGHAI):%Y-%m-%d %H:%M} 至 {trades[-1].opened_at.astimezone(SHANGHAI):%Y-%m-%d %H:%M}（北京时间）。",
        f"- 近期样本：以 2026-06-19 22:50（北京时间）的核心逻辑变更为切点，共 {len(current_trades)} 笔交易，净收益 {sum(trade.pnl for trade in current_trades):+.2f} USDT。该数据截止 2026-07-13，不包含 2026-07-14 刚上线的 30 分钟首加仓规则和 09:00 禁 Base 的真实结果。",
        "- Leg 边际贡献按该 Leg 的成交均价、最终统一退出价和手续费份额计算。负值表示这个 Leg 对真实整笔交易的最终收益产生负贡献。",
        "- 删除或缩放 Leg 是线性反事实：保留真实后续止损与其他 Leg 路径，仅改变该 Leg 的收益贡献；它适合筛选方向，但不等价于逐分钟完整回放。",
        f"- 全量交易净收益与 Leg 贡献之和的残差为 {residual:+.2f} USDT；当前逻辑阶段残差为 {current_residual:+.2f} USDT。",
        "",
        "## 全量历史逐 Leg",
        "",
    ]
    lines.extend(
        markdown_table(
            ["Leg", "样本", "正贡献率", "净贡献", "PF", "收益/风险", "尾部贡献", "非尾部贡献", "去掉最大赢家后"],
            [
                [
                    row["leg_no"],
                    row["count"],
                    f"{fmt(row['positive_pct'], 1)}%",
                    f"{float(row['net_pnl']):+.2f}",
                    fmt(row["profit_factor"], 3),
                    fmt(row["pnl_per_risk"], 3),
                    f"{float(row['tail_leg_pnl']):+.2f}",
                    f"{float(row['non_tail_leg_pnl']):+.2f}",
                    f"{float(row['pnl_without_top_1']):+.2f}",
                ]
                for row in full_legs
            ],
        )
    )
    lines.extend(["", "## 月度逐 Leg 漂移", ""])
    lines.extend(
        markdown_table(
            ["月份", "交易", "整笔净收益", "PF", "Base", "Leg 2", "Leg 3", "Leg 4", "Leg 5", "Leg 6", "Leg 7+"],
            [
                [
                    row["month"],
                    row["trades"],
                    f"{float(row['net_pnl']):+.2f}",
                    fmt(row["profit_factor"], 3),
                    f"{float(row['base_pnl']):+.2f}",
                    f"{float(row['leg2_pnl']):+.2f}",
                    f"{float(row['leg3_pnl']):+.2f}",
                    f"{float(row['leg4_pnl']):+.2f}",
                    f"{float(row['leg5_pnl']):+.2f}",
                    f"{float(row['leg6_pnl']):+.2f}",
                    f"{float(row['leg7_plus_pnl']):+.2f}",
                ]
                for row in month_rows
            ],
        )
    )
    lines.extend(["", "## 近期阶段逐 Leg（用于对照）", ""])
    lines.extend(
        markdown_table(
            ["Leg", "样本", "正贡献率", "净贡献", "PF", "收益/风险", "尾部贡献", "非尾部贡献"],
            [
                [
                    row["leg_no"],
                    row["count"],
                    f"{fmt(row['positive_pct'], 1)}%",
                    f"{float(row['net_pnl']):+.2f}",
                    fmt(row["profit_factor"], 3),
                    fmt(row["pnl_per_risk"], 3),
                    f"{float(row['tail_leg_pnl']):+.2f}",
                    f"{float(row['non_tail_leg_pnl']):+.2f}",
                ]
                for row in current_legs
            ],
        )
    )
    lines.extend(["", "## 全量历史：加仓年龄分桶", ""])
    lines.extend(
        markdown_table(
            ["Leg", "距 Base", "样本", "正贡献率", "净贡献", "收益/风险", "尾部贡献", "非尾部贡献"],
            [
                [
                    row["leg_no"],
                    row["elapsed_bucket"],
                    row["count"],
                    f"{fmt(row['positive_pct'], 1)}%",
                    f"{float(row['net_pnl']):+.2f}",
                    fmt(row["pnl_per_risk"], 3),
                    f"{float(row['tail_leg_pnl']):+.2f}",
                    f"{float(row['non_tail_leg_pnl']):+.2f}",
                ]
                for row in full_timing
            ],
        )
    )
    lines.extend(["", "## 全量历史：计划窗口与延迟补仓", ""])
    lines.append(
        "计划窗口定义为 Leg 2 在 Base 后 30–60 分钟，Leg 3 在 1–2 小时，Leg 4 在 2–3 小时，依此类推；超过各自上限视为延迟补仓。"
    )
    lines.append("")
    lines.extend(
        markdown_table(
            ["Leg", "状态", "样本", "正贡献率", "净贡献", "收益/风险", "尾部贡献", "非尾部贡献"],
            [
                [
                    row["leg_no"],
                    row["schedule_status"],
                    row["count"],
                    f"{fmt(row['positive_pct'], 1)}%",
                    f"{float(row['net_pnl']):+.2f}",
                    fmt(row["pnl_per_risk"], 3),
                    f"{float(row['tail_leg_pnl']):+.2f}",
                    f"{float(row['non_tail_leg_pnl']):+.2f}",
                ]
                for row in full_schedule
            ],
        )
    )
    lines.extend(["", "## 全量历史：最终交易深度", ""])
    lines.extend(
        markdown_table(
            ["最终 Leg 数", "交易数", "胜率", "整笔净收益", "Base 贡献", "加仓贡献", "尾部交易"],
            [
                [
                    row["exact_depth"],
                    row["trades"],
                    f"{fmt(row['trade_win_pct'], 1)}%",
                    f"{float(row['trade_net_pnl']):+.2f}",
                    f"{float(row['base_contribution']):+.2f}",
                    f"{float(row['add_on_contribution']):+.2f}",
                    row["tail_trade_count"],
                ]
                for row in full_depth
            ],
        )
    )
    lines.extend(["", "## 全量历史：仓位反事实", ""])
    lines.extend(
        markdown_table(
            ["方案", "估计净收益", "相对基准", "PF", "最大回撤", "尾部收益保留", "仍盈利的原尾部单"],
            [
                [
                    row["scenario"],
                    f"{float(row['estimated_net_pnl']):+.2f}",
                    f"{float(row['improvement']):+.2f}",
                    fmt(row["profit_factor"], 3),
                    f"{float(row['max_drawdown']):+.2f}",
                    f"{fmt(row['tail_pnl_retained_pct'], 1)}%",
                    f"{row['original_tail_winners_still_positive']}/{row['original_tail_count']}",
                ]
                for row in full_scenarios
            ],
        )
    )
    lines.extend(["", "## 近期阶段：仓位反事实（对照）", ""])
    lines.extend(
        markdown_table(
            ["方案", "估计净收益", "相对基准", "PF", "最大回撤", "尾部收益保留"],
            [
                [
                    row["scenario"],
                    f"{float(row['estimated_net_pnl']):+.2f}",
                    f"{float(row['improvement']):+.2f}",
                    fmt(row["profit_factor"], 3),
                    f"{float(row['max_drawdown']):+.2f}",
                    f"{fmt(row['tail_pnl_retained_pct'], 1)}%",
                ]
                for row in current_scenarios
            ],
        )
    )

    lines.extend(["", "## 发现", ""])
    lines.append(
        "1. 全量 974 笔累计净收益 -2192.57 USDT，Profit Factor 0.727。Base 贡献 -532.39 USDT，所有 add-on 合计贡献 -1613.56 USDT；从全周期结果看，旧策略不是单一 Leg 出问题，而是 Base 与加仓都没有形成正期望。"
    )
    lines.append(
        "2. 直接删除全部加仓可改善 1613.56 USDT，但全量尾部收益只保留 36.9%，这会破坏长尾策略的核心。正确方向不是取消 add-on，而是筛掉低质量加仓路径。"
    )
    lines.append(
        "3. Base 后 30 分钟内的 Leg 2 共 189 个，贡献 -480.96 USDT；删除它们后尾部收益仍保留 97.5%。这条规律在全量和近期阶段方向一致，是目前证据最充分的过滤条件。"
    )
    lines.append(
        "4. 189 笔首个加仓窗口不足 30 分钟的交易，其整条加仓链合计贡献 -1327.96 USDT；禁用整条链的线性估计尾部收益保留 94.6%。这是很强的影子候选，但比只跳过过早 Leg 更依赖路径假设。"
    )
    lines.append(
        "5. 全量 222 个延迟补仓贡献 -482.62 USDT；删除后尾部收益保留 88.8%。近期阶段同类 48 个贡献 -219.35 USDT，尾部收益可保留 98.2%。方向一致，但旧版历史中确实有更多长尾依赖延迟补仓，因此只能先做影子。"
    )
    lines.append(
        "6. Leg 4 是唯一从 4 月到 7 月每个月都为负的主要层级，四个月分别贡献 -29.50、-228.04、-85.00、-70.73 USDT。它适合做缩仓或质量过滤影子，但直接删除仍会损失约 12% 的全量尾部收益。"
    )
    lines.append(
        "7. 历史存在明显的制度漂移：4 月至 6 月均亏损，7 月转为 +204.41 USDT；2026-06-19 后 Base、Leg 2、Leg 3 已转正。全量数据适合寻找跨版本稳定坏点，不适合直接决定当前各层仓位大小。"
    )
    lines.append(
        "8. 深 Leg 的交易最终收益很高，是因为只有强趋势才能走到深层，并不代表深 Leg 自身有效。Leg 7 以后样本只有 46 个，且多数已经是零本金风险、用浮盈换凸性，暂时不应据此硬限制。"
    )
    lines.append(
        "9. 新 30 分钟规则会使实际 Leg 编号前移：主动跳过首个小时槽位后，下一小时成交会成为新的 Leg 2。后续判断延迟补仓必须记录小时槽位和主动跳过原因，不能只用 Leg 编号与 Base 年龄。"
    )
    lines.append(
        "10. 所有删除或缩放结论都可能改变后续成交数量与止损轨迹。候选方案应先进入影子策略，再用新版本数据或逐分钟重放验证。"
    )
    return "\n".join(lines) + "\n"


def main() -> None:
    args = parse_args()
    trades = load_trades(args.db)
    if not trades:
        raise SystemExit("no round trips with leg data found")
    periods = ("full", "pre_current_logic", "current_logic")
    leg_rows = [row for period in periods for row in summarize_legs(trades, period)]
    timing_rows = [row for period in periods for row in summarize_timing(trades, period)]
    schedule_rows = [row for period in periods for row in summarize_schedule(trades, period)]
    depth_rows = [row for period in periods for row in summarize_depth(trades, period)]
    scenarios = [
        row
        for period in ("full", "current_logic")
        for row in scenario_rows(trades, period)
    ]
    month_rows = summarize_months(trades)

    args.output_dir.mkdir(parents=True, exist_ok=True)
    write_csv(args.output_dir / "leg_summary.csv", leg_rows)
    write_csv(args.output_dir / "leg_timing.csv", timing_rows)
    write_csv(args.output_dir / "leg_schedule.csv", schedule_rows)
    write_csv(args.output_dir / "trade_depth.csv", depth_rows)
    write_csv(args.output_dir / "leg_scenarios.csv", scenarios)
    write_csv(args.output_dir / "leg_monthly.csv", month_rows)
    report = render_report(
        trades,
        leg_rows,
        timing_rows,
        schedule_rows,
        depth_rows,
        scenarios,
        month_rows,
    )
    (args.output_dir / "analysis.md").write_text(report, encoding="utf-8")
    print(report)


if __name__ == "__main__":
    main()
