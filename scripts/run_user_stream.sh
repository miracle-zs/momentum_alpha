#!/usr/bin/env bash
set -euo pipefail

ARGS=(user-stream)

if [[ "${BINANCE_USE_TESTNET:-0}" == "1" ]]; then
  ARGS+=(--testnet)
fi

exec python3 -m momentum_alpha.main "${ARGS[@]}"
