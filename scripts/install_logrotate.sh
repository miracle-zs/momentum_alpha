#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

TMP_FILE="$(mktemp)"
sed "s#__SERVICE_ROOT__#${HOME}/momentum_alpha#g" "${PROJECT_ROOT}/deploy/logrotate/momentum-alpha" > "${TMP_FILE}"
sudo cp "${TMP_FILE}" /etc/logrotate.d/momentum-alpha
rm -f "${TMP_FILE}"

echo "installed logrotate policy to /etc/logrotate.d/momentum-alpha"
