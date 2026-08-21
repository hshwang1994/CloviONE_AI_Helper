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
KEEP_PLATFORM_DAYS=7   # 플랫폼 백업 보존 기간(일)
KEEP_N8N=4        # n8n DB 백업 보존 개수 (주 단위 실행 기준 4주)

log() { echo "[backup-cron] $(date -Iseconds) $*"; }

# 1) 플랫폼 백업 (기존 스크립트 재사용 — DB 는 `pg_dump -Fc` 로 일관 온라인 덤프).
#    그 스크립트는 덤프에 실패하면 **0 이 아닌 코드로 죽는다** — `set -e` 아래라 여기서
#    함께 멈춘다. DB 없는 백업이 «성공» 으로 남는 것보다 낫다(D-204).
if [ -x "$APP_DIR/scripts/backup-clovirone-web-assistant.sh" ]; then
  "$APP_DIR/scripts/backup-clovirone-web-assistant.sh"
else
  log "SKIP: 플랫폼 백업 스크립트 없음"
fi

# 2) 플랫폼 백업 보존 정리 — 타임스탬프 디렉터리(YYYYmmdd_HHMMSS / YYYYmmdd-HHMMSS)만 대상.
#    설치·배포 스크립트가 만든 백업도 같은 이름 규칙이므로 함께 보존 관리된다(같은 풀을
#    공유한다는 뜻이기도 하다 — 그래서 "개수"가 아니라 "나이"로 지운다, BKP-10). 예전엔
#    "최근 KEEP_PLATFORM개만 남긴다"였는데, 배포 백업이 일일 백업과 같은 이름 규칙·같은
#    풀을 쓰다 보니 배포가 잦은 날 하루 만에 일주일치 복원 지점이 증발할 수 있었다(배포
#    N번 = 그날 슬롯 N개 소모). 배포 빈도와 무관하게 항상 최소 KEEP_PLATFORM_DAYS일치가
#    남도록, 그 기간보다 오래된 것만 지운다.
if [ -d "$BACKUP_ROOT" ]; then
  mapfile -t old_dirs < <(find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d \
    -regextype posix-extended -regex '.*/[0-9]{8}[-_][0-9]{6}' \
    -mtime "+$KEEP_PLATFORM_DAYS")
  for d in "${old_dirs[@]}"; do
    log "prune platform backup: $d"
    rm -rf -- "$d"
  done
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
