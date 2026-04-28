#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-user-stream.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-dashboard.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-rebuild-trade-analytics.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-trade-data-sync.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-trade-data-sync.timer" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-daily-review-report.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-daily-review-report.timer" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-user-stream-healthcheck.service" /etc/systemd/system/
sudo cp "${PROJECT_ROOT}/deploy/systemd/momentum-alpha-user-stream-healthcheck.timer" /etc/systemd/system/
sudo systemctl daemon-reload
sudo systemctl start momentum-alpha-rebuild-trade-analytics.service
sudo systemctl enable --now momentum-alpha-trade-data-sync.timer
sudo systemctl enable --now momentum-alpha-dashboard.service
sudo systemctl enable --now momentum-alpha-user-stream.service
sudo systemctl enable --now momentum-alpha.service
sudo systemctl enable --now momentum-alpha-daily-review-report.timer
sudo systemctl enable --now momentum-alpha-user-stream-healthcheck.timer

echo "installed and started momentum-alpha.service, momentum-alpha-user-stream.service, momentum-alpha-dashboard.service, enabled momentum-alpha-trade-data-sync.timer, momentum-alpha-daily-review-report.timer and momentum-alpha-user-stream-healthcheck.timer, and ran momentum-alpha-rebuild-trade-analytics.service once"
