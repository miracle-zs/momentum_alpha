#!/usr/bin/env python3
"""Build local SVG/HTML visualizations for trade time distributions."""

from __future__ import annotations

import argparse
import html
import json
import math
import sqlite3
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import median


BEIJING = timezone(timedelta(hours=8))
GREEN = "#21c784"
RED = "#ff4d6d"
GOLD = "#f6c85f"
CYAN = "#4cc9f0"
TEXT = "#e8edf3"
MUTED = "#96a0b2"
GRID = "#223043"
PANEL = "#0c111a"
PANEL_2 = "#111824"


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
        default=Path("local_analytics/trade_time_distribution_20260708.html"),
    )
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00")).astimezone(BEIJING)


def fmt_money(value: float) -> str:
    return f"{value:+,.2f}"


def fmt_plain_money(value: float) -> str:
    return f"{value:,.2f}"


def pct(value: float) -> str:
    return f"{value:.1f}%"


def svg_attrs(attrs: dict[str, str | float]) -> str:
    return " ".join(
        f'{key.replace("_", "-")}="{html.escape(str(value), quote=True)}"'
        for key, value in attrs.items()
    )


def detail_attrs(detail: dict | None) -> str:
    if not detail:
        return ""
    payload = html.escape(json.dumps(detail, ensure_ascii=False), quote=True)
    return (
        ' class="viz-clickable" tabindex="0" role="button" '
        f'data-detail="{payload}"'
    )


def detail_payload(title: str, rows: list[tuple[str, str, str | None]]) -> dict:
    return {
        "title": title,
        "rows": [
            {"label": label, "value": value, "tone": tone}
            for label, value, tone in rows
        ],
    }


def money_tone(value: float) -> str:
    if value > 0:
        return "pos"
    if value < 0:
        return "neg"
    return ""


def load_trades(db_path: Path) -> list[dict]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    rows = connection.execute(
        """
        SELECT symbol, round_trip_id, opened_at, closed_at,
               CAST(realized_pnl AS REAL) AS gross_pnl,
               CAST(commission AS REAL) AS commission,
               CAST(net_pnl AS REAL) AS net_pnl,
               duration_seconds, exit_reason
        FROM trade_round_trips
        ORDER BY opened_at
        """
    ).fetchall()
    connection.close()

    trades = []
    for row in rows:
        opened_bj = parse_time(row["opened_at"])
        closed_bj = parse_time(row["closed_at"])
        trades.append(
            {
                "symbol": row["symbol"],
                "round_trip_id": row["round_trip_id"],
                "opened_at": row["opened_at"],
                "closed_at": row["closed_at"],
                "opened_bj": opened_bj,
                "closed_bj": closed_bj,
                "date": opened_bj.date().isoformat(),
                "hour": opened_bj.hour,
                "minute_of_day": opened_bj.hour * 60 + opened_bj.minute,
                "gross_pnl": float(row["gross_pnl"] or 0.0),
                "commission": float(row["commission"] or 0.0),
                "net_pnl": float(row["net_pnl"] or 0.0),
                "duration_seconds": int(row["duration_seconds"] or 0),
                "exit_reason": row["exit_reason"] or "",
            }
        )
    return trades


def summarize_by_hour(trades: list[dict]) -> list[dict]:
    result = []
    for hour in range(24):
        rows = [trade for trade in trades if trade["hour"] == hour]
        wins = [trade for trade in rows if trade["net_pnl"] > 0]
        losses = [trade for trade in rows if trade["net_pnl"] < 0]
        net = sum(trade["net_pnl"] for trade in rows)
        pos = sum(trade["net_pnl"] for trade in wins)
        neg = sum(trade["net_pnl"] for trade in losses)
        result.append(
            {
                "hour": hour,
                "count": len(rows),
                "win_count": len(wins),
                "loss_count": len(losses),
                "win_rate": len(wins) / len(rows) * 100 if rows else 0.0,
                "gross": sum(trade["gross_pnl"] for trade in rows),
                "commission": sum(trade["commission"] for trade in rows),
                "net": net,
                "positive_net": pos,
                "negative_net": neg,
                "avg_net": net / len(rows) if rows else 0.0,
                "median_net": median([trade["net_pnl"] for trade in rows])
                if rows
                else 0.0,
                "best": max((trade["net_pnl"] for trade in rows), default=0.0),
                "worst": min((trade["net_pnl"] for trade in rows), default=0.0),
                "profit_factor": pos / abs(neg) if neg else math.inf if pos else 0.0,
                "avg_hold_hours": (
                    sum(trade["duration_seconds"] for trade in rows) / len(rows) / 3600
                    if rows
                    else 0.0
                ),
            }
        )
    return result


def svg_text(x: float, y: float, content: str, **attrs: str | float) -> str:
    attr = svg_attrs(attrs)
    return f'<text x="{x:.1f}" y="{y:.1f}" {attr}>{html.escape(content)}</text>'


def svg_rect(
    x: float,
    y: float,
    w: float,
    h: float,
    fill: str,
    *,
    title: str | None = None,
    detail: dict | None = None,
    **attrs: str | float,
) -> str:
    attr = svg_attrs(attrs)
    interactive = detail_attrs(detail)
    base = (
        f'<rect x="{x:.1f}" y="{y:.1f}" width="{w:.1f}" height="{h:.1f}" '
        f'fill="{fill}" {attr}{interactive}'
    )
    if title is None:
        return f"{base}/>"
    return f"{base}><title>{html.escape(title)}</title></rect>"


def detail_panel_html() -> str:
    return """
  <div id="detail-popover" class="detail-popover" aria-live="polite" hidden>
    <div class="detail-popover-head">
      <div>
        <div class="label">Selection Details</div>
        <div id="detail-title" class="detail-title">No selection</div>
      </div>
      <button id="detail-close" class="detail-close" type="button" aria-label="Close details">×</button>
    </div>
    <div id="detail-grid" class="detail-grid"></div>
  </div>
"""


def interaction_script() -> str:
    return """
  <script>
  (() => {
    const popover = document.getElementById("detail-popover");
    const title = document.getElementById("detail-title");
    const grid = document.getElementById("detail-grid");
    const close = document.getElementById("detail-close");
    const marks = Array.from(document.querySelectorAll(".viz-clickable"));

    function text(value) {
      return value == null ? "" : String(value);
    }

    function clamp(value, min, max) {
      return Math.max(min, Math.min(max, value));
    }

    function positionPopover(clientX, clientY) {
      popover.hidden = false;
      const margin = 12;
      const rect = popover.getBoundingClientRect();
      const left = clamp(clientX + 14, margin, window.innerWidth - rect.width - margin);
      const top = clamp(clientY + 14, margin, window.innerHeight - rect.height - margin);
      popover.style.left = `${left}px`;
      popover.style.top = `${top}px`;
    }

    function hidePopover() {
      popover.hidden = true;
      marks.forEach((item) => item.classList.remove("is-selected"));
    }

    function render(mark, clientX, clientY) {
      let data;
      try {
        data = JSON.parse(mark.dataset.detail || "{}");
      } catch {
        return;
      }
      marks.forEach((item) => item.classList.remove("is-selected"));
      mark.classList.add("is-selected");
      title.textContent = data.title || "Selection";
      grid.replaceChildren();
      for (const row of data.rows || []) {
        const label = document.createElement("div");
        label.className = "detail-label";
        label.textContent = text(row.label);
        const value = document.createElement("div");
        value.className = `detail-value ${row.tone || ""}`.trim();
        value.textContent = text(row.value);
        grid.append(label, value);
      }
      positionPopover(clientX, clientY);
    }

    for (const mark of marks) {
      mark.addEventListener("click", (event) => {
        event.stopPropagation();
        render(mark, event.clientX, event.clientY);
      });
      mark.addEventListener("keydown", (event) => {
        if (event.key === "Enter" || event.key === " ") {
          event.preventDefault();
          const rect = mark.getBoundingClientRect();
          render(mark, rect.left + rect.width / 2, rect.top + rect.height / 2);
        }
      });
    }

    close.addEventListener("click", (event) => {
      event.stopPropagation();
      hidePopover();
    });
    document.addEventListener("click", (event) => {
      if (!popover.hidden && !popover.contains(event.target)) {
        hidePopover();
      }
    });
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape") {
        hidePopover();
      }
    });
  })();
  </script>
"""


def chart_count_by_hour(hourly: list[dict]) -> str:
    width, height = 1120, 380
    left, right, top, bottom = 64, 28, 34, 54
    inner_w = width - left - right
    inner_h = height - top - bottom
    max_count = max(max(row["win_count"], row["loss_count"]) for row in hourly) or 1
    step = inner_w / 24
    bar_w = step * 0.32
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Profit and loss trade counts by Beijing open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
    ]
    for i in range(5):
        value = max_count * i / 4
        y = top + inner_h - inner_h * i / 4
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(svg_text(16, y + 4, f"{value:.0f}", fill=MUTED, font_size=12))
    for row in hourly:
        x0 = left + row["hour"] * step + step * 0.15
        win_h = inner_h * row["win_count"] / max_count
        loss_h = inner_h * row["loss_count"] / max_count
        win_title = (
            f"{row['hour']:02d}:00 profitable trades={row['win_count']} "
            f"total trades={row['count']} win rate={row['win_rate']:.1f}% "
            f"net={fmt_money(row['net'])}"
        )
        loss_title = (
            f"{row['hour']:02d}:00 losing trades={row['loss_count']} "
            f"total trades={row['count']} win rate={row['win_rate']:.1f}% "
            f"net={fmt_money(row['net'])}"
        )
        detail = detail_payload(
            f"{row['hour']:02d}:00 trade count",
            [
                ("Total trades", str(row["count"]), None),
                ("Profitable trades", str(row["win_count"]), "pos"),
                ("Losing trades", str(row["loss_count"]), "neg"),
                ("Win rate", pct(row["win_rate"]), None),
                ("Winner sum", fmt_money(row["positive_net"]), "pos"),
                ("Loser sum", fmt_money(row["negative_net"]), "neg"),
                ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
            ],
        )
        parts.append(svg_rect(x0, top + inner_h - win_h, bar_w, win_h, GREEN, title=win_title, detail=detail, rx=3))
        parts.append(svg_rect(x0 + bar_w + 4, top + inner_h - loss_h, bar_w, loss_h, RED, title=loss_title, detail=detail, rx=3))
        parts.append(svg_text(left + row["hour"] * step + step / 2, height - 24, f"{row['hour']:02d}", fill=MUTED, font_size=12, text_anchor="middle"))
    parts.append(svg_text(left, 22, "Profitable vs losing trades by Beijing open hour", fill=TEXT, font_size=16, font_weight=700))
    parts.append(svg_rect(width - 230, 14, 12, 12, GREEN, rx=2))
    parts.append(svg_text(width - 212, 25, "profitable count", fill=MUTED, font_size=12))
    parts.append(svg_rect(width - 112, 14, 12, 12, RED, rx=2))
    parts.append(svg_text(width - 94, 25, "losing count", fill=MUTED, font_size=12))
    parts.append("</svg>")
    return "\n".join(parts)


def chart_net_by_hour(hourly: list[dict]) -> str:
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
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Profit and loss money by Beijing open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
        f'<line x1="{left}" y1="{baseline:.1f}" x2="{width-right}" y2="{baseline:.1f}" stroke="#7f8b9e" stroke-width="1.2"/>',
    ]
    for frac in (-1, -0.5, 0.5, 1):
        y = baseline - frac * max_abs * scale
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(svg_text(12, y + 4, fmt_money(frac * max_abs), fill=MUTED, font_size=11))
    for row in hourly:
        x = left + row["hour"] * step + step * 0.22
        w = step * 0.56
        pos_h = row["positive_net"] * scale
        neg_h = abs(row["negative_net"]) * scale
        if row["positive_net"] > 0:
            title = (
                f"{row['hour']:02d}:00 winner sum={fmt_money(row['positive_net'])} "
                f"loser sum={fmt_money(row['negative_net'])} net={fmt_money(row['net'])} "
                f"trades={row['count']}"
            )
            detail = detail_payload(
                f"{row['hour']:02d}:00 PnL",
                [
                    ("Total trades", str(row["count"]), None),
                    ("Winner sum", fmt_money(row["positive_net"]), "pos"),
                    ("Loser sum", fmt_money(row["negative_net"]), "neg"),
                    ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                    ("Average net", fmt_money(row["avg_net"]), money_tone(row["avg_net"])),
                    ("Median net", fmt_money(row["median_net"]), money_tone(row["median_net"])),
                    ("Best trade", fmt_money(row["best"]), money_tone(row["best"])),
                    ("Worst trade", fmt_money(row["worst"]), money_tone(row["worst"])),
                ],
            )
            parts.append(svg_rect(x, baseline - pos_h, w, pos_h, GREEN, title=title, detail=detail, rx=3))
        if row["negative_net"] < 0:
            title = (
                f"{row['hour']:02d}:00 loser sum={fmt_money(row['negative_net'])} "
                f"winner sum={fmt_money(row['positive_net'])} net={fmt_money(row['net'])} "
                f"trades={row['count']}"
            )
            detail = detail_payload(
                f"{row['hour']:02d}:00 PnL",
                [
                    ("Total trades", str(row["count"]), None),
                    ("Winner sum", fmt_money(row["positive_net"]), "pos"),
                    ("Loser sum", fmt_money(row["negative_net"]), "neg"),
                    ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                    ("Average net", fmt_money(row["avg_net"]), money_tone(row["avg_net"])),
                    ("Median net", fmt_money(row["median_net"]), money_tone(row["median_net"])),
                    ("Best trade", fmt_money(row["best"]), money_tone(row["best"])),
                    ("Worst trade", fmt_money(row["worst"]), money_tone(row["worst"])),
                ],
            )
            parts.append(svg_rect(x, baseline, w, neg_h, RED, title=title, detail=detail, rx=3))
        net_y = baseline - row["net"] * scale
        detail = detail_payload(
            f"{row['hour']:02d}:00 net marker",
            [
                ("Net PnL", fmt_money(row["net"]), money_tone(row["net"])),
                ("Winner sum", fmt_money(row["positive_net"]), "pos"),
                ("Loser sum", fmt_money(row["negative_net"]), "neg"),
                ("Total trades", str(row["count"]), None),
            ],
        )
        parts.append(
            f'<circle cx="{x + w / 2:.1f}" cy="{net_y:.1f}" r="3.2" '
            f'fill="{GOLD}"{detail_attrs(detail)}><title>{html.escape(detail["title"])}</title></circle>'
        )
        parts.append(svg_text(left + row["hour"] * step + step / 2, height - 24, f"{row['hour']:02d}", fill=MUTED, font_size=12, text_anchor="middle"))
    parts.append(svg_text(left, 24, "Positive and negative net PnL by Beijing open hour", fill=TEXT, font_size=16, font_weight=700))
    parts.append(svg_rect(width - 322, 14, 12, 12, GREEN, rx=2))
    parts.append(svg_text(width - 304, 25, "sum of winners", fill=MUTED, font_size=12))
    parts.append(svg_rect(width - 202, 14, 12, 12, RED, rx=2))
    parts.append(svg_text(width - 184, 25, "sum of losers", fill=MUTED, font_size=12))
    parts.append(f'<circle cx="{width - 74}" cy="20" r="3.2" fill="{GOLD}"/>')
    parts.append(svg_text(width - 64, 25, "net", fill=MUTED, font_size=12))
    parts.append("</svg>")
    return "\n".join(parts)


def chart_scatter(trades: list[dict]) -> str:
    width, height = 1120, 460
    left, right, top, bottom = 78, 26, 34, 58
    inner_w = width - left - right
    inner_h = height - top - bottom
    dates = sorted({trade["date"] for trade in trades})
    date_index = {date: idx for idx, date in enumerate(dates)}
    max_abs = max(abs(trade["net_pnl"]) for trade in trades) or 1
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="Trade scatter by date and time of day">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
    ]
    for hour in range(0, 25, 3):
        y = top + inner_h * hour / 24
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{width-right}" y2="{y:.1f}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(svg_text(18, y + 4, f"{hour:02d}:00", fill=MUTED, font_size=11))
    month_marks = []
    seen_months = set()
    for date in dates:
        month = date[:7]
        if month not in seen_months:
            seen_months.add(month)
            month_marks.append((date_index[date], month))
    for idx, label in month_marks:
        x = left + (idx / max(len(dates) - 1, 1)) * inner_w
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top+inner_h}" stroke="{GRID}" stroke-width="1"/>')
        parts.append(svg_text(x + 4, height - 22, label, fill=MUTED, font_size=11))
    for trade in trades:
        x = left + (date_index[trade["date"]] / max(len(dates) - 1, 1)) * inner_w
        y = top + (trade["minute_of_day"] / 1440) * inner_h
        radius = 2.4 + min(math.sqrt(abs(trade["net_pnl"]) / max_abs) * 8, 8)
        color = GREEN if trade["net_pnl"] > 0 else RED if trade["net_pnl"] < 0 else MUTED
        opacity = 0.82 if abs(trade["net_pnl"]) >= 20 else 0.45
        title = html.escape(
            f"{trade['opened_bj']:%Y-%m-%d %H:%M} {trade['symbol']} {fmt_money(trade['net_pnl'])}"
        )
        detail = detail_payload(
            f"{trade['symbol']} {trade['round_trip_id']}",
            [
                ("Opened", f"{trade['opened_bj']:%Y-%m-%d %H:%M:%S}", None),
                ("Closed", f"{trade['closed_bj']:%Y-%m-%d %H:%M:%S}", None),
                ("Open hour", f"{trade['hour']:02d}:00", None),
                ("Gross PnL", fmt_money(trade["gross_pnl"]), money_tone(trade["gross_pnl"])),
                ("Commission", fmt_plain_money(trade["commission"]), "neg"),
                ("Net PnL", fmt_money(trade["net_pnl"]), money_tone(trade["net_pnl"])),
                ("Exit reason", trade["exit_reason"], None),
                ("Duration", f"{trade['duration_seconds'] / 3600:.1f}h", None),
            ],
        )
        parts.append(
            f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" '
            f'opacity="{opacity}"{detail_attrs(detail)}><title>{title}</title></circle>'
        )
    parts.append(svg_text(left, 24, "Each trade by open date and Beijing time of day", fill=TEXT, font_size=16, font_weight=700))
    parts.append("</svg>")
    return "\n".join(parts)


def heat_color(value: float, max_value: float, color: str) -> str:
    if max_value <= 0 or value <= 0:
        return "#151d2a"
    alpha = 0.16 + 0.84 * min(value / max_value, 1)
    if color == "green":
        return f"rgba(33, 199, 132, {alpha:.3f})"
    return f"rgba(255, 77, 109, {alpha:.3f})"


def chart_date_hour_heatmap(trades: list[dict], *, kind: str) -> str:
    dates = sorted({trade["date"] for trade in trades})
    cell_w, cell_h = 34, 11
    left, right, top, bottom = 92, 26, 42, 36
    width = left + 24 * cell_w + right
    height = top + len(dates) * cell_h + bottom
    by_key = defaultdict(list)
    for trade in trades:
        if kind == "winner" and trade["net_pnl"] <= 0:
            continue
        if kind == "loser" and trade["net_pnl"] >= 0:
            continue
        by_key[(trade["date"], trade["hour"])].append(trade)
    max_value = max((len(rows) for rows in by_key.values()), default=1)
    color_kind = "green" if kind == "winner" else "red"
    title = "Profitable trade count heatmap" if kind == "winner" else "Losing trade count heatmap"
    parts = [
        f'<svg viewBox="0 0 {width} {height}" role="img" aria-label="{title} by date and Beijing open hour">',
        svg_rect(0, 0, width, height, PANEL, rx=8),
        svg_text(left, 25, f"{title} by date x Beijing open hour", fill=TEXT, font_size=16, font_weight=700),
    ]
    for hour in range(24):
        x = left + hour * cell_w + cell_w / 2
        parts.append(svg_text(x, top - 9, f"{hour:02d}", fill=MUTED, font_size=10, text_anchor="middle"))
    for row_idx, date in enumerate(dates):
        y = top + row_idx * cell_h
        if date.endswith("-01") or row_idx == 0 or row_idx == len(dates) - 1:
            parts.append(svg_text(12, y + 8.5, date, fill=MUTED, font_size=10))
        for hour in range(24):
            cell_trades = by_key.get((date, hour), [])
            value = len(cell_trades)
            net = sum(trade["net_pnl"] for trade in cell_trades)
            symbols = ", ".join(trade["symbol"] for trade in cell_trades[:10])
            fill = heat_color(value, max_value, color_kind)
            x = left + hour * cell_w
            title_tag = html.escape(
                f"{date} {hour:02d}:00 count={int(value)} net={fmt_money(net)} {symbols}"
            )
            detail = detail_payload(
                f"{date} {hour:02d}:00 {'profitable' if kind == 'winner' else 'losing'} trades",
                [
                    ("Date", date, None),
                    ("Open hour", f"{hour:02d}:00", None),
                    ("Trade type", "Profitable" if kind == "winner" else "Losing", "pos" if kind == "winner" else "neg"),
                    ("Count", str(int(value)), None),
                    ("Net PnL", fmt_money(net), money_tone(net)),
                    ("Symbols", symbols, None),
                ],
            )
            parts.append(
                f'<rect x="{x:.1f}" y="{y:.1f}" width="{cell_w-1:.1f}" '
                f'height="{cell_h-1:.1f}" fill="{fill}"{detail_attrs(detail)}>'
                f'<title>{title_tag}</title></rect>'
            )
    parts.append("</svg>")
    return "\n".join(parts)


def render_table(hourly: list[dict]) -> str:
    rows = []
    for row in sorted(hourly, key=lambda item: item["net"]):
        pf = "inf" if math.isinf(row["profit_factor"]) else f"{row['profit_factor']:.2f}"
        rows.append(
            "<tr>"
            f"<td>{row['hour']:02d}:00</td>"
            f"<td>{row['count']}</td>"
            f"<td>{row['win_count']}</td>"
            f"<td>{row['loss_count']}</td>"
            f"<td>{pct(row['win_rate'])}</td>"
            f"<td class=\"money {'pos' if row['positive_net'] >= 0 else 'neg'}\">{fmt_money(row['positive_net'])}</td>"
            f"<td class=\"money neg\">{fmt_money(row['negative_net'])}</td>"
            f"<td class=\"money {'pos' if row['net'] >= 0 else 'neg'}\">{fmt_money(row['net'])}</td>"
            f"<td class=\"money {'pos' if row['avg_net'] >= 0 else 'neg'}\">{fmt_money(row['avg_net'])}</td>"
            f"<td class=\"money {'pos' if row['median_net'] >= 0 else 'neg'}\">{fmt_money(row['median_net'])}</td>"
            f"<td>{pf}</td>"
            f"<td>{row['avg_hold_hours']:.1f}h</td>"
            "</tr>"
        )
    return "\n".join(rows)


def render_html(db_path: Path, trades: list[dict], hourly: list[dict]) -> str:
    winners = [trade for trade in trades if trade["net_pnl"] > 0]
    losers = [trade for trade in trades if trade["net_pnl"] < 0]
    total_net = sum(trade["net_pnl"] for trade in trades)
    total_gross = sum(trade["gross_pnl"] for trade in trades)
    total_fee = sum(trade["commission"] for trade in trades)
    worst_hour = min(hourly, key=lambda row: row["net"])
    best_hour = max(hourly, key=lambda row: row["net"])
    generated_at = datetime.now(BEIJING)
    rows_json = json.dumps(
        [
            {
                "symbol": trade["symbol"],
                "round_trip_id": trade["round_trip_id"],
                "opened_bj": trade["opened_bj"].isoformat(),
                "hour": trade["hour"],
                "net_pnl": trade["net_pnl"],
            }
            for trade in trades
        ],
        ensure_ascii=False,
    )
    return f"""<!doctype html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Trade Time Distribution</title>
<style>
:root {{
  color-scheme: dark;
  --bg: #070a10;
  --panel: {PANEL};
  --panel2: {PANEL_2};
  --text: {TEXT};
  --muted: {MUTED};
  --grid: {GRID};
  --green: {GREEN};
  --red: {RED};
  --gold: {GOLD};
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
h1 {{
  margin: 0 0 4px;
  font-size: 28px;
  letter-spacing: 0;
}}
.subtle {{
  color: var(--muted);
}}
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
.value {{
  margin-top: 6px;
  font-size: 22px;
  font-weight: 700;
}}
.pos {{ color: var(--green); }}
.neg {{ color: var(--red); }}
.chart {{
  margin-top: 18px;
}}
svg {{
  display: block;
  width: 100%;
  height: auto;
  border: 1px solid #1d2838;
  border-radius: 8px;
}}
.heatmaps {{
  display: grid;
  grid-template-columns: 1fr;
  gap: 18px;
  margin-top: 18px;
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
th {{
  color: var(--muted);
  font-size: 12px;
  font-weight: 600;
}}
th:first-child, td:first-child {{
  text-align: left;
}}
tr:last-child td {{ border-bottom: 0; }}
.money {{
  font-variant-numeric: tabular-nums;
}}
.note {{
  margin-top: 14px;
  color: var(--muted);
}}
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
  .table-wrap {{ overflow-x: auto; }}
  .detail-grid {{ grid-template-columns: 1fr; }}
}}
</style>
</head>
<body>
<main>
  <h1>Trade Time Distribution</h1>
  <div class="subtle">Source: {html.escape(str(db_path))} · generated at {generated_at:%Y-%m-%d %H:%M:%S} Beijing time · bucketed by open time</div>

  <section class="cards">
    <div class="metric"><div class="label">Trades</div><div class="value">{len(trades)}</div></div>
    <div class="metric"><div class="label">Win / Loss</div><div class="value"><span class="pos">{len(winners)}</span> / <span class="neg">{len(losers)}</span></div></div>
    <div class="metric"><div class="label">Net PnL</div><div class="value {'pos' if total_net >= 0 else 'neg'}">{fmt_money(total_net)}</div></div>
    <div class="metric"><div class="label">Worst / Best Hour</div><div class="value"><span class="neg">{worst_hour['hour']:02d}</span> / <span class="pos">{best_hour['hour']:02d}</span></div></div>
  </section>

  <div class="note">Gross {fmt_money(total_gross)} · commission {fmt_plain_money(total_fee)} · Beijing open range {trades[0]['opened_bj']:%Y-%m-%d %H:%M} to {trades[-1]['opened_bj']:%Y-%m-%d %H:%M}</div>
{detail_panel_html()}

  <section class="chart">{chart_count_by_hour(hourly)}</section>
  <section class="chart">{chart_net_by_hour(hourly)}</section>
  <section class="chart">{chart_scatter(trades)}</section>

  <section class="heatmaps">
    {chart_date_hour_heatmap(trades, kind="winner")}
    {chart_date_hour_heatmap(trades, kind="loser")}
  </section>

  <div class="table-wrap">
    <table>
      <thead>
        <tr>
          <th>Hour</th><th>Trades</th><th>Wins</th><th>Losses</th><th>Win Rate</th>
          <th>Winner Sum</th><th>Loser Sum</th><th>Net</th><th>Avg Net</th><th>Median</th><th>PF</th><th>Avg Hold</th>
        </tr>
      </thead>
      <tbody>
        {render_table(hourly)}
      </tbody>
    </table>
  </div>

  <script type="application/json" id="trade-data">{html.escape(rows_json)}</script>
{interaction_script()}
</main>
</body>
</html>
"""


def main() -> None:
    args = parse_args()
    trades = load_trades(args.db)
    if not trades:
        raise SystemExit("no trades found")

    hourly = summarize_by_hour(trades)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(render_html(args.db, trades, hourly), encoding="utf-8")
    print(args.output)


if __name__ == "__main__":
    main()
