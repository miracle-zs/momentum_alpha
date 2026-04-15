# Binance Leader Rotation Strategy Design

## Goal

Build a Binance USDⓈ-M perpetual futures trading system that:

- Computes the intraday percentage change for all tradable symbols every minute.
- Detects changes in the minute-end leader of the daily gain ranking.
- Opens a new long base position when the leader changes and the new leader is not already held.
- Keeps positions across rank changes and across UTC day boundaries.
- Trails stops and pyramids all surviving positions at each hourly boundary.

## Strategy Scope

- Exchange: Binance USDⓈ-M perpetual futures only.
- Direction: long only.
- Ranking universe: all tradable symbols that are not paused.
- Daily reference price: the open price of the `00:00` UTC `1m` candle.
- Live rank price: latest traded price.
- Entry window: `01:00:00` UTC through `23:59:59` UTC.
- No forced flat at `00:00` UTC. Existing positions continue to be managed.

## Trading Rules

### Leader Ranking

At each minute close:

`daily_change_pct = (latest_trade_price - utc_day_open_price) / utc_day_open_price`

The symbol with the highest `daily_change_pct` is the current leader.

### Base Entry

At each minute close in the entry window:

1. Recompute the current leader.
2. Compare it to the previous minute's leader.
3. If the leader changed:
4. Check whether the new leader already has an open position.
5. Check whether the symbol has a fully completed previous `1h` candle.
6. If both checks pass, open a long base position immediately.

### Stop Placement

For each new base entry or add-on entry:

- Initial stop price = low of the previous fully completed `1h` candle.
- Order size is derived from a fixed stop loss budget of `10 USDT`.
- If the stop would already be above the market and the position would therefore be immediately invalid, the trade is not opened because the position would already be stopped.

### Hourly Add-On

At every `HH:00:00` UTC:

1. First process any minute-close leader-change base entry for that same minute.
2. For every open position:
3. Move the stop to the low of the previous fully completed `1h` candle.
4. Open one additional long add-on sized so that its stop risk is `10 USDT`.

All surviving positions are eligible. There is no per-symbol add-on cap and no account-level risk cap in this version.

### Exit

Positions exit only through stop loss execution:

- Trigger source: latest traded price.
- Execution style: market stop.
- Losing the leader rank does not close the position.
- Crossing into a new UTC day does not close the position.
- If a symbol later becomes the leader again while no position is held, that is a new valid base entry.

## Time Semantics

- The system runs 24/7.
- Ranking is refreshed at the close of every minute.
- Base entries are blocked between `00:00:00` UTC and `00:59:59` UTC.
- Existing positions remain managed during the blocked entry window.
- Hourly add-ons always remain active, including after day rollover.

## State Model

The system needs these persistent state objects:

- Symbol market state
  - current tradable status
  - reference `00:00` UTC open price for the current UTC date
  - latest trade price
  - previous completed `1h` low
  - previous minute leader flag
- Position state per symbol
  - symbol
  - current aggregate quantity
  - weighted average entry
  - active stop price
  - number of legs
  - open legs with entry price, quantity, and creation time
  - open stop order id
- Strategy state
  - current UTC date
  - previous minute leader symbol
  - positions by symbol
  - pending order and reconciliation state

## Execution Requirements

### Binance Exchange Constraints

The implementation must consume futures `exchangeInfo` and apply symbol filters before order placement:

- price precision and tick size
- quantity precision and step size
- minimum quantity
- notional or exchange minimums when applicable

The implementation must round:

- prices to valid tick size
- quantities down to valid step size

If rounding causes quantity to become invalid or zero, the trade is skipped.

### Stop Orders

Per Binance USDⓈ-M futures `POST /fapi/v1/order`, the system must support:

- `MARKET` for entries
- `STOP_MARKET` for exits
- `workingType=CONTRACT_PRICE` so trigger logic follows contract price

The system should cancel and replace the active stop after any successful add-on or stop update.

## Edge Cases

- Symbols listed after `00:00` UTC are included in ranking once tradable, but cannot be entered until a fully completed previous `1h` candle exists.
- If no valid `00:00` UTC reference price is available for a symbol on a given day, that symbol is excluded from ranking until reference data exists.
- If the current leader already has an open position, no duplicate base entry is opened.
- If multiple symbols tie on daily change, the implementation must use a deterministic tie-breaker. Recommended: lexicographically smallest symbol.
- If an hourly boundary and minute-close signal coincide, base entry processing runs first, then hourly add-ons.

## Risk Characteristics

This design intentionally has:

- fixed per-leg stop risk of `10 USDT`
- no account-level risk cap
- no profit target
- no time stop
- no volatility or liquidity filter
- no add-on count limit

That means total account exposure and single-symbol cumulative stop exposure are intentionally unbounded in theory.

## Recommended Architecture

Use a layered Python architecture:

- `domain`
  - immutable market and position models
  - pure strategy decision logic
- `services`
  - ranking service
  - risk sizing service
  - exchange filter normalization service
- `adapters`
  - Binance REST/WebSocket client
  - persistence adapter
  - execution adapter
- `app`
  - event loop
  - schedulers for minute-close, hour-close, and daily rollover
  - reconciliation jobs

Keep strategy decisions pure and deterministic so the same code can be used in both backtest and live trading.

## Delivery Plan

Implement in stages:

1. Pure domain model and strategy state machine.
2. Exchange filter normalization and order sizing.
3. In-memory simulation harness and tests.
4. Live Binance adapter and runtime service.
5. Persistence, logging, and operator controls.
