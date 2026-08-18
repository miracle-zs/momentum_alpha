from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import sqrt
from statistics import pstdev


_ONE_HUNDRED = Decimal("100")
_ONE_MINUTE_MS = 60_000
_FEATURE_CANDLE_LIMIT = 60


@dataclass(frozen=True)
class BaseVetoFeatures:
    """Causal features used by the Base veto.

    Values are computed only from candles whose close time is before the
    current decision timestamp.  ``None`` means that the feature is not
    available; callers should fail open in that case.
    """

    atr_15m_pct: Decimal | None = None
    trade_count_ratio_30m: Decimal | None = None
    return_to_vol_15m: Decimal | None = None
    completed_candle_count: int = 0
    as_of: datetime | None = None
    unavailable_reason: str | None = None

    @property
    def data_ready(self) -> bool:
        return (
            self.completed_candle_count >= _FEATURE_CANDLE_LIMIT
            and self.atr_15m_pct is not None
            and self.trade_count_ratio_30m is not None
            and self.return_to_vol_15m is not None
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable telemetry names for audit and long-tail analysis."""

        values: dict[str, object] = {
            "atr_15m_pct": _decimal_text(self.atr_15m_pct),
            "trade_count_ratio_30m": _decimal_text(self.trade_count_ratio_30m),
            "return_to_vol_15m": _decimal_text(self.return_to_vol_15m),
            "base_veto_atr_15m_pct": _decimal_text(self.atr_15m_pct),
            "base_veto_trade_count_ratio_30m": _decimal_text(self.trade_count_ratio_30m),
            "base_veto_return_to_vol_15m": _decimal_text(self.return_to_vol_15m),
            "base_veto_completed_candle_count": self.completed_candle_count,
            "base_veto_feature_data_ready": self.data_ready,
            "base_veto_feature_unavailable_reason": self.unavailable_reason,
            "base_veto_features_as_of": (
                self.as_of.astimezone(timezone.utc).isoformat()
                if self.as_of is not None
                else None
            ),
        }
        return values


@dataclass(frozen=True)
class BaseVetoDecision:
    enabled: bool
    triggered: bool
    rule: str | None
    atr_triggered: bool
    composite_triggered: bool

    def to_payload(self) -> dict[str, object]:
        return {
            "base_veto_enabled": self.enabled,
            "base_veto_triggered": self.triggered,
            "base_veto_rule": self.rule,
            "base_veto_atr_triggered": self.atr_triggered,
            "base_veto_composite_triggered": self.composite_triggered,
        }


def _decimal_text(value: Decimal | None) -> str | None:
    return str(value) if value is not None else None


def evaluate_base_veto(
    features: BaseVetoFeatures | None,
    *,
    enabled: bool = True,
    atr_15m_pct_threshold: Decimal = Decimal("3"),
    trade_count_ratio_30m_threshold: Decimal = Decimal("1"),
    return_to_vol_15m_threshold: Decimal = Decimal("0.5"),
) -> BaseVetoDecision:
    """Evaluate the agreed A OR B Base veto without using future data."""

    features_ready = bool(
        features is not None
        and features.completed_candle_count >= _FEATURE_CANDLE_LIMIT
    )
    atr_triggered = bool(
        features_ready
        and features is not None
        and features.atr_15m_pct is not None
        and features.atr_15m_pct >= atr_15m_pct_threshold
    )
    composite_triggered = bool(
        features_ready
        and features is not None
        and features.trade_count_ratio_30m is not None
        and features.return_to_vol_15m is not None
        and features.trade_count_ratio_30m <= trade_count_ratio_30m_threshold
        and features.return_to_vol_15m <= return_to_vol_15m_threshold
    )
    triggered = bool(enabled and (atr_triggered or composite_triggered))
    if not triggered:
        rule = None
    elif atr_triggered and composite_triggered:
        rule = "A_OR_B"
    elif atr_triggered:
        rule = "A"
    else:
        rule = "B"
    return BaseVetoDecision(
        enabled=enabled,
        triggered=triggered,
        rule=rule,
        atr_triggered=atr_triggered,
        composite_triggered=composite_triggered,
    )


def _parse_candle(row: list | tuple) -> tuple[int, Decimal, Decimal, Decimal, Decimal, int] | None:
    if len(row) < 9:
        return None
    try:
        open_time_ms = int(row[0])
        open_price = Decimal(str(row[1]))
        high_price = Decimal(str(row[2]))
        low_price = Decimal(str(row[3]))
        close_price = Decimal(str(row[4]))
        trades = int(row[8])
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return None
    if not all(
        value.is_finite()
        for value in (open_price, high_price, low_price, close_price)
    ):
        return None
    return (
        open_time_ms,
        open_price,
        high_price,
        low_price,
        close_price,
        trades,
    )


def _completed_candles(
    *,
    klines: list,
    signal_at: datetime,
) -> list[tuple[int, Decimal, Decimal, Decimal, Decimal, int]]:
    resolved_signal_at = (
        signal_at.replace(tzinfo=timezone.utc)
        if signal_at.tzinfo is None
        else signal_at.astimezone(timezone.utc)
    )
    signal_ms = int(resolved_signal_at.timestamp() * 1000)
    parsed: dict[int, tuple[int, Decimal, Decimal, Decimal, Decimal, int]] = {}
    for row in klines:
        if len(row) < 7:
            continue
        try:
            close_time_ms = int(row[6])
        except (TypeError, ValueError):
            continue
        if close_time_ms >= signal_ms:
            continue
        candle = _parse_candle(row)
        if candle is not None:
            parsed[candle[0]] = candle
    return [parsed[open_time] for open_time in sorted(parsed)]


def _is_contiguous(candles: list[tuple[int, Decimal, Decimal, Decimal, Decimal, int]]) -> bool:
    return all(
        candles[index][0] - candles[index - 1][0] == _ONE_MINUTE_MS
        for index in range(1, len(candles))
    )


def compute_base_veto_features(*, klines: list, signal_at: datetime) -> BaseVetoFeatures:
    """Compute A/B inputs from completed, contiguous 1m Binance klines."""

    candles = _completed_candles(klines=klines, signal_at=signal_at)
    if len(candles) < _FEATURE_CANDLE_LIMIT:
        return BaseVetoFeatures(
            completed_candle_count=len(candles),
            unavailable_reason="insufficient_completed_candles",
        )

    candles = candles[-_FEATURE_CANDLE_LIMIT:]
    if not _is_contiguous(candles):
        return BaseVetoFeatures(
            completed_candle_count=len(candles),
            unavailable_reason="non_contiguous_completed_candles",
        )

    closes = [candle[4] for candle in candles]
    last_close = closes[-1]
    if last_close <= 0:
        return BaseVetoFeatures(
            completed_candle_count=len(candles),
            unavailable_reason="non_positive_close",
        )

    true_ranges: list[Decimal] = []
    previous_close: Decimal | None = None
    for _, _, high, low, close, _ in candles:
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = close

    atr_15m_pct = (
        sum(true_ranges[-15:], Decimal("0")) / Decimal("15") / last_close * _ONE_HUNDRED
    )
    recent_trades = sum(candle[5] for candle in candles[-30:])
    prior_trades = sum(candle[5] for candle in candles[-60:-30])
    trade_count_ratio_30m = (
        Decimal(recent_trades) / Decimal(prior_trades)
        if prior_trades > 0
        else None
    )

    return_window = closes[-16:]
    returns = [
        float(return_window[index] / return_window[index - 1] - Decimal("1"))
        for index in range(1, len(return_window))
        if return_window[index - 1] > 0
    ]
    return_to_vol_15m: Decimal | None = None
    if len(returns) == 15 and return_window[0] > 0:
        period_return_pct = (return_window[-1] / return_window[0] - Decimal("1")) * _ONE_HUNDRED
        realized_volatility_pct = Decimal(str(pstdev(returns) * sqrt(len(returns)) * 100))
        if realized_volatility_pct != 0:
            return_to_vol_15m = period_return_pct / realized_volatility_pct

    as_of = datetime.fromtimestamp((candles[-1][0] + _ONE_MINUTE_MS) / 1000, tz=timezone.utc)
    return BaseVetoFeatures(
        atr_15m_pct=atr_15m_pct,
        trade_count_ratio_30m=trade_count_ratio_30m,
        return_to_vol_15m=return_to_vol_15m,
        completed_candle_count=len(candles),
        as_of=as_of,
    )
