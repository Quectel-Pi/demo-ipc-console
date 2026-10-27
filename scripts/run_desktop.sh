#!/usr/bin/env bash
set -e
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
cd "$PROJECT_ROOT"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
export CAMERA_IP="${CAMERA_IP:-192.0.2.10}"
export CAMERA_USER="${CAMERA_USER:-admin}"
export CAMERA_PASSWORD="${CAMERA_PASSWORD:-}"
PYTHON_BIN="python3"
if [ -x "$PROJECT_ROOT/.venv/bin/python" ]; then
  PYTHON_BIN="$PROJECT_ROOT/.venv/bin/python"
fi
exec "$PYTHON_BIN" src/desktop_app.py
