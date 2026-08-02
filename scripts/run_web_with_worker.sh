#!/usr/bin/env bash
set -Eeuo pipefail

: "${ZPPZ_PYTHON_BIN:?ZPPZ_PYTHON_BIN is required}"
: "${ZPPZ_APP_PORT:?ZPPZ_APP_PORT is required}"
: "${ZPPZ_WEB_CONCURRENCY:?ZPPZ_WEB_CONCURRENCY is required}"

worker_pid=""
webhook_worker_pid=""
web_pid=""

stop_children() {
  trap - TERM INT
  if [ -n "$web_pid" ]; then
    kill -TERM "$web_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$worker_pid" ]; then
    kill -TERM "$worker_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$webhook_worker_pid" ]; then
    kill -TERM "$webhook_worker_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$web_pid" ]; then
    wait "$web_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$worker_pid" ]; then
    wait "$worker_pid" >/dev/null 2>&1 || true
  fi
  if [ -n "$webhook_worker_pid" ]; then
    wait "$webhook_worker_pid" >/dev/null 2>&1 || true
  fi
}

trap 'stop_children; exit 143' TERM INT

if command -v ionice >/dev/null 2>&1; then
  nice -n 10 ionice -c 2 -n 7 "$ZPPZ_PYTHON_BIN" -m app.worker &
else
  nice -n 10 "$ZPPZ_PYTHON_BIN" -m app.worker &
fi
worker_pid=$!

"$ZPPZ_PYTHON_BIN" -m app.webhook_worker &
webhook_worker_pid=$!

"$ZPPZ_PYTHON_BIN" -m uvicorn app.main:app \
  --host 127.0.0.1 \
  --port "$ZPPZ_APP_PORT" \
  --workers "$ZPPZ_WEB_CONCURRENCY" &
web_pid=$!

# Any process exiting is unhealthy. Stop its siblings and let systemd restart
# the complete cgroup so a dead Worker can never go unnoticed.
set +e
wait -n "$worker_pid" "$webhook_worker_pid" "$web_pid"
status=$?
set -e
stop_children
exit "$status"
