#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "${SCRIPT_DIR}/.." && pwd)"

mkdir -p "${PROJECT_ROOT}/var"
mkdir -p "${PROJECT_ROOT}/var/log"

echo "initialized runtime directories under ${PROJECT_ROOT}/var"
