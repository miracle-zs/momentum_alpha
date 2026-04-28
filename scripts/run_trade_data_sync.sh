#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"
TRADE_SYNC_LOOKBACK_HOURS="${TRADE_SYNC_LOOKBACK_HOURS:-36}"

SYNC_END_TIME="$("${VENV_PYTHON}" -c 'from datetime import datetime, timezone; print(datetime.now(timezone.utc).isoformat())')"
SYNC_START_TIME="$(
  TRADE_SYNC_LOOKBACK_HOURS="${TRADE_SYNC_LOOKBACK_HOURS}" "${VENV_PYTHON}" -c 'import os; from datetime import datetime, timedelta, timezone; hours = int(os.environ["TRADE_SYNC_LOOKBACK_HOURS"]); print((datetime.now(timezone.utc) - timedelta(hours=hours)).isoformat())'
)"

"${VENV_PYTHON}" -u -m momentum_alpha.main \
  backfill-binance-trades \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --start-time "${SYNC_START_TIME}" \
  --end-time "${SYNC_END_TIME}" \
  --skip-rebuild

"${VENV_PYTHON}" -u -m momentum_alpha.main \
  backfill-account-flows \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --start-time "${SYNC_START_TIME}" \
  --end-time "${SYNC_END_TIME}" \
  --income-types REALIZED_PNL COMMISSION FUNDING_FEE TRANSFER

exec "${VENV_PYTHON}" -u -m momentum_alpha.main \
  rebuild-trade-analytics \
  --runtime-db-file "${RUNTIME_DB_FILE}"
