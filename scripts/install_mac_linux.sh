#!/usr/bin/env bash
set -euo pipefail

# Creates a local virtualenv and installs dependencies.
# Usage: ./scripts/install_mac_linux.sh

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "Do NOT run this installer with sudo."
  echo "It creates a local .venv in your project folder and should run as your normal user."
  echo ""
  echo "Run:"
  echo "  ./scripts/install_mac_linux.sh"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

if [ -n "${PYTHON:-}" ]; then
  PYTHON="${PYTHON}"
elif command -v python3.12 >/dev/null 2>&1; then
  PYTHON="python3.12"
elif command -v python3.11 >/dev/null 2>&1; then
  PYTHON="python3.11"
else
  PYTHON="python3"
fi

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3.10+ first."
  exit 1
fi

PY_VER="$("${PYTHON}" - <<'PY'
import sys
print(f"{sys.version_info.major}.{sys.version_info.minor}")
PY
)"

case "${PY_VER}" in
  3.13)
    echo "Python ${PY_VER} detected."
    echo "This project currently requires Python 3.10–3.12 due to upstream wheels (llvmlite/numba) on macOS."
    echo ""
    echo "Install Python 3.12 and re-run:"
    echo "  PYTHON=python3.12 ./scripts/install_mac_linux.sh"
    exit 2
    ;;
esac

if [ ! -d ".venv" ]; then
  "${PYTHON}" -m venv .venv
fi

source ".venv/bin/activate"
export PIP_CACHE_DIR="${PIP_CACHE_DIR:-${ROOT_DIR}/.venv/pip-cache}"
python -m pip install -U pip
python -m pip install -U setuptools wheel
EXTRAS="${EXTRAS:-}"
if [ -n "${EXTRAS}" ]; then
  python -m pip install -e ".[${EXTRAS}]"
else
  python -m pip install -e .
fi

echo ""
echo "Installed. Try:"
echo "  ./.venv/bin/removebg-batch --help"

