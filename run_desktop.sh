#!/usr/bin/env bash
set -e
cd "$(dirname "$0")"
if [ -f .env ]; then
  set -a
  . ./.env
  set +a
fi
export CAMERA_IP="${CAMERA_IP:-192.0.2.10}"
export CAMERA_USER="${CAMERA_USER:-admin}"
export CAMERA_PASSWORD="${CAMERA_PASSWORD:-}"
exec python3 desktop_app.py
