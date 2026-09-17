@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EotU Official Cheat Flags - OFF

rem  Turns all four debug switches OFF:
rem    InfinateResources / FreeHatch / InstantBuild / InstantDig

set "PY=C:\Users\beimo\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=C:\Users\beimo\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py"
"%PY%" "scripts\cheat_flags.py" off
echo.
echo  All cheat flags are now OFF.
pause
