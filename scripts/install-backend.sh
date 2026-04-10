#!/usr/bin/env bash
set -euo pipefail

# ──────────────────────────────────────────────
# LR-AutoTag Backend — Install Script
# Runs on the Debian target after unpacking the release tarball.
# ──────────────────────────────────────────────

INSTALL_DIR="${INSTALL_DIR:-/opt/lr-autotag}"
SERVICE_USER="${SERVICE_USER:-lr-autotag}"

echo "==> Installing LR-AutoTag Backend to ${INSTALL_DIR}"

# 1. Create system user if it doesn't exist
if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin "${SERVICE_USER}"
    echo "    Created system user: ${SERVICE_USER}"
fi

# 2. Create install directory
mkdir -p "${INSTALL_DIR}"

# 3. Create venv and install wheel
echo "==> Setting up Python venv and installing wheel ..."
python3.12 -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade --quiet pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet wheel/*.whl

# 4. Copy migrations
echo "==> Copying migrations ..."
cp -r migrations/ "${INSTALL_DIR}/migrations/"

# 5. Copy .env.example only if .env doesn't exist yet
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp .env.example "${INSTALL_DIR}/.env"
    echo ""
    echo "*** IMPORTANT: Edit ${INSTALL_DIR}/.env before starting the service ***"
    echo ""
fi

# 6. Set ownership
chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

# 7. Install systemd unit
cp lr-autotag.service /etc/systemd/system/
systemctl daemon-reload
systemctl enable lr-autotag.service

echo "==> Installation complete."
echo "    Start with:  systemctl start lr-autotag"
echo "    Logs:        journalctl -u lr-autotag -f"
