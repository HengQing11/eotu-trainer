@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EotU Official Cheat Flags (auto-closes when the level ends)

rem  Opens the game's own debug switches on the current level grid:
rem    InfinateResources / FreeHatch / InstantBuild / InstantDig
rem  They are re-asserted every 0.5s and re-applied on level change.
rem  Close this window to turn off the keep-alive (flags stay as they are).

set "PY=C:\Users\beimo\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=C:\Users\beimo\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py"
echo  Official cheat flags: ON (infinite resources / free hatch / instant build / instant dig)
echo.
echo  Close this window to stop the keep-alive.
echo  It also stops BY ITSELF (and closes this window) when the level ends.
echo.
"%PY%" "scripts\cheat_flags.py" on 86400
set "RC=%ERRORLEVEL%"

if "%RC%"=="10" (
    echo.
    echo  Level finished - cheat keep-alive stopped.
    ping -n 2 127.0.0.1 >nul
    exit
)
if "%RC%"=="2" (
    echo.
    echo  Not inside a level yet - enter a level first, then run this again.
    ping -n 3 127.0.0.1 >nul
    exit
)

echo.
pause
