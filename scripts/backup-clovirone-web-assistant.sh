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
# BKP-04: venv는 requirements.txt(app.tar.gz 안에 이미 포함)+오프라인 wheelhouse만 있으면
# 그대로 재현 가능하다(설치 스크립트가 venv를 항상 새로 만든다) — 백업마다 수백MB를
# 그대로 반복해 담을 이유가 없다. 제외한 만큼은 rollback-clovirone-web-assistant.sh가
# 복원 직후 venv를 다시 만들어 채운다(한쪽만 바뀌면 롤백이 venv 없는 상태로 끝난다).
[ -d "$APP_DIR" ] && tar czf "$BACKUP_DIR/app.tar.gz" --exclude='clovirone-web-assistant/venv' -C /opt clovirone-web-assistant 2>/dev/null || true
[ -d "$ETC_DIR" ] && tar czf "$BACKUP_DIR/etc.tar.gz" -C /etc clovirone-web-assistant 2>/dev/null || true

# BKP-01: 첨부(게시판 글·팀챗 이미지·티켓 첨부·프로필 사진)는 DB 밖의 실제 파일이다 — DB만
# 백업하면 복구 후 그 행들이 가리키는 파일이 없어 404가 난다(OPS-01류 발견 이후 이 공백이
# 문서에는 이미 적혀 있었는데 스크립트가 안 고쳐져 있었다).
[ -d "$VAR_DIR/uploads" ] && tar czf "$BACKUP_DIR/uploads.tar.gz" -C "$VAR_DIR" uploads 2>/dev/null || true

# systemd units + nginx vhost
# DEPLOY-04: privhelper 도 함께 백업한다 - 안 하면 롤백이 web·worker 만 되살리고 관리 콘솔의
# 시스템 설정(타임존·DNS·호스트명·프록시·인증서)은 죽은 채로 "ROLLBACK_OK" 가 찍힌다.
for u in clovirone-web-assistant.service clovirone-web-worker.service clovirone-privhelper.service; do
  [ -f "/etc/systemd/system/$u" ] && cp "/etc/systemd/system/$u" "$BACKUP_DIR/" || true
done
[ -f /etc/nginx/sites-available/clovirone-web-assistant ] && cp /etc/nginx/sites-available/clovirone-web-assistant "$BACKUP_DIR/nginx-vhost.conf" || true

# PostgreSQL via pg_dump -Fc (spec §6.1 — 파일 복사가 아니다).
#
# ⚠️ **여기서 실패하면 백업 전체가 실패다.** 예전에는 `if [ -f "$DB" ]` 로 감싸 두어,
# 파일이 없으면 조용히 건너뛰고 마지막에 `BACKUP_OK` 를 찍었다 — DB 가 안 담긴 백업이
# «성공» 으로 남는다는 뜻이다. PG 로 옮긴 지금 그 조건은 **항상 거짓**이므로, 그대로 두면
# 매일 밤 DB 없는 백업이 쌓이고 그 사실을 되돌려야 하는 날에 알게 된다.
: "${DATABASE_URL:=}"
if [ -z "$DATABASE_URL" ] && [ -f "$ETC_DIR/web.env" ]; then
  DATABASE_URL="$(sed -n 's/^DATABASE_URL=//p' "$ETC_DIR/web.env" | head -1)"
  PG_BIN_DIR="$(sed -n 's/^PG_BIN_DIR=//p' "$ETC_DIR/web.env" | head -1)"
fi
[ -n "$DATABASE_URL" ] || { echo "DATABASE_URL 을 찾을 수 없습니다 ($ETC_DIR/web.env)"; exit 3; }
PGDUMP="${PG_BIN_DIR:+$PG_BIN_DIR/}pg_dump"
command -v "$PGDUMP" >/dev/null 2>&1 || { echo "pg_dump 를 찾을 수 없습니다: $PGDUMP"; exit 3; }

# `--no-owner --no-privileges`: 복원하는 쪽 역할을 따른다 — 원본과 같은 역할이 없는
# 서버(재해 복구 대상)에서 복원이 통째로 실패하지 않게 한다.
#
# **서비스 사용자로 덤프하고, 파일은 root 가 만든다.** 운영은 유닉스 소켓 + peer 인증이라
# root 로 붙으면 `root` 역할로 인증돼 거부된다 — 그래서 `runuser` 가 필요하다. 반대로
# 백업 디렉터리는 0700 root 전용이라 그 사용자가 직접 못 쓴다. 그래서 덤프는 stdout 으로
# 받고 리다이렉트를 root 쪽에서 한다.
DUMP="$BACKUP_DIR/web.dump"
if ! runuser -u "${SVC_USER:-clovirone-web}" -- "$PGDUMP"         --format=custom --no-owner --no-privileges         --dbname "$DATABASE_URL" > "$DUMP"; then
  # 실패한 덤프 조각을 남기지 않는다 — 남으면 다음 검증이 그것을 «백업» 으로 본다.
  rm -f "$DUMP"
  echo "pg_dump 실패 — 백업을 성공으로 표시하지 않습니다"; exit 3
fi
chmod 0600 "$DUMP"

# 파일이 생겼다는 것만으로 성공이 아니다(D-204). 목차를 읽을 수 있는지 확인한다.
PGRESTORE="${PG_BIN_DIR:+$PG_BIN_DIR/}pg_restore"
if ! "$PGRESTORE" --list "$DUMP" >/dev/null; then
  echo "덤프를 읽을 수 없습니다 — 백업을 성공으로 표시하지 않습니다"; exit 3
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
