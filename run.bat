@echo off
setlocal
cd /d "%~dp0"
set "AMRS_PYTHON=.venv\Scripts\python.exe"
if exist "%AMRS_PYTHON%" goto dependencies
echo Preparing AMRS Python environment for this folder...
where py.exe >nul 2>&1
if errorlevel 1 (
    python -c "import sys; sys.exit(sys.version_info[:2] != (3, 14))"
    if errorlevel 1 goto python_error
    python -m venv .venv
) else (
    py -3.14 -m venv .venv
)
if errorlevel 1 goto python_error

:dependencies
if exist ".venv\amrs-local-runtime.ready" goto launch
echo Installing the locked AMRS packages...
if exist "Offline_Wheels\" (
    "%AMRS_PYTHON%" -m pip install --disable-pip-version-check --no-index --find-links "Offline_Wheels" --require-hashes -r requirements.lock.txt
) else (
    "%AMRS_PYTHON%" -m pip install --disable-pip-version-check --require-hashes -r requirements.lock.txt
)
if errorlevel 1 exit /b 1
type nul > ".venv\amrs-local-runtime.ready"

:launch
"%AMRS_PYTHON%" -m tools.local_start %*
exit /b %errorlevel%

:python_error
echo AMRS needs Windows x64 Python 3.14. Install it and run this file again.
exit /b 1
