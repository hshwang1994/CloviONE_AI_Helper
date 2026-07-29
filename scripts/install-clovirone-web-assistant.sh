#!/usr/bin/env bash
# ClovirONE Web Assistant installer (spec §30). Idempotent, re-runnable.
# Run as root. Source must be staged at STAGE (default /home/cloviradmin/deploy/stage).
# Does NOT create the admin account (that is a separate sensitive step —
# scripts/seed_admin.py — so the temp password never lands in this log).
# Does NOT change the firewall (spec §30).
set -euo pipefail
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive

case "$(head -c 200 "$0" 2>/dev/null)" in *$'\r'*) echo "CRLF in script"; exit 64;; esac
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

STAGE="${STAGE:-/home/cloviradmin/deploy/stage}"
APP_DIR=/opt/clovirone-web-assistant
ETC_DIR=/etc/clovirone-web-assistant
VAR_DIR=/var/lib/clovirone-web-assistant
SVC_USER=clovirone-web
DNS_NAME=clovirone-ai.gooddi.lab
BIND_IP=10.100.64.71
LOG_DIR=/home/cloviradmin/deploy/logs
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/install.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
trap 'echo "RESULT name=install rc=$?"' EXIT

log "=== install start (stage=$STAGE) ==="

# 1. Packages ---------------------------------------------------------------
NEED_PKGS=()
for pkg in python3.12-venv nginx openssl sqlite3 zip rsync; do
  dpkg -s "$pkg" >/dev/null 2>&1 || NEED_PKGS+=("$pkg")
done
if [ "${#NEED_PKGS[@]}" -gt 0 ]; then
  log "apt install: ${NEED_PKGS[*]}"
  apt-get update -qq >>"$LOG" 2>&1 || true
  apt-get install -y --no-install-recommends "${NEED_PKGS[@]}" >>"$LOG" 2>&1
else
  log "all OS packages present"
fi

# 2. System user ------------------------------------------------------------
if ! id "$SVC_USER" >/dev/null 2>&1; then
  log "create system user $SVC_USER"
  useradd --system --shell /usr/sbin/nologin --no-create-home "$SVC_USER"
fi

# 3. Directories + permissions (spec §9) -----------------------------------
install -d -o root -g root -m 0755 "$APP_DIR"
install -d -o root -g "$SVC_USER" -m 0750 "$ETC_DIR"
install -d -o root -g root -m 0755 "$ETC_DIR/tls"
install -d -o root -g "$SVC_USER" -m 0750 "$ETC_DIR/secrets"
install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR" \
  "$VAR_DIR/exports" "$VAR_DIR/generated" "$VAR_DIR/temp" "$VAR_DIR/locks"
install -d -o root -g root -m 0700 /var/backups/clovirone-web-assistant

# 4. Deploy source ----------------------------------------------------------
log "deploy source -> $APP_DIR"
# --delete keeps the tree clean, but MUST preserve the runtime venv (it lives
# inside $APP_DIR and is not in the source) and any local var/.
rsync -a --delete \
  --exclude '.git' --exclude 'var' --exclude 'tests' --exclude '.venv' \
  --exclude 'venv' --exclude 'dist' \
  --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
  "$STAGE/app-src/" "$APP_DIR/"
# Normalize ownership/permissions on the SOURCE tree only — never touch the
# runtime venv (its console scripts must stay executable; a blanket chmod 0644
# would break `pip`/`uvicorn`/`alembic` on an upgrade re-run where venv exists).
find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -exec chown root:root {} +
find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -type d -exec chmod 0755 {} +
find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -type f -exec chmod 0644 {} +
find "$APP_DIR/scripts" -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true

# 5. venv + dependencies ----------------------------------------------------
if [ ! -x "$APP_DIR/venv/bin/python" ]; then
  log "create venv"
  python3 -m venv "$APP_DIR/venv"
fi
if [ -d "$STAGE/wheels" ] && [ -n "$(ls -A "$STAGE/wheels" 2>/dev/null)" ]; then
  log "pip install (offline wheelhouse)"
  "$APP_DIR/venv/bin/pip" install --no-index --find-links "$STAGE/wheels" --upgrade pip >>"$LOG" 2>&1 || true
  "$APP_DIR/venv/bin/pip" install --no-index --find-links "$STAGE/wheels" -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1
else
  log "pip install (online)"
  "$APP_DIR/venv/bin/pip" install --upgrade pip >>"$LOG" 2>&1 || true
  "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1
fi
log "import smoke test"
"$APP_DIR/venv/bin/python" -c "import fastapi, sqlalchemy, alembic, httpx, argon2, pydantic_settings, cronsim; print('imports ok')" >>"$LOG" 2>&1

# 6. Config: web.env + allowlists ------------------------------------------
if [ ! -f "$ETC_DIR/web.env" ]; then
  log "generate web.env (SESSION_SECRET server-side)"
  SECRET="$(openssl rand -base64 48)"
  umask 077
  sed "s#__GENERATED_ON_SERVER__#${SECRET}#" "$APP_DIR/deploy/web.env.example" > "$ETC_DIR/web.env"
  unset SECRET
else
  log "web.env exists — preserving SESSION_SECRET"
fi
chown root:"$SVC_USER" "$ETC_DIR/web.env"; chmod 0640 "$ETC_DIR/web.env"
# Seed allowlist/feature-flag configs only on first install — never overwrite
# an operator's live edits on re-run/upgrade.
for f in allowed-services.json allowed-runners.json allowed-workflows.json feature-flags.json; do
  if [ ! -f "$ETC_DIR/$f" ]; then
    cp "$APP_DIR/config/$f" "$ETC_DIR/$f"
    log "seeded $f"
  else
    log "$f exists — preserving operator edits"
  fi
  chown root:"$SVC_USER" "$ETC_DIR/$f"; chmod 0640 "$ETC_DIR/$f"
done

# 7. DB migration -----------------------------------------------------------
# Run from $APP_DIR so alembic's relative script_location resolves and
# `python -m app...` finds the app package. runuser (no -l) preserves CWD.
cd "$APP_DIR"
log "alembic upgrade head"
runuser -u "$SVC_USER" -- env $(grep -v '^#' "$ETC_DIR/web.env" | xargs) \
  "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head >>"$LOG" 2>&1
DB="$VAR_DIR/web.sqlite3"
if [ -f "$DB" ]; then
  chown "$SVC_USER":"$SVC_USER" "$DB"; chmod 0660 "$DB"
  MODE="$(runuser -u "$SVC_USER" -- sqlite3 "$DB" 'PRAGMA journal_mode;')"
  log "sqlite journal_mode=$MODE"
fi

# 8. Discovery import (integrations + workflows) ---------------------------
log "discovery import"
runuser -u "$SVC_USER" -- env $(grep -v '^#' "$ETC_DIR/web.env" | xargs) \
  "$APP_DIR/venv/bin/python" -m app.integrations.discovery >>"$LOG" 2>&1 || true

# 9. systemd units ----------------------------------------------------------
log "install systemd units"
cp -f "$APP_DIR/deploy/systemd/clovirone-web-assistant.service" /etc/systemd/system/
cp -f "$APP_DIR/deploy/systemd/clovirone-web-worker.service" /etc/systemd/system/
chmod 0644 /etc/systemd/system/clovirone-web-*.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/clovirone-web-assistant.service >>"$LOG" 2>&1 || true
systemctl enable clovirone-web-assistant.service clovirone-web-worker.service >>"$LOG" 2>&1

# 10. TLS: discover existing SAN cert or self-sign -------------------------
CRT="$ETC_DIR/tls/$DNS_NAME.crt"
KEY="$ETC_DIR/tls/$DNS_NAME.key"
if [ ! -f "$CRT" ] || [ ! -f "$KEY" ]; then
  log "generate self-signed ECDSA P-256 cert (365d)"
  openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
    -keyout "$KEY" -out "$CRT" -days 365 -nodes \
    -subj "/CN=$DNS_NAME" \
    -addext "subjectAltName=DNS:$DNS_NAME,IP:$BIND_IP" >>"$LOG" 2>&1
  chmod 0600 "$KEY"; chmod 0644 "$CRT"; chown root:root "$KEY" "$CRT"
  cp -f "$CRT" "/home/cloviradmin/$DNS_NAME.crt"
  chown cloviradmin:cloviradmin "/home/cloviradmin/$DNS_NAME.crt" 2>/dev/null || true
else
  log "TLS cert already present"
fi

# 11. nginx vhost + gate ----------------------------------------------------
log "install nginx vhost"
cp -f "$APP_DIR/deploy/nginx/clovirone-web-assistant.conf" /etc/nginx/sites-available/clovirone-web-assistant
ln -sf /etc/nginx/sites-available/clovirone-web-assistant /etc/nginx/sites-enabled/clovirone-web-assistant
if nginx -t >>"$LOG" 2>&1; then
  log "nginx -t OK; reload"
  systemctl reload nginx 2>>"$LOG" || systemctl restart nginx >>"$LOG" 2>&1
else
  log "nginx -t FAILED — removing our vhost and aborting"
  rm -f /etc/nginx/sites-enabled/clovirone-web-assistant
  nginx -t >>"$LOG" 2>&1 && log "baseline nginx config intact"
  exit 20
fi

# 12. Start services + health gate -----------------------------------------
log "start services"
systemctl restart clovirone-web-assistant.service
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8080/healthz >>"$LOG" 2>&1 || { log "web healthz FAILED"; journalctl -u clovirone-web-assistant -n 50 --no-pager >>"$LOG" 2>&1; exit 20; }
systemctl restart clovirone-web-worker.service
sleep 2
systemctl is-active clovirone-web-worker.service >>"$LOG" 2>&1 || { log "worker not active"; journalctl -u clovirone-web-worker -n 50 --no-pager >>"$LOG" 2>&1; exit 20; }

log "web healthz OK; worker active"
log "=== install complete ==="
echo "INSTALL_OK"
