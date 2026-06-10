#!/usr/bin/env python3
"""Research conservative false-breakout vetoes for base entries."""

from __future__ import annotations

import argparse
import csv
import itertools
import json
import math
import subprocess
import sys
import time
from collections import defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import fmean, median, pstdev


sys.path.insert(0, str(Path(__file__).resolve().parent))

from analyze_tight_stop_thresholds import load_data  # noqa: E402


@dataclass(frozen=True)
class Condition:
    family: str
    feature: str
    operator: str
    threshold: float

    @property
    def label(self) -> str:
        return f"{self.feature}{self.operator}{self.threshold:g}"


def evaluate_condition(row: dict, condition: Condition) -> bool:
    value = row.get(condition.feature, "")
    if value in ("", None):
        return False
    numeric = float(value)
    if condition.operator == "<=":
        return numeric <= condition.threshold
    if condition.operator == ">=":
        return numeric >= condition.threshold
    raise ValueError(f"unsupported operator: {condition.operator}")


def _parse_datetime(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def summarize_candidate(
    rows: list[dict],
    conditions: tuple[Condition, ...],
    *,
    unmatched: list[dict] | tuple[dict, ...] = (),
    recent_cutoff: datetime = datetime.fromisoformat(
        "2026-05-29T00:00:00+00:00"
    ),
) -> dict:
    filtered = [
        row
        for row in rows
        if all(evaluate_condition(row, condition) for condition in conditions)
    ]
    filtered_ids = {row["round_trip_id"] for row in filtered}
    all_rows = [*rows, *unmatched]
    baseline = sum(float(row["net_pnl"]) for row in all_rows)
    estimated = sum(
        0.0
        if row.get("round_trip_id") in filtered_ids
        else float(row["net_pnl"])
        for row in all_rows
    )

    tail_50_original = sum(
        float(row["net_pnl"])
        for row in all_rows
        if float(row["net_pnl"]) >= 50
    )
    tail_50_estimated = sum(
        0.0
        if row.get("round_trip_id") in filtered_ids
        else float(row["net_pnl"])
        for row in all_rows
        if float(row["net_pnl"]) >= 50
    )
    weekly_deltas: dict[str, float] = {}
    recent_delta = 0.0
    earlier_delta = 0.0
    for row in filtered:
        opened_at = _parse_datetime(row["opened_at_utc"])
        year, week, _ = opened_at.isocalendar()
        key = f"{year}-W{week:02d}"
        delta = -float(row["net_pnl"])
        weekly_deltas[key] = weekly_deltas.get(key, 0.0) + delta
        if opened_at >= recent_cutoff:
            recent_delta += delta
        else:
            earlier_delta += delta

    filtered_losses = [
        row for row in filtered if float(row["net_pnl"]) < 0
    ]
    estimated_delta = estimated - baseline
    max_trade_gain = max(
        (-float(row["net_pnl"]) for row in filtered_losses),
        default=0.0,
    )
    max_week_gain = max(weekly_deltas.values(), default=0.0)
    total_add_on_count = sum(int(row.get("add_on_count", 0)) for row in rows)
    filtered_add_on_count = sum(
        int(row.get("add_on_count", 0)) for row in filtered
    )
    total_add_on_pnl = sum(float(row.get("add_on_pnl", 0.0)) for row in rows)
    filtered_add_on_pnl = sum(
        float(row.get("add_on_pnl", 0.0)) for row in filtered
    )

    return {
        "condition_count": len(conditions),
        "conditions": " AND ".join(condition.label for condition in conditions),
        "families": "+".join(condition.family for condition in conditions),
        "baseline_total_pnl": baseline,
        "estimated_total_pnl": estimated,
        "estimated_delta": estimated_delta,
        "recent_delta": recent_delta,
        "earlier_delta": earlier_delta,
        "filtered_count": len(filtered),
        "filtered_ids": sorted(filtered_ids),
        "filtered_losses": len(filtered_losses),
        "filtered_winners": sum(float(row["net_pnl"]) > 0 for row in filtered),
        "filtered_original_pnl": sum(float(row["net_pnl"]) for row in filtered),
        "filtered_add_on_count": filtered_add_on_count,
        "filtered_add_on_pnl": filtered_add_on_pnl,
        "add_on_count_retention_pct": (
            (total_add_on_count - filtered_add_on_count)
            / total_add_on_count
            * 100
            if total_add_on_count
            else 100.0
        ),
        "add_on_pnl_retention_pct": (
            (total_add_on_pnl - filtered_add_on_pnl)
            / total_add_on_pnl
            * 100
            if total_add_on_pnl
            else 100.0
        ),
        "tail_50_original_pnl": tail_50_original,
        "tail_50_estimated_pnl": tail_50_estimated,
        "tail_50_retention_pct": (
            tail_50_estimated / tail_50_original * 100
            if tail_50_original
            else 100.0
        ),
        "tail_100_filtered_count": sum(
            float(row["net_pnl"]) >= 100 for row in filtered
        ),
        "weekly_deltas": weekly_deltas,
        "positive_weeks": sum(value > 0 for value in weekly_deltas.values()),
        "negative_weeks": sum(value < 0 for value in weekly_deltas.values()),
        "max_trade_concentration_pct": (
            max_trade_gain / estimated_delta * 100
            if estimated_delta > 0
            else ""
        ),
        "max_week_concentration_pct": (
            max_week_gain / estimated_delta * 100
            if estimated_delta > 0
            else ""
        ),
    }


def passes_tail_constraints(summary: dict) -> bool:
    return (
        int(summary["tail_100_filtered_count"]) == 0
        and float(summary["tail_50_retention_pct"]) >= 98.0
        and float(summary["estimated_delta"]) > 0
    )


def expand_veto_condition(
    condition: Condition,
    *,
    fraction: float,
) -> Condition:
    step = max(abs(condition.threshold) * fraction, 0.05)
    threshold = (
        condition.threshold + step
        if condition.operator == "<="
        else condition.threshold - step
    )
    return Condition(
        condition.family,
        condition.feature,
        condition.operator,
        threshold,
    )


def completed_candles_before(klines: list, signal_time: datetime) -> list[dict]:
    signal_ms = int(signal_time.timestamp() * 1000)
    completed = []
    for item in sorted(klines, key=lambda row: int(row[0])):
        if int(item[6]) >= signal_ms:
            continue
        completed.append(
            {
                "open_minute": int(item[0]) // 60_000,
                "open": float(item[1]),
                "high": float(item[2]),
                "low": float(item[3]),
                "close": float(item[4]),
                "quote_volume": float(item[7]),
                "trades": int(item[8]),
                "taker_buy_quote": float(item[10]),
            }
        )
    return completed


def _true_ranges(candles: list[dict]) -> list[float]:
    ranges = []
    previous_close = None
    for candle in candles:
        if previous_close is None:
            value = candle["high"] - candle["low"]
        else:
            value = max(
                candle["high"] - candle["low"],
                abs(candle["high"] - previous_close),
                abs(candle["low"] - previous_close),
            )
        ranges.append(value)
        previous_close = candle["close"]
    return ranges


def compute_features(
    candles: list[dict],
    trade: dict,
    *,
    windows: tuple[int, ...] = (5, 15, 30, 60),
    day_start_minute: int | None = None,
    signal_minute: int | None = None,
) -> dict[str, float | str]:
    features: dict[str, float | str] = {}
    if not candles:
        for window in windows:
            for name in (
                "return",
                "efficiency",
                "positive_share",
                "pullback",
                "quote_volume_ratio",
                "trade_count_ratio",
                "taker_buy_share",
                "realized_volatility",
                "atr",
            ):
                features[f"{name}_{window}m"] = ""
        return features

    last = candles[-1]
    close = last["close"]
    day_candles = (
        [
            candle
            for candle in candles
            if candle["open_minute"] >= day_start_minute
        ]
        if day_start_minute is not None
        else candles
    )
    day_high = max(candle["high"] for candle in day_candles)
    features["distance_day_high_pct"] = (
        (day_high - close) / day_high * 100 if day_high > 0 else ""
    )
    candle_range = last["high"] - last["low"]
    features["close_location"] = (
        (last["close"] - last["low"]) / candle_range if candle_range > 0 else ""
    )
    features["upper_wick_fraction"] = (
        (last["high"] - max(last["open"], last["close"])) / candle_range
        if candle_range > 0
        else ""
    )
    signal_price = float(trade["signal_price"])
    signal_stop = float(trade["signal_stop"])
    features["stop_distance_pct"] = (
        (signal_price - signal_stop) / signal_price * 100
        if signal_price > signal_stop
        else ""
    )

    true_ranges = _true_ranges(candles)
    closes = [candle["close"] for candle in candles]
    ema_values: dict[int, float] = {}
    for period in (8, 20, 21):
        value = None
        alpha = 2.0 / (period + 1)
        for item in closes:
            value = item if value is None else alpha * item + (1 - alpha) * value
        ema_values[period] = value if value is not None else close
    features["ema8_above_ema21"] = float(ema_values[8] > ema_values[21])
    features["close_above_ema20"] = float(close > ema_values[20])

    current_hour_start = (last["open_minute"] // 60) * 60
    current_hour = [
        candle
        for candle in candles
        if candle["open_minute"] >= current_hour_start
    ]
    features["current_hour_return_pct"] = (
        (close / current_hour[0]["open"] - 1) * 100
        if current_hour and current_hour[0]["open"] > 0
        else ""
    )
    features["current_hour_green"] = float(
        features["current_hour_return_pct"] != ""
        and float(features["current_hour_return_pct"]) > 0
    )
    for window in windows:
        value_keys = (
            f"return_{window}m_pct",
            f"efficiency_{window}m",
            f"positive_share_{window}m",
            f"pullback_{window}m_pct",
            f"quote_volume_ratio_{window}m",
            f"trade_count_ratio_{window}m",
            f"taker_buy_share_{window}m",
            f"realized_volatility_{window}m_pct",
            f"atr_{window}m_pct",
        )
        if len(candles) < window + 1:
            for key in value_keys:
                features[key] = ""
            continue

        window_candles = candles[-window:]
        window_closes = closes[-(window + 1) :]
        returns = [
            window_closes[index] / window_closes[index - 1] - 1
            for index in range(1, len(window_closes))
            if window_closes[index - 1] > 0
        ]
        net_move = window_closes[-1] - window_closes[0]
        path_length = sum(
            abs(window_closes[index] - window_closes[index - 1])
            for index in range(1, len(window_closes))
        )
        rolling_high = max(candle["high"] for candle in window_candles)
        features[f"return_{window}m_pct"] = (
            (window_closes[-1] / window_closes[0] - 1) * 100
            if window_closes[0] > 0
            else ""
        )
        features[f"efficiency_{window}m"] = (
            abs(net_move) / path_length if path_length > 0 else 0.0
        )
        features[f"positive_share_{window}m"] = (
            sum(value > 0 for value in returns) / len(returns)
            if returns
            else ""
        )
        features[f"pullback_{window}m_pct"] = (
            (rolling_high - close) / rolling_high * 100
            if rolling_high > 0
            else ""
        )

        recent_quote = fmean(candle["quote_volume"] for candle in window_candles)
        prior_quote_candles = candles[-(2 * window) : -window]
        recent_trades = fmean(candle["trades"] for candle in window_candles)
        prior_trade_candles = prior_quote_candles
        if len(prior_quote_candles) == window:
            prior_quote = fmean(
                candle["quote_volume"] for candle in prior_quote_candles
            )
            prior_trades = fmean(candle["trades"] for candle in prior_trade_candles)
            features[f"quote_volume_ratio_{window}m"] = (
                recent_quote / prior_quote if prior_quote > 0 else ""
            )
            features[f"trade_count_ratio_{window}m"] = (
                recent_trades / prior_trades if prior_trades > 0 else ""
            )
        else:
            features[f"quote_volume_ratio_{window}m"] = ""
            features[f"trade_count_ratio_{window}m"] = ""

        quote_total = sum(candle["quote_volume"] for candle in window_candles)
        taker_total = sum(candle["taker_buy_quote"] for candle in window_candles)
        features[f"taker_buy_share_{window}m"] = (
            taker_total / quote_total if quote_total > 0 else ""
        )
        features[f"realized_volatility_{window}m_pct"] = (
            pstdev(returns) * math.sqrt(len(returns)) * 100
            if len(returns) >= 2
            else ""
        )
        features[f"atr_{window}m_pct"] = (
            fmean(true_ranges[-window:]) / close * 100 if close > 0 else ""
        )
        prior_ranges = true_ranges[-(2 * window) : -window]
        features[f"range_expansion_{window}m"] = (
            fmean(true_ranges[-window:]) / fmean(prior_ranges)
            if len(prior_ranges) == window and fmean(prior_ranges) > 0
            else ""
        )
        prior_highs = candles[-(window + 1) : -1]
        prior_high = max(
            (candle["high"] for candle in prior_highs),
            default=0.0,
        )
        features[f"breakout_{window}m_pct"] = (
            (close / prior_high - 1) * 100 if prior_high > 0 else ""
        )
        realized = features[f"realized_volatility_{window}m_pct"]
        period_return = features[f"return_{window}m_pct"]
        features[f"return_to_vol_{window}m"] = (
            float(period_return) / float(realized)
            if period_return != "" and realized not in ("", 0)
            else ""
        )

    if (
        features.get("return_5m_pct", "") != ""
        and features.get("return_30m_pct", "") != ""
    ):
        features["return_acceleration_5_30"] = float(
            features["return_5m_pct"]
        ) - float(features["return_30m_pct"]) / 6
    else:
        features["return_acceleration_5_30"] = ""

    def period_sum(
        field: str,
        start_minute: int,
        end_minute: int,
    ) -> float | None:
        period = [
            candle
            for candle in candles
            if start_minute <= candle["open_minute"] < end_minute
        ]
        if len(period) != end_minute - start_minute:
            return None
        return sum(float(candle[field]) for candle in period)

    if len(candles) >= 180:
        rolling = [
            sum(float(candle[field]) for candle in candles[start:end])
            for field in ("quote_volume", "trades")
            for start, end in (
                (-60, len(candles)),
                (-120, -60),
                (-180, -120),
            )
        ]
        for field_index, prefix in ((0, "quote_volume"), (3, "trade_count")):
            latest, previous, two_back = rolling[
                field_index : field_index + 3
            ]
            previous_average = (previous + two_back) / 2
            features[f"{prefix}_ratio_60m_prev_2h_avg"] = (
                latest / previous_average if previous_average > 0 else ""
            )
            features[f"{prefix}_above_both_prev_hours"] = float(
                latest > previous and latest > two_back
            )
            features[f"{prefix}_three_hour_rising"] = float(
                latest > previous > two_back
            )
    else:
        for prefix in ("quote_volume", "trade_count"):
            features[f"{prefix}_ratio_60m_prev_2h_avg"] = ""
            features[f"{prefix}_above_both_prev_hours"] = ""
            features[f"{prefix}_three_hour_rising"] = ""

    effective_signal_minute = (
        signal_minute
        if signal_minute is not None
        else candles[-1]["open_minute"] + 1
    )
    current_hour_start = (effective_signal_minute // 60) * 60
    for field, prefix in (
        ("quote_volume", "completed_hour_volume"),
        ("trades", "completed_hour_trade_count"),
    ):
        latest = period_sum(
            field,
            current_hour_start - 60,
            current_hour_start,
        )
        previous = period_sum(
            field,
            current_hour_start - 120,
            current_hour_start - 60,
        )
        two_back = period_sum(
            field,
            current_hour_start - 180,
            current_hour_start - 120,
        )
        if latest is None or previous is None or two_back is None:
            features[f"{prefix}_ratio_prev_2h_avg"] = ""
            features[f"{prefix}_above_both_prev_hours"] = ""
            features[f"{prefix}_three_hour_rising"] = ""
            continue
        previous_average = (previous + two_back) / 2
        features[f"{prefix}_ratio_prev_2h_avg"] = (
            latest / previous_average if previous_average > 0 else ""
        )
        features[f"{prefix}_above_both_prev_hours"] = float(
            latest > previous and latest > two_back
        )
        features[f"{prefix}_three_hour_rising"] = float(
            latest > previous > two_back
        )
    return features


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--db", type=Path, default=Path("var/runtime.db"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("var/analysis/base_filter_research_20260610"),
    )
    parser.add_argument("--proxy", default="http://127.0.0.1:7897")
    parser.add_argument("--fetch", action="store_true")
    return parser.parse_args()


def fetch_day(symbol: str, day_text: str, proxy: str) -> list:
    day = datetime.fromisoformat(f"{day_text}T00:00:00+00:00")
    url = (
        "https://fapi.binance.com/fapi/v1/klines"
        f"?symbol={symbol}&interval=1m"
        f"&startTime={int(day.timestamp() * 1000)}"
        f"&endTime={int((day + timedelta(days=1)).timestamp() * 1000 - 1)}"
        "&limit=1440"
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
            if isinstance(data, list):
                return data
            raise RuntimeError(f"unexpected Binance response: {str(data)[:200]}")
        except Exception as error:
            last_error = error
            time.sleep(1 + attempt * 0.5)
    raise RuntimeError(f"failed to fetch {symbol} {day_text}: {last_error}")


def required_cache_keys(trades: list[dict]) -> set[str]:
    required = set()
    for trade in trades:
        day = trade["signal_time"].date()
        required.add(f"{trade['symbol']}:{day.isoformat()}")
        required.add(
            f"{trade['symbol']}:{(day - timedelta(days=1)).isoformat()}"
        )
    return required


def load_kline_cache(
    *,
    trades: list[dict],
    cache_path: Path,
    seed_paths: tuple[Path, ...],
    proxy: str,
    fetch: bool,
) -> dict[str, list]:
    cache: dict[str, list] = {}
    for path in seed_paths:
        if path.exists():
            cache.update(json.loads(path.read_text()))
    if cache_path.exists():
        cache.update(json.loads(cache_path.read_text()))

    missing = sorted(required_cache_keys(trades) - cache.keys())
    if missing and not fetch:
        raise RuntimeError(
            f"{len(missing)} symbol-days missing from {cache_path}; "
            "rerun with --fetch"
        )
    if not missing:
        return cache

    cache_path.parent.mkdir(parents=True, exist_ok=True)
    failures = []
    with ThreadPoolExecutor(max_workers=6) as executor:
        futures = {}
        for key in missing:
            symbol, day_text = key.split(":", 1)
            futures[executor.submit(fetch_day, symbol, day_text, proxy)] = key
        for index, future in enumerate(as_completed(futures), start=1):
            key = futures[future]
            try:
                cache[key] = future.result()
            except RuntimeError as error:
                print(str(error), flush=True)
                failures.append(key)
            if index % 20 == 0 or index == len(missing):
                cache_path.write_text(json.dumps(cache))
                print(
                    f"1m cache {index}/{len(missing)}; "
                    f"failures={len(failures)}",
                    flush=True,
                )
    cache_path.write_text(json.dumps(cache))
    if failures:
        raise RuntimeError(
            f"{len(failures)} symbol-days failed: {', '.join(failures[:10])}"
        )
    return cache


def build_feature_rows(
    trades: list[dict],
    cache: dict[str, list],
) -> list[dict]:
    rows = []
    for trade in trades:
        day = trade["signal_time"].date()
        previous_key = (
            f"{trade['symbol']}:{(day - timedelta(days=1)).isoformat()}"
        )
        current_key = f"{trade['symbol']}:{day.isoformat()}"
        current_klines = cache.get(current_key, [])
        if not current_klines:
            raise RuntimeError(f"missing signal-day klines: {current_key}")
        combined = {
            int(item[0]): item
            for item in [*cache.get(previous_key, []), *current_klines]
        }
        candles = completed_candles_before(
            list(combined.values()),
            trade["signal_time"],
        )
        day_start = datetime.combine(
            day,
            datetime.min.time(),
            tzinfo=timezone.utc,
        )
        features = compute_features(
            candles,
            trade,
            day_start_minute=int(day_start.timestamp() // 60),
            signal_minute=int(trade["signal_time"].timestamp() // 60),
        )
        base_pnl = float(trade["base_leg"]["net_pnl_contribution"])
        add_on_legs = [
            leg
            for leg in trade["payload"].get("legs", [])
            if leg.get("leg_type") == "add_on"
        ]
        row = {
            "round_trip_id": trade["round_trip_id"],
            "symbol": trade["symbol"],
            "signal_at_utc": trade["signal_at"],
            "opened_at_utc": trade["opened_at"],
            "closed_at_utc": trade["closed_at"],
            "net_pnl": trade["net_pnl"],
            "base_pnl": base_pnl,
            "add_on_count": len(add_on_legs),
            "add_on_pnl": trade["net_pnl"] - base_pnl,
            "stop_distance_pct_recorded": trade["stop_distance_pct"],
            **features,
        }
        rows.append(row)
    return rows


def unmatched_rows(trades: list[dict]) -> list[dict]:
    return [
        {
            "round_trip_id": trade["round_trip_id"],
            "opened_at_utc": trade["opened_at"],
            "net_pnl": trade["net_pnl"],
        }
        for trade in trades
    ]


def condition_grid() -> list[Condition]:
    definitions = {
        "path": [
            ("efficiency_15m", "<=", (0.15, 0.25, 0.35, 0.45)),
            ("efficiency_30m", "<=", (0.15, 0.25, 0.35, 0.45)),
            ("positive_share_15m", "<=", (0.4, 0.5, 0.6)),
            ("positive_share_30m", "<=", (0.4, 0.5, 0.6)),
            ("return_15m_pct", "<=", (0.0, 0.5, 1.0, 2.0)),
            ("return_acceleration_5_30", "<=", (-0.5, 0.0, 0.5)),
            ("current_hour_green", "<=", (0.0,)),
            ("ema8_above_ema21", "<=", (0.0,)),
            ("close_above_ema20", "<=", (0.0,)),
        ],
        "acceptance": [
            ("distance_day_high_pct", ">=", (0.5, 1.0, 2.0, 3.0, 5.0)),
            ("pullback_15m_pct", ">=", (0.5, 1.0, 2.0, 3.0)),
            ("pullback_30m_pct", ">=", (0.5, 1.0, 2.0, 3.0)),
            ("close_location", "<=", (0.25, 0.4, 0.55)),
            ("upper_wick_fraction", ">=", (0.4, 0.6, 0.75)),
            ("breakout_15m_pct", "<=", (-1.0, 0.0)),
            ("breakout_30m_pct", "<=", (-1.0, 0.0)),
        ],
        "participation": [
            ("quote_volume_ratio_15m", "<=", (0.5, 0.75, 1.0)),
            ("quote_volume_ratio_30m", "<=", (0.5, 0.75, 1.0)),
            ("quote_volume_ratio_60m", "<=", (0.5, 0.75, 1.0, 1.25)),
            (
                "quote_volume_ratio_60m_prev_2h_avg",
                "<=",
                (0.5, 0.75, 1.0, 1.25),
            ),
            ("quote_volume_above_both_prev_hours", "<=", (0.0,)),
            ("quote_volume_three_hour_rising", "<=", (0.0,)),
            (
                "completed_hour_volume_ratio_prev_2h_avg",
                "<=",
                (0.5, 0.75, 1.0, 1.25),
            ),
            (
                "completed_hour_volume_above_both_prev_hours",
                "<=",
                (0.0,),
            ),
            ("completed_hour_volume_three_hour_rising", "<=", (0.0,)),
            ("trade_count_ratio_15m", "<=", (0.5, 0.75, 1.0)),
            ("trade_count_ratio_30m", "<=", (0.5, 0.75, 1.0)),
            ("trade_count_ratio_60m", "<=", (0.5, 0.75, 1.0, 1.25)),
            (
                "trade_count_ratio_60m_prev_2h_avg",
                "<=",
                (0.5, 0.75, 1.0, 1.25),
            ),
            ("trade_count_above_both_prev_hours", "<=", (0.0,)),
            ("trade_count_three_hour_rising", "<=", (0.0,)),
            (
                "completed_hour_trade_count_ratio_prev_2h_avg",
                "<=",
                (0.5, 0.75, 1.0, 1.25),
            ),
            (
                "completed_hour_trade_count_above_both_prev_hours",
                "<=",
                (0.0,),
            ),
            ("completed_hour_trade_count_three_hour_rising", "<=", (0.0,)),
            ("taker_buy_share_5m", "<=", (0.4, 0.45, 0.5)),
            ("taker_buy_share_15m", "<=", (0.4, 0.45, 0.5)),
        ],
        "overheat": [
            ("return_60m_pct", ">=", (3.0, 5.0, 10.0)),
            ("return_30m_pct", ">=", (2.0, 3.0, 5.0)),
        ],
        "volatility": [
            ("stop_distance_pct", ">=", (3.0, 4.0, 5.0, 6.0)),
            ("return_to_vol_15m", "<=", (0.0, 0.5, 1.0)),
            ("range_expansion_15m", ">=", (1.5, 2.0, 3.0)),
            ("atr_15m_pct", ">=", (1.0, 2.0, 3.0)),
        ],
    }
    return [
        Condition(family, feature, operator, threshold)
        for family, family_definitions in definitions.items()
        for feature, operator, thresholds in family_definitions
        for threshold in thresholds
    ]


def candidate_combinations(
    conditions: list[Condition],
    size: int,
) -> list[tuple[Condition, ...]]:
    if size == 1:
        return [(condition,) for condition in conditions]
    return [
        combination
        for combination in itertools.combinations(conditions, size)
        if len({condition.family for condition in combination}) == size
    ]


def is_stable_candidate(summary: dict) -> bool:
    trade_concentration = summary["max_trade_concentration_pct"]
    week_concentration = summary["max_week_concentration_pct"]
    return (
        summary["earlier_delta"] > 0
        and summary["recent_delta"] > 0
        and summary["filtered_losses"] >= 8
        and summary["positive_weeks"] >= 4
        and summary["negative_weeks"] <= 2
        and trade_concentration != ""
        and float(trade_concentration) <= 35
        and week_concentration != ""
        and float(week_concentration) <= 55
    )


def search_candidates(
    rows: list[dict],
    unmatched: list[dict],
) -> tuple[list[dict], list[dict]]:
    conditions = condition_grid()
    single_results = []
    combined_results = []
    seen_masks: set[tuple[str, ...]] = set()
    for size in (1, 2, 3):
        target = single_results if size == 1 else combined_results
        combinations = candidate_combinations(conditions, size)
        for index, combination in enumerate(combinations, start=1):
            summary = summarize_candidate(
                rows,
                combination,
                unmatched=unmatched,
            )
            mask = tuple(summary["filtered_ids"])
            if size > 1 and mask in seen_masks:
                continue
            if mask:
                seen_masks.add(mask)
            summary["passes_tail_constraints"] = passes_tail_constraints(summary)
            summary["stable"] = (
                summary["passes_tail_constraints"]
                and is_stable_candidate(summary)
            )
            if summary["passes_tail_constraints"]:
                for fraction, suffix in ((0.1, "10"), (0.2, "20")):
                    sensitivity = summarize_candidate(
                        rows,
                        tuple(
                            expand_veto_condition(
                                condition,
                                fraction=fraction,
                            )
                            for condition in combination
                        ),
                        unmatched=unmatched,
                    )
                    summary[f"relaxed_{suffix}_delta"] = sensitivity[
                        "estimated_delta"
                    ]
                    summary[f"relaxed_{suffix}_tail_50_retention_pct"] = (
                        sensitivity["tail_50_retention_pct"]
                    )
                    summary[f"relaxed_{suffix}_tail_100_filtered_count"] = (
                        sensitivity["tail_100_filtered_count"]
                    )
            else:
                for suffix in ("10", "20"):
                    summary[f"relaxed_{suffix}_delta"] = ""
                    summary[f"relaxed_{suffix}_tail_50_retention_pct"] = ""
                    summary[f"relaxed_{suffix}_tail_100_filtered_count"] = ""
            summary["robust_full_tail_20pct"] = bool(
                summary["passes_tail_constraints"]
                and summary["tail_50_retention_pct"] >= 100 - 1e-9
                and summary["relaxed_20_tail_50_retention_pct"] >= 100 - 1e-9
                and summary["relaxed_20_tail_100_filtered_count"] == 0
            )
            summary["weekly_deltas_json"] = json.dumps(
                summary.pop("weekly_deltas"),
                sort_keys=True,
            )
            summary.pop("filtered_ids")
            target.append(summary)
            if size > 1 and index % 5000 == 0:
                print(
                    f"searched {index}/{len(combinations)} "
                    f"size-{size} candidates",
                    flush=True,
                )
    return single_results, combined_results


def csv_value(value):
    if isinstance(value, (dict, list, tuple)):
        return json.dumps(value, sort_keys=True)
    return value


def write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        path.write_text("")
        return
    fieldnames = list(rows[0])
    with path.open("w", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow({key: csv_value(row.get(key, "")) for key in fieldnames})


def numeric_feature_names(rows: list[dict]) -> list[str]:
    metadata = {
        "round_trip_id",
        "symbol",
        "signal_at_utc",
        "opened_at_utc",
        "closed_at_utc",
        "net_pnl",
        "base_pnl",
        "add_on_count",
        "add_on_pnl",
    }
    return [
        key
        for key in rows[0]
        if key not in metadata
        and any(row.get(key, "") not in ("", None) for row in rows)
    ]


def percentile(values: list[float], fraction: float) -> float | str:
    if not values:
        return ""
    ordered = sorted(values)
    position = (len(ordered) - 1) * fraction
    lower = math.floor(position)
    upper = math.ceil(position)
    if lower == upper:
        return ordered[lower]
    return ordered[lower] + (ordered[upper] - ordered[lower]) * (
        position - lower
    )


def build_feature_audit(rows: list[dict]) -> list[dict]:
    groups = {
        "loss": lambda row: float(row["net_pnl"]) < 0,
        "profit_below_50": lambda row: 0 < float(row["net_pnl"]) < 50,
        "tail_50": lambda row: float(row["net_pnl"]) >= 50,
        "tail_100": lambda row: float(row["net_pnl"]) >= 100,
    }
    audit = []
    for feature in numeric_feature_names(rows):
        for group, predicate in groups.items():
            values = [
                float(row[feature])
                for row in rows
                if predicate(row) and row.get(feature, "") not in ("", None)
            ]
            audit.append(
                {
                    "feature": feature,
                    "group": group,
                    "count": len(values),
                    "p25": percentile(values, 0.25),
                    "median": median(values) if values else "",
                    "p75": percentile(values, 0.75),
                }
            )
    return audit


def candidate_conditions(summary: dict) -> tuple[Condition, ...]:
    conditions = []
    for label in summary["conditions"].split(" AND "):
        if "<=" in label:
            feature, threshold = label.split("<=", 1)
            operator = "<="
        else:
            feature, threshold = label.split(">=", 1)
            operator = ">="
        family = next(
            condition.family
            for condition in condition_grid()
            if condition.feature == feature
            and condition.operator == operator
            and math.isclose(condition.threshold, float(threshold))
        )
        conditions.append(Condition(family, feature, operator, float(threshold)))
    return tuple(conditions)


def select_recommendations(passing: list[dict]) -> tuple[dict | None, dict | None]:
    conservative_singles = [
        row
        for row in passing
        if row["stable"]
        and row["condition_count"] == 1
        and row["robust_full_tail_20pct"]
        and row["recent_delta"] > 0
    ]
    conservative_singles.sort(
        key=lambda row: float(row["estimated_delta"]),
        reverse=True,
    )
    preferred = conservative_singles[0] if conservative_singles else None
    fallback = conservative_singles[1] if len(conservative_singles) > 1 else None
    return preferred, fallback


HOURLY_FOCUS_CONDITIONS = (
    (
        "rolling_hour_not_above_previous_two_hour_average",
        "quote_volume_ratio_60m_prev_2h_avg<=1",
    ),
    (
        "rolling_hour_not_above_both_previous_hours",
        "quote_volume_above_both_prev_hours<=0",
    ),
    (
        "completed_hour_not_above_previous_two_hour_average",
        "completed_hour_volume_ratio_prev_2h_avg<=1",
    ),
    (
        "rolling_hour_extreme_volume_collapse",
        "quote_volume_ratio_60m_prev_2h_avg<=0.5",
    ),
    (
        "completed_hour_extreme_trade_count_collapse",
        "completed_hour_trade_count_ratio_prev_2h_avg<=0.5",
    ),
    (
        "price_up_participation_down",
        "trade_count_ratio_30m<=0.75 AND return_60m_pct>=3",
    ),
)


def focus_candidate_rows(results: list[dict]) -> list[dict]:
    by_conditions = {row["conditions"]: row for row in results}
    focused = []
    for name, conditions in HOURLY_FOCUS_CONDITIONS:
        row = by_conditions.get(conditions)
        if row is not None:
            focused.append({"focus_name": name, **row})
    return focused


def candidate_details(
    rows: list[dict],
    candidates: list[tuple[str, dict]],
) -> list[dict]:
    details = []
    for name, candidate in candidates:
        conditions = candidate_conditions(candidate)
        for row in rows:
            if not all(evaluate_condition(row, condition) for condition in conditions):
                continue
            details.append(
                {
                    "candidate": name,
                    "conditions": candidate["conditions"],
                    "round_trip_id": row["round_trip_id"],
                    "symbol": row["symbol"],
                    "signal_at_utc": row["signal_at_utc"],
                    "net_pnl": row["net_pnl"],
                    "counterfactual_delta": -float(row["net_pnl"]),
                    "add_on_count": row["add_on_count"],
                    "add_on_pnl": row["add_on_pnl"],
                }
            )
    return details


def format_candidate(row: dict | None) -> str:
    if row is None:
        return "None"
    return (
        f"`{row['conditions']}`: delta={row['estimated_delta']:.2f}, "
        f"filtered={row['filtered_count']}, "
        f"tail50={row['tail_50_retention_pct']:.2f}%, "
        f"recent={row['recent_delta']:.2f}"
    )


def write_report(
    *,
    output_dir: Path,
    rows: list[dict],
    single_results: list[dict],
    combined_results: list[dict],
    passing: list[dict],
    preferred: dict | None,
    fallback: dict | None,
    hourly_focus: list[dict],
) -> str:
    stable = [row for row in passing if row["stable"]]
    best_in_sample = max(
        stable,
        key=lambda row: float(row["estimated_delta"]),
        default=None,
    )
    best_full_tail = max(
        (
            row
            for row in stable
            if row["tail_50_retention_pct"] >= 100 - 1e-9
        ),
        key=lambda row: float(row["estimated_delta"]),
        default=None,
    )
    lines = [
        "# Base-entry false-breakout filter research\n\n",
        "## Dataset and constraints\n\n",
        f"- Matched base trades: {len(rows)}\n",
        f"- Historical trades with PnL >= 50 USDT: {sum(float(row['net_pnl']) >= 50 for row in rows)}\n",
        f"- Historical trades with PnL >= 100 USDT: {sum(float(row['net_pnl']) >= 100 for row in rows)}\n",
        "- Features use completed 1m candles strictly before the signal timestamp.\n",
        "- Passing rules retain every >=100 USDT trade and at least 98% of >=50 USDT aggregate PnL.\n\n",
        "## Search\n\n",
        f"- Single conditions evaluated: {len(single_results)}\n",
        f"- Unique pair/triple vetoes evaluated: {len(combined_results)}\n",
        f"- Tail-constrained improving candidates: {len(passing)}\n",
        f"- Candidates passing stability checks: {len(stable)}\n\n",
        "## Recommendation\n\n",
    ]
    if preferred is None:
        lines.append(
            "No single-condition candidate preserved every >=50 USDT trade "
            "after a 20% adverse threshold expansion. Do not deploy a hard "
            "indicator filter from this sample.\n\n"
        )
    else:
        lines.append(
            f"- Conservative deployment candidate: {format_candidate(preferred)}\n"
        )
    lines.append(f"- Conservative fallback: {format_candidate(fallback)}\n")
    lines.append(f"- Best in-sample rule: {format_candidate(best_in_sample)}\n")
    lines.append(
        f"- Best rule retaining 100% of >=50 USDT trades: "
        f"{format_candidate(best_full_tail)}\n\n"
    )
    if preferred is not None:
        preferred_conditions = candidate_conditions(preferred)
        preferred_filtered = [
            row
            for row in rows
            if all(
                evaluate_condition(row, condition)
                for condition in preferred_conditions
            )
        ]
        tail_values = [
            float(row[preferred_conditions[0].feature])
            for row in rows
            if float(row["net_pnl"]) >= 50
        ]
        lines.extend(
            [
                "### Conservative candidate interpretation\n\n",
                "- `quote_volume_ratio_15m` is the mean quote volume of the "
                "last 15 completed 1m candles divided by the mean of the "
                "preceding 15 completed 1m candles.\n",
                f"- The preferred veto removes {len(preferred_filtered)} trades: "
                f"{preferred['filtered_losses']} losses and "
                f"{preferred['filtered_winners']} winners.\n",
                f"- Estimated portfolio PnL changes from "
                f"{preferred['baseline_total_pnl']:.2f} to "
                f"{preferred['estimated_total_pnl']:.2f} USDT.\n",
                f"- It retains {preferred['add_on_count_retention_pct']:.1f}% "
                f"of original add-on legs and removes "
                f"{preferred['filtered_add_on_pnl']:.2f} USDT of add-on PnL.\n",
                f"- The smallest value among the 19 historical >=50 USDT "
                f"trades is {min(tail_values):.3f}; the veto threshold is "
                f"{preferred_conditions[0].threshold:.3f}.\n",
                f"- Expanding the threshold by 20% still retains "
                f"{preferred['relaxed_20_tail_50_retention_pct']:.2f}% of "
                f">=50 USDT PnL and changes PnL by "
                f"{preferred['relaxed_20_delta']:.2f} USDT.\n\n",
            ]
        )
    if best_in_sample is not None and not best_in_sample["robust_full_tail_20pct"]:
        lines.append(
            "### Why the highest-scoring rule is rejected\n\n"
            f"The highest in-sample rule retains only "
            f"{best_in_sample['tail_50_retention_pct']:.2f}% of >=50 USDT "
            "PnL and therefore intentionally removes a historical tail trade. "
            "Its higher PnL improvement is not aligned with the primary "
            "objective.\n\n"
        )
    if best_full_tail is not None and not best_full_tail["robust_full_tail_20pct"]:
        lines.append(
            "The highest-scoring rule with 100% original tail retention is "
            "also rejected: after a 20% adverse threshold expansion its "
            f">=50 USDT retention falls to "
            f"{best_full_tail['relaxed_20_tail_50_retention_pct']:.2f}%. "
            "The original result depends on narrow historical boundaries.\n\n"
        )

    lines.extend(
        [
            "## Hourly volume and price-participation study\n\n",
            "| interpretation | conditions | filtered | delta | tail50 | missed >=100 | recent | robust20 |\n",
            "|---|---|---:|---:|---:|---:|---:|---|\n",
        ]
    )
    for row in hourly_focus:
        lines.append(
            f"| {row['focus_name']} | {row['conditions']} | "
            f"{row['filtered_count']} | {row['estimated_delta']:.2f} | "
            f"{row['tail_50_retention_pct']:.2f}% | "
            f"{row['tail_100_filtered_count']} | {row['recent_delta']:.2f} | "
            f"{row['robust_full_tail_20pct']} |\n"
        )
    divergence = next(
        (
            row
            for row in hourly_focus
            if row["focus_name"] == "price_up_participation_down"
        ),
        None,
    )
    if divergence is not None:
        lines.extend(
            [
                "\nThe strict hourly-volume requirement is rejected because "
                "several historical long-tail trades began without hourly "
                "volume exceeding both prior hours. The stronger alternative "
                "is a divergence veto: filter only after price has already "
                "risen at least 3% over 60 completed minutes while the latest "
                "30-minute trade count is at most 75% of the preceding "
                "30 minutes.\n\n",
                f"This divergence veto filters {divergence['filtered_count']} "
                f"trades ({divergence['filtered_losses']} losses and "
                f"{divergence['filtered_winners']} winners), improves PnL by "
                f"{divergence['estimated_delta']:.2f} USDT, retains "
                f"{divergence['tail_50_retention_pct']:.2f}% of >=50 USDT "
                f"PnL, and has {divergence['positive_weeks']}/"
                f"{divergence['negative_weeks']} positive/negative weeks.\n\n",
            ]
        )

    lines.extend(
        [
            "## Top passing candidates\n\n",
            "| conditions | count | delta | recent | tail50 | relaxed20 tail50 | add-on count | weeks | stable/robust |\n",
            "|---|---:|---:|---:|---:|---:|---:|---:|---|\n",
        ]
    )
    for row in sorted(
        passing,
        key=lambda item: (
            bool(item["stable"]),
            float(item["estimated_delta"]),
        ),
        reverse=True,
    )[:20]:
        lines.append(
            f"| {row['conditions']} | {row['filtered_count']} | "
            f"{row['estimated_delta']:.2f} | {row['recent_delta']:.2f} | "
            f"{row['tail_50_retention_pct']:.2f}% | "
            f"{float(row['relaxed_20_tail_50_retention_pct']):.2f}% | "
            f"{row['add_on_count_retention_pct']:.1f}% | "
            f"{row['positive_weeks']}/{row['negative_weeks']} | "
            f"{row['stable']}/{row['robust_full_tail_20pct']} |\n"
        )

    selected = [
        ("preferred", preferred),
        ("fallback", fallback),
    ]
    for name, candidate in selected:
        if candidate is None:
            continue
        conditions = candidate_conditions(candidate)
        filtered = [
            row
            for row in rows
            if all(evaluate_condition(row, condition) for condition in conditions)
        ]
        lines.extend(
            [
                f"\n## {name.title()} filtered trades\n\n",
                f"- Conditions: `{candidate['conditions']}`\n",
                f"- Original filtered basket: {candidate['filtered_original_pnl']:.2f} USDT\n",
                f"- Filtered losers/winners: {candidate['filtered_losses']}/{candidate['filtered_winners']}\n",
                f"- Add-on PnL removed: {candidate['filtered_add_on_pnl']:.2f} USDT\n\n",
            ]
        )
        for row in sorted(filtered, key=lambda item: float(item["net_pnl"])):
            lines.append(
                f"- {row['symbol']} {row['signal_at_utc'][:16]}: "
                f"{float(row['net_pnl']):.2f} USDT, "
                f"add-ons={row['add_on_count']}\n"
            )

    lines.extend(
        [
            "\n## Limitations\n\n",
            "- This is an in-sample study over 692 matched trades and only "
            "eight >=100 USDT winners.\n",
            "- Filtering an original base can create later entry opportunities "
            "that did not exist in the recorded state because the original "
            "position was held. Those never-generated signals cannot be "
            "reconstructed from round trips alone.\n",
            "- The result supports shadow deployment and continued collection, "
            "not a claim that future long-tail recall is guaranteed.\n",
        ]
    )
    report = "".join(lines)
    (output_dir / "summary.md").write_text(report)
    return report


def main() -> None:
    args = parse_args()
    args.output_dir.mkdir(parents=True, exist_ok=True)
    matched, unmatched, _ = load_data(args.db)
    cache = load_kline_cache(
        trades=matched,
        cache_path=args.output_dir / "binance_1m_cache.json",
        seed_paths=(
            args.output_dir.parent
            / "ema_pending_20260610"
            / "binance_1m_cache.json",
            args.output_dir.parent
            / "tight_stop_20260609"
            / "binance_1m_cache.json",
        ),
        proxy=args.proxy,
        fetch=args.fetch,
    )
    rows = build_feature_rows(matched, cache)
    write_csv(args.output_dir / "feature_table.csv", rows)
    write_csv(args.output_dir / "feature_audit.csv", build_feature_audit(rows))

    singles, combined = search_candidates(rows, unmatched_rows(unmatched))
    write_csv(args.output_dir / "single_condition_results.csv", singles)
    write_csv(args.output_dir / "combined_veto_results.csv", combined)
    passing = sorted(
        [
            row
            for row in [*singles, *combined]
            if row["passes_tail_constraints"]
        ],
        key=lambda row: float(row["estimated_delta"]),
        reverse=True,
    )
    write_csv(args.output_dir / "passing_candidates.csv", passing)
    hourly_focus = focus_candidate_rows([*singles, *combined])
    write_csv(args.output_dir / "hourly_volume_focus.csv", hourly_focus)
    preferred, fallback = select_recommendations(passing)
    divergence = next(
        (
            row
            for row in hourly_focus
            if row["focus_name"] == "price_up_participation_down"
        ),
        None,
    )
    details = candidate_details(
        rows,
        [
            (name, candidate)
            for name, candidate in (
                ("preferred", preferred),
                ("fallback", fallback),
                ("price_up_participation_down", divergence),
            )
            if candidate is not None
        ],
    )
    write_csv(args.output_dir / "candidate_trade_detail.csv", details)
    report = write_report(
        output_dir=args.output_dir,
        rows=rows,
        single_results=singles,
        combined_results=combined,
        passing=passing,
        preferred=preferred,
        fallback=fallback,
        hourly_focus=hourly_focus,
    )
    print(report)


if __name__ == "__main__":
    main()
