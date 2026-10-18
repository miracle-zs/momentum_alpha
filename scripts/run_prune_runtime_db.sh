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
ARCHIVE_DB_FILE="${ARCHIVE_DB_FILE:-${PROJECT_ROOT}/var/runtime_archive.db}"
BACKUP_DIR="${BACKUP_DIR:-${PROJECT_ROOT}/var/backups}"
MAX_BACKUPS="${MAX_BACKUPS:-3}"
AUDIT_RETENTION_DAYS="${AUDIT_RETENTION_DAYS:-30}"
SNAPSHOT_RETENTION_DAYS="${SNAPSHOT_RETENTION_DAYS:-7}"
SIGNAL_DECISION_RETENTION_DAYS="${SIGNAL_DECISION_RETENTION_DAYS:-30}"
LIVE_SERIES_RETENTION_DAYS="${LIVE_SERIES_RETENTION_DAYS:-7}"

ARGS=(
  prune-runtime-db
  --runtime-db-file "${RUNTIME_DB_FILE}"
  --archive-file "${ARCHIVE_DB_FILE}"
  --backup-dir "${BACKUP_DIR}"
  --max-backups "${MAX_BACKUPS}"
  --audit-retention-days "${AUDIT_RETENTION_DAYS}"
  --snapshot-retention-days "${SNAPSHOT_RETENTION_DAYS}"
  --signal-decision-retention-days "${SIGNAL_DECISION_RETENTION_DAYS}"
  --live-series-retention-days "${LIVE_SERIES_RETENTION_DAYS}"
)

"${VENV_PYTHON}" -u -m momentum_alpha.main "${ARGS[@]}"

# Compress newly created backups and retain only newest MAX_BACKUPS
gzip -f "${BACKUP_DIR}"/*.db 2>/dev/null || true
ls -t "${BACKUP_DIR}"/runtime_backup_*.db.gz 2>/dev/null | tail -n +$((MAX_BACKUPS + 1)) | xargs -r rm -f
