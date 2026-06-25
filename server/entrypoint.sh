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

# --- Collector selection (priority: eBPF > Go-libpcap > Python-Scapy) ---

GO_COLLECTOR_PORT="${GO_COLLECTOR_PORT:-18088}"

try_ebpf() {
  EBPF_BIN="${GO_COLLECTOR_EBPF_BIN:-/app/bin/go-collector-ebpf}"
  if [ -x "$EBPF_BIN" ] && [ -e /sys/kernel/btf/vmlinux ]; then
    echo "Starting eBPF collector on port $GO_COLLECTOR_PORT..."
    "$EBPF_BIN" -port "$GO_COLLECTOR_PORT" &
    export GO_COLLECTOR_URL="http://127.0.0.1:${GO_COLLECTOR_PORT}"
    return 0
  fi
  return 1
}

try_go_libpcap() {
  GO_BIN="${GO_COLLECTOR_BIN:-/app/bin/go-collector}"
  if [ -x "$GO_BIN" ]; then
    echo "Starting Go libpcap collector on port $GO_COLLECTOR_PORT..."
    "$GO_BIN" -port "$GO_COLLECTOR_PORT" &
    export GO_COLLECTOR_URL="http://127.0.0.1:${GO_COLLECTOR_PORT}"
    return 0
  fi
  return 1
}

if [ "${COLLECTOR_MODE:-auto}" = "ebpf" ]; then
  try_ebpf || try_go_libpcap || echo "eBPF collector unavailable, falling back to Python Scapy"
elif [ "${COLLECTOR_MODE:-auto}" = "golibpcap" ]; then
  try_go_libpcap || echo "Go collector unavailable, falling back to Python Scapy"
else
  # auto mode: try eBPF first, then Go, then Python
  if ! try_ebpf; then
    if ! try_go_libpcap; then
      echo "No external collector available, using Python Scapy"
    fi
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
