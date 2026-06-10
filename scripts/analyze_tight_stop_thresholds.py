#!/usr/bin/env python3
"""Compare delayed base-entry stop-distance thresholds on live trade data."""

from __future__ import annotations

import argparse
import csv
import json
import math
import sqlite3
import subprocess
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal, ROUND_DOWN
from pathlib import Path
from statistics import median


THRESHOLDS = (3.0, 4.0, 5.0, 6.0)
TAKER_FEE_RATE = Decimal("0.0005")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("var/runtime.db"))
    parser.add_argument("--output-dir", type=Path, default=Path("var/analysis/tight_stop_20260609"))
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--fetch", action="store_true")
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def floor_minute(value: datetime) -> datetime:
    return value.replace(second=0, microsecond=0)


def daterange(start: datetime, end: datetime):
    current = start.date()
    while current <= end.date():
        yield current.isoformat()
        current += timedelta(days=1)


def load_data(db_path: Path) -> tuple[list[dict], list[dict], dict[datetime, str]]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    cursor = connection.cursor()

    decisions_by_symbol: dict[str, list[dict]] = defaultdict(list)
    leader_by_minute: dict[datetime, str] = {}
    for row in cursor.execute(
        """
        SELECT id, timestamp, decision_type, symbol, next_leader_symbol,
               payload_json, decision_id, intent_id
        FROM signal_decisions NOT INDEXED
        ORDER BY id
        """
    ):
        row_id, timestamp, decision_type, symbol, next_leader, payload_json, decision_id, intent_id = row
        event_time = parse_time(timestamp)
        if next_leader:
            leader_by_minute[floor_minute(event_time)] = next_leader
        if decision_type != "base_entry":
            continue
        payload = json.loads(payload_json)
        decisions_by_symbol[symbol].append(
            {
                "id": row_id,
                "timestamp": timestamp,
                "time": event_time,
                "symbol": symbol,
                "payload": payload,
                "decision_id": decision_id,
                "intent_id": intent_id,
            }
        )

    matched: list[dict] = []
    unmatched: list[dict] = []
    for row in cursor.execute(
        """
        SELECT id, round_trip_id, symbol, opened_at, closed_at, net_pnl,
               weighted_avg_exit_price, commission, exit_reason, payload_json
        FROM trade_round_trips NOT INDEXED
        ORDER BY opened_at
        """
    ):
        (
            row_id,
            round_trip_id,
            symbol,
            opened_at,
            closed_at,
            net_pnl,
            exit_price,
            commission,
            exit_reason,
            payload_json,
        ) = row
        payload = json.loads(payload_json)
        base_leg = next((leg for leg in payload.get("legs", []) if leg.get("leg_type") == "base"), None)
        base_opened_at = parse_time(base_leg["opened_at"] if base_leg else opened_at)
        candidates = []
        for decision in decisions_by_symbol.get(symbol, []):
            difference = (base_opened_at - decision["time"]).total_seconds()
            if -5 <= difference <= 300:
                candidates.append((abs(difference), difference, decision))

        trade = {
            "id": row_id,
            "round_trip_id": round_trip_id,
            "symbol": symbol,
            "opened_at": opened_at,
            "opened_time": parse_time(opened_at),
            "closed_at": closed_at,
            "closed_time": parse_time(closed_at),
            "net_pnl": float(net_pnl or 0),
            "exit_price": Decimal(exit_price),
            "commission": float(commission or 0),
            "exit_reason": exit_reason,
            "payload": payload,
            "base_leg": base_leg,
        }
        if not candidates:
            unmatched.append(trade)
            continue

        _, match_difference, decision = min(candidates, key=lambda item: item[0])
        latest_price = Decimal(decision["payload"]["latest_price"])
        stop_price = Decimal(decision["payload"]["stop_price"])
        stop_distance_pct = float((latest_price - stop_price) / latest_price * Decimal("100"))
        trade.update(
            {
                "decision": decision,
                "match_difference_seconds": match_difference,
                "signal_time": decision["time"],
                "signal_at": decision["timestamp"],
                "signal_price": latest_price,
                "signal_stop": stop_price,
                "stop_distance_pct": stop_distance_pct,
            }
        )
        matched.append(trade)

    connection.close()
    return matched, unmatched, leader_by_minute


def fetch_day(symbol: str, day: str, proxy: str) -> list:
    day_start = datetime.fromisoformat(f"{day}T00:00:00+00:00")
    start_time = int(day_start.timestamp() * 1000)
    end_time = int((day_start + timedelta(days=1)).timestamp() * 1000 - 1)
    url = (
        "https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval=1m&startTime={start_time}"
        f"&endTime={end_time}&limit=1440"
    )
    last_error: Exception | None = None
    for attempt in range(6):
        try:
            result = subprocess.run(
                [
                    "curl",
                    "--fail",
                    "--silent",
                    "--show-error",
                    "--max-time",
                    "30",
                    "--proxy",
                    proxy,
                    url,
                ],
                check=True,
                capture_output=True,
                text=True,
            )
            data = json.loads(result.stdout)
            if isinstance(data, list) and data:
                return data
            raise RuntimeError(f"unexpected Binance response: {str(data)[:200]}")
        except Exception as error:
            last_error = error
            time.sleep(1 + attempt * 0.5)
    raise RuntimeError(f"failed to fetch {symbol} {day}: {last_error}")


def load_kline_cache(
    *,
    trades: list[dict],
    cache_path: Path,
    fetch: bool,
    proxy: str,
) -> dict[str, list]:
    cache: dict[str, list] = {}
    if cache_path.exists():
        cache = json.loads(cache_path.read_text())

    required = set()
    for trade in trades:
        if trade["stop_distance_pct"] >= max(THRESHOLDS):
            continue
        for day in daterange(trade["signal_time"], trade["closed_time"]):
            required.add(f"{trade['symbol']}:{day}")

    missing = sorted(required - cache.keys())
    if missing and not fetch:
        raise RuntimeError(
            f"{len(missing)} symbol-days missing from {cache_path}; rerun with --fetch"
        )

    failures: list[str] = []
    completed = 0

    def fetch_key(key: str) -> tuple[str, list]:
        symbol, day = key.split(":", 1)
        return key, fetch_day(symbol, day, proxy)

    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {executor.submit(fetch_key, key): key for key in missing}
        for index, future in enumerate(as_completed(futures), start=1):
            key = futures[future]
            try:
                fetched_key, data = future.result()
                cache[fetched_key] = data
                completed += 1
            except RuntimeError as error:
                failures.append(key)
                print(str(error), flush=True)
            if completed % 10 == 0 or index == len(missing):
                print(
                    f"processed {index}/{len(missing)} symbol-days; "
                    f"fetched={completed}, failed={len(failures)}",
                    flush=True,
                )
                cache_path.write_text(json.dumps(cache))
                time.sleep(0.15)
    if missing:
        cache_path.write_text(json.dumps(cache))
    if failures:
        raise RuntimeError(
            f"{len(failures)} symbol-days still missing; rerun with --fetch: "
            + ", ".join(failures[:10])
        )
    return cache


def build_market_index(cache: dict[str, list]) -> dict[str, dict[int, tuple[Decimal, Decimal]]]:
    by_symbol: dict[str, dict[int, tuple[Decimal, Decimal]]] = defaultdict(dict)
    for key, klines in cache.items():
        symbol, _ = key.split(":", 1)
        for kline in klines:
            minute = int(kline[0] // 60000)
            by_symbol[symbol][minute] = (Decimal(kline[3]), Decimal(kline[4]))
    return by_symbol


def market_at_poll(
    symbol: str,
    poll_time: datetime,
    market_index: dict[str, dict[int, tuple[Decimal, Decimal]]],
) -> tuple[Decimal, Decimal, float] | None:
    """Return latest, entry stop, and distance using only completed 1m candles."""
    if poll_time.hour < 1:
        return None
    minute = int(floor_minute(poll_time).timestamp() // 60)
    symbol_index = market_index.get(symbol, {})
    previous_candle = symbol_index.get(minute - 1)
    if previous_candle is None:
        return None
    latest_price = previous_candle[1]

    hour_start = floor_minute(poll_time).replace(minute=0)
    current_start_minute = int(hour_start.timestamp() // 60)
    previous_start_minute = current_start_minute - 60
    previous_lows = [
        symbol_index[item][0]
        for item in range(previous_start_minute, current_start_minute)
        if item in symbol_index
    ]
    if len(previous_lows) < 55:
        return None
    current_lows = [
        symbol_index[item][0]
        for item in range(current_start_minute, minute)
        if item in symbol_index
    ]
    previous_hour_low = min(previous_lows)
    current_hour_low = min(current_lows) if current_lows else latest_price
    stop_price = current_hour_low if latest_price < previous_hour_low else previous_hour_low
    if stop_price >= latest_price:
        return None
    distance = float((latest_price - stop_price) / latest_price * Decimal("100"))
    return latest_price, stop_price, distance


def find_recapture(
    *,
    trade: dict,
    threshold: float,
    leader_events: list[tuple[datetime, str]],
    market_index: dict[str, dict[int, tuple[Decimal, Decimal]]],
    same_segment_only: bool,
) -> dict:
    symbol = trade["symbol"]
    signal_minute = floor_minute(trade["signal_time"])
    closed_minute = floor_minute(trade["closed_time"])
    started = False
    for event_time, leader in leader_events:
        if event_time < signal_minute:
            continue
        if event_time > closed_minute:
            break
        if not started:
            started = True
            if leader != symbol:
                return {"recaptured": False}
        if same_segment_only and leader != symbol:
            return {"recaptured": False}
        if leader != symbol or event_time <= signal_minute:
            continue
        market = market_at_poll(symbol, event_time, market_index)
        if market is None:
            continue
        latest_price, stop_price, distance = market
        if distance >= threshold:
            return {
                "recaptured": True,
                "hit_time": event_time,
                "hit_price": latest_price,
                "hit_stop": stop_price,
                "hit_distance_pct": distance,
                "delay_minutes": (event_time - trade["signal_time"]).total_seconds() / 60,
            }
    return {"recaptured": False}


def floor_to_step(quantity: Decimal, step_size: Decimal) -> Decimal:
    if step_size <= 0:
        return quantity
    steps = (quantity / step_size).to_integral_value(rounding=ROUND_DOWN)
    return steps * step_size


def estimate_delayed_pnl(trade: dict, recapture: dict) -> dict:
    base_leg = trade["base_leg"] or {}
    risk_value = base_leg.get("leg_risk") or trade["payload"].get("base_leg_risk")
    if not risk_value:
        return {"available": False}
    risk_budget = Decimal(risk_value)
    entry_price = recapture["hit_price"]
    stop_price = recapture["hit_stop"]
    risk_per_unit = entry_price - stop_price
    if risk_budget <= 0 or risk_per_unit <= 0:
        return {"available": False}

    decision_payload = trade["decision"]["payload"]
    step_size = Decimal(decision_payload.get("step_size", "0"))
    quantity = floor_to_step(risk_budget / risk_per_unit, step_size)
    if quantity <= 0:
        return {"available": False}

    exit_price = trade["exit_price"]
    base_gross = quantity * (exit_price - entry_price)
    base_fee = quantity * (entry_price + exit_price) * TAKER_FEE_RATE
    base_net = base_gross - base_fee

    later_add_on_net = Decimal("0")
    later_add_on_count = 0
    for leg in trade["payload"].get("legs", []):
        if leg.get("leg_type") != "add_on":
            continue
        if parse_time(leg["opened_at"]) < recapture["hit_time"]:
            continue
        later_add_on_net += Decimal(leg["net_pnl_contribution"])
        later_add_on_count += 1

    return {
        "available": True,
        "quantity": quantity,
        "base_net": base_net,
        "later_add_on_net": later_add_on_net,
        "later_add_on_count": later_add_on_count,
        "total_net": base_net + later_add_on_net,
    }


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def calculate_stats(values: list[float]) -> dict:
    if not values:
        return {"count": 0, "net": 0.0, "wins": 0, "win_rate": 0.0, "median": 0.0}
    wins = sum(value > 0 for value in values)
    return {
        "count": len(values),
        "net": sum(values),
        "wins": wins,
        "win_rate": wins / len(values) * 100,
        "median": median(values),
    }


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matched, unmatched, leader_by_minute = load_data(args.db)
    baseline = sum(trade["net_pnl"] for trade in matched + unmatched)
    leader_events = sorted(leader_by_minute.items())

    cache_path = args.output_dir / "binance_1m_cache.json"
    cache = load_kline_cache(
        trades=matched,
        cache_path=cache_path,
        fetch=args.fetch,
        proxy=args.proxy,
    )
    market_index = build_market_index(cache)

    detail_rows: list[dict] = []
    summary_rows: list[dict] = []
    recent_cutoff = datetime(2026, 5, 29, tzinfo=timezone.utc)
    for threshold in THRESHOLDS:
        affected = [trade for trade in matched if trade["stop_distance_pct"] < threshold]
        unaffected = [trade for trade in matched if trade["stop_distance_pct"] >= threshold]
        original_affected_pnl = sum(trade["net_pnl"] for trade in affected)
        hard_filter_total = sum(trade["net_pnl"] for trade in unaffected + unmatched)
        estimated_total = hard_filter_total
        recaptured_original_pnl = 0.0
        estimated_affected_pnl = 0.0
        same_count = 0
        any_count = 0
        estimated_count = 0
        delays: list[float] = []
        missed_winners = 0
        missed_tail_50 = 0
        missed_tail_100 = 0
        saved_missed_losses = 0.0
        recaptured_original_base_pnl = 0.0
        recaptured_estimated_base_pnl = 0.0
        recaptured_original_add_on_pnl = 0.0
        recaptured_retained_add_on_pnl = 0.0
        counterfactual_by_round_trip: dict[str, float] = {}

        for trade in affected:
            same = find_recapture(
                trade=trade,
                threshold=threshold,
                leader_events=leader_events,
                market_index=market_index,
                same_segment_only=True,
            )
            any_top1 = find_recapture(
                trade=trade,
                threshold=threshold,
                leader_events=leader_events,
                market_index=market_index,
                same_segment_only=False,
            )
            same_count += int(same["recaptured"])
            any_count += int(any_top1["recaptured"])
            estimate = {"available": False}
            if any_top1["recaptured"]:
                recaptured_original_pnl += trade["net_pnl"]
                delays.append(any_top1["delay_minutes"])
                estimate = estimate_delayed_pnl(trade, any_top1)
                if estimate["available"]:
                    estimated_count += 1
                    estimated_value = float(estimate["total_net"])
                    estimated_affected_pnl += estimated_value
                    estimated_total += estimated_value
                    counterfactual_by_round_trip[trade["round_trip_id"]] = estimated_value
                    original_base_pnl = float(trade["base_leg"]["net_pnl_contribution"])
                    recaptured_original_base_pnl += original_base_pnl
                    recaptured_estimated_base_pnl += float(estimate["base_net"])
                    recaptured_original_add_on_pnl += trade["net_pnl"] - original_base_pnl
                    recaptured_retained_add_on_pnl += float(estimate["later_add_on_net"])
            else:
                counterfactual_by_round_trip[trade["round_trip_id"]] = 0.0
                missed_winners += int(trade["net_pnl"] > 0)
                missed_tail_50 += int(trade["net_pnl"] >= 50)
                missed_tail_100 += int(trade["net_pnl"] >= 100)
                if trade["net_pnl"] < 0:
                    saved_missed_losses += -trade["net_pnl"]

            detail_rows.append(
                {
                    "threshold_pct": threshold,
                    "round_trip_id": trade["round_trip_id"],
                    "symbol": trade["symbol"],
                    "signal_at_utc": trade["signal_at"],
                    "closed_at_utc": trade["closed_at"],
                    "original_stop_distance_pct": trade["stop_distance_pct"],
                    "original_net_pnl": trade["net_pnl"],
                    "original_add_on_count": trade["payload"].get("add_on_leg_count", 0),
                    "same_segment_recaptured": "YES" if same["recaptured"] else "NO",
                    "any_top1_recaptured": "YES" if any_top1["recaptured"] else "NO",
                    "hit_at_utc": any_top1.get("hit_time", "").isoformat()
                    if any_top1.get("hit_time")
                    else "",
                    "delay_minutes": any_top1.get("delay_minutes", ""),
                    "hit_price": str(any_top1.get("hit_price", "")),
                    "hit_stop": str(any_top1.get("hit_stop", "")),
                    "hit_distance_pct": any_top1.get("hit_distance_pct", ""),
                    "estimated_base_net_pnl": str(estimate.get("base_net", "")),
                    "retained_add_on_count": estimate.get("later_add_on_count", ""),
                    "retained_add_on_net_pnl": str(estimate.get("later_add_on_net", "")),
                    "estimated_delayed_total_pnl": str(estimate.get("total_net", "")),
                }
            )

        affected_stats = calculate_stats([trade["net_pnl"] for trade in affected])
        earlier_original = 0.0
        earlier_estimated = 0.0
        recent_original = 0.0
        recent_estimated = 0.0
        tail_50_original = 0.0
        tail_50_estimated = 0.0
        tail_100_original = 0.0
        tail_100_estimated = 0.0
        for trade in matched + unmatched:
            estimated_value = counterfactual_by_round_trip.get(
                trade["round_trip_id"], trade["net_pnl"]
            )
            if trade["opened_time"] < recent_cutoff:
                earlier_original += trade["net_pnl"]
                earlier_estimated += estimated_value
            else:
                recent_original += trade["net_pnl"]
                recent_estimated += estimated_value
            if trade["net_pnl"] >= 50:
                tail_50_original += trade["net_pnl"]
                tail_50_estimated += estimated_value
            if trade["net_pnl"] >= 100:
                tail_100_original += trade["net_pnl"]
                tail_100_estimated += estimated_value

        summary_rows.append(
            {
                "threshold_pct": threshold,
                "baseline_total_pnl": baseline,
                "affected_count": len(affected),
                "affected_original_pnl": original_affected_pnl,
                "affected_wins": affected_stats["wins"],
                "affected_tail_50": sum(trade["net_pnl"] >= 50 for trade in affected),
                "affected_tail_100": sum(trade["net_pnl"] >= 100 for trade in affected),
                "hard_filter_total_pnl": hard_filter_total,
                "hard_filter_delta": hard_filter_total - baseline,
                "same_segment_recaptured_count": same_count,
                "any_top1_recaptured_count": any_count,
                "any_top1_recaptured_original_pnl": recaptured_original_pnl,
                "estimated_count": estimated_count,
                "estimated_delayed_affected_pnl": estimated_affected_pnl,
                "estimated_strategy_total_pnl": estimated_total,
                "estimated_strategy_delta": estimated_total - baseline,
                "missed_count": len(affected) - any_count,
                "missed_winners": missed_winners,
                "missed_tail_50": missed_tail_50,
                "missed_tail_100": missed_tail_100,
                "saved_missed_losses": saved_missed_losses,
                "median_delay_minutes": median(delays) if delays else "",
                "max_delay_minutes": max(delays) if delays else "",
                "recaptured_original_base_pnl": recaptured_original_base_pnl,
                "recaptured_estimated_base_pnl": recaptured_estimated_base_pnl,
                "recaptured_original_add_on_pnl": recaptured_original_add_on_pnl,
                "recaptured_retained_add_on_pnl": recaptured_retained_add_on_pnl,
                "earlier_estimated_delta": earlier_estimated - earlier_original,
                "recent_estimated_delta": recent_estimated - recent_original,
                "tail_50_original_pnl": tail_50_original,
                "tail_50_estimated_pnl": tail_50_estimated,
                "tail_50_retention_pct": tail_50_estimated / tail_50_original * 100,
                "tail_100_original_pnl": tail_100_original,
                "tail_100_estimated_pnl": tail_100_estimated,
                "tail_100_retention_pct": tail_100_estimated / tail_100_original * 100,
            }
        )

    matched_rows = []
    for trade in matched:
        matched_rows.append(
            {
                "round_trip_id": trade["round_trip_id"],
                "symbol": trade["symbol"],
                "signal_at_utc": trade["signal_at"],
                "opened_at_utc": trade["opened_at"],
                "closed_at_utc": trade["closed_at"],
                "match_difference_seconds": trade["match_difference_seconds"],
                "signal_price": str(trade["signal_price"]),
                "signal_stop": str(trade["signal_stop"]),
                "stop_distance_pct": trade["stop_distance_pct"],
                "net_pnl": trade["net_pnl"],
                "base_leg_net_pnl": trade["base_leg"].get("net_pnl_contribution", "")
                if trade["base_leg"]
                else "",
                "add_on_count": trade["payload"].get("add_on_leg_count", 0),
                "exit_reason": trade["exit_reason"],
            }
        )

    write_csv(args.output_dir / "matched_base_trades.csv", matched_rows)
    write_csv(args.output_dir / "threshold_summary.csv", summary_rows)
    write_csv(args.output_dir / "threshold_trade_detail.csv", detail_rows)

    all_stats = calculate_stats([trade["net_pnl"] for trade in matched + unmatched])
    earlier = [trade for trade in matched + unmatched if trade["opened_time"] < recent_cutoff]
    recent = [trade for trade in matched + unmatched if trade["opened_time"] >= recent_cutoff]
    earlier_stats = calculate_stats([trade["net_pnl"] for trade in earlier])
    recent_stats = calculate_stats([trade["net_pnl"] for trade in recent])

    lines = [
        "# Tight-stop base entry threshold analysis\n\n",
        "## Data quality\n\n",
        f"- Closed round trips: {len(matched) + len(unmatched)}\n",
        f"- Matched to base signals: {len(matched)}\n",
        f"- Unmatched legacy/rebuilt trades retained in baseline: {len(unmatched)}\n",
        "- Replay price convention: previous completed 1m candle close; no current-minute lookahead.\n",
        "- Entry stop is recomputed from previous-hour low/current-hour low using the live strategy rule.\n\n",
        "## Baseline\n\n",
        f"- Net PnL: {all_stats['net']:.2f} USDT\n",
        f"- Wins: {all_stats['wins']}/{all_stats['count']} ({all_stats['win_rate']:.2f}%)\n",
        f"- Median trade: {all_stats['median']:.2f} USDT\n",
        f"- Before 2026-05-29 UTC: {earlier_stats['count']} trades, {earlier_stats['net']:.2f} USDT\n",
        f"- Since 2026-05-29 UTC: {recent_stats['count']} trades, {recent_stats['net']:.2f} USDT\n\n",
        "## Threshold comparison\n\n",
        "| threshold | affected | original basket | hard-filter delta | any-top1 recaptured | estimated total | estimated delta | recent delta | tail>=50 retained | missed >=50/>=100 | median delay |\n",
        "|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|---:|\n",
    ]
    for row in summary_rows:
        lines.append(
            f"| {row['threshold_pct']:.0f}% | {row['affected_count']} | "
            f"{row['affected_original_pnl']:.2f} | {row['hard_filter_delta']:.2f} | "
            f"{row['any_top1_recaptured_count']} | {row['estimated_strategy_total_pnl']:.2f} | "
            f"{row['estimated_strategy_delta']:.2f} | {row['recent_estimated_delta']:.2f} | "
            f"{row['tail_50_retention_pct']:.1f}% | "
            f"{row['missed_tail_50']}/{row['missed_tail_100']} | "
            f"{float(row['median_delay_minutes']):.1f}m |\n"
        )

    lines.extend(
        [
            "\n## PnL decomposition for recaptured trades\n\n",
            "| threshold | original base | delayed base | original add-ons | retained add-ons | earlier delta | recent delta |\n",
            "|---:|---:|---:|---:|---:|---:|---:|\n",
        ]
    )
    for row in summary_rows:
        lines.append(
            f"| {row['threshold_pct']:.0f}% | {row['recaptured_original_base_pnl']:.2f} | "
            f"{row['recaptured_estimated_base_pnl']:.2f} | "
            f"{row['recaptured_original_add_on_pnl']:.2f} | "
            f"{row['recaptured_retained_add_on_pnl']:.2f} | "
            f"{row['earlier_estimated_delta']:.2f} | {row['recent_estimated_delta']:.2f} |\n"
        )

    lines.extend(
        [
            "\n## Stop-distance distribution\n\n",
            "| range | trades | net PnL | wins | >=50 | >=100 | base PnL | add-on PnL |\n",
            "|---:|---:|---:|---:|---:|---:|---:|---:|\n",
        ]
    )
    distance_bins = (
        (0, 1),
        (1, 2),
        (2, 3),
        (3, 4),
        (4, 5),
        (5, 6),
        (6, 8),
        (8, 10),
        (10, 15),
        (15, 20),
        (20, float("inf")),
    )
    for lower, upper in distance_bins:
        bucket = [
            trade
            for trade in matched
            if lower <= trade["stop_distance_pct"] < upper
        ]
        bucket_net = sum(trade["net_pnl"] for trade in bucket)
        bucket_base = sum(
            float(trade["base_leg"]["net_pnl_contribution"]) for trade in bucket
        )
        upper_label = f"{upper:g}" if upper != float("inf") else "+"
        lines.append(
            f"| {lower:g}-{upper_label}% | {len(bucket)} | {bucket_net:.2f} | "
            f"{sum(trade['net_pnl'] > 0 for trade in bucket)} | "
            f"{sum(trade['net_pnl'] >= 50 for trade in bucket)} | "
            f"{sum(trade['net_pnl'] >= 100 for trade in bucket)} | "
            f"{bucket_base:.2f} | {bucket_net - bucket_base:.2f} |\n"
        )

    lines.append("\n## Affected long-tail trades\n")
    for threshold in THRESHOLDS:
        lines.append(f"\n### {threshold:.0f}%\n\n")
        threshold_rows = [
            row
            for row in detail_rows
            if row["threshold_pct"] == threshold and float(row["original_net_pnl"]) >= 50
        ]
        if not threshold_rows:
            lines.append("- None.\n")
            continue
        for row in sorted(threshold_rows, key=lambda item: float(item["original_net_pnl"]), reverse=True):
            estimated = row["estimated_delayed_total_pnl"] or "not recaptured"
            lines.append(
                f"- {row['symbol']} {row['signal_at_utc'][:16]}: original "
                f"{float(row['original_net_pnl']):.2f}, recaptured={row['any_top1_recaptured']}, "
                f"delay={row['delay_minutes']}, estimated={estimated}\n"
            )

    (args.output_dir / "summary.md").write_text("".join(lines))
    print("".join(lines))


if __name__ == "__main__":
    main()
