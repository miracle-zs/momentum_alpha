#!/usr/bin/env bash
set -euo pipefail

is_truthy() (
  shopt -s nocasematch
  [[ "${1:-}" =~ ^[[:space:]]*(1|true|yes|on)[[:space:]]*$ ]]
)

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"
SYMBOLS="${SYMBOLS:-}"

ARGS=(poll)
if [[ -n "${SYMBOLS// }" ]]; then
  ARGS+=(--symbols)
  for symbol in ${SYMBOLS}; do
    ARGS+=("${symbol}")
  done
fi

ARGS+=(--runtime-db-file "${RUNTIME_DB_FILE}" --restore-positions --execute-stop-replacements)

if is_truthy "${BINANCE_USE_TESTNET:-0}"; then
  ARGS+=(--testnet)
fi

if is_truthy "${SUBMIT_ORDERS:-0}"; then
  ARGS+=(--submit-orders)
fi

exec "${VENV_PYTHON}" -u -m momentum_alpha.main "${ARGS[@]}"
