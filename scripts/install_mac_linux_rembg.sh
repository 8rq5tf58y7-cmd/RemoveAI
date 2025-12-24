#!/usr/bin/env bash
set -euo pipefail

# Installer for the OPTIONAL rembg engine.
# - Uses uv to install Python 3.12 into a local venv (.venv-rembg)
# - Installs the optional extra: .[rembg]
# - Forces modern numba/llvmlite (Python 3.12 compatible) and prefers binary wheels
#   to avoid source builds (and the LLVM toolchain) on macOS.

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "Do NOT run this installer with sudo."
  echo "Run it as your normal user: ./scripts/install_mac_linux_rembg.sh"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

REQUIRED_PY="${REQUIRED_PY:-3.12}"
VENV_DIR="${VENV_DIR:-.venv-rembg}"

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
    export PATH="${HOME}/.local/bin:${PATH}"
  fi
fi

echo "Installing Python ${REQUIRED_PY} (via uv) ..."
uv python install "${REQUIRED_PY}"

echo "Creating venv (${VENV_DIR}) ..."
uv venv --python "${REQUIRED_PY}" "${VENV_DIR}"

echo "Installing dependencies (with rembg extra)..."

source "${VENV_DIR}/bin/activate"

# Some uv-created venvs may not include pip until seeded.
python -m ensurepip --upgrade >/dev/null 2>&1 || true
python -m pip install -U pip setuptools wheel

# Prefer wheels for the heavy stack to avoid compilation on macOS.
python -m pip install --only-binary=:all: -c constraints/rembg_py312.txt "numba>=0.61" "llvmlite>=0.44"
python -m pip install -c constraints/rembg_py312.txt -e ".[rembg]"

echo ""
echo "Installed rembg option. Use:"
echo "  ${VENV_DIR}/bin/removebg-batch --engine rembg --help"

