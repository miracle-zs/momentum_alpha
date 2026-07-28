#!/usr/bin/env python3
"""Evaluate tail-preserving entry vetoes and causal add-on confirmation signals."""

from __future__ import annotations

import argparse
import json
import sqlite3
import sys
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from decimal import Decimal
from pathlib import Path


SHANGHAI = timezone(timedelta(hours=8))
MONTHS = ("2026-04", "2026-05", "2026-06", "2026-07")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, required=True)
    parser.add_argument("--output", type=Path, required=True)
    return parser.parse_args()


def parse_time(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def number(value: object, default: float | None = None) -> float | None:
    if value in (None, ""):
        return default
    return float(value)


def load_rows(db_path: Path) -> tuple[list[dict], list[dict]]:
    connection = sqlite3.connect(f"file:{db_path}?mode=ro", uri=True)
    connection.row_factory = sqlite3.Row
    base_decisions: dict[str, list[dict]] = defaultdict(list)
    add_decisions: dict[str, list[dict]] = defaultdict(list)
    leader_observations: list[tuple[datetime, str]] = []
    for row in connection.execute(
        """
        SELECT timestamp, decision_type, symbol, next_leader_symbol, payload_json
        FROM signal_decisions NOT INDEXED
        WHERE next_leader_symbol IS NOT NULL
        ORDER BY id
        """
    ):
        if row["next_leader_symbol"]:
            leader_observations.append(
                (parse_time(row["timestamp"]), str(row["next_leader_symbol"]))
            )
        if row["decision_type"] not in ("base_entry", "add_on"):
            continue
        item = {
            "time": parse_time(row["timestamp"]),
            "payload": json.loads(row["payload_json"]),
        }
        target = base_decisions if row["decision_type"] == "base_entry" else add_decisions
        target[str(row["symbol"])].append(item)

    trades: list[dict] = []
    add_legs: list[dict] = []
    for row in connection.execute(
        """
        SELECT round_trip_id, symbol, opened_at, closed_at, net_pnl,
               commission, payload_json
        FROM trade_round_trips NOT INDEXED
        ORDER BY opened_at
        """
    ):
        payload = json.loads(row["payload_json"])
        legs = payload.get("legs") or []
        if not legs:
            continue
        opened = parse_time(row["opened_at"])
        local_opened = opened.astimezone(SHANGHAI)
        candidates = [
            decision
            for decision in base_decisions.get(str(row["symbol"]), [])
            if -5 <= (opened - decision["time"]).total_seconds() <= 300
        ]
        decision = min(
            candidates,
            key=lambda item: abs((opened - item["time"]).total_seconds()),
            default=None,
        )
        decision_payload = decision["payload"] if decision else {}
        latest = number(decision_payload.get("latest_price"))
        stop = number(decision_payload.get("stop_price"))
        stop_distance = (
            (latest - stop) / latest * 100
            if latest not in (None, 0) and stop is not None
            else None
        )
        trade = {
            "id": row["round_trip_id"],
            "symbol": row["symbol"],
            "opened": opened,
            "month": local_opened.strftime("%Y-%m"),
            "hour": local_opened.hour,
            "weekday": local_opened.weekday(),
            "pnl": float(row["net_pnl"] or 0),
            "base_pnl": number(legs[0].get("net_pnl_contribution"), 0.0) or 0.0,
            "add_pnl": sum(number(leg.get("net_pnl_contribution"), 0.0) or 0.0 for leg in legs[1:]),
            "legs": len(legs),
            "matched": decision is not None,
            "signal_time": decision["time"] if decision else None,
            "stop_distance": stop_distance,
            "daily_change": number(decision_payload.get("daily_change_pct")),
            "leader_gap": number(decision_payload.get("leader_gap_pct")),
        }
        trades.append(trade)

        base_risk = number(payload.get("base_leg_risk")) or number(legs[0].get("leg_risk"))
        for index, leg in enumerate(legs[1:], start=1):
            leg_time = parse_time(leg["opened_at"])
            leg_stop = number(leg.get("stop_price_at_entry"))
            prior = legs[:index]
            locked_before = None
            if leg_stop is not None:
                locked_before = sum(
                    (leg_stop - float(item["entry_price"])) * float(item["quantity"])
                    for item in prior
                )
            add_candidates = [
                item
                for item in add_decisions.get(str(row["symbol"]), [])
                if -5 <= (leg_time - item["time"]).total_seconds() <= 300
            ]
            add_decision = min(
                add_candidates,
                key=lambda item: abs((leg_time - item["time"]).total_seconds()),
                default=None,
            )
            add_payload = add_decision["payload"] if add_decision else {}
            add_legs.append(
                {
                    "trade_id": row["round_trip_id"],
                    "symbol": row["symbol"],
                    "month": local_opened.strftime("%Y-%m"),
                    "leg_index": int(leg.get("leg_index") or index + 1),
                    "elapsed_hours": (leg_time - opened).total_seconds() / 3600,
                    "net_pnl": number(leg.get("net_pnl_contribution"), 0.0) or 0.0,
                    "leg_risk": number(leg.get("leg_risk"), 0.0) or 0.0,
                    "post_risk": number(leg.get("cumulative_risk_after_leg")),
                    "locked_before": locked_before,
                    "locked_r": (
                        locked_before / base_risk
                        if locked_before is not None and base_risk not in (None, 0)
                        else None
                    ),
                    "daily_change": number(add_payload.get("daily_change_pct")),
                    "leader_gap": number(add_payload.get("leader_gap_pct")),
                    "trade_pnl": float(row["net_pnl"] or 0),
                }
            )
    for trade in trades:
        signal_time = trade["signal_time"]
        for minutes in (5, 10, 15, 30):
            if signal_time is None:
                trade[f"leader_persisted_{minutes}m"] = None
                continue
            end = signal_time + timedelta(minutes=minutes)
            observations = [
                leader
                for timestamp, leader in leader_observations
                if signal_time < timestamp <= end
            ]
            trade[f"leader_persisted_{minutes}m"] = bool(observations) and all(
                leader == trade["symbol"] for leader in observations
            )
    connection.close()
    return trades, add_legs


def filter_summary(trades: list[dict], name: str, predicate) -> dict:
    selected = [trade for trade in trades if predicate(trade)]
    pnl = sum(trade["pnl"] for trade in selected)
    tail = [trade for trade in trades if trade["pnl"] >= 50]
    removed_tail = [trade for trade in selected if trade["pnl"] >= 50]
    tail_pnl = sum(trade["pnl"] for trade in tail)
    removed_tail_pnl = sum(trade["pnl"] for trade in removed_tail)
    monthly = {
        month: -sum(trade["pnl"] for trade in selected if trade["month"] == month)
        for month in MONTHS
    }
    return {
        "name": name,
        "removed_count": len(selected),
        "removed_pct": len(selected) / len(trades) * 100,
        "pnl_improvement": -pnl,
        "losses_removed": sum(trade["pnl"] < 0 for trade in selected),
        "winners_removed": sum(trade["pnl"] > 0 for trade in selected),
        "tail_trades_removed": len(removed_tail),
        "tail_pnl_retained_pct": (tail_pnl - removed_tail_pnl) / tail_pnl * 100,
        "monthly_improvement": monthly,
        "removed_tail_ids": [trade["id"] for trade in removed_tail],
    }


def group_add_legs(add_legs: list[dict], key, label: str) -> list[dict]:
    groups: dict[str, list[dict]] = defaultdict(list)
    for leg in add_legs:
        groups[str(key(leg))].append(leg)
    rows = []
    for bucket, legs in groups.items():
        pnl = sum(leg["net_pnl"] for leg in legs)
        rows.append(
            {
                label: bucket,
                "count": len(legs),
                "pnl": pnl,
                "avg_pnl": pnl / len(legs),
                "positive_legs_pct": sum(leg["net_pnl"] > 0 for leg in legs) / len(legs) * 100,
                "tail_trade_legs": sum(leg["trade_pnl"] >= 50 for leg in legs),
                "monthly_pnl": {
                    month: sum(leg["net_pnl"] for leg in legs if leg["month"] == month)
                    for month in MONTHS
                },
            }
        )
    return rows


def condition_summary(add_legs: list[dict], name: str, predicate) -> dict:
    selected = [leg for leg in add_legs if predicate(leg)]
    pnl = sum(leg["net_pnl"] for leg in selected)
    risk = sum(leg["leg_risk"] for leg in selected)
    by_trade: dict[str, float] = defaultdict(float)
    for leg in selected:
        by_trade[leg["trade_id"]] += leg["net_pnl"]
    ranked_trades = sorted(by_trade.items(), key=lambda item: item[1], reverse=True)
    return {
        "name": name,
        "count": len(selected),
        "count_pct": len(selected) / len(add_legs) * 100 if add_legs else 0,
        "pnl": pnl,
        "avg_pnl": pnl / len(selected) if selected else 0,
        "gross_leg_risk": risk,
        "pnl_per_leg_risk": pnl / risk if risk else None,
        "positive_legs_pct": sum(leg["net_pnl"] > 0 for leg in selected) / len(selected) * 100 if selected else 0,
        "trade_count": len(by_trade),
        "top_trade_contributors": ranked_trades[:5],
        "bottom_trade_contributors": ranked_trades[-5:],
        "tail_trade_pnl": sum(leg["net_pnl"] for leg in selected if leg["trade_pnl"] >= 50),
        "non_tail_trade_pnl": sum(leg["net_pnl"] for leg in selected if leg["trade_pnl"] < 50),
        "monthly_pnl": {
            month: sum(leg["net_pnl"] for leg in selected if leg["month"] == month)
            for month in MONTHS
        },
    }


def allocation_summary(trades: list[dict], add_legs: list[dict], name: str, base_scale: float, add_scale) -> dict:
    add_by_trade: dict[str, float] = defaultdict(float)
    for leg in add_legs:
        add_by_trade[leg["trade_id"]] += leg["net_pnl"] * add_scale(leg)
    estimated_by_trade = {
        trade["id"]: trade["base_pnl"] * base_scale + add_by_trade[trade["id"]]
        for trade in trades
    }
    baseline = sum(trade["pnl"] for trade in trades)
    estimated = sum(estimated_by_trade.values())
    tail = [trade for trade in trades if trade["pnl"] >= 50]
    original_tail = sum(trade["pnl"] for trade in tail)
    estimated_tail = sum(estimated_by_trade[trade["id"]] for trade in tail)
    return {
        "name": name,
        "estimated_pnl": estimated,
        "improvement": estimated - baseline,
        "original_tail_pnl": original_tail,
        "estimated_original_tail_pnl": estimated_tail,
        "tail_pnl_retained_pct": estimated_tail / original_tail * 100,
        "profitable_original_tail_count": sum(estimated_by_trade[trade["id"]] > 0 for trade in tail),
        "monthly_pnl": {
            month: sum(estimated_by_trade[trade["id"]] for trade in trades if trade["month"] == month)
            for month in MONTHS
        },
    }


def main() -> None:
    args = parse_args()
    trades, add_legs = load_rows(args.db)
    matched = [trade for trade in trades if trade["matched"]]
    filters = [
        filter_summary(trades, "Beijing 09:00", lambda trade: trade["hour"] == 9),
        filter_summary(trades, "Sunday", lambda trade: trade["weekday"] == 6),
        filter_summary(trades, "Sunday or Monday", lambda trade: trade["weekday"] in (0, 6)),
        filter_summary(matched, "stop distance <1%", lambda trade: trade["stop_distance"] is not None and trade["stop_distance"] < 1),
        filter_summary(matched, "stop distance <2%", lambda trade: trade["stop_distance"] is not None and trade["stop_distance"] < 2),
        filter_summary(matched, "stop distance <3%", lambda trade: trade["stop_distance"] is not None and trade["stop_distance"] < 3),
        filter_summary(matched, "09:00 OR stop <2%", lambda trade: trade["hour"] == 9 or (trade["stop_distance"] is not None and trade["stop_distance"] < 2)),
        filter_summary(matched, "daily change 20%-40%", lambda trade: trade["daily_change"] is not None and .20 <= trade["daily_change"] < .40),
        filter_summary(matched, "leader gap <0.5%", lambda trade: trade["leader_gap"] is not None and trade["leader_gap"] < .005),
        filter_summary(matched, "fails 5m leader persistence", lambda trade: trade["leader_persisted_5m"] is False),
        filter_summary(matched, "fails 10m leader persistence", lambda trade: trade["leader_persisted_10m"] is False),
        filter_summary(matched, "fails 15m leader persistence", lambda trade: trade["leader_persisted_15m"] is False),
        filter_summary(matched, "fails 30m leader persistence", lambda trade: trade["leader_persisted_30m"] is False),
        filter_summary(matched, "09:00 AND fails 10m persistence", lambda trade: trade["hour"] == 9 and trade["leader_persisted_10m"] is False),
        filter_summary(matched, "stop <1% OR fails 10m persistence", lambda trade: (trade["stop_distance"] is not None and trade["stop_distance"] < 1) or trade["leader_persisted_10m"] is False),
    ]

    elapsed = group_add_legs(
        add_legs,
        lambda leg: "<1h" if leg["elapsed_hours"] < 1 else "1-2h" if leg["elapsed_hours"] < 2 else "2-3h" if leg["elapsed_hours"] < 3 else "3-4h" if leg["elapsed_hours"] < 4 else "4-6h" if leg["elapsed_hours"] < 6 else "6h+",
        "elapsed",
    )
    locked = group_add_legs(
        [leg for leg in add_legs if leg["locked_r"] is not None],
        lambda leg: "<0R" if leg["locked_r"] < 0 else "0-1R" if leg["locked_r"] < 1 else "1-3R" if leg["locked_r"] < 3 else "3R+",
        "locked_r",
    )
    conditions = [
        condition_summary(add_legs, "all add-ons", lambda leg: True),
        condition_summary(add_legs, "elapsed >=2h", lambda leg: leg["elapsed_hours"] >= 2),
        condition_summary(add_legs, "elapsed >=3h", lambda leg: leg["elapsed_hours"] >= 3),
        condition_summary(add_legs, "locked before >=0R", lambda leg: leg["locked_r"] is not None and leg["locked_r"] >= 0),
        condition_summary(add_legs, "locked before >=1R", lambda leg: leg["locked_r"] is not None and leg["locked_r"] >= 1),
        condition_summary(add_legs, "post-add risk = 0", lambda leg: leg["post_risk"] is not None and leg["post_risk"] <= 1e-9),
        condition_summary(add_legs, "elapsed >=3h AND post-risk=0", lambda leg: leg["elapsed_hours"] >= 3 and leg["post_risk"] is not None and leg["post_risk"] <= 1e-9),
        condition_summary(add_legs, "change >=40% AND gap >=5%", lambda leg: leg["daily_change"] is not None and leg["daily_change"] >= .4 and leg["leader_gap"] is not None and leg["leader_gap"] >= .05),
        condition_summary(add_legs, "change >=80% AND gap >=10%", lambda leg: leg["daily_change"] is not None and leg["daily_change"] >= .8 and leg["leader_gap"] is not None and leg["leader_gap"] >= .10),
        condition_summary(add_legs, "change >=100% AND gap >=10%", lambda leg: leg["daily_change"] is not None and leg["daily_change"] >= 1.0 and leg["leader_gap"] is not None and leg["leader_gap"] >= .10),
        condition_summary(add_legs, "change >=100% AND gap >=20%", lambda leg: leg["daily_change"] is not None and leg["daily_change"] >= 1.0 and leg["leader_gap"] is not None and leg["leader_gap"] >= .20),
        condition_summary(add_legs, "change >=150% AND gap >=20%", lambda leg: leg["daily_change"] is not None and leg["daily_change"] >= 1.5 and leg["leader_gap"] is not None and leg["leader_gap"] >= .20),
        condition_summary(add_legs, "elapsed>=3h risk=0 change>=40% gap>=5%", lambda leg: leg["elapsed_hours"] >= 3 and leg["post_risk"] is not None and leg["post_risk"] <= 1e-9 and leg["daily_change"] is not None and leg["daily_change"] >= .4 and leg["leader_gap"] is not None and leg["leader_gap"] >= .05),
    ]
    allocations = [
        allocation_summary(trades, add_legs, "base 0.75R, add 1R", .75, lambda leg: 1.0),
        allocation_summary(trades, add_legs, "base 0.50R, add 1R", .50, lambda leg: 1.0),
        allocation_summary(trades, add_legs, "base 0.25R, add 1R", .25, lambda leg: 1.0),
        allocation_summary(trades, add_legs, "base 0.5R, adds 0.5R", .50, lambda leg: .5),
        allocation_summary(
            trades,
            add_legs,
            "base 0.5R, add 0.5R; strong change/gap add 2R",
            .50,
            lambda leg: 2.0 if leg["daily_change"] is not None and leg["daily_change"] >= .8 and leg["leader_gap"] is not None and leg["leader_gap"] >= .10 else .5,
        ),
        allocation_summary(
            trades,
            add_legs,
            "base 0.5R, add 0.5R; strong+self-funded add 2R",
            .50,
            lambda leg: 2.0 if leg["daily_change"] is not None and leg["daily_change"] >= .8 and leg["leader_gap"] is not None and leg["leader_gap"] >= .10 and leg["post_risk"] is not None and leg["post_risk"] <= 1e-9 else .5,
        ),
    ]
    result = {
        "dataset": {
            "trades": len(trades),
            "matched_base_signals": len(matched),
            "net_pnl": sum(trade["pnl"] for trade in trades),
            "tail_50_count": sum(trade["pnl"] >= 50 for trade in trades),
            "tail_50_pnl": sum(trade["pnl"] for trade in trades if trade["pnl"] >= 50),
            "add_on_legs": len(add_legs),
        },
        "entry_filters": filters,
        "add_on_by_elapsed": elapsed,
        "add_on_by_locked_r": locked,
        "add_on_confirmation": conditions,
        "allocation_counterfactuals": allocations,
    }
    args.output.parent.mkdir(parents=True, exist_ok=True)
    args.output.write_text(json.dumps(result, indent=2, ensure_ascii=True))
    print(json.dumps(result, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
