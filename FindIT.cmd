@echo off
rem ==========================================================================
rem  Find-IT v1.1.2 - one-click menu for Windows
rem  Double-click this file. The first time it installs everything by itself
rem  (needs internet once). Then pick a number from the menu.
rem  Doing nothing for 20 seconds starts Find-IT automatically - only the
rem  first time the menu shows (BUG-009: it used to repeat every 20 seconds).
rem ==========================================================================
setlocal EnableExtensions
title Find-IT v1.1.2
cd /d "%~dp0"
set "PY=%~dp0.venv\Scripts\python.exe"

call :findpython
if not defined SYSPY goto :nopython
call :setup
if errorlevel 1 goto :fail

rem AUTOSTART is set until the menu has shown once; after that the menu waits.
set "AUTOSTART=1"

:menu
cls
echo.
echo   ==================  Find-IT v1.1.2  ==================
echo.
echo     1  Start Find-IT  ^(opens your browser^)
echo     2  Show the demo sign-ins for this PC
echo     3  Reset the demo data  ^(fresh database; a backup is made first^)
echo     4  Run the automatic checks  ^(about 2 minutes^)
echo     5  Make a backup now
echo     6  Developer account
echo     0  Quit
echo.
if defined AUTOSTART (
  echo   Starts automatically in 20 seconds if you press nothing.
  echo.
  set "AUTOSTART="
  choice /c 1234560 /n /t 20 /d 1 /m "  Type a number: "
) else (
  choice /c 1234560 /n /m "  Type a number: "
)
if errorlevel 7 goto :eof
if errorlevel 6 goto :developer
if errorlevel 5 goto :backup
if errorlevel 4 goto :checks
if errorlevel 3 goto :reset
if errorlevel 2 goto :accounts
goto :start

rem --------------------------------------------------------------------------
:start
netstat -ano | findstr /r /c:":8000 .*LISTENING" >nul 2>nul
if not errorlevel 1 (
  echo.
  echo   Find-IT is already running in another window.
  echo   Opening http://127.0.0.1:8000/ in your browser once.
  echo   You can close this extra window; keep the other one open.
  start "" http://127.0.0.1:8000/
  echo.
  pause
  goto :menu
)
taskkill /fi "WINDOWTITLE eq Find-IT timers*" /t /f >nul 2>nul
cls
echo.
echo   Find-IT is starting at http://127.0.0.1:8000/  - your browser opens in a few seconds.
echo.
echo   KEEP THIS WINDOW OPEN while you use Find-IT.
echo   To stop: close this window, or press Ctrl+C and then Y.
echo.
echo   Test emails ^(verification codes^) appear below and on the "Test inbox" page.
echo   ------------------------------------------------------------------------
start "Find-IT timers" /min "%PY%" manage.py process_due --loop
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://127.0.0.1:8000/"
"%PY%" manage.py runserver 127.0.0.1:8000
taskkill /fi "WINDOWTITLE eq Find-IT timers*" /t /f >nul 2>nul
goto :eof

rem --------------------------------------------------------------------------
:accounts
cls
echo.
echo   Demo sign-ins for THIS PC ^(fictional accounts, local testing only^)
echo.
rem v1.1.2: passwords are made on this PC. Older databases get new ones the first time.
if not exist demo-logins.txt "%PY%" manage.py seed_demo --logins-only >nul
if exist demo-logins.txt (
  type demo-logins.txt
) else (
  echo   No demo sign-ins yet. Use menu 3 to make the demo data first.
)
echo.
echo   Each PC has its own random passwords. Never post them online.
echo.
pause
goto :menu

rem --------------------------------------------------------------------------
:reset
cls
echo.
echo   This deletes ALL local Find-IT data on this PC ^(posts, accounts, photos^)
echo   and creates fresh demo data. A backup is made first, just in case.
echo   Close any running Find-IT window first.
echo.
choice /c YN /n /m "  Are you sure? Type Y for yes or N for no: "
if errorlevel 2 goto :menu
if exist db.sqlite3 "%PY%" manage.py backup_now
if exist db.sqlite3 del /q db.sqlite3
if exist db.sqlite3 (
  echo.
  echo   The database is still in use. Close the other Find-IT window and try again.
  pause
  goto :menu
)
if exist media rmdir /s /q media
"%PY%" manage.py migrate --noinput || goto :fail
"%PY%" manage.py seed_demo || goto :fail
echo.
echo   Done. Fresh demo data is ready.
pause
goto :menu

rem --------------------------------------------------------------------------
:checks
cls
echo.
echo   Running the automatic checks. "OK" at the end means everything passed.
echo.
"%PY%" manage.py check
"%PY%" manage.py makemigrations --check --dry-run
"%PY%" manage.py test core
echo.
pause
goto :menu

rem --------------------------------------------------------------------------
:backup
cls
"%PY%" manage.py backup_now
"%PY%" manage.py backup_now --list
echo.
echo   Backups are in the "backups" folder. Keep it private: it contains chats and claim answers.
pause
goto :menu

rem --------------------------------------------------------------------------
:developer
cls
echo.
echo     1  Create the Developer account
echo     2  Reset the Developer password
echo     0  Back
echo.
choice /c 120 /n /m "  Type a number: "
if errorlevel 3 goto :menu
if errorlevel 2 (
  "%PY%" manage.py create_developer --reset-password
) else (
  "%PY%" manage.py create_developer
)
echo.
pause
goto :menu

rem ==========================================================================
rem  Helpers
rem ==========================================================================
:findpython
rem Prefer Python 3.13 / 3.14 (tested, supported by Django 5.2), then 3.12.
set "SYSPY="
where py >nul 2>nul
if not errorlevel 1 (
  for %%V in (3.13 3.14 3.12) do if not defined SYSPY py -%%V -c "import sys" >nul 2>nul && set "SYSPY=py -%%V"
)
if not defined SYSPY (
  where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "SYSPY=python"
)
exit /b 0

:setup
if exist "%PY%" goto :haveenv
echo.
echo   First run: setting up Find-IT. This takes a few minutes and needs internet once.
echo   [1/3] Creating the private Python folder ^(.venv^)...
%SYSPY% -m venv .venv
if errorlevel 1 exit /b 1
:haveenv
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul
if not errorlevel 1 goto :havepkgs
echo   [2/3] Installing packages...
"%PY%" -m pip install --upgrade pip >nul 2>nul
"%PY%" -m pip install -r requirements.txt
if errorlevel 1 (
  echo.
  echo   Packages could not be installed. Check your internet connection and try again.
  exit /b 1
)
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
:havepkgs
set "FIRSTDB="
if not exist db.sqlite3 set "FIRSTDB=1"
echo   [3/3] Updating the database...
"%PY%" manage.py migrate --noinput
if errorlevel 1 exit /b 1
if defined FIRSTDB (
  echo          Creating the fictional demo accounts...
  "%PY%" manage.py seed_demo
  if errorlevel 1 exit /b 1
)
exit /b 0

:nopython
cls
echo.
echo   Python 3.13 is needed and was not found on this PC.
echo.
where winget >nul 2>nul
if errorlevel 1 goto :pythonsite
choice /c YN /n /m "  Install Python 3.13 now? Type Y for yes or N for no: "
if errorlevel 2 goto :pythonsite
winget install -e --id Python.Python.3.13 --accept-source-agreements --accept-package-agreements
echo.
echo   When the install finishes, CLOSE this window and double-click FindIT.cmd again.
pause
exit /b 1
:pythonsite
echo   Opening the Python download page. Install Python 3.13 and TICK
echo   "Add python.exe to PATH" on the first screen. Then double-click FindIT.cmd again.
start "" https://www.python.org/downloads/
echo.
pause
exit /b 1

:fail
echo.
echo   Something went wrong ^(see the messages above^). Nothing was deleted.
echo   Take a screenshot of this window and send it to the developers.
echo.
pause
exit /b 1
