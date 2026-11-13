@echo off
REM ColdChain Monitor - START (Windows)
REM Double-click this file. It starts the system with Docker Desktop and opens
REM it in your web browser. Your data is kept between runs.
setlocal EnableExtensions
cd /d "%~dp0"
title ColdChain Monitor - Start

echo ============================================================
echo  ColdChain Monitor - starting
echo ============================================================

REM 1. Is Docker installed?
where docker >nul 2>&1
if errorlevel 1 (
  echo.
  echo PROBLEM: Docker Desktop is not installed.
  echo WHAT TO DO: Install Docker Desktop from https://www.docker.com/products/docker-desktop/
  echo            and run this file again.
  goto fail
)

REM 2. Is Docker running? If not, try to start Docker Desktop and wait up to 3 minutes.
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
echo Docker Desktop is not running. Starting it now (this can take a minute)...
if exist "%ProgramFiles%\Docker\Docker\Docker Desktop.exe" start "" "%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set /a TRIES=0
:wait_docker
timeout /t 3 /nobreak >nul
docker info >nul 2>&1
if not errorlevel 1 goto docker_ready
set /a TRIES+=1
if %TRIES% lss 60 goto wait_docker
echo.
echo PROBLEM: Docker Desktop did not start.
echo WHAT TO DO: Open Docker Desktop yourself, wait until it shows "Engine running",
echo            then run this file again.
goto fail

:docker_ready
docker compose version >nul 2>&1
if errorlevel 1 (
  echo.
  echo PROBLEM: Docker Compose is not available.
  echo WHAT TO DO: Update Docker Desktop to a recent version.
  goto fail
)

REM 3. Local settings file (never overwritten if it already exists).
if not exist ".env" (
  copy /y ".env.example" ".env" >nul
  if errorlevel 1 (
    echo PROBLEM: Could not create the settings file .env.
    goto fail
  )
  echo Created settings file .env from .env.example.
)
set "PORT=3000"
for /f "tokens=1,* delims==" %%A in ('findstr /b /c:"FRONTEND_PORT=" ".env"') do set "PORT=%%B"
set "URL=http://localhost:%PORT%"

REM 4. Pre-flight: is another program already using the port? (Skipped if ColdChain itself is running.)
set "OURS="
for /f %%I in ('docker compose ps -q --status running frontend 2^>nul') do set "OURS=1"
if defined OURS goto port_ok
netstat -ano | findstr /r /c:":%PORT% .*LISTENING" >nul 2>&1
if errorlevel 1 goto port_ok
echo.
echo PROBLEM: Port %PORT% is already used by another program.
echo WHAT TO DO: Close that program, or edit .env and change FRONTEND_PORT to another
echo            number (for example 3001), save, and run this file again.
goto fail
:port_ok

REM 5. Start all services and wait until they report healthy.
echo Starting services. The first start downloads and builds everything and can take
echo several minutes. Later starts take a few seconds.
docker compose up -d --build --wait --wait-timeout 600
if errorlevel 1 goto start_failed

REM 6. Confirm the application answers through the web server.
curl -fsS --max-time 10 "%URL%/api/health" >nul 2>&1
if errorlevel 1 (
  echo.
  echo PROBLEM: The services started, but %URL% does not answer as expected.
  echo WHAT TO DO: Another program may be using port %PORT%: change FRONTEND_PORT in .env
  echo            for example to 3001, and run this file again. Otherwise wait 30 seconds,
  echo            open %URL%, and see README.md section "Troubleshooting".
  goto fail
)

echo.
echo ============================================================
echo  ColdChain Monitor is running:  %URL%
echo  To stop it, double-click stop.bat (your data is kept).
echo ============================================================
start "" "%URL%"
echo.
pause
exit /b 0

:start_failed
echo.
echo Service status:
docker compose ps -a
echo.
echo Recent log messages:
docker compose logs --tail 40
echo.
echo PROBLEM: The system did not start correctly. Your data has not been deleted.
echo WHAT TO DO: If a message above says the port is "already allocated", another
echo            program uses port %PORT%. Close it, or edit .env and change
echo            FRONTEND_PORT to another number (for example 3001).
echo            Otherwise see README.md section "Troubleshooting".

:fail
echo.
pause
exit /b 1
