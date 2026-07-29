#!/usr/bin/env bash
# 정기 백업 cron 진입점 (root). 매일: 플랫폼 백업 + 보존 정리. 일요일: n8n DB 백업 추가.
# 설치: scripts/install-backup-cron.sh 참조. 수동 실행도 안전(멱등).
set -euo pipefail
export LC_ALL=C.UTF-8
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

APP_DIR=/opt/clovirone-web-assistant
BACKUP_ROOT=/var/backups/clovirone-web-assistant
N8N_BACKUP_ROOT=/var/backups/n8n
N8N_DB=/var/lib/n8n/.n8n/database.sqlite
KEEP_PLATFORM=7   # 플랫폼 백업 보존 개수 (일 단위 실행 기준 7일)
KEEP_N8N=4        # n8n DB 백업 보존 개수 (주 단위 실행 기준 4주)

log() { echo "[backup-cron] $(date -Iseconds) $*"; }

# 1) 플랫폼 백업 (기존 스크립트 재사용 — DB는 sqlite Backup API로 일관 스냅샷)
if [ -x "$APP_DIR/scripts/backup-clovirone-web-assistant.sh" ]; then
  "$APP_DIR/scripts/backup-clovirone-web-assistant.sh"
else
  log "SKIP: 플랫폼 백업 스크립트 없음"
fi

# 2) 플랫폼 백업 보존 정리 — 타임스탬프 디렉터리(YYYYmmdd_HHMMSS / YYYYmmdd-HHMMSS)만 대상.
#    설치·배포 스크립트가 만든 백업도 같은 이름 규칙이므로 함께 보존 관리된다.
if [ -d "$BACKUP_ROOT" ]; then
  mapfile -t dirs < <(find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d \
    -regextype posix-extended -regex '.*/[0-9]{8}[-_][0-9]{6}' | sort)
  count=${#dirs[@]}
  if (( count > KEEP_PLATFORM )); then
    for d in "${dirs[@]:0:count-KEEP_PLATFORM}"; do
      log "prune platform backup: $d"
      rm -rf -- "$d"
    done
  fi
fi

# 3) n8n DB 백업 (일요일에만) — 온라인 스냅샷은 sqlite Backup API 사용(WAL 안전)
if [ "$(date +%u)" = "7" ] && [ -f "$N8N_DB" ]; then
  install -d -o root -g root -m 0700 "$N8N_BACKUP_ROOT"
  out="$N8N_BACKUP_ROOT/database-$(date +%Y%m%d_%H%M%S).sqlite"
  sqlite3 "$N8N_DB" ".backup '$out'"
  gzip -f "$out"
  log "n8n DB backup: $out.gz ($(du -h "$out.gz" | cut -f1))"
  mapfile -t n8nbaks < <(find "$N8N_BACKUP_ROOT" -maxdepth 1 -name 'database-*.sqlite.gz' | sort)
  n8ncount=${#n8nbaks[@]}
  if (( n8ncount > KEEP_N8N )); then
    for f in "${n8nbaks[@]:0:n8ncount-KEEP_N8N}"; do
      log "prune n8n backup: $f"
      rm -f -- "$f"
    done
  fi
fi

log "BACKUP_CRON_OK"
