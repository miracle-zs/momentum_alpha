# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

Momentum Alpha is a Binance USDⓈ-M Futures trading system implementing a "leader-rotation" strategy. The strategy tracks the cryptocurrency perpetual contract with the highest daily percentage gain (the "leader") and executes trades with stop-loss protection.

## Development Commands

### Run Tests
```bash
python -m unittest discover -s tests -v
```

Run a specific test file:
```bash
python -m unittest tests.test_strategy -v
```

Run a single test:
```bash
python -m unittest tests.test_strategy.StrategyTests.test_opens_base_entry_when_leader_changes_and_symbol_not_held -v
```

### CLI Commands

Single evaluation (dry-run by default):
```bash
python3 -m momentum_alpha.main run-once-live --symbols BTCUSDT ETHUSDT --state-file ./var/state.json
```

Submit orders (requires `--submit-orders`):
```bash
python3 -m momentum_alpha.main run-once-live --symbols BTCUSDT --state-file ./var/state.json --submit-orders
```

Minute-based polling loop:
```bash
python3 -m momentum_alpha.main poll --state-file ./var/state.json --restore-positions --execute-stop-replacements
```

User stream for real-time updates:
```bash
python3 -m momentum_alpha.main user-stream --testnet --state-file ./var/state.json
```

Dashboard server:
```bash
python3 -m momentum_alpha.main dashboard --state-file ./var/state.json --poll-log-file ./var/log/momentum-alpha.log --user-stream-log-file ./var/log/momentum-alpha-user-stream.log --runtime-db-file ./var/runtime.db
```

### Environment Setup

Required environment variables:
```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
export BINANCE_USE_TESTNET=1  # 1 for testnet, 0 for production
```

## Architecture

### Core Data Flow

```
Market Snapshots → Strategy Evaluation → Execution Plan → Broker → Binance API
                         ↓
                   State Persistence (state.json)
                         ↓
                   Telemetry (runtime.db)
```

### Key Modules

**Strategy Layer** (pure state machine, no I/O):
- `strategy.py`: Core trading logic - leader selection, entry/exit decisions
- `models.py`: Data classes - `MarketSnapshot`, `Position`, `PositionLeg`, `StrategyState`, `TickDecision`
- `runtime.py`: Combines strategy with execution planning

**Execution Layer**:
- `execution.py`: Builds orders from strategy decisions, fixed stop-budget sizing
- `orders.py`: Constructs Binance order payloads
- `sizing.py`: Position sizing based on stop budget
- `binance_filters.py`: Price/quantity normalization per Binance symbol filters

**Integration Layer**:
- `broker.py`: Thin wrapper for order submission
- `binance_client.py`: REST API client (no external HTTP dependencies)
- `user_stream.py`: WebSocket client for real-time account/order updates
- `exchange_info.py`: Parses Binance exchange info for symbol filters

**Persistence**:
- `state_store.py`: JSON-based strategy state persistence
- `runtime_store.py`: SQLite-based telemetry (signal decisions, broker orders, position/account snapshots)

**Infrastructure**:
- `main.py`: CLI entry point, orchestrates all components
- `scheduler.py`: Minute-based polling loop
- `reconciliation.py`: Position restoration from Binance API state
- `dashboard.py`: HTTP monitoring server

### Two-Process Deployment Model

The system runs as two separate long-lived processes:

1. **`poll`** (momentum-alpha.service): Minute-based strategy evaluation and order placement
2. **`user-stream`** (momentum-alpha-user-stream.service): WebSocket for account/order state convergence

Both processes write to shared state (`state.json`) and telemetry (`runtime.db`).

### Strategy Logic

- **Leader Selection**: Symbol with highest daily % gain among tradable USDⓈ-M perpetuals
- **Entry Window**: UTC 01:00 onwards (blocked before UTC 01:00)
- **Stop Price**: Previous hour's low (or current hour low if price already below previous hour low)
- **Entry Condition**: Leader changes AND not already holding that symbol
- **Add-on Legs**: At each hour boundary, add to existing positions with updated stops
- **Fixed Stop Budget**: Position size calculated so stop-out risk equals configured budget (default 10 USDT)

### Blocked Entry Reasons

Strategy may block entry with these reasons:
- `outside_entry_window`: Before UTC 01:00
- `leader_unchanged`: Same leader as previous evaluation
- `already_holding`: Already have position in leader symbol
- `missing_previous_hour_candle`: No hourly candle data available
- `invalid_stop_price`: Stop price >= current price (can't protect)

## Test Patterns

Tests use Python's built-in `unittest`. Each module has a corresponding test file:

- Tests construct `MarketSnapshot` and `StrategyState` directly
- No mocking frameworks - uses simple test doubles (callables, dicts)
- Tests verify decision outputs, not implementation details
- Path setup in test files adds `src/` to sys.path

## Deployment

Production deployment uses systemd:
- `deploy/systemd/momentum-alpha.service`: Poll worker
- `deploy/systemd/momentum-alpha-user-stream.service`: User stream worker
- `deploy/env.local`: Environment configuration

Runtime directories initialized by `scripts/init_runtime_dirs.sh`:
- `var/state.json`: Strategy state
- `var/runtime.db`: SQLite telemetry
- `var/log/`: Service logs

## Safety Model

- All operations default to dry-run mode
- Real order submission requires explicit `--submit-orders` flag or `SUBMIT_ORDERS=1` env var
- Testnet mode via `BINANCE_USE_TESTNET=1` or `--testnet` flag
- State file persists previous leader, positions, processed event IDs, tracked order statuses
