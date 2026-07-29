#!/usr/bin/env bash
# 정기 백업 cron 설치 (root, 멱등). 매일 03:30 KST 실행.
set -euo pipefail
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

APP_DIR=/opt/clovirone-web-assistant
CRON_FILE=/etc/cron.d/clovirone-backups

install -o root -g root -m 0755 "$APP_DIR/scripts/backup-cron.sh" /usr/local/sbin/clovirone-backup-cron

cat > "$CRON_FILE" <<'CRON'
# ClovirONE 정기 백업 — 매일 03:30 플랫폼 백업(+보존 7), 일요일엔 n8n DB 백업(+보존 4)
SHELL=/bin/bash
PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin
30 3 * * * root /usr/local/sbin/clovirone-backup-cron >> /var/log/clovirone-backup.log 2>&1
CRON
chmod 0644 "$CRON_FILE"

echo "INSTALL_BACKUP_CRON_OK ($CRON_FILE)"
