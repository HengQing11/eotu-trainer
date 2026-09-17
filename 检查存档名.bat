@echo off
chcp 65001 >nul
cd /d "%~dp0"

set "PY=%LOCALAPPDATA%\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=%LOCALAPPDATA%\Programs\Python\Python313\pythonw.exe"
if not exist "%PY%" set "PY=python"

"%PY%" "scripts\try_saves.py"
echo.
pause
