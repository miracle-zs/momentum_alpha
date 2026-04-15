#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

ARGS=(user-stream)

if [[ "${BINANCE_USE_TESTNET:-0}" == "1" ]]; then
  ARGS+=(--testnet)
fi

exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"
