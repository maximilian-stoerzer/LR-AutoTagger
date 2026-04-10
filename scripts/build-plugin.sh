#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# Build plugin release ZIP
# Usage: scripts/build-plugin.sh <version>
# ──────────────────────────────────────────────

VERSION="${1:?Usage: build-plugin.sh <version>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
PLUGIN_DIR="${PROJECT_DIR}/plugin"
OUT_DIR="${PROJECT_DIR}/release/plugin"

# Check if plugin directory has content
if [ -z "$(ls -A "${PLUGIN_DIR}" 2>/dev/null)" ]; then
    echo "==> Plugin directory is empty — skipping (Sprint 3)."
    exit 0
fi

echo "==> Building plugin release v${VERSION}"

mkdir -p "${OUT_DIR}"
ARTIFACT="${OUT_DIR}/lr-autotag-plugin-${VERSION}.zip"

cd "${PLUGIN_DIR}"
zip -r "${ARTIFACT}" . -x '.*' '__pycache__/*' > /dev/null

echo "==> Plugin artifact: ${ARTIFACT} ($(du -h "${ARTIFACT}" | cut -f1))"
