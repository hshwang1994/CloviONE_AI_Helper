#!/usr/bin/env bash
# Rollback / uninstall (spec §6.2). Run as root.
#   rollback-clovirone-web-assistant.sh <BACKUP_DIR>   # restore from a backup
#   rollback-clovirone-web-assistant.sh --uninstall     # first-install rollback
# Restores only OUR files. On a shared server the full /etc/nginx tarball is a
# manual disaster-recovery artifact, never blanket-restored here.
set -euo pipefail
export LC_ALL=C.UTF-8
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

APP_DIR=/opt/clovirone-web-assistant
ETC_DIR=/etc/clovirone-web-assistant
VAR_DIR=/var/lib/clovirone-web-assistant

stop_services() {
  systemctl stop clovirone-web-worker.service 2>/dev/null || true
  systemctl stop clovirone-web-assistant.service 2>/dev/null || true
  # 특권 헬퍼(§S)는 웹 다음에 멈춘다 — 웹이 살아 있는 동안 소켓이 먼저 사라지면 관리 화면이
  # 그 사이 "도우미 없음" 을 보여 준다. 순서를 지키면 그 창이 없다.
  systemctl stop clovirone-privhelper.service 2>/dev/null || true
}

if [ "${1:-}" = "--uninstall" ]; then
  echo "=== uninstall (first-install rollback) ==="
  stop_services
  systemctl disable clovirone-web-assistant.service clovirone-web-worker.service 2>/dev/null || true
  systemctl disable clovirone-privhelper.service 2>/dev/null || true
  rm -f /etc/systemd/system/clovirone-web-assistant.service /etc/systemd/system/clovirone-web-worker.service
  rm -f /etc/systemd/system/clovirone-privhelper.service
  systemctl daemon-reload
  rm -f /etc/nginx/sites-enabled/clovirone-web-assistant /etc/nginx/sites-available/clovirone-web-assistant
  if nginx -t 2>/dev/null; then systemctl reload nginx 2>/dev/null || true; fi
  echo "제거 완료. 데이터는 보존됨: $VAR_DIR"
  echo "데이터까지 삭제하려면: rm -rf $VAR_DIR $ETC_DIR $APP_DIR"
  echo "UNINSTALL_OK"
  exit 0
fi

BACKUP_DIR="${1:-}"
[ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ] || { echo "사용법: $0 <BACKUP_DIR> | --uninstall"; exit 2; }

echo "=== rollback from $BACKUP_DIR ==="
if [ -f "$BACKUP_DIR/SHA256SUMS" ]; then
  ( cd "$BACKUP_DIR" && sha256sum -c SHA256SUMS ) || { echo "체크섬 검증 실패 — 중단"; exit 3; }
fi

stop_services

[ -f "$BACKUP_DIR/app.tar.gz" ] && { rm -rf "$APP_DIR"; tar xzf "$BACKUP_DIR/app.tar.gz" -C /opt; }
[ -f "$BACKUP_DIR/etc.tar.gz" ] && { rm -rf "$ETC_DIR"; tar xzf "$BACKUP_DIR/etc.tar.gz" -C /etc; }
if [ -f "$BACKUP_DIR/web.sqlite3" ]; then
  install -d -o clovirone-web -g clovirone-web -m 0750 "$VAR_DIR"
  # Remove stale WAL/SHM sidecars first — copying a fresh DB over an old one
  # while its -wal/-shm remain would corrupt the restored database.
  rm -f "$VAR_DIR/web.sqlite3-wal" "$VAR_DIR/web.sqlite3-shm"
  cp "$BACKUP_DIR/web.sqlite3" "$VAR_DIR/web.sqlite3"
  chown clovirone-web:clovirone-web "$VAR_DIR/web.sqlite3"
  chmod 0660 "$VAR_DIR/web.sqlite3"
  # Verify the restored DB before bringing services back up.
  if ! sqlite3 "$VAR_DIR/web.sqlite3" 'PRAGMA integrity_check;' | grep -q '^ok$'; then
    echo "복원된 DB 무결성 검사 실패 — 중단"; exit 6
  fi
fi
for u in clovirone-web-assistant.service clovirone-web-worker.service; do
  [ -f "$BACKUP_DIR/$u" ] && cp "$BACKUP_DIR/$u" /etc/systemd/system/
done
[ -f "$BACKUP_DIR/nginx-vhost.conf" ] && cp "$BACKUP_DIR/nginx-vhost.conf" /etc/nginx/sites-available/clovirone-web-assistant

systemctl daemon-reload
if ! nginx -t; then
  echo "nginx -t 실패 — 수동 확인 필요. 우리 vhost 심링크를 제거하고 재확인하세요:"
  echo "  rm -f /etc/nginx/sites-enabled/clovirone-web-assistant && nginx -t"
  exit 4
fi
systemctl reload nginx 2>/dev/null || true
systemctl restart clovirone-web-assistant.service clovirone-web-worker.service 2>/dev/null || true

for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && { echo "ROLLBACK_OK"; exit 0; }
  sleep 1
done
echo "복원 후 healthz 실패 — journalctl -u clovirone-web-assistant -n 100 확인 필요"
exit 5
