from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation
from math import sqrt
from statistics import pstdev


_ONE_HUNDRED = Decimal("100")
_ONE_MINUTE_MS = 60_000
_FEATURE_CANDLE_LIMIT = 60
_FIVE_MINUTES = 5
_FIFTEEN_MINUTES = 15
_THIRTY_MINUTES = 30

_Candle = tuple[
    int,
    Decimal,
    Decimal,
    Decimal,
    Decimal,
    Decimal | None,
    Decimal | None,
    int,
]


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
    taker_buy_share_15m: Decimal | None = None
    efficiency_15m: Decimal | None = None
    range_expansion_15m: Decimal | None = None
    breakout_5m_pct: Decimal | None = None
    pullback_5m_pct: Decimal | None = None

    @property
    def data_ready(self) -> bool:
        return (
            self.completed_candle_count >= _FEATURE_CANDLE_LIMIT
            and self.atr_15m_pct is not None
            and self.trade_count_ratio_30m is not None
            and self.return_to_vol_15m is not None
            and self.taker_buy_share_15m is not None
            and self.efficiency_15m is not None
            and self.range_expansion_15m is not None
            and self.breakout_5m_pct is not None
            and self.pullback_5m_pct is not None
        )

    def to_payload(self) -> dict[str, object]:
        """Return stable telemetry names for audit and long-tail analysis."""

        values: dict[str, object] = {
            "atr_15m_pct": _decimal_text(self.atr_15m_pct),
            "trade_count_ratio_30m": _decimal_text(self.trade_count_ratio_30m),
            "return_to_vol_15m": _decimal_text(self.return_to_vol_15m),
            "taker_buy_share_15m": _decimal_text(self.taker_buy_share_15m),
            "efficiency_15m": _decimal_text(self.efficiency_15m),
            "range_expansion_15m": _decimal_text(self.range_expansion_15m),
            "breakout_5m_pct": _decimal_text(self.breakout_5m_pct),
            "pullback_5m_pct": _decimal_text(self.pullback_5m_pct),
            "base_veto_atr_15m_pct": _decimal_text(self.atr_15m_pct),
            "base_veto_trade_count_ratio_30m": _decimal_text(self.trade_count_ratio_30m),
            "base_veto_return_to_vol_15m": _decimal_text(self.return_to_vol_15m),
            "base_veto_taker_buy_share_15m": _decimal_text(self.taker_buy_share_15m),
            "base_veto_efficiency_15m": _decimal_text(self.efficiency_15m),
            "base_veto_range_expansion_15m": _decimal_text(self.range_expansion_15m),
            "base_veto_breakout_5m_pct": _decimal_text(self.breakout_5m_pct),
            "base_veto_pullback_5m_pct": _decimal_text(self.pullback_5m_pct),
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
    c_triggered: bool = False
    d_triggered: bool = False
    e_triggered: bool = False
    breakout_triggered: bool = False

    def to_payload(self) -> dict[str, object]:
        return {
            "base_veto_enabled": self.enabled,
            "base_veto_triggered": self.triggered,
            "base_veto_rule": self.rule,
            "base_veto_a_triggered": self.atr_triggered,
            "base_veto_b_triggered": self.composite_triggered,
            "base_veto_atr_triggered": self.atr_triggered,
            "base_veto_composite_triggered": self.composite_triggered,
            "base_veto_c_triggered": self.c_triggered,
            "base_veto_d_triggered": self.d_triggered,
            "base_veto_e_triggered": self.e_triggered,
            "base_veto_breakout_triggered": self.breakout_triggered,
            "base_veto_abcde_triggered": bool(
                self.atr_triggered
                or self.composite_triggered
                or self.c_triggered
                or self.d_triggered
                or self.e_triggered
            ),
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
    trade_count_ratio_30m_c_threshold: Decimal = Decimal("0.75"),
    taker_buy_share_15m_threshold: Decimal = Decimal("0.50"),
    efficiency_15m_d_threshold: Decimal = Decimal("0.15"),
    efficiency_15m_e_threshold: Decimal = Decimal("0.45"),
    range_expansion_15m_threshold: Decimal = Decimal("1.50"),
    breakout_5m_pct_threshold: Decimal = Decimal("0.50"),
    pullback_5m_pct_threshold: Decimal = Decimal("1.25"),
) -> BaseVetoDecision:
    """Evaluate the causal Base veto and the shadow breakout observation.

    A--E are live false-signal veto candidates and remain OR'ed together.
    Breakout is evaluated separately as a shadow-only observation: it is
    returned in ``breakout_triggered`` for telemetry, but it cannot veto a
    Base entry by itself.  Missing inputs fail open for the affected clause.
    """

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
    c_triggered = bool(
        features_ready
        and features is not None
        and features.trade_count_ratio_30m is not None
        and features.trade_count_ratio_30m <= trade_count_ratio_30m_c_threshold
    )
    d_triggered = bool(
        features_ready
        and features is not None
        and features.taker_buy_share_15m is not None
        and features.efficiency_15m is not None
        and features.taker_buy_share_15m <= taker_buy_share_15m_threshold
        and features.efficiency_15m <= efficiency_15m_d_threshold
    )
    e_triggered = bool(
        features_ready
        and features is not None
        and features.efficiency_15m is not None
        and features.range_expansion_15m is not None
        and features.efficiency_15m <= efficiency_15m_e_threshold
        and features.range_expansion_15m >= range_expansion_15m_threshold
    )
    breakout_triggered = bool(
        features_ready
        and features is not None
        and features.breakout_5m_pct is not None
        and features.pullback_5m_pct is not None
        and features.breakout_5m_pct >= breakout_5m_pct_threshold
        and features.pullback_5m_pct <= pullback_5m_pct_threshold
    )
    live_triggered_rules = [
        label
        for label, value in (
            ("A", atr_triggered),
            ("B", composite_triggered),
            ("C", c_triggered),
            ("D", d_triggered),
            ("E", e_triggered),
        )
        if value
    ]
    triggered = bool(enabled and live_triggered_rules)
    if not triggered:
        rule = None
    elif live_triggered_rules == ["A", "B"]:
        rule = "A_OR_B"
    else:
        rule = "+".join(live_triggered_rules)
    return BaseVetoDecision(
        enabled=enabled,
        triggered=triggered,
        rule=rule,
        atr_triggered=atr_triggered,
        composite_triggered=composite_triggered,
        c_triggered=c_triggered,
        d_triggered=d_triggered,
        e_triggered=e_triggered,
        breakout_triggered=breakout_triggered,
    )


def _parse_candle(row: list | tuple) -> _Candle | None:
    if len(row) < 9:
        return None
    try:
        open_time_ms = int(row[0])
        open_price = Decimal(str(row[1]))
        high_price = Decimal(str(row[2]))
        low_price = Decimal(str(row[3]))
        close_price = Decimal(str(row[4]))
        quote_volume = Decimal(str(row[7])) if len(row) > 7 else None
        trades = int(row[8])
        taker_buy_quote = Decimal(str(row[10])) if len(row) > 10 else None
    except (ArithmeticError, InvalidOperation, TypeError, ValueError):
        return None
    if not all(
        value.is_finite()
        for value in (open_price, high_price, low_price, close_price)
    ):
        return None
    if quote_volume is not None and not quote_volume.is_finite():
        quote_volume = None
    if taker_buy_quote is not None and not taker_buy_quote.is_finite():
        taker_buy_quote = None
    return (
        open_time_ms,
        open_price,
        high_price,
        low_price,
        close_price,
        quote_volume,
        taker_buy_quote,
        trades,
    )


def _completed_candles(
    *,
    klines: list,
    signal_at: datetime,
) -> list[_Candle]:
    resolved_signal_at = (
        signal_at.replace(tzinfo=timezone.utc)
        if signal_at.tzinfo is None
        else signal_at.astimezone(timezone.utc)
    )
    signal_ms = int(resolved_signal_at.timestamp() * 1000)
    parsed: dict[int, _Candle] = {}
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


def _is_contiguous(candles: list[_Candle]) -> bool:
    return all(
        candles[index][0] - candles[index - 1][0] == _ONE_MINUTE_MS
        for index in range(1, len(candles))
    )


def compute_base_veto_features(*, klines: list, signal_at: datetime) -> BaseVetoFeatures:
    """Compute combined-veto inputs from completed, contiguous 1m klines."""

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
    for _, _, high, low, close, _, _, _ in candles:
        if previous_close is None:
            true_range = high - low
        else:
            true_range = max(high - low, abs(high - previous_close), abs(low - previous_close))
        true_ranges.append(true_range)
        previous_close = close

    atr_15m_pct = (
        sum(true_ranges[-15:], Decimal("0")) / Decimal("15") / last_close * _ONE_HUNDRED
    )
    recent_trades = sum(candle[7] for candle in candles[-_THIRTY_MINUTES:])
    prior_trades = sum(candle[7] for candle in candles[-60:-_THIRTY_MINUTES])
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

    quote_volume_15m = [candle[5] for candle in candles[-_FIFTEEN_MINUTES:]]
    taker_buy_quote_15m = [candle[6] for candle in candles[-_FIFTEEN_MINUTES:]]
    taker_buy_share_15m: Decimal | None = None
    if all(value is not None for value in (*quote_volume_15m, *taker_buy_quote_15m)):
        quote_total = sum((value for value in quote_volume_15m if value is not None), Decimal("0"))
        taker_total = sum((value for value in taker_buy_quote_15m if value is not None), Decimal("0"))
        if quote_total > 0:
            taker_buy_share_15m = taker_total / quote_total

    path_length = sum(
        abs(return_window[index] - return_window[index - 1])
        for index in range(1, len(return_window))
    )
    efficiency_15m = (
        abs(return_window[-1] - return_window[0]) / path_length
        if path_length > 0
        else Decimal("0")
    )

    recent_range_mean = sum(true_ranges[-_FIFTEEN_MINUTES:], Decimal("0")) / Decimal(str(_FIFTEEN_MINUTES))
    prior_range_mean = sum(true_ranges[-_THIRTY_MINUTES:-_FIFTEEN_MINUTES], Decimal("0")) / Decimal(str(_FIFTEEN_MINUTES))
    range_expansion_15m = (
        recent_range_mean / prior_range_mean
        if prior_range_mean > 0
        else None
    )

    prior_breakout_high = max(
        (candle[2] for candle in candles[-(_FIVE_MINUTES + 1):-1]),
        default=Decimal("0"),
    )
    breakout_5m_pct = (
        (last_close / prior_breakout_high - Decimal("1")) * _ONE_HUNDRED
        if prior_breakout_high > 0
        else None
    )
    rolling_high_5m = max(
        (candle[2] for candle in candles[-_FIVE_MINUTES:]),
        default=Decimal("0"),
    )
    pullback_5m_pct = (
        (rolling_high_5m - last_close) / rolling_high_5m * _ONE_HUNDRED
        if rolling_high_5m > 0
        else None
    )

    unavailable_reason = None
    if any(
        value is None
        for value in (
            taker_buy_share_15m,
            efficiency_15m,
            range_expansion_15m,
            breakout_5m_pct,
            pullback_5m_pct,
        )
    ):
        unavailable_reason = "extended_feature_unavailable"

    as_of = datetime.fromtimestamp((candles[-1][0] + _ONE_MINUTE_MS) / 1000, tz=timezone.utc)
    return BaseVetoFeatures(
        atr_15m_pct=atr_15m_pct,
        trade_count_ratio_30m=trade_count_ratio_30m,
        return_to_vol_15m=return_to_vol_15m,
        completed_candle_count=len(candles),
        as_of=as_of,
        unavailable_reason=unavailable_reason,
        taker_buy_share_15m=taker_buy_share_15m,
        efficiency_15m=efficiency_15m,
        range_expansion_15m=range_expansion_15m,
        breakout_5m_pct=breakout_5m_pct,
        pullback_5m_pct=pullback_5m_pct,
    )
