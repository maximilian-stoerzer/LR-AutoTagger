#!/usr/bin/env bash
set -euo pipefail
shopt -s nullglob

# ──────────────────────────────────────────────
# LR-AutoTag Backend — Install Script
# Runs on the Debian target after unpacking the release tarball.
# Installs the backend as a systemd service.
# ──────────────────────────────────────────────

INSTALL_DIR="${INSTALL_DIR:-/opt/lr-autotag}"
SERVICE_USER="${SERVICE_USER:-lr-autotag}"
SERVICE_NAME="lr-autotag.service"

# Run from the directory containing this script so relative paths to
# wheel/, migrations/, .env.example, lr-autotag.service resolve reliably.
cd "$(dirname "$0")"

echo "==> Installing LR-AutoTag Backend to ${INSTALL_DIR}"

if [ "$(id -u)" -ne 0 ]; then
    echo "ERROR: install.sh must be run as root (use sudo)." >&2
    exit 1
fi

# Locate a suitable Python interpreter (>= 3.12). We let Python do the
# comparison to avoid fragile shell parsing of version strings and to
# automatically skip broken/segfaulting interpreters.
PYTHON_BIN=""
for candidate in python3.13 python3.12 python3; do
    cand_path="$(command -v "${candidate}" 2>/dev/null || true)"
    [ -n "${cand_path}" ] || continue
    if "${cand_path}" -c 'import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)' 2>/dev/null; then
        PYTHON_BIN="${cand_path}"
        version="$("${cand_path}" -c 'import sys; print("{}.{}.{}".format(*sys.version_info[:3]))')"
        echo "    Using Python ${version} (${PYTHON_BIN})"
        break
    fi
done

if [ -z "${PYTHON_BIN}" ]; then
    echo "ERROR: No Python >= 3.12 found on PATH. Install python3.12 or later." >&2
    exit 1
fi

# Verify expected tarball layout before we start mutating anything
wheels=(wheel/*.whl)
if [ "${#wheels[@]}" -ne 1 ]; then
    echo "ERROR: expected exactly one wheel in wheel/, found ${#wheels[@]}." >&2
    exit 1
fi
if [ ! -d migrations ]; then
    echo "ERROR: migrations/ not found in release tarball." >&2
    exit 1
fi
if [ ! -f lr-autotag.service ]; then
    echo "ERROR: lr-autotag.service not found in release tarball." >&2
    exit 1
fi

if ! id "${SERVICE_USER}" &>/dev/null; then
    useradd --system --shell /usr/sbin/nologin --home-dir "${INSTALL_DIR}" "${SERVICE_USER}"
    echo "    Created system user: ${SERVICE_USER}"
fi

mkdir -p "${INSTALL_DIR}"

echo "==> Setting up Python venv and installing wheel ..."
"${PYTHON_BIN}" -m venv "${INSTALL_DIR}/venv"
"${INSTALL_DIR}/venv/bin/pip" install --upgrade --quiet pip
"${INSTALL_DIR}/venv/bin/pip" install --quiet "${wheels[0]}"

echo "==> Copying migrations ..."
rm -rf "${INSTALL_DIR}/migrations"
cp -r migrations/ "${INSTALL_DIR}/migrations/"

FRESH_INSTALL=0
if [ ! -f "${INSTALL_DIR}/.env" ]; then
    cp .env.example "${INSTALL_DIR}/.env"
    chmod 640 "${INSTALL_DIR}/.env"
    FRESH_INSTALL=1
fi

chown -R "${SERVICE_USER}:${SERVICE_USER}" "${INSTALL_DIR}"

echo "==> Installing systemd unit ${SERVICE_NAME} ..."
cp "${SERVICE_NAME}" "/etc/systemd/system/${SERVICE_NAME}"
systemctl daemon-reload
systemctl enable "${SERVICE_NAME}" >/dev/null

echo ""
echo "==> Installation complete."
echo ""

if [ "${FRESH_INSTALL}" -eq 1 ]; then
    cat <<EOF
*** FRESH INSTALL — action required ***

1. Edit ${INSTALL_DIR}/.env and set at least:
     - DATABASE_URL
     - OLLAMA_BASE_URL (+ OLLAMA_MODEL)
     - API_KEY  (generate: openssl rand -base64 32)

2. Start the service:
     systemctl start ${SERVICE_NAME}

3. Verify:
     systemctl status ${SERVICE_NAME}
     journalctl -u ${SERVICE_NAME} -f
     curl http://localhost:8000/api/v1/health
EOF
else
    echo "    Existing .env preserved. Restart the service to pick up the new binary:"
    echo "      systemctl restart ${SERVICE_NAME}"
fi
