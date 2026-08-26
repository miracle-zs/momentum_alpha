from __future__ import annotations

from dataclasses import dataclass, replace
from datetime import date, datetime, time as datetime_time, timedelta, timezone
from decimal import Decimal
from pathlib import Path

from momentum_alpha.binance_filters import SymbolFilters
from momentum_alpha.sizing import size_from_stop_budget
from momentum_alpha.skipped_base_replay_data import (
    BinanceKlineCache,
    KlineFetchError,
    ReplayCandle,
    ReplaySeed,
    load_replay_inputs,
)


@dataclass(frozen=True)
class ShadowReplayEvent:
    shadow_opportunity_id: str
    symbol: str
    timestamp: datetime
    event_type: str
    price: Decimal | None = None
    stop_price: Decimal | None = None
    quantity: Decimal | None = None
    reason: str | None = None


@dataclass(frozen=True)
class ShadowLegResult:
    shadow_opportunity_id: str
    leg_type: str
    sequence: int
    opened_at: datetime
    entry_price: Decimal
    stop_at_entry: Decimal
    quantity: Decimal
    risk_budget: Decimal
    entry_fee: Decimal
    closed_at: datetime | None
    exit_price: Decimal | None
    gross_pnl: Decimal | None
    net_contribution: Decimal | None


@dataclass(frozen=True)
class ShadowReplayResult:
    shadow_opportunity_id: str
    symbol: str
    base_signal_at: datetime
    base_signal_sequence: int
    first_base_signal_at: datetime
    status: str
    base_entry_price: Decimal | None
    initial_stop_price: Decimal | None
    base_quantity: Decimal | None
    add_on_count: int
    skipped_add_on_count: int
    exit_at: datetime | None
    exit_price: Decimal | None
    duration_minutes: Decimal | None
    gross_pnl: Decimal | None
    entry_fees: Decimal | None
    exit_fees: Decimal | None
    net_pnl: Decimal | None
    mark_price_at_cutoff: Decimal | None
    mark_to_market_net_pnl: Decimal | None
    legs: tuple[ShadowLegResult, ...]
    events: tuple[ShadowReplayEvent, ...]
    warnings: tuple[str, ...]
    blocked_reason: str | None = None


@dataclass(frozen=True)
class ShadowOverlap:
    shadow_opportunity_id: str
    symbol: str
    signal_at: datetime
    active_shadow_opportunity_id: str
    status: str = "overlap_existing_shadow"


@dataclass(frozen=True)
class ShadowSuppression:
    """A filtered seed that would not create a Base in a continuous replay."""

    shadow_opportunity_id: str
    symbol: str
    signal_at: datetime
    reason: str
    active_shadow_opportunity_id: str | None = None


@dataclass(frozen=True)
class ShadowReplayReport:
    seed_count: int
    opportunities: tuple[ShadowReplayResult, ...]
    overlaps: tuple[ShadowOverlap, ...]
    warnings: tuple[str, ...]
    had_fetch_errors: bool = False
    suppressed: tuple[ShadowSuppression, ...] = ()
    replay_mode: str = "independent"


@dataclass(frozen=True)
class _OpenLeg:
    leg_type: str
    sequence: int
    opened_at: datetime
    entry_price: Decimal
    stop_at_entry: Decimal
    quantity: Decimal
    risk_budget: Decimal
    entry_fee: Decimal


def _utc(value: datetime) -> datetime:
    if value.tzinfo is None:
        return value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc)


def _unresolved_result(
    *,
    seed: ReplaySeed,
    warnings: list[str],
    events: list[ShadowReplayEvent] | None = None,
) -> ShadowReplayResult:
    unresolved_events = list(events or [])
    unresolved_events.append(
        ShadowReplayEvent(
            shadow_opportunity_id=seed.shadow_opportunity_id,
            symbol=seed.symbol,
            timestamp=seed.signal_at,
            event_type="unresolved",
            reason=";".join(warnings),
        )
    )
    return ShadowReplayResult(
        shadow_opportunity_id=seed.shadow_opportunity_id,
        symbol=seed.symbol,
        base_signal_at=seed.signal_at,
        base_signal_sequence=seed.base_signal_sequence,
        first_base_signal_at=seed.first_base_signal_at,
        status="unresolved",
        base_entry_price=seed.latest_price,
        initial_stop_price=seed.stop_price,
        base_quantity=None,
        add_on_count=0,
        skipped_add_on_count=0,
        exit_at=None,
        exit_price=None,
        duration_minutes=None,
        gross_pnl=None,
        entry_fees=None,
        exit_fees=None,
        net_pnl=None,
        mark_price_at_cutoff=None,
        mark_to_market_net_pnl=None,
        legs=(),
        events=tuple(unresolved_events),
        warnings=tuple(warnings),
        blocked_reason=seed.blocked_reason,
    )


def _closed_legs(
    *,
    shadow_opportunity_id: str,
    legs: list[_OpenLeg],
    exit_at: datetime,
    exit_price: Decimal,
    taker_fee_rate: Decimal,
) -> tuple[ShadowLegResult, ...]:
    return tuple(
        ShadowLegResult(
            shadow_opportunity_id=shadow_opportunity_id,
            leg_type=leg.leg_type,
            sequence=leg.sequence,
            opened_at=leg.opened_at,
            entry_price=leg.entry_price,
            stop_at_entry=leg.stop_at_entry,
            quantity=leg.quantity,
            risk_budget=leg.risk_budget,
            entry_fee=leg.entry_fee,
            closed_at=exit_at,
            exit_price=exit_price,
            gross_pnl=leg.quantity * (exit_price - leg.entry_price),
            net_contribution=(
                leg.quantity * (exit_price - leg.entry_price)
                - leg.entry_fee
                - leg.quantity * exit_price * taker_fee_rate
            ),
        )
        for leg in legs
    )


def _open_legs(
    *,
    shadow_opportunity_id: str,
    legs: list[_OpenLeg],
) -> tuple[ShadowLegResult, ...]:
    return tuple(
        ShadowLegResult(
            shadow_opportunity_id=shadow_opportunity_id,
            leg_type=leg.leg_type,
            sequence=leg.sequence,
            opened_at=leg.opened_at,
            entry_price=leg.entry_price,
            stop_at_entry=leg.stop_at_entry,
            quantity=leg.quantity,
            risk_budget=leg.risk_budget,
            entry_fee=leg.entry_fee,
            closed_at=None,
            exit_price=None,
            gross_pnl=None,
            net_contribution=None,
        )
        for leg in legs
    )


def _full_position_net_pnl_at_stop(
    *,
    legs: list[_OpenLeg],
    candidate_quantity: Decimal,
    candidate_entry_price: Decimal,
    stop_price: Decimal,
    taker_fee_rate: Decimal,
) -> Decimal:
    """Estimate the whole position's net PnL if stopped at ``stop_price``."""
    gross_pnl = Decimal("0")
    entry_notional = Decimal("0")
    total_quantity = Decimal("0")
    for leg in legs:
        gross_pnl += (stop_price - leg.entry_price) * leg.quantity
        entry_notional += leg.entry_price * leg.quantity
        total_quantity += leg.quantity
    gross_pnl += (stop_price - candidate_entry_price) * candidate_quantity
    entry_notional += candidate_entry_price * candidate_quantity
    total_quantity += candidate_quantity
    exit_notional = stop_price * total_quantity
    return gross_pnl - taker_fee_rate * (entry_notional + exit_notional)


def replay_shadow_seed(
    *,
    seed: ReplaySeed,
    candles: list[ReplayCandle],
    leaders: dict[datetime, str],
    cutoff: datetime,
    taker_fee_rate: Decimal,
    first_add_on_min_hold_minutes: int = 30,
    enforce_full_position_coverage: bool = True,
) -> ShadowReplayResult:
    warnings = list(seed.warnings)
    required = {
        "latest_price": seed.latest_price,
        "stop_price": seed.stop_price,
        "stop_budget_usdt": seed.stop_budget_usdt,
        "step_size": seed.step_size,
        "min_qty": seed.min_qty,
        "tick_size": seed.tick_size,
    }
    missing = [name for name, value in required.items() if value is None]
    if missing:
        warnings.append(f"missing_sizing_inputs:{','.join(missing)}")
        return _unresolved_result(seed=seed, warnings=warnings)

    assert seed.latest_price is not None
    assert seed.stop_price is not None
    assert seed.stop_budget_usdt is not None
    assert seed.step_size is not None
    assert seed.min_qty is not None
    assert seed.tick_size is not None
    filters = SymbolFilters(
        step_size=seed.step_size,
        min_qty=seed.min_qty,
        tick_size=seed.tick_size,
    )
    base_quantity = size_from_stop_budget(
        seed.latest_price,
        seed.stop_price,
        seed.stop_budget_usdt,
        filters,
    )
    if base_quantity is None:
        warnings.append("invalid_base_sizing")
        return _unresolved_result(seed=seed, warnings=warnings)

    signal_at = _utc(seed.signal_at)
    cutoff_utc = _utc(cutoff)
    signal_minute = signal_at.replace(second=0, microsecond=0)
    ordered_candles = sorted(
        [
            candle
            for candle in candles
            if _utc(candle.close_time) <= cutoff_utc
        ],
        key=lambda candle: candle.open_time,
    )
    eligible_candles = [
        candle
        for candle in ordered_candles
        if _utc(candle.open_time) >= signal_minute
    ]
    if not eligible_candles:
        warnings.append("missing_post_signal_candles")
        return _unresolved_result(seed=seed, warnings=warnings)

    legs = [
        _OpenLeg(
            leg_type="base",
            sequence=0,
            opened_at=signal_at,
            entry_price=seed.latest_price,
            stop_at_entry=seed.stop_price,
            quantity=base_quantity,
            risk_budget=seed.stop_budget_usdt,
            entry_fee=base_quantity * seed.latest_price * taker_fee_rate,
        )
    ]
    events = [
        ShadowReplayEvent(
            shadow_opportunity_id=seed.shadow_opportunity_id,
            symbol=seed.symbol,
            timestamp=signal_at,
            event_type="base_entry",
            price=seed.latest_price,
            stop_price=seed.stop_price,
            quantity=base_quantity,
        )
    ]
    active_stop = seed.stop_price
    add_on_count = 0
    skipped_add_on_count = 0
    hour_candles: dict[datetime, list[ReplayCandle]] = {}

    for candle in ordered_candles:
        candle_open = _utc(candle.open_time)
        hour_start = candle_open.replace(minute=0, second=0, microsecond=0)
        hour_candles.setdefault(hour_start, []).append(candle)
        if candle_open < signal_minute:
            continue

        if candle.low_price <= active_stop:
            exit_at = _utc(candle.close_time)
            exit_price = active_stop
            closed_legs = _closed_legs(
                shadow_opportunity_id=seed.shadow_opportunity_id,
                legs=legs,
                exit_at=exit_at,
                exit_price=exit_price,
                taker_fee_rate=taker_fee_rate,
            )
            gross_pnl = sum(
                (leg.gross_pnl or Decimal("0"))
                for leg in closed_legs
            )
            entry_fees = sum(leg.entry_fee for leg in closed_legs)
            total_quantity = sum(leg.quantity for leg in closed_legs)
            exit_fees = total_quantity * exit_price * taker_fee_rate
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=exit_at,
                    event_type="stop_exit",
                    price=exit_price,
                    stop_price=active_stop,
                    quantity=total_quantity,
                )
            )
            return ShadowReplayResult(
                shadow_opportunity_id=seed.shadow_opportunity_id,
                symbol=seed.symbol,
                base_signal_at=signal_at,
                base_signal_sequence=seed.base_signal_sequence,
                first_base_signal_at=seed.first_base_signal_at,
                status="closed",
                base_entry_price=seed.latest_price,
                initial_stop_price=seed.stop_price,
                base_quantity=base_quantity,
                add_on_count=add_on_count,
                skipped_add_on_count=skipped_add_on_count,
                exit_at=exit_at,
                exit_price=exit_price,
                duration_minutes=Decimal(str((exit_at - signal_at).total_seconds())) / Decimal("60"),
                gross_pnl=gross_pnl,
                entry_fees=entry_fees,
                exit_fees=exit_fees,
                net_pnl=gross_pnl - entry_fees - exit_fees,
                mark_price_at_cutoff=None,
                mark_to_market_net_pnl=None,
                legs=closed_legs,
                events=tuple(events),
                warnings=tuple(warnings),
                blocked_reason=seed.blocked_reason,
            )

        if candle_open.minute != 59:
            continue
        boundary = hour_start + timedelta(hours=1)
        if boundary <= signal_at:
            continue
        completed_hour = hour_candles.get(hour_start, [])
        minute_set = {item.open_time.astimezone(timezone.utc).minute for item in completed_hour}
        if len(completed_hour) != 60 or minute_set != set(range(60)):
            skipped_add_on_count += 1
            warnings.append(f"missing_previous_hour_candles:{boundary.isoformat()}")
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=boundary,
                    event_type="add_on_skipped",
                    reason="missing_previous_hour_candles",
                )
            )
            continue

        active_stop = max(active_stop, min(item.low_price for item in completed_hour))
        events.append(
            ShadowReplayEvent(
                shadow_opportunity_id=seed.shadow_opportunity_id,
                symbol=seed.symbol,
                timestamp=boundary,
                event_type="stop_update",
                stop_price=active_stop,
            )
        )
        leader = leaders.get(boundary)
        if leader is None:
            skipped_add_on_count += 1
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=boundary,
                    event_type="add_on_skipped",
                    reason="missing_leader_data",
                    stop_price=active_stop,
                )
            )
            continue
        if leader != seed.symbol:
            skipped_add_on_count += 1
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=boundary,
                    event_type="add_on_skipped",
                    reason="not_current_leader",
                    stop_price=active_stop,
                )
            )
            continue
        if add_on_count == 0 and boundary - signal_at < timedelta(minutes=first_add_on_min_hold_minutes):
            # The live strategy records this as a shadow-only diagnostic but
            # still submits the add-on.  The replay must model the order, not
            # the diagnostic label, or its PnL will understate the strategy.
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=boundary,
                    event_type="add_on_shadow",
                    price=candle.close_price,
                    stop_price=active_stop,
                    reason="first_add_on_before_30m",
                )
            )

        add_on_quantity = size_from_stop_budget(
            candle.close_price,
            active_stop,
            seed.stop_budget_usdt,
            filters,
        )
        if add_on_quantity is None:
            skipped_add_on_count += 1
            events.append(
                ShadowReplayEvent(
                    shadow_opportunity_id=seed.shadow_opportunity_id,
                    symbol=seed.symbol,
                    timestamp=boundary,
                    event_type="add_on_skipped",
                    price=candle.close_price,
                    stop_price=active_stop,
                    reason="invalid_add_on_sizing",
                )
            )
            continue

        if add_on_count >= 1 and enforce_full_position_coverage:
            expected_net_pnl_at_stop = _full_position_net_pnl_at_stop(
                legs=legs,
                candidate_quantity=add_on_quantity,
                candidate_entry_price=candle.close_price,
                stop_price=active_stop,
                taker_fee_rate=taker_fee_rate,
            )
            if expected_net_pnl_at_stop < 0:
                skipped_add_on_count += 1
                events.append(
                    ShadowReplayEvent(
                        shadow_opportunity_id=seed.shadow_opportunity_id,
                        symbol=seed.symbol,
                        timestamp=boundary,
                        event_type="add_on_skipped",
                        price=candle.close_price,
                        stop_price=active_stop,
                        quantity=add_on_quantity,
                        reason="full_position_coverage_below_zero",
                    )
                )
                continue

        add_on_count += 1
        legs.append(
            _OpenLeg(
                leg_type="add_on",
                sequence=add_on_count,
                opened_at=boundary,
                entry_price=candle.close_price,
                stop_at_entry=active_stop,
                quantity=add_on_quantity,
                risk_budget=seed.stop_budget_usdt,
                entry_fee=add_on_quantity * candle.close_price * taker_fee_rate,
            )
        )
        events.append(
            ShadowReplayEvent(
                shadow_opportunity_id=seed.shadow_opportunity_id,
                symbol=seed.symbol,
                timestamp=boundary,
                event_type="add_on",
                price=candle.close_price,
                stop_price=active_stop,
                quantity=add_on_quantity,
            )
        )

    mark_price = eligible_candles[-1].close_price
    total_quantity = sum(leg.quantity for leg in legs)
    gross_mtm = sum(
        leg.quantity * (mark_price - leg.entry_price)
        for leg in legs
    )
    entry_fees = sum(leg.entry_fee for leg in legs)
    hypothetical_exit_fees = total_quantity * mark_price * taker_fee_rate
    events.append(
        ShadowReplayEvent(
            shadow_opportunity_id=seed.shadow_opportunity_id,
            symbol=seed.symbol,
            timestamp=cutoff_utc,
            event_type="open_at_cutoff",
            price=mark_price,
            stop_price=active_stop,
            quantity=total_quantity,
        )
    )
    return ShadowReplayResult(
        shadow_opportunity_id=seed.shadow_opportunity_id,
        symbol=seed.symbol,
        base_signal_at=signal_at,
        base_signal_sequence=seed.base_signal_sequence,
        first_base_signal_at=seed.first_base_signal_at,
        status="open",
        base_entry_price=seed.latest_price,
        initial_stop_price=seed.stop_price,
        base_quantity=base_quantity,
        add_on_count=add_on_count,
        skipped_add_on_count=skipped_add_on_count,
        exit_at=None,
        exit_price=None,
        duration_minutes=Decimal(str((cutoff_utc - signal_at).total_seconds())) / Decimal("60"),
        gross_pnl=None,
        entry_fees=entry_fees,
        exit_fees=None,
        net_pnl=None,
        mark_price_at_cutoff=mark_price,
        mark_to_market_net_pnl=gross_mtm - entry_fees - hypothetical_exit_fees,
        legs=_open_legs(
            shadow_opportunity_id=seed.shadow_opportunity_id,
            legs=legs,
        ),
        events=tuple(events),
        warnings=tuple(warnings),
        blocked_reason=seed.blocked_reason,
    )


def replay_shadow_opportunities(
    *,
    seeds: list[ReplaySeed],
    candles_by_symbol: dict[str, list[ReplayCandle]],
    leaders: dict[datetime, str],
    cutoff: datetime,
    taker_fee_rate: Decimal,
    had_fetch_errors: bool = False,
    independent_candidate_replay: bool = True,
    enforce_daily_base_limit: bool = False,
) -> ShadowReplayReport:
    """Replay skipped Base candidates.

    The default mode answers the filtered-review question: what would each
    entry sample have done if the veto rule were absent?  Every seed is replayed
    independently, including samples for the same symbol whose time windows
    overlap.  Set ``independent_candidate_replay=False`` for a portfolio-style
    replay.  Add ``enforce_daily_base_limit=True`` to apply the production
    strategy's one-Base-per-symbol-per-UTC-day state transition as well.
    Independent-sample PnL must not be presented as a portfolio return.
    """
    opportunities: list[ShadowReplayResult] = []
    overlaps: list[ShadowOverlap] = []
    suppressed: list[ShadowSuppression] = []
    warnings: list[str] = []
    active_by_symbol: dict[str, ShadowReplayResult] = {}
    daily_base_by_symbol: dict[tuple[date, str], str] = {}

    if enforce_daily_base_limit:
        ordered_seeds = sorted(
            seeds,
            key=lambda item: (_utc(item.signal_at), item.symbol, item.shadow_opportunity_id),
        )
    else:
        ordered_seeds = sorted(
            seeds,
            key=lambda item: (item.symbol, item.signal_at, item.shadow_opportunity_id),
        )

    for seed in ordered_seeds:
        if not independent_candidate_replay:
            active = active_by_symbol.get(seed.symbol)
            if active is not None and active.status != "unresolved" and (
                active.exit_at is None
                or active.exit_at > seed.signal_at
            ):
                overlaps.append(
                    ShadowOverlap(
                        shadow_opportunity_id=seed.shadow_opportunity_id,
                        symbol=seed.symbol,
                        signal_at=seed.signal_at,
                        active_shadow_opportunity_id=active.shadow_opportunity_id,
                    )
                )
                continue

        if enforce_daily_base_limit:
            daily_key = (_utc(seed.signal_at).date(), seed.symbol)
            first_base = daily_base_by_symbol.get(daily_key)
            if first_base is not None:
                suppressed.append(
                    ShadowSuppression(
                        shadow_opportunity_id=seed.shadow_opportunity_id,
                        symbol=seed.symbol,
                        signal_at=seed.signal_at,
                        reason="daily_repeat_base",
                        active_shadow_opportunity_id=first_base,
                    )
                )
                continue

            # The production strategy consumes the daily opportunity when the
            # first valid Base candidate reaches the veto/entry gate. Mark it
            # before replay so unresolved market data cannot make a later
            # same-day candidate incorrectly open.
            daily_base_by_symbol[daily_key] = seed.shadow_opportunity_id
        result = replay_shadow_seed(
            seed=seed,
            candles=candles_by_symbol.get(seed.symbol, []),
            leaders=leaders,
            cutoff=cutoff,
            taker_fee_rate=taker_fee_rate,
        )
        opportunities.append(result)
        if enforce_daily_base_limit:
            daily_key = (_utc(seed.signal_at).date(), seed.symbol)
            daily_base_by_symbol[daily_key] = result.shadow_opportunity_id
        if not independent_candidate_replay:
            active_by_symbol[seed.symbol] = result
        warnings.extend(
            f"seed={seed.shadow_opportunity_id} {warning}"
            for warning in result.warnings
        )

    return ShadowReplayReport(
        seed_count=len(seeds),
        opportunities=tuple(opportunities),
        overlaps=tuple(overlaps),
        warnings=tuple(warnings),
        suppressed=tuple(suppressed),
        had_fetch_errors=had_fetch_errors,
        replay_mode=("continuous_strategy" if enforce_daily_base_limit else "portfolio" if not independent_candidate_replay else "independent"),
    )


def replay_skipped_bases(
    *,
    runtime_db_path: Path,
    output_dir: Path,
    start_time: datetime | None = None,
    seed_end_time: datetime | None = None,
    end_time: datetime | None = None,
    symbols: list[str] | None = None,
    proxy: str | None = "http://127.0.0.1:7897",
    taker_fee_rate: Decimal = Decimal("0.0005"),
    refresh_klines: bool = False,
    blocked_reasons: set[str] | None = None,
    independent_candidate_replay: bool = True,
    enforce_daily_base_limit: bool = False,
    load_inputs_fn=load_replay_inputs,
    kline_cache_factory=BinanceKlineCache,
    write_artifacts_fn=None,
) -> ShadowReplayReport:
    if write_artifacts_fn is None:
        from momentum_alpha.skipped_base_replay_output import write_replay_artifacts

        write_artifacts_fn = write_replay_artifacts
    if not runtime_db_path.exists():
        raise FileNotFoundError(runtime_db_path)

    load_inputs_kwargs = {
        "runtime_db_path": runtime_db_path,
        "start_time": start_time,
        "end_time": seed_end_time if seed_end_time is not None else end_time,
        "symbols": set(symbols) if symbols else None,
    }
    if blocked_reasons is not None:
        load_inputs_kwargs["blocked_reasons"] = blocked_reasons
    seeds, leaders, input_warnings, database_cutoff = load_inputs_fn(**load_inputs_kwargs)
    effective_cutoff = end_time or database_cutoff
    if effective_cutoff is None:
        report = ShadowReplayReport(
            seed_count=0,
            opportunities=(),
            overlaps=(),
            warnings=tuple(input_warnings),
            replay_mode=("continuous_strategy" if enforce_daily_base_limit else "portfolio" if not independent_candidate_replay else "independent"),
        )
        write_artifacts_fn(report=report, output_dir=output_dir)
        return report

    cache = kline_cache_factory(
        cache_path=output_dir / "binance_1m_cache.json",
        proxy=proxy,
    )
    candles_by_symbol: dict[str, list[ReplayCandle]] = {}
    fetch_warnings: list[str] = []
    had_fetch_errors = False
    for symbol in sorted({seed.symbol for seed in seeds}):
        symbol_seeds = [seed for seed in seeds if seed.symbol == symbol]
        first_signal_at = min(seed.signal_at for seed in symbol_seeds).astimezone(timezone.utc)
        range_start = datetime.combine(
            first_signal_at.date(),
            datetime_time.min,
            tzinfo=timezone.utc,
        )
        try:
            candles_by_symbol[symbol] = cache.load_range(
                symbol=symbol,
                start_time=range_start,
                end_time=effective_cutoff,
                refresh=refresh_klines,
            )
        except KlineFetchError as exc:
            had_fetch_errors = True
            candles_by_symbol[symbol] = []
            fetch_warnings.append(str(exc))

    report = replay_shadow_opportunities(
        seeds=seeds,
        candles_by_symbol=candles_by_symbol,
        leaders=leaders,
        cutoff=effective_cutoff,
        taker_fee_rate=taker_fee_rate,
        had_fetch_errors=had_fetch_errors,
        independent_candidate_replay=independent_candidate_replay,
        enforce_daily_base_limit=enforce_daily_base_limit,
    )
    report = replace(
        report,
        warnings=tuple([*input_warnings, *fetch_warnings, *report.warnings]),
    )
    write_artifacts_fn(report=report, output_dir=output_dir)
    return report
