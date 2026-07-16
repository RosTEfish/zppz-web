#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${RELEASE_NAME:?RELEASE_NAME is required}"

SERVICE_NAME="${SERVICE_NAME:-zppz-web}"
APP_PORT="${APP_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
RUN_USER="${RUN_USER:-$(id -un)}"
RUN_GROUP="${RUN_GROUP:-$(id -gn)}"

app_dir="$DEPLOY_PATH"
deploy_state_dir="$app_dir/.deploy"
incoming_dir="$deploy_state_dir/incoming"
releases_dir="$deploy_state_dir/releases"
pip_cache_dir="$deploy_state_dir/pip-cache"
archive_path="$incoming_dir/$RELEASE_NAME.tar.gz"
release_dir="$releases_dir/$RELEASE_NAME"
rollback_archive="$deploy_state_dir/rollback-$RELEASE_NAME.tar.gz"
venv_dir="$app_dir/.venv"
env_file="$app_dir/.env"
legacy_database_path="$app_dir/backend/zppz_v2.db"

if [[ "$app_dir" != /* || "$app_dir" == "/" ]]; then
  echo "DEPLOY_PATH must be an absolute path other than /." >&2
  exit 1
fi

rollback_enabled=0
rollback_in_progress=0

restore_live_release() {
  local path

  for path in "$app_dir"/* "$app_dir"/.[!.]* "$app_dir"/..?*; do
    [ -e "$path" ] || [ -L "$path" ] || continue
    case "$path" in
      "$deploy_state_dir"|"$venv_dir"|"$app_dir/venv"|"$app_dir/uploads"|"$app_dir/logs"|"$app_dir/data"|"$env_file"|"$legacy_database_path")
        continue
        ;;
    esac
    rm -rf -- "$path"
  done

  tar -xzf "$rollback_archive" -C "$app_dir"
}

rollback_on_exit() {
  local status=$?
  trap - EXIT

  if [ "$rollback_enabled" -eq 1 ] && [ "$rollback_in_progress" -eq 0 ]; then
    rollback_in_progress=1
    echo "Deployment failed; restoring the previous application files." >&2
    set +e
    if [ -f "$rollback_archive" ]; then
      restore_live_release
      sudo -n systemctl restart "$SERVICE_NAME"
      if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "The previous release could not be restarted automatically." >&2
        systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
        journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
      fi
    else
      echo "No previous application snapshot was available for rollback." >&2
    fi
    rm -f -- "$rollback_archive"
  fi

  exit "$status"
}

trap rollback_on_exit EXIT

if [ ! -f "$archive_path" ]; then
  echo "Release archive not found: $archive_path" >&2
  exit 1
fi

mkdir -p "$incoming_dir" "$releases_dir" "$pip_cache_dir" "$app_dir/logs" "$app_dir/data"

if [ ! -f "$env_file" ]; then
  umask 077
  cat > "$env_file" <<EOF
# Loaded by systemd. Fill production values on the server.
SECRET_KEY=
PORT=$APP_PORT
DATABASE_URL=sqlite:///$app_dir/data/zppz_v2.db
DATA_DIR=$app_dir/data
ADMIN_SEED_CODE=admin
ADMIN_SEED_PASSWORD=change-me-please
MAX_UPLOAD_MB=100
ALLOWED_EXTENSIONS=zip,7z,rar
WEB_CONCURRENCY=$WEB_CONCURRENCY
DB_POOL_SIZE=5
DB_MAX_OVERFLOW=5
DB_POOL_TIMEOUT=30
DB_POOL_RECYCLE=1800
SLOW_REQUEST_MS=500
EOF
fi

# The production .env is persistent and may have been edited or uploaded from
# Windows. Bash treats the trailing carriage return in CRLF files as part of
# the command/value when sourcing the file, which can fail with exit code 127
# or silently contaminate environment variables. Normalize line endings before
# this script reads the file and before systemd consumes it.
if LC_ALL=C grep -q $'\r' "$env_file"; then
  echo "Normalizing CRLF line endings in $env_file"
  sed -i 's/\r$//' "$env_file"
fi

if LC_ALL=C grep -q $'\r' "$env_file"; then
  echo "Environment file contains unsupported carriage-return characters: $env_file" >&2
  exit 1
fi

# Older Docker-oriented configurations used /data, which is not writable for
# the unprivileged user used by native systemd deployments. Keep the persistent
# environment file aligned with this script's runtime data directory. Only the
# exact legacy paths are migrated; PostgreSQL and custom database URLs are left
# untouched.
configured_data_dir="$(sed -n 's/^DATA_DIR=//p' "$env_file" | tail -n 1 | tr -d '"' | tr -d "'")"
if [ "$configured_data_dir" = "/data" ]; then
  echo "Migrating DATA_DIR from /data to $app_dir/data"
  sed -i "s|^DATA_DIR=.*$|DATA_DIR=$app_dir/data|" "$env_file"
fi

configured_database_url="$(sed -n 's/^DATABASE_URL=//p' "$env_file" | tail -n 1 | tr -d '"' | tr -d "'")"
if [[ "$configured_database_url" == sqlite:////data/* ]]; then
  sqlite_file="${configured_database_url#sqlite:////data/}"
  migrated_database_url="sqlite:///$app_dir/data/$sqlite_file"
  echo "Migrating SQLite database path from /data to $app_dir/data"
  sed -i "s|^DATABASE_URL=.*$|DATABASE_URL=$migrated_database_url|" "$env_file"
fi

# A previous manual CLI invocation without the production environment could
# create this relative SQLite file under backend/. It is not the persistent
# database used by the service, but a root-owned copy can otherwise prevent
# the release snapshot and writable-path check from completing. Keep it in
# place for safety and exclude only this exact legacy path when the configured
# database is the native deployment database.
skip_legacy_database=0
configured_database_url="$(sed -n 's/^DATABASE_URL=//p' "$env_file" | tail -n 1 | tr -d '"' | tr -d "'")"
expected_database_url="sqlite:///$app_dir/data/zppz_v2.db"
if [ "$configured_database_url" = "$expected_database_url" ] && [ -f "$legacy_database_path" ] && [ ! -L "$legacy_database_path" ]; then
  skip_legacy_database=1
  echo "Ignoring legacy database outside DATA_DIR: $legacy_database_path"
fi

configured_workers="$(sed -n 's/^WEB_CONCURRENCY=//p' "$env_file" | tail -n 1 | tr -d '"' | tr -d "'")"
if [[ "$configured_workers" =~ ^[1-9][0-9]*$ ]]; then
  WEB_CONCURRENCY="$configured_workers"
fi

rm -rf "$release_dir"
mkdir -p "$release_dir"
tar -xzf "$archive_path" -C "$release_dir"

echo "Deploying release: $RELEASE_NAME"
if [ -f "$release_dir/REVISION" ]; then
  echo "Deploying commit: $(cat "$release_dir/REVISION")"
fi

if [ ! -f "$release_dir/backend/app/main.py" ] || [ ! -f "$release_dir/backend/requirements.txt" ]; then
  echo "Invalid V2 release: backend/app/main.py or backend/requirements.txt is missing." >&2
  exit 1
fi
echo "Detected app kind: fastapi-v2"

if [ ! -w "$app_dir" ]; then
  echo "Deploy user '$RUN_USER' cannot write to $app_dir." >&2
  echo "The deployment target has incorrect ownership or permissions; update the server's deployment prerequisites." >&2
  exit 1
fi

find_prune_path_args=(
  -path "$deploy_state_dir" -o -path "$deploy_state_dir/*"
  -o -path "$venv_dir" -o -path "$venv_dir/*"
  -o -path "$app_dir/venv" -o -path "$app_dir/venv/*"
  -o -path "$app_dir/uploads" -o -path "$app_dir/uploads/*"
  -o -path "$app_dir/logs" -o -path "$app_dir/logs/*"
  -o -path "$app_dir/data" -o -path "$app_dir/data/*"
)

find_skip_args=( "(" "${find_prune_path_args[@]}" ")" -prune )
if [ "$skip_legacy_database" -eq 1 ]; then
  find_skip_args+=( -o -path "$legacy_database_path" -prune )
fi

unwritable_path="$(
  find "$app_dir" "${find_skip_args[@]}" \
    -o ! -writable -print -quit
)"

if [ -n "$unwritable_path" ]; then
  echo "Deploy user '$RUN_USER' cannot overwrite existing path: $unwritable_path" >&2
  echo "The deployment target has incorrect ownership or permissions; update the server's deployment prerequisites." >&2
  exit 1
fi

# Keep a code-only snapshot so a failed dependency install, preparation step,
# service restart, or health check does not leave the host on a half-written
# release. Persistent data, uploads, logs, the virtualenv, and .env remain in
# place and are deliberately excluded from this snapshot.
rollback_snapshot_excludes=()
if [ "$skip_legacy_database" -eq 1 ]; then
  rollback_snapshot_excludes+=(--exclude='./backend/zppz_v2.db')
fi
tar -C "$app_dir" \
  --exclude='./.deploy' \
  --exclude='./.venv' \
  --exclude='./venv' \
  --exclude='./uploads' \
  --exclude='./logs' \
  --exclude='./data' \
  --exclude='./.env' \
  --exclude='./node_modules' \
  --exclude='./frontend/node_modules' \
  --exclude='./*.db' \
  --exclude='./*.sqlite' \
  --exclude='./*.sqlite3' \
  "${rollback_snapshot_excludes[@]}" \
  -czf "$rollback_archive" .
rollback_enabled=1

# Copy the built release into the live application directory. Runtime data lives
# outside the archive and is preserved in place.
tar -C "$release_dir" -cf - . | tar --no-same-owner --no-same-permissions --delay-directory-restore --touch -C "$app_dir" -xf -

"$PYTHON_BIN" -m venv "$venv_dir"
PIP_CACHE_DIR="$pip_cache_dir" "$venv_dir/bin/python" -m pip install --disable-pip-version-check --upgrade pip

mkdir -p "$app_dir/data/uploads" "$app_dir/data/assets"
PIP_CACHE_DIR="$pip_cache_dir" "$venv_dir/bin/pip" install --disable-pip-version-check -r "$app_dir/backend/requirements.txt"
"$venv_dir/bin/python" -m uvicorn --version
service_workdir="$app_dir/backend"
service_exec="$venv_dir/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT --workers $WEB_CONCURRENCY"

# Run write-producing database preparation exactly once per deployment, before
# the service master and its workers are started.
(
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  # Match the explicit DATA_DIR override in the generated systemd service.
  export DATA_DIR="$app_dir/data"
  cd "$service_workdir"
  "$venv_dir/bin/python" -m app.prepare
)

service_file="/etc/systemd/system/$SERVICE_NAME.service"
sudo -n tee "$service_file" >/dev/null <<EOF
[Unit]
Description=ZPPZ Web
After=network.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$service_workdir
EnvironmentFile=-$env_file
Environment=PORT=$APP_PORT
Environment=DATA_DIR=$app_dir/data
ExecStart=$service_exec
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo -n systemctl daemon-reload
sudo -n systemctl enable "$SERVICE_NAME"

pkill -TERM -u "$RUN_USER" -f "uvicorn app.main:app" || true
sleep 2
pkill -KILL -u "$RUN_USER" -f "uvicorn app.main:app" || true

"$venv_dir/bin/python" - <<PY || true
import os
import signal
import time

port_hex = format(int("$APP_PORT"), "04X")
targets = set()

for table in ("/proc/net/tcp", "/proc/net/tcp6"):
    try:
        lines = open(table, encoding="utf-8").read().splitlines()[1:]
    except OSError:
        continue
    for line in lines:
        parts = line.split()
        local_address = parts[1]
        state = parts[3]
        inode = parts[9]
        if state == "0A" and local_address.rsplit(":", 1)[-1].upper() == port_hex:
            targets.add(inode)

if targets:
    current_pid = os.getpid()
    killed = []
    for pid in filter(str.isdigit, os.listdir("/proc")):
        if int(pid) == current_pid:
            continue
        fd_dir = f"/proc/{pid}/fd"
        try:
            for fd in os.listdir(fd_dir):
                try:
                    link = os.readlink(os.path.join(fd_dir, fd))
                except OSError:
                    continue
                if link.startswith("socket:[") and link[8:-1] in targets:
                    os.kill(int(pid), signal.SIGTERM)
                    killed.append(pid)
                    break
        except (PermissionError, FileNotFoundError, ProcessLookupError):
            continue
    if killed:
        print(f"Terminated stale listener(s) on port $APP_PORT: {', '.join(killed)}")
        time.sleep(2)
    else:
        print("Port $APP_PORT is still occupied, but no killable process was visible to $RUN_USER.")
PY

sudo -n systemctl restart "$SERVICE_NAME"

sleep 3
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Service $SERVICE_NAME failed to stay active after restart." >&2
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
  exit 1
fi

if ! "$venv_dir/bin/python" - <<PY
import sys
import urllib.request

url = "http://127.0.0.1:$APP_PORT/health"
try:
    with urllib.request.urlopen(url, timeout=10) as response:
        if response.status >= 400:
            raise SystemExit(f"health check returned HTTP {response.status}")
except Exception as exc:
    raise SystemExit(f"health check failed for {url}: {exc}")
PY
then
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
  exit 1
fi

rollback_enabled=0
rm -f "$archive_path"
rm -f "$rollback_archive"

if [ "$KEEP_RELEASES" -gt 0 ]; then
  mapfile -t old_releases < <(find "$releases_dir" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | awk '{print $2}' | tail -n +"$((KEEP_RELEASES + 1))")
  for old_release in "${old_releases[@]}"; do
    rm -rf "$old_release"
  done
fi

sudo -n systemctl --no-pager --full status "$SERVICE_NAME"
