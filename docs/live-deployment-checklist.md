# Live Deployment Checklist

This checklist is the shortest path to deciding whether the current codebase is ready to connect to Binance live API and run as a deployed service.

## Already Implemented

- Strategy polling worker with Binance symbol filter handling
- UTC `00:00` daily baseline logic and previous closed `1h` stop anchor logic
- Testnet-aware REST and websocket endpoint selection
- User stream listen-key lifecycle
- Startup-time REST prewarm for `positionRisk` and `openOrders`
- User stream state convergence for:
  - `ORDER_TRADE_UPDATE`
  - `ACCOUNT_UPDATE`
  - tracked order statuses
  - stop-price backfill from active stop orders
- User stream auto-reconnect with retry logging and bounded backoff
- Listen-key keepalive loop
- Shell wrappers and systemd service templates for separate `poll` and `user-stream` workers

## Must Confirm Before Live Trading

- Binance production API key and secret are valid and have futures permissions
- The account is enabled for USDⓈ-M perpetual trading
- `BINANCE_USE_TESTNET=0`
- `SUBMIT_ORDERS=1`
- `STATE_FILE` points to a persistent writable path
- `SYMBOLS` matches the symbols you actually want the polling worker to scan
- Project virtualenv exists at `.venv/`
- `websocket-client` is installed with `./.venv/bin/python -m pip install -e .[live]`
- Runtime directories exist:
  - `var/`
  - `var/log/`
- Both long-lived workers are enabled:
  - polling worker
  - user-stream worker
- Systemd unit `EnvironmentFile=` paths point to the real env file you intend to use
- Wrapper scripts can execute `.venv/bin/python` on the server

## Recommended Cutover Sequence

1. Run `run-once-live --testnet --submit-orders` only after validating dry-run output.
2. Run `poll --testnet --submit-orders` on Testnet as a long-lived worker.
3. Run `user-stream --testnet` in parallel and confirm state file convergence.
4. Verify:
   - positions are restored after restart
   - stop orders appear in tracked `order_statuses`
   - user stream reconnect logs are visible
   - keepalive loop does not crash
5. Switch the env file from Testnet to production.
6. Start `user-stream` first.
7. Start `poll` second.

## Residual Risks Not Yet Eliminated

- No account-level risk cap beyond the per-entry fixed stop budget
- No explicit take-profit or exit enhancement beyond trailing by hour-low logic
- No portfolio-level exposure cap across many simultaneous symbols
- No alerting integration for repeated reconnect failures or order-placement failures
- No end-to-end live exchange simulation covering Binance-specific rejection edge cases
- No automatic verification that the polling worker and user-stream worker are using the same env file in production

## Recommended First Live Mode

- Start with Binance Testnet and `SUBMIT_ORDERS=1`
- Then switch to production with the smallest practical account size
- Keep both service logs open during first live session
- Verify at least one full cycle of:
  - base entry
  - stop order placement
  - user-stream order-state update
  - restart and state restoration
