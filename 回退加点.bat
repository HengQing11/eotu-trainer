@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EotU Undo Addons
set "PY=C:\Users\beimo\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" "scripts\revert_addons.py" %*
echo.
pause
