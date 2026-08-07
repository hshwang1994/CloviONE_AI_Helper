#!/usr/bin/env bash
# ClovirONE Web Assistant installer (spec §30). Idempotent, re-runnable.
# Run as root.
#
# 원본은 두 가지 중 하나다:
#   (기본) 번들 STAGE   - 개발 머신에서 build-bundle.sh 로 만들어 scp 한 것.
#                         STAGE 기본값 /home/cloviradmin/deploy/stage
#   --from-repo         - 이 저장소를 git clone 한 자리에서 바로 설치한다.
#                         자세한 절차와 폐쇄망 준비물은 docs/INSTALL_FROM_GIT.md 에 있다.
#
# Does NOT create the admin account (that is a separate sensitive step —
# scripts/seed_admin.py — so the temp password never lands in this log).
# Does NOT change the firewall (spec §30).
set -euo pipefail
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive

case "$(head -c 200 "$0" 2>/dev/null)" in *$'\r'*) echo "CRLF in script"; exit 64;; esac
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

# ── 설치 원본 고르기 (P5) ────────────────────────────────────────────────────
# 예전에는 번들 STAGE 전제밖에 없었다. clone 한 사람이 문서만 보고 설치할 방법이 없어서
# 결국 개발 머신에서 build-bundle.sh 를 돌려 scp 하는 사람이 늘 한 명 필요했다.
MODE=stage
for arg in "$@"; do
  case "$arg" in
    --from-repo) MODE=repo ;;
    -h|--help)
      sed -n '2,12p' "$0"
      exit 0
      ;;
    *)
      echo "모르는 인자: $arg (쓸 수 있는 것: --from-repo)"
      exit 64
      ;;
  esac
done

STAGE="${STAGE:-/home/cloviradmin/deploy/stage}"
APP_DIR=/opt/clovirone-web-assistant
ETC_DIR=/etc/clovirone-web-assistant
VAR_DIR=/var/lib/clovirone-web-assistant
SVC_USER=clovirone-web
# 설치처 고유값. **기본값을 두지 않는다** - 예전엔 최초 고객사의 호스트명·IP 가 여기 박혀
# 있어서, 다른 곳에서 그냥 실행하면 남의 이름으로 인증서를 만들고 없는 주소에 바인딩했다.
# 무엇이 잘못됐는지 아무 데도 안 뜨는 종류의 실패라 여기서 먼저 멈춘다.
DNS_NAME="${DNS_NAME:-}"
BIND_IP="${BIND_IP:-}"
if [ -z "$DNS_NAME" ] || [ -z "$BIND_IP" ]; then
  echo "DNS_NAME 과 BIND_IP 를 지정해야 합니다(설치처마다 다른 값이라 기본값이 없습니다)."
  echo "예: DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 bash $0"
  exit 2
fi
# 원본 경로와 wheelhouse 를 여기서 한 번에 정한다. 아래 단계들은 SRC_DIR/WHEELS_DIR 만 본다.
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
# rsync 제외 목록. 첫 항목은 어차피 아래에서도 빼는 것이라 무해하다 - 배열을 비워 두면
# `set -u` 에서 빈 배열 전개가 문제를 일으키는 셸이 있어서 일부러 하나를 채워 둔다.
EXTRA_EXCLUDES=(--exclude '.git')
if [ "$MODE" = repo ]; then
  SRC_DIR="$REPO_DIR"
  # 오프라인 wheelhouse. 없으면 pip 이 인터넷(pypi.org, files.pythonhosted.org)으로 나간다.
  # 폐쇄망이면 반드시 미리 만들어 둬야 한다 - docs/INSTALL_FROM_GIT.md 의 "폐쇄망" 절.
  WHEELS_DIR="${WHEELHOUSE:-$REPO_DIR/wheelhouse}"
  # 저장소에만 있고 운영에 실리면 안 되는 것들. build-bundle.sh 가 번들에서 빼는 것과
  # 같은 목록이다(두 경로가 만드는 /opt 를 같게 유지한다).
  #   node_modules  수백 MB, 운영에서 안 쓴다
  #   .claude       에이전트 worktree 사본. 옛 코드가 섞여 무엇이 도는지 알 수 없게 된다
  #   docs          운영에서 안 읽는다
  #   wheelhouse    설치 재료지 애플리케이션이 아니다
  EXTRA_EXCLUDES+=(--exclude 'node_modules' --exclude '.claude' --exclude '.pytest_cache'
                   --exclude 'docs' --exclude 'wheelhouse' --exclude '.github'
                   --exclude '*.bak' --exclude '*.bak-*')
  # clone 을 설치 대상 안에 두면 rsync 가 자기 자신을 --delete 하며 덮어쓴다.
  if [ "$SRC_DIR" = "$APP_DIR" ]; then
    echo "저장소를 $APP_DIR 안에 clone 하지 마십시오. 설치가 자기 자신을 덮어씁니다."
    echo "예: /opt/src/clovirone-web-assistant 처럼 다른 곳에 두십시오."
    exit 65
  fi
else
  SRC_DIR="$STAGE/app-src"
  WHEELS_DIR="$STAGE/wheels"
fi

# 로그 자리. 번들 모드는 예전 그대로 둔다(운영자들이 그 경로를 외우고 있다).
# git 설치는 cloviradmin 계정이 없을 수 있어 시스템 로그 디렉터리를 쓴다.
if [ "$MODE" = repo ]; then
  LOG_DIR="${LOG_DIR:-/var/log/clovirone-web-assistant}"
else
  LOG_DIR="${LOG_DIR:-/home/cloviradmin/deploy/logs}"
fi
mkdir -p "$LOG_DIR"
LOG="$LOG_DIR/install.log"

log() { echo "[$(date +%H:%M:%S)] $*" | tee -a "$LOG"; }
trap 'echo "RESULT name=install rc=$?"' EXIT

log "=== install start (mode=$MODE src=$SRC_DIR) ==="
if [ ! -d "$SRC_DIR" ]; then
  log "원본 디렉터리가 없습니다: $SRC_DIR"
  exit 66
fi

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

# 1.5 번들 신선도 (P5) -------------------------------------------------------
# git 설치는 **커밋된 번들**(app/static/react/)을 그대로 서빙한다. 소스만 새롭고 번들을
# 다시 안 만든 상태면 이 서버는 아무 오류 없이 **옛 UI** 를 돈다. 로그에도 화면에도 흔적이
# 없어서, 이 검사를 지나지 않으면 잡을 방법이 사실상 없다.
# 번들 모드에서는 검사하지 않는다: build-bundle.sh 를 돌리는 개발 머신에서 잡는 편이 맞고,
# 배포 산출물에는 frontend/ 가 없어 판정할 근거 자체가 없다.
if [ "$MODE" = repo ]; then
  if ! command -v python3 >/dev/null 2>&1; then
    log "python3 가 없어 번들 신선도를 확인할 수 없습니다. 확인하지 않은 채로는 설치하지 않습니다."
    exit 21
  fi
  if python3 "$SRC_DIR/scripts/check_bundle_fresh.py" >>"$LOG" 2>&1; then
    log "bundle freshness OK"
  else
    log "번들이 소스보다 낡았습니다. 이대로 설치하면 이 서버는 옛 화면을 조용히 계속 씁니다."
    log "고치는 법(개발 머신에서): cd frontend && npm run build"
    log "                          python scripts/check_bundle_fresh.py --write"
    log "                          그리고 app/static/react/ 를 커밋해서 push"
    tail -n 6 "$LOG" >&2 || true
    exit 21
  fi
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
  "${EXTRA_EXCLUDES[@]}" \
  "$SRC_DIR/" "$APP_DIR/"
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
if [ -d "$WHEELS_DIR" ] && [ -n "$(ls -A "$WHEELS_DIR" 2>/dev/null)" ]; then
  log "pip install (offline wheelhouse: $WHEELS_DIR)"
  "$APP_DIR/venv/bin/pip" install --no-index --find-links "$WHEELS_DIR" --upgrade pip >>"$LOG" 2>&1 || true
  "$APP_DIR/venv/bin/pip" install --no-index --find-links "$WHEELS_DIR" -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1
else
  # 폐쇄망이면 여기서 조용히 몇 분 매달렸다가 타임아웃으로 죽는다. 무엇이 필요한지를
  # 미리 말해 둔다 - docs/INSTALL_FROM_GIT.md 의 "폐쇄망" 절에 만드는 법이 있다.
  log "wheelhouse 가 없습니다($WHEELS_DIR). pip 이 인터넷으로 나갑니다."
  log "  필요한 호스트: pypi.org, files.pythonhosted.org (HTTPS)"
  log "  폐쇄망이면 중단하고 wheelhouse 를 먼저 만드십시오: docs/INSTALL_FROM_GIT.md"
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

# 6b. 기존 설치인데 설치처 고유값이 설정에 없으면 멈춘다 (P1 업그레이드 함정) ---------
#
# 🔴 실제 운영에서 이 사고가 났다. 예전 코드는 Notion DB id 의 **기본값을 소스에 들고**
# 있어서, 그 설치의 web.env 에는 그 값이 한 줄도 없었다. P1 로 소스 기본값을 비우자
# 업그레이드 직후 그 설치는 **DB id 가 빈 채로** 떴고, 티켓·문서 조회가 전부 400 이 됐다.
# 서비스는 'active' 라 겉으로는 성공한 배포처럼 보였다 - 가장 나쁜 실패다.
#
# 그래서 **마이그레이션 전에** 막는다. 여기서 멈추면 되돌릴 것이 없다(아직 아무것도 안 바꿨다).
# 신규 설치는 DB 가 없으므로 이 검사를 지나가고, 셋업 마법사가 안내한다.
DB_FILE="$VAR_DIR/web.sqlite3"
if [ -s "$DB_FILE" ]; then
  MISSING_KEYS=""
  for key in NOTION_TASKS_DATABASE_ID NOTION_DOCUMENTS_DATABASE_ID; do
    grep -qE "^${key}=.+" "$ETC_DIR/web.env" || MISSING_KEYS="$MISSING_KEYS $key"
  done
  if [ -n "$MISSING_KEYS" ]; then
    log "STOP: 기존 설치인데 설치처 고유값이 web.env 에 없다:$MISSING_KEYS"
    cat >&2 <<EOM

이 서버에는 이미 데이터가 있는데, 새 코드가 요구하는 설치처 고유값이
  $ETC_DIR/web.env
에 없습니다. 예전 코드는 이 값의 기본값을 소스에 들고 있었지만 이제는 없습니다
(설치처마다 다른 값이라 소스에 두면 다른 고객에 설치했을 때 남의 워크스페이스를 가리킵니다).

이대로 진행하면 서비스는 뜨지만 **티켓과 문서 조회가 전부 실패**합니다.

고치는 법 - 아래를 web.env 에 추가하고 다시 실행하세요:
$(for k in $MISSING_KEYS; do echo "  $k=<이 설치의 값>"; done)

예전 값은 업그레이드 전 코드에서 확인할 수 있습니다:
  git show <이전커밋>:app/core/config.py | grep database_id
EOM
    exit 21
  fi
  log "설치처 고유값 확인됨 (기존 설치)"
fi

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
# 특권 헬퍼(§S). 이것이 있어야 관리자 콘솔의 시스템 설정(타임존·DNS·호스트 이름·프록시·
# 인증서)이 동작한다. 웹은 하드닝돼 있어 /etc 를 못 쓰기 때문이다 — 그 하드닝은 풀지 않는다.
# 없어도 웹은 정상 기동하고 화면이 "도우미가 없습니다" 라고 말한다.
cp -f "$APP_DIR/deploy/systemd/clovirone-privhelper.service" /etc/systemd/system/
mkdir -p /etc/ssl/clovirone
chmod 0750 /etc/ssl/clovirone
chmod 0644 /etc/systemd/system/clovirone-web-*.service /etc/systemd/system/clovirone-privhelper.service
systemctl daemon-reload
systemd-analyze verify /etc/systemd/system/clovirone-web-assistant.service >>"$LOG" 2>&1 || true
systemd-analyze verify /etc/systemd/system/clovirone-privhelper.service >>"$LOG" 2>&1 || true
systemctl enable clovirone-web-assistant.service clovirone-web-worker.service >>"$LOG" 2>&1
systemctl enable clovirone-privhelper.service >>"$LOG" 2>&1
# 웹보다 먼저 띄운다(유닛의 Before= 와 같은 뜻이지만, 설치 중에는 순서를 명시해야 한다).
systemctl restart clovirone-privhelper.service >>"$LOG" 2>&1 || \
  log "privhelper did not start; system settings will show as unavailable"

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
  # 사용자에게 나눠 줄 사본. cloviradmin 계정이 없는 설치(git clone 설치가 그렇다)에서는
  # cp 가 실패하고 `set -e` 때문에 설치 전체가 여기서 죽는다 - 인증서는 이미 만들어졌는데.
  # 있을 때만 둔다.
  if [ -d /home/cloviradmin ]; then
    cp -f "$CRT" "/home/cloviradmin/$DNS_NAME.crt"
    chown cloviradmin:cloviradmin "/home/cloviradmin/$DNS_NAME.crt" 2>/dev/null || true
  else
    log "cloviradmin 홈이 없어 인증서 사본을 두지 않았습니다. 원본: $CRT"
  fi
else
  log "TLS cert already present"
fi

# 11. nginx vhost + gate ----------------------------------------------------
log "install nginx vhost (DNS_NAME=$DNS_NAME BIND_IP=$BIND_IP)"
# vhost 는 템플릿이다. 설치처 값을 여기서 채운다 - 저장소에 한 고객사의 IP·호스트명을
# 박아 두면 다른 곳에 설치했을 때 남의 이름으로 응답하거나 조용히 바인딩에 실패한다.
sed -e "s/__BIND_IP__/$BIND_IP/g" -e "s/__DNS_NAME__/$DNS_NAME/g" \
  "$APP_DIR/deploy/nginx/clovirone-web-assistant.conf" \
  > /etc/nginx/sites-available/clovirone-web-assistant
# 치환이 남았으면 잘못된 vhost 를 nginx 에 물리지 않는다(nginx -t 는 이걸 못 잡는다).
if grep -q '__BIND_IP__\|__DNS_NAME__' /etc/nginx/sites-available/clovirone-web-assistant; then
  log "nginx vhost 템플릿 치환 실패 - DNS_NAME/BIND_IP 를 확인하라"
  rm -f /etc/nginx/sites-available/clovirone-web-assistant
  exit 20
fi
ln -sf /etc/nginx/sites-available/clovirone-web-assistant /etc/nginx/sites-enabled/clovirone-web-assistant

# 로그 회전 (P6). vhost 가 자기 로그 파일을 따로 쓰므로 회전 주체가 있어야 한다.
# ⚠️ 같은 파일을 두 설정이 회전시키면 logrotate 가 "duplicate log entry" 를 내고 그 실행
# 전체가 실패한다. 데비안/우분투 nginx 패키지는 /var/log/nginx/*.log 를 이미 가져가므로,
# 그럴 때는 우리 설정을 **넣지 않는 것이 옳다.**
LOGROTATE_SRC="$APP_DIR/deploy/nginx/logrotate-clovirone-web-assistant"
if grep -qs '/var/log/nginx/\*\.log' /etc/logrotate.d/nginx; then
  log "logrotate: 배포판 nginx 설정이 우리 로그도 회전시킨다 - 중복 설정을 넣지 않는다"
  rm -f /etc/logrotate.d/clovirone-web-assistant
elif [ -f "$LOGROTATE_SRC" ]; then
  cp -f "$LOGROTATE_SRC" /etc/logrotate.d/clovirone-web-assistant
  chown root:root /etc/logrotate.d/clovirone-web-assistant
  chmod 0644 /etc/logrotate.d/clovirone-web-assistant
  # 문법이 틀리면 회전이 조용히 멈춘다. 지금 확인해서 지금 알려 준다.
  if command -v logrotate >/dev/null 2>&1; then
    logrotate -d /etc/logrotate.d/clovirone-web-assistant >>"$LOG" 2>&1 \
      || log "logrotate 설정 점검에서 경고가 났다 - $LOG 를 확인하라"
  fi
  log "logrotate: /etc/logrotate.d/clovirone-web-assistant 설치"
fi

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
