#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${RELEASE_NAME:?RELEASE_NAME is required}"

SERVICE_NAME="${SERVICE_NAME:-zppz-web}"
WORKER_SERVICE_NAME="${WORKER_SERVICE_NAME:-${SERVICE_NAME}-worker}"
APP_PORT="${APP_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
WEB_CONCURRENCY="${WEB_CONCURRENCY:-1}"
SERVER_PIP_INDEX_URL="${SERVER_PIP_INDEX_URL:-https://pypi.tuna.tsinghua.edu.cn/simple}"
STORAGE_CONFIG_PATH="${STORAGE_CONFIG_PATH:-}"
OWNER_USER_CODE_B64="${OWNER_USER_CODE_B64:-}"
RUN_USER="${RUN_USER:-$(id -un)}"
RUN_GROUP="${RUN_GROUP:-$(id -gn)}"

owner_user_code=""
if [ -n "$OWNER_USER_CODE_B64" ]; then
  if ! owner_user_code="$(printf '%s' "$OWNER_USER_CODE_B64" | base64 --decode)"; then
    echo "OWNER_USER_CODE_B64 is not valid base64." >&2
    exit 1
  fi
  if [ -z "$owner_user_code" ]; then
    echo "OWNER_USER_CODE decoded to an empty account code." >&2
    exit 1
  fi
fi

app_dir="$DEPLOY_PATH"
deploy_state_dir="$app_dir/.deploy"
incoming_dir="$deploy_state_dir/incoming"
releases_dir="$deploy_state_dir/releases"
pip_cache_dir="$deploy_state_dir/pip-cache"
archive_path="$incoming_dir/$RELEASE_NAME.tar.gz"
release_dir="$releases_dir/$RELEASE_NAME"
rollback_archive="$deploy_state_dir/rollback-$RELEASE_NAME.tar.gz"
rollback_env="$deploy_state_dir/rollback-$RELEASE_NAME.env"
rollback_service_unit="$deploy_state_dir/rollback-$RELEASE_NAME.service"
venv_dir="$app_dir/.venv"
env_file="$app_dir/.env"
legacy_database_path="$app_dir/backend/zppz_v2.db"
service_file="/etc/systemd/system/$SERVICE_NAME.service"
worker_service_file="/etc/systemd/system/$WORKER_SERVICE_NAME.service"
worker_unit_preexisting=0
worker_unit_created=0
worker_service_mode="combined"
if systemctl cat "$WORKER_SERVICE_NAME" >/dev/null 2>&1; then
  worker_unit_preexisting=1
  worker_service_mode="separate"
fi

if [[ "$app_dir" != /* || "$app_dir" == "/" ]]; then
  echo "DEPLOY_PATH must be an absolute path other than /." >&2
  exit 1
fi

rollback_enabled=0
rollback_in_progress=0

install_unit_file() {
  local source_path="$1"
  local target_path="$2"

  # The deploy user intentionally reads its own temporary unit file; only tee
  # needs elevated privileges to write under /etc/systemd/system.
  # shellcheck disable=SC2024
  sudo -n tee "$target_path" < "$source_path" >/dev/null
}

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

  if [ -n "$STORAGE_CONFIG_PATH" ]; then
    rm -f -- "$STORAGE_CONFIG_PATH"
  fi

  if [ "$rollback_enabled" -eq 1 ] && [ "$rollback_in_progress" -eq 0 ]; then
    rollback_in_progress=1
    echo "Deployment failed; restoring the previous application files." >&2
    set +e
    if [ -f "$rollback_archive" ]; then
      restore_live_release
      if [ -f "$rollback_env" ]; then
        cp "$rollback_env" "$env_file"
        chmod 600 "$env_file"
      fi
      if [ -f "$rollback_service_unit" ]; then
        install_unit_file "$rollback_service_unit" "$service_file"
        sudo -n systemctl daemon-reload
      fi
      sudo -n systemctl restart "$SERVICE_NAME"
      if [ "$worker_unit_preexisting" -eq 1 ]; then
        sudo -n systemctl restart "$WORKER_SERVICE_NAME"
      elif [ "$worker_unit_created" -eq 1 ]; then
        sudo -n systemctl disable --now "$WORKER_SERVICE_NAME" >/dev/null 2>&1 || true
      fi
      if ! systemctl is-active --quiet "$SERVICE_NAME"; then
        echo "The previous release could not be restarted automatically." >&2
        systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
        journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
      fi
      if [ "$worker_unit_preexisting" -eq 1 ] && ! systemctl is-active --quiet "$WORKER_SERVICE_NAME"; then
        echo "The previous worker could not be restarted automatically." >&2
        systemctl --no-pager --full status "$WORKER_SERVICE_NAME" >&2 || true
        journalctl -u "$WORKER_SERVICE_NAME" --no-pager -n 160 >&2 || true
      fi
    else
      echo "No previous application snapshot was available for rollback." >&2
    fi
    rm -f -- "$rollback_archive"
  fi
  if [ -f "$rollback_env" ]; then
    cp "$rollback_env" "$env_file"
    chmod 600 "$env_file"
  fi
  rm -f -- "$rollback_env"
  rm -f -- "$rollback_service_unit"

  exit "$status"
}

trap rollback_on_exit EXIT

if [ ! -f "$archive_path" ]; then
  echo "Release archive not found: $archive_path" >&2
  exit 1
fi

mkdir -p "$incoming_dir" "$releases_dir" "$pip_cache_dir" "$app_dir/logs" "$app_dir/data"
if [ -f "$service_file" ]; then
  cp "$service_file" "$rollback_service_unit"
fi

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
cp "$env_file" "$rollback_env"
chmod 600 "$rollback_env"

if [ -z "$STORAGE_CONFIG_PATH" ] || [ ! -f "$STORAGE_CONFIG_PATH" ]; then
  echo "Production object-storage configuration was not uploaded." >&2
  exit 1
fi

case "$SERVER_PIP_INDEX_URL" in
  https://*) ;;
  *)
    echo "SERVER_PIP_INDEX_URL must be an HTTPS URL." >&2
    exit 1
    ;;
esac

merge_env_file="$(mktemp "$deploy_state_dir/.env.merge.XXXXXX")"
chmod 600 "$merge_env_file"
cp "$env_file" "$merge_env_file"
storage_config_error=""
while IFS='=' read -r name value; do
  [ -n "$name" ] || continue
  case "$name" in
    OBJECT_STORAGE_BACKEND|R2_ACCOUNT_ID|R2_BUCKET_NAME|R2_ACCESS_KEY_ID|R2_SECRET_ACCESS_KEY|R2_UPLOAD_URL_TTL_SECONDS|R2_DOWNLOAD_URL_TTL_SECONDS|UPLOAD_INTENT_TTL_SECONDS|PREVIEW_ENABLED|PREVIEW_PLAYER_URL|PREVIEW_PLAYER_ORIGIN|PREVIEW_URL_TTL_SECONDS|PREVIEW_BACKFILL_POLL_SECONDS|WEBHOOK_SIGNING_MASTER_KEY|PUBLIC_BASE_URL|WEBHOOK_SCAN_INTERVAL_SECONDS|WEBHOOK_ASSET_URL_TTL_SECONDS|WEBHOOK_ASSET_RETENTION_DAYS)
      next_env="$(mktemp "$deploy_state_dir/.env.next.XXXXXX")"
      grep -v "^${name}=" "$merge_env_file" > "$next_env" || true
      printf '%s=%s\n' "$name" "$value" >> "$next_env"
      chmod 600 "$next_env"
      mv "$next_env" "$merge_env_file"
      ;;
    *)
      storage_config_error="Unexpected key in storage configuration: $name"
      break
      ;;
  esac
done < "$STORAGE_CONFIG_PATH"
if [ -n "$storage_config_error" ]; then
  echo "$storage_config_error" >&2
  rm -f -- "$merge_env_file" "$STORAGE_CONFIG_PATH"
  exit 1
fi
mv "$merge_env_file" "$env_file"
chmod 600 "$env_file"
rm -f -- "$STORAGE_CONFIG_PATH"

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
# create this relative SQLite file under backend/. Its ownership and the exact
# DATABASE_URL spelling vary between older installations. Treat only this
# exact, regular, non-symlink file as persistent runtime data regardless of the
# current URL: preserve it in place and never require the deploy user to modify
# it. A release containing the same path is rejected below before extraction.
skip_legacy_database=0
if [ -f "$legacy_database_path" ] && [ ! -L "$legacy_database_path" ]; then
  skip_legacy_database=1
  echo "Preserving database file outside the release: $legacy_database_path"
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
if [ -e "$release_dir/backend/zppz_v2.db" ] || [ -L "$release_dir/backend/zppz_v2.db" ]; then
  echo "Invalid V2 release: backend/zppz_v2.db must not be included in a release archive." >&2
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

# Stop the old worker before replacing code or migrating the shared database.
# The web service remains online until the new release is ready to activate.
if [ "$worker_unit_preexisting" -eq 1 ]; then
  sudo -n systemctl stop "$WORKER_SERVICE_NAME" >/dev/null 2>&1 || true
fi

# Copy the built release into the live application directory. Runtime data lives
# outside the archive and is preserved in place.
tar -C "$release_dir" -cf - . | tar --no-same-owner --no-same-permissions --delay-directory-restore --touch -C "$app_dir" -xf -

"$PYTHON_BIN" -m venv "$venv_dir"

pip_with_index() {
  local index_url="$1"
  shift
  PIP_CACHE_DIR="$pip_cache_dir" "$venv_dir/bin/python" -m pip install \
    --disable-pip-version-check --index-url "$index_url" "$@"
}

if ! pip_with_index "$SERVER_PIP_INDEX_URL" --upgrade pip; then
  echo "Configured PyPI mirror failed while upgrading pip; retrying official PyPI." >&2
  pip_with_index "https://pypi.org/simple" --upgrade pip
fi

mkdir -p "$app_dir/data/uploads" "$app_dir/data/assets"
if ! pip_with_index "$SERVER_PIP_INDEX_URL" -r "$app_dir/backend/requirements.txt"; then
  echo "Configured PyPI mirror failed while installing requirements; retrying official PyPI." >&2
  pip_with_index "https://pypi.org/simple" -r "$app_dir/backend/requirements.txt"
fi
"$venv_dir/bin/python" -m uvicorn --version
service_workdir="$app_dir/backend"
service_exec="$venv_dir/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT --workers $WEB_CONCURRENCY"
worker_exec="$venv_dir/bin/python -m app.worker_supervisor"

# Run write-producing database preparation exactly once per deployment, before
# the service master and its workers are started.
# The previous web release may still own legacy in-process upload tasks, so it
# must be stopped before 0016 requeues them into the durable worker table.
sudo -n systemctl stop "$SERVICE_NAME" >/dev/null 2>&1 || true
(
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  # Match the explicit DATA_DIR override in the generated systemd service.
  export DATA_DIR="$app_dir/data"
  cd "$service_workdir"
  "$venv_dir/bin/python" -m app.prepare
  "$venv_dir/bin/python" -m app.manage worker-recover
  "$venv_dir/bin/python" -m app.manage storage-check
  "$venv_dir/bin/python" -m app.manage preview-check
  "$venv_dir/bin/python" -m app.manage worker-check
  if [ -n "$owner_user_code" ]; then
    "$venv_dir/bin/python" -m app.manage set-owner --user-code "$owner_user_code"
  else
    echo "OWNER_USER_CODE is empty; keeping the current owner unchanged."
  fi
)

worker_unit_candidate="$(mktemp "$deploy_state_dir/.worker-unit.XXXXXX")"
cat > "$worker_unit_candidate" <<EOF
[Unit]
Description=ZPPZ Submission and Webhook Workers
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
User=$RUN_USER
Group=$RUN_GROUP
WorkingDirectory=$service_workdir
EnvironmentFile=-$env_file
Environment=DATA_DIR=$app_dir/data
ExecStart=$worker_exec
Nice=10
IOSchedulingClass=best-effort
IOSchedulingPriority=7
Restart=always
RestartSec=5
TimeoutStopSec=30

[Install]
WantedBy=multi-user.target
EOF

if [ "$worker_unit_preexisting" -eq 1 ]; then
  if ! install_unit_file "$worker_unit_candidate" "$worker_service_file" 2>/dev/null; then
    echo "::warning::The existing Worker unit could not be updated; keeping its current definition." >&2
  fi
elif install_unit_file "$worker_unit_candidate" "$worker_service_file" 2>/dev/null; then
  worker_unit_created=1
  worker_service_mode="separate"
else
  echo "::warning::No passwordless permission to create $worker_service_file; running the single Worker inside the Web service cgroup." >&2
fi
rm -f -- "$worker_unit_candidate"

if [ "$worker_service_mode" = "combined" ]; then
  service_exec="/bin/bash $app_dir/scripts/run_web_with_worker.sh"
fi

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
Environment=ZPPZ_PYTHON_BIN=$venv_dir/bin/python
Environment=ZPPZ_APP_PORT=$APP_PORT
Environment=ZPPZ_WEB_CONCURRENCY=$WEB_CONCURRENCY
ExecStart=$service_exec
KillMode=control-group
TimeoutStopSec=30
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
EOF

sudo -n systemctl daemon-reload
sudo -n systemctl enable "$SERVICE_NAME"
if [ "$worker_service_mode" = "separate" ]; then
  sudo -n systemctl enable "$WORKER_SERVICE_NAME"
fi

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

if [ "$worker_service_mode" = "separate" ]; then
  sudo -n systemctl restart "$WORKER_SERVICE_NAME"
fi
sudo -n systemctl restart "$SERVICE_NAME"

sleep 3
if [ "$worker_service_mode" = "separate" ]; then
  if ! systemctl is-active --quiet "$WORKER_SERVICE_NAME"; then
    echo "Service $WORKER_SERVICE_NAME failed to stay active after restart." >&2
    systemctl --no-pager --full status "$WORKER_SERVICE_NAME" >&2 || true
    journalctl -u "$WORKER_SERVICE_NAME" --no-pager -n 160 >&2 || true
    exit 1
  fi
elif ! pgrep -u "$RUN_USER" -f "$venv_dir/bin/python -m app.worker" >/dev/null; then
  echo "The submission Worker did not stay active inside $SERVICE_NAME." >&2
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
  exit 1
fi
if ! pgrep -u "$RUN_USER" -f "$venv_dir/bin/python -m app.webhook_worker" >/dev/null; then
  echo "The Webhook Worker did not stay active." >&2
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  if [ "$worker_service_mode" = "separate" ]; then
    systemctl --no-pager --full status "$WORKER_SERVICE_NAME" >&2 || true
  fi
  exit 1
fi
if ! systemctl is-active --quiet "$SERVICE_NAME"; then
  echo "Service $SERVICE_NAME failed to stay active after restart." >&2
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
  exit 1
fi

if ! "$venv_dir/bin/python" - <<PY
import time
import urllib.request

url = "http://127.0.0.1:$APP_PORT/health"
deadline = time.monotonic() + 60
last_error = None
attempt = 0
while time.monotonic() < deadline:
    attempt += 1
    try:
        with urllib.request.urlopen(url, timeout=5) as response:
            if response.status >= 400:
                raise RuntimeError(f"health check returned HTTP {response.status}")
        print(f"health check passed for {url} after {attempt} attempt(s)")
        break
    except Exception as exc:
        last_error = exc
        remaining = deadline - time.monotonic()
        if remaining > 0:
            time.sleep(min(2, remaining))
else:
    raise SystemExit(f"health check failed for {url} after {attempt} attempt(s): {last_error}")
PY
then
  systemctl --no-pager --full status "$SERVICE_NAME" >&2 || true
  journalctl -u "$SERVICE_NAME" --no-pager -n 160 >&2 || true
  exit 1
fi

if ! (
  set -a
  # shellcheck disable=SC1090
  source "$env_file"
  set +a
  "$venv_dir/bin/python" - <<PY
import os
import time
import urllib.request

if os.environ.get("PREVIEW_ENABLED", "").lower() in {"1", "true", "yes", "on"}:
    url = os.environ.get("PREVIEW_PLAYER_URL", "")
    if not url:
        raise SystemExit("PREVIEW_PLAYER_URL is empty")
    errors = []
    for attempt in range(1, 4):
        request = urllib.request.Request(
            url,
            headers={
                "Accept": "text/html",
                "Range": "bytes=0-1023",
                "User-Agent": "Mozilla/5.0 (compatible; zppz-deploy-health/1.0)",
            },
        )
        try:
            with urllib.request.urlopen(request, timeout=15) as response:
                if response.status >= 400:
                    raise RuntimeError(f"preview player returned HTTP {response.status}")
                if "text/html" not in response.headers.get("Content-Type", ""):
                    raise RuntimeError("preview player did not return text/html")
                response.read(1024)
            print(f"preview player is reachable from the application host: {url}")
            break
        except Exception as exc:
            errors.append(f"attempt {attempt}: {exc}")
            if attempt < 3:
                time.sleep(attempt * 2)
    else:
        raise SystemExit(
            f"preview player could not be reached from the application host: {url}; "
            + "; ".join(errors)
        )
PY
)
then
  # The immutable player URL, MIME types, and CSP were already checked from the
  # public Internet by publish_preview_player.py. The application server never
  # proxies or fetches player assets at runtime, so a host-specific egress or
  # Cloudflare bot-filter failure must not roll back an otherwise healthy app.
  echo "::warning::Application host could not reach the preview player after retries; public CDN verification already passed, continuing activation." >&2
fi

rollback_enabled=0
rm -f "$archive_path"
rm -f "$rollback_archive"
rm -f "$rollback_env"
rm -f "$rollback_service_unit"

if [ "$KEEP_RELEASES" -gt 0 ]; then
  mapfile -t old_releases < <(find "$releases_dir" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | awk '{print $2}' | tail -n +"$((KEEP_RELEASES + 1))")
  for old_release in "${old_releases[@]}"; do
    rm -rf "$old_release"
  done
fi

sudo -n systemctl --no-pager --full status "$SERVICE_NAME"
if [ "$worker_service_mode" = "separate" ]; then
  sudo -n systemctl --no-pager --full status "$WORKER_SERVICE_NAME"
else
  echo "Submission and Webhook Workers are active inside the $SERVICE_NAME cgroup."
fi
