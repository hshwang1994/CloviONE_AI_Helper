#!/usr/bin/env bash
# ClovirAssist 설치 · 배포 자동화 단일 진입점 (docs/platform/INSTALLATION.md).
#
#   sudo /opt/clovirassist/deploy/install.sh <subcommand> [options]
#
# 서브커맨드: install · upgrade · rollback · uninstall · verify · version · preflight · storage · ai
#
# ── 받는 길은 셋이고 설치 명령은 하나다 (계획 3.17, D-522) ─────────────────────
#
#   최종 사용자  Release 페이지에서 이 파일 하나를 받아 실행한다.
#                sudo bash install.sh install --release v1.2.0 --dns-name <host> --bind-ip <ip>
#                스크립트가 같은 Release 의 묶음과 SHA256SUMS 를 받아 **확인한 뒤에만** 푼다.
#   개발자       git clone 한 저장소 안의 deploy/install.sh 를 실행한다(--ref 로 태그 고정).
#   폐쇄망       오프라인 번들(--source bundle)과 wheelhouse 로 설치한다.
#
# 설치가 끝나면 /usr/local/bin/clovirassist 가 생긴다. 그 뒤의 업그레이드, 되돌리기, 검증, 계정, 저장소, AI 모델은
# 전부 `sudo clovirassist <명령>` 하나로 한다(deploy/clovirassist-cli.sh).
#
# ── 이 스크립트가 옛 installer 와 다른 점 ────────────────────────────────────
#
# 1. **검증이 전부 Preflight(Stage 0)에 있다.** 옛 스크립트는 rsync --delete 로 /opt 를
#    갈아엎고 venv 를 다시 만든 **뒤에** 테넌트 값 가드가 exit 21 을 했다. 그 순간 서버는
#    「새 코드 + 옛 스키마」였고, 되돌리는 일은 호출자에게 떠넘겨졌다. 아무것도 바꾸기 전에
#    멈추면 되돌릴 것이 없다.
# 2. **어느 Stage 에서 왜 멈췄는지가 표준 출력만으로 판별된다.**
#    `STAGE_<n>_<NAME>: OK|SKIP|FAIL <사유> | <조치>` 한 줄이 Stage 마다 나간다.
# 3. **재실행이 무해하다.** 모든 Stage 가 「이미 되어 있음」을 감지한다. 설정·데이터·비밀은
#    최초 1회만 만들고 이후에는 보존한다.
# 4. **slug 가 `clovirassist` 다** (R13). 옛 설치(`clovirone-web-assistant`)를 발견하면
#    스냅샷을 뜬 뒤 경로·유닛·시스템 계정을 새 이름으로 이전한다.
#
# ── SKIP 이 있는 이유 ────────────────────────────────────────────────────────
# 아직 제품에 없는 Component(File Storage Provider=S8, AI Gateway=S9)의 Stage 는 OK 가
# 아니라 SKIP 을 낸다. OK 로 찍으면 「설치했다」는 거짓말이 로그에 남는다. 그 Session 들이
# 자기 Component 를 넣을 때 SKIP 이 OK 로 바뀐다 — S22 Acceptance 는 전 Stage OK 를
# 요구하므로 SKIP 이 남아 있으면 그때 걸린다.

set -euo pipefail
export LC_ALL=C.UTF-8 DEBIAN_FRONTEND=noninteractive

case "$(head -c 400 "$0" 2>/dev/null)" in *$'\r'*) echo "CRLF in script"; exit 64;; esac

# ── 제품 정체성 ──────────────────────────────────────────────────────────────
# app/core/product.py 와 **글자까지 같아야 한다.**
# tests/unit/test_product_identity.py 가 그 일치를 지킨다.
SLUG=clovirassist
SVC_USER=clovirassist
APP_DIR="/opt/$SLUG"
ETC_DIR="/etc/$SLUG"
VAR_DIR="/var/lib/$SLUG"
BACKUP_ROOT="/var/backups/$SLUG"
LOG_ROOT="/var/log/$SLUG"
RUN_DIR="/run/$SLUG"
TLS_DIR="$ETC_DIR/tls"
SECRETS_DIR="$ETC_DIR/secrets"
ENV_FILE="$ETC_DIR/$SLUG.env"
MANIFEST="$ETC_DIR/installed_manifest.json"
STATE_FILE="$LOG_ROOT/install_state.json"
NGINX_SITE="$SLUG"
SSL_FALLBACK_DIR="/etc/ssl/$SLUG"

WEB_UNIT="$SLUG-web.service"
WORKER_UNIT="$SLUG-worker.service"
WORKER_CONV_UNIT="$SLUG-worker-conversational.service"
SCHEDULER_UNIT="$SLUG-scheduler.service"
INDEX_UNIT="$SLUG-index.service"
PRIVHELPER_UNIT="$SLUG-privhelper.service"
# 기동 순서. privhelper 가 먼저(관리 화면이 「도우미 없음」을 안 보이게), 웹이 마지막
# (VIS-109R: 워커가 새 job_type 을 이해하기 전에 웹이 그 잡을 넣을 수 있는 창을 없앤다).
ALL_UNITS=("$PRIVHELPER_UNIT" "$WORKER_UNIT" "$WORKER_CONV_UNIT" "$SCHEDULER_UNIT" "$INDEX_UNIT" "$WEB_UNIT")
# 재부팅 뒤 **떠 있어야** 하는 유닛. 대화형 레인은 설정 플래그가 꺼져 있으면 정상적으로
# exit(0) 해 inactive(dead) 가 된다 — 그것이 그 유닛의 정상 대기 상태다 (D-118).
# 색인 레인은 기본이 켜짐이라 여기 있다 (S9 · D-203) — 임베딩 모델이 없어도 파싱과
# chunk 는 돌아야 하므로 「모델이 없으니 안 떠도 된다」가 아니다.
ALWAYS_ACTIVE_UNITS=("$PRIVHELPER_UNIT" "$WORKER_UNIT" "$SCHEDULER_UNIT" "$INDEX_UNIT" "$WEB_UNIT")

LEGACY_SLUG=clovirone-web-assistant
LEGACY_SVC_USER=clovirone-web
LEGACY_PREFIX=clovirone
# 옛 유닛 이름 넷. **여기서만** 옛 이름을 안다 — 이전 경로가 그것을 찾아야 하기 때문이다.
# 다른 곳에 또 적으면 옛 정체성이 제품에 남는다(CLAUDE.md §0).
LEGACY_UNITS=("${LEGACY_SLUG}.service"
              "${LEGACY_SVC_USER}-worker.service"
              "${LEGACY_SVC_USER}-worker-conversational.service"
              "${LEGACY_PREFIX}-privhelper.service")

PG_MAJOR=16
PG_ROLE="$SLUG"
PG_DB="$SLUG"
PG_BIN_DIR="/usr/lib/postgresql/$PG_MAJOR/bin"
APP_PORT=8080

# 워커 수 × (pool_size + max_overflow). app/core/db.py 의 기본값이 5+10 이고 웹 유닛이
# --workers 4 다. 여기에 워커·스케줄러·대화형 레인 프로세스와 AI 쿼터 잠금이 쓰는 몫을
# 더해 여유를 둔다(WORK_STATE 의 「쿼터 잠금이 커넥션을 하나 더 쓴다」 risk).
PG_MIN_CONNECTIONS=120

# ── 기본값 없는 설치처 고유값 ────────────────────────────────────────────────
# 저장소에 한 고객사의 이름·IP 를 박아 두면 다른 곳에 설치했을 때 남의 이름으로 인증서를
# 만들고 없는 주소에 바인딩한다. 무엇이 잘못됐는지 아무 데도 안 뜨는 종류의 실패다.
DNS_NAME="${DNS_NAME:-}"
BIND_IP="${BIND_IP:-}"
# 앞단 역방향 프록시(쉼표 구분 IP · CIDR). 비우면 연결한 주소가 곧 사용자 주소다.
# 있는데 비워 두면 nginx 의 속도 제한이 **프록시 주소 하나**에 걸려 사용자 전원이 한 예산을
# 나눈다 — 같은 프록시를 지나는 스캐너가 하루 1만 건의 429 를 만들던 날 실제 사용자 요청도
# 429 를 맞았다(2026-09-21 실측, docs/NGINX_AND_CAPACITY.md). `none` 은 기록된 값을 지운다.
UPSTREAM_PROXIES="${UPSTREAM_PROXIES:-}"

SOURCE_KIND=""            # git | bundle | local
GIT_REMOTE="${GIT_REMOTE:-}"
GIT_REF="${GIT_REF:-}"
WHEELHOUSE="${WHEELHOUSE:-}"
OFFLINE=0
ASSUME_YES=0
INJECT_FAILURE=""         # 리허설용 — INSTALLATION.md §8 부가검증 3
ROLLBACK_TARGET=""
PURGE=0
# AI Component(S9). **기본이 꺼짐이다** — AI 기능을 기본 ON 으로 두는 관례가 이 저장소에
# 없고(`llm_enabled`·`game_ai_enabled`·`assistant_narrative_enabled` 전부 기본 OFF),
# 켜려면 임베딩 모델 파일 465MB 가 서버에 들어와 있어야 한다. `--ai-model-dir` 를 주면
# 「켠다」는 뜻이므로 함께 켜진다.
WITH_AI=0
AI_MODEL_DIR="${AI_MODEL_DIR:-}"
# 로컬 릴레이 구성 요소(Postfix · OpenDKIM, D-551)를 빼고 설치한다 - 특수 설치 예외다. 기본은 설치하고 꺼 둔다.
WITHOUT_MAIL_RELAY=0
# 오프라인 설치에서 메일 구성 요소 .deb 가 든 디렉터리(Packages.gz). 비우면 wheelhouse 옆의 debs/ 를 쓴다.
MAIL_DEBS="${MAIL_DEBS:-}"
# 임베딩 모델을 설치 중에 받는다(계획 3.16). 주소, revision, 파일마다의 sha256 은 제품 카탈로그(app/ai/catalog.py)에
# 고정돼 있고, 받은 파일은 그 값과 맞아야만 쓴다. 폐쇄망은 지금처럼 --ai-model-dir 로 넣는다.
DOWNLOAD_MODEL=0

# GitHub Release 설치(계획 3.17, D-522). RELEASE_TAG_DEFAULT 는 저장소에서는 비어 있고, Release 에 올리는 단독
# install.sh 에는 scripts/build-bundle.sh 가 그 Release 의 태그를 적는다. 그래서 Release 에서 받은 파일은
# --release 없이 돌려도 자기 버전을 설치한다.
RELEASE_TAG=""
RELEASE_TAG_DEFAULT=""
RELEASE_BASE="${RELEASE_BASE:-}"
RELEASE_BASE_DEFAULT="https://github.com/hshwang1994/clovirassist/releases/download"
RELEASE_WORK_DIR=""
# 설치 뒤의 운영 명령. 이 파일(deploy/clovirassist-cli.sh)을 Stage 13 이 깐다.
CLI_BIN="/usr/local/bin/$SLUG"
# Stage 10 이 만든 첫 관리자 설정 코드. 설치 로그에는 쓰지 않고, 모든 Stage 가 끝난 뒤 콘솔에만 한 번 보인다.
FIRST_ADMIN_CODE=""
FIRST_ADMIN_EXPIRES=""

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── 출력 ─────────────────────────────────────────────────────────────────────
LOG=""
declare -a STAGE_RESULTS=()
CURRENT_STAGE=""

_ts() { date +%Y%m%d-%H%M%S; }
log()  { local line="[$(date +%H:%M:%S)] $*"; echo "$line"; [ -n "$LOG" ] && echo "$line" >>"$LOG" || true; }
say()  { echo "$*"; [ -n "$LOG" ] && echo "$*" >>"$LOG" || true; }
die()  { say "$1"; exit "${2:-1}"; }  # 둘째 인자는 종료 코드다 - 메시지에 섞지 않는다

open_log() {
  mkdir -p "$LOG_ROOT" 2>/dev/null || true
  chmod 0750 "$LOG_ROOT" 2>/dev/null || true
  LOG="$LOG_ROOT/install-$(_ts).log"
  : >"$LOG" 2>/dev/null || LOG=""
  [ -n "$LOG" ] && chmod 0640 "$LOG" 2>/dev/null || true
}

# `STAGE_<n>_<NAME>: OK|SKIP|FAIL <사유> | <조치>`
# 이 한 줄이 계약이다. 로그 파일을 열어 보지 않고도 어디서 왜 멈췄는지 판별돼야 한다.
stage_line() {
  local n="$1" name="$2" verdict="$3" reason="${4:-}" action="${5:-}"
  local line="STAGE_${n}_${name}: ${verdict}"
  [ -n "$reason" ] && line="$line ${reason}"
  [ -n "$action" ] && line="$line | 조치: ${action}"
  say "$line"
  STAGE_RESULTS+=("{\"stage\":$n,\"name\":\"$name\",\"verdict\":\"$verdict\",\"reason\":$(json_str "$reason")}")
  write_state
}

json_str() {
  local s="${1:-}"
  s="${s//\\/\\\\}"; s="${s//\"/\\\"}"; s="${s//$'\n'/ }"; s="${s//$'\t'/ }"
  printf '"%s"' "$s"
}

write_state() {
  [ -d "$LOG_ROOT" ] || return 0
  local joined="" r
  for r in "${STAGE_RESULTS[@]:-}"; do
    [ -z "$r" ] && continue
    [ -n "$joined" ] && joined="$joined,"
    joined="$joined$r"
  done
  {
    printf '{\n'
    printf '  "slug": "%s",\n' "$SLUG"
    printf '  "subcommand": %s,\n' "$(json_str "${SUBCOMMAND:-}")"
    printf '  "started_at": %s,\n' "$(json_str "${STARTED_AT:-}")"
    printf '  "log": %s,\n' "$(json_str "$LOG")"
    printf '  "stages": [%s]\n' "$joined"
    printf '}\n'
  } >"$STATE_FILE" 2>/dev/null || true
  chmod 0640 "$STATE_FILE" 2>/dev/null || true
}

# Stage 실행기. 함수가 0 이 아니면 그 자리에서 멈춘다 — 다음 Stage 로 넘어가지 않는다.
# `_reason`/`_action` 은 Stage 함수가 채운다.
_reason=""; _action=""
run_stage() {
  local n="$1" name="$2" fn="$3"
  CURRENT_STAGE="$n"
  _reason=""; _action=""
  if [ "$INJECT_FAILURE" = "$n" ]; then
    stage_line "$n" "$name" FAIL "의도적 실패 주입(--inject-failure $n)" \
      "리허설용 스위치다. 실제 설치에서는 이 인자를 주지 않는다"
    say "INSTALL_FAILED stage=$n name=$name"
    exit 90
  fi
  local rc=0
  "$fn" || rc=$?
  if [ "$rc" -eq 0 ]; then
    stage_line "$n" "$name" OK "$_reason"
  elif [ "$rc" -eq 3 ]; then
    stage_line "$n" "$name" SKIP "$_reason" "$_action"
  else
    stage_line "$n" "$name" FAIL "${_reason:-원인 미상(rc=$rc)}" "${_action:-$LOG 의 마지막 40줄을 확인하라}"
    [ -n "$LOG" ] && { say "--- $LOG (마지막 40줄) ---"; tail -n 40 "$LOG" | sed 's/^/  /'; }
    say "INSTALL_FAILED stage=$n name=$name"
    exit "$rc"
  fi
}
skip() { _reason="$1"; _action="${2:-}"; return 3; }
fail() { _reason="$1"; _action="${2:-}"; return "${3:-20}"; }

# ── 도우미 ───────────────────────────────────────────────────────────────────
have() { command -v "$1" >/dev/null 2>&1; }

# `/healthz` 가 200 을 줄 때까지 기다린다. 유닛은 `Type=simple` 이라 프로세스가 뜨는 순간
# active 지만, uvicorn 이 워커 넷을 올려 포트를 듣기까지는 그보다 오래 걸린다 —
# 「active 인데 아직 안 듣는다」를 실패로 읽지 않으려면 기다리는 쪽이 한 곳이어야 한다.
wait_for_health() {
  local timeout="${1:-40}" i
  for i in $(seq 1 "$timeout"); do
    curl -fsS "http://127.0.0.1:$APP_PORT/healthz" >/dev/null 2>&1 && return 0
    sleep 1
  done
  return 1
}
unit_exists() { [ -f "/etc/systemd/system/$1" ]; }
unit_active() { systemctl is-active --quiet "$1" 2>/dev/null; }

# `KEY=VALUE` 파일을 **단어 분리 없이** 환경으로 올린다.
# 옛 스크립트의 `env $(grep -v '^#' file | xargs)` 는 값에 공백이나 따옴표가 있으면
# 조용히 깨졌다(`ALLOWED_EMAIL_DOMAINS=a.com, b.com` 한 줄이면 그렇다).
export_env_file() {
  local f="$1" line key val
  [ -f "$f" ] || return 0
  while IFS= read -r line || [ -n "$line" ]; do
    line="${line%$'\r'}"
    case "$line" in ''|'#'*) continue;; esac
    case "$line" in *=*) ;; *) continue;; esac
    key="${line%%=*}"; val="${line#*=}"
    case "$key" in *[!A-Za-z0-9_]*) continue;; esac
    export "$key=$val"
  done <"$f"
}

env_get() {
  local key="$1" f="${2:-$ENV_FILE}"
  [ -f "$f" ] || return 1
  sed -n "s/^${key}=//p" "$f" | tail -1
}

env_set() {
  local key="$1" val="$2" f="${3:-$ENV_FILE}"
  if grep -qE "^${key}=" "$f" 2>/dev/null; then
    local tmp; tmp="$(mktemp)"
    awk -v k="$key" -v v="$val" 'BEGIN{FS=OFS="="} $1==k {print k "=" v; done=1; next} {print} END{if(!done) print k "=" v}' "$f" >"$tmp"
    cat "$tmp" >"$f"; rm -f "$tmp"
  else
    printf '%s=%s\n' "$key" "$val" >>"$f"
  fi
}

# 서비스 계정 + 설치 환경으로 명령을 돌린다. alembic·discovery·seed 가 이걸 쓴다.
run_as_app() {
  ( export_env_file "$ENV_FILE"; cd "$APP_DIR" && exec runuser -u "$SVC_USER" --preserve-environment -- "$@" )
}

psql_super() { runuser -u postgres -- psql -v ON_ERROR_STOP=1 -tAc "$1"; }

# alembic 출력에서 revision 만 뽑는다.
#
# 🔴 여기가 한 번 틀렸다. 예전 구현은 `^[0-9a-f]{6,}` 로 걸렀는데 이 저장소의 head 는
# `0001_pg_baseline` 이라 16진수 여섯 자리로 시작하지 않는다 — 그래서 마이그레이션이
# **정상으로 붙었는데도** Stage 9 가 «revision 이 비어 있습니다» 로 죽었다. 검사기가 제품을
# 틀렸다고 말하는 종류라, LXD 리허설이 거기서 멈추고 나서야 드러났다.
# alembic 이 앞에 붙이는 로그 줄만 걷어내고 마지막 줄의 첫 낱말을 쓴다.
_alembic_revision() {
  grep -vE '^(INFO|WARNI|DEBUG|ERROR|CRITI)' | grep -vE '^[[:space:]]*$' | tail -1 | awk '{print $1}'
}
alembic_head_code() {
  run_as_app "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" heads 2>/dev/null | _alembic_revision
}
alembic_current_db() {
  run_as_app "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" current 2>/dev/null | _alembic_revision
}

legacy_present() {
  # 🔴 **옛 자리에 뭐라도 남아 있으면 이전이 안 끝난 것이다** (S14).
  #
  # 예전에는 `/opt` · `web.env` · 유닛 셋만 봤다. 그 셋이 먼저 사라지고 `/etc/<옛>/secrets`
  # 만 남는 상태가 실제로 생겼고(디렉터리 병합 버그), 그때 이 함수가 「이전할 것 없음」을
  # 돌려주는 바람에 **다시 실행해도 그 비밀들이 영원히 안 옮겨졌다.**
  #
  # 남은 것을 보는 쪽이 옳다: 이전이 끝났으면 옛 디렉터리 자체가 없다.
  [ -d "/opt/$LEGACY_SLUG" ] || [ -d "/etc/$LEGACY_SLUG" ] || [ -d "/var/lib/$LEGACY_SLUG" ]     || unit_exists "${LEGACY_UNITS[0]}"
}

# ── 인자 ─────────────────────────────────────────────────────────────────────
usage() {
  cat <<EOF
ClovirAssist 설치 진입점

  sudo $SCRIPT_PATH <subcommand> [options]

서브커맨드
  install     Clean 설치 또는 재실행(idempotent). --dns-name·--bind-ip 필요
  upgrade     스냅샷 → 새 ref checkout → 재설치 → Health. 옛 slug 설치도 이 경로로 이전한다
  rollback    스냅샷으로 원복. 대상을 안 주면 가장 최근 스냅샷
  uninstall   유닛·설정·소스 제거. --purge 를 주면 데이터와 백업까지 지운다
  verify      설치가 실제로 동작하는지 확인(TLS 검증 포함). 아무것도 바꾸지 않는다
  version     VERSION · git ref/commit · alembic head · PG/extension 버전 · 유닛 상태
  preflight   Stage 0 만 실행한다. 아무것도 바꾸지 않는다
  storage     Stage 11 만 실행한다. 저장소를 추가한 뒤 마운트 유닛을 다시 깐다(S8)
  ai          Stage 12 만 실행한다. 모델을 나중에 넣고 AI 를 켤 때 쓴다(S9)
  mail-relay  로컬 릴레이 구성 요소(Postfix · OpenDKIM)를 나중에 깐다. 깐 뒤에도 꺼져 있다(D-551)

설치 뒤에는 같은 일을 sudo clovirassist <서브커맨드> 로 합니다. clovirassist user, migrate, storage-cli,
ai-cli, first-admin-code 는 제품 안의 도구입니다(clovirassist --help).

옵션
  --dns-name <name>     설치처 호스트명. 인증서 CN/SAN 과 nginx server_name 이 이 값이다
  --bind-ip <ip>        nginx 가 묶일 주소
  --upstream-proxy <ip[,cidr…]>
                        앞단 역방향 프록시 주소. nginx 가 그 뒤의 실제 사용자 주소로 속도 제한을
                        건다. 한 번 주면 manifest 가 기억하고, none 을 주면 지운다
  --source git|bundle|local|release
  --release <tag>       GitHub Release 로 설치하거나 업그레이드한다(예: v1.2.0). 받은 묶음은
                        SHA256SUMS 와 맞아야만 푼다. Release 에서 받은 install.sh 는 기본이 자기 태그다
  --release-base <url>  Release 자산을 받을 주소. 기본은 공개 저장소의 releases/download 다
  --git-remote <url>    제품 기준 Source. 기본은 기존 설치의 manifest 값
  --ref <tag>           고정할 tag. 브랜치 추적은 하지 않는다
  --wheelhouse <dir>    오프라인 wheel 디렉터리
  --offline             네트워크를 쓰지 않는다(wheelhouse·번들 필수)
  --with-ai             AI Component 를 함께 설치한다(임베딩 런타임 + 모델 로드 검증)
  --ai-model-dir <dir>  임베딩 모델 파일이 있는 디렉터리. 주면 --with-ai 가 함께 켜진다
  --download-model      임베딩 모델을 설치 중에 받는다. 제품이 고정한 체크섬과 맞아야 쓴다. --with-ai 가 함께 켜진다
  --without-mail-relay  로컬 릴레이 구성 요소(Postfix · OpenDKIM)를 깔지 않는다. 기본은 깔고 꺼 둔다
  --mail-debs <dir>     오프라인 설치에서 메일 구성 요소 .deb 가 든 디렉터리. 기본은 wheelhouse 옆의 debs/
  --inject-failure <n>  Stage n 에서 일부러 멈춘다(리허설 전용)
  --purge               uninstall 에서 데이터·백업까지 지운다
  --yes                 되돌리기 어려운 동작을 묻지 않고 진행한다
EOF
}

SUBCOMMAND="${1:-}"
[ -n "$SUBCOMMAND" ] || { usage; exit 64; }
shift || true
case "$SUBCOMMAND" in
  install|upgrade|rollback|uninstall|verify|version|preflight|storage|ai|mail-relay) ;;
  # clovirassist user|migrate|storage-cli|ai-cli|first-admin-code 가 이 길로 온다(deploy/clovirassist-cli.sh).
  # 설치 환경을 읽어 서비스 계정으로 도는 방법(run_as_app)이 이 파일 한 곳에만 있게 하려는 것이다.
  app-cli)
    [ "${EUID:-$(id -u)}" -eq 0 ] || die "root 권한이 필요합니다: sudo clovirassist …" 1
    APP_CLI_MODULE="${1:-}"
    shift || true
    case "$APP_CLI_MODULE" in
      user_cli|migrate_cli|storage_cli|ai_cli) ;;
      *) die "모르는 제품 명령입니다: ${APP_CLI_MODULE:-<없음>}" 64 ;;
    esac
    [ -x "$APP_DIR/venv/bin/python" ] || die "설치된 제품을 찾을 수 없습니다($APP_DIR/venv)" 1
    APP_CLI_RC=0
    run_as_app "$APP_DIR/venv/bin/python" -m "app.cli.$APP_CLI_MODULE" "$@" || APP_CLI_RC=$?
    exit "$APP_CLI_RC" ;;
  -h|--help) usage; exit 0 ;;
  *) echo "모르는 서브커맨드: $SUBCOMMAND"; usage; exit 64 ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --dns-name) DNS_NAME="${2:-}"; shift 2 ;;
    --bind-ip) BIND_IP="${2:-}"; shift 2 ;;
    --upstream-proxy) UPSTREAM_PROXIES="${2:-}"; shift 2 ;;
    --source) SOURCE_KIND="${2:-}"; shift 2 ;;
    --git-remote) GIT_REMOTE="${2:-}"; shift 2 ;;
    --ref) GIT_REF="${2:-}"; shift 2 ;;
    --release) RELEASE_TAG="${2:-}"; shift 2 ;;
    --release-base) RELEASE_BASE="${2:-}"; shift 2 ;;
    --wheelhouse) WHEELHOUSE="${2:-}"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
    --with-ai) WITH_AI=1; shift ;;
    # 모델 디렉터리를 주는 것은 「AI 를 켠다」는 뜻이다. 둘을 따로 주게 하면 하나만
    # 준 설치가 «켰는데 모델이 없다»/«모델은 넣었는데 안 켜진다» 로 끝난다.
    --ai-model-dir) AI_MODEL_DIR="${2:-}"; WITH_AI=1; shift 2 ;;
    # 모델을 받는 것도 「AI 를 켠다」는 뜻이다. 위와 같은 이유로 함께 켠다.
    --download-model) DOWNLOAD_MODEL=1; WITH_AI=1; shift ;;
    --without-mail-relay) WITHOUT_MAIL_RELAY=1; shift ;;
    --mail-debs) MAIL_DEBS="${2:-}"; shift 2 ;;
    --inject-failure) INJECT_FAILURE="${2:-}"; shift 2 ;;
    --purge) PURGE=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    --target) ROLLBACK_TARGET="${2:-}"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    -*) echo "모르는 옵션: $1"; usage; exit 64 ;;
    *) [ -z "$ROLLBACK_TARGET" ] && ROLLBACK_TARGET="$1" || { echo "남는 인자: $1"; exit 64; }; shift ;;
  esac
done

[ "${EUID:-$(id -u)}" -eq 0 ] || die "root 권한이 필요합니다: sudo $SCRIPT_PATH $SUBCOMMAND …" 1
STARTED_AT="$(date -Is)"

# ═════════════════════════════════════════════════════════════════════════════
# Stage 0 — Preflight
# ═════════════════════════════════════════════════════════════════════════════
# **아무것도 바꾸기 전에** 멈출 수 있는 검사만 여기 둔다. 옛 installer 가 /opt 를 갈아엎은
# 뒤에야 테넌트 값을 확인해 「새 코드 + 옛 스키마」를 남긴 실패 모드를 구조적으로 없앤다.
PREFLIGHT_NOTES=""
note() { PREFLIGHT_NOTES="${PREFLIGHT_NOTES}${PREFLIGHT_NOTES:+ · }$1"; }

# 지원하는 OS 인가. 시험(tests/regression/test_installer_contract.py)이 이 함수만 떼어 22.04 와 24.04 로 부른다.
os_release_supported() {
  [ "${1:-}" = ubuntu ] && [ "${2:-}" = "24.04" ]
}

# --source 를 안 줬을 때의 소스 종류. 표준 출력 한 줄이 결과다.
#   --release 를 줬다                          → release
#   스크립트가 $APP_DIR 안에 있다(설치된 자리) → git 트리면 git, 아니면 manifest 가 기억하는 종류(없으면 local)
#   저장소 clone 이나 풀린 번들 안에 있다       → local
#   이 파일 하나만 받아 저장소 밖에서 돌렸다   → release
resolve_source_kind() {
  if [ -n "$RELEASE_TAG" ]; then echo release; return 0; fi
  if [ "$SRC_DIR" = "$APP_DIR" ]; then
    if [ -d "$APP_DIR/.git" ]; then echo git; return 0; fi
    local remembered; remembered="$(jq_get source_kind)"
    echo "${remembered:-local}"; return 0
  fi
  if [ -f "$SRC_DIR/requirements.txt" ]; then echo local; return 0; fi
  echo release
}

# Release 받기(계획 3.17, D-522). **확인이 끝나기 전에는 아무것도 풀지 않는다.**
#
# 묶음과 SHA256SUMS 를 임시 자리에 받고, 목록에서 그 묶음의 줄을 골라 sha256sum 으로 맞춰 본다. 목록에 그 줄이 없으면
# 확인한 것이 없으므로 실패다. 맞으면 임시 자리에 풀고 그 안의 제품 트리를 SRC_DIR 로 삼는다. $APP_DIR 는 Stage 3 에서야
# 바뀐다. 그래서 받다 끊겼거나 파일이 바뀐 Release 는 서버에 아무 흔적도 남기지 않는다.
fetch_release() {
  local tag="${RELEASE_TAG:-$RELEASE_TAG_DEFAULT}" base="${RELEASE_BASE:-$RELEASE_BASE_DEFAULT}"
  [ -n "$tag" ] || fail "어느 Release 를 설치할지 모릅니다" "--release v<버전> 을 주십시오(Release 페이지의 태그)" 16 || return $?
  case "$tag" in
    v[0-9]*) ;;
    *) fail "Release 태그 모양이 아닙니다: $tag" "v1.2.0 처럼 v 로 시작하는 태그를 주십시오" 16 || return $? ;;
  esac
  case "$tag" in
    *[!A-Za-z0-9._-]*) fail "Release 태그에 쓸 수 없는 글자가 있습니다: $tag" "v1.2.0 처럼 주십시오" 16 || return $? ;;
  esac
  local ver="${tag#v}" tarball dir
  tarball="$SLUG-$ver.tar.gz"
  dir="$(mktemp -d "/var/tmp/$SLUG-release.XXXXXX")"
  RELEASE_WORK_DIR="$dir"
  # 설치가 어디서 끝나든(성공, 실패, 중단) 임시 자리를 치운다. 풀린 트리는 Stage 3 이 이미 옮긴 뒤다.
  trap 'rm -rf "$RELEASE_WORK_DIR"' EXIT
  RELEASE_TAG="$tag"
  log "release $tag 받기: $base/$tag/"
  if ! curl -fsSL --retry 3 --proto '=https' -o "$dir/$tarball" "$base/$tag/$tarball" >>"$LOG" 2>&1 \
     || ! curl -fsSL --retry 3 --proto '=https' -o "$dir/SHA256SUMS" "$base/$tag/SHA256SUMS" >>"$LOG" 2>&1; then
    fail "Release 자산을 받을 수 없습니다($base/$tag)" \
      "태그가 있는지, 이 서버가 github.com 에 닿는지 확인하십시오. 폐쇄망이면 오프라인 번들(--source bundle)을 쓰십시오" 16 || return $?
  fi
  if ! verify_release_checksum "$dir" "$tarball"; then
    fail "받은 Release 묶음의 체크섬이 맞지 않습니다($tarball)" \
      "아무것도 풀지 않았습니다. 다시 받아 보고, 계속 틀리면 Release 페이지의 SHA256SUMS 와 비교하십시오" 16 || return $?
  fi
  mkdir -p "$dir/src"
  tar -xzf "$dir/$tarball" -C "$dir/src" --no-same-owner >>"$LOG" 2>&1 \
    || { fail "Release 묶음을 풀 수 없습니다" "$LOG 를 확인하십시오" 16 || return $?; }
  local root="$dir/src/$SLUG-$ver"
  [ -f "$root/requirements.txt" ] && [ -f "$root/deploy/install.sh" ] \
    || { fail "풀린 Release 에 제품 트리가 없습니다($SLUG-$ver/)" "Release 자산이 scripts/build-bundle.sh --release 로 만든 것인지 확인하십시오" 16 || return $?; }
  SRC_DIR="$root"
  note "Release $tag 를 받아 체크섬을 확인했습니다"
  return 0
}

# SHA256SUMS 에서 그 파일의 줄 하나만 골라 확인한다. 시험이 이 함수만 떼어 맞는 묶음과 바뀐 묶음으로 부른다.
verify_release_checksum() {
  local dir="$1" name="$2" line
  # 이름은 글자 그대로 비교한다(정규식으로 만들면 이름의 점이 아무 글자와 맞는다). 앞의 * 는 이진 모드 표시다.
  line="$(awk -v n="$name" 'length($1) == 64 && $1 ~ /^[0-9a-f]+$/ && ($2 == n || $2 == "*" n) { print; exit }' \
    "$dir/SHA256SUMS" 2>/dev/null)"
  [ -n "$line" ] || return 1
  ( cd "$dir" && printf '%s\n' "$line" | sha256sum -c --strict --status - )
}

stage_0_preflight() {
  local os_id os_ver arch mem_mb disk_mb

  os_id="$(. /etc/os-release 2>/dev/null && echo "${ID:-}")"
  os_ver="$(. /etc/os-release 2>/dev/null && echo "${VERSION_ID:-}")"
  [ "$os_id" = ubuntu ] || fail "지원하지 않는 OS 입니다(id=$os_id)" "Ubuntu Server 24.04 에서 실행하십시오" 10 || return $?
  # 24.04 만 받는다(계획 결정 6, D-522). 예전에는 다른 버전이면 알리기만 하고 계속했다. 그러면 python3.12-venv,
  # postgresql-16 같은 패키지 이름이 없는 버전에서 Stage 1 이 한참 뒤에 이해하기 어려운 apt 오류로 멈췄다.
  os_release_supported "$os_id" "$os_ver" \
    || fail "지원하지 않는 Ubuntu 버전입니다($os_ver)" "이 제품은 Ubuntu Server 24.04 만 지원합니다. 24.04 서버에서 실행하십시오" 10 || return $?

  arch="$(dpkg --print-architecture 2>/dev/null || uname -m)"
  case "$arch" in amd64|x86_64|arm64|aarch64) ;; *) fail "지원하지 않는 아키텍처: $arch" "amd64 또는 arm64 가 필요합니다" 10 || return $?;; esac

  mem_mb=$(( $(awk '/MemTotal/{print $2}' /proc/meminfo 2>/dev/null || echo 0) / 1024 ))
  [ "$mem_mb" -ge 1800 ] || fail "RAM 이 부족합니다(${mem_mb}MB)" "최소 2GB 가 필요합니다" 10 || return $?
  [ "$mem_mb" -ge 3800 ] || note "RAM ${mem_mb}MB — 임베딩·색인까지 올리면 부족할 수 있습니다"

  disk_mb=$(( $(df -Pk / | awk 'NR==2{print $4}') / 1024 ))
  [ "$disk_mb" -ge 5120 ] || fail "여유 디스크가 부족합니다(${disk_mb}MB)" "최소 5GB 를 확보하십시오" 10 || return $?

  case "$SUBCOMMAND" in
    install|upgrade|preflight|verify)
      [ -n "$DNS_NAME" ] || fail "--dns-name 이 없습니다" "설치처마다 다른 값이라 기본값이 없습니다: --dns-name clovirassist.example.internal" 11 || return $?
      [ -n "$BIND_IP" ] || fail "--bind-ip 가 없습니다" "nginx 가 묶일 주소를 주십시오: --bind-ip 10.0.0.10" 11 || return $?
      ;;
  esac
  if [ -n "$BIND_IP" ] && ! ip -o addr show 2>/dev/null | grep -qw "$BIND_IP"; then
    fail "--bind-ip $BIND_IP 가 이 서버의 주소가 아닙니다" "ip -o addr 로 실제 주소를 확인하십시오. nginx 는 없는 주소에 조용히 바인딩 실패합니다" 11 || return $?
  fi
  # 앞단 프록시 목록은 nginx 설정에 그대로 들어간다 — 주소가 아닌 글자나 「모든 주소」(/0)를
  # 받으면 누구나 X-Forwarded-For 로 자기 주소를 꾸며 속도 제한과 로그인 제한을 피한다.
  if [ -n "$UPSTREAM_PROXIES" ]; then
    local _proxy
    for _proxy in ${UPSTREAM_PROXIES//,/ }; do
      upstream_proxy_ok "$_proxy" || fail "--upstream-proxy 의 $_proxy 를 주소로 읽을 수 없습니다" \
        "IP 나 CIDR 을 쉼표로 이어 주십시오(예: 10.0.0.5,10.0.1.0/24). 모든 주소를 믿는 /0 은 받지 않습니다" 11 || return $?
    done
  fi
  # 이름이 안 풀려도 설치는 된다(설치처가 나중에 DNS 를 넣는 경우가 있다). 다만 **말은 한다** —
  # S3 이 죽은 이름을 들고 있던 APP_BASE_URL 로 알림 링크가 전부 깨져 있던 것을 찾았다.
  if [ -n "$DNS_NAME" ] && ! getent hosts "$DNS_NAME" >/dev/null 2>&1; then
    note "$DNS_NAME 이 이 서버에서 안 풀립니다 — 알림 메일·공유 링크가 열리지 않습니다"
  fi

  # 포트 충돌. 우리 유닛이 이미 물고 있는 것은 충돌이 아니다(재실행).
  local p
  for p in 80 443 "$APP_PORT"; do
    if ss -lntH "sport = :$p" 2>/dev/null | grep -q .; then
      local who; who="$(ss -lntpH "sport = :$p" 2>/dev/null | head -1)"
      case "$who" in
        *nginx*|*uvicorn*|*python*) note "포트 $p 는 이미 우리 스택이 쓰고 있습니다(재실행)" ;;
        *) fail "포트 $p 를 다른 프로세스가 쓰고 있습니다: $who" "그 서비스를 멈추거나 --bind-ip 를 바꾸십시오" 12 || return $? ;;
      esac
    fi
  done

  if ! timedatectl show -p NTPSynchronized --value 2>/dev/null | grep -q yes; then
    note "시간 동기가 확인되지 않습니다 — 인증서 만료 판정과 감사 로그 시각이 어긋날 수 있습니다"
  fi

  # 네트워크(또는 오프라인 모드). 폐쇄망에서 pip 이 몇 분 매달렸다가 죽는 것을 여기서 끊는다.
  if [ "$OFFLINE" = 1 ]; then
    [ -n "$WHEELHOUSE" ] && [ -d "$WHEELHOUSE" ] || \
      fail "--offline 인데 wheelhouse 가 없습니다" "--wheelhouse <dir> 로 오프라인 wheel 디렉터리를 주십시오" 13 || return $?
  else
    if ! timeout 8 getent hosts archive.ubuntu.com >/dev/null 2>&1; then
      note "apt 원본이 안 풀립니다 — 폐쇄망이면 --offline --wheelhouse 로 실행하십시오"
    fi
  fi

  # 기존 설치 감지. **가장 중요한 검사가 여기 있다.**
  if [ -f "$ENV_FILE" ]; then
    note "기존 설치를 감지했습니다($ENV_FILE) — 설정·비밀·데이터는 보존합니다"
    local missing="" key
    for key in DATABASE_URL SESSION_SECRET; do
      grep -qE "^${key}=.+" "$ENV_FILE" || missing="$missing $key"
    done
    [ -z "$missing" ] || fail "기존 설정에 필수 값이 없습니다:$missing" \
      "$ENV_FILE 을 고친 뒤 다시 실행하십시오. 이 상태로 진행하면 서비스는 뜨지만 전 화면이 실패합니다" 14 || return $?
  elif legacy_present; then
    note "옛 slug 설치($LEGACY_SLUG)를 감지했습니다 — 스냅샷 후 새 이름으로 이전합니다"
  fi

  # 소스 종류 결정(resolve_source_kind). 스크립트가 이미 $APP_DIR 안에 있으면 그 자리가 소스다(§1 의 3줄 경로).
  # 저장소 밖에서 이 파일 하나만 받아 실행했으면 Release 를 받는다.
  [ -n "$SOURCE_KIND" ] || SOURCE_KIND="$(resolve_source_kind)"
  case "$SOURCE_KIND" in
    git|bundle|local|release) ;;
    *) fail "모르는 --source: $SOURCE_KIND" "git, bundle, local, release 중 하나입니다" 15 || return $? ;;
  esac
  # Release 는 받아서 확인한 뒤 임시 자리에 푼다. 그 자리가 이번 설치의 소스다(Stage 3 이 그것을 $APP_DIR 로 옮긴다).
  # 설치된 Release 를 --release 없이 다시 돌리면 받을 것이 없다 - 지금 자리가 소스다.
  if [ "$SOURCE_KIND" = release ] && { [ -n "$RELEASE_TAG" ] || [ ! -f "$SRC_DIR/requirements.txt" ]; }; then
    fetch_release || return $?
  fi
  if [ "$SOURCE_KIND" = git ] && [ "$SRC_DIR" != "$APP_DIR" ] && [ -z "$GIT_REMOTE" ]; then
    fail "--source git 인데 원본을 모릅니다" "--git-remote <url> 을 주거나 $APP_DIR 에 clone 한 뒤 그 안의 install.sh 를 실행하십시오" 15 || return $?
  fi
  [ -f "$SRC_DIR/requirements.txt" ] || \
    fail "소스가 아닌 자리에서 실행됐습니다($SRC_DIR)" "저장소 clone 안의 deploy/install.sh 를 실행하십시오" 15 || return $?
  # 오프라인 번들은 전개하기 전에 번들이 든 목록(MANIFEST.sha256)으로 모든 파일을 확인한다(D-522). 예전 문서는 그렇게
  # 한다고 적었지만 설치는 목록을 읽지 않았다.
  if [ "$SOURCE_KIND" = bundle ]; then
    local bundle_root; bundle_root="$(cd "$SRC_DIR/.." && pwd)"
    [ -f "$bundle_root/MANIFEST.sha256" ] \
      || fail "번들에 MANIFEST.sha256 이 없습니다($bundle_root)" "scripts/build-bundle.sh 가 만든 번들을 그대로 푸십시오" 15 || return $?
    ( cd "$bundle_root" && sha256sum -c --quiet --strict MANIFEST.sha256 ) >>"$LOG" 2>&1 \
      || fail "번들 파일이 목록(MANIFEST.sha256)과 다릅니다" "번들이 깨졌거나 바뀌었습니다. 아무것도 전개하지 않았습니다. 번들을 다시 옮기십시오" 15 || return $?
    [ -n "$WHEELHOUSE" ] || WHEELHOUSE="$bundle_root/wheels"
    note "번들 파일을 목록과 맞춰 확인했습니다"
  fi
  # 오프라인 wheelhouse 는 x86_64 용으로 만든다(scripts/build-bundle.sh). 다른 아키텍처에서 그것으로 설치하면 Stage 4 가
  # 한참 뒤에 이해하기 어려운 pip 오류로 멈춘다.
  if [ -n "$WHEELHOUSE" ] && [ -d "$WHEELHOUSE" ]; then
    case "$arch" in
      arm64|aarch64)
        ls "$WHEELHOUSE" 2>/dev/null | grep -q 'aarch64' \
          || fail "wheelhouse 에 arm64 용 wheel 이 없습니다" "오프라인 번들은 x86_64 서버용입니다. x86_64 서버에 설치하거나 온라인으로 설치하십시오" 13 || return $? ;;
    esac
  fi
  # clone 을 설치 대상 안에 두면 rsync 가 자기 자신을 --delete 하며 덮어쓴다.
  case "$SRC_DIR" in
    "$APP_DIR"/*) fail "소스가 $APP_DIR 안에 있습니다($SRC_DIR)" "설치가 자기 자신을 덮어씁니다. 다른 곳에 두십시오" 15 || return $? ;;
  esac

  _reason="os=$os_ver arch=$arch ram=${mem_mb}MB disk=${disk_mb}MB source=$SOURCE_KIND${PREFLIGHT_NOTES:+ · $PREFLIGHT_NOTES}"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 1 — apt dependency
# ═════════════════════════════════════════════════════════════════════════════
BASE_PKGS=(ca-certificates rsync openssl curl git
           "postgresql-$PG_MAJOR" "postgresql-$PG_MAJOR-pgvector" postgresql-contrib
           nginx python3.12-venv nfs-common cifs-utils)


# ── ClovirAssist 로컬 릴레이 구성 요소 (D-551) ────────────────────────────────
#
# Postfix · OpenDKIM 은 **기본 설치 구성 요소**다. 설치 한 번이면 준비돼 있지만 사용자가 메일 화면에서 켜기 전에는 아무 메일
# 서비스도 돌지 않는다 — 설치 직후 두 서비스는 disabled · inactive 이고 25 · 2525 · 8891 을 아무도 듣지 않는다(어기면 이 Stage 가
# 실패한다). 켜고 끄기와 설정은 특권 헬퍼(`app/sysops/actions_mailrelay.py`)가 한다.
#
# 기존 메일 서버와 충돌하지 않는다:
#   · 다른 메일 발송 프로그램(`mail-transport-agent` 를 제공하는 exim4 · sendmail · opensmtpd …)이 있으면 깔지 않는다 —
#     apt 가 기존 MTA 를 지우는 일을 막는다.
#   · postfix 가 이미 있고 main.cf 에 제품 표지가 없으면 **기존 구성**이다. 지우지도, 덮지도, 끄지도 않는다.
#   · --without-mail-relay 는 꾸러미 설치까지 빼는 특수 설치 예외다.
# 오프라인 설치는 번들의 `debs/`(Packages.gz)를 임시 로컬 apt 원본으로 걸고 같은 명령으로 깐 뒤 원본을 지운다. 번들에 `debs/` 가
# 없으면(옛 번들) 경고하고 메일 구성 요소만 건너뛴다.
MAIL_RELAY_PKGS=(postfix opendkim libsasl2-modules)
MAIL_RELAY_MARKER='# managed-by: clovirassist'
MAIL_RELAY_NOTE=""

mail_relay_other_mta() {
  dpkg-query -W --showformat='${db:Status-Abbrev}|${Package}|${Provides}\n' 2>/dev/null \
    | awk -F'|' '$1 ~ /^ii/ && $2 != "postfix" && $3 ~ /mail-transport-agent/ {print $2}' | tr '\n' ' ' | sed 's/ $//'
}

mail_relay_managed() {
  [ -f /etc/postfix/main.cf ] && head -n1 /etc/postfix/main.cf | grep -qxF "$MAIL_RELAY_MARKER"
}

mail_relay_listeners() {
  ss -ltnH 2>/dev/null | awk '{print $4}' | grep -E ':(25|2525|8891)$' | tr '\n' ' ' | sed 's/ $//'
}

# 기본 꺼짐을 확인한다. 어기면 설치를 실패로 멈춘다(켜지 않은 메일 서비스가 돌고 있으면 안 된다).
mail_relay_assert_off() {
  local u state
  for u in postfix.service opendkim.service; do
    state="$(systemctl is-enabled "$u" 2>/dev/null || true)"
    case "$state" in enabled|enabled-runtime|static) fail "$u 가 켜져 있습니다($state)" "systemctl disable --now $u" 21 || return $? ;; esac
  done
  for u in postfix.service postfix@-.service opendkim.service; do
    if systemctl is-active --quiet "$u" 2>/dev/null; then
      fail "$u 가 돌고 있습니다" "systemctl disable --now $u" 21 || return $?
    fi
  done
  local heard; heard="$(mail_relay_listeners)"
  if [ -n "$heard" ]; then
    fail "메일 포트를 듣는 소켓이 있습니다: $heard" "ss -ltnp 로 어느 프로그램인지 확인하십시오" 21 || return $?
  fi
  return 0
}

install_mail_relay() {
  MAIL_RELAY_NOTE=""
  if [ "$WITHOUT_MAIL_RELAY" = 1 ]; then MAIL_RELAY_NOTE="메일 구성 요소를 빼고 설치했습니다(--without-mail-relay)"; return 0; fi
  local other; other="$(mail_relay_other_mta)"
  if [ -n "$other" ]; then
    MAIL_RELAY_NOTE="다른 메일 발송 프로그램($other)이 있어 메일 구성 요소를 깔지 않았습니다"
    return 0
  fi
  local need=() pkg
  for pkg in "${MAIL_RELAY_PKGS[@]}"; do dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg"); done
  if [ "${#need[@]}" -gt 0 ]; then
    if [ -f /etc/postfix/main.cf ] && ! mail_relay_managed; then
      MAIL_RELAY_NOTE="기존 메일 발송 구성이 있어 메일 구성 요소를 건드리지 않았습니다"
      return 0
    fi
    local src_list="" debs=""
    if [ "$OFFLINE" = 1 ]; then
      debs="${MAIL_DEBS:-}"
      [ -z "$debs" ] && [ -n "$WHEELHOUSE" ] && debs="$(dirname "$WHEELHOUSE")/debs"
      if [ -z "$debs" ] || [ ! -f "$debs/Packages.gz" ]; then
        log "주의: 오프라인 번들에 메일 구성 요소(.deb)가 없어 로컬 릴레이 구성 요소를 건너뜁니다(옛 번들)"
        MAIL_RELAY_NOTE="번들에 메일 구성 요소가 없어 건너뛰었습니다"
        return 0
      fi
      src_list="/etc/apt/sources.list.d/$SLUG-mail-local.list"
      printf 'deb [trusted=yes] file:%s ./\n' "$(cd "$debs" && pwd)" >"$src_list"
      apt-get update -qq -o Dir::Etc::sourcelist="$src_list" -o Dir::Etc::sourceparts=- \
        -o APT::Get::List-Cleanup=0 >>"$LOG" 2>&1 || true
    fi
    echo "postfix postfix/main_mailer_type select No configuration" | debconf-set-selections
    # 설치하는 동안 서비스가 잠깐도 뜨지 않게 한다. 이미 있는 policy-rc.d 는 건드리지 않고 mask 로 같은 효과를 낸 뒤 되돌린다.
    local guard=file rc=0
    if [ -e /usr/sbin/policy-rc.d ]; then
      guard=mask
      systemctl mask postfix.service opendkim.service >>"$LOG" 2>&1 || true
    else
      printf '#!/bin/sh\nexit 101\n' >/usr/sbin/policy-rc.d
      chmod 0755 /usr/sbin/policy-rc.d
    fi
    log "apt install(메일 구성 요소, 기본 꺼짐): ${need[*]}"
    DEBIAN_FRONTEND=noninteractive apt-get install -y --no-install-recommends "${need[@]}" >>"$LOG" 2>&1 || rc=$?
    if [ "$guard" = file ]; then rm -f /usr/sbin/policy-rc.d; else systemctl unmask postfix.service opendkim.service >>"$LOG" 2>&1 || true; fi
    if [ -n "$src_list" ]; then rm -f "$src_list"; apt-get update -qq >>"$LOG" 2>&1 || true; fi
    [ "$rc" -eq 0 ] || { fail "메일 구성 요소 설치 실패: ${need[*]}" "apt-get install ${need[*]} 로 원인을 보십시오" 21 || return $?; }
  fi
  if mail_relay_managed; then
    # 관리자가 메일 화면에서 켠 릴레이(업그레이드). 켜고 끄기는 관리자의 선택이라 그대로 둔다.
    MAIL_RELAY_NOTE="로컬 릴레이 설정을 그대로 두었습니다"
    return 0
  fi
  if [ -f /etc/postfix/main.cf ]; then
    MAIL_RELAY_NOTE="기존 메일 발송 구성이 있어 메일 구성 요소를 건드리지 않았습니다"
    return 0
  fi
  systemctl disable --now postfix.service >>"$LOG" 2>&1 || true
  systemctl stop postfix@-.service >>"$LOG" 2>&1 || true
  systemctl disable --now opendkim.service >>"$LOG" 2>&1 || true
  mail_relay_assert_off || return $?
  MAIL_RELAY_NOTE="메일 구성 요소 준비됨(꺼짐)"
  return 0
}

stage_1_apt() {
  local need=() pkg
  for pkg in "${BASE_PKGS[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
  done
  if [ "${#need[@]}" -eq 0 ]; then
    _reason="필요한 패키지 ${#BASE_PKGS[@]}개가 이미 있습니다"
  else
    if [ "$OFFLINE" = 1 ]; then
      fail "오프라인인데 없는 패키지가 있습니다: ${need[*]}" "설치 전에 이 패키지들을 미리 넣으십시오" 21 || return $?
    fi
    log "apt install: ${need[*]}"
    apt-get update -qq >>"$LOG" 2>&1 || true
    if ! apt-get install -y --no-install-recommends "${need[@]}" >>"$LOG" 2>&1; then
      fail "apt 설치 실패: ${need[*]}" "apt-get install ${need[*]} 를 직접 실행해 원인을 보십시오" 21 || return $?
    fi
    _reason="설치함: ${need[*]}"
  fi
  install_mail_relay || return $?
  [ -n "$MAIL_RELAY_NOTE" ] && _reason="$_reason · $MAIL_RELAY_NOTE"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 2 — 계정 · 디렉터리 (+ 옛 slug 이전)
# ═════════════════════════════════════════════════════════════════════════════
_merge_move() {
  # `$1` 아래의 모든 것을 `$2` 로 옮긴다. **같은 이름이 이미 있으면 그것만 건너뛰고**,
  # 디렉터리는 한 겹 더 들어가 같은 규칙을 다시 적용한다.
  local src="$1" dst="$2" f base
  mkdir -p "$dst"
  ( shopt -s dotglob nullglob
    for f in "$src"/*; do
      base="$(basename "$f")"
      if [ -d "$f" ] && [ -d "$dst/$base" ]; then
        _merge_move "$f" "$dst/$base"
        rmdir "$f" 2>/dev/null || true
      elif [ ! -e "$dst/$base" ]; then
        mv "$f" "$dst/"
      fi
    done )
}

migrate_legacy_paths() {
  legacy_present || return 0
  log "옛 slug 설치를 이전합니다($LEGACY_SLUG → $SLUG)"
  local u
  for u in "${LEGACY_UNITS[@]}"; do
    unit_exists "$u" || continue
    systemctl stop "$u" >>"$LOG" 2>&1 || true
    systemctl disable "$u" >>"$LOG" 2>&1 || true
    rm -f "/etc/systemd/system/$u"
    rm -rf "/etc/systemd/system/$u.d"
  done
  systemctl daemon-reload >>"$LOG" 2>&1 || true

  local src dst
  for pair in "/etc/$LEGACY_SLUG:$ETC_DIR" "/var/lib/$LEGACY_SLUG:$VAR_DIR" \
              "/var/backups/$LEGACY_SLUG:$BACKUP_ROOT" "/var/log/$LEGACY_SLUG:$LOG_ROOT"; do
    src="${pair%%:*}"; dst="${pair##*:}"
    [ -d "$src" ] || continue
    mkdir -p "$dst"
    # 이미 새 자리에 있는 파일은 덮지 않는다(재실행 안전). 다만 **디렉터리는 파고든다.**
    #
    # 🔴 예전에는 최상위 항목 하나만 보고 「있으면 건너뛴다」였다. 그래서 새 자리에
    # `secrets/` 가 이미 있으면(S8 이 SMB 자격증명을 거기 넣어 둔다) 옛 `secrets/` 가
    # **통째로 안 옮겨졌다** — 그 안의 Notion 토큰 넷이 옛 경로에 남고, 설치는 OK 를
    # 찍는다. 제품은 토큰이 없는 채로 뜨고, 그 사실은 첫 동기화가 실패할 때 처음 보인다.
    # 실제로 Cutover 첫 회차가 그 상태로 지나갔다 (S14).
    #
    # `cp -a --no-clobber` 뒤 원본을 지우는 대신 파일 단위로 옮기는 이유: 부분 실패 뒤
    # 원본이 남아 있어야 사람이 무엇이 안 옮겨졌는지 볼 수 있다.
    _merge_move "$src" "$dst"
    rmdir "$src" 2>/dev/null || true
  done
  # web.env → clovirassist.env. 안의 경로 값도 함께 옮긴다.
  if [ -f "$ETC_DIR/web.env" ] && [ ! -f "$ENV_FILE" ]; then
    mv "$ETC_DIR/web.env" "$ENV_FILE"
    sed -i "s#/etc/$LEGACY_SLUG#$ETC_DIR#g; s#/var/lib/$LEGACY_SLUG#$VAR_DIR#g" "$ENV_FILE"
  fi
  # 콘솔이 쓴 드롭인·표시자.
  local d
  for d in /etc/systemd/timesyncd.conf.d /etc/systemd/resolved.conf.d; do
    [ -f "$d/99-$LEGACY_PREFIX.conf" ] && mv -n "$d/99-$LEGACY_PREFIX.conf" "$d/99-$SLUG.conf" || true
  done
  rm -f "/etc/nginx/sites-enabled/$LEGACY_SLUG" "/etc/nginx/sites-available/$LEGACY_SLUG" \
        "/etc/logrotate.d/$LEGACY_SLUG"
  # 옛 소스 트리. 이전 직전에 뜬 스냅샷에 app.tar.gz 가 들어 있으므로 지워도 되돌릴 수 있다.
  rm -rf "/opt/$LEGACY_SLUG"
  rm -rf "/etc/ssl/$LEGACY_PREFIX"
  # 옛 시스템 계정. 파일 소유권은 아래에서 새 계정으로 바꾼다.
  id "$LEGACY_SVC_USER" >/dev/null 2>&1 && userdel "$LEGACY_SVC_USER" >>"$LOG" 2>&1 || true
  note_migrated=1
}

stage_2_accounts() {
  note_migrated=0
  migrate_legacy_paths

  if ! id "$SVC_USER" >/dev/null 2>&1; then
    useradd --system --shell /usr/sbin/nologin --no-create-home "$SVC_USER" \
      || { fail "시스템 계정 $SVC_USER 를 만들 수 없습니다" "useradd 출력을 확인하십시오" 22 || return $?; }
  fi

  install -d -o root -g root -m 0755 "$APP_DIR"
  install -d -o root -g "$SVC_USER" -m 0750 "$ETC_DIR"
  install -d -o root -g root -m 0755 "$TLS_DIR"
  install -d -o root -g "$SVC_USER" -m 0750 "$SECRETS_DIR"
  # 0750 root:서비스계정 — rollback 이 서비스 계정으로 pg_restore 를 돌린다(위 take_snapshot 주석).
  install -d -o root -g "$SVC_USER" -m 0750 "$BACKUP_ROOT"
  install -d -o root -g "$SVC_USER" -m 0750 "$LOG_ROOT"
  install -d -o root -g root -m 0750 "$SSL_FALLBACK_DIR"
  # uploads 는 app/core/uploads.py 가 첫 업로드 때도 만들지만, 상위 경로 소유자가 어긋나면
  # 소용없다(OPS-01: 이 디렉터리가 root:750 이라 첨부가 영구히 막혔던 사고). 매 실행마다
  # 형제들과 똑같이 소유권을 강제해 재발을 막는다.
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR" \
    "$VAR_DIR/exports" "$VAR_DIR/generated" "$VAR_DIR/temp" "$VAR_DIR/locks" "$VAR_DIR/uploads"
  chown -R "$SVC_USER":"$SVC_USER" "$VAR_DIR"
  chgrp -R "$SVC_USER" "$ETC_DIR" 2>/dev/null || true

  if [ "$note_migrated" = 1 ]; then
    _reason="옛 slug 설치를 $SLUG 로 이전하고 계정·디렉터리를 세웠습니다"
  else
    _reason="계정 $SVC_USER · 디렉터리 6종"
  fi
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 3 — Source 배치
# ═════════════════════════════════════════════════════════════════════════════
stage_3_source() {
  if [ "$SRC_DIR" = "$APP_DIR" ]; then
    # §1 의 3줄 경로 — clone 이 이미 제자리에 있다. ref 만 맞춘다.
    if [ -n "$GIT_REF" ] && [ -d "$APP_DIR/.git" ]; then
      git -C "$APP_DIR" fetch --tags --quiet >>"$LOG" 2>&1 || true
      git -C "$APP_DIR" checkout --quiet "$GIT_REF" >>"$LOG" 2>&1 \
        || { fail "ref 를 체크아웃할 수 없습니다: $GIT_REF" "tag 가 원격에 있는지 확인하십시오" 23 || return $?; }
    fi
    # 실행 비트는 여기서도 세운다. systemd 가 `ExecStartPre=` 로 **직접** 부르는
    # `wait-for-postgres.sh` 가 0644 면 조용히 안 돈다 — `-` 접두사 때문에 유닛은 그대로
    # 뜨고, 「PG 준비를 기다린다」가 아무 흔적 없이 사라진다. 딱 이 저장소가 싫어하는 종류다.
    chmod 0755 "$APP_DIR"/deploy/*.sh 2>/dev/null || true
    find "$APP_DIR/scripts" -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true
    _reason="소스가 이미 $APP_DIR 에 있습니다($(git -C "$APP_DIR" rev-parse --short HEAD 2>/dev/null || echo 'git 아님'))"
    return 0
  fi

  log "deploy source -> $APP_DIR"
  # --delete 는 트리를 깨끗이 유지하지만 **런타임 venv 는 반드시 보존**해야 한다
  # ($APP_DIR 안에 있고 소스에는 없다).
  rsync -a --delete \
    --exclude '.git' --exclude 'var' --exclude 'tests' --exclude '.venv' \
    --exclude 'venv' --exclude 'dist' --exclude 'node_modules' --exclude '.claude' \
    --exclude '.pytest_cache' --exclude 'docs' --exclude 'wheelhouse' --exclude '.github' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
    --exclude '*.bak' --exclude '*.bak-*' \
    "$SRC_DIR/" "$APP_DIR/" >>"$LOG" 2>&1 \
    || { fail "소스 복사에 실패했습니다" "$LOG 를 확인하십시오" 23 || return $?; }

  # 소스 트리만 정규화한다 — venv 는 건드리지 않는다(콘솔 스크립트의 실행 비트가 필요하다).
  find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -exec chown root:root {} +
  find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -type d -exec chmod 0755 {} +
  find "$APP_DIR" -path "$APP_DIR/venv" -prune -o -type f -exec chmod 0644 {} +
  find "$APP_DIR/scripts" -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true
  find "$APP_DIR/deploy" -name '*.sh' -exec chmod 0755 {} + 2>/dev/null || true
  _reason="$SRC_DIR → $APP_DIR (kind=$SOURCE_KIND)"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 4 — Python Runtime
# ═════════════════════════════════════════════════════════════════════════════
stage_4_python() {
  if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    python3 -m venv "$APP_DIR/venv" >>"$LOG" 2>&1 \
      || { fail "venv 를 만들 수 없습니다" "python3.12-venv 패키지를 확인하십시오" 24 || return $?; }
  fi
  local wheels="${WHEELHOUSE:-$APP_DIR/wheelhouse}"
  if [ -d "$wheels" ] && [ -n "$(ls -A "$wheels" 2>/dev/null)" ]; then
    log "pip install (offline wheelhouse: $wheels)"
    "$APP_DIR/venv/bin/pip" install --no-index --find-links "$wheels" --upgrade pip >>"$LOG" 2>&1 || true
    "$APP_DIR/venv/bin/pip" install --no-index --find-links "$wheels" -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1 \
      || { fail "오프라인 wheelhouse 로 의존성을 못 깔았습니다" "wheelhouse 에 requirements.txt 전부가 있는지 확인하십시오" 24 || return $?; }
  else
    [ "$OFFLINE" = 1 ] && { fail "--offline 인데 wheelhouse 가 비어 있습니다($wheels)" "wheel 을 미리 받아 두십시오" 24 || return $?; }
    log "pip install (online)"
    "$APP_DIR/venv/bin/pip" install --upgrade pip >>"$LOG" 2>&1 || true
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1 \
      || { fail "의존성 설치에 실패했습니다" "pypi.org·files.pythonhosted.org 도달 여부를 확인하십시오" 24 || return $?; }
  fi
  "$APP_DIR/venv/bin/python" -c \
    "import fastapi, sqlalchemy, alembic, httpx, argon2, pydantic_settings, cronsim, psycopg" >>"$LOG" 2>&1 \
    || { fail "설치된 의존성을 import 할 수 없습니다" "$LOG 의 traceback 을 확인하십시오" 24 || return $?; }
  _reason="venv + 의존성 import 확인"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 5 — Frontend Artifact
# ═════════════════════════════════════════════════════════════════════════════
# 커밋된 번들(app/static/react/)을 그대로 서빙한다. 소스만 새롭고 번들을 다시 안 만들면
# 이 서버는 **아무 오류 없이 옛 UI** 를 돈다 — 로그에도 화면에도 흔적이 없다.
stage_5_frontend() {
  [ -f "$APP_DIR/app/static/react/index.html" ] \
    || { fail "프런트 번들이 없습니다($APP_DIR/app/static/react)" "번들을 커밋했는지 확인하십시오" 25 || return $?; }
  if [ ! -f "$APP_DIR/scripts/check_bundle_fresh.py" ]; then
    skip "신선도 검사기가 없어 번들 나이를 판정하지 못했습니다" "scripts/check_bundle_fresh.py 를 배포에 포함하십시오" || return $?
  fi
  # 번들 신선도는 **frontend/ 소스가 함께 있을 때만** 판정할 수 있다. 배포본에는 frontend/ 가
  # 없으므로(rsync 제외 목록) 그때는 판정 근거 자체가 없다 — 있는 척하지 않는다.
  if [ ! -d "$APP_DIR/frontend/src" ]; then
    _reason="번들 존재 확인(배포본에 frontend/ 소스가 없어 신선도는 빌드 머신이 판정한다)"
    return 0
  fi
  if "$APP_DIR/venv/bin/python" "$APP_DIR/scripts/check_bundle_fresh.py" >>"$LOG" 2>&1; then
    _reason="번들이 소스와 맞습니다"
    return 0
  fi
  fail "프런트 번들이 소스보다 낡았습니다" \
    "빌드 머신에서: cd frontend && npm run build && python scripts/check_bundle_fresh.py --write 뒤 app/static/react/ 를 커밋하십시오" 25 || return $?
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 6 — PostgreSQL 설치 · 초기화
# ═════════════════════════════════════════════════════════════════════════════
stage_6_postgres() {
  systemctl enable --now postgresql >>"$LOG" 2>&1 || true
  local cluster_ok=0 i
  for i in $(seq 1 30); do
    if runuser -u postgres -- psql -tAc 'select 1' >/dev/null 2>&1; then cluster_ok=1; break; fi
    sleep 1
  done
  [ "$cluster_ok" = 1 ] || { fail "PostgreSQL 에 접속할 수 없습니다" "systemctl status postgresql 과 journalctl -u postgresql 을 보십시오" 26 || return $?; }

  # locale/encoding. UTF-8 이 아니면 한글 정렬·길이 판정이 어긋난다.
  local enc; enc="$(psql_super "select pg_encoding_to_char(encoding) from pg_database where datname='template1'")"
  [ "$enc" = "UTF8" ] || { fail "template1 인코딩이 UTF8 이 아닙니다($enc)" "UTF-8 로 initdb 된 cluster 가 필요합니다" 26 || return $?; }

  # role / DB. 재실행이면 만들지 않는다.
  if [ "$(psql_super "select count(*) from pg_roles where rolname='$PG_ROLE'")" = 0 ]; then
    psql_super "create role \"$PG_ROLE\" login" >>"$LOG" 2>&1 \
      || { fail "role $PG_ROLE 를 만들 수 없습니다" "psql 출력을 확인하십시오" 26 || return $?; }
  fi
  if [ "$(psql_super "select count(*) from pg_database where datname='$PG_DB'")" = 0 ]; then
    runuser -u postgres -- createdb -O "$PG_ROLE" -E UTF8 "$PG_DB" >>"$LOG" 2>&1 \
      || { fail "DB $PG_DB 를 만들 수 없습니다" "createdb 출력을 확인하십시오" 26 || return $?; }
  fi
  # 🔴 **CREATEDB 를 준다** (S14). 조건 밖에 두는 이유는 재실행에서도 붙어야 하기 때문이다.
  #
  # 이 권한이 없으면 백업이 「복원할 수 있다」를 **영원히 증명하지 못한다.** 복구 검증은
  # 임시 데이터베이스를 만들어 실제로 복원해 보는 방식이고(D-204 · D-273), 못 만들면
  # 제품이 정직하게 `structure_only` 로 멈춘다 — 그런데 그 상태는 오류가 아니라서
  # **백업은 매일 성공하고 검증만 조용히 안 된다.** Cutover 직후 첫 리허설이 정확히
  # 거기서 멈췄고, 그때까지 아무 로그도 그 사실을 말하지 않았다.
  #
  # 남의 데이터를 열어 주는 권한이 아니다. 자기 데이터베이스를 만들 수 있을 뿐이고,
  # 그것이 이 제품이 자기 백업을 스스로 검증하는 방식이다.
  psql_super "alter role \"$PG_ROLE\" createdb" >>"$LOG" 2>&1 \
    || { fail "role $PG_ROLE 에 createdb 를 줄 수 없습니다" \
             "이 권한이 없으면 백업 복원 검증이 영원히 structure_only 로 멈춥니다" 26 || return $?; }

  # 최소 권한 · 유닉스 소켓 peer 인증. 비밀번호를 env 파일에 두지 않기 위한 선택이다.
  local hba; hba="$(runuser -u postgres -- psql -tAc 'show hba_file')"
  if ! grep -qE "^local\s+$PG_DB\s+$PG_ROLE\s+peer" "$hba" 2>/dev/null; then
    sed -i "1i local   $PG_DB   $PG_ROLE   peer" "$hba"
    log "pg_hba: local $PG_DB $PG_ROLE peer 추가"
  fi
  # listen 은 로컬만. 앱·워커가 전부 같은 호스트에 있다.
  local conf; conf="$(runuser -u postgres -- psql -tAc 'show config_file')"
  if ! grep -qE "^listen_addresses\s*=\s*'localhost'" "$conf" 2>/dev/null; then
    sed -i "s/^#\?listen_addresses.*/listen_addresses = 'localhost'/" "$conf"
  fi
  # max_connections ≥ 워커수 ×(pool 5 + overflow 10). 부족하면 조용히 「느리다」로만 보인다.
  local maxconn; maxconn="$(runuser -u postgres -- psql -tAc 'show max_connections')"
  if [ "${maxconn:-0}" -lt "$PG_MIN_CONNECTIONS" ]; then
    sed -i "s/^#\?max_connections.*/max_connections = $PG_MIN_CONNECTIONS/" "$conf"
    log "max_connections $maxconn → $PG_MIN_CONNECTIONS"
    systemctl restart postgresql >>"$LOG" 2>&1 || true
    sleep 2
  fi
  systemctl reload postgresql >>"$LOG" 2>&1 || systemctl restart postgresql >>"$LOG" 2>&1 || true
  sleep 1

  # 서비스 계정으로 실제 접속해 본다. 여기까지 와야 「설치했다」고 말할 수 있다.
  runuser -u "$SVC_USER" -- psql -d "$PG_DB" -tAc 'select 1' >/dev/null 2>&1 \
    || { fail "$SVC_USER 계정으로 $PG_DB 에 접속할 수 없습니다" "pg_hba($hba) 의 peer 줄과 role 이름을 확인하십시오" 26 || return $?; }

  local ver; ver="$(psql_super 'show server_version')"
  _reason="PostgreSQL $ver · role=$PG_ROLE db=$PG_DB · max_connections=$(runuser -u postgres -- psql -tAc 'show max_connections')"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 7 — Extension
# ═════════════════════════════════════════════════════════════════════════════
stage_7_extensions() {
  local ext out
  for ext in vector pg_trgm; do
    if ! runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d "$PG_DB" -tAc "create extension if not exists $ext" >>"$LOG" 2>&1; then
      fail "extension $ext 를 만들 수 없습니다" \
        "$( [ "$ext" = vector ] && echo "postgresql-$PG_MAJOR-pgvector 패키지를 확인하십시오" || echo "postgresql-contrib 패키지를 확인하십시오" )" 27 || return $?
    fi
    # 🔴 **`template1` 에도 넣는다** (S14). 백업 복원 검증이 여기 걸려 있다.
    #
    # `pg_dump -Fc` 는 덤프 안에 `CREATE EXTENSION IF NOT EXISTS vector` 를 담는다. 복구
    # 검증은 그 덤프를 **서비스 계정이 만든 새 데이터베이스**에 되돌려 보는데, 확장 생성은
    # superuser 만 할 수 있어서 `pg_restore` 가 거기서 죽는다 — 즉 **이 설치의 백업은
    # 실제로 복원되지 않는다.** 백업 자체는 매일 성공하므로 그 사실은 아무 데도 안 보인다.
    #
    # 확장이 **이미 있으면** `IF NOT EXISTS` 는 권한 검사 전에 끝난다(NOTICE 만 남는다).
    # `template1` 에 넣어 두면 새로 만드는 모든 데이터베이스가 그 상태로 태어나므로,
    # 복원이 자기 권한만으로 지나간다. 실측으로 확인하고 넣었다.
    runuser -u postgres -- psql -v ON_ERROR_STOP=1 -d template1 \
      -tAc "create extension if not exists $ext" >>"$LOG" 2>&1 \
      || { fail "template1 에 extension $ext 를 넣을 수 없습니다" \
               "이것이 없으면 백업이 복원되지 않습니다(복구 검증이 pg_restore 에서 죽는다)" 27 \
           || return $?; }
  done
  out="$(runuser -u postgres -- psql -d "$PG_DB" -tAc \
    "select string_agg(extname||' '||extversion, ' · ' order by extname) from pg_extension where extname in ('vector','pg_trgm')")"
  _reason="$out"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 8 — Configuration / Secret 분리
# ═════════════════════════════════════════════════════════════════════════════
stage_8_config() {
  local created=0
  if [ ! -f "$ENV_FILE" ]; then
    local secret; secret="$(openssl rand -base64 48)"
    ( umask 077; sed "s#__GENERATED_ON_SERVER__#${secret}#" "$APP_DIR/deploy/$SLUG.env.example" >"$ENV_FILE" )
    unset secret
    created=1
  fi
  chown root:"$SVC_USER" "$ENV_FILE"; chmod 0640 "$ENV_FILE"

  # 설치처 값을 반영한다. 이 넷은 설치 인자에서 나오므로 **매 실행마다** 맞춘다 —
  # S3 이 죽은 이름을 든 APP_BASE_URL 로 알림 링크가 전부 깨져 있던 것을 찾았다.
  env_set APP_BASE_URL "https://$DNS_NAME"
  env_set TLS_CERT_PATH "$TLS_DIR/$DNS_NAME.crt"
  env_set PG_BIN_DIR "$PG_BIN_DIR"
  env_set CONFIG_DIR "$ETC_DIR"
  env_set SECRETS_DIR "$SECRETS_DIR"
  env_set DATA_DIR "$VAR_DIR"
  # DATABASE_URL 은 **기존 값을 존중한다.** 이미 PostgreSQL 을 가리키고 있으면 그 DB 를
  # 계속 쓴다 — 데이터가 거기 있고, 이름을 바꾸는 것은 이 스크립트의 일이 아니다.
  #
  # 🔴 **`sqlite://` 는 예외다** (S14). 옛 slug 설치를 이전하면 그 설치의 `web.env` 가
  # 그대로 넘어오는데, 거기 적힌 것은 SQLite 파일 경로다. 그 값을 존중하면 Stage 9 가
  # `alembic upgrade head` 에서 죽는다 — 제품이 PG 전용이라 `normalize_database_url` 이
  # 스킴을 보고 거절하기 때문이다(D-215). 실제로 Cutover 첫 회차가 거기서 멈췄다.
  #
  # 「존중」의 뜻은 **운영자가 정한 PostgreSQL 주소를 안 덮어쓴다**이지, 이 제품이 못 쓰는
  # 주소를 지킨다는 것이 아니다. SQLite 주소는 이전 전의 잔재이지 운영자의 선택이 아니다.
  _dburl="$(grep -E '^DATABASE_URL=' "$ENV_FILE" 2>/dev/null | head -1 | cut -d= -f2- | tr -d "'\"")"
  case "$_dburl" in
    sqlite*) _dburl="" ;;
  esac
  if [ "$created" = 1 ] || [ -z "$_dburl" ]; then
    env_set DATABASE_URL "postgresql://$PG_ROLE@/$PG_DB?host=/var/run/postgresql"
  fi

  # 🔴 걷어낸 런타임이 남긴 죽은 줄을 지운다 (S22 · §10-13).
  #
  # 설정 보존은 **운영자가 정한 값을 안 덮어쓴다**는 뜻이지, 이 제품이 더는 안 읽는 줄을
  # 영원히 들고 다닌다는 뜻이 아니다. 옛 slug 설치에서 넘어온 `web.env` 에는 S11 이 걷어낸
  # 런타임이 쓰던 두 줄이 그대로 남아 있었고, 그 값은 **옛 제품 이름**을 담고 있다.
  # 앱은 그 키를 한 번도 안 읽는다 — 확인은 `grep -ri <키> app/` 이고 지금 0건이다. 남겨
  # 두면 설정을 읽는 운영자가 「이 제품이 아직 그 엔진을 부른다」고 읽는다. 위 `DATABASE_URL`
  # 의 `sqlite://` 예외와 같은 종류다: 이전 전의 잔재이지 운영자의 선택이 아니다.
  #
  # **아는 이름만 지운다.** 「소스가 안 읽는 키를 전부 지운다」로 넓히면 아직 배선 안 된
  # 설치처 값이나 운영자가 손으로 적어 둔 것까지 함께 사라진다.
  #
  # 아래 목록에 그 엔진 이름이 글자로 남는 것은 **지우기 위해서**다 — 부르기 위해서가
  # 아니다. `test_installer_and_ops_scripts_have_no_n8n_trace` 가 같은 줄의 `S11` 표식으로
  # 그 둘을 구별한다(그 검사가 처음부터 그렇게 적혀 있다).
  # 옛 LLM 설정이 가리키던 API 키 파일을 AI 제공자 슬롯 이름으로 옮긴다(계획 3.16, D-517). 파일을 복사할 뿐 값을 읽거나
  # 출력하지 않는다. 새 슬롯에 이미 파일이 있으면 관리자가 화면에서 넣은 값이므로 건드리지 않는다.
  local legacy_ref
  legacy_ref="$(env_get LLM_API_SECRET_REF 2>/dev/null || true)"
  if [ -n "$legacy_ref" ] && [[ "$legacy_ref" =~ ^[A-Za-z0-9][A-Za-z0-9._-]{0,127}$ ]] \
     && [ -f "$SECRETS_DIR/$legacy_ref" ] && [ ! -f "$SECRETS_DIR/ai.anthropic.api_key" ]; then
    install -o root -g "$SVC_USER" -m 0640 "$SECRETS_DIR/$legacy_ref" "$SECRETS_DIR/ai.anthropic.api_key"
    log "옛 LLM_API_SECRET_REF 가 가리키던 키 파일을 ai.anthropic.api_key 로 옮겼습니다(값은 로그에 남기지 않습니다)"
  fi

  local dead tmp
  # A1 이 걷어낸 옛 LLM 실행기의 키들이다. AI 설정은 이제 관리 화면이 DB 에 둔다(D-517). 남겨 두면 설정을 읽는 사람이
  # 「이 값으로 AI 가 돈다」고 읽는다.
  for dead in LLM_ENABLED LLM_BACKEND LLM_MODEL LLM_EXECUTABLE LLM_CLI_PATH LLM_TIMEOUT_SECONDS \
              LLM_MAX_CONCURRENCY LLM_API_URL LLM_API_MODEL LLM_API_SECRET_REF; do
    grep -qE "^${dead}=" "$ENV_FILE" 2>/dev/null || continue
    tmp="$(mktemp)"
    grep -vE "^${dead}=" "$ENV_FILE" >"$tmp" && cat "$tmp" >"$ENV_FILE"
    rm -f "$tmp"
    log "걷어낸 LLM 실행기의 죽은 설정 줄을 지웠습니다: $dead"
  done
  for dead in N8N_WORK_ASSISTANT_URL N8N_TIMEOUT_SECONDS; do  # S11 이 걷어낸 엔진의 죽은 키
    grep -qE "^${dead}=" "$ENV_FILE" 2>/dev/null || continue
    tmp="$(mktemp)"
    grep -vE "^${dead}=" "$ENV_FILE" >"$tmp" && cat "$tmp" >"$ENV_FILE"
    rm -f "$tmp"
    log "걷어낸 런타임의 죽은 설정 줄을 지웠습니다: $dead"
  done

  ai_env_apply

  # 목록을 손으로 적지 않고 `config/` 에 실제로 있는 것을 전부 옮긴다.
  #
  # 손으로 적었을 때 실제로 이런 일이 났다: S11 이 `allowed-runners.json` 과
  # `allowed-workflows.json` 을 지웠는데 이 목록에는 남아 있어서 `cp` 가 매번 실패했다.
  # 그런데 `run_stage` 가 `set -e` 를 끄고 부르므로 **Stage 는 그대로 OK 를 찍었다** —
  # 없는 파일을 복사하려다 실패한 사실이 로그에만 남고 판정에는 안 잡혔다.
  #
  # 반대 방향도 있었다: S13 이 만든 `allowed-migration-sources.json` 은 목록에 없어서
  # 서버로 안 갔고, `AllowlistRegistry` 는 파일이 없으면 **전부 거절**이라 Cutover 회차의
  # Notion 호출이 전부 400 이 됐을 것이다. 그 400 은 설정 실수처럼 안 보인다.
  #
  # 허용 목록(`hosts` 가 있는 파일)은 **새 기본 호스트만** 더한다(deploy/merge_allowlist.py, D-522). 설치본을 덮지 않는
  # 규칙만 있으면 새 버전이 기본 목록에 더한 호스트(예: OpenAI)가 업그레이드한 서버에 영영 안 들어가고, 사람이 서버에서
  # 파일을 고쳐야 한다. 직전 기본 목록의 사본을 $ETC_DIR/defaults/ 에 남겨 운영자가 지운 기본 항목은 되살리지 않는다.
  local f added_line
  install -d -o root -g "$SVC_USER" -m 0750 "$ETC_DIR/defaults"
  for f in "$APP_DIR"/config/*.json; do
    [ -f "$f" ] || continue
    local base; base="$(basename "$f")"
    if [ ! -f "$ETC_DIR/$base" ]; then
      cp "$f" "$ETC_DIR/$base"
    fi
    if ! added_line="$("$APP_DIR/venv/bin/python" "$APP_DIR/deploy/merge_allowlist.py" \
        --default "$f" --installed "$ETC_DIR/$base" --record "$ETC_DIR/defaults/$base" 2>>"$LOG")"; then
      fail "허용 목록을 합치지 못했습니다($base)" "$LOG 를 보고 $ETC_DIR/$base 가 JSON 인지 확인하십시오" 28 || return $?
    fi
    if [ -n "$added_line" ]; then
      log "$base 에 새 기본 호스트를 더했습니다: $(echo "$added_line" | sed 's/^added //' | tr '\n' ' ')"
    fi
    chown root:"$SVC_USER" "$ETC_DIR/$base"; chmod 0640 "$ETC_DIR/$base"
    [ -f "$ETC_DIR/defaults/$base" ] && { chown root:"$SVC_USER" "$ETC_DIR/defaults/$base"; chmod 0640 "$ETC_DIR/defaults/$base"; }
  done
  # 🔴 **0750 이지 0700 이 아니다** (S14). 소유자는 root 이고 그룹이 서비스 계정이다 —
  # `0700` 이면 그룹에 아무 권한이 없어서 **제품이 자기 비밀을 못 읽는다.** 파일이 0640
  # 이어도 소용없다: 디렉터리를 통과(x)하지 못하면 그 안의 파일에 닿을 수가 없다.
  #
  # 실제로 그 상태로 설치가 `OK` 를 찍었고, 처음 드러난 자리는 Cutover 이관이 Notion
  # 토큰을 읽으려다 `PermissionError` 를 낸 것이었다. 「비밀을 못 읽는다」는 기동 때
  # 안 보인다 — 그 비밀을 실제로 쓰는 첫 요청까지 조용하다.
  #
  # `others` 는 여전히 아무것도 못 한다. 좁히려던 목적은 그대로다.
  chmod 0750 "$SECRETS_DIR"; chown root:"$SVC_USER" "$SECRETS_DIR"
  find "$SECRETS_DIR" -type f -exec chmod 0640 {} + 2>/dev/null || true
  find "$SECRETS_DIR" -type f -exec chown root:"$SVC_USER" {} + 2>/dev/null || true

  # 비밀은 로그에 한 글자도 안 나간다. 「몇 개 있다」까지만 말한다.
  local nsec; nsec="$(find "$SECRETS_DIR" -type f 2>/dev/null | wc -l | tr -d ' ')"
  if [ "$created" = 1 ]; then
    _reason="$ENV_FILE 을 새로 만들었습니다(SESSION_SECRET 은 서버에서 생성) · secrets $nsec개"
  else
    _reason="기존 설정을 보존하고 설치처 값만 맞췄습니다 · secrets $nsec개"
  fi
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 9 — DB Migration
# ═════════════════════════════════════════════════════════════════════════════

# 옛 메일 설정이 가리키던 비밀번호 파일 이름으로 옮겨도 되는가(D-545). `smtp` 로 시작하는 이름만 받는다 — 0042 전의
# `password_ref` 는 아무 비밀 이름이나 받았으므로, 누군가 미리 AI 키나 저장소 자격 이름을 심어 두었으면 이 복사가 그
# 비밀을 메일 비밀번호 칸으로 옮겨 막은 길을 다시 연다. 고정 칸 자기 자신과 경로 문자는 받지 않는다.
legacy_smtp_secret_name_ok() {
  [[ "${1:-}" =~ ^smtp[A-Za-z0-9._-]{0,123}$ ]] || return 1
  [ "$1" != "smtp.password" ] || return 1
  case "$1" in *..*) return 1 ;; esac
  return 0
}

# 0042 가 `password_ref` 를 걷기 **전에** 그 이름의 파일을 고정 칸 `smtp.password` 로 복사한다. 값을 읽거나 로그에
# 남기지 않는다. 고정 칸에 이미 파일이 있으면 관리자가 화면에서 넣은 값이므로 건드리지 않는다. 새 설치(표 없음)는
# 조회가 실패해 아무 일도 하지 않는다.
copy_legacy_smtp_secret() {
  local legacy
  legacy="$(runuser -u postgres -- psql -d "$PG_DB" -tAc \
    "select coalesce(value_json::jsonb->>'password_ref','') from app_settings where key='smtp'" 2>/dev/null | tr -d '[:space:]')" || return 0
  [ -n "$legacy" ] || return 0
  if ! legacy_smtp_secret_name_ok "$legacy"; then
    log "옛 메일 설정의 비밀번호 파일 이름은 옮기지 않습니다(smtp 로 시작하는 이름만 옮깁니다). 메일 화면에서 비밀번호를 다시 넣으십시오"
    return 0
  fi
  if [ -f "$SECRETS_DIR/$legacy" ] && [ ! -f "$SECRETS_DIR/smtp.password" ]; then
    install -o root -g "$SVC_USER" -m 0640 "$SECRETS_DIR/$legacy" "$SECRETS_DIR/smtp.password"
    log "옛 메일 설정이 가리키던 비밀번호 파일을 smtp.password 로 옮겼습니다(값은 로그에 남기지 않습니다)"
  fi
  return 0
}

stage_9_migration() {
  local before after head
  copy_legacy_smtp_secret
  before="$(alembic_current_db)"; head="$(alembic_head_code)"
  log "alembic: current=${before:-<없음>} target=${head:-<모름>}"
  say "  alembic revision: ${before:-<없음>} → ${head:-<모름>}"
  if ! run_as_app "$APP_DIR/venv/bin/alembic" -c "$APP_DIR/alembic.ini" upgrade head >>"$LOG" 2>&1; then
    fail "alembic upgrade head 가 실패했습니다(현재 revision=${before:-<없음>})" \
      "$LOG 의 traceback 을 보고, 필요하면 rollback 서브커맨드로 스냅샷을 되돌리십시오" 29 || return $?
  fi
  after="$(alembic_current_db)"
  [ -n "$after" ] || { fail "마이그레이션 뒤에도 revision 이 비어 있습니다" "alembic 이 실제로 붙었는지 확인하십시오" 29 || return $?; }
  if [ -n "$head" ] && [ "$after" != "$head" ]; then
    fail "DB revision($after)이 코드 head($head)와 다릅니다" "alembic history 로 갈라진 지점을 확인하십시오" 29 || return $?
  fi
  local ntab; ntab="$(runuser -u "$SVC_USER" -- psql -d "$PG_DB" -tAc \
    "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null || echo '?')"
  _reason="revision ${before:-<없음>} → $after · public 표 ${ntab}개"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 10 — Seed / 부트스트랩
# ═════════════════════════════════════════════════════════════════════════════
stage_10_seed() {
  # 통합·워크플로 discovery. 실패해도 설치를 막지 않는다(외부 연동이 없는 설치가 있다).
  run_as_app "$APP_DIR/venv/bin/python" -m app.integrations.discovery >>"$LOG" 2>&1 \
    || log "discovery import 가 실패했습니다(연동 없는 설치에서는 정상)"

  local nusers
  nusers="$(runuser -u "$SVC_USER" -- psql -d "$PG_DB" -tAc 'select count(*) from users' 2>/dev/null || echo 0)"
  if [ "${nusers:-0}" -eq 0 ]; then
    # 🔴 관리자 계정을 여기서 만들지 않는다(D-522). 계정을 만들면 비밀번호를 누군가 정해야 하고, 그 값이 설치 콘솔이나
    # 로그에 남는다. 대신 일회용 설정 코드를 만든다. 서버에는 해시만 남고, 원문은 모든 Stage 가 끝난 뒤 콘솔에만 한 번
    # 나온다(print_first_admin_code). 사람은 브라우저의 /setup/first-admin 에서 자기 비밀번호로 계정을 만든다.
    local out
    if ! out="$(run_as_app "$APP_DIR/venv/bin/python" -m app.cli.user_cli first-admin-code 2>>"$LOG")"; then
      fail "첫 관리자 설정 코드를 만들지 못했습니다" "$LOG 의 traceback 을 보십시오" 30 || return $?
    fi
    FIRST_ADMIN_CODE="$(printf '%s\n' "$out" | sed -n 's/^code=//p' | head -1)"
    FIRST_ADMIN_EXPIRES="$(printf '%s\n' "$out" | sed -n 's/^expires_at=//p' | head -1)"
    unset out
    [ -n "$FIRST_ADMIN_CODE" ] || { fail "첫 관리자 설정 코드가 비어 있습니다" "$LOG 를 보십시오" 30 || return $?; }
    _reason="아직 계정이 없습니다. 설치가 끝나면 첫 관리자 설정 코드를 보여 드립니다"
  else
    _reason="사용자 ${nusers}명, 기본 Role/Permission 확인"
  fi
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 11 — File Storage 준비
# ═════════════════════════════════════════════════════════════════════════════
stage_11_storage() {
  # 옛 미러(게시판·채팅·티켓·프로필)가 쓰는 로컬 업로드 뿌리. S14 까지 남는다.
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR/uploads"
  runuser -u "$SVC_USER" -- test -w "$VAR_DIR/uploads" \
    || { fail "$VAR_DIR/uploads 에 서비스 계정이 쓸 수 없습니다" "소유권을 $SVC_USER 로 맞추십시오(OPS-01)" 31 || return $?; }
  # 새 Storage 뿌리(S8). 기본 LOCAL Provider 가 이 경로를 가리킨다.
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR/files"

  # 기본 저장소를 세운다. **경로 판정을 셸에서 다시 하지 않는다** — `stat` 으로 장치
  # 번호를 비교하는 순간 판정이 두 벌이 되고, 그 둘은 언젠가 갈린다(D-199 13번).
  run_as_app "$APP_DIR/venv/bin/python" -m app.cli.storage_cli bootstrap >>"$LOG" 2>&1 \
    || { fail "기본 저장소를 세우지 못했습니다" "$LOG 의 traceback 을 보십시오" 31 || return $?; }

  # 마운트 유닛과 RequiresMountsFor drop-in. 켜진 NFS/SMB Provider 가 없으면 유닛은
  # 0개이고 drop-in 은 빈 지시자 한 줄이 된다(옛 경로를 기다리는 상태를 지운다).
  local staged; staged="$(mktemp -d)"
  # 🔴 `mktemp -d` 는 **root 소유 0700** 이다. 그 안에 파일을 쓰는 것은 이 셸이 아니라
  # `run_as_app` 으로 띄운 **서비스 계정**이라, 소유를 안 넘기면 `PermissionError` 로
  # 죽는다 — Stage 11 이 그 자리에서 설치를 통째로 세운다.
  #
  # S8 이 이 결함을 못 본 이유는 정직하게 적어 둔다: Storage 를 **호스트에서** 검증했고
  # 그때는 root 로 CLI 를 불렀다. Clean 설치 경로(서비스 계정으로 부른다)는 S9 의 LXD
  # 리허설이 처음 지났고, 첫 통과에서 바로 걸렸다.
  chown "$SVC_USER":"$SVC_USER" "$staged"
  if ! run_as_app "$APP_DIR/venv/bin/python" -m app.cli.storage_cli units --out "$staged" >>"$LOG" 2>&1; then
    rm -rf "$staged"
    fail "마운트 유닛을 만들지 못했습니다" "저장소의 마운트 소스(source)가 비어 있는지 확인하십시오" 31 || return $?
  fi
  local nmount=0 f base
  for f in "$staged"/*.mount; do
    [ -e "$f" ] || break
    base="$(basename "$f")"
    install -o root -g root -m 0644 "$f" "/etc/systemd/system/$base"
    nmount=$((nmount + 1))
  done
  # drop-in 은 유닛 넷 전부에 같은 내용으로 얹는다. 웹만 기다리게 하면 워커가 마운트
  # 전에 떠서 같은 사고를 낸다.
  local u
  for u in "${ALL_UNITS[@]}"; do
    install -d -o root -g root -m 0755 "/etc/systemd/system/$u.d"
    install -o root -g root -m 0644 "$staged/10-storage-mounts.conf" "/etc/systemd/system/$u.d/10-storage-mounts.conf"
  done
  rm -rf "$staged"
  systemctl daemon-reload
  local mu
  for mu in $(ls /etc/systemd/system/*.mount 2>/dev/null); do
    base="$(basename "$mu")"
    grep -q "ClovirAssist" "$mu" 2>/dev/null || continue
    systemctl enable "$base" >>"$LOG" 2>&1 || log "mount enable 실패: $base"
    systemctl start "$base" >>"$LOG" 2>&1 || log "mount start 실패: $base"
  done

  # 마지막으로 **제품 코드가** 지금 쓸 수 있는지 판정한다. 종료코드가 계약이다.
  local status_out; status_out="$(mktemp)"
  if run_as_app "$APP_DIR/venv/bin/python" -m app.cli.storage_cli status >"$status_out" 2>>"$LOG"; then
    _reason="저장소 준비 완료 · 마운트 유닛 ${nmount}개 · drop-in ${#ALL_UNITS[@]}유닛"
    rm -f "$status_out"
    return 0
  fi
  cat "$status_out" >>"$LOG" 2>/dev/null || true
  rm -f "$status_out"
  fail "저장소가 지금 **쓰기를 거부하는 상태**입니다(마운트 미확인)" \
    "systemctl start <마운트 유닛> 으로 붙인 뒤 다시 실행하십시오. 상태: $APP_DIR/venv/bin/python -m app.cli.storage_cli status" 31 \
    || return $?
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 12 — AI Component
# ═════════════════════════════════════════════════════════════════════════════
# AI 설정 두 줄을 env 에 반영한다. Stage 8 과 `ai` 서브커맨드가 **같은 함수**를 부른다 —
# 두 자리에 각자 적으면 한쪽만 고치는 날이 오고, 그때 「모델은 넣었는데 안 켜진다」가 된다.
#
# 기존 값을 존중하지 않는 것이 의도다: `--with-ai` 없이 다시 설치하는 것은 「AI 를 끄고
# 설치한다」는 뜻이고, 그때 env 에 옛 `AI_ENABLED=true` 가 남아 있으면 모델도 런타임도
# 없이 켜진 상태가 된다.
ai_env_apply() {
  if [ "$WITH_AI" = 1 ]; then
    env_set AI_ENABLED "true"
    env_set AI_MODEL_ROOT "$VAR_DIR/ai/models"
  else
    env_set AI_ENABLED "false"
  fi
}

# 카탈로그가 정한 모델 파일을 받는다. 파일마다 크기와 sha256 을 맞춰 보고, 하나라도 틀리면 실패다.
# 계획표 한 줄은 `<주소> <sha256> <크기> <상대 경로>` 다(app/cli/ai_cli.py::cmd_download_plan).
download_model_files() {
  local target="$1" plan url sum size rel
  plan="$(run_as_app "$APP_DIR/venv/bin/python" -m app.cli.ai_cli download-plan 2>>"$LOG")" || return 1
  [ -n "$plan" ] || return 1
  while read -r url sum size rel; do
    [ -n "$rel" ] || continue
    case "$rel" in /*|*..*) log "모델 계획의 경로가 이상합니다: $rel"; return 1 ;; esac
    mkdir -p "$target/$(dirname "$rel")"
    log "모델 파일 받기: $rel (${size}바이트)"
    curl -fsSL --retry 3 --proto '=https' -o "$target/$rel" "$url" >>"$LOG" 2>&1 || { log "받기 실패: $rel"; return 1; }
    [ "$(stat -c %s "$target/$rel")" = "$size" ] || { log "크기가 다릅니다: $rel"; return 1; }
    echo "$sum  $target/$rel" | sha256sum -c --strict --status - || { log "체크섬이 다릅니다: $rel"; return 1; }
  done <<<"$plan"
  return 0
}

stage_12_ai() {
  # 모델 캐시 뿌리. **`storage_providers` 와 별개다** — 모델은 사용자 데이터가 아니라
  # 재생성 가능한 자산이고 백업 대상이 아니다(D-203 · D-204). 저장소 표에 안 넣는다.
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR/ai"
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR/ai/models"

  # AI 를 끄고 설치하는 것은 **정상 선택**이다. 그때는 런타임도 모델도 안 깐다.
  if [ "$WITH_AI" != 1 ]; then
    _reason="AI 를 끄고 설치했습니다(--with-ai 로 켭니다) · 모델 캐시 자리만 만들었습니다"
    return 0
  fi

  # ① 임베딩 런타임. 기본 의존과 따로 두는 이유는 requirements-ai.txt 머리말에 있다.
  local wheels="${WHEELHOUSE:-$APP_DIR/wheelhouse}"
  if [ -d "$wheels" ] && [ -n "$(ls -A "$wheels" 2>/dev/null)" ]; then
    "$APP_DIR/venv/bin/pip" install --no-index --find-links "$wheels" -r "$APP_DIR/requirements-ai.txt" >>"$LOG" 2>&1 \
      || { fail "오프라인 wheelhouse 로 AI 런타임을 못 깔았습니다" \
           "wheelhouse 에 requirements-ai.txt 전부가 있는지 확인하십시오" 32 || return $?; }
  else
    [ "$OFFLINE" = 1 ] && { fail "--offline 인데 wheelhouse 가 비어 있습니다($wheels)" \
      "AI wheel 을 미리 받아 두십시오" 32 || return $?; }
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements-ai.txt" >>"$LOG" 2>&1 \
      || { fail "AI 런타임 설치에 실패했습니다" "pypi.org 도달 여부를 확인하십시오" 32 || return $?; }
  fi

  # ② 모델 파일. 기본은 **네트워크로 받지 않는다** — 폐쇄망이 기본 전제다(D-205). 오프라인 번들이나 --ai-model-dir
  # 로 들어오고, 이미 캐시에 있으면 그대로 쓴다.
  #
  # --download-model 을 주면 설치가 받는다(계획 3.16, D-522). 받는 것은 이 셸이고 제품은 받지 않는다 - 제품의 바깥
  # 허용 목록에 모델 호스트를 넣지 않기 위해서다. 주소, revision, 파일마다의 sha256 은 제품 카탈로그가 정하고
  # (ai_cli download-plan), 받은 파일은 install-model --verify 가 그 값과 맞춰 본 뒤에야 캐시에 놓인다.
  local source="" fetched=""
  if [ -n "$AI_MODEL_DIR" ]; then source="$AI_MODEL_DIR"
  elif [ -d "$APP_DIR/ai-models" ]; then source="$APP_DIR/ai-models"
  elif [ "$DOWNLOAD_MODEL" = 1 ]; then
    fetched="$(mktemp -d "/var/tmp/$SLUG-model.XXXXXX")"
    if ! download_model_files "$fetched"; then
      rm -rf "$fetched"
      fail "임베딩 모델을 받지 못했습니다" \
        "$LOG 에 어느 파일에서 멈췄는지 적혀 있습니다. 이 서버가 huggingface.co 에 닿는지 확인하거나, 받아 둔 파일을 --ai-model-dir 로 주십시오" 32 || return $?
    fi
    chown -R "$SVC_USER":"$SVC_USER" "$fetched"
    source="$fetched"
  fi
  if [ -n "$source" ]; then
    local verify_flag=""
    [ -n "$fetched" ] && verify_flag="--verify"
    if ! run_as_app "$APP_DIR/venv/bin/python" -m app.cli.ai_cli install-model --from "$source" $verify_flag >>"$LOG" 2>&1; then
      [ -n "$fetched" ] && rm -rf "$fetched"
      fail "모델 파일을 캐시 자리에 놓지 못했습니다(원본: $source)" \
        "$LOG 에 어느 파일이 없거나 체크섬이 틀렸는지 적혀 있습니다. 그 파일들을 갖춘 뒤 다시 실행하십시오" 32 || return $?
    fi
    [ -n "$fetched" ] && rm -rf "$fetched"
  fi

  # ③ **제품 코드가** 지금 쓸 수 있는지 판정한다. 종료코드가 계약이다 — 셸이 모델
  # 디렉터리에 ls 를 걸어 다시 판정하지 않는다(Stage 11 과 같은 규율).
  local out; out="$(mktemp)"
  if ! run_as_app "$APP_DIR/venv/bin/python" -m app.cli.ai_cli status >"$out" 2>>"$LOG"; then
    cat "$out" >>"$LOG" 2>/dev/null || true; rm -f "$out"
    fail "AI 를 켜고 설치했는데 임베딩을 쓸 수 없는 상태입니다" \
      "--download-model 로 모델을 받게 하거나 모델 파일을 --ai-model-dir <디렉터리> 로 주고 다시 실행하십시오. 상태: sudo clovirassist ai-cli status" 32 \
      || return $?
  fi
  rm -f "$out"
  # ④ **있다 ≠ 된다.** 받다 만 model.onnx 는 크기도 있고 이름도 맞는데 세션을 만들다
  # 죽는다. 실제로 벡터를 하나 만들어 보고 그것이 길이 1 인지까지 본다.
  if ! run_as_app "$APP_DIR/venv/bin/python" -m app.cli.ai_cli selftest >>"$LOG" 2>&1; then
    fail "모델 파일은 있는데 실제로 벡터를 만들지 못했습니다" \
      "$LOG 의 traceback 을 보십시오. 모델 파일이 온전한지(받다 말지 않았는지) 확인하십시오" 32 \
      || return $?
  fi
  _reason="AI 런타임 + 모델 로드 검증 통과"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 13 — systemd unit 생성 / 설치
# ═════════════════════════════════════════════════════════════════════════════
stage_13_units() {
  local u
  for u in "${ALL_UNITS[@]}"; do
    [ -f "$APP_DIR/deploy/systemd/$u" ] \
      || { fail "유닛 파일이 배포본에 없습니다: deploy/systemd/$u" "저장소에 그 파일이 있는지 확인하십시오" 33 || return $?; }
    install -o root -g root -m 0644 "$APP_DIR/deploy/systemd/$u" "/etc/systemd/system/$u"
  done
  # 바깥 프록시(계획 2.10). 시스템 설정 화면이 웹 유닛에 둔 프록시 드롭인이 있으면, 그 드롭인이 없는 나머지 바깥 호출
  # 유닛에도 같은 파일을 둔다. 새 버전이 드롭인 대상 유닛을 늘렸을 때(대화형 워커) 업그레이드만으로 맞춰진다.
  # 사람이 유닛마다 다르게 둔 드롭인은 건드리지 않는다 - 없는 곳에만 복사한다.
  local proxy_name="99-$SLUG-proxy.conf" proxy_unit
  if [ -f "/etc/systemd/system/$WEB_UNIT.d/$proxy_name" ]; then
    for proxy_unit in "$WORKER_UNIT" "$WORKER_CONV_UNIT" "$SCHEDULER_UNIT"; do
      if [ ! -f "/etc/systemd/system/$proxy_unit.d/$proxy_name" ]; then
        install -d -o root -g root -m 0755 "/etc/systemd/system/$proxy_unit.d"
        install -o root -g root -m 0644 "/etc/systemd/system/$WEB_UNIT.d/$proxy_name" \
          "/etc/systemd/system/$proxy_unit.d/$proxy_name"
        log "프록시 드롭인을 $proxy_unit 에도 두었습니다"
      fi
    done
  fi
  # 색인 레인 유닛은 S9 이 넣었고 위 루프가 그것을 깐다(ALL_UNITS 에 있다). 이 가드는
  # 남겨 둔다 — 유닛을 지우면서 레인은 남기는 실수를 잡는 자리이고, 그 상태의 증상은
  # 「색인이 안 되는데 아무 오류도 없다」뿐이다.
  if grep -q 'LANE_INDEX' "$APP_DIR/app/jobs/lanes.py" 2>/dev/null && [ ! -f "$APP_DIR/deploy/systemd/$INDEX_UNIT" ]; then
    fail "색인 레인이 소스에 있는데 systemd 유닛이 없습니다" \
      "deploy/systemd/$INDEX_UNIT 를 추가하고 ALL_UNITS 에 넣으십시오" 33 || return $?
  fi
  systemctl daemon-reload
  for u in "${ALL_UNITS[@]}"; do
    systemd-analyze verify "/etc/systemd/system/$u" >>"$LOG" 2>&1 || log "systemd-analyze verify 경고: $u"
  done
  # 설치 뒤의 운영 명령(D-522). 설치본 안의 파일을 그대로 깐다 - 업그레이드가 설치본을 바꾸면 명령도 함께 바뀐다.
  [ -f "$APP_DIR/deploy/clovirassist-cli.sh" ] \
    || { fail "운영 명령 파일이 배포본에 없습니다: deploy/clovirassist-cli.sh" "저장소에 그 파일이 있는지 확인하십시오" 33 || return $?; }
  install -o root -g root -m 0755 "$APP_DIR/deploy/clovirassist-cli.sh" "$CLI_BIN"
  _reason="유닛 ${#ALL_UNITS[@]}종 설치, $CLI_BIN 명령 설치"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 14 — enable + 의존 순서
# ═════════════════════════════════════════════════════════════════════════════
stage_14_enable() {
  systemctl enable postgresql >>"$LOG" 2>&1 || true
  systemctl enable nginx >>"$LOG" 2>&1 || true
  local u
  for u in "${ALL_UNITS[@]}"; do
    systemctl enable "$u" >>"$LOG" 2>&1 \
      || { fail "$u 를 enable 할 수 없습니다" "systemctl status $u 를 보십시오" 34 || return $?; }
  done
  # 재부팅 후 **수동 명령 0회** 복구가 이 Stage 의 존재 이유다. enabled 가 아닌 유닛이
  # 하나라도 있으면 그 사실이 재부팅 전에 드러나야 한다.
  local notenabled=""
  for u in postgresql nginx "${ALL_UNITS[@]}"; do
    systemctl is-enabled --quiet "$u" 2>/dev/null || notenabled="$notenabled $u"
  done
  [ -z "$notenabled" ] || { fail "enable 되지 않은 유닛이 있습니다:$notenabled" "systemctl enable 을 직접 실행해 원인을 보십시오" 34 || return $?; }
  _reason="postgresql · nginx · 제품 유닛 ${#ALL_UNITS[@]}종이 enabled"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 15 — TLS (nginx 보다 **먼저**)
# ═════════════════════════════════════════════════════════════════════════════
stage_15_tls() {
  local crt="$TLS_DIR/$DNS_NAME.crt" key="$TLS_DIR/$DNS_NAME.key"
  if [ -f "$crt" ] && [ -f "$key" ]; then
    # 이름이 어긋난 인증서를 그대로 두면 브라우저가 막는다. **있다** 가 아니라 **맞다** 를 본다.
    if ! openssl x509 -in "$crt" -noout -ext subjectAltName 2>/dev/null | grep -q "DNS:$DNS_NAME"; then
      fail "기존 인증서의 SAN 에 $DNS_NAME 이 없습니다($crt)" \
        "그 파일을 치우고 다시 실행하면 자체서명으로 새로 만듭니다" 36 || return $?
    fi
    _reason="기존 인증서 사용 · 만료 $(openssl x509 -in "$crt" -noout -enddate | sed 's/notAfter=//')"
  else
    # S3 이 서버를 고칠 때 쓴 것과 **같은 openssl 호출**이다. 설치처와 저장소가 어긋나지
    # 않게 이 모양을 유지한다.
    openssl req -x509 -newkey ec -pkeyopt ec_paramgen_curve:P-256 \
      -keyout "$key" -out "$crt" -days 365 -nodes \
      -subj "/CN=$DNS_NAME" \
      -addext "subjectAltName=DNS:$DNS_NAME,IP:$BIND_IP" >>"$LOG" 2>&1 \
      || { fail "자체서명 인증서를 만들 수 없습니다" "openssl 출력을 확인하십시오" 36 || return $?; }
    _reason="자체서명 ECDSA P-256 생성(CN/SAN=$DNS_NAME, IP:$BIND_IP, 365일)"
  fi
  chmod 0600 "$key"; chmod 0644 "$crt"; chown root:root "$key" "$crt"
  env_set TLS_CERT_PATH "$crt"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 16 — nginx
# **순서가 사양(INSTALLATION.md §5 초안)과 반대다.** 그 표는 15=nginx, 16=TLS 로 적혀 있었는데
# 그 순서로는 **돌아갈 수가 없다**: `nginx -t` 는 `ssl_certificate` 파일이 없으면
# `cannot load certificate … BIO_new_file() failed` 로 죽는다. LXD 리허설이 정확히 그렇게
# 멈췄고, 사양을 실제와 맞게 정정했다(CLAUDE.md 머리말 — 문서와 Runtime 이 충돌하면 실제를 따른다).
# ═════════════════════════════════════════════════════════════════════════════
# 앞단 프록시 한 칸이 주소로 읽히는가(IPv4 · IPv6 · CIDR). 접두 길이 0 은 「모든 주소를 믿는다」라 거절한다.
upstream_proxy_ok() {
  local p="$1" addr prefix="" octet
  case "$p" in
    */*)
      addr="${p%/*}"; prefix="${p#*/}"
      case "$prefix" in ''|*[!0-9]*) return 1 ;; esac
      [ "$prefix" -ge 1 ] || return 1
      ;;
    *) addr="$p" ;;
  esac
  case "$addr" in
    *:*)
      printf '%s' "$addr" | grep -Eq '^[0-9A-Fa-f:]+$' || return 1
      [ -z "$prefix" ] || [ "$prefix" -le 128 ] || return 1
      ;;
    *)
      printf '%s' "$addr" | grep -Eq '^([0-9]{1,3}\.){3}[0-9]{1,3}$' || return 1
      for octet in ${addr//./ }; do [ "$octet" -le 255 ] || return 1; done
      [ -z "$prefix" ] || [ "$prefix" -le 32 ] || return 1
      ;;
  esac
  return 0
}

# install · upgrade 가 앞단 프록시 목록을 정한다 — 주지 않았으면 manifest 가 기억한 값이고,
# `none` 은 기억한 값을 지운다. 재실행이 조용히 목록을 비우면 그날부터 다시 모두가 한 예산이다.
resolve_upstream_proxies() {
  [ -n "$UPSTREAM_PROXIES" ] || UPSTREAM_PROXIES="$(jq_get upstream_proxies)"
  [ "$UPSTREAM_PROXIES" = "none" ] && UPSTREAM_PROXIES=""
  UPSTREAM_PROXIES="${UPSTREAM_PROXIES// /}"
  return 0
}

stage_16_nginx() {
  local site="/etc/nginx/sites-available/$NGINX_SITE"
  # 앞단 프록시 신뢰 목록을 먼저 쓴다. vhost 는 이 파일을 `include …/realip*.conf` 로 읽는다 —
  # glob 이라 파일이 없어도 `nginx -t` 가 통과하고, 목록이 비면 주석만 든 파일이라 지금과 같다.
  if [ -n "$UPSTREAM_PROXIES" ] && ! nginx -V 2>&1 | grep -q 'http_realip_module'; then
    fail "nginx 에 realip 모듈이 없습니다" "배포판 nginx 를 쓰거나 --upstream-proxy none 으로 목록을 지우십시오" 35 || return $?
  fi
  install -d -o root -g root -m 0755 "$ETC_DIR/nginx"
  {
    echo "# ClovirAssist 앞단 프록시 신뢰 목록이다. deploy/install.sh 의 Stage 16 이 매번 다시 쓰므로 손으로 고치지 않는다."
    if [ -n "$UPSTREAM_PROXIES" ]; then
      local _proxy
      for _proxy in ${UPSTREAM_PROXIES//,/ }; do echo "set_real_ip_from $_proxy;"; done
      echo "real_ip_header X-Forwarded-For;"
      echo "real_ip_recursive on;"
    else
      echo "# 앞단 프록시가 없다. 연결한 주소가 곧 사용자 주소다(--upstream-proxy 로 바꾼다)."
    fi
  } >"$ETC_DIR/nginx/realip.conf"
  chmod 0644 "$ETC_DIR/nginx/realip.conf"

  sed -e "s/__BIND_IP__/$BIND_IP/g" -e "s/__DNS_NAME__/$DNS_NAME/g" \
    "$APP_DIR/deploy/nginx/$SLUG.conf" >"$site"
  # 치환이 남았으면 잘못된 vhost 를 nginx 에 물리지 않는다 — `nginx -t` 는 이걸 못 잡는다.
  if grep -q '__BIND_IP__\|__DNS_NAME__' "$site"; then
    rm -f "$site"
    fail "vhost 템플릿 치환이 남았습니다" "--dns-name·--bind-ip 값을 확인하십시오" 35 || return $?
  fi
  ln -sf "$site" "/etc/nginx/sites-enabled/$NGINX_SITE"

  # 로그 회전. 같은 파일을 두 설정이 회전시키면 logrotate 가 "duplicate log entry" 를 내고
  # **그 실행 전체가 실패한다** — 배포판 설정이 이미 덮고 있으면 넣지 않는 것이 옳다.
  if grep -qs '/var/log/nginx/\*\.log' /etc/logrotate.d/nginx; then
    rm -f "/etc/logrotate.d/$SLUG"
  elif [ -f "$APP_DIR/deploy/nginx/logrotate-$SLUG" ]; then
    install -o root -g root -m 0644 "$APP_DIR/deploy/nginx/logrotate-$SLUG" "/etc/logrotate.d/$SLUG"
    have logrotate && { logrotate -d "/etc/logrotate.d/$SLUG" >>"$LOG" 2>&1 || log "logrotate 설정 점검 경고"; }
  fi

  if ! nginx -t >>"$LOG" 2>&1; then
    rm -f "/etc/nginx/sites-enabled/$NGINX_SITE"
    nginx -t >>"$LOG" 2>&1 && log "우리 vhost 를 빼니 기존 설정은 정상입니다"
    fail "nginx -t 가 실패했습니다" "$LOG 의 nginx 출력을 보십시오. 우리 vhost 는 이미 해제했습니다" 35 || return $?
  fi
  # 같은 이름을 두 server 블록이 들면 nginx 는 경고만 내고 **첫 번째가 조용히 이긴다.**
  local nsrv; nsrv="$(nginx -T 2>/dev/null | grep -cE "^[[:space:]]*server_name[[:space:]].*\b$DNS_NAME\b" || true)"
  [ "${nsrv:-0}" = 2 ] || { fail "server_name $DNS_NAME 을 든 블록이 ${nsrv}개입니다(:80·:443 둘이어야 합니다)" \
      "다른 vhost 가 같은 이름을 들고 있습니다. nginx -T 로 찾으십시오" 35 || return $?; }
  _reason="vhost $site · server_name 블록 2개"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 17 — 기동 + Health Check
# ═════════════════════════════════════════════════════════════════════════════
stage_17_start() {
  # VIS-109R — 워커를 **웹보다 먼저** 띄운다. 반대 순서면 새 웹이 새 job_type 을 큐에
  # 넣는 동안 옛 워커가 그 큐를 빼 가고, 모르는 job_type 이라 잡이 영구 실패한다.
  local u
  for u in "${ALL_UNITS[@]}"; do
    systemctl restart "$u" >>"$LOG" 2>&1 || true
  done
  sleep 2
  for u in "${ALWAYS_ACTIVE_UNITS[@]}"; do
    if ! unit_active "$u"; then
      journalctl -u "$u" -n 40 --no-pager >>"$LOG" 2>&1 || true
      fail "$u 가 뜨지 않았습니다" "journalctl -u $u -n 60 을 보십시오(마지막 40줄은 $LOG 에 있습니다)" 37 || return $?
    fi
  done
  systemctl reload nginx >>"$LOG" 2>&1 || systemctl restart nginx >>"$LOG" 2>&1 || true

  if ! wait_for_health 40; then
    journalctl -u "$WEB_UNIT" -n 40 --no-pager >>"$LOG" 2>&1 || true
    fail "/healthz 가 40초 안에 200 을 주지 않았습니다" "journalctl -u $WEB_UNIT -n 60 을 보십시오" 37 || return $?
  fi
  # readyz 는 DB 까지 본다. healthz 만 보면 「떴는데 DB 는 안 붙은」 상태를 초록으로 읽는다.
  curl -fsS "http://127.0.0.1:$APP_PORT/readyz" >/dev/null 2>&1 \
    || { fail "/readyz 가 200 이 아닙니다(프로세스는 떴지만 의존 자원이 안 붙었습니다)" \
         "curl -s http://127.0.0.1:$APP_PORT/readyz 로 어느 항목이 실패인지 보십시오" 37 || return $?; }
  _reason="유닛 ${#ALWAYS_ACTIVE_UNITS[@]}종 active · /healthz · /readyz 200"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 18 — 설치 검증 + manifest 확정
# ═════════════════════════════════════════════════════════════════════════════
stage_18_verify() {
  if ! do_verify; then
    fail "설치 검증(verify)이 실패했습니다" "위의 [FAIL] 줄이 어느 항목인지 말합니다" 38 || return $?
  fi
  write_manifest
  _reason="verify 통과 · $MANIFEST 기록"
  return 0
}

write_manifest() {
  local git_remote="" git_commit="" git_ref="" ver="" head=""
  if [ -d "$APP_DIR/.git" ]; then
    git_remote="$(git -C "$APP_DIR" remote get-url origin 2>/dev/null || true)"
    git_commit="$(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || true)"
    git_ref="$(git -C "$APP_DIR" describe --tags --always 2>/dev/null || true)"
  fi
  [ -n "$GIT_REMOTE" ] && git_remote="$GIT_REMOTE"
  [ -n "$GIT_REF" ] && git_ref="$GIT_REF"
  # Release 로 설치했으면 그 태그를, 아니면 전에 기록한 태그를 그대로 둔다(같은 Release 를 다시 돌린 경우).
  local release_tag=""
  if [ "$SOURCE_KIND" = release ]; then release_tag="${RELEASE_TAG:-$(jq_get release_tag)}"; fi
  ver="$(cat "$APP_DIR/VERSION" 2>/dev/null || echo unknown)"
  head="$(alembic_current_db)"
  local pgver extver
  pgver="$(psql_super 'show server_version' 2>/dev/null || echo '?')"
  extver="$(runuser -u postgres -- psql -d "$PG_DB" -tAc \
    "select string_agg(extname||'='||extversion, ',' order by extname) from pg_extension where extname in ('vector','pg_trgm')" 2>/dev/null || echo '')"
  local joined="" r
  for r in "${STAGE_RESULTS[@]:-}"; do
    [ -z "$r" ] && continue
    [ -n "$joined" ] && joined="$joined,"
    joined="$joined$r"
  done
  {
    printf '{\n'
    printf '  "product": "ClovirAssist",\n'
    printf '  "slug": "%s",\n' "$SLUG"
    printf '  "version": %s,\n' "$(json_str "$ver")"
    printf '  "source_kind": %s,\n' "$(json_str "$SOURCE_KIND")"
    printf '  "git_remote": %s,\n' "$(json_str "$git_remote")"
    printf '  "git_ref": %s,\n' "$(json_str "$git_ref")"
    printf '  "git_commit": %s,\n' "$(json_str "$git_commit")"
    printf '  "release_tag": %s,\n' "$(json_str "$release_tag")"
    printf '  "alembic_head": %s,\n' "$(json_str "$head")"
    printf '  "postgres_version": %s,\n' "$(json_str "$pgver")"
    printf '  "extensions": %s,\n' "$(json_str "$extver")"
    printf '  "dns_name": %s,\n' "$(json_str "$DNS_NAME")"
    printf '  "bind_ip": %s,\n' "$(json_str "$BIND_IP")"
    printf '  "upstream_proxies": %s,\n' "$(json_str "$UPSTREAM_PROXIES")"
    printf '  "installed_at": %s,\n' "$(json_str "$(date -Is)")"
    printf '  "installer_log": %s,\n' "$(json_str "$LOG")"
    printf '  "stages": [%s]\n' "$joined"
    printf '}\n'
  } >"$MANIFEST"
  chown root:"$SVC_USER" "$MANIFEST"; chmod 0640 "$MANIFEST"
}

# ═════════════════════════════════════════════════════════════════════════════
# verify — 아무것도 바꾸지 않는다
# ═════════════════════════════════════════════════════════════════════════════
VFAIL=0
vchk() { if eval "$2" >/dev/null 2>&1; then say "[OK ] $1"; else say "[FAIL] $1"; VFAIL=1; fi; }

do_verify() {
  VFAIL=0
  [ -n "$DNS_NAME" ] || DNS_NAME="$(sed -n 's#^APP_BASE_URL=https\?://##p' "$ENV_FILE" 2>/dev/null | tail -1)"
  [ -n "$BIND_IP" ] || BIND_IP="$(jq_get bind_ip)"
  local crt="$TLS_DIR/$DNS_NAME.crt"
  local resolve="--resolve $DNS_NAME:443:$BIND_IP --resolve $DNS_NAME:80:$BIND_IP"

  say "=== ClovirAssist 검증 (dns=$DNS_NAME bind=$BIND_IP) ==="
  local u
  for u in "${ALWAYS_ACTIVE_UNITS[@]}"; do vchk "$u active" "systemctl is-active --quiet $u"; done
  vchk "postgresql active" "systemctl is-active --quiet postgresql"
  vchk "nginx active" "systemctl is-active --quiet nginx"
  for u in postgresql nginx "${ALL_UNITS[@]}"; do vchk "$u enabled" "systemctl is-enabled --quiet $u"; done

  vchk "앱이 127.0.0.1:$APP_PORT 를 듣는다" "ss -lntH 2>/dev/null | grep -q '127.0.0.1:$APP_PORT'"
  # 로컬 릴레이(D-551) — 켰으면 받는 문이 127.0.0.1:2525 하나이고 25번은 닫혀 있다. 꺼져 있으면 메일 포트를 아무도 듣지 않는다.
  # 기존 메일 구성이 있는 서버는 우리 것이 아니라 보지 않는다.
  if mail_relay_managed && systemctl is-active --quiet postfix@-.service 2>/dev/null; then
    vchk "로컬 릴레이 받는 문은 127.0.0.1:2525 하나다" "mail_relay_ports_running"
  elif dpkg -s postfix >/dev/null 2>&1 && { [ ! -f /etc/postfix/main.cf ] || mail_relay_managed; }; then
    vchk "메일 구성 요소가 꺼져 있고 메일 포트를 듣지 않는다" "[ -z \"\$(mail_relay_listeners)\" ]"
  fi
  vchk "nginx 가 :443 을 듣는다" "ss -lntH 2>/dev/null | grep -qE ':443'"

  # ⚠️ `curl -k` 로 치면 **아무것도 증명되지 않는다** — 이름이 어긋나도, 남의 인증서여도
  # 초록이다. 실제로 이 저장소는 제품 이름이 바뀐 뒤에도 옛 CN/SAN 을 서브하는데 설치
  # 검증은 계속 OK 였다(S3 이 찾았다). 신뢰 기준점을 주고 진짜로 검증한다.
  # 그리고 **이름만으로 자기 서버를 부르면 안 된다** — 서버의 /etc/hosts 가 그 이름을
  # 127.0.1.1 로 풀어 nginx 가 아닌 곳을 찌르고 code=000 이 난다. --resolve 로 못박는다.
  vchk "healthz via nginx (TLS 검증)" "curl -fsS --cacert '$crt' $resolve https://$DNS_NAME/healthz"
  vchk "readyz via nginx (TLS 검증)" "curl -fsS --cacert '$crt' $resolve https://$DNS_NAME/readyz"
  vchk "ssl_verify_result=0" \
    "[ \"\$(curl -s -o /dev/null --cacert '$crt' $resolve -w '%{ssl_verify_result}' https://$DNS_NAME/healthz)\" = 0 ]"
  vchk "80 → 443 이 이름을 보존한다" \
    "curl -sI $resolve http://$DNS_NAME/ | tr -d '\r' | grep -qi '^location: https://$DNS_NAME/'"

  local cert_text
  cert_text="$(echo | openssl s_client -connect "$BIND_IP:443" -servername "$DNS_NAME" 2>/dev/null | \
    openssl x509 -noout -subject -enddate -ext subjectAltName 2>/dev/null || true)"
  vchk "서브되는 인증서 CN 이 $DNS_NAME" "grep -q 'subject=.*CN *= *$DNS_NAME' <<<\"$cert_text\""
  vchk "서브되는 인증서 SAN 에 $DNS_NAME" "grep -q 'DNS:$DNS_NAME' <<<\"$cert_text\""

  local nsrv; nsrv="$(nginx -T 2>/dev/null | grep -cE "^[[:space:]]*server_name[[:space:]].*\b$DNS_NAME\b" || true)"
  vchk "server_name 블록이 :80·:443 둘뿐(현재 ${nsrv:-0})" "[ '${nsrv:-0}' = 2 ]"

  # 앞단 프록시를 기록해 둔 설치처는 nginx 가 그 목록을 실제로 읽고 있어야 한다 — 파일만 있고 vhost 가
  # 안 읽으면 속도 제한이 다시 프록시 주소 하나에 걸린다.
  local proxies; proxies="$(jq_get upstream_proxies)"
  if [ -n "$proxies" ]; then
    vchk "nginx 가 앞단 프록시 목록을 읽는다($proxies)" "nginx -T 2>/dev/null | grep -q 'set_real_ip_from'"
  fi

  vchk "실패한 제품 유닛이 없다" "[ -z \"\$(systemctl --failed --plain --no-legend 2>/dev/null | grep $SLUG)\" ]"
  vchk "운영 명령 $CLI_BIN 이 있다" "[ -x '$CLI_BIN' ]"
  # 화면에서 넣는 비밀(메일 비밀번호, AI 키)과 ChatGPT 토큰 갱신이 이 소켓을 지난다(계획 2.3, 3.15).
  vchk "비밀 저장 도우미 소켓이 있다" "[ -S '$RUN_DIR/privhelper.sock' ]"

  local dbrev codehead
  dbrev="$(alembic_current_db)"; codehead="$(alembic_head_code)"
  vchk "alembic head 가 코드와 같다(db=${dbrev:-?} code=${codehead:-?})" "[ -n '$dbrev' ] && [ '$dbrev' = '$codehead' ]"
  vchk "extension vector · pg_trgm 이 있다" \
    "[ \"\$(runuser -u postgres -- psql -d $PG_DB -tAc \"select count(*) from pg_extension where extname in ('vector','pg_trgm')\")\" = 2 ]"

  if [ "$VFAIL" -eq 0 ]; then say "VERIFY_OK"; else say "VERIFY_FAILED"; fi
  return "$VFAIL"
}

jq_get() {
  [ -f "$MANIFEST" ] || return 0
  sed -n "s/^[[:space:]]*\"$1\":[[:space:]]*\"\([^\"]*\)\".*/\1/p" "$MANIFEST" | tail -1
}

# ═════════════════════════════════════════════════════════════════════════════
# version
# ═════════════════════════════════════════════════════════════════════════════
do_version() {
  echo "ClovirAssist ($SLUG)"
  echo "  VERSION       : $(cat "$APP_DIR/VERSION" 2>/dev/null || echo '(설치 안 됨)')"
  if [ -d "$APP_DIR/.git" ]; then
    echo "  git ref       : $(git -C "$APP_DIR" describe --tags --always 2>/dev/null || echo '?')"
    echo "  git commit    : $(git -C "$APP_DIR" rev-parse HEAD 2>/dev/null || echo '?')"
    echo "  git remote    : $(git -C "$APP_DIR" remote get-url origin 2>/dev/null || echo '?')"
  else
    echo "  git           : (Release 나 번들 설치라 git 트리가 아닙니다)"
    echo "  source        : $(jq_get source_kind)"
    echo "  release       : $(jq_get release_tag)"
    echo "  manifest ref  : $(jq_get git_ref)"
  fi
  echo "  alembic head  : $(alembic_current_db 2>/dev/null || echo '?')  (코드: $(alembic_head_code 2>/dev/null || echo '?'))"
  echo "  PostgreSQL    : $(psql_super 'show server_version' 2>/dev/null || echo '?')"
  echo "  extensions    : $(runuser -u postgres -- psql -d "$PG_DB" -tAc \
      "select string_agg(extname||' '||extversion, ' · ' order by extname) from pg_extension where extname in ('vector','pg_trgm')" 2>/dev/null || echo '?')"
  echo "  installed_at  : $(jq_get installed_at)"
  echo "  서비스 상태:"
  local u
  for u in postgresql nginx "${ALL_UNITS[@]}"; do
    printf '    %-42s %s / %s\n' "$u" \
      "$(systemctl is-active "$u" 2>/dev/null || echo unknown)" \
      "$(systemctl is-enabled "$u" 2>/dev/null || echo unknown)"
  done
}

# ═════════════════════════════════════════════════════════════════════════════
# 스냅샷 · rollback · uninstall
# ═════════════════════════════════════════════════════════════════════════════
# 제품의 Backup **정책**(Schedule·Retention·Manifest)이 아니다. 그것은 S12 가 제품 안에
# 세웠다(`app/backups/`). 여기는 upgrade 가 되돌릴 지점을 남기기 위한 최소 스냅샷이고,
# 둘은 대상이 다르다 — 이쪽은 **배포**(코드 + 그 시점 DB)를 되돌리고, 제품 백업은
# **데이터**를 되돌린다.
# 결과는 **전역 `SNAPSHOT_DIR`** 로 준다. 예전에는 마지막에 경로를 `echo` 하고 호출부가
# `$(take_snapshot)` 로 받았는데, 같은 함수 안의 `log` 도 표준 출력으로 나가는 바람에
# 「[17:03:54] 스냅샷: /var/backups/…」 한 줄이 통째로 경로 값이 됐다. rollback 대상이
# 그 문자열이 되어 되돌리기가 엉뚱한 자리를 찾았다 — 리허설에서 실제로 그렇게 어긋났다.
SNAPSHOT_DIR=""

# DSN 에서 데이터베이스 이름만 뽑는다. `postgresql://user@/name?host=…` 모양을 쓴다.
dsn_dbname() {
  local u="${1#*://}"
  u="${u#*/}"
  printf '%s' "${u%%\?*}"
}

take_snapshot() {
  local dir="$BACKUP_ROOT/$(_ts)"
  # 0750 root:서비스계정 — rollback 이 **서비스 계정으로** `pg_restore` 를 돌리기 때문이다.
  # 0700 root:root 로 두면 복원이 «Permission denied» 로 죽는데, 그때는 이미 `--clean` 이
  # 표를 지운 뒤라 **빈 데이터베이스**가 남는다. 리허설에서 실제로 그렇게 됐다.
  # 넓히는 것이 아니다: 이 계정은 어차피 그 DB 전체를 읽을 수 있다.
  install -d -o root -g "$SVC_USER" -m 0750 "$BACKUP_ROOT" 2>/dev/null \
    || install -d -o root -g root -m 0700 "$BACKUP_ROOT"
  install -d -o root -g root -m 0750 "$dir"
  id "$SVC_USER" >/dev/null 2>&1 && chgrp "$SVC_USER" "$dir" 2>/dev/null || true
  SNAPSHOT_DIR="$dir"
  log "스냅샷: $dir"
  [ -d "$APP_DIR" ] && tar czf "$dir/app.tar.gz" --exclude="$SLUG/venv" -C /opt "$SLUG" 2>/dev/null || true
  [ -d "/opt/$LEGACY_SLUG" ] && tar czf "$dir/app-legacy.tar.gz" --exclude="$LEGACY_SLUG/venv" -C /opt "$LEGACY_SLUG" 2>/dev/null || true
  [ -d "$ETC_DIR" ] && tar czf "$dir/etc.tar.gz" -C /etc "$SLUG" 2>/dev/null || true
  [ -d "/etc/$LEGACY_SLUG" ] && tar czf "$dir/etc-legacy.tar.gz" -C /etc "$LEGACY_SLUG" 2>/dev/null || true

  # 🔴 사용자가 올린 파일과 제품이 만든 산출물. **DB 덤프만으로는 못 돌아온다** — 첨부·
  # 업로드는 디스크에 있고 DB 에는 그 파일을 가리키는 행만 있다. 여기가 빠지면 rollback 이
  # 「행은 있는데 파일이 없는」 상태를 만들고, 그 화면은 오류가 아니라 **빈 첨부**로 보인다.
  #
  # 옛 백업 스크립트(`backup-*.sh`)가 이 성질을 갖고 있었는데 새 설치기로 옮겨 오면서
  # 빠졌다. 옛 스크립트의 시험이 계속 초록이라 아무도 못 봤다 — 지운 것이 아니라 **옮겨
  # 오지 않은 것**이 이 종류의 사고다.
  #
  # `ai/models` 는 뺀다. 수 GB 이고 **되받을 수 있는 것**이라(설치기가 다시 깐다) 여기
  # 넣으면 스냅샷 하나가 디스크를 채워 되돌릴 지점 자체를 못 만들게 된다. `temp` 도 뺀다 —
  # 이름 그대로 중간 파일이다.
  # 🔴 워커 리스 파일(`*.lock`)은 **데이터가 아니라 지금 누가 살아 있는가**다. 담으면
  # 되돌릴 때 죽은 프로세스의 리스가 되살아나고, 그 뒤에 뜬 워커는 «다른 워커가 이미 돌고
  # 있다» 며 스스로 물러난다(S22 실측 — 배치·스케줄러·색인 세 레인이 그렇게 안 돌아왔다).
  [ -d "$VAR_DIR" ] && tar czf "$dir/data.tar.gz"     --exclude="$SLUG/ai/models" --exclude="$SLUG/temp" --exclude="$SLUG/*.lock" -C /var/lib "$SLUG" 2>/dev/null || true
  [ -d "/var/lib/$LEGACY_SLUG" ] && tar czf "$dir/data-legacy.tar.gz"     --exclude="$LEGACY_SLUG/ai/models" --exclude="$LEGACY_SLUG/temp"     -C /var/lib "$LEGACY_SLUG" 2>/dev/null || true
  local u
  for u in "${ALL_UNITS[@]}" "${LEGACY_UNITS[@]}"; do
    [ -f "/etc/systemd/system/$u" ] && cp "/etc/systemd/system/$u" "$dir/" || true
  done
  [ -f "/etc/nginx/sites-available/$NGINX_SITE" ] && cp "/etc/nginx/sites-available/$NGINX_SITE" "$dir/nginx-vhost.conf" || true
  # 로컬 릴레이(D-551) — 제품이 관리하는 Postfix 설정 · 인증서 · DKIM 키. 기존 메일 구성은 우리 것이 아니라 담지 않는다.
  if mail_relay_managed; then
    local mail_parts=(postfix/main.cf postfix/master.cf postfix/clovirassist)
    [ -d /etc/opendkim ] && mail_parts+=(opendkim)
    [ -f /etc/opendkim.conf ] && mail_parts+=(opendkim.conf)
    tar czf "$dir/mail-relay.tar.gz" -C /etc "${mail_parts[@]}" 2>/dev/null || true
  fi

  # DB 덤프.
  #
  # **덤프에 실패하면 죽는다** — 예전 백업은 파일이 없으면 조용히 건너뛰고 `BACKUP_OK` 를
  # 찍었고, 그 초록을 믿고 복원 계획을 세우는 것이 가장 나쁘다(S2 가 고친 그 성질을 지킨다).
  #
  # 다만 **「덤프에 실패했다」와 「덤프할 것이 아직 없다」는 다르다.** 옛 slug 설치를 새로
  # 이전하는 자리에는 아직 데이터베이스가 없을 수 있는데, 그때 죽으면 이전 자체를 시작할
  # 수 없다 — 잃을 데이터가 없는데 되돌릴 지점을 요구하는 셈이다. 없으면 **없다고 적고**
  # 넘어간다(조용히 넘어가지 않는다).
  local dsn dbname
  dsn="$(env_get DATABASE_URL || true)"
  [ -n "$dsn" ] || dsn="$(env_get DATABASE_URL "/etc/$LEGACY_SLUG/web.env" || true)"
  dbname="$(dsn_dbname "${dsn:-}")"
  [ -n "$dbname" ] || dbname="$PG_DB"

  local db_exists=0
  if systemctl is-active --quiet postgresql 2>/dev/null; then
    [ "$(psql_super "select count(*) from pg_database where datname='$dbname'" 2>/dev/null || echo 0)" = 1 ] && db_exists=1
  fi

  if [ -z "$dsn" ] || [ "$db_exists" = 0 ]; then
    printf '데이터베이스가 아직 없습니다(dsn=%s db=%s). 덤프할 것이 없어 파일만 담았습니다.\n' \
      "${dsn:-<없음>}" "$dbname" >"$dir/db.absent"
    log "덤프 없음: 데이터베이스 '$dbname' 가 아직 없습니다 — 잃을 데이터가 없어 계속합니다"
  elif [ ! -x "$PG_BIN_DIR/pg_dump" ]; then
    die "pg_dump 가 없습니다($PG_BIN_DIR). 되돌릴 지점 없이 진행하지 않습니다" 40
  else
    # 서비스 계정이 아직 없는 이전 자리에서는 postgres 로 뜬다(둘 다 peer 인증이다).
    local as_user="$SVC_USER"
    id "$SVC_USER" >/dev/null 2>&1 || as_user=postgres
    runuser -u "$as_user" -- "$PG_BIN_DIR/pg_dump" --format=custom --no-owner --no-privileges \
      --dbname "postgresql:///$dbname" >"$dir/db.dump" 2>>"$LOG" \
      || die "pg_dump 가 실패했습니다(db=$dbname). 되돌릴 지점 없이 진행하지 않습니다: $dir" 40
    "$PG_BIN_DIR/pg_restore" --list "$dir/db.dump" >"$dir/db.toc" 2>>"$LOG" \
      || die "덤프를 읽을 수 없습니다(pg_restore --list 실패): $dir/db.dump" 40
  fi
  ( cd "$dir" && sha256sum ./* >SHA256SUMS 2>/dev/null ) || true
  if id "$SVC_USER" >/dev/null 2>&1; then
    chown root:"$SVC_USER" "$dir"/* 2>/dev/null || true
    chmod 0640 "$dir"/* 2>/dev/null || true
  fi
  prune_snapshots
}

# 스냅샷 보존(S12). 스냅샷을 만드는 자리에서 함께 지운다 — 별도 cron 을 두면 그 cron 이
# 안 도는 설치에서 `$BACKUP_ROOT` 가 무한히 자라고, 그 사실은 디스크가 찰 때 처음 드러난다.
# 스냅샷은 install.sh 가 돌 때만 생기므로, 만들 때 치우는 것으로 충분하다.
#
# **개수가 아니라 나이로 지운다.** 배포가 잦은 날 하루 만에 일주일치 복원 지점이 증발하는
# 것을 막는다(배포 N번 = 그날 슬롯 N개 소모). 제품 쪽 보존이 개수와 나이를 **둘 다** 거는
# 것과 같은 이유이고, 여기서는 만드는 주체가 하나뿐이라 나이 하나로 충분하다.
SNAPSHOT_KEEP_DAYS="${SNAPSHOT_KEEP_DAYS:-14}"

# 되돌릴 스냅샷의 이름 규칙(`_ts` 가 만든다). 고르는 곳(latest_snapshot)과 지우는 곳(prune_snapshots)이 같은 규칙을 쓴다.
SNAPSHOT_NAME_RE='.*/[0-9]{8}[-_][0-9]{6}'

# 가장 최근 스냅샷. **타임스탬프 디렉터리만** 본다(D-522 · I3 리허설).
#
# 예전에는 `$BACKUP_ROOT` 아래 디렉터리를 이름순으로 세워 마지막 것을 골랐다. 그런데 그 자리에는 특권 도우미가 바꾼 설정
# 파일의 사본을 두는 `sysops/` 도 있고, 글자는 숫자보다 뒤에 선다. 그래서 시스템 설정 화면에서 프록시나 인증서를 한 번이라도
# 바꾼 설치는 `rollback` 이 스냅샷 대신 `sysops/` 를 고르고 「DB 덤프도 없음 기록도 없다」며 멈췄다. Release 리허설이 프록시를
# 설정한 뒤 되돌리기에서 실제로 그렇게 멈췄다.
latest_snapshot() {
  [ -d "$BACKUP_ROOT" ] || return 0
  find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d -regextype posix-extended -regex "$SNAPSHOT_NAME_RE" 2>/dev/null \
    | sort | tail -1
}

prune_snapshots() {
  [ -d "$BACKUP_ROOT" ] || return 0
  local old
  # 타임스탬프 디렉터리만 대상이다(`_ts` 가 만드는 이름). 사람이 손으로 둔 디렉터리를
  # 지우지 않는다 — 되돌릴 자료를 따로 챙겨 둔 자리일 수 있다.
  while IFS= read -r old; do
    [ -n "$old" ] || continue
    log "스냅샷 정리(${SNAPSHOT_KEEP_DAYS}일 초과): $old"
    rm -rf -- "$old"
  done < <(find "$BACKUP_ROOT" -maxdepth 1 -mindepth 1 -type d \
             -regextype posix-extended -regex "$SNAPSHOT_NAME_RE" \
             -mtime "+$SNAPSHOT_KEEP_DAYS" 2>/dev/null)
}

do_rollback() {
  local dir="$ROLLBACK_TARGET"
  if [ -z "$dir" ]; then
    dir="$(latest_snapshot)"
  fi
  [ -n "$dir" ] && [ -d "$dir" ] || die "되돌릴 스냅샷이 없습니다(대상: ${ROLLBACK_TARGET:-<자동>})" 41
  # `db.absent` 는 그 스냅샷을 뜰 때 **데이터베이스가 아직 없었다**는 기록이다. 그때는
  # 되돌릴 데이터도 없으니 파일만 되돌린다. 둘 다 없으면 그 스냅샷은 못 믿는다.
  if [ ! -f "$dir/db.dump" ] && [ ! -f "$dir/db.absent" ]; then
    die "스냅샷에 DB 덤프도 «없음» 기록도 없습니다. 이 스냅샷으로는 되돌릴 수 없습니다: $dir" 41
  fi
  log "rollback ← $dir"
  if [ -f "$dir/SHA256SUMS" ]; then
    ( cd "$dir" && sha256sum -c --quiet SHA256SUMS ) \
      || die "스냅샷 체크섬이 맞지 않습니다. 손상된 백업으로 복원하지 않습니다: $dir" 41
    say "  체크섬 확인"
  fi

  local u
  for u in "${ALL_UNITS[@]}"; do systemctl stop "$u" >>"$LOG" 2>&1 || true; done

  [ -f "$dir/app.tar.gz" ] && { rm -rf "$APP_DIR.rollback-tmp"; tar xzf "$dir/app.tar.gz" -C /opt; }
  [ -f "$dir/etc.tar.gz" ] && tar xzf "$dir/etc.tar.gz" -C /etc
  # 파일도 함께 되돌린다 — DB 만 되돌리면 첨부 행이 없는 파일을 가리킨다(take_snapshot 참조).
  # 소유는 다시 잡아 준다: tar 가 담아 온 uid/gid 가 이 서버의 서비스 계정과 다를 수 있다.
  if [ -f "$dir/data.tar.gz" ]; then
    tar xzf "$dir/data.tar.gz" -C /var/lib
    id "$SVC_USER" >/dev/null 2>&1 && chown -R "$SVC_USER":"$SVC_USER" "$VAR_DIR" 2>/dev/null || true
  fi
  # 🔴 되살아난 리스를 지운다. 위에서 유닛을 **전부 멈춘 뒤**라 지금 이 호스트에 도는
  # 워커는 없다 — 그러니 남아 있는 `*.lock` 은 전부 죽은 프로세스의 것이다. 옛 스냅샷은
  # 아직 리스를 담고 있고(그 자리를 이번에 `take_snapshot` 에서 뺐다), 담긴 리스를 그대로
  # 되돌리면 뒤이어 뜨는 워커가 «다른 워커가 이미 돌고 있다» 며 1 로 죽는다. 유닛은
  # `Restart=on-failure` · `RestartSec=10` · `StartLimitBurst=10` 이라 100초 만에 시도를
  # 멈추는데 리스는 120초를 산다 — **재시도가 먼저 끝나서 레인이 영영 안 돌아온다.**
  rm -f "$VAR_DIR"/*.lock 2>/dev/null || true
  for u in "${ALL_UNITS[@]}"; do
    [ -f "$dir/$u" ] && install -m 0644 "$dir/$u" "/etc/systemd/system/$u" || true
  done
  [ -f "$dir/nginx-vhost.conf" ] && cp "$dir/nginx-vhost.conf" "/etc/nginx/sites-available/$NGINX_SITE" || true
  systemctl daemon-reload

  # venv 는 스냅샷에 없다(용량). 없으면 다시 만든다.
  if [ ! -x "$APP_DIR/venv/bin/python" ]; then
    log "venv 재생성"
    python3 -m venv "$APP_DIR/venv" >>"$LOG" 2>&1
    "$APP_DIR/venv/bin/pip" install -r "$APP_DIR/requirements.txt" >>"$LOG" 2>&1 \
      || die "복원한 소스의 의존성을 깔 수 없습니다" 41
  fi

  if [ ! -f "$dir/db.dump" ]; then
    say "  이 스냅샷을 뜰 때는 데이터베이스가 없었습니다 — 파일만 되돌렸습니다($dir/db.absent)"
    for u in "${ALL_UNITS[@]}"; do systemctl start "$u" >>"$LOG" 2>&1 || true; done
    say "ROLLBACK_OK $dir (DB 없음)"
    return 0
  fi

  local dsn; dsn="$(env_get DATABASE_URL || true)"
  [ -n "$dsn" ] || die "DATABASE_URL 을 읽을 수 없습니다" 41

  # 🔴 extension DDL 을 복원 목록에서 뺀다.
  #
  # 덤프에는 `CREATE EXTENSION vector` 가 들어 있는데, `--clean` 은 그 앞에
  # `DROP EXTENSION IF EXISTS vector` 를 낸다. 둘 다 **슈퍼유저만** 할 수 있다(pgvector 는
  # trusted extension 이 아니다). 서비스 계정으로 복원하면 거기서 오류가 나고 `pg_restore`
  # 가 0 이 아닌 값으로 끝난다 — 그런데 그 시점에는 이미 표를 다 지운 뒤라, 복원이 실패한
  # 자리에 **빈 데이터베이스**가 남는다. 리허설에서 실제로 그렇게 됐고, 그 뒤 모든 검사가
  # 「roles 표가 없다」로 무너졌다. 되돌리기가 데이터를 없애는 것이 가장 나쁘다.
  #
  # extension 은 Stage 7 이 이미 만들어 두었고 `--clean` 이 지우지만 않으면 그대로 있다.
  # 그래서 복원 목록에서 그 항목만 빼면 나머지(표·인덱스·데이터)는 소유자인 서비스 계정이
  # 전부 복원할 수 있다. 슈퍼유저로 복원하는 쪽은 소유권이 postgres 로 넘어가 앱이 못 쓴다.
  local list="$dir/db.restore.list"
  "$PG_BIN_DIR/pg_restore" --list "$dir/db.dump" \
    | grep -vE '(^;|[[:space:]]EXTENSION[[:space:]]|EXTENSION - )' >"$list" \
    || die "덤프 목록을 읽을 수 없습니다: $dir/db.dump" 41
  [ -s "$list" ] || die "복원 목록이 비었습니다. 덤프가 손상됐을 수 있습니다: $dir/db.dump" 41

  # 🔴 `--exit-on-error` 가 없으면 `pg_restore` 는 **오류를 세어 두고 0 으로 끝난다**
  # ("warning: errors ignored on restore: N"). 그러면 `--clean` 이 표를 다 지운 뒤 전부
  # 실패해도 이 스크립트는 «복원했다» 고 말한다 — 리허설에서 실제로 그렇게 빈 데이터베이스가
  # 초록으로 통과했다. 되돌리기가 조용히 데이터를 없애는 것이 가장 나쁘다.
  if ! runuser -u "$SVC_USER" -- "$PG_BIN_DIR/pg_restore" --clean --if-exists --exit-on-error \
      --no-owner --no-privileges --use-list "$list" --dbname "$dsn" "$dir/db.dump" >>"$LOG" 2>&1; then
    say "--- pg_restore 오류 (마지막 20줄) ---"
    tail -n 20 "$LOG" | sed 's/^/  /'
    die "pg_restore 가 실패했습니다. $LOG 를 보십시오" 41
  fi

  # 복원 뒤 **실제로 표가 있는지** 본다. 위 검사가 놓치는 경우가 남아 있을 수 있고,
  # 「복원 성공」과 「빈 데이터베이스」를 구분하지 못하면 그 초록이 가장 비싸다.
  local ntab
  ntab="$(runuser -u "$SVC_USER" -- psql -d "$(dsn_dbname "$dsn")" -tAc \
    "select count(*) from information_schema.tables where table_schema='public'" 2>/dev/null || echo 0)"
  [ "${ntab:-0}" -gt 1 ] || die "복원 뒤 public 스키마에 표가 ${ntab:-0}개뿐입니다. 빈 데이터베이스를 «복원 성공» 이라고 부르지 않습니다" 41
  say "  복원 확인: public 표 ${ntab}개"

  for u in "${ALL_UNITS[@]}"; do systemctl start "$u" >>"$LOG" 2>&1 || true; done
  systemctl reload nginx >>"$LOG" 2>&1 || systemctl restart nginx >>"$LOG" 2>&1 || true
  # 🔴 여기서  만 하고 판정했다. 유닛은 Type=simple 이라 프로세스가 뜨는 순간
  # active 가 되지만 uvicorn 이 워커 넷을 올려 8080 을 듣기까지는 그보다 오래 걸린다 —
  # 그래서 복원이 실제로 성공했는데도 ROLLBACK_DEGRADED 로 읽혔다(리허설에서 실측).
  # Stage 17 과 **같은 기다림**을 쓴다.
  wait_for_health 40 || say "  /healthz 가 아직 응답하지 않습니다 — 아래 verify 가 무엇이 빠졌는지 말합니다"
  if do_verify; then say "ROLLBACK_OK $dir"; else say "ROLLBACK_DEGRADED $dir — verify 가 실패했습니다"; return 1; fi
}

do_uninstall() {
  if [ "$PURGE" = 1 ] && [ "$ASSUME_YES" != 1 ]; then
    die "--purge 는 데이터($VAR_DIR)와 백업($BACKUP_ROOT)과 DB($PG_DB)를 지웁니다. 확실하면 --yes 를 함께 주십시오" 42
  fi
  local u
  for u in "${ALL_UNITS[@]}"; do
    systemctl stop "$u" >>"$LOG" 2>&1 || true
    systemctl disable "$u" >>"$LOG" 2>&1 || true
    rm -f "/etc/systemd/system/$u"
    rm -rf "/etc/systemd/system/$u.d"
  done
  # 저장소 마운트 유닛(S8). 제품이 깐 것만 지운다 — 사람이 손으로 만든 마운트를
  # 제품 제거가 함께 떼어 내면, 같은 서버의 다른 것이 조용히 안 보이게 된다.
  local mu base
  for mu in /etc/systemd/system/*.mount; do
    [ -e "$mu" ] || break
    grep -q "ClovirAssist" "$mu" 2>/dev/null || continue
    base="$(basename "$mu")"
    systemctl stop "$base" >>"$LOG" 2>&1 || true
    systemctl disable "$base" >>"$LOG" 2>&1 || true
    rm -f "$mu"
  done
  systemctl daemon-reload
  rm -f "/etc/nginx/sites-enabled/$NGINX_SITE" "/etc/nginx/sites-available/$NGINX_SITE" "/etc/logrotate.d/$SLUG"
  nginx -t >>"$LOG" 2>&1 && { systemctl reload nginx >>"$LOG" 2>&1 || true; }
  rm -rf "$APP_DIR" "$SSL_FALLBACK_DIR"
  rm -f "$CLI_BIN"
  rm -f /etc/systemd/timesyncd.conf.d/99-"$SLUG".conf /etc/systemd/resolved.conf.d/99-"$SLUG".conf
  # AI 모델 캐시(S9). **`--purge` 가 아니어도 지운다** — 모델은 사용자 데이터가 아니라
  # 재생성 가능한 자산이고(D-203 · D-204), 465MB 짜리 파일을 「데이터를 남겼습니다」에
  # 넣어 두면 제품을 지운 뒤에도 디스크가 안 돌아온다. 다시 깔면 다시 넣는다.
  rm -rf "$VAR_DIR/ai"
  if [ "$PURGE" = 1 ]; then
    rm -rf "$ETC_DIR" "$VAR_DIR" "$BACKUP_ROOT"
    runuser -u postgres -- dropdb --if-exists "$PG_DB" >>"$LOG" 2>&1 || true
    psql_super "drop role if exists \"$PG_ROLE\"" >>"$LOG" 2>&1 || true
    id "$SVC_USER" >/dev/null 2>&1 && userdel "$SVC_USER" >>"$LOG" 2>&1 || true
    say "UNINSTALL_OK purge=1 — 설정·데이터·백업·DB·계정까지 지웠습니다"
  else
    say "UNINSTALL_OK purge=0 — 설정($ETC_DIR)·데이터($VAR_DIR)·백업($BACKUP_ROOT)·DB($PG_DB)는 남겼습니다"
    say "  전부 지우려면: $SCRIPT_PATH uninstall --purge --yes"
  fi
}

# ═════════════════════════════════════════════════════════════════════════════
# install / upgrade 본체
# ═════════════════════════════════════════════════════════════════════════════
# 첫 관리자 설정 코드를 콘솔에만 보인다. say 가 아니라 echo 인 이유: say 는 설치 로그에도 쓴다(D-522).
print_first_admin_code() {
  [ -n "$FIRST_ADMIN_CODE" ] || return 0
  echo
  echo "=== 첫 관리자 계정 ==="
  echo "아직 계정이 없습니다. 브라우저에서 https://$DNS_NAME/setup/first-admin 을 열고 아래 설정 코드를 넣어"
  echo "시스템 관리자 계정을 만드세요. 코드는 한 번만 쓸 수 있고 설치 로그에는 남지 않습니다."
  echo
  echo "  설정 코드: $FIRST_ADMIN_CODE"
  [ -n "$FIRST_ADMIN_EXPIRES" ] && echo "  만료(UTC): $FIRST_ADMIN_EXPIRES"
  echo
  echo "코드를 잃어버렸거나 만료됐으면 sudo clovirassist first-admin-code 로 새 코드를 만드세요."
  FIRST_ADMIN_CODE=""
}

run_all_stages() {
  run_stage 0  PREFLIGHT   stage_0_preflight
  run_stage 1  APT         stage_1_apt
  run_stage 2  ACCOUNTS    stage_2_accounts
  run_stage 3  SOURCE      stage_3_source
  run_stage 4  PYTHON      stage_4_python
  run_stage 5  FRONTEND    stage_5_frontend
  run_stage 6  POSTGRES    stage_6_postgres
  run_stage 7  EXTENSIONS  stage_7_extensions
  run_stage 8  CONFIG      stage_8_config
  run_stage 9  MIGRATION   stage_9_migration
  run_stage 10 SEED        stage_10_seed
  run_stage 11 STORAGE     stage_11_storage
  run_stage 12 AI          stage_12_ai
  run_stage 13 UNITS       stage_13_units
  run_stage 14 ENABLE      stage_14_enable
  run_stage 15 TLS         stage_15_tls
  run_stage 16 NGINX       stage_16_nginx
  run_stage 17 START       stage_17_start
  run_stage 18 VERIFY      stage_18_verify
}

mail_relay_ports_running() {
  local heard; heard="$(mail_relay_listeners)"
  case " $heard " in *" 127.0.0.1:2525 "*) ;; *) return 1 ;; esac
  ! printf '%s\n' $heard | grep -qE ':25$' && ! printf '%s\n' $heard | grep -vE '^127\.0\.0\.1:' | grep -q .
}

case "$SUBCOMMAND" in
  preflight)
    open_log
    resolve_upstream_proxies
    run_stage 0 PREFLIGHT stage_0_preflight
    say "PREFLIGHT_OK"
    ;;
  install)
    open_log
    resolve_upstream_proxies
    log "=== install 시작 (dns=$DNS_NAME bind=$BIND_IP proxies=${UPSTREAM_PROXIES:-없음} source=${SOURCE_KIND:-auto}) ==="
    # 기존 설치 위에 다시 도는 install 은 되돌릴 지점을 먼저 만든다.
    if [ -f "$ENV_FILE" ] || legacy_present; then
      take_snapshot; say "스냅샷: $SNAPSHOT_DIR"
    fi
    run_all_stages
    say "INSTALL_OK dns=$DNS_NAME log=$LOG"
    print_first_admin_code
    ;;
  upgrade)
    open_log
    [ -f "$MANIFEST" ] || [ -f "$ENV_FILE" ] || legacy_present \
      || die "업그레이드할 기존 설치가 없습니다. 먼저 install 을 실행하십시오" 43
    # Source 위치를 사용자가 다시 알려 줄 필요가 없다 — manifest 가 들고 있다.
    # Release 로 설치한 서버에는 git 트리가 없다. 다음 버전을 주지 않으면 올릴 것이 없다 - 같은 것을 다시 까는 것을
    # 업그레이드라고 부르지 않는다.
    if [ -z "$RELEASE_TAG" ] && [ -z "$GIT_REF" ] && [ ! -d "$APP_DIR/.git" ] && [ "$(jq_get source_kind)" = release ]; then
      die "Release 로 설치한 서버입니다. 올릴 버전을 주십시오: sudo clovirassist upgrade --release v<버전>" 43
    fi
    [ -n "$GIT_REMOTE" ] || GIT_REMOTE="$(jq_get git_remote)"
    [ -n "$DNS_NAME" ] || DNS_NAME="$(jq_get dns_name)"
    [ -n "$BIND_IP" ] || BIND_IP="$(jq_get bind_ip)"
    resolve_upstream_proxies
    log "=== upgrade 시작 (ref=${GIT_REF:-<현재>} remote=${GIT_REMOTE:-<현재>} proxies=${UPSTREAM_PROXIES:-없음}) ==="
    take_snapshot; say "스냅샷: $SNAPSHOT_DIR"
    say "  실패하면 되돌리기: $SCRIPT_PATH rollback --target $SNAPSHOT_DIR"
    if [ -n "$GIT_REF" ] && [ -d "$APP_DIR/.git" ]; then
      [ -n "$GIT_REMOTE" ] && git -C "$APP_DIR" remote set-url origin "$GIT_REMOTE" >>"$LOG" 2>&1 || true
      git -C "$APP_DIR" fetch --tags --quiet >>"$LOG" 2>&1 \
        || die "원격에서 fetch 할 수 없습니다($GIT_REMOTE)" 43
    fi
    run_all_stages
    say "UPGRADE_OK ref=${GIT_REF:-${RELEASE_TAG:-<현재>}} snapshot=$SNAPSHOT_DIR log=$LOG"
    print_first_admin_code
    ;;
  rollback)  open_log; do_rollback ;;
  uninstall) open_log; do_uninstall ;;
  verify)    do_verify || exit 1 ;;
  version)   do_version ;;
  # 저장소를 추가·변경한 뒤 마운트 유닛을 다시 까는 경로. 전체 재설치를 시키지
  # 않는 이유는 하나다 — 그러면 사람이 안 하고, 안 하면 유닛 없이 도는 저장소가
  # 남는다(INSTALLATION.md §6.1 Installer 계약).
  storage)   open_log; run_stage 11 STORAGE stage_11_storage; say "STORAGE_OK log=$LOG" ;;
  # 모델 파일을 나중에 넣고 AI 를 켜는 경로(S9). 저장소와 같은 이유로 전체 재설치를
  # 시키지 않는다. 유닛을 다시 시작하는 것까지가 이 명령의 일이다 — 안 하면 색인
  # 레인이 옛 설정을 든 채로 계속 돌고, 화면은 「켰다」고 말한다.
  # 로컬 릴레이 구성 요소를 나중에 까는 경로(D-551). 같은 가드(다른 MTA · 기존 구성 · 기본 꺼짐)를 지난다. 켜기는 메일 화면이 한다.
  mail-relay) open_log
             run_stage 1 APT stage_1_apt
             say "MAIL_RELAY_OK ${MAIL_RELAY_NOTE:-} log=$LOG" ;;
  ai)        open_log
             ai_env_apply
             run_stage 12 AI stage_12_ai
             systemctl restart "$INDEX_UNIT" >>"$LOG" 2>&1 || log "색인 유닛 재시작 실패"
             say "AI_OK log=$LOG" ;;
esac
