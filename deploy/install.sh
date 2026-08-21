#!/usr/bin/env bash
# ClovirAssist 설치 · 배포 자동화 단일 진입점 (docs/platform/INSTALLATION.md).
#
#   sudo /opt/clovirassist/deploy/install.sh <subcommand> [options]
#
# 서브커맨드: install · upgrade · rollback · uninstall · verify · version · preflight
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
PRIVHELPER_UNIT="$SLUG-privhelper.service"
# 기동 순서. privhelper 가 먼저(관리 화면이 「도우미 없음」을 안 보이게), 웹이 마지막
# (VIS-109R: 워커가 새 job_type 을 이해하기 전에 웹이 그 잡을 넣을 수 있는 창을 없앤다).
ALL_UNITS=("$PRIVHELPER_UNIT" "$WORKER_UNIT" "$WORKER_CONV_UNIT" "$SCHEDULER_UNIT" "$WEB_UNIT")
# 재부팅 뒤 **떠 있어야** 하는 유닛. 대화형 레인은 설정 플래그가 꺼져 있으면 정상적으로
# exit(0) 해 inactive(dead) 가 된다 — 그것이 그 유닛의 정상 대기 상태다 (D-118).
ALWAYS_ACTIVE_UNITS=("$PRIVHELPER_UNIT" "$WORKER_UNIT" "$SCHEDULER_UNIT" "$WEB_UNIT")

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

SOURCE_KIND=""            # git | bundle | local
GIT_REMOTE="${GIT_REMOTE:-}"
GIT_REF="${GIT_REF:-}"
WHEELHOUSE="${WHEELHOUSE:-}"
OFFLINE=0
ASSUME_YES=0
INJECT_FAILURE=""         # 리허설용 — INSTALLATION.md §8 부가검증 3
ROLLBACK_TARGET=""
PURGE=0

SCRIPT_PATH="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)/$(basename "${BASH_SOURCE[0]}")"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

# ── 출력 ─────────────────────────────────────────────────────────────────────
LOG=""
declare -a STAGE_RESULTS=()
CURRENT_STAGE=""

_ts() { date +%Y%m%d-%H%M%S; }
log()  { local line="[$(date +%H:%M:%S)] $*"; echo "$line"; [ -n "$LOG" ] && echo "$line" >>"$LOG" || true; }
say()  { echo "$*"; [ -n "$LOG" ] && echo "$*" >>"$LOG" || true; }
die()  { say "$*"; exit "${2:-1}"; }

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
  [ -d "/opt/$LEGACY_SLUG" ] || [ -f "/etc/$LEGACY_SLUG/web.env" ] || unit_exists "${LEGACY_UNITS[0]}"
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

옵션
  --dns-name <name>     설치처 호스트명. 인증서 CN/SAN 과 nginx server_name 이 이 값이다
  --bind-ip <ip>        nginx 가 묶일 주소
  --source git|bundle|local
  --git-remote <url>    제품 기준 Source. 기본은 기존 설치의 manifest 값
  --ref <tag>           고정할 tag. 브랜치 추적은 하지 않는다
  --wheelhouse <dir>    오프라인 wheel 디렉터리
  --offline             네트워크를 쓰지 않는다(wheelhouse·번들 필수)
  --inject-failure <n>  Stage n 에서 일부러 멈춘다(리허설 전용)
  --purge               uninstall 에서 데이터·백업까지 지운다
  --yes                 되돌리기 어려운 동작을 묻지 않고 진행한다
EOF
}

SUBCOMMAND="${1:-}"
[ -n "$SUBCOMMAND" ] || { usage; exit 64; }
shift || true
case "$SUBCOMMAND" in
  install|upgrade|rollback|uninstall|verify|version|preflight) ;;
  -h|--help) usage; exit 0 ;;
  *) echo "모르는 서브커맨드: $SUBCOMMAND"; usage; exit 64 ;;
esac

while [ $# -gt 0 ]; do
  case "$1" in
    --dns-name) DNS_NAME="${2:-}"; shift 2 ;;
    --bind-ip) BIND_IP="${2:-}"; shift 2 ;;
    --source) SOURCE_KIND="${2:-}"; shift 2 ;;
    --git-remote) GIT_REMOTE="${2:-}"; shift 2 ;;
    --ref) GIT_REF="${2:-}"; shift 2 ;;
    --wheelhouse) WHEELHOUSE="${2:-}"; shift 2 ;;
    --offline) OFFLINE=1; shift ;;
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

stage_0_preflight() {
  local os_id os_ver arch mem_mb disk_mb

  os_id="$(. /etc/os-release 2>/dev/null && echo "${ID:-}")"
  os_ver="$(. /etc/os-release 2>/dev/null && echo "${VERSION_ID:-}")"
  [ "$os_id" = ubuntu ] || fail "지원하지 않는 OS 입니다(id=$os_id)" "Ubuntu Server 24.04 에서 실행하십시오" 10 || return $?
  [ "$os_ver" = "24.04" ] || note "OS 버전이 24.04 가 아닙니다($os_ver) — 계속 진행합니다"

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

  # 소스 종류 결정. 스크립트가 이미 $APP_DIR 안에 있으면 그 자리가 소스다(§1 의 3줄 경로).
  if [ -z "$SOURCE_KIND" ]; then
    if [ "$SRC_DIR" = "$APP_DIR" ]; then SOURCE_KIND=git
    else SOURCE_KIND=local; fi
  fi
  case "$SOURCE_KIND" in
    git|bundle|local) ;;
    *) fail "모르는 --source: $SOURCE_KIND" "git · bundle · local 중 하나입니다" 15 || return $? ;;
  esac
  if [ "$SOURCE_KIND" = git ] && [ "$SRC_DIR" != "$APP_DIR" ] && [ -z "$GIT_REMOTE" ]; then
    fail "--source git 인데 원본을 모릅니다" "--git-remote <url> 을 주거나 $APP_DIR 에 clone 한 뒤 그 안의 install.sh 를 실행하십시오" 15 || return $?
  fi
  [ -f "$SRC_DIR/requirements.txt" ] || \
    fail "소스가 아닌 자리에서 실행됐습니다($SRC_DIR)" "저장소 clone 안의 deploy/install.sh 를 실행하십시오" 15 || return $?
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

stage_1_apt() {
  local need=() pkg
  for pkg in "${BASE_PKGS[@]}"; do
    dpkg -s "$pkg" >/dev/null 2>&1 || need+=("$pkg")
  done
  if [ "${#need[@]}" -eq 0 ]; then _reason="필요한 패키지 ${#BASE_PKGS[@]}개가 이미 있습니다"; return 0; fi
  if [ "$OFFLINE" = 1 ]; then
    fail "오프라인인데 없는 패키지가 있습니다: ${need[*]}" "설치 전에 이 패키지들을 미리 넣으십시오" 21 || return $?
  fi
  log "apt install: ${need[*]}"
  apt-get update -qq >>"$LOG" 2>&1 || true
  if ! apt-get install -y --no-install-recommends "${need[@]}" >>"$LOG" 2>&1; then
    fail "apt 설치 실패: ${need[*]}" "apt-get install ${need[*]} 를 직접 실행해 원인을 보십시오" 21 || return $?
  fi
  _reason="설치함: ${need[*]}"
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 2 — 계정 · 디렉터리 (+ 옛 slug 이전)
# ═════════════════════════════════════════════════════════════════════════════
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
    # 이미 새 자리에 있는 것은 덮지 않는다(재실행 안전).
    ( shopt -s dotglob nullglob; for f in "$src"/*; do
        [ -e "$dst/$(basename "$f")" ] || mv "$f" "$dst/"
      done )
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
  # DATABASE_URL 은 **기존 값을 존중한다.** 옛 slug 설치를 이전한 경우 그 DB 를 계속 쓴다 —
  # 데이터가 거기 있고, 이름을 바꾸는 것은 이 스크립트의 일이 아니다.
  if [ "$created" = 1 ] || ! grep -qE '^DATABASE_URL=.+' "$ENV_FILE"; then
    env_set DATABASE_URL "postgresql://$PG_ROLE@/$PG_DB?host=/var/run/postgresql"
  fi

  local f
  for f in allowed-services.json allowed-runners.json allowed-workflows.json feature-flags.json; do
    if [ ! -f "$ETC_DIR/$f" ]; then
      cp "$APP_DIR/config/$f" "$ETC_DIR/$f"
    fi
    chown root:"$SVC_USER" "$ETC_DIR/$f"; chmod 0640 "$ETC_DIR/$f"
  done
  chmod 0700 "$SECRETS_DIR"; chown root:"$SVC_USER" "$SECRETS_DIR"
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
stage_9_migration() {
  local before after head
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
    # 🔴 관리자 계정을 여기서 만들지 않는다. 임시 비밀번호가 설치 로그에 남는다.
    _reason="기본 Role/Permission 은 마이그레이션이 넣었습니다. **관리자 계정이 아직 없습니다**"
    _action="sudo runuser -u $SVC_USER -- $APP_DIR/venv/bin/python -m app.cli.user_cli add --email <you> --role admin"
    say "  ⚠️ 관리자 계정이 없습니다. 만들기: $_action"
  else
    _reason="사용자 ${nusers}명 · 기본 Role/Permission 확인"
  fi
  return 0
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 11 — File Storage 준비
# ═════════════════════════════════════════════════════════════════════════════
stage_11_storage() {
  install -d -o "$SVC_USER" -g "$SVC_USER" -m 0750 "$VAR_DIR/uploads"
  runuser -u "$SVC_USER" -- test -w "$VAR_DIR/uploads" \
    || { fail "$VAR_DIR/uploads 에 서비스 계정이 쓸 수 없습니다" "소유권을 $SVC_USER 로 맞추십시오(OPS-01)" 31 || return $?; }
  # NFS/SMB Provider · 마운트 유닛 · st_dev 가드는 아직 제품에 없다 — S8(P-17)의 일이다.
  # 여기서 OK 를 찍으면 「Storage 를 설치했다」는 거짓말이 로그에 남는다.
  skip "로컬 업로드 디렉터리만 준비했습니다. NFS/SMB Provider·마운트 유닛·st_dev 가드는 아직 제품에 없습니다" \
       "S8(P-17)이 이 Stage 를 OK 로 바꿉니다" || return $?
}

# ═════════════════════════════════════════════════════════════════════════════
# Stage 12 — AI Component
# ═════════════════════════════════════════════════════════════════════════════
stage_12_ai() {
  if [ -d "$APP_DIR/app/ai/gateway" ]; then
    fail "AI Gateway 가 소스에 있는데 이 Stage 가 아직 그것을 설치하지 않습니다" \
      "S9(P-18)이 이 Stage 를 채워야 합니다 — INSTALLATION.md §6.1 Installer 계약" 32 || return $?
  fi
  skip "Model Gateway·임베딩/리랭킹 모델·ONNX Runtime 이 아직 제품에 없습니다" \
       "S9(P-18)이 이 Stage 를 OK 로 바꿉니다" || return $?
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
  # 색인 레인 유닛(clovirassist-index.service)은 여기 없다 — 그 Component 자체가 아직
  # 제품에 없다(S9 · P-18). INSTALLATION.md §6.1 대로 그 Session 이 유닛·probe·uninstall·
  # 복구를 함께 넣는다. 소스에 레인이 생겼는데 유닛이 없으면 아래에서 걸린다.
  if grep -q 'LANE_INDEX' "$APP_DIR/app/jobs/lanes.py" 2>/dev/null && [ ! -f "$APP_DIR/deploy/systemd/$SLUG-index.service" ]; then
    fail "색인 레인이 소스에 있는데 systemd 유닛이 없습니다" \
      "deploy/systemd/$SLUG-index.service 를 추가하고 ALL_UNITS 에 넣으십시오" 33 || return $?
  fi
  systemctl daemon-reload
  for u in "${ALL_UNITS[@]}"; do
    systemd-analyze verify "/etc/systemd/system/$u" >>"$LOG" 2>&1 || log "systemd-analyze verify 경고: $u"
  done
  _reason="유닛 ${#ALL_UNITS[@]}종 설치"
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
stage_16_nginx() {
  local site="/etc/nginx/sites-available/$NGINX_SITE"
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
    printf '  "alembic_head": %s,\n' "$(json_str "$head")"
    printf '  "postgres_version": %s,\n' "$(json_str "$pgver")"
    printf '  "extensions": %s,\n' "$(json_str "$extver")"
    printf '  "dns_name": %s,\n' "$(json_str "$DNS_NAME")"
    printf '  "bind_ip": %s,\n' "$(json_str "$BIND_IP")"
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

  vchk "실패한 제품 유닛이 없다" "[ -z \"\$(systemctl --failed --plain --no-legend 2>/dev/null | grep $SLUG)\" ]"

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
    echo "  git           : (bundle 설치이거나 git 트리가 아닙니다)"
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
# S12 가 만들 Backup **정책**(Schedule·Retention·Manifest)이 아니다. upgrade 가 되돌릴
# 지점을 남기기 위한 최소 스냅샷이다 — 그 이상을 여기서 만들면 S12 와 역할이 겹친다.
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
  local u
  for u in "${ALL_UNITS[@]}" "${LEGACY_UNITS[@]}"; do
    [ -f "/etc/systemd/system/$u" ] && cp "/etc/systemd/system/$u" "$dir/" || true
  done
  [ -f "/etc/nginx/sites-available/$NGINX_SITE" ] && cp "/etc/nginx/sites-available/$NGINX_SITE" "$dir/nginx-vhost.conf" || true

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
}

do_rollback() {
  local dir="$ROLLBACK_TARGET"
  if [ -z "$dir" ]; then
    dir="$(ls -1d "$BACKUP_ROOT"/*/ 2>/dev/null | sort | tail -1)"
    dir="${dir%/}"
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
  systemctl daemon-reload
  rm -f "/etc/nginx/sites-enabled/$NGINX_SITE" "/etc/nginx/sites-available/$NGINX_SITE" "/etc/logrotate.d/$SLUG"
  nginx -t >>"$LOG" 2>&1 && { systemctl reload nginx >>"$LOG" 2>&1 || true; }
  rm -rf "$APP_DIR" "$SSL_FALLBACK_DIR"
  rm -f /etc/systemd/timesyncd.conf.d/99-"$SLUG".conf /etc/systemd/resolved.conf.d/99-"$SLUG".conf
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

case "$SUBCOMMAND" in
  preflight)
    open_log
    run_stage 0 PREFLIGHT stage_0_preflight
    say "PREFLIGHT_OK"
    ;;
  install)
    open_log
    log "=== install 시작 (dns=$DNS_NAME bind=$BIND_IP source=${SOURCE_KIND:-auto}) ==="
    # 기존 설치 위에 다시 도는 install 은 되돌릴 지점을 먼저 만든다.
    if [ -f "$ENV_FILE" ] || legacy_present; then
      take_snapshot; say "스냅샷: $SNAPSHOT_DIR"
    fi
    run_all_stages
    say "INSTALL_OK dns=$DNS_NAME log=$LOG"
    ;;
  upgrade)
    open_log
    [ -f "$MANIFEST" ] || [ -f "$ENV_FILE" ] || legacy_present \
      || die "업그레이드할 기존 설치가 없습니다. 먼저 install 을 실행하십시오" 43
    # Source 위치를 사용자가 다시 알려 줄 필요가 없다 — manifest 가 들고 있다.
    [ -n "$GIT_REMOTE" ] || GIT_REMOTE="$(jq_get git_remote)"
    [ -n "$DNS_NAME" ] || DNS_NAME="$(jq_get dns_name)"
    [ -n "$BIND_IP" ] || BIND_IP="$(jq_get bind_ip)"
    log "=== upgrade 시작 (ref=${GIT_REF:-<현재>} remote=${GIT_REMOTE:-<현재>}) ==="
    take_snapshot; say "스냅샷: $SNAPSHOT_DIR"
    say "  실패하면 되돌리기: $SCRIPT_PATH rollback --target $SNAPSHOT_DIR"
    if [ -n "$GIT_REF" ] && [ -d "$APP_DIR/.git" ]; then
      [ -n "$GIT_REMOTE" ] && git -C "$APP_DIR" remote set-url origin "$GIT_REMOTE" >>"$LOG" 2>&1 || true
      git -C "$APP_DIR" fetch --tags --quiet >>"$LOG" 2>&1 \
        || die "원격에서 fetch 할 수 없습니다($GIT_REMOTE)" 43
    fi
    run_all_stages
    say "UPGRADE_OK ref=${GIT_REF:-<현재>} snapshot=$SNAPSHOT_DIR log=$LOG"
    ;;
  rollback)  open_log; do_rollback ;;
  uninstall) open_log; do_uninstall ;;
  verify)    do_verify || exit 1 ;;
  version)   do_version ;;
esac
