#!/bin/sh
set -eu

. ./server/entrypoint_helpers.sh

assert_eq() {
  actual="$1"
  expected="$2"
  name="$3"
  if [ "$actual" != "$expected" ]; then
    echo "FAIL: $name: expected $expected, got $actual" >&2
    exit 1
  fi
}

assert_eq "$(APP_PORT=8088 resolve_go_collector_port)" "18088" "default collector port"
assert_eq "$(APP_PORT=18088 resolve_go_collector_port)" "18089" "collector port avoids APP_PORT"
assert_eq "$(APP_PORT=8088 GO_COLLECTOR_PORT=19000 resolve_go_collector_port)" "19000" "custom collector port"
assert_eq "$(APP_PORT=19000 GO_COLLECTOR_PORT=19000 resolve_go_collector_port)" "19001" "custom collector port avoids APP_PORT"

echo "entrypoint helper tests passed"
