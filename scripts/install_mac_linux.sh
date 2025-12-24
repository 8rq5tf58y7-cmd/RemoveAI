#!/usr/bin/env bash
set -euo pipefail

# Creates a local virtualenv and installs dependencies.
# Usage: ./scripts/install_mac_linux.sh

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

PYTHON="${PYTHON:-python3}"

if ! command -v "${PYTHON}" >/dev/null 2>&1; then
  echo "python3 not found. Please install Python 3.10+ first."
  exit 1
fi

if [ ! -d ".venv" ]; then
  "${PYTHON}" -m venv .venv
fi

source ".venv/bin/activate"
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

