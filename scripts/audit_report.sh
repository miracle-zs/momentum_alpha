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
AUDIT_LOG_FILE="${AUDIT_LOG_FILE:-}"
SINCE_MINUTES="${SINCE_MINUTES:-1440}"
LIMIT="${LIMIT:-20}"

ARGS=(
  audit-report
  --runtime-db-file "${RUNTIME_DB_FILE}"
  --since-minutes "${SINCE_MINUTES}"
  --limit "${LIMIT}"
)

if [[ -n "${AUDIT_LOG_FILE}" ]]; then
  ARGS+=(--audit-log-file "${AUDIT_LOG_FILE}")
fi

exec "${VENV_PYTHON}" -m momentum_alpha.main "${ARGS[@]}"
