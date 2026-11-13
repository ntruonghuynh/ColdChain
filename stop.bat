@echo off
REM ColdChain Monitor - STOP (Windows)
REM Double-click this file. It stops the system. Your data is KEPT.
setlocal EnableExtensions
cd /d "%~dp0"
title ColdChain Monitor - Stop

echo ============================================================
echo  ColdChain Monitor - stopping
echo ============================================================

where docker >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not installed, so nothing is running.
  goto done
)
docker info >nul 2>&1
if errorlevel 1 (
  echo Docker Desktop is not running, so ColdChain Monitor is already stopped.
  goto done
)

REM 'down' removes the containers but NOT the data volume (no -v flag).
docker compose down
if errorlevel 1 (
  echo.
  echo PROBLEM: The system could not be stopped cleanly. Your data has not been deleted.
  echo WHAT TO DO: Open Docker Desktop and stop the "coldchain" containers there.
  echo.
  pause
  exit /b 1
)
echo.
echo ColdChain Monitor has stopped. Your data is kept for the next start.

:done
echo.
pause
exit /b 0
