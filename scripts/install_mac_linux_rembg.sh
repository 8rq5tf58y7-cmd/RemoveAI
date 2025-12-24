#!/usr/bin/env bash
set -euo pipefail

# Installer for the OPTIONAL rembg engine.
# - Uses uv to install Python 3.12 into a local .venv
# - Installs the optional extra: .[rembg]
# - If llvmlite tries to build from source on macOS, it may need LLVM.
#   This script will attempt to install LLVM via Homebrew and re-run with LLVM env vars.

if [ "${EUID:-$(id -u)}" -eq 0 ]; then
  echo "Do NOT run this installer with sudo."
  echo "Run it as your normal user: ./scripts/install_mac_linux_rembg.sh"
  exit 2
fi

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "${ROOT_DIR}"

REQUIRED_PY="${REQUIRED_PY:-3.12}"

if ! command -v uv >/dev/null 2>&1; then
  echo "uv not found; installing it..."
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

echo "Installing Python ${REQUIRED_PY} (via uv) ..."
uv python install "${REQUIRED_PY}"

echo "Creating venv (.venv) ..."
uv venv --python "${REQUIRED_PY}" .venv

echo "Installing dependencies (with rembg extra)..."
set +e
uv pip install -e ".[rembg]"
RC=$?
set -e

if [ "${RC}" -ne 0 ]; then
  echo ""
  echo "rembg install failed. If the error mentions missing LLVMConfig.cmake / llvm-config.cmake,"
  echo "we can fix it by installing LLVM and pointing llvmlite's build at it."
  echo ""
  if command -v brew >/dev/null 2>&1; then
    echo "Homebrew detected. Installing LLVM (and CMake) ..."
    brew install llvm cmake || true
    LLVM_PREFIX="$(brew --prefix llvm)"
    export LLVM_CONFIG="${LLVM_PREFIX}/bin/llvm-config"
    export LLVM_DIR="${LLVM_PREFIX}/lib/cmake/llvm"
    export CMAKE_PREFIX_PATH="${LLVM_PREFIX}:${CMAKE_PREFIX_PATH:-}"
    echo "Retrying install with LLVM_CONFIG=${LLVM_CONFIG}"
    uv pip install -e ".[rembg]"
  else
    echo "Homebrew not found."
    echo "Install Homebrew, then re-run this installer:"
    echo "  https://brew.sh"
    exit "${RC}"
  fi
fi

echo ""
echo "Installed rembg option. Use:"
echo "  ./.venv/bin/removebg-batch --engine rembg --help"

