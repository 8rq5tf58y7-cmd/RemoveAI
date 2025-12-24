Param(
  [string]$RequiredPy = "3.12"
)

$ErrorActionPreference = "Stop"
Set-Location (Join-Path $PSScriptRoot "..")

function Ensure-Uv {
  if (Get-Command uv -ErrorAction SilentlyContinue) { return }
  Write-Host "uv not found; installing it..."
  irm https://astral.sh/uv/install.ps1 | iex
  $env:Path = "$env:USERPROFILE\.local\bin;$env:Path"
  if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    $env:Path = "$env:USERPROFILE\.cargo\bin;$env:Path"
  }
}

Ensure-Uv

Write-Host "Installing Python $RequiredPy (via uv) ..."
uv python install $RequiredPy

Write-Host "Creating venv (.venv) ..."
uv venv --python $RequiredPy .venv

Write-Host "Installing dependencies (with rembg extra)..."
uv pip install -e ".[rembg]"

Write-Host ""
Write-Host "Installed rembg option. Use:"
Write-Host "  .\.venv\Scripts\removebg-batch --engine rembg --help"

