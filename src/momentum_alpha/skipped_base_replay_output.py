from __future__ import annotations

import csv
from collections import defaultdict
from datetime import datetime
from decimal import Decimal
from pathlib import Path

from momentum_alpha.skipped_base_replay import ShadowReplayReport


SUMMARY_FIELDS = [
    "shadow_opportunity_id",
    "symbol",
    "base_signal_at",
    "base_signal_sequence",
    "first_base_signal_at",
    "blocked_reason",
    "status",
    "base_entry_price",
    "initial_stop_price",
    "base_quantity",
    "add_on_count",
    "skipped_add_on_count",
    "exit_at",
    "exit_price",
    "duration_minutes",
    "gross_pnl",
    "entry_fees",
    "exit_fees",
    "net_pnl",
    "mark_price_at_cutoff",
    "mark_to_market_net_pnl",
    "warning_count",
]

LEG_FIELDS = [
    "shadow_opportunity_id",
    "symbol",
    "leg_type",
    "sequence",
    "opened_at",
    "entry_price",
    "stop_at_entry",
    "quantity",
    "risk_budget",
    "entry_fee",
    "closed_at",
    "exit_price",
    "gross_pnl",
    "net_contribution",
]

EVENT_FIELDS = [
    "shadow_opportunity_id",
    "symbol",
    "timestamp",
    "event_type",
    "price",
    "stop_price",
    "quantity",
    "reason",
    "active_shadow_opportunity_id",
]


def _value(value) -> str | int:
    if value is None:
        return ""
    if isinstance(value, datetime):
        return value.isoformat()
    return str(value)


def _write_csv(*, path: Path, fields: list[str], rows: list[dict]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _summary_rows(report: ShadowReplayReport) -> list[dict]:
    rows = [
        {
            "shadow_opportunity_id": item.shadow_opportunity_id,
            "symbol": item.symbol,
            "base_signal_at": _value(item.base_signal_at),
            "base_signal_sequence": item.base_signal_sequence,
            "first_base_signal_at": _value(item.first_base_signal_at),
            "blocked_reason": _value(item.blocked_reason),
            "status": item.status,
            "base_entry_price": _value(item.base_entry_price),
            "initial_stop_price": _value(item.initial_stop_price),
            "base_quantity": _value(item.base_quantity),
            "add_on_count": item.add_on_count,
            "skipped_add_on_count": item.skipped_add_on_count,
            "exit_at": _value(item.exit_at),
            "exit_price": _value(item.exit_price),
            "duration_minutes": _value(item.duration_minutes),
            "gross_pnl": _value(item.gross_pnl),
            "entry_fees": _value(item.entry_fees),
            "exit_fees": _value(item.exit_fees),
            "net_pnl": _value(item.net_pnl),
            "mark_price_at_cutoff": _value(item.mark_price_at_cutoff),
            "mark_to_market_net_pnl": _value(item.mark_to_market_net_pnl),
            "warning_count": len(item.warnings),
        }
        for item in report.opportunities
    ]
    rows.extend(
        {
            "shadow_opportunity_id": item.shadow_opportunity_id,
            "symbol": item.symbol,
            "base_signal_at": _value(item.signal_at),
            "base_signal_sequence": "",
            "first_base_signal_at": "",
            "blocked_reason": item.status,
            "status": "suppressed",
            "base_entry_price": "",
            "initial_stop_price": "",
            "base_quantity": "",
            "add_on_count": 0,
            "skipped_add_on_count": 0,
            "exit_at": "",
            "exit_price": "",
            "duration_minutes": "",
            "gross_pnl": "",
            "entry_fees": "",
            "exit_fees": "",
            "net_pnl": "",
            "mark_price_at_cutoff": "",
            "mark_to_market_net_pnl": "",
            "warning_count": 0,
        }
        for item in report.overlaps
    )
    rows.extend(
        {
            "shadow_opportunity_id": item.shadow_opportunity_id,
            "symbol": item.symbol,
            "base_signal_at": _value(item.signal_at),
            "base_signal_sequence": "",
            "first_base_signal_at": "",
            "blocked_reason": item.reason,
            "status": "suppressed",
            "base_entry_price": "",
            "initial_stop_price": "",
            "base_quantity": "",
            "add_on_count": 0,
            "skipped_add_on_count": 0,
            "exit_at": "",
            "exit_price": "",
            "duration_minutes": "",
            "gross_pnl": "",
            "entry_fees": "",
            "exit_fees": "",
            "net_pnl": "",
            "mark_price_at_cutoff": "",
            "mark_to_market_net_pnl": "",
            "warning_count": 0,
        }
        for item in report.suppressed
    )
    return rows


def _leg_rows(report: ShadowReplayReport) -> list[dict]:
    rows = []
    symbols = {
        item.shadow_opportunity_id: item.symbol
        for item in report.opportunities
    }
    for item in report.opportunities:
        for leg in item.legs:
            rows.append(
                {
                    "shadow_opportunity_id": leg.shadow_opportunity_id,
                    "symbol": symbols.get(leg.shadow_opportunity_id, item.symbol),
                    "leg_type": leg.leg_type,
                    "sequence": leg.sequence,
                    "opened_at": _value(leg.opened_at),
                    "entry_price": _value(leg.entry_price),
                    "stop_at_entry": _value(leg.stop_at_entry),
                    "quantity": _value(leg.quantity),
                    "risk_budget": _value(leg.risk_budget),
                    "entry_fee": _value(leg.entry_fee),
                    "closed_at": _value(leg.closed_at),
                    "exit_price": _value(leg.exit_price),
                    "gross_pnl": _value(leg.gross_pnl),
                    "net_contribution": _value(leg.net_contribution),
                }
            )
    return rows


def _event_rows(report: ShadowReplayReport) -> list[dict]:
    rows: list[dict] = []
    for item in report.opportunities:
        for event in item.events:
            rows.append(
                {
                    "shadow_opportunity_id": event.shadow_opportunity_id,
                    "symbol": event.symbol,
                    "timestamp": _value(event.timestamp),
                    "event_type": event.event_type,
                    "price": _value(event.price),
                    "stop_price": _value(event.stop_price),
                    "quantity": _value(event.quantity),
                    "reason": _value(event.reason),
                    "active_shadow_opportunity_id": "",
                }
            )
    for overlap in report.overlaps:
        rows.append(
            {
                "shadow_opportunity_id": overlap.shadow_opportunity_id,
                "symbol": overlap.symbol,
                "timestamp": _value(overlap.signal_at),
                "event_type": overlap.status,
                "price": "",
                "stop_price": "",
                "quantity": "",
                "reason": "active_shadow_exists",
                "active_shadow_opportunity_id": overlap.active_shadow_opportunity_id,
            }
        )
    for suppressed in report.suppressed:
        rows.append(
            {
                "shadow_opportunity_id": suppressed.shadow_opportunity_id,
                "symbol": suppressed.symbol,
                "timestamp": _value(suppressed.signal_at),
                "event_type": suppressed.reason,
                "price": "",
                "stop_price": "",
                "quantity": "",
                "reason": suppressed.reason,
                "active_shadow_opportunity_id": suppressed.active_shadow_opportunity_id or "",
            }
        )
    return sorted(
        rows,
        key=lambda row: (
            row["timestamp"],
            row["shadow_opportunity_id"],
            row["event_type"],
        ),
    )


def _markdown(report: ShadowReplayReport) -> str:
    closed = [item for item in report.opportunities if item.status == "closed"]
    open_items = [item for item in report.opportunities if item.status == "open"]
    unresolved = [item for item in report.opportunities if item.status == "unresolved"]
    winners = [item for item in closed if (item.net_pnl or Decimal("0")) > 0]
    realized = sum(
        (item.net_pnl or Decimal("0"))
        for item in closed
    )
    open_mtm = sum(
        (item.mark_to_market_net_pnl or Decimal("0"))
        for item in open_items
    )
    win_rate = (
        Decimal(len(winners)) / Decimal(len(closed)) * Decimal("100")
        if closed
        else Decimal("0")
    )
    add_on_count = sum(item.add_on_count for item in report.opportunities)
    skipped_add_on_count = sum(item.skipped_add_on_count for item in report.opportunities)
    base_count = sum(1 for item in report.opportunities if item.base_quantity is not None)
    daily_repeat_count = sum(
        1 for item in report.suppressed if item.reason == "daily_repeat_base"
    )
    suppressed_count = len(report.suppressed) + len(report.overlaps)

    sequence_pnl: dict[int, Decimal] = defaultdict(lambda: Decimal("0"))
    reason_pnl: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    reason_count: dict[str, int] = defaultdict(int)
    week_pnl: dict[str, Decimal] = defaultdict(lambda: Decimal("0"))
    for item in closed:
        sequence_pnl[item.base_signal_sequence] += item.net_pnl or Decimal("0")
        reason = item.blocked_reason or "unknown"
        reason_count[reason] += 1
        reason_pnl[reason] += item.net_pnl or Decimal("0")
        iso_year, iso_week, _ = item.base_signal_at.isocalendar()
        week_pnl[f"{iso_year}-W{iso_week:02d}"] += item.net_pnl or Decimal("0")

    ordered_closed = sorted(
        closed,
        key=lambda item: item.net_pnl or Decimal("0"),
        reverse=True,
    )
    warnings = sorted(
        {
            *report.warnings,
            *(
                warning
                for item in report.opportunities
                for warning in item.warnings
            ),
        }
    )
    lines = [
        "# Skipped Base Shadow Replay",
        "",
        f"- Replay mode: {report.replay_mode}",
        f"- Seed count: {report.seed_count}",
        f"- Accepted Base opportunities: {len(report.opportunities)}",
        f"- Position overlap count: {len(report.overlaps)}",
        f"- Daily repeat Base count: {daily_repeat_count}",
        f"- Suppressed seed count: {suppressed_count}",
        f"- Closed / open / unresolved: {len(closed)} / {len(open_items)} / {len(unresolved)}",
        f"- Realized net PnL: {realized}",
        f"- Open mark-to-market net PnL: {open_mtm}",
        f"- Base / add-on / skipped add-on count: {base_count} / {add_on_count} / {skipped_add_on_count}",
        f"- Win rate: {win_rate:.2f}%",
        "",
        "## Top winners",
    ]
    lines.extend(
        f"- {item.shadow_opportunity_id} {item.symbol}: {item.net_pnl}"
        for item in ordered_closed[:5]
        if item.net_pnl is not None and item.net_pnl > 0
    )
    if not any(item.net_pnl is not None and item.net_pnl > 0 for item in ordered_closed):
        lines.append("- None")

    lines.extend(["", "## Top losers"])
    losers = [
        item
        for item in reversed(ordered_closed)
        if item.net_pnl is not None and item.net_pnl <= 0
    ]
    lines.extend(
        f"- {item.shadow_opportunity_id} {item.symbol}: {item.net_pnl}"
        for item in losers[:5]
    )
    if not losers:
        lines.append("- None")

    lines.extend(["", "## PnL by base signal sequence"])
    lines.extend(
        f"- Sequence {sequence}: {pnl}"
        for sequence, pnl in sorted(sequence_pnl.items())
    )
    if not sequence_pnl:
        lines.append("- None")

    lines.extend(["", "## PnL by blocked reason"])
    lines.extend(
        f"- {reason}: count={reason_count[reason]} pnl={pnl}"
        for reason, pnl in sorted(reason_pnl.items())
    )
    if not reason_pnl:
        lines.append("- None")

    lines.extend(["", "## PnL by ISO week"])
    lines.extend(
        f"- {week}: {pnl}"
        for week, pnl in sorted(week_pnl.items())
    )
    if not week_pnl:
        lines.append("- None")

    lines.extend(["", "## Warnings"])
    lines.extend(f"- {warning}" for warning in warnings)
    if not warnings:
        lines.append("- None")
    lines.append("")
    return "\n".join(lines)


def write_replay_artifacts(
    *,
    report: ShadowReplayReport,
    output_dir: Path,
) -> dict[str, Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    paths = {
        "summary_csv": output_dir / "skipped_base_replay_summary.csv",
        "legs_csv": output_dir / "skipped_base_replay_legs.csv",
        "events_csv": output_dir / "skipped_base_replay_events.csv",
        "summary_md": output_dir / "summary.md",
    }
    _write_csv(
        path=paths["summary_csv"],
        fields=SUMMARY_FIELDS,
        rows=_summary_rows(report),
    )
    _write_csv(
        path=paths["legs_csv"],
        fields=LEG_FIELDS,
        rows=_leg_rows(report),
    )
    _write_csv(
        path=paths["events_csv"],
        fields=EVENT_FIELDS,
        rows=_event_rows(report),
    )
    paths["summary_md"].write_text(_markdown(report), encoding="utf-8")
    return paths
