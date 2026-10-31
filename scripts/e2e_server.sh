#!/usr/bin/env bash
# Ephemeral API for Playwright smoke tests.
# Serves frontend/dist (same path as production) from a fresh sqlite database.
# Defaults match frontend/e2e/constants.ts. Does not read production secrets or R2.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
# Fixed location so a bad override cannot wipe another directory.
E2E_DIR="$ROOT/.e2e"

PORT="${E2E_PORT:-8765}"
BASE_URL="${E2E_BASE_URL:-http://127.0.0.1:${PORT}}"
ADMIN_CODE="${E2E_ADMIN_CODE:-admin}"
ADMIN_PASSWORD="${E2E_ADMIN_PASSWORD:-e2e-admin-password}"

if [[ ! "$PORT" =~ ^[0-9]+$ ]]; then
  echo "E2E_PORT must be a number" >&2
  exit 1
fi

if [[ ! -f "$ROOT/frontend/dist/index.html" ]]; then
  echo "frontend/dist/index.html is missing. From frontend/: npm run build" >&2
  exit 1
fi

if [[ -n "${PYTHON:-}" ]]; then
  :
elif [[ -x "$ROOT/backend/.venv/bin/python" ]]; then
  PYTHON="$ROOT/backend/.venv/bin/python"
elif command -v python >/dev/null 2>&1; then
  PYTHON=python
else
  PYTHON=python3
fi

rm -rf "$E2E_DIR"
mkdir -p "$E2E_DIR/data"

# Override any developer environment so smoke runs cannot attach to a real DB or R2.
export DATA_DIR="$E2E_DIR/data"
export DATABASE_URL="sqlite:///${E2E_DIR}/e2e.db"
export PUBLIC_BASE_URL="$BASE_URL"
export SECURE_COOKIES=false
export SECRET_KEY="e2e-smoke-secret-key"
export WEBHOOK_SIGNING_MASTER_KEY="e2e-webhook-master-key"
export ADMIN_SEED_CODE="$ADMIN_CODE"
export ADMIN_SEED_PASSWORD="$ADMIN_PASSWORD"
export OBJECT_STORAGE_BACKEND=local
export PREVIEW_ENABLED=false
export SENTRY_DSN=""
export BAN_EXTERNAL_PROVIDER=disabled
export METRICS_TOKEN=""
export WEB_CONCURRENCY=1
export PYTHONUNBUFFERED=1

cd "$ROOT/backend"
"$PYTHON" -m app.prepare
echo "e2e server ${BASE_URL} admin=${ADMIN_CODE}"
exec "$PYTHON" -m uvicorn app.main:app --host 127.0.0.1 --port "$PORT"
