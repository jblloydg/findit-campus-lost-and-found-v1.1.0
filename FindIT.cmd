@echo off
rem ==========================================================================
rem  Find-IT v1.1.0 - one-click start for Windows
rem  First run: creates .venv, installs packages, builds the database and the
rem  fictional demo accounts. Later runs: just starts the site.
rem  Opens http://127.0.0.1:8000/ in your browser. Close this window to stop.
rem ==========================================================================
setlocal
title Find-IT v1.1.0
cd /d "%~dp0"

rem --- Find Python: prefer 3.13 / 3.14 (tested, officially supported by Django 5.2),
rem     then any Python 3.12 or newer -------------------------------------------
set "SYSPY="
where py >nul 2>nul || goto :trypython
for %%V in (3.13 3.14 3.12) do if not defined SYSPY py -%%V -c "import sys" >nul 2>nul && set "SYSPY=py -%%V"
if not defined SYSPY py -3 -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "SYSPY=py -3"
:trypython
if not defined SYSPY where python >nul 2>nul && python -c "import sys; sys.exit(0 if sys.version_info >= (3, 12) else 1)" >nul 2>nul && set "SYSPY=python"
if not defined SYSPY goto :nopython
for /f "delims=" %%P in ('%SYSPY% -c "import sys; print(sys.version.split()[0])"') do echo Using Python %%P

rem --- Virtual environment ---------------------------------------------------
set "PY=%~dp0.venv\Scripts\python.exe"
if exist "%PY%" goto :haveenv
echo [1/4] Creating the virtual environment - first run only...
%SYSPY% -m venv .venv || goto :fail
:haveenv

rem --- Packages (reinstalled only when requirements.txt changes) -------------
fc /b requirements.txt ".venv\installed-requirements.txt" >nul 2>nul && goto :havepkgs
echo [2/4] Installing packages - this can take a few minutes the first time...
"%PY%" -m pip install --upgrade pip >nul
"%PY%" -m pip install -r requirements.txt || goto :fail
copy /y requirements.txt ".venv\installed-requirements.txt" >nul
:havepkgs

rem --- Database ---------------------------------------------------------------
set "FIRSTDB="
if not exist db.sqlite3 set "FIRSTDB=1"
echo [3/4] Updating the database...
"%PY%" manage.py migrate --noinput || goto :fail
if not defined FIRSTDB goto :havedb
echo        Creating the fictional demo accounts...
"%PY%" manage.py seed_demo || goto :fail
:havedb

rem --- Start --------------------------------------------------------------------
echo [4/4] Starting Find-IT at http://127.0.0.1:8000/
echo        Close this window (or press Ctrl+C) to stop the website.
start "Find-IT timers" /min "%PY%" manage.py process_due --loop
start "" cmd /c "timeout /t 5 /nobreak >nul & start http://127.0.0.1:8000/"
"%PY%" manage.py runserver 127.0.0.1:8000
taskkill /fi "WINDOWTITLE eq Find-IT timers*" /t /f >nul 2>nul
goto :eof

:nopython
echo.
echo Python 3.12 or newer was not found.
echo Install it from https://www.python.org/downloads/ and tick
echo "Add python.exe to PATH" during setup, then run FindIT.cmd again.
echo.
pause
exit /b 1

:fail
echo.
echo Something went wrong (see the messages above). Nothing was deleted.
echo Copy the error text and send it to the developers.
echo.
pause
exit /b 1
