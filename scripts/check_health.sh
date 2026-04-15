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
POLL_LOG_FILE="${POLL_LOG_FILE:-${PROJECT_ROOT}/var/log/momentum-alpha.log}"
USER_STREAM_LOG_FILE="${USER_STREAM_LOG_FILE:-${PROJECT_ROOT}/var/log/momentum-alpha-user-stream.log}"

exec "${VENV_PYTHON}" -m momentum_alpha.main healthcheck \
  --state-file "${STATE_FILE}" \
  --poll-log-file "${POLL_LOG_FILE}" \
  --user-stream-log-file "${USER_STREAM_LOG_FILE}" \
  --audit-log-file "${AUDIT_LOG_FILE}"
