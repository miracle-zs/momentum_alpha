# Live Ops Checklist

Use this checklist during the first production session and any later restart or incident review.

## Before Starting

- Confirm `deploy/env.local` has the intended production values:
  - `BINANCE_USE_TESTNET=0`
  - `SUBMIT_ORDERS=1`
  - `RUNTIME_DB_FILE=/root/momentum_alpha/var/runtime.db`
  - `SYMBOLS=` unless you intentionally want a whitelist
- Confirm the virtualenv exists and the current code is installed with `./.venv/bin/python -m pip install -e .[live]`
- Confirm runtime directories exist:
  - `/root/momentum_alpha/var`
  - `/root/momentum_alpha/var/log`
- During installation, run the one-time trade analytics rebuild first:
  - `systemctl start momentum-alpha-rebuild-trade-analytics.service`
  - Re-run it manually any time you need to backfill closed-trade analytics after a data repair
- Confirm log rotation is installed at `/etc/logrotate.d/momentum-alpha`
- Log rotation should cover `momentum-alpha.log`, `momentum-alpha-user-stream.log`, `momentum-alpha-dashboard.log`, `momentum-alpha-rebuild-trade-analytics.log`, and `momentum-alpha-daily-review-report.log`
- Confirm `AUDIT_LOG_FILE` points to a persistent writable path
- If you want push alerts, confirm `SERVERCHAN_SENDKEY` is set

## Start Order

1. Start `momentum-alpha-user-stream.service`.
2. Confirm it is `active (running)`.
3. Start `momentum-alpha.service`.
4. Confirm it is `active (running)`.

## First 15 Minutes

- Watch both services:
  - `systemctl status momentum-alpha-user-stream.service -l --no-pager`
  - `systemctl status momentum-alpha.service -l --no-pager`
- Watch logs:
  - `tail -f /root/momentum_alpha/var/log/momentum-alpha-user-stream.log`
  - `tail -f /root/momentum_alpha/var/log/momentum-alpha.log`
- Run `bash scripts/check_health.sh` after both services are up
- Optionally run `bash scripts/check_health_and_notify.sh` from cron/systemd timer to push FAIL and recovery alerts through Server酱
- If you need a quick read-only overview, run `bash scripts/run_dashboard.sh` and inspect `http://127.0.0.1:8080/`
- Reject the session if you see any of:
  - `HTTP Error 403`
  - `HTTP Error 429`
  - `Traceback`
  - repeated websocket reconnect failures
  - repeated service restarts in `journalctl`

## Healthy Signals

- `momentum-alpha-user-stream.service` remains `active (running)` without restart churn
- `momentum-alpha.service` remains `active (running)` for multiple minute ticks
- `momentum-alpha.log` shows periodic `tick ...` lines without new errors
- `momentum-alpha-user-stream.log` does not show repeated prewarm or listen-key failures
- `/root/momentum_alpha/var/runtime.db` exists and receives new strategy/runtime rows over time

## If Something Breaks

- Check recent service logs first:
  - `journalctl -u momentum-alpha.service -n 100 --no-pager`
  - `journalctl -u momentum-alpha-user-stream.service -n 100 --no-pager`
- Re-run private API diagnostics from the same env file:
  - `cd /root/momentum_alpha`
  - `set -a`
  - `source deploy/env.local`
  - `set +a`
  - `bash scripts/diagnose_private_api.sh`
- If the poll worker fails, clear only the worker log and restart only that service before changing code:
  - `truncate -s 0 /root/momentum_alpha/var/log/momentum-alpha.log`
  - `systemctl restart momentum-alpha.service`
- Use `bash scripts/audit_report.sh` to review the latest structured decision and fill history
- Use `bash scripts/check_health_and_notify.sh` when you want a deduplicated alert plus recovery notification

## Daily Checks

- Confirm both services are still `active`
- Confirm log files are rotating instead of growing without bound
- Confirm there is no repeated error pattern in the latest 100 log lines
- Confirm `runtime.db` is still writable and current
- Confirm `audit_events` and related runtime tables are still growing with new runtime and user-stream events
- Confirm the daily review timer has run successfully at 08:30 Asia/Shanghai and inserted a fresh row into `daily_review_reports`
- Run `bash scripts/run_daily_review_report.sh` manually when you need to backfill or debug the daily review output
- Run `python3 -m momentum_alpha.main prune-runtime-db --runtime-db-file /root/momentum_alpha/var/runtime.db` when old audit or snapshot rows need to be trimmed
