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
DASHBOARD_HOST="${DASHBOARD_HOST:-127.0.0.1}"
DASHBOARD_PORT="${DASHBOARD_PORT:-8080}"

mkdir -p "$(dirname "${RUNTIME_DB_FILE}")"
touch "${RUNTIME_DB_FILE}"

ARGS=(
  dashboard
  --host "${DASHBOARD_HOST}"
  --port "${DASHBOARD_PORT}"
  --runtime-db-file "${RUNTIME_DB_FILE}"
)

exec "${VENV_PYTHON}" -u -m momentum_alpha.main "${ARGS[@]}"
