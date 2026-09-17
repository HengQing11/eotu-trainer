@echo off
chcp 65001 >nul
cd /d "%~dp0"
title EotU Royal Jelly (works while the game is running)

rem ============================================================
rem  Runtime royal-jelly refill. The game must be RUNNING.
rem
rem  Locating method = "anchor": it walks the level's object list,
rem  finds the colony object (fixed layout) and reads the jelly slot.
rem  This does NOT depend on the jelly value, so it also works for a
rem  brand-new colony whose jelly is 0.
rem
rem  If that fails, it falls back to asking you for the number shown
rem  in the in-game "adaptations" panel.
rem
rem  Exit codes of jelly_live.py:
rem     0 ok / 1 usage / 4 locate failed / 5 read-back mismatch
rem ============================================================

set "PY=C:\Users\beimo\.workbuddy\binaries\python\versions\3.13.12\python.exe"
if not exist "%PY%" set "PY=C:\Users\beimo\AppData\Local\Programs\Python\Python313\python.exe"
if not exist "%PY%" set "PY=py"

echo  ============================================================
echo   Royal Jelly refill  (the game must be RUNNING)
echo  ============================================================
echo.
echo  Looking for the colony object automatically, please wait...
echo.

"%PY%" "scripts\jelly_live.py"
set "RC=%ERRORLEVEL%"

if "%RC%"=="4" goto manual
goto done

:manual
echo.
echo  ---- Automatic detection failed ----
echo  Make sure you are inside a level (not on the world map).
echo  You can also open the in-game adaptations panel, read the Royal
echo  Jelly number and type it below (digits only).
echo  Press Enter on an empty line to quit.
echo.
set "CUR="
set /p "CUR=Royal Jelly = "
if not defined CUR goto done
"%PY%" "scripts\jelly_live.py" %CUR%
goto done

:done
echo.
pause
