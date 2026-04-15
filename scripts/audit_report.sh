#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

AUDIT_LOG_FILE="${AUDIT_LOG_FILE:-${PROJECT_ROOT}/var/audit.jsonl}"
SINCE_MINUTES="${SINCE_MINUTES:-1440}"
LIMIT="${LIMIT:-20}"

exec "${VENV_PYTHON}" -m momentum_alpha.main audit-report \
  --audit-log-file "${AUDIT_LOG_FILE}" \
  --since-minutes "${SINCE_MINUTES}" \
  --limit "${LIMIT}"
