from __future__ import annotations

import csv
import json
import sqlite3
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from decimal import Decimal, InvalidOperation
from pathlib import Path
from statistics import median

from momentum_alpha.analytics_schema import connect_leader_candidates_db
from momentum_alpha.runtime_schema import _connect


_CSV_COLUMNS = [
    "run_id",
    "symbol",
    "run_start",
    "run_end",
    "run_minutes",
    "snapshot_count",
    "start_daily_change_pct",
    "peak_daily_change_pct",
    "peak_timestamp",
    "leader_gap_pct_start",
    "trade_status",
    "signal_decision_id",
    "decision_type",
    "matched_round_trip_id",
    "entered_at",
    "exit_at",
    "entry_price",
    "exit_price",
    "realized_pnl",
    "net_pnl",
    "peak_return_pct",
    "realized_return_pct",
    "capture_rate",
    "miss_reason",
    "notes",
]


@dataclass(frozen=True)
class OpportunityDiagnosticsReport:
    rows: list[dict]
    warnings: list[str]
    total_runs: int
    captured_runs: int
    missed_runs: int
    open_at_cutoff_runs: int
    median_entry_delay_minutes: Decimal | None
    average_capture_rate: Decimal | None
    matched_net_pnl: Decimal | None
    miss_reason_counts: list[tuple[str, int]]

    def summary_lines(self) -> list[str]:
        lines = [
            f"total_leader_runs={self.total_runs}",
            f"captured_runs={self.captured_runs}",
            f"missed_runs={self.missed_runs}",
            f"open_at_cutoff_runs={self.open_at_cutoff_runs}",
        ]
        if self.median_entry_delay_minutes is not None:
            lines.append(f"median_entry_delay_minutes={_decimal_text(self.median_entry_delay_minutes)}")
        if self.average_capture_rate is not None:
            lines.append(f"average_capture_rate={_decimal_text(self.average_capture_rate)}")
        if self.matched_net_pnl is not None:
            lines.append(f"matched_net_pnl={_decimal_text(self.matched_net_pnl)}")
        for reason, count in self.miss_reason_counts:
            lines.append(f"miss_reason {reason} count={count}")
        return lines


@dataclass(frozen=True)
class _LeaderCandidateRow:
    timestamp: datetime
    source: str | None
    symbol: str
    rank: int
    daily_open_price: Decimal | None
    latest_price: Decimal | None
    daily_change_pct: Decimal | None
    previous_hour_low: Decimal | None
    current_hour_low: Decimal | None
    leader_gap_pct: Decimal | None
    payload: dict


@dataclass(frozen=True)
class _SignalDecisionRow:
    timestamp: datetime
    source: str | None
    decision_id: str | None
    intent_id: str | None
    decision_type: str | None
    symbol: str | None
    previous_leader_symbol: str | None
    next_leader_symbol: str | None
    payload: dict


@dataclass(frozen=True)
class _PositionSnapshotRow:
    timestamp: datetime
    source: str | None
    leader_symbol: str | None
    decision_id: str | None
    intent_id: str | None
    position_count: int | None
    order_status_count: int | None
    symbol_count: int | None
    submit_orders: bool | None
    restore_positions: bool | None
    execute_stop_replacements: bool | None
    payload: dict


@dataclass(frozen=True)
class _TradeRoundTripRow:
    round_trip_id: str
    symbol: str
    opened_at: datetime
    closed_at: datetime
    entry_fill_count: int
    exit_fill_count: int
    total_entry_quantity: Decimal | None
    total_exit_quantity: Decimal | None
    weighted_avg_entry_price: Decimal | None
    weighted_avg_exit_price: Decimal | None
    realized_pnl: Decimal | None
    commission: Decimal | None
    net_pnl: Decimal | None
    exit_reason: str | None
    duration_seconds: int | None
    payload: dict


def _json_loads(value: str | None) -> dict:
    if not value:
        return {}
    try:
        loaded = json.loads(value)
    except json.JSONDecodeError:
        return {}
    return loaded if isinstance(loaded, dict) else {}


def _datetime_from_iso(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _datetime_to_iso(value: datetime) -> str:
    return value.astimezone(timezone.utc).isoformat()


def _decimal_from_value(value: object | None) -> Decimal | None:
    if value in (None, ""):
        return None
    try:
        return Decimal(str(value))
    except (InvalidOperation, ValueError, TypeError):
        return None


def _decimal_text(value: Decimal | None) -> str:
    if value is None:
        return ""
    normalized = value.normalize()
    if normalized == normalized.to_integral():
        return str(normalized.quantize(Decimal("1")))
    return format(normalized, "f")


def _optional_text(value: object | None) -> str:
    if value in (None, ""):
        return ""
    return str(value)


def _optional_bool(value: object | None) -> bool | None:
    if value is None:
        return None
    return bool(value)


def _load_candidate_rows(*, path: Path) -> list[_LeaderCandidateRow]:
    if not path.exists():
        return []
    with connect_leader_candidates_db(path) as connection:
        try:
            rows = connection.execute(
                """
                SELECT
                    timestamp,
                    source,
                    symbol,
                    rank,
                    daily_open_price,
                    latest_price,
                    daily_change_pct,
                    previous_hour_low,
                    current_hour_low,
                    leader_gap_pct,
                    payload_json
                FROM leader_candidate_snapshots
                WHERE rank = 1
                ORDER BY timestamp ASC, id ASC
                """
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    parsed_rows: list[_LeaderCandidateRow] = []
    for row in rows:
        symbol = row[2]
        timestamp_text = row[0]
        if symbol in (None, "") or timestamp_text in (None, ""):
            continue
        try:
            timestamp = _datetime_from_iso(str(timestamp_text))
        except ValueError:
            continue
        parsed_rows.append(
            _LeaderCandidateRow(
                timestamp=timestamp,
                source=row[1],
                symbol=str(symbol).upper(),
                rank=int(row[3]),
                daily_open_price=_decimal_from_value(row[4]),
                latest_price=_decimal_from_value(row[5]),
                daily_change_pct=_decimal_from_value(row[6]),
                previous_hour_low=_decimal_from_value(row[7]),
                current_hour_low=_decimal_from_value(row[8]),
                leader_gap_pct=_decimal_from_value(row[9]),
                payload=_json_loads(row[10]),
            )
        )
    return parsed_rows


def _load_signal_decisions(*, path: Path, window_start: datetime, window_end: datetime) -> list[_SignalDecisionRow]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        try:
            rows = connection.execute(
                """
                SELECT
                    timestamp,
                    source,
                    decision_id,
                    intent_id,
                    decision_type,
                    symbol,
                    previous_leader_symbol,
                    next_leader_symbol,
                    payload_json
                FROM signal_decisions
                WHERE timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC, id ASC
                """,
                (_datetime_to_iso(window_start), _datetime_to_iso(window_end)),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    parsed_rows: list[_SignalDecisionRow] = []
    for row in rows:
        timestamp_text = row[0]
        if timestamp_text in (None, ""):
            continue
        try:
            timestamp = _datetime_from_iso(str(timestamp_text))
        except ValueError:
            continue
        parsed_rows.append(
            _SignalDecisionRow(
                timestamp=timestamp,
                source=row[1],
                decision_id=row[2],
                intent_id=row[3],
                decision_type=row[4],
                symbol=row[5],
                previous_leader_symbol=row[6],
                next_leader_symbol=row[7],
                payload=_json_loads(row[8]),
            )
        )
    return parsed_rows


def _load_position_snapshots(*, path: Path, window_start: datetime, window_end: datetime) -> list[_PositionSnapshotRow]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        try:
            rows = connection.execute(
                """
                SELECT
                    timestamp,
                    source,
                    leader_symbol,
                    decision_id,
                    intent_id,
                    position_count,
                    order_status_count,
                    symbol_count,
                    submit_orders,
                    restore_positions,
                    execute_stop_replacements,
                    payload_json
                FROM position_snapshots
                WHERE timestamp >= ? AND timestamp < ?
                ORDER BY timestamp ASC, id ASC
                """,
                (_datetime_to_iso(window_start), _datetime_to_iso(window_end)),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    parsed_rows: list[_PositionSnapshotRow] = []
    for row in rows:
        timestamp_text = row[0]
        if timestamp_text in (None, ""):
            continue
        try:
            timestamp = _datetime_from_iso(str(timestamp_text))
        except ValueError:
            continue
        parsed_rows.append(
            _PositionSnapshotRow(
                timestamp=timestamp,
                source=row[1],
                leader_symbol=row[2],
                decision_id=row[3],
                intent_id=row[4],
                position_count=row[5],
                order_status_count=row[6],
                symbol_count=row[7],
                submit_orders=_optional_bool(row[8]),
                restore_positions=_optional_bool(row[9]),
                execute_stop_replacements=_optional_bool(row[10]),
                payload=_json_loads(row[11]),
            )
        )
    return parsed_rows


def _load_trade_round_trips(*, path: Path, window_start: datetime, window_end: datetime) -> list[_TradeRoundTripRow]:
    if not path.exists():
        return []
    with _connect(path) as connection:
        try:
            rows = connection.execute(
                """
                SELECT
                    round_trip_id,
                    symbol,
                    opened_at,
                    closed_at,
                    entry_fill_count,
                    exit_fill_count,
                    total_entry_quantity,
                    total_exit_quantity,
                    weighted_avg_entry_price,
                    weighted_avg_exit_price,
                    realized_pnl,
                    commission,
                    net_pnl,
                    exit_reason,
                    duration_seconds,
                    payload_json
                FROM trade_round_trips
                WHERE closed_at >= ? AND closed_at < ?
                ORDER BY closed_at ASC, id ASC
                """,
                (_datetime_to_iso(window_start), _datetime_to_iso(window_end)),
            ).fetchall()
        except sqlite3.OperationalError:
            return []
    parsed_rows: list[_TradeRoundTripRow] = []
    for row in rows:
        try:
            opened_at = _datetime_from_iso(str(row[2]))
            closed_at = _datetime_from_iso(str(row[3]))
        except (TypeError, ValueError):
            continue
        symbol = row[1]
        round_trip_id = row[0]
        if symbol in (None, "") or round_trip_id in (None, ""):
            continue
        parsed_rows.append(
            _TradeRoundTripRow(
                round_trip_id=str(round_trip_id),
                symbol=str(symbol).upper(),
                opened_at=opened_at,
                closed_at=closed_at,
                entry_fill_count=int(row[4]),
                exit_fill_count=int(row[5]),
                total_entry_quantity=_decimal_from_value(row[6]),
                total_exit_quantity=_decimal_from_value(row[7]),
                weighted_avg_entry_price=_decimal_from_value(row[8]),
                weighted_avg_exit_price=_decimal_from_value(row[9]),
                realized_pnl=_decimal_from_value(row[10]),
                commission=_decimal_from_value(row[11]),
                net_pnl=_decimal_from_value(row[12]),
                exit_reason=row[13],
                duration_seconds=int(row[14]) if row[14] is not None else None,
                payload=_json_loads(row[15]),
            )
        )
    return parsed_rows


def _normalize_symbols(symbols: list[str] | tuple[str, ...] | None) -> set[str] | None:
    if symbols is None:
        return None
    normalized = {str(symbol).upper() for symbol in symbols if symbol}
    return normalized


def _filter_candidate_rows(
    *,
    rows: list[_LeaderCandidateRow],
    start_time: datetime | None,
    end_time: datetime | None,
    symbols: set[str] | None,
) -> list[_LeaderCandidateRow]:
    filtered: list[_LeaderCandidateRow] = []
    for row in rows:
        if start_time is not None and row.timestamp < start_time:
            continue
        if end_time is not None and row.timestamp >= end_time:
            continue
        if symbols is not None and row.symbol not in symbols:
            continue
        filtered.append(row)
    return filtered


def _build_runs(rows: list[_LeaderCandidateRow]) -> list[list[_LeaderCandidateRow]]:
    runs: list[list[_LeaderCandidateRow]] = []
    current: list[_LeaderCandidateRow] = []
    previous_symbol: str | None = None
    for row in rows:
        if previous_symbol is None or row.symbol == previous_symbol:
            current.append(row)
        else:
            if current:
                runs.append(current)
            current = [row]
        previous_symbol = row.symbol
    if current:
        runs.append(current)
    return runs


def _format_run_id(*, index: int, symbol: str, run_start: datetime) -> str:
    stamp = run_start.astimezone(timezone.utc).strftime("%Y%m%dT%H%M%S%fZ")
    return f"{index:04d}:{symbol}:{stamp}"


def _timedelta_minutes(value: timedelta) -> Decimal:
    return Decimal(str(value.total_seconds())) / Decimal("60")


def _overlaps(*, left_start: datetime, left_end: datetime, right_start: datetime, right_end: datetime) -> bool:
    return left_start <= right_end and right_start <= left_end


def _decision_symbol_matches(*, decision: _SignalDecisionRow, symbol: str) -> bool:
    decision_symbols = {
        str(decision.symbol).upper() if decision.symbol else None,
        str(decision.next_leader_symbol).upper() if decision.next_leader_symbol else None,
        str(decision.previous_leader_symbol).upper() if decision.previous_leader_symbol else None,
        str(decision.payload.get("symbol")).upper() if decision.payload.get("symbol") else None,
        str(decision.payload.get("next_leader_symbol")).upper() if decision.payload.get("next_leader_symbol") else None,
        str(decision.payload.get("previous_leader_symbol")).upper() if decision.payload.get("previous_leader_symbol") else None,
        str(decision.payload.get("leader_symbol")).upper() if decision.payload.get("leader_symbol") else None,
    }
    return symbol in {item for item in decision_symbols if item}


def _snapshot_symbol_matches(*, snapshot: _PositionSnapshotRow, symbol: str) -> bool:
    snapshot_symbols = {
        str(snapshot.leader_symbol).upper() if snapshot.leader_symbol else None,
        str(snapshot.payload.get("leader_symbol")).upper() if snapshot.payload.get("leader_symbol") else None,
        str(snapshot.payload.get("symbol")).upper() if snapshot.payload.get("symbol") else None,
        str(snapshot.payload.get("market_context", {}).get("leader_symbol")).upper()
        if isinstance(snapshot.payload.get("market_context"), dict) and snapshot.payload["market_context"].get("leader_symbol")
        else None,
    }
    return symbol in {item for item in snapshot_symbols if item}


def _snapshot_is_open_position(snapshot: _PositionSnapshotRow) -> bool:
    if snapshot.position_count is not None and snapshot.position_count > 0:
        return True
    positions = snapshot.payload.get("positions")
    if isinstance(positions, dict) and positions:
        return True
    if isinstance(positions, list) and positions:
        return True
    return False


def _choose_anchor_snapshot(
    *,
    snapshots: list[_PositionSnapshotRow],
    symbol: str,
    run_start: datetime,
    run_end: datetime,
) -> _PositionSnapshotRow | None:
    matching = [snapshot for snapshot in snapshots if _snapshot_symbol_matches(snapshot=snapshot, symbol=symbol)]
    if not matching:
        return None
    within_run = [snapshot for snapshot in matching if snapshot.timestamp <= run_end and snapshot.timestamp >= run_start - timedelta(hours=6)]
    if within_run:
        return max(within_run, key=lambda snapshot: snapshot.timestamp)
    return min(matching, key=lambda snapshot: snapshot.timestamp)


def _choose_signal_decision(
    *,
    decisions: list[_SignalDecisionRow],
    symbol: str,
    run_end: datetime,
    anchor_snapshot: _PositionSnapshotRow | None,
) -> _SignalDecisionRow | None:
    if anchor_snapshot is not None and anchor_snapshot.decision_id:
        for decision in decisions:
            if decision.decision_id == anchor_snapshot.decision_id:
                return decision
    matching = [decision for decision in decisions if _decision_symbol_matches(decision=decision, symbol=symbol)]
    if not matching:
        return None
    before_run_end = [decision for decision in matching if decision.timestamp <= run_end]
    if before_run_end:
        return max(before_run_end, key=lambda decision: decision.timestamp)
    return min(matching, key=lambda decision: decision.timestamp)


def _choose_matching_trade_round_trip(
    *,
    trade_round_trips: list[_TradeRoundTripRow],
    symbol: str,
    run_start: datetime,
    run_end: datetime,
) -> _TradeRoundTripRow | None:
    matching = [
        trip
        for trip in trade_round_trips
        if trip.symbol == symbol
        and trip.opened_at >= run_start
        and _overlaps(left_start=trip.opened_at, left_end=trip.closed_at, right_start=run_start, right_end=run_end)
    ]
    if not matching:
        return None
    return min(matching, key=lambda trip: (trip.opened_at, trip.closed_at, trip.round_trip_id))


def _summarize_report_rows(rows: list[dict]) -> tuple[int, int, int, int, Decimal | None, Decimal | None, Decimal | None, list[tuple[str, int]]]:
    total_runs = len(rows)
    captured_rows = [row for row in rows if row["trade_status"] == "matched_closed_round_trip"]
    open_rows = [row for row in rows if row["trade_status"] == "open_at_cutoff"]
    missed_rows = [row for row in rows if row["trade_status"] in {"missed", "unresolved"}]

    entry_delays = [
        _decimal_from_value(row["entry_delay_minutes"])
        for row in captured_rows
        if _decimal_from_value(row["entry_delay_minutes"]) is not None
    ]
    capture_rates = [
        _decimal_from_value(row["capture_rate"])
        for row in captured_rows
        if _decimal_from_value(row["capture_rate"]) is not None
    ]
    net_pnls = [
        _decimal_from_value(row["net_pnl"])
        for row in captured_rows
        if _decimal_from_value(row["net_pnl"]) is not None
    ]
    miss_reason_counter = Counter(
        row["miss_reason"] for row in rows if row["miss_reason"] not in ("", None)
    )

    return (
        total_runs,
        len(captured_rows),
        len(missed_rows),
        len(open_rows),
        median(entry_delays) if entry_delays else None,
        (sum(capture_rates) / Decimal(len(capture_rates))) if capture_rates else None,
        sum(net_pnls, Decimal("0")) if net_pnls else None,
        sorted(miss_reason_counter.items(), key=lambda item: (-item[1], item[0])),
    )


def _build_row_for_run(
    *,
    index: int,
    run_rows: list[_LeaderCandidateRow],
    signal_decisions: list[_SignalDecisionRow],
    position_snapshots: list[_PositionSnapshotRow],
    trade_round_trips: list[_TradeRoundTripRow],
) -> dict:
    run_symbol = run_rows[0].symbol
    run_start = run_rows[0].timestamp
    run_end = run_rows[-1].timestamp
    peak_row = max(
        run_rows,
        key=lambda row: (
            row.daily_change_pct if row.daily_change_pct is not None else Decimal("-Infinity"),
            row.timestamp,
        ),
    )
    anchor_snapshot = _choose_anchor_snapshot(
        snapshots=position_snapshots,
        symbol=run_symbol,
        run_start=run_start,
        run_end=run_end,
    )
    decision = _choose_signal_decision(
        decisions=signal_decisions,
        symbol=run_symbol,
        run_end=run_end,
        anchor_snapshot=anchor_snapshot,
    )
    matched_trade = _choose_matching_trade_round_trip(
        trade_round_trips=trade_round_trips,
        symbol=run_symbol,
        run_start=run_start,
        run_end=run_end,
    )

    trade_status = "unresolved"
    if matched_trade is not None:
        trade_status = "matched_closed_round_trip"
    elif anchor_snapshot is not None and _snapshot_is_open_position(anchor_snapshot):
        trade_status = "open_at_cutoff"
    elif decision is not None:
        trade_status = "missed"

    blocked_reason = ""
    if trade_status != "matched_closed_round_trip":
        if decision is not None:
            blocked_reason = decision.payload.get("blocked_reason") or decision.payload.get("blockedReason") or ""
            if blocked_reason in (None, ""):
                blocked_reason = decision.payload.get("reason") or ""
        if blocked_reason in (None, "") and decision is not None:
            blocked_reason = decision.decision_type or ""
        if blocked_reason in (None, "") and trade_status == "open_at_cutoff":
            blocked_reason = "open_at_cutoff"
        if blocked_reason in (None, ""):
            blocked_reason = "no_matching_signal"

    entry_delay_minutes: Decimal | None = None
    entry_price = None
    exit_price = None
    realized_pnl = None
    net_pnl = None
    peak_return_pct = None
    realized_return_pct = None
    capture_rate = None
    matched_round_trip_id = ""
    entered_at = ""
    exit_at = ""
    notes = ""

    if matched_trade is not None:
        matched_round_trip_id = matched_trade.round_trip_id
        entered_at = _datetime_to_iso(matched_trade.opened_at)
        exit_at = _datetime_to_iso(matched_trade.closed_at)
        entry_price = matched_trade.weighted_avg_entry_price
        exit_price = matched_trade.weighted_avg_exit_price
        realized_pnl = matched_trade.realized_pnl
        net_pnl = matched_trade.net_pnl
        notes = "matched_closed_round_trip"
        if entry_price is not None and peak_row.latest_price is not None and entry_price > 0:
            peak_return_pct = (peak_row.latest_price - entry_price) / entry_price
        if entry_price is not None and exit_price is not None and entry_price > 0:
            realized_return_pct = (exit_price - entry_price) / entry_price
        if peak_return_pct is not None and peak_return_pct > 0 and realized_return_pct is not None:
            capture_rate = realized_return_pct / peak_return_pct
        if run_start is not None and matched_trade.opened_at is not None:
            entry_delay_minutes = _timedelta_minutes(matched_trade.opened_at - run_start)
    elif trade_status == "open_at_cutoff":
        notes = "open_position_at_cutoff"
    elif decision is not None:
        notes = "missed_without_closed_trade"
    else:
        notes = "no_matching_signal_or_trade"

    return {
        "run_id": _format_run_id(index=index, symbol=run_symbol, run_start=run_start),
        "symbol": run_symbol,
        "run_start": _datetime_to_iso(run_start),
        "run_end": _datetime_to_iso(run_end),
        "run_minutes": _decimal_text(_timedelta_minutes(run_end - run_start)),
        "snapshot_count": str(len(run_rows)),
        "start_daily_change_pct": _decimal_text(run_rows[0].daily_change_pct),
        "peak_daily_change_pct": _decimal_text(peak_row.daily_change_pct),
        "peak_timestamp": _datetime_to_iso(peak_row.timestamp),
        "leader_gap_pct_start": _decimal_text(run_rows[0].leader_gap_pct),
        "trade_status": trade_status,
        "signal_decision_id": (decision.decision_id or "") if decision is not None else "",
        "decision_type": (decision.decision_type or "") if decision is not None else "",
        "matched_round_trip_id": matched_round_trip_id,
        "entered_at": entered_at,
        "exit_at": exit_at,
        "entry_price": _decimal_text(entry_price),
        "exit_price": _decimal_text(exit_price),
        "realized_pnl": _decimal_text(realized_pnl),
        "net_pnl": _decimal_text(net_pnl),
        "peak_return_pct": _decimal_text(peak_return_pct),
        "realized_return_pct": _decimal_text(realized_return_pct),
        "capture_rate": _decimal_text(capture_rate),
        "miss_reason": blocked_reason or "",
        "notes": notes,
        "entry_delay_minutes": _decimal_text(entry_delay_minutes),
    }


def build_leader_opportunity_diagnostics(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    min_peak_change_pct: Decimal = Decimal("0"),
) -> OpportunityDiagnosticsReport:
    if not runtime_db_path.exists():
        raise FileNotFoundError(f"runtime DB missing: {runtime_db_path}")

    warnings: list[str] = []
    candidate_rows = _load_candidate_rows(path=leader_candidates_db_path)
    if not candidate_rows:
        warnings.append(f"leader-opportunity-diagnostics no_leader_candidates path={leader_candidates_db_path}")
        return OpportunityDiagnosticsReport(
            rows=[],
            warnings=warnings,
            total_runs=0,
            captured_runs=0,
            missed_runs=0,
            open_at_cutoff_runs=0,
            median_entry_delay_minutes=None,
            average_capture_rate=None,
            matched_net_pnl=None,
            miss_reason_counts=[],
        )

    start_time_utc = start_time.astimezone(timezone.utc) if start_time is not None else None
    end_time_utc = end_time.astimezone(timezone.utc) if end_time is not None else None
    normalized_symbols = _normalize_symbols(symbols)
    filtered_rows = _filter_candidate_rows(
        rows=candidate_rows,
        start_time=start_time_utc,
        end_time=end_time_utc,
        symbols=normalized_symbols,
    )
    if not filtered_rows:
        warnings.append("leader-opportunity-diagnostics no_candidate_rows_after_filtering")
        return OpportunityDiagnosticsReport(
            rows=[],
            warnings=warnings,
            total_runs=0,
            captured_runs=0,
            missed_runs=0,
            open_at_cutoff_runs=0,
            median_entry_delay_minutes=None,
            average_capture_rate=None,
            matched_net_pnl=None,
            miss_reason_counts=[],
        )

    analysis_start = start_time_utc or filtered_rows[0].timestamp
    analysis_end = end_time_utc or (filtered_rows[-1].timestamp + timedelta(microseconds=1))
    runtime_window_start = analysis_start - timedelta(hours=6)
    runtime_window_end = analysis_end + timedelta(days=1)

    signal_decisions = _load_signal_decisions(
        path=runtime_db_path,
        window_start=runtime_window_start,
        window_end=runtime_window_end,
    )
    position_snapshots = _load_position_snapshots(
        path=runtime_db_path,
        window_start=runtime_window_start,
        window_end=runtime_window_end,
    )
    trade_round_trips = _load_trade_round_trips(
        path=runtime_db_path,
        window_start=runtime_window_start,
        window_end=runtime_window_end,
    )

    report_rows: list[dict] = []
    for index, run_rows in enumerate(_build_runs(filtered_rows), start=1):
        peak_row = max(
            run_rows,
            key=lambda row: (
                row.daily_change_pct if row.daily_change_pct is not None else Decimal("-Infinity"),
                row.timestamp,
            ),
        )
        if peak_row.daily_change_pct is not None and peak_row.daily_change_pct < min_peak_change_pct:
            continue
        report_rows.append(
            _build_row_for_run(
                index=index,
                run_rows=run_rows,
                signal_decisions=signal_decisions,
                position_snapshots=position_snapshots,
                trade_round_trips=trade_round_trips,
            )
        )

    total_runs, captured_runs, missed_runs, open_at_cutoff_runs, median_entry_delay, average_capture_rate, matched_net_pnl, miss_reason_counts = _summarize_report_rows(
        report_rows
    )
    return OpportunityDiagnosticsReport(
        rows=report_rows,
        warnings=warnings,
        total_runs=total_runs,
        captured_runs=captured_runs,
        missed_runs=missed_runs,
        open_at_cutoff_runs=open_at_cutoff_runs,
        median_entry_delay_minutes=median_entry_delay,
        average_capture_rate=average_capture_rate,
        matched_net_pnl=matched_net_pnl,
        miss_reason_counts=miss_reason_counts,
    )


def write_opportunity_diagnostics_csv(*, path: Path, rows: list[dict]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=_CSV_COLUMNS)
        writer.writeheader()
        for row in rows:
            writer.writerow({column: row.get(column, "") for column in _CSV_COLUMNS})


def diagnose_opportunities(
    *,
    runtime_db_path: Path,
    leader_candidates_db_path: Path,
    output_file: Path,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | tuple[str, ...] | None = None,
    min_peak_change_pct: Decimal = Decimal("0"),
    logger=print,
) -> OpportunityDiagnosticsReport:
    report = build_leader_opportunity_diagnostics(
        runtime_db_path=runtime_db_path,
        leader_candidates_db_path=leader_candidates_db_path,
        start_time=start_time,
        end_time=end_time,
        symbols=symbols,
        min_peak_change_pct=min_peak_change_pct,
    )
    write_opportunity_diagnostics_csv(path=output_file, rows=report.rows)
    for warning in report.warnings:
        logger(warning)
    for line in report.summary_lines():
        logger(line)
    logger(f"opportunity_rows={len(report.rows)}")
    return report
