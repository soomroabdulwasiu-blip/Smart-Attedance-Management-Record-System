@echo off
setlocal
cd /d "%~dp0"
python -m venv .venv
if errorlevel 1 goto error
.venv\Scripts\python.exe -m pip install --require-hashes -r requirements.lock.txt
if errorlevel 1 goto error
.venv\Scripts\python.exe tools\fetch_models.py
if errorlevel 1 goto error
echo Setup completed. Run run.bat for one-time encrypted Oracle connection setup.
pause
exit /b 0
:error
echo Setup failed. Check Python and Internet connection.
pause
exit /b 1
