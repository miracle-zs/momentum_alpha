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
TRADE_SYNC_MAX_REQUEST_WEIGHT="${TRADE_SYNC_MAX_REQUEST_WEIGHT:-100}"
TRADE_SYNC_OVERLAP_MINUTES="${TRADE_SYNC_OVERLAP_MINUTES:-20}"

SYNC_LOCAL_HHMM="$(TZ=Asia/Shanghai date +%H%M)"
SYNC_LOCAL_MINUTES=$((10#${SYNC_LOCAL_HHMM:0:2} * 60 + 10#${SYNC_LOCAL_HHMM:2:2}))
if ((
  (SYNC_LOCAL_MINUTES >= 7 * 60 + 30 && SYNC_LOCAL_MINUTES <= 8 * 60 + 10) ||
  (SYNC_LOCAL_MINUTES >= 11 * 60 + 40 && SYNC_LOCAL_MINUTES <= 12 * 60 + 15)
)); then
  echo "trade-data-sync skipped local_time=${SYNC_LOCAL_HHMM}"
  exit 0
fi

exec "${VENV_PYTHON}" -u -m momentum_alpha.main \
  sync-trade-data \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --max-request-weight "${TRADE_SYNC_MAX_REQUEST_WEIGHT}" \
  --overlap-minutes "${TRADE_SYNC_OVERLAP_MINUTES}"
