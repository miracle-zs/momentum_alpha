#!/usr/bin/env python3
"""Historical Slippage Analysis Tool for Momentum Alpha.

Analyzes entry slippage (decision latest_price vs executed fill average_price)
and exit slippage (stop trigger price vs actual executed exit price)
from runtime database history (signal_decisions, trade_fills, stop_exit_summaries).
"""

from __future__ import annotations

import argparse
import csv
from dataclasses import asdict, dataclass
import json
import math
from pathlib import Path
import sqlite3
import sys
from typing import Any, Sequence

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / "src"
if str(SRC) not in sys.path:
    sys.path.insert(0, str(SRC))

from momentum_alpha.runtime_schema import _connect


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Analyze historical entry and exit slippage from Momentum Alpha runtime database.",
    )
    parser.add_argument(
        "--db",
        type=Path,
        required=True,
        help="Path to runtime.db SQLite database file",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Optional directory to save detailed CSV and JSON summary reports",
    )
    parser.add_argument(
        "--min-date",
        type=str,
        default=None,
        help="Filter records on or after this ISO datetime/date (e.g. 2026-04-01)",
    )
    parser.add_argument(
        "--max-date",
        type=str,
        default=None,
        help="Filter records before this ISO datetime/date (e.g. 2026-05-01)",
    )
    parser.add_argument(
        "--json",
        action="store_true",
        help="Output summary statistics as JSON to stdout instead of formatted table",
    )
    return parser.parse_args()


@dataclass(frozen=True)
class EntrySlippageRecord:
    timestamp: str
    symbol: str
    leg_type: str
    decision_price: float
    fill_price: float
    quantity: float
    notional_usd: float
    slippage_abs: float
    slippage_pct: float
    slippage_bps: float
    slippage_usd: float
    intent_id: str | None
    client_order_id: str | None


@dataclass(frozen=True)
class ExitSlippageRecord:
    timestamp: str
    symbol: str
    round_trip_id: str
    trigger_price: float
    average_exit_price: float
    quantity: float
    notional_usd: float
    slippage_abs: float
    slippage_pct: float
    slippage_bps: float
    slippage_usd: float


@dataclass(frozen=True)
class SlippageDistribution:
    count: int
    mean_pct: float
    mean_bps: float
    median_bps: float
    p90_bps: float
    p95_bps: float
    p99_bps: float
    max_adverse_bps: float
    max_favorable_bps: float
    total_slippage_usd: float
    mean_slippage_usd: float
    adverse_count: int
    favorable_count: int
    zero_count: int


def _percentile(sorted_values: Sequence[float], pct: float) -> float:
    if not sorted_values:
        return 0.0
    if len(sorted_values) == 1:
        return sorted_values[0]
    index = (len(sorted_values) - 1) * (pct / 100.0)
    lower = int(math.floor(index))
    upper = int(math.ceil(index))
    weight = index - lower
    return sorted_values[lower] * (1.0 - weight) + sorted_values[upper] * weight


def compute_distribution(bps_values: Sequence[float], usd_values: Sequence[float]) -> SlippageDistribution:
    if not bps_values:
        return SlippageDistribution(
            count=0,
            mean_pct=0.0,
            mean_bps=0.0,
            median_bps=0.0,
            p90_bps=0.0,
            p95_bps=0.0,
            p99_bps=0.0,
            max_adverse_bps=0.0,
            max_favorable_bps=0.0,
            total_slippage_usd=0.0,
            mean_slippage_usd=0.0,
            adverse_count=0,
            favorable_count=0,
            zero_count=0,
        )

    sorted_bps = sorted(bps_values)
    count = len(sorted_bps)
    mean_bps = sum(sorted_bps) / count
    mean_pct = mean_bps / 100.0
    median_bps = _percentile(sorted_bps, 50.0)
    p90_bps = _percentile(sorted_bps, 90.0)
    p95_bps = _percentile(sorted_bps, 95.0)
    p99_bps = _percentile(sorted_bps, 99.0)
    max_adverse_bps = sorted_bps[-1]
    max_favorable_bps = sorted_bps[0]

    total_usd = sum(usd_values)
    mean_usd = total_usd / count if count > 0 else 0.0

    adverse = sum(1 for v in sorted_bps if v > 0.001)
    favorable = sum(1 for v in sorted_bps if v < -0.001)
    zero = count - adverse - favorable

    return SlippageDistribution(
        count=count,
        mean_pct=round(mean_pct, 4),
        mean_bps=round(mean_bps, 2),
        median_bps=round(median_bps, 2),
        p90_bps=round(p90_bps, 2),
        p95_bps=round(p95_bps, 2),
        p99_bps=round(p99_bps, 2),
        max_adverse_bps=round(max_adverse_bps, 2),
        max_favorable_bps=round(max_favorable_bps, 2),
        total_slippage_usd=round(total_usd, 2),
        mean_slippage_usd=round(mean_usd, 2),
        adverse_count=adverse,
        favorable_count=favorable,
        zero_count=zero,
    )


def load_entry_slippage(
    db_path: Path,
    min_date: str | None = None,
    max_date: str | None = None,
) -> list[EntrySlippageRecord]:
    """Extract entry orders and correlate decision prices with execution fills."""
    if not db_path.exists():
        return []

    with _connect(db_path, readonly=True) as conn:
        conn.row_factory = sqlite3.Row

        # 1. Fetch signal decisions that decided on an entry
        date_filter = ""
        params: list[Any] = []
        if min_date:
            date_filter += " AND timestamp >= ?"
            params.append(min_date)
        if max_date:
            date_filter += " AND timestamp < ?"
            params.append(max_date)

        decision_rows = conn.execute(
            f"""
            SELECT timestamp, decision_id, intent_id, decision_type, symbol, payload_json
            FROM signal_decisions
            WHERE decision_type IN ('base_entry', 'add_on')
            {date_filter}
            ORDER BY timestamp ASC, id ASC
            """,
            params,
        ).fetchall()

        decision_by_intent: dict[str, dict] = {}
        for row in decision_rows:
            intent_id = row["intent_id"]
            if not intent_id:
                continue
            payload = {}
            if row["payload_json"]:
                try:
                    payload = json.loads(row["payload_json"])
                except Exception:
                    pass
            latest_price = payload.get("latest_price")
            if latest_price is not None:
                try:
                    decision_by_intent[intent_id] = {
                        "timestamp": row["timestamp"],
                        "symbol": row["symbol"],
                        "decision_type": row["decision_type"],
                        "latest_price": float(latest_price),
                        "leg_type": payload.get("leg_type", "base" if row["decision_type"] == "base_entry" else "add_on"),
                    }
                except (ValueError, TypeError):
                    continue

        # 2. Fetch trade fills for entries (side = BUY)
        fill_rows = conn.execute(
            f"""
            SELECT timestamp, symbol, client_order_id, intent_id, side, quantity, average_price, last_price
            FROM trade_fills
            WHERE side = 'BUY'
            {date_filter}
            ORDER BY timestamp ASC, id ASC
            """,
            params,
        ).fetchall()

        # Group fills by client_order_id or intent_id
        grouped_fills: dict[str, list[dict]] = {}
        for row in fill_rows:
            cid = row["client_order_id"] or ""
            intent_id = row["intent_id"] or (cid[:-1] if cid.endswith("e") else cid)
            if not intent_id:
                continue
            grouped_fills.setdefault(intent_id, []).append(row)

        records: list[EntrySlippageRecord] = []
        for intent_id, fills in grouped_fills.items():
            decision = decision_by_intent.get(intent_id)
            if not decision:
                # If no direct match in signal_decisions, try looking up from client_order_id
                continue

            total_qty = 0.0
            total_notional = 0.0
            last_timestamp = fills[0]["timestamp"]
            cid = fills[0]["client_order_id"]

            for f in fills:
                try:
                    q = float(f["quantity"] or 0)
                    p = float(f["average_price"] or f["last_price"] or 0)
                except (ValueError, TypeError):
                    continue
                if q > 0 and p > 0:
                    total_qty += q
                    total_notional += q * p
                    last_timestamp = f["timestamp"]

            if total_qty <= 0 or total_notional <= 0:
                continue

            avg_fill_price = total_notional / total_qty
            decision_price = decision["latest_price"]

            if decision_price <= 0:
                continue

            # For BUY orders, paying more than decision price is adverse slippage (+)
            slip_abs = avg_fill_price - decision_price
            slip_pct = (slip_abs / decision_price) * 100.0
            slip_bps = slip_pct * 100.0
            slip_usd = slip_abs * total_qty

            records.append(
                EntrySlippageRecord(
                    timestamp=last_timestamp,
                    symbol=decision["symbol"],
                    leg_type=decision["leg_type"],
                    decision_price=round(decision_price, 8),
                    fill_price=round(avg_fill_price, 8),
                    quantity=round(total_qty, 8),
                    notional_usd=round(total_notional, 2),
                    slippage_abs=round(slip_abs, 8),
                    slippage_pct=round(slip_pct, 4),
                    slippage_bps=round(slip_bps, 2),
                    slippage_usd=round(slip_usd, 4),
                    intent_id=intent_id,
                    client_order_id=cid,
                )
            )

        return records


def load_exit_slippage(
    db_path: Path,
    min_date: str | None = None,
    max_date: str | None = None,
) -> list[ExitSlippageRecord]:
    """Extract stop exit records from stop_exit_summaries table."""
    if not db_path.exists():
        return []

    with _connect(db_path, readonly=True) as conn:
        conn.row_factory = sqlite3.Row

        # Check if table exists
        has_table = conn.execute(
            "SELECT 1 FROM sqlite_master WHERE type = 'table' AND name = 'stop_exit_summaries'"
        ).fetchone()
        if not has_table:
            return []

        date_filter = ""
        params: list[Any] = []
        if min_date:
            date_filter += " AND timestamp >= ?"
            params.append(min_date)
        if max_date:
            date_filter += " AND timestamp < ?"
            params.append(max_date)

        rows = conn.execute(
            f"""
            SELECT timestamp, symbol, round_trip_id, trigger_price, average_exit_price,
                   slippage_abs, slippage_pct, exit_quantity
            FROM stop_exit_summaries
            WHERE 1=1
            {date_filter}
            ORDER BY timestamp ASC, id ASC
            """,
            params,
        ).fetchall()

        records: list[ExitSlippageRecord] = []
        for r in rows:
            try:
                trigger = float(r["trigger_price"] or 0)
                exit_price = float(r["average_exit_price"] or 0)
                qty = float(r["exit_quantity"] or 0)
            except (ValueError, TypeError):
                continue

            if trigger <= 0 or exit_price <= 0:
                continue

            # For Long exit (SELL), selling below trigger is adverse slippage (+)
            slip_abs = trigger - exit_price
            slip_pct = (slip_abs / trigger) * 100.0
            slip_bps = slip_pct * 100.0
            slip_usd = slip_abs * qty
            notional = exit_price * qty

            records.append(
                ExitSlippageRecord(
                    timestamp=r["timestamp"],
                    symbol=r["symbol"],
                    round_trip_id=r["round_trip_id"],
                    trigger_price=round(trigger, 8),
                    average_exit_price=round(exit_price, 8),
                    quantity=round(qty, 8),
                    notional_usd=round(notional, 2),
                    slippage_abs=round(slip_abs, 8),
                    slippage_pct=round(slip_pct, 4),
                    slippage_bps=round(slip_bps, 2),
                    slippage_usd=round(slip_usd, 4),
                )
            )

        return records


def format_table(title: str, headers: list[str], rows: list[list[str]]) -> str:
    """Format an ASCII table with consistent alignment."""
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, val in enumerate(row):
            col_widths[i] = max(col_widths[i], len(val))

    header_line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    separator_line = "-+-".join("-" * col_widths[i] for i in range(len(headers)))
    data_lines = [
        " | ".join(val.ljust(col_widths[i]) for i, val in enumerate(row))
        for row in rows
    ]

    return f"\n=== {title} ===\n{header_line}\n{separator_line}\n" + "\n".join(data_lines) + "\n"


def build_analysis_report(
    entry_records: list[EntrySlippageRecord],
    exit_records: list[ExitSlippageRecord],
) -> dict[str, Any]:
    entry_bps = [r.slippage_bps for r in entry_records]
    entry_usd = [r.slippage_usd for r in entry_records]
    entry_dist = compute_distribution(entry_bps, entry_usd)

    exit_bps = [r.slippage_bps for r in exit_records]
    exit_usd = [r.slippage_usd for r in exit_records]
    exit_dist = compute_distribution(exit_bps, exit_usd)

    # Leg breakdown
    base_entries = [r for r in entry_records if r.leg_type == "base"]
    addon_entries = [r for r in entry_records if r.leg_type != "base"]
    base_dist = compute_distribution([r.slippage_bps for r in base_entries], [r.slippage_usd for r in base_entries])
    addon_dist = compute_distribution([r.slippage_bps for r in addon_entries], [r.slippage_usd for r in addon_entries])

    # Symbol breakdown
    symbol_entry_map: dict[str, list[EntrySlippageRecord]] = {}
    for r in entry_records:
        symbol_entry_map.setdefault(r.symbol, []).append(r)

    symbol_stats: list[dict[str, Any]] = []
    for sym, recs in symbol_entry_map.items():
        dist = compute_distribution([r.slippage_bps for r in recs], [r.slippage_usd for r in recs])
        symbol_stats.append({
            "symbol": sym,
            "count": dist.count,
            "mean_bps": dist.mean_bps,
            "median_bps": dist.median_bps,
            "p95_bps": dist.p95_bps,
            "max_adverse_bps": dist.max_adverse_bps,
            "total_usd": dist.total_slippage_usd,
        })
    symbol_stats.sort(key=lambda x: x["total_usd"], reverse=True)

    return {
        "entry_summary": asdict(entry_dist),
        "exit_summary": asdict(exit_dist),
        "base_leg_summary": asdict(base_dist),
        "add_on_leg_summary": asdict(addon_dist),
        "symbol_breakdown": symbol_stats,
    }


def print_cli_report(report: dict[str, Any]) -> None:
    ed = report["entry_summary"]
    xd = report["exit_summary"]
    bd = report["base_leg_summary"]
    ad = report["add_on_leg_summary"]

    headers = [
        "Category", "Count", "Mean (bps)", "Median (bps)", "P90 (bps)",
        "P95 (bps)", "P99 (bps)", "Max Adv (bps)", "Total Slip ($)",
    ]
    rows = [
        [
            "All Entries (Market)",
            str(ed["count"]),
            f"{ed['mean_bps']:+.1f}",
            f"{ed['median_bps']:+.1f}",
            f"{ed['p90_bps']:+.1f}",
            f"{ed['p95_bps']:+.1f}",
            f"{ed['p99_bps']:+.1f}",
            f"{ed['max_adverse_bps']:+.1f}",
            f"${ed['total_slippage_usd']:,.2f}",
        ],
        [
            "  - Base Legs",
            str(bd["count"]),
            f"{bd['mean_bps']:+.1f}",
            f"{bd['median_bps']:+.1f}",
            f"{bd['p90_bps']:+.1f}",
            f"{bd['p95_bps']:+.1f}",
            f"{bd['p99_bps']:+.1f}",
            f"{bd['max_adverse_bps']:+.1f}",
            f"${bd['total_slippage_usd']:,.2f}",
        ],
        [
            "  - Add-on Legs",
            str(ad["count"]),
            f"{ad['mean_bps']:+.1f}",
            f"{ad['median_bps']:+.1f}",
            f"{ad['p90_bps']:+.1f}",
            f"{ad['p95_bps']:+.1f}",
            f"{ad['p99_bps']:+.1f}",
            f"{ad['max_adverse_bps']:+.1f}",
            f"${ad['total_slippage_usd']:,.2f}",
        ],
        [
            "Stop Exits (Stop-Market)",
            str(xd["count"]),
            f"{xd['mean_bps']:+.1f}",
            f"{xd['median_bps']:+.1f}",
            f"{xd['p90_bps']:+.1f}",
            f"{xd['p95_bps']:+.1f}",
            f"{xd['p99_bps']:+.1f}",
            f"{xd['max_adverse_bps']:+.1f}",
            f"${xd['total_slippage_usd']:,.2f}",
        ],
    ]
    print(format_table("MOMENTUM ALPHA HISTORICAL SLIPPAGE SUMMARY", headers, rows))

    # Print top symbols
    top_symbols = report["symbol_breakdown"][:10]
    if top_symbols:
        sym_headers = ["Symbol", "Orders", "Mean (bps)", "Median (bps)", "P95 (bps)", "Max Adv (bps)", "Total Slip ($)"]
        sym_rows = [
            [
                s["symbol"],
                str(s["count"]),
                f"{s['mean_bps']:+.1f}",
                f"{s['median_bps']:+.1f}",
                f"{s['p95_bps']:+.1f}",
                f"{s['max_adverse_bps']:+.1f}",
                f"${s['total_usd']:,.2f}",
            ]
            for s in top_symbols
        ]
        print(format_table("TOP 10 SYMBOLS BY SLIPPAGE IMPACT", sym_headers, sym_rows))


def export_csv(
    output_dir: Path,
    entry_records: list[EntrySlippageRecord],
    exit_records: list[ExitSlippageRecord],
    report: dict[str, Any],
) -> None:
    output_dir.mkdir(parents=True, exist_ok=True)

    # 1. Entry slippage CSV
    if entry_records:
        entry_csv_path = output_dir / "entry_slippage.csv"
        with entry_csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(entry_records[0]).keys()))
            writer.writeheader()
            for r in entry_records:
                writer.writerow(asdict(r))

    # 2. Exit slippage CSV
    if exit_records:
        exit_csv_path = output_dir / "exit_slippage.csv"
        with exit_csv_path.open("w", newline="", encoding="utf-8") as f:
            writer = csv.DictWriter(f, fieldnames=list(asdict(exit_records[0]).keys()))
            writer.writeheader()
            for r in exit_records:
                writer.writerow(asdict(r))

    # 3. Summary JSON
    summary_json_path = output_dir / "slippage_summary.json"
    with summary_json_path.open("w", encoding="utf-8") as f:
        json.dump(report, f, indent=2)

    print(f"Exported detailed slippage reports to: {output_dir}")


def main() -> None:
    args = parse_args()
    if not args.db.exists():
        print(f"Error: Database file does not exist: {args.db}", file=sys.stderr)
        sys.exit(1)

    entry_records = load_entry_slippage(args.db, min_date=args.min_date, max_date=args.max_date)
    exit_records = load_exit_slippage(args.db, min_date=args.min_date, max_date=args.max_date)

    report = build_analysis_report(entry_records, exit_records)

    if args.json:
        print(json.dumps(report, indent=2))
    else:
        print_cli_report(report)

    if args.output_dir:
        export_csv(args.output_dir, entry_records, exit_records, report)


if __name__ == "__main__":
    main()
