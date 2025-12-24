Param(
  [string]$RequiredPy = "3.12",
  [string]$Extras = ""
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

Write-Host "Installing dependencies..."
if ($Extras -ne "") {
  uv pip install -e ".[$Extras]"
} else {
  uv pip install -e .
}

Write-Host ""
Write-Host "Installed. Try:"
Write-Host "  .\.venv\Scripts\removebg-batch --help"

