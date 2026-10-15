@echo off
setlocal
cd /d "%~dp0"
set "PYTHONDONTWRITEBYTECODE=1"
set "PYTHONW=%~dp0runtime\pythonw.exe"
set "PYTHON=%~dp0runtime\python.exe"
if exist "%PYTHONW%" goto launch
echo Bundled Python is missing: "%PYTHONW%"
echo Keep the runtime folder beside this launcher.
pause
exit /b 1
:launch
"%PYTHON%" "%~dp0portable_bootstrap.py"
if errorlevel 1 (
    pause
    exit /b 1
)
start "TWW Moving Object Drop Finder" "%PYTHONW%" -m harness.collision.object_route_gui
