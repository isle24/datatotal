#!/bin/sh
set -eu

DB_FILE="${DB_PATH:-/data/traffic.db}"
DB_DIR="$(dirname "$DB_FILE")"
LOG_PATH="${LOG_DIR:-/logs}"
mkdir -p "$LOG_PATH" "$DB_DIR"
touch "$LOG_PATH/uvicorn.log" "$LOG_PATH/uvicorn-error.log"

if [ "${CONSOLE_LOG:-true}" = "true" ]; then
  tail -n 0 -q -F "$LOG_PATH/uvicorn.log" "$LOG_PATH/uvicorn-error.log" &
fi

ACCESS_LOG_FLAG=""
if [ "${UVICORN_ACCESS_LOG:-false}" = "true" ]; then
  ACCESS_LOG_FLAG="--access-log"
else
  ACCESS_LOG_FLAG="--no-access-log"
fi

exec uvicorn server.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT:-8088}" \
  $ACCESS_LOG_FLAG \
  >> "$LOG_PATH/uvicorn.log" \
  2>> "$LOG_PATH/uvicorn-error.log"
