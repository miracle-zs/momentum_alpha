#!/usr/bin/env python3
"""Visualize PnL after combining trades by Beijing open date and hour."""

from __future__ import annotations

import argparse
import html
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean, median

from visualize_trade_time_distribution import (
    BEIJING,
    CYAN,
    GOLD,
    GREEN,
    GRID,
    MUTED,
    PANEL,
    PANEL_2,
    RED,
    TEXT,
    detail_attrs,
    detail_panel_html,
    detail_payload,
    fmt_money,
    fmt_plain_money,
    interaction_script,
    money_tone,
    pct,
    svg_rect,
    svg_text,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--db",
        type=Path,
        default=Path("var/server_snapshots/runtime_20260708_full.db"),
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("local_analytics/open_hour_bucket_distribution_20260708.html"),
    )
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BEIJING)


def load_buckets(db_path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT symbol, round_trip_id, opened_at,
               CAST(realized_pnl AS REAL) AS gross_pnl,
               CAST(commission AS REAL) AS commission,
               CAST(net_pnl AS REAL) AS net_pnl
        FROM trade_round_trips
        ORDER BY opened_at
        """
    ).fetchall()
    connection.close()

    grouped: dict[tuple[str, int], dict] = {}
    for row in rows:
        opened_bj = parse_time(row["opened_at"])
        key = (opened_bj.date().isoformat(), opened_bj.hour)
        bucket = grouped.setdefault(
            key,
            {
                "date": key[0],
                "hour": key[1],
                "opened_bj": opened_bj.replace(minute=0, second=0, microsecond=0),
                "minute_of_day": key[1] * 60,
                "trade_count": 0,
                "gross_pnl": 0.0,
                "commission": 0.0,
                "net_pnl": 0.0,
                "symbols": [],
                "round_trip_ids": [],
            },
        )
        bucket["trade_count"] += 1
        bucket["gross_pnl"] += float(row["gross_pnl"] or 0.0)
        bucket["commission"] += float(row["commission"] or 0.0)
        bucket["net_pnl"] += float(row["net_pnl"] or 0.0)
        bucket["symbols"].append(row["symbol"])
        bucket["round_trip_ids"].append(row["round_trip_id"])

    return [grouped[key] for key in sorted(grouped)]


def summarize_by_hour(buckets: list[dict]) -> list[dict]:
    result = []
    for hour in range(24):
        rows = [bucket for bucket in buckets if bucket["hour"] == hour]
        positives = [bucket for bucket in rows if bucket["net_pnl"] > 0]
        negatives = [bucket for bucket in rows if bucket["net_pnl"] < 0]
        net = sum(bucket["net_pnl"] for bucket in rows)
        pos = sum(bucket["net_pnl"] for bucket in positives)
        neg = sum(bucket["net_pnl"] for bucket in negatives)
        trade_count = sum(bucket["trade_count"] for bucket in rows)
        values = [bucket["net_pnl"] for bucket in rows]
        result.append(
            {
                "hour": hour,
                "bucket_count": len(rows),
                "count": len(rows),
                "trade_count": trade_count,
                "win_count": len(positives),
                "loss_count": len(negatives),
                "win_rate": len(positives) / len(rows) * 100 if rows else 0.0,
                "gross": sum(bucket["gross_pnl"] for bucket in rows),
                "commission": sum(bucket["commission"] for bucket in rows),
                "net": net,
                "positive_net": pos,
                "negative_net": neg,
                "avg_net": net / len(rows) if rows else 0.0,
                "median_net": median(values) if values else 0.0,
                "best": max(values, default=0.0),
                "worst": min(values, default=0.0),
                "profit_factor": pos / abs(neg) if neg else math.inf if pos else 0.0,
                "avg_trades_per_bucket": trade_count / len(rows) if rows else 0.0,
            }
        )
    return result


def chart_bucket_counts(hourly: list[dict]) -> str:
    width, height = 1120, 380
    left, right, top, bottom = 64, 28, 34, 54
    inner_w = width - left - right
    inner_h = height - top - bottom
    max_count = max(max(row["win_count"], row["loss_count"]) for row in hourly) or 1
    step = inner_w / 24
    bar_w = step * 0.32
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Winning and losing date-hour bucket counts">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
    ]
    for i in range(5):
        value = max_count * i / 4
        y = top + inner_h - inner_h * i / 4
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(svg_text(16, y + 4, f"{value:.0f}", fill=MUTED, font_size=12))
    for row in hourly:
        x0 = left + row["hour"] * step + step * 0.15
        win_h = inner_h * row["win_count"] / max_count
        loss_h = inner_h * row["loss_count"] / max_count
        win_title = (
            f"{row['hour']:02d}:00 winning buckets={row['win_count']} "
            f"losing buckets={row['loss_count']} date-hour buckets={row['bucket_count']} "
            f"trades={row['trade_count']} net={fmt_money(row['net'])}"
        )
        loss_title = (
            f"{row['hour']:02d}:00 losing buckets={row['loss_count']} "
            f"winning buckets={row['win_count']} date-hour buckets={row['bucket_count']} "
            f"trades={row['trade_count']} net={fmt_money(row['net'])}"
        )
        detail = detail_payload(
            f"{row['hour']:02d}:00 date-hour buckets",
            [
                ("Date-hour buckets", str(row["bucket_count"]), None),
                ("Trades", str(row["trade_count"]), None),
                ("Winning buckets", str(row["win_count"]), "pos"),
                ("Losing buckets", str(row["loss_count"]), "neg"),
                ("Bucket win rate", pct(row["win_rate"]), None),
                ("Winner sum", fmt_money(row["positive_net"]), "pos"),
                ("Loser sum", fmt_money(row["negative_net"]), "neg"),
                ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
            ],
        )
        parts.append(svg_rect(x0, top + inner_h - win_h, bar_w, win_h, GREEN, title=win_title, detail=detail, rx=3))
        parts.append(svg_rect(x0 + bar_w + 4, top + inner_h - loss_h, bar_w, loss_h, RED, title=loss_title, detail=detail, rx=3))
        parts.append(
            svg_text(
                left + row["hour"] * step + step / 2,
                height - 24,
                f"{row['hour']:02d}",
                fill=MUTED,
                font_size=12,
                text_anchor="middle",
            )
        )
    parts.append(svg_text(left, 22, "Winning vs losing date-hour buckets by Beijing open hour", fill=TEXT, font_size=16, font_weight=700))
    parts.append(svg_rect(width - 254, 14, 12, 12, GREEN, rx=2))
    parts.append(svg_text(width - 236, 25, "profitable bucket", fill=MUTED, font_size=12))
    parts.append(svg_rect(width - 120, 14, 12, 12, RED, rx=2))
    parts.append(svg_text(width - 102, 25, "losing bucket", fill=MUTED, font_size=12))
    parts.append("</svg>")
    return "\n".join(parts)


def chart_bucket_net(hourly: list[dict]) -> str:
    width, height = 1120, 420
    left, right, top, bottom = 72, 28, 36, 58
    inner_w = width - left - right
    inner_h = height - top - bottom
    max_abs = max(
        max(abs(row["positive_net"]), abs(row["negative_net"]), abs(row["net"]))
        for row in hourly
    ) or 1
    step = inner_w / 24
    baseline = top + inner_h / 2
    scale = inner_h / 2 / max_abs
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Date-hour bucket PnL by Beijing open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
        f'<line x1="{left}" y1="{baseline:.1f}" x2="{width-right}" y2="{baseline:.1f}" stroke="#7f8b9e" stroke-width="1.2"/>',
    ]
    for frac in (-1, -0.5, 0.5, 1):
        y = baseline - frac * max_abs * scale
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(svg_text(12, y + 4, fmt_money(frac * max_abs), fill=MUTED, font_size=11))
    for row in hourly:
        x = left + row["hour"] * step + step * 0.22
        w = step * 0.56
        pos_h = row["positive_net"] * scale
        neg_h = abs(row["negative_net"]) * scale
        if row["positive_net"] > 0:
            title = (
                f"{row['hour']:02d}:00 profitable bucket sum={fmt_money(row['positive_net'])} "
                f"losing bucket sum={fmt_money(row['negative_net'])} net={fmt_money(row['net'])} "
                f"buckets={row['bucket_count']} trades={row['trade_count']}"
            )
            detail = detail_payload(
                f"{row['hour']:02d}:00 bucket PnL",
                [
                    ("Date-hour buckets", str(row["bucket_count"]), None),
                    ("Trades", str(row["trade_count"]), None),
                    ("Profitable bucket sum", fmt_money(row["positive_net"]), "pos"),
                    ("Losing bucket sum", fmt_money(row["negative_net"]), "neg"),
                    ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                    ("Average bucket", fmt_money(row["avg_net"]), money_tone(row["avg_net"])),
                    ("Median bucket", fmt_money(row["median_net"]), money_tone(row["median_net"])),
                    ("Best bucket", fmt_money(row["best"]), money_tone(row["best"])),
                    ("Worst bucket", fmt_money(row["worst"]), money_tone(row["worst"])),
                    ("Trades per bucket", f"{row['avg_trades_per_bucket']:.1f}", None),
                ],
            )
            parts.append(svg_rect(x, baseline - pos_h, w, pos_h, GREEN, title=title, detail=detail, rx=3))
        if row["negative_net"] < 0:
            title = (
                f"{row['hour']:02d}:00 losing bucket sum={fmt_money(row['negative_net'])} "
                f"profitable bucket sum={fmt_money(row['positive_net'])} net={fmt_money(row['net'])} "
                f"buckets={row['bucket_count']} trades={row['trade_count']}"
            )
            detail = detail_payload(
                f"{row['hour']:02d}:00 bucket PnL",
                [
                    ("Date-hour buckets", str(row["bucket_count"]), None),
                    ("Trades", str(row["trade_count"]), None),
                    ("Profitable bucket sum", fmt_money(row["positive_net"]), "pos"),
                    ("Losing bucket sum", fmt_money(row["negative_net"]), "neg"),
                    ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                    ("Average bucket", fmt_money(row["avg_net"]), money_tone(row["avg_net"])),
                    ("Median bucket", fmt_money(row["median_net"]), money_tone(row["median_net"])),
                    ("Best bucket", fmt_money(row["best"]), money_tone(row["best"])),
                    ("Worst bucket", fmt_money(row["worst"]), money_tone(row["worst"])),
                    ("Trades per bucket", f"{row['avg_trades_per_bucket']:.1f}", None),
                ],
            )
            parts.append(svg_rect(x, baseline, w, neg_h, RED, title=title, detail=detail, rx=3))
        net_y = baseline - row["net"] * scale
        detail = detail_payload(
            f"{row['hour']:02d}:00 net marker",
            [
                ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                ("Profitable bucket sum", fmt_money(row["positive_net"]), "pos"),
                ("Losing bucket sum", fmt_money(row["negative_net"]), "neg"),
                ("Date-hour buckets", str(row["bucket_count"]), None),
                ("Trades", str(row["trade_count"]), None),
            ],
        )
        parts.append(
            f'<circle cx="{x + w / 2:.1f}" cy="{net_y:.1f}" r="3.2" '
            f'fill="{GOLD}"{detail_attrs(detail)}><title>{html.escape(detail["title"])}</title></circle>'
        )
        parts.append(
            svg_text(
                left + row["hour"] * step + step / 2,
                height - 24,
                f"{row['hour']:02d}",
                fill=MUTED,
                font_size=12,
                text_anchor="middle",
            )
        )
    parts.append(svg_text(left, 24, "Positive and negative bucket PnL by Beijing open hour", fill=TEXT, font_size=16, font_weight=700))
    parts.append(svg_rect(width - 330, 14, 12, 12, GREEN, rx=2))
    parts.append(svg_text(width - 312, 25, "profitable buckets", fill=MUTED, font_size=12))
    parts.append(svg_rect(width - 190, 14, 12, 12, RED, rx=2))
    parts.append(svg_text(width - 172, 25, "losing buckets", fill=MUTED, font_size=12))
    parts.append(f'<circle cx="{width - 58}" cy="20" r="3.2" fill="{GOLD}"/>')
    parts.append(svg_text(width - 48, 25, "net", fill=MUTED, font_size=12))
    parts.append("</svg>")
    return "\n".join(parts)


def chart_bucket_scatter(buckets: list[dict]) -> str:
    width, height = 1120, 460
    left, right, top, bottom = 78, 26, 34, 58
    inner_w = width - left - right
    inner_h = height - top - bottom
    dates = sorted({bucket["date"] for bucket in buckets})
    date_index = {date: idx for idx, date in enumerate(dates)}
    max_abs = max(abs(bucket["net_pnl"]) for bucket in buckets) or 1
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Date-hour buckets by date and open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
    ]
    for hour in range(0, 25, 3):
        y = top + inner_h * hour / 24
        parts.append(
            f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(svg_text(18, y + 4, f"{hour:02d}:00", fill=MUTED, font_size=11))
    seen_months = set()
    for date in dates:
        month = date[:7]
        if month in seen_months:
            continue
        seen_months.add(month)
        x = left + (date_index[date] / max(len(dates) - 1, 1)) * inner_w
        parts.append(
            f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+inner_h}" stroke="{GRID}" stroke-width="1"/>'
        )
        parts.append(svg_text(x + 4, height - 22, month, fill=MUTED, font_size=11))
    for bucket in buckets:
        x = left + (date_index[bucket["date"]] / max(len(dates) - 1, 1)) * inner_w
        y = top + (bucket["minute_of_day"] / 1440) * inner_h
        radius = 3.0 + min(math.sqrt(abs(bucket["net_pnl"]) / max_abs) * 9, 9)
        color = GREEN if bucket["net_pnl"] > 0 else RED if bucket["net_pnl"] < 0 else MUTED
        opacity = 0.86 if abs(bucket["net_pnl"]) >= 20 else 0.48
        title = html.escape(
            f"{bucket['date']} {bucket['hour']:02d}:00 "
            f"{bucket['trade_count']} trades {fmt_money(bucket['net_pnl'])} "
            f"{', '.join(bucket['symbols'][:6])}"
        )
        detail = detail_payload(
            f"{bucket['date']} {bucket['hour']:02d}:00",
            [
                ("Date", bucket["date"], None),
                ("Open hour", f"{bucket['hour']:02d}:00", None),
                ("Trades", str(bucket["trade_count"]), None),
                ("Gross PnL", fmt_money(bucket["gross_pnl"]), money_tone(bucket["gross_pnl"])),
                ("Commission", fmt_plain_money(bucket["commission"]), "neg"),
                ("Net PnL", fmt_money(bucket["net_pnl"]), money_tone(bucket["net_pnl"])),
                ("Symbols", ", ".join(bucket["symbols"][:12]), None),
            ],
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            f'opacity="{opacity}"{detail_attrs(detail)}><title>{title}</title></circle>'
        )
    parts.append(svg_text(left, 24, "Each date-hour bucket by date and Beijing open hour", fill=TEXT, font_size=16, font_weight=700))
    parts.append("</svg>")
    return "\n".join(parts)


def heat_color(value: float, max_abs: float) -> str:
    if value == 0 or max_abs <= 0:
        return "#151d2a"
    alpha = 0.14 + 0.86 * min(abs(value) / max_abs, 1)
    if value > 0:
        return f"rgba(33, 199, 132, {alpha:.3f})"
    return f"rgba(255, 77, 109, {alpha:.3f})"


def chart_bucket_heatmap(buckets: list[dict]) -> str:
    dates = sorted({bucket["date"] for bucket in buckets})
    by_key = {(bucket["date"], bucket["hour"]): bucket for bucket in buckets}
    max_abs = max(abs(bucket["net_pnl"]) for bucket in buckets) or 1
    cell_w, cell_h = 34, 11
    left, right, top, bottom = 92, 26, 42, 36
    width = left + 24 * cell_w + right
    height = top + len(dates) * cell_h + bottom
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Net PnL heatmap by date and Beijing open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
        svg_text(left, 25, "Net PnL heatmap by date x Beijing open hour", fill=TEXT, font_size=16, font_weight=700),
    ]
    for hour in range(24):
        x = left + hour * cell_w + cell_w / 2
        parts.append(svg_text(x, top - 9, f"{hour:02d}", fill=MUTED, font_size=10, text_anchor="middle"))
    for row_idx, date in enumerate(dates):
        y = top + row_idx * cell_h
        if date.endswith("-01") or row_idx == 0 or row_idx == len(dates) - 1:
            parts.append(svg_text(12, y + 8.5, date, fill=MUTED, font_size=10))
        for hour in range(24):
            bucket = by_key.get((date, hour))
            value = bucket["net_pnl"] if bucket else 0.0
            trade_count = bucket["trade_count"] if bucket else 0
            symbols = ", ".join(bucket["symbols"][:6]) if bucket else ""
            title = html.escape(f"{date} {hour:02d}:00 trades={trade_count} net={fmt_money(value)} {symbols}")
            detail = detail_payload(
                f"{date} {hour:02d}:00",
                [
                    ("Date", date, None),
                    ("Open hour", f"{hour:02d}:00", None),
                    ("Trades", str(trade_count), None),
                    ("Gross PnL", fmt_money(bucket["gross_pnl"] if bucket else 0.0), money_tone(bucket["gross_pnl"] if bucket else 0.0)),
                    ("Commission", fmt_plain_money(bucket["commission"] if bucket else 0.0), "neg" if bucket else None),
                    ("Net PnL", fmt_money(value), money_tone(value)),
                    ("Symbols", symbols, None),
                ],
            )
            x = left + hour * cell_w
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w-1:.1f}" '
                f'height="{cell_h-1:.1f}" fill="{heat_color(value, max_abs)}"{detail_attrs(detail)}>'
                f'<title>{title}</title></rect>'
            )
    parts.append(svg_rect(width - 214, 14, 12, 12, GREEN, rx=2))
    parts.append(svg_text(width - 196, 25, "net positive", fill=MUTED, font_size=12))
    parts.append(svg_rect(width - 104, 14, 12, 12, RED, rx=2))
    parts.append(svg_text(width - 86, 25, "net negative", fill=MUTED, font_size=12))
    parts.append("</svg>")
    return "\n".join(parts)


def render_table(hourly: list[dict]) -> str:
    rows = []
    for row in sorted(hourly, key=lambda item: item["net"]):
        pf = "inf" if math.isinf(row["profit_factor"]) else f"{row['profit_factor']:.2f}"
        rows.append(
            "<tr>"
            f"<td>{row['hour']:02d}:00</td>"
            f"<td>{row['bucket_count']}</td>"
            f"<td>{row['trade_count']}</td>"
            f"<td>{row['win_count']}</td>"
            f"<td>{row['loss_count']}</td>"
            f"<td>{pct(row['win_rate'])}</td>"
            f"<td class=\"money {'pos' if row['positive_net'] >= 0 else 'neg'}\">{fmt_money(row['positive_net'])}</td>"
            f"<td class=\"money neg\">{fmt_money(row['negative_net'])}</td>"
            f"<td class=\"money {'pos' if row['net'] >= 0 else 'neg'}\">{fmt_money(row['net'])}</td>"
            f"<td class=\"money {'pos' if row['avg_net'] >= 0 else 'neg'}\">{fmt_money(row['avg_net'])}</td>"
            f"<td class=\"money {'pos' if row['median_net'] >= 0 else 'neg'}\">{fmt_money(row['median_net'])}</td>"
            f"<td>{pf}</td>"
            f"<td>{row['avg_trades_per_bucket']:.1f}</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html(db_path: Path, buckets: list[dict], hourly: list[dict]) -> str:
    winners = [bucket for bucket in buckets if bucket["net_pnl"] > 0]
    losers = [bucket for bucket in buckets if bucket["net_pnl"] < 0]
    total_net = sum(bucket["net_pnl"] for bucket in buckets)
    total_gross = sum(bucket["gross_pnl"] for bucket in buckets)
    total_fee = sum(bucket["commission"] for bucket in buckets)
    total_trades = sum(bucket["trade_count"] for bucket in buckets)
    worst_hour = min(hourly, key=lambda row: row["net"])
    best_hour = max(hourly, key=lambda row: row["net"])
    generated_at = datetime.now(BEIJING)
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Open Hour Bucket Distribution</title>
<style>
:root {{
  color-scheme: dark;
  --bg: #070a10;
  --panel: {PANEL};
  --panel2: {PANEL_2};
  --text: {TEXT};
  --muted: {MUTED};
  --green: {GREEN};
  --red: {RED};
  --gold: {GOLD};
  --cyan: {CYAN};
}}
* {{ box-sizing: border-box; }}
body {{
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
}}
main {{
  max-width: 1180px;
  margin: 0 auto;
  padding: 28px 24px 48px;
}}
h1 {{ margin: 0 0 4px; font-size: 28px; letter-spacing: 0; }}
.subtle, .note {{ color: var(--muted); }}
.cards {{
  display: grid;
  grid-template-columns: repeat(4, minmax(0, 1fr));
  gap: 12px;
  margin: 22px 0 18px;
}}
.metric {{
  background: var(--panel2);
  border: 1px solid #1d2838;
  border-radius: 8px;
  padding: 14px 16px;
}}
.label {{
  color: var(--muted);
  font-size: 12px;
  text-transform: uppercase;
  letter-spacing: .08em;
}}
.value {{ margin-top: 6px; font-size: 22px; font-weight: 700; }}
.pos {{ color: var(--green); }}
.neg {{ color: var(--red); }}
.chart {{ margin-top: 18px; }}
svg {{
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #1d2838;
  border-radius: 8px;
}}
table {{
  width: 100%;
  border-collapse: collapse;
  margin-top: 18px;
  background: var(--panel);
  border: 1px solid #1d2838;
  border-radius: 8px;
  overflow: hidden;
}}
th, td {{
  padding: 9px 10px;
  border-bottom: 1px solid #1d2838;
  text-align: right;
  white-space: nowrap;
}}
th {{ color: var(--muted); font-size: 12px; font-weight: 600; }}
th:first-child, td:first-child {{ text-align: left; }}
tr:last-child td {{ border-bottom: 0; }}
.money {{ font-variant-numeric: tabular-nums; }}
.table-wrap {{ overflow-x: auto; }}
.detail-popover {{
  position: fixed;
  z-index: 20;
  width: min(420px, calc(100vw - 24px));
  max-height: min(560px, calc(100vh - 24px));
  overflow: auto;
  background: #111824;
  border: 1px solid #3a4b66;
  border-radius: 8px;
  box-shadow: 0 18px 60px rgba(0, 0, 0, .48);
  padding: 14px 16px 16px;
}}
.detail-popover[hidden] {{
  display: none;
}}
.detail-popover-head {{
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 12px;
}}
.detail-close {{
  appearance: none;
  border: 1px solid #2a3a51;
  border-radius: 999px;
  width: 28px;
  height: 28px;
  background: #0b1019;
  color: var(--text);
  cursor: pointer;
  font-size: 18px;
  line-height: 1;
}}
.detail-close:hover,
.detail-close:focus {{
  border-color: var(--gold);
}}
.detail-title {{
  margin-top: 5px;
  font-size: 18px;
  font-weight: 700;
}}
.detail-grid {{
  display: grid;
  grid-template-columns: minmax(110px, 180px) minmax(0, 1fr);
  gap: 7px 16px;
  margin-top: 12px;
}}
.detail-label {{
  color: var(--muted);
}}
.detail-value {{
  font-variant-numeric: tabular-nums;
  overflow-wrap: anywhere;
}}
.viz-clickable {{
  cursor: pointer;
  outline: none;
}}
.viz-clickable:hover,
.viz-clickable:focus {{
  filter: brightness(1.22);
  stroke: #f4f7fb;
  stroke-width: 1.4;
}}
.viz-clickable.is-selected {{
  stroke: var(--gold);
  stroke-width: 2;
}}
@media (max-width: 760px) {{
  main {{ padding: 20px 12px 36px; }}
  .cards {{ grid-template-columns: repeat(2, minmax(0, 1fr)); }}
  .detail-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <h1>Open Hour Bucket Distribution</h1>
  <div class="subtle">Source: {html.escape(str(db_path))} · generated at {generated_at:%Y-%m-%d %H:%M:%S} Beijing time · trades are first combined by open date + open hour</div>

  <section class="cards">
    <div class="metric"><div class="label">Date-Hour Buckets</div><div class="value">{len(buckets)}</div></div>
    <div class="metric"><div class="label">Trades</div><div class="value">{total_trades}</div></div>
    <div class="metric"><div class="label">Winning / Losing Buckets</div><div class="value"><span class="pos">{len(winners)}</span> / <span class="neg">{len(losers)}</span></div></div>
    <div class="metric"><div class="label">Net PnL</div><div class="value {'pos' if total_net >= 0 else 'neg'}">{fmt_money(total_net)}</div></div>
  </section>

  <div class="note">Gross {fmt_money(total_gross)} · commission {fmt_plain_money(total_fee)} · worst hour <span class="neg">{worst_hour['hour']:02d}:00</span> · best hour <span class="pos">{best_hour['hour']:02d}:00</span></div>
  <div class="note">Example: if five trades opened on the same day between 09:00 and 09:59, this report combines them into one 09:00 bucket before calculating the hourly distribution.</div>
{detail_panel_html()}

  <section class="chart">{chart_bucket_counts(hourly)}</section>
  <section class="chart">{chart_bucket_net(hourly)}</section>
  <section class="chart">{chart_bucket_scatter(buckets)}</section>
  <section class="chart">{chart_bucket_heatmap(buckets)}</section>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Hour</th><th>Buckets</th><th>Trades</th><th>Win Buckets</th><th>Loss Buckets</th><th>Win Rate</th>
          <th>Winner Sum</th><th>Loser Sum</th><th>Net</th><th>Avg Bucket</th><th>Median Bucket</th><th>PF</th><th>Trades/Bucket</th>
        </tr>
      </thead>
      <tbody>{render_table(hourly)}</tbody>
    </table>
  </div>
{interaction_script()}
</main>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    buckets = load_buckets(args.db)
    if not buckets:
        raise SystemExit("no buckets found")
    hourly = summarize_by_hour(buckets)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(args.db, buckets, hourly), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
