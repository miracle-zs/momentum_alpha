#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

STATE_FILE="${STATE_FILE:-${PROJECT_ROOT}/var/state.json}"
AUDIT_LOG_FILE="${AUDIT_LOG_FILE:-${PROJECT_ROOT}/var/audit.jsonl}"
SYMBOLS="${SYMBOLS:-}"

ARGS=(poll)
if [[ -n "${SYMBOLS// }" ]]; then
  ARGS+=(--symbols)
  for symbol in ${SYMBOLS}; do
    ARGS+=("${symbol}")
  done
fi

ARGS+=(--state-file "${STATE_FILE}" --audit-log-file "${AUDIT_LOG_FILE}" --restore-positions --execute-stop-replacements)

if [[ "${BINANCE_USE_TESTNET:-0}" == "1" ]]; then
  ARGS+=(--testnet)
fi

if [[ "${SUBMIT_ORDERS:-0}" == "1" ]]; then
  ARGS+=(--submit-orders)
fi

exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"
