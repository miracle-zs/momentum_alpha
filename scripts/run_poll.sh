#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

STATE_FILE="${STATE_FILE:-${PROJECT_ROOT}/var/state.json}"
SYMBOLS="${SYMBOLS:-BTCUSDT ETHUSDT}"

ARGS=(poll --symbols)
for symbol in ${SYMBOLS}; do
  ARGS+=("${symbol}")
done

ARGS+=(--state-file "${STATE_FILE}" --restore-positions --execute-stop-replacements)

if [[ "${BINANCE_USE_TESTNET:-0}" == "1" ]]; then
  ARGS+=(--testnet)
fi

if [[ "${SUBMIT_ORDERS:-0}" == "1" ]]; then
  ARGS+=(--submit-orders)
fi

exec python3 -m momentum_alpha.main "${ARGS[@]}"
