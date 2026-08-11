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
# BKP-04: app.tar.gz(2026-08-11부터)는 venv를 담지 않는다(requirements.txt만 있으면 그대로
# 재현 가능해 백업 크기만 키우던 것을 뺐다) — 복원 직후 여기서 다시 만들지 않으면 systemd
# 유닛이 가리키는 $APP_DIR/venv/bin/python 자체가 없어 서비스가 아예 못 뜬다. 구버전
# 백업(app.tar.gz가 venv를 이미 담고 있던 시절)이면 이 블록은 조용히 건너뛴다.
if [ -f "$BACKUP_DIR/app.tar.gz" ] && [ ! -x "$APP_DIR/venv/bin/python" ]; then
  echo "venv 재생성 중 (app.tar.gz는 2026-08-11부터 venv를 백업에 포함하지 않습니다)..."
  python3 -m venv "$APP_DIR/venv"
  WHEELS_DIR="${WHEELHOUSE:-}"
  if [ -n "$WHEELS_DIR" ] && [ -d "$WHEELS_DIR" ] && [ -n "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
    echo "pip install (offline wheelhouse: $WHEELS_DIR)"
    "$APP_DIR/venv/bin/pip" install --no-index --find-links "$WHEELS_DIR" --upgrade pip >/dev/null 2>&1 || true
    "$APP_DIR/venv/bin/pip" install --no-index --find-links "$WHEELS_DIR" -r "$APP_DIR/requirements.txt" >/dev/null 2>&1
  else
    echo "wheelhouse 없음(WHEELHOUSE 환경변수로 지정 가능) — pip이 인터넷으로 나갑니다."
    echo "  필요한 호스트: pypi.org, files.pythonhosted.org (HTTPS)"
    "$APP_DIR/venv/bin/pip" install --upgrade pip >/dev/null 2>&1 || true
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >/dev/null 2>&1
  fi
  "$APP_DIR/venv/bin/python" -c "import fastapi, sqlalchemy, alembic, httpx, argon2, pydantic_settings, cronsim; print('imports ok')"
fi
[ -f "$BACKUP_DIR/etc.tar.gz" ] && { rm -rf "$ETC_DIR"; tar xzf "$BACKUP_DIR/etc.tar.gz" -C /etc; }
# BKP-01: 첨부(게시판·팀챗·티켓·프로필 사진)도 되살린다 — DB 행이 가리키는 파일이 없으면
# 그 행들은 조용히 404가 난다(BKP-02가 잡는 것과 같은 종류의 갭). OPS-01/OPS-02 실사고와
# 같은 이유로 chown을 명시한다(이 디렉터리는 소유권이 어긋난 전례가 있다).
if [ -f "$BACKUP_DIR/uploads.tar.gz" ]; then
  install -d -o clovirone-web -g clovirone-web -m 0750 "$VAR_DIR"
  rm -rf "$VAR_DIR/uploads"
  tar xzf "$BACKUP_DIR/uploads.tar.gz" -C "$VAR_DIR"
  chown -R clovirone-web:clovirone-web "$VAR_DIR/uploads"
fi
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
# DEPLOY-04: privhelper 도 되살린다 - 예전엔 web·worker 만 복원해 healthz 는 통과하고
# "ROLLBACK_OK" 가 찍히는데, 관리 콘솔의 시스템 설정(타임존·DNS·호스트명·프록시·인증서)은
# 죽은 채로 남았다. 백업이 그 유닛을 안 담고 있으면(구버전 백업) 조용히 건너뛴다 - 그 경우
# install 이 다음에 다시 배포될 때 재생성된다, 지금 당장은 web·worker 복원이 우선이다.
for u in clovirone-web-assistant.service clovirone-web-worker.service clovirone-privhelper.service; do
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
systemctl restart clovirone-privhelper.service 2>/dev/null || \
  echo "privhelper 재시작 실패 - 시스템 설정 화면이 '도우미 없음'을 보일 수 있습니다(치명적이지 않음)"

for i in $(seq 1 20); do
  curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 && { echo "ROLLBACK_OK"; exit 0; }
  sleep 1
done
echo "복원 후 healthz 실패 — journalctl -u clovirone-web-assistant -n 100 확인 필요"
exit 5
