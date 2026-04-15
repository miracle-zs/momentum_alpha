#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

sudo cp "${PROJECT_ROOT}/deploy/logrotate/momentum-alpha" /etc/logrotate.d/momentum-alpha

echo "installed logrotate policy to /etc/logrotate.d/momentum-alpha"
