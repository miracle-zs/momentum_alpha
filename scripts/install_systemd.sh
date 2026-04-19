#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-user-stream.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-dashboard.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-rebuild-trade-analytics.service" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start momentum-alpha-rebuild-trade-analytics.service
sudo systemctl enable --now momentum-alpha-dashboard.service
sudo systemctl enable --now momentum-alpha-user-stream.service
sudo systemctl enable --now momentum-alpha.service

echo "installed and started momentum-alpha.service, momentum-alpha-user-stream.service, momentum-alpha-dashboard.service, and ran momentum-alpha-rebuild-trade-analytics.service once"
