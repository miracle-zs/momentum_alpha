# Momentum Alpha

Core strategy implementation for the Binance leader-rotation futures system.

Current scope:

- pure strategy state machine
- Binance filter-aware price and quantity normalization
- fixed stop-budget sizing helpers
- in-memory runtime skeleton for deterministic tests
- live snapshot assembly that prefers the UTC `00:00` 1m candle open and falls back to the first available UTC-day `1m` candle for new listings
- live snapshot assembly that reads the previous fully closed UTC `1h` candle low as the stop anchor
- base-entry stop selection that falls back to the current hour low when the entry price is already below the previous hour low
- live snapshot assembly that skips symbols with no usable UTC-day `1m` baseline yet
- live snapshot assembly that skips symbols whose latest ticker price is missing or malformed
- Testnet-aware CLI/client configuration via `BINANCE_USE_TESTNET=1` or `--testnet`
- Binance Futures user-data listen-key lifecycle and `user-stream` CLI
- deployment artifacts for shell and systemd-based service startup
- startup-time REST prewarm, websocket auto-reconnect, and listen-key keepalive for the user stream worker

## Environment

Set Binance credentials before using the live CLI:

```bash
export BINANCE_API_KEY="your_api_key"
export BINANCE_API_SECRET="your_api_secret"
```

Use Testnet with either an environment variable or CLI flag:

```bash
export BINANCE_USE_TESTNET=1
```

## Run Once

Dry-run a single live evaluation without submitting orders:

```bash
python3 -m momentum_alpha.main run-once-live --symbols BTCUSDT ETHUSDT --state-file ./var/state.json
```

Submit orders for a single live evaluation:

```bash
python3 -m momentum_alpha.main run-once-live --symbols BTCUSDT ETHUSDT --state-file ./var/state.json --submit-orders
```

Dry-run the same evaluation against Testnet:

```bash
python3 -m momentum_alpha.main run-once-live --symbols BTCUSDT ETHUSDT --state-file ./var/state.json --testnet
```

## Polling

Run the minute-based polling loop in dry-run mode:

```bash
python3 -m momentum_alpha.main poll \
  --symbols BTCUSDT ETHUSDT \
  --state-file ./var/state.json \
  --restore-positions \
  --execute-stop-replacements
```

Limit the loop for testing:

```bash
python3 -m momentum_alpha.main poll \
  --symbols BTCUSDT \
  --state-file ./var/state.json \
  --max-ticks 5
```

## User Stream

Start the Binance Futures user-data stream:

```bash
python3 -m momentum_alpha.main user-stream --testnet
```

`user-stream` uses `websocket-client` when running against a real socket connection.

For real deployment, `poll` and `user-stream` should run as separate long-lived processes. `poll` is responsible for minute/hour strategy evaluation and order placement; `user-stream` is responsible for account/order state convergence.

## Deployment

Use the provided wrappers and systemd units as a starting point:

```bash
cp deploy/env.example .env.local
cp deploy/env.example deploy/env.local
chmod +x scripts/init_runtime_dirs.sh
chmod +x scripts/install_systemd.sh
chmod +x scripts/run_poll.sh
chmod +x scripts/run_user_stream.sh
./scripts/init_runtime_dirs.sh
```

Relevant artifacts:

- `scripts/init_runtime_dirs.sh`
- `scripts/install_systemd.sh`
- `scripts/run_poll.sh`
- `scripts/run_user_stream.sh`
- `deploy/systemd/momentum-alpha.service`
- `deploy/systemd/momentum-alpha-user-stream.service`
- `deploy/env.example`
- `docs/live-deployment-checklist.md`

Recommended first-time bootstrap:

```bash
python3 -m pip install -e .[live]
cp deploy/env.example deploy/env.local
chmod +x scripts/init_runtime_dirs.sh scripts/install_systemd.sh scripts/run_poll.sh scripts/run_user_stream.sh
./scripts/init_runtime_dirs.sh
```

Then edit `deploy/env.local` with your real API key, secret, symbols, state file path, and whether `SUBMIT_ORDERS=1`.

Suggested systemd rollout:

```bash
./scripts/install_systemd.sh
```

The provided unit files already point to `deploy/env.local`.

Operational split:

- `momentum-alpha.service`: minute polling, strategy decisions, optional live order submission
- `momentum-alpha-user-stream.service`: listen key lifecycle, websocket account/order updates, local state convergence

Practical live startup order:

1. Install dependencies with `python3 -m pip install -e .[live]`.
2. Initialize runtime directories with `./scripts/init_runtime_dirs.sh`.
3. Fill in credentials and runtime flags in your chosen env file.
4. Start `momentum-alpha-user-stream.service` first so local order/account state begins converging.
5. Start `momentum-alpha.service` second so minute polling runs against a warmed state file.
6. Watch `var/log/momentum-alpha-user-stream.log` and `var/log/momentum-alpha.log` for reconnects, keepalive activity, and order flow.

Pre-go-live review:

- Read `docs/live-deployment-checklist.md` before switching `BINANCE_USE_TESTNET=0` and `SUBMIT_ORDERS=1`.

## Safety Notes

- `run-once-live` and `poll` default to dry-run mode.
- Real order submission only happens when `--submit-orders` is explicitly provided.
- State persistence now stores previous leader, local position view, processed user-stream event ids, and tracked order statuses.
