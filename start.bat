@echo off
setlocal EnableExtensions EnableDelayedExpansion

rem =============================================================================
rem  TAM / Meraqi — one-click local stack startup
rem  Starts: Docker Desktop (if installed), optional compose services,
rem          FastAPI backend (uvicorn), Next.js frontend (npm run dev)
rem =============================================================================

cd /d "%~dp0"
set "ROOT=%CD%"
set "BACKEND_DIR=%ROOT%\backend"
set "FRONTEND_DIR=%ROOT%\frontend"
set "VENV_PY=%BACKEND_DIR%\.venv\Scripts\python.exe"
set "DOCKER_DESKTOP=%ProgramFiles%\Docker\Docker\Docker Desktop.exe"
set "BACKEND_URL=http://localhost:8000"
set "FRONTEND_URL=http://localhost:3000"
set "HEALTH_URL=%BACKEND_URL%/health"

echo.
echo ========================================
echo   TAM local stack startup
echo ========================================
echo   Root: %ROOT%
echo.

rem --- 1) Docker Desktop -------------------------------------------------------
call :ensure_docker
if errorlevel 1 (
  echo [warn] Continuing without Docker. Backend/frontend do not require it today.
) else (
  call :maybe_compose_up
)

rem --- 2) Backend prerequisites ------------------------------------------------
if not exist "%VENV_PY%" (
  echo [error] Backend venv not found: %VENV_PY%
  echo         Run:  cd backend ^&^& python -m venv .venv ^&^& .venv\Scripts\pip install -e ".[dev]"
  exit /b 1
)

rem --- 3) Frontend prerequisites ----------------------------------------------
where npm >nul 2>&1
if errorlevel 1 (
  echo [error] npm not found on PATH. Install Node.js 20+ and retry.
  exit /b 1
)
if not exist "%FRONTEND_DIR%\node_modules\" (
  echo [info] frontend\node_modules missing - running npm install...
  pushd "%FRONTEND_DIR%"
  call npm install
  if errorlevel 1 (
    echo [error] npm install failed.
    popd
    exit /b 1
  )
  popd
)

rem --- 4) Launch services in dedicated windows --------------------------------
echo.
echo [info] Starting backend  (uvicorn)  on %BACKEND_URL%
start "TAM Backend" /D "%BACKEND_DIR%" cmd /k ""%VENV_PY%" -m uvicorn app.main:app --reload --host 127.0.0.1 --port 8000"

echo [info] Starting frontend (Next.js) on %FRONTEND_URL%
start "TAM Frontend" /D "%FRONTEND_DIR%" cmd /k "npm run dev"

rem --- 5) Wait for backend health (best-effort) --------------------------------
echo.
echo [info] Waiting for backend health at %HEALTH_URL% ...
set /a "TRIES=0"
:wait_health
set /a "TRIES+=1"
curl -fsS "%HEALTH_URL%" >nul 2>&1
if not errorlevel 1 goto health_ok
if !TRIES! GEQ 40 (
  echo [warn] Backend health check timed out. Check the "TAM Backend" window.
  goto summary
)
timeout /t 1 /nobreak >nul
goto wait_health

:health_ok
echo [ok]   Backend is healthy.

:summary
echo.
echo ========================================
echo   Stack is starting
echo ========================================
echo   Backend API : %BACKEND_URL%
echo   API docs    : %BACKEND_URL%/docs
echo   Frontend    : %FRONTEND_URL%
echo.
echo   Close the "TAM Backend" / "TAM Frontend" windows to stop those services.
if exist "%ROOT%\docker-compose.yml" (
  echo   Docker: docker compose -f "%ROOT%\docker-compose.yml" down
) else if exist "%ROOT%\compose.yml" (
  echo   Docker: docker compose -f "%ROOT%\compose.yml" down
)
echo ========================================
echo.

start "" "%FRONTEND_URL%"
exit /b 0

rem =============================================================================
rem  Helpers
rem =============================================================================

:ensure_docker
where docker >nul 2>&1
if errorlevel 1 (
  echo [warn] Docker CLI not found on PATH. Skipping Docker startup.
  exit /b 1
)

docker info >nul 2>&1
if not errorlevel 1 (
  echo [ok]   Docker daemon is already running.
  exit /b 0
)

if not exist "%DOCKER_DESKTOP%" (
  echo [warn] Docker Desktop not found at:
  echo         %DOCKER_DESKTOP%
  exit /b 1
)

echo [info] Starting Docker Desktop...
start "" "%DOCKER_DESKTOP%"

set /a "TRIES=0"
:wait_docker
set /a "TRIES+=1"
docker info >nul 2>&1
if not errorlevel 1 (
  echo [ok]   Docker daemon is ready.
  exit /b 0
)
if !TRIES! GEQ 90 (
  echo [warn] Timed out waiting for Docker daemon ^(~90s^).
  exit /b 1
)
timeout /t 1 /nobreak >nul
goto wait_docker

:maybe_compose_up
set "COMPOSE_FILE="
if exist "%ROOT%\docker-compose.yml" set "COMPOSE_FILE=%ROOT%\docker-compose.yml"
if exist "%ROOT%\compose.yml" set "COMPOSE_FILE=%ROOT%\compose.yml"
if exist "%ROOT%\docker-compose.yaml" set "COMPOSE_FILE=%ROOT%\docker-compose.yaml"
if exist "%ROOT%\compose.yaml" set "COMPOSE_FILE=%ROOT%\compose.yaml"

if not defined COMPOSE_FILE (
  echo [info] No compose file found - skipping docker compose up.
  echo        ^(Backend/frontend run natively; add docker-compose.yml when needed.^)
  exit /b 0
)

echo [info] Running: docker compose -f "%COMPOSE_FILE%" up -d
docker compose -f "%COMPOSE_FILE%" up -d
if errorlevel 1 (
  echo [warn] docker compose up failed. Continuing with app services.
  exit /b 1
)
echo [ok]   Compose services are up.
exit /b 0
