#!/bin/sh

resolve_go_collector_port() {
  app_port="${APP_PORT:-8088}"
  collector_port="${GO_COLLECTOR_PORT:-18088}"

  if [ "$collector_port" = "$app_port" ]; then
    collector_port=$((collector_port + 1))
  fi

  printf '%s\n' "$collector_port"
}
