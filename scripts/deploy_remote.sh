#!/usr/bin/env bash
set -Eeuo pipefail

: "${DEPLOY_PATH:?DEPLOY_PATH is required}"
: "${RELEASE_NAME:?RELEASE_NAME is required}"

SERVICE_NAME="${SERVICE_NAME:-zppz-web}"
APP_PORT="${APP_PORT:-8000}"
PYTHON_BIN="${PYTHON_BIN:-python3}"
KEEP_RELEASES="${KEEP_RELEASES:-5}"
RUN_USER="${RUN_USER:-$(id -un)}"
RUN_GROUP="${RUN_GROUP:-$(id -gn)}"

app_dir="$DEPLOY_PATH"
deploy_state_dir="$app_dir/.deploy"
incoming_dir="$deploy_state_dir/incoming"
releases_dir="$deploy_state_dir/releases"
pip_cache_dir="$deploy_state_dir/pip-cache"
archive_path="$incoming_dir/$RELEASE_NAME.tar.gz"
release_dir="$releases_dir/$RELEASE_NAME"
venv_dir="$app_dir/.venv"
env_file="$app_dir/.env"

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
EOF
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
  echo "Run this once on the server: sudo chown -R $RUN_USER:$RUN_GROUP $app_dir" >&2
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

unwritable_path="$(
  find "$app_dir" \
    \( "${find_prune_path_args[@]}" \) -prune \
    -o ! -writable -print -quit
)"

if [ -n "$unwritable_path" ]; then
  echo "Deploy user '$RUN_USER' cannot overwrite existing path: $unwritable_path" >&2
  echo "Run this once on the server: sudo chown -R $RUN_USER:$RUN_GROUP $app_dir" >&2
  exit 1
fi

# Copy the built release into the live application directory. Runtime data lives
# outside the archive and is preserved in place.
tar -C "$release_dir" -cf - . | tar --no-same-owner --no-same-permissions --delay-directory-restore --touch -C "$app_dir" -xf -

"$PYTHON_BIN" -m venv "$venv_dir"
PIP_CACHE_DIR="$pip_cache_dir" "$venv_dir/bin/python" -m pip install --disable-pip-version-check --upgrade pip

mkdir -p "$app_dir/data/uploads" "$app_dir/data/assets"
PIP_CACHE_DIR="$pip_cache_dir" "$venv_dir/bin/pip" install --disable-pip-version-check -r "$app_dir/backend/requirements.txt"
"$venv_dir/bin/python" -m uvicorn --version
service_workdir="$app_dir/backend"
service_exec="$venv_dir/bin/python -m uvicorn app.main:app --host 127.0.0.1 --port $APP_PORT"

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

rm -f "$archive_path"

if [ "$KEEP_RELEASES" -gt 0 ]; then
  mapfile -t old_releases < <(find "$releases_dir" -mindepth 1 -maxdepth 1 -type d -printf '%T@ %p\n' | sort -rn | awk '{print $2}' | tail -n +"$((KEEP_RELEASES + 1))")
  for old_release in "${old_releases[@]}"; do
    rm -rf "$old_release"
  done
fi

sudo -n systemctl --no-pager --full status "$SERVICE_NAME"
