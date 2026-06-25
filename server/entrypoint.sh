#!/bin/sh
set -eu

DB_FILE="${DB_PATH:-/data/traffic.db}"
DB_DIR="$(dirname "$DB_FILE")"
LOG_PATH="${LOG_DIR:-/logs}"
mkdir -p "$LOG_PATH" "$DB_DIR"
touch "$LOG_PATH/uvicorn.log" "$LOG_PATH/uvicorn-error.log"

ACCESS_LOG_FLAG=""
if [ "${UVICORN_ACCESS_LOG:-false}" = "true" ]; then
  ACCESS_LOG_FLAG="--access-log"
else
  ACCESS_LOG_FLAG="--no-access-log"
fi

# --- Collector selection (production: Go-libpcap > Python-Scapy) ---

. /app/server/entrypoint_helpers.sh

REQUESTED_GO_COLLECTOR_PORT="${GO_COLLECTOR_PORT:-18088}"
GO_COLLECTOR_PORT="$(resolve_go_collector_port)"
COLLECTOR_MODE="${COLLECTOR_MODE:-auto}"
COLLECTOR_PROFILE="${COLLECTOR_PROFILE:-balanced}"
GO_COLLECTOR_ENABLED="${GO_COLLECTOR_ENABLED:-true}"

try_go_libpcap() {
  GO_BIN="${GO_COLLECTOR_BIN:-/app/bin/go-collector}"
  if [ -x "$GO_BIN" ]; then
    if [ "$GO_COLLECTOR_PORT" != "$REQUESTED_GO_COLLECTOR_PORT" ]; then
      echo "Go collector port $REQUESTED_GO_COLLECTOR_PORT conflicts with APP_PORT ${APP_PORT:-8088}; using $GO_COLLECTOR_PORT instead"
    fi
    echo "Starting Go libpcap collector on port $GO_COLLECTOR_PORT..."
    "$GO_BIN" -port "$GO_COLLECTOR_PORT" &
    export GO_COLLECTOR_URL="http://127.0.0.1:${GO_COLLECTOR_PORT}"
    return 0
  fi
  return 1
}

if [ "$GO_COLLECTOR_ENABLED" != "true" ] || [ "$COLLECTOR_PROFILE" = "low" ] || [ "$COLLECTOR_MODE" = "off" ] || [ "$COLLECTOR_MODE" = "python" ]; then
  echo "External collector disabled; using Python/system counters profile"
elif [ "$COLLECTOR_MODE" = "ebpf" ]; then
  echo "eBPF collector is experimental in this build; starting Go libpcap instead"
  try_go_libpcap || echo "Go collector unavailable, falling back to Python Scapy"
elif [ "$COLLECTOR_MODE" = "golibpcap" ]; then
  try_go_libpcap || echo "Go collector unavailable, falling back to Python Scapy"
else
  if ! try_go_libpcap; then
    echo "Go collector unavailable, using Python Scapy"
  fi
fi

if [ "${FILE_LOG:-true}" != "true" ]; then
  exec uvicorn server.main:app \
    --host 0.0.0.0 \
    --port "${APP_PORT:-8088}" \
    $ACCESS_LOG_FLAG
fi

if [ "${CONSOLE_LOG:-true}" = "true" ]; then
  tail -n 0 -q -F "$LOG_PATH/uvicorn.log" "$LOG_PATH/uvicorn-error.log" &
fi

exec uvicorn server.main:app \
  --host 0.0.0.0 \
  --port "${APP_PORT:-8088}" \
  $ACCESS_LOG_FLAG \
  >> "$LOG_PATH/uvicorn.log" \
  2>> "$LOG_PATH/uvicorn-error.log"
