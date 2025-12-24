@echo off
setlocal enabledelayedexpansion

REM Creates a local virtualenv and installs dependencies.
REM Usage: scripts\install_windows.bat

cd /d "%~dp0\.."

if not exist ".venv" (
  py -3 -m venv .venv
)

call ".venv\Scripts\activate.bat"
python -m pip install -U pip
python -m pip install -U setuptools wheel
if not "%EXTRAS%"=="" (
  python -m pip install -e ".[%EXTRAS%]"
) else (
  python -m pip install -e .
)

echo.
echo Installed. Try:
echo   .\.venv\Scripts\removebg-batch --help

endlocal

