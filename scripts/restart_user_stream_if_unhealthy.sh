#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

HEALTH_OUTPUT="$("${PROJECT_ROOT}/scripts/check_health.sh" 2>&1)" || HEALTH_STATUS=$?
printf '%s\n' "${HEALTH_OUTPUT}"

if printf '%s\n' "${HEALTH_OUTPUT}" | grep -q '^user_stream_events status=FAIL'; then
  echo "user-stream healthcheck failed; restarting momentum-alpha-user-stream.service"
  systemctl restart momentum-alpha-user-stream.service
  exit 0
fi

exit 0
