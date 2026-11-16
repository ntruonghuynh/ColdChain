#!/bin/bash
# ColdChain Monitor - START (macOS)
# Double-click this file in Finder. It starts the system with Docker Desktop
# and opens it in your web browser. PostgreSQL persists; Hardhat history is in memory.

cd "$(dirname "$0")" || exit 1

pause() {
  if [ -z "${COLDCHAIN_NO_PAUSE:-}" ]; then
    echo
    read -r -p "Press Enter to close this window..." _
  fi
}

fail() {
  echo
  echo "------------------------------------------------------------"
  echo "PROBLEM: $1"
  [ -n "${2:-}" ] && echo "WHAT TO DO: $2"
  echo "------------------------------------------------------------"
  pause
  exit 1
}

echo "============================================================"
echo " ColdChain Monitor - starting"
echo "============================================================"

# Finder starts scripts with a short PATH; add the usual Docker Desktop locations.
for dir in /usr/local/bin "$HOME/.docker/bin" /opt/homebrew/bin /Applications/Docker.app/Contents/Resources/bin; do
  [ -x "$dir/docker" ] && PATH="$dir:$PATH"
done
export PATH

# 1. Is Docker installed?
if ! command -v docker >/dev/null 2>&1; then
  fail "Docker Desktop is not installed." \
       "Install Docker Desktop from https://www.docker.com/products/docker-desktop/ and run this file again."
fi

# 2. Is Docker running? If not, try to start Docker Desktop and wait up to 3 minutes.
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running. Starting it now (this can take a minute)..."
  open -a Docker >/dev/null 2>&1 || true
  for _ in $(seq 1 60); do
    docker info >/dev/null 2>&1 && break
    printf "."
    sleep 3
  done
  echo
  docker info >/dev/null 2>&1 || fail "Docker Desktop did not start." \
    "Open Docker Desktop yourself, wait until it shows 'Engine running', then run this file again."
fi

if ! docker compose version >/dev/null 2>&1; then
  fail "Docker Compose is not available." "Update Docker Desktop to a recent version."
fi

# 3. Local settings file (never overwritten if it already exists).
if [ ! -f .env ]; then
  cp .env.example .env || fail "Could not create the settings file .env." "Check that this folder is not read-only."
  echo "Created settings file .env from .env.example."
fi
python3 scripts/setup_local_env.py || fail "Could not initialize local M5 credentials." \
  "Run python3 scripts/setup_local_env.py from this folder, or fill the blank M5 secret values in .env."
PORT="$(grep -E '^FRONTEND_PORT=' .env | tail -n 1 | cut -d= -f2 | tr -d '[:space:]')"
PORT="${PORT:-3000}"
URL="http://localhost:${PORT}"

# 4. Pre-flight: is another program already using the port? (Skipped if ColdChain itself is running.)
if [ -z "$(docker compose ps -q --status running frontend 2>/dev/null)" ] \
   && lsof -nP -iTCP:"${PORT}" -sTCP:LISTEN >/dev/null 2>&1; then
  fail "Port ${PORT} is already used by another program." \
       "Close that program, or open the file .env, change FRONTEND_PORT=${PORT} to another number (for example 3001), save, and run this file again."
fi

# 5. Start all services and wait until they report healthy.
echo "Starting services. The first start downloads and builds everything and can take"
echo "several minutes. Later starts take a few seconds."
LOG="$(mktemp -t coldchain-start)"
if ! docker compose up -d --build --wait --wait-timeout 600 2>&1 | tee "$LOG"; then
  echo
  echo "Service status:"
  docker compose ps -a
  if grep -qiE "port is already allocated|address already in use|bind" "$LOG"; then
    fail "Port ${PORT} is already used by another program." \
         "Close that program, or open the file .env, change FRONTEND_PORT=${PORT} to another number (for example 3001), save, and run this file again."
  fi
  echo
  echo "Recent log messages:"
  docker compose logs --tail 40
  fail "The system did not start correctly." \
       "Read the messages above. See README.md, section 'Troubleshooting'. Your data has not been deleted."
fi
rm -f "$LOG"

# 6. Confirm the application answers through the web server.
if ! curl -fsS --max-time 10 "${URL}/api/health" >/dev/null 2>&1; then
  fail "The services started, but ${URL} does not answer as expected." \
       "Another program may be using port ${PORT}: change FRONTEND_PORT in .env (for example to 3001) and run this file again. Otherwise wait 30 seconds, open ${URL}, and see README.md 'Troubleshooting'."
fi

echo
echo "============================================================"
echo " ColdChain Monitor is running:  ${URL}"
echo " To stop it, double-click stop.command (your data is kept)."
echo "============================================================"
[ -z "${COLDCHAIN_NO_BROWSER:-}" ] && open "$URL"
pause
exit 0
