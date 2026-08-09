#!/usr/bin/env bash
# Consistent backup of app config + DB + service state (spec §6.1). Run as root.
set -euo pipefail
export LC_ALL=C.UTF-8
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

BACKUP_ROOT=/var/backups/clovirone-web-assistant
BACKUP_DIR="$BACKUP_ROOT/$(date +%Y%m%d_%H%M%S)"
ETC_DIR=/etc/clovirone-web-assistant
VAR_DIR=/var/lib/clovirone-web-assistant
APP_DIR=/opt/clovirone-web-assistant
install -d -o root -g root -m 0700 "$BACKUP_DIR"

echo "backup dir: $BACKUP_DIR"

# Application + config (no secrets excluded here — this is a root-only local backup dir 0700)
[ -d "$APP_DIR" ] && tar czf "$BACKUP_DIR/app.tar.gz" -C /opt clovirone-web-assistant 2>/dev/null || true
[ -d "$ETC_DIR" ] && tar czf "$BACKUP_DIR/etc.tar.gz" -C /etc clovirone-web-assistant 2>/dev/null || true

# systemd units + nginx vhost
# DEPLOY-04: privhelper 도 함께 백업한다 - 안 하면 롤백이 web·worker 만 되살리고 관리 콘솔의
# 시스템 설정(타임존·DNS·호스트명·프록시·인증서)은 죽은 채로 "ROLLBACK_OK" 가 찍힌다.
for u in clovirone-web-assistant.service clovirone-web-worker.service clovirone-privhelper.service; do
  [ -f "/etc/systemd/system/$u" ] && cp "/etc/systemd/system/$u" "$BACKUP_DIR/" || true
done
[ -f /etc/nginx/sites-available/clovirone-web-assistant ] && cp /etc/nginx/sites-available/clovirone-web-assistant "$BACKUP_DIR/nginx-vhost.conf" || true

# SQLite via Backup API (spec §6.1 — not a naive copy)
DB="$VAR_DIR/web.sqlite3"
if [ -f "$DB" ]; then
  sqlite3 "$DB" ".backup '$BACKUP_DIR/web.sqlite3'"
fi

# Environment snapshot (masked-safe: statuses only)
{
  echo "# state snapshot $(date -Iseconds)"
  ss -lntp 2>/dev/null || true
  echo "---"
  systemctl is-active clovirone-web-assistant clovirone-web-worker nginx n8n 2>/dev/null || true
  echo "---"
  df -h "$VAR_DIR" 2>/dev/null || true
} > "$BACKUP_DIR/state.txt"

# Checksums
( cd "$BACKUP_DIR" && sha256sum * > SHA256SUMS 2>/dev/null || true )
echo "BACKUP_OK $BACKUP_DIR"
