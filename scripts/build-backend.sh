#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# Build backend release tarball
# Usage: scripts/build-backend.sh <version>
# ──────────────────────────────────────────────

VERSION="${1:?Usage: build-backend.sh <version>}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$(cd "${SCRIPT_DIR}/.." && pwd)"
OUT_DIR="${PROJECT_DIR}/release/backend"
STAGE="$(mktemp -d)"

trap 'rm -rf "${STAGE}"' EXIT

echo "==> Building backend release v${VERSION}"

# 1. Build wheel
echo "    Building wheel ..."
cd "${PROJECT_DIR}/backend"
"${PROJECT_DIR}/backend/.venv/bin/python" -m build --wheel --outdir "${STAGE}/wheel/" 2>&1 | tail -1

# 2. Copy supporting files
echo "    Staging supporting files ..."
cp -r "${PROJECT_DIR}/backend/migrations/" "${STAGE}/migrations/"
cp "${PROJECT_DIR}/.env.example" "${STAGE}/.env.example"
cp "${SCRIPT_DIR}/install-backend.sh" "${STAGE}/install.sh"
cp "${SCRIPT_DIR}/lr-autotag.service" "${STAGE}/lr-autotag.service"

# 3. Create tarball
mkdir -p "${OUT_DIR}"
ARTIFACT="${OUT_DIR}/lr-autotag-backend-${VERSION}.tar.gz"
tar -czf "${ARTIFACT}" -C "${STAGE}" .

echo "==> Backend artifact: ${ARTIFACT} ($(du -h "${ARTIFACT}" | cut -f1))"
