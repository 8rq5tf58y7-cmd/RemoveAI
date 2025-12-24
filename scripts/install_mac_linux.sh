#!/usr/bin/env bash
set -euo pipefail

# Bootstraps Python + venv + deps using uv (recommended).
# Usage: ./scripts/install_mac_linux.sh

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "Do NOT run this installer with sudo."
  echo "Run it as your normal user: ./scripts/install_mac_linux.sh"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

REQUIRED_PY="${REQUIRED_PY:-3.12}"
EXTRAS="${EXTRAS:-}"

if ! command -v uv >/dev/null 2>&1; then
  if [ -x "${HOME}/.local/bin/uv" ]; then
    export PATH="${HOME}/.local/bin:${PATH}"
  elif [ -x "${HOME}/.cargo/bin/uv" ]; then
    export PATH="${HOME}/.cargo/bin:${PATH}"
  else
    echo "uv not found; installing it..."
    if ! curl -LsSf https://astral.sh/uv/install.sh | sh; then
      echo ""
      echo "Failed to install uv (network error)."
      echo "If you already have uv installed, ensure it's on PATH and re-run."
      exit 1
    fi
    # uv installer commonly places binaries here:
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
fi

echo "Installing Python ${REQUIRED_PY} (via uv) ..."
uv python install "${REQUIRED_PY}"

echo "Creating venv (.venv) ..."
uv venv --python "${REQUIRED_PY}" .venv

echo "Installing dependencies..."
if [ -n "${EXTRAS}" ]; then
  uv pip install -e ".[${EXTRAS}]"
else
  uv pip install -e .
fi

echo ""
echo "Installed. Try:"
echo "  ./.venv/bin/removebg-batch --help"

