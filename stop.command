#!/bin/bash
# ColdChain Monitor - STOP (macOS)
# Double-click this file in Finder. It stops the system. Your data is KEPT.

cd "$(dirname "$0")" || exit 1

pause() {
  if [ -z "${COLDCHAIN_NO_PAUSE:-}" ]; then
    echo
    read -r -p "Press Enter to close this window..." _
  fi
}

for dir in /usr/local/bin "$HOME/.docker/bin" /opt/homebrew/bin /Applications/Docker.app/Contents/Resources/bin; do
  [ -x "$dir/docker" ] && PATH="$dir:$PATH"
done
export PATH

echo "============================================================"
echo " ColdChain Monitor - stopping"
echo "============================================================"

if ! command -v docker >/dev/null 2>&1; then
  echo "Docker Desktop is not installed, so nothing is running."
  pause
  exit 0
fi
if ! docker info >/dev/null 2>&1; then
  echo "Docker Desktop is not running, so ColdChain Monitor is already stopped."
  pause
  exit 0
fi

# 'down' removes the containers but NOT the data volume (no -v flag).
if docker compose down; then
  echo
  echo "ColdChain Monitor has stopped. Your data is kept for the next start."
  pause
  exit 0
fi

echo
echo "PROBLEM: The system could not be stopped cleanly. Your data has not been deleted."
echo "WHAT TO DO: Open Docker Desktop and stop the 'coldchain' containers there."
pause
exit 1
