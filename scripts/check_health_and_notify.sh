#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"
VENV_PYTHON="${PROJECT_ROOT}/.venv/bin/python"

if [[ ! -x "${VENV_PYTHON}" ]]; then
  echo "missing virtualenv python at ${VENV_PYTHON}" >&2
  exit 1
fi

SERVERCHAN_SENDKEY="${SERVERCHAN_SENDKEY:-}"
RUNTIME_DB_FILE="${RUNTIME_DB_FILE:-${PROJECT_ROOT}/var/runtime.db}"

if [[ -z "${SERVERCHAN_SENDKEY}" ]]; then
  echo "missing SERVERCHAN_SENDKEY" >&2
  exit 1
fi

TMP_OUTPUT="$(mktemp)"
trap 'rm -f "${TMP_OUTPUT}"' EXIT

set +e
bash "${SCRIPT_DIR}/check_health.sh" >"${TMP_OUTPUT}" 2>&1
HEALTH_EXIT_CODE=$?
set -e

cat "${TMP_OUTPUT}"

exec "${VENV_PYTHON}" -m momentum_alpha.serverchan \
  --sendkey "${SERVERCHAN_SENDKEY}" \
  --runtime-db-file "${RUNTIME_DB_FILE}" \
  --health-output-file "${TMP_OUTPUT}" \
  --hostname "$(hostname)"
