#!/usr/bin/env bash
# git clone 한 설치본을 최신 커밋으로 올린다 (P5).
#
#   fetch -> 무엇이 바뀌는지 먼저 보여 준다 -> (확인) -> 코드 교체 -> 번들 신선도 검사
#   -> 서비스 정지 -> 백업 -> 설치(마이그레이션 포함) -> 검증 -> 실패하면 되돌린다
#
# 사용법 (root):
#   DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 \
#     bash scripts/update-from-git.sh [--ref origin/main] [--dry-run] [--yes]
#
# ── 롤백이 실제로 무엇을 되돌리는가 (읽고 시작하라) ──────────────────────────
#
# 이 스크립트는 `alembic downgrade` 를 **쓰지 않는다.** 되돌릴 때는 백업해 둔 DB 파일을
# 통째로 제자리에 놓는다. 그래서:
#
#   * 되돌릴 수 없는 마이그레이션(컬럼을 지우는 것 등)이 섞여 있어도 이 자리에서의
#     자동 롤백은 안전하다. 스키마도 데이터도 백업 시점 그대로 돌아온다.
#   * 대신 **백업 이후에 쓰인 데이터는 사라진다.** 그래서 백업을 서비스를 멈춘 뒤에
#     뜬다 - 그러면 "백업 이후"라는 창이 사실상 없다.
#   * ⚠️ 문제는 나중이다. 업데이트가 성공해서 사람들이 새 버전으로 하루를 일한 뒤에
#     되돌리고 싶어지면, 되돌리는 방법은 그 백업을 복원하는 것뿐이다. 즉 **그 하루치
#     작업을 버려야 한다.** 되돌릴 수 없는 마이그레이션이 있으면 다른 길이 없다.
#     그래서 시작할 때 그런 마이그레이션이 있는지 먼저 알려 주고 확인을 받는다.
#
# 판정은 어림짐작이다(파일을 읽어서 downgrade() 가 비어 있는지, upgrade() 가 테이블·
# 컬럼을 지우는지 본다). 놓칠 수 있으므로, 경고가 없다고 "되돌릴 수 있다"는 뜻은 아니다.
set -euo pipefail
export LC_ALL=C.UTF-8

case "$(head -c 400 "$0" 2>/dev/null)" in *$'\r'*) echo "CRLF in script"; exit 64;; esac
[[ "${EUID}" -eq 0 ]] || { echo "root 권한이 필요합니다"; exit 1; }

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_DIR="${REPO_DIR:-$(cd "$SCRIPT_DIR/.." && pwd)}"
APP_DIR=/opt/clovirone-web-assistant

REF=""
DRY_RUN=0
ASSUME_YES=0
while [ "$#" -gt 0 ]; do
  case "$1" in
    --ref) REF="${2:-}"; shift 2 || true ;;
    --ref=*) REF="${1#--ref=}"; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --yes|-y) ASSUME_YES=1; shift ;;
    -h|--help) sed -n '2,30p' "$0"; exit 0 ;;
    *) echo "모르는 인자: $1"; exit 64 ;;
  esac
done

# 롤백에 필요한 상태. 아직 아무것도 안 했다는 뜻으로 비워 둔다.
CURRENT_SHA=""
BACKUP_DIR=""

say() { echo "$*"; }
hr()  { echo "------------------------------------------------------------"; }

git_repo() { git -C "$REPO_DIR" "$@"; }

# ── 되돌리기 ────────────────────────────────────────────────────────────────
rollback_now() {
  local why="$1"
  echo ""
  hr
  say "업데이트 실패: $why"
  say "되돌립니다."
  hr
  if [ -n "$CURRENT_SHA" ]; then
    if git_repo reset --hard --quiet "$CURRENT_SHA"; then
      say "[OK ] 저장소를 ${CURRENT_SHA:0:12} 로 되돌렸습니다"
    else
      say "[FAIL] git reset 실패. 손으로: git -C $REPO_DIR reset --hard $CURRENT_SHA"
    fi
  fi
  if [ -n "$BACKUP_DIR" ] && [ -d "$BACKUP_DIR" ]; then
    say "복원 중: $BACKUP_DIR"
    if bash "$REPO_DIR/scripts/rollback-clovirone-web-assistant.sh" "$BACKUP_DIR"; then
      say "UPDATE_ROLLED_BACK $BACKUP_DIR"
      exit 30
    fi
    say "[FAIL] 자동 복원이 끝나지 못했습니다. 서비스가 내려가 있을 수 있습니다."
    say "       확인: systemctl status clovirone-web-assistant"
    say "       재시도: bash $REPO_DIR/scripts/rollback-clovirone-web-assistant.sh $BACKUP_DIR"
    exit 40
  fi
  say "백업을 뜨기 전에 실패해서 코드만 되돌렸습니다. 서비스는 건드리지 않았습니다."
  exit 30
}

# ── 0. 사전 조건. 백업을 뜨기 전에 전부 확인한다 ─────────────────────────────
if [ -z "${DNS_NAME:-}" ] || [ -z "${BIND_IP:-}" ]; then
  say "DNS_NAME 과 BIND_IP 를 지정해야 합니다(설치 스크립트가 씁니다)."
  say "예: DNS_NAME=portal.example.internal BIND_IP=10.0.0.10 bash $0"
  exit 2
fi
if ! command -v git >/dev/null 2>&1; then
  say "git 이 없습니다. 이 스크립트는 git clone 으로 설치한 서버 전용입니다."
  exit 2
fi
# python3 와 curl 은 각각 번들 신선도 검사와 검증에 쓴다. 그 자리에서 없는 것을 알면
# 이미 코드를 갈아 끼운 뒤라 되돌릴 일이 생긴다. 시작하기 전에 확인한다.
for tool in python3 curl; do
  if ! command -v "$tool" >/dev/null 2>&1; then
    say "$tool 이 없습니다. 업데이트 도중에 필요합니다."
    exit 2
  fi
done
if ! git_repo rev-parse --is-inside-work-tree >/dev/null 2>&1; then
  say "$REPO_DIR 는 git 저장소가 아닙니다. 번들로 설치했다면 upgrade-clovirone-web-assistant.sh 를 쓰십시오."
  exit 2
fi
if [ ! -d "$APP_DIR" ]; then
  say "$APP_DIR 가 없습니다. 아직 설치되지 않았습니다."
  say "처음 설치라면: bash $REPO_DIR/scripts/install-clovirone-web-assistant.sh --from-repo"
  exit 2
fi
# 손으로 고친 것이 있으면 멈춘다. 아래에서 `git reset --hard` 를 쓰기 때문에, 이 확인이
# 없으면 되돌리는 순간 운영자가 서버에서 직접 고친 내용이 흔적 없이 사라진다.
if [ -n "$(git_repo status --porcelain)" ]; then
  say "설치용 clone 에 커밋되지 않은 변경이 있습니다. 그대로 두면 롤백이 그것을 지웁니다."
  say "확인: git -C $REPO_DIR status"
  say "버릴 생각이면: git -C $REPO_DIR reset --hard && git -C $REPO_DIR clean -fd"
  exit 2
fi

# ── 1. 가져오기 ─────────────────────────────────────────────────────────────
say "=== update from git ==="
say "저장소: $REPO_DIR"
say "가져오는 중(fetch)..."
if ! git_repo fetch --prune --tags --quiet; then
  say "fetch 실패. 원격에 닿지 못했습니다(폐쇄망이면 원격 미러 주소를 확인하십시오)."
  exit 4
fi

CURRENT_SHA="$(git_repo rev-parse HEAD)"
BRANCH="$(git_repo rev-parse --abbrev-ref HEAD)"
if [ -z "$REF" ]; then
  if [ "$BRANCH" = "HEAD" ]; then
    say "지금 HEAD 가 어느 브랜치에도 붙어 있지 않습니다. --ref 로 대상을 지정하십시오."
    exit 2
  fi
  REF="$(git_repo rev-parse --abbrev-ref --symbolic-full-name "@{upstream}" 2>/dev/null || true)"
  if [ -z "$REF" ]; then
    say "브랜치 $BRANCH 에 upstream 이 없습니다. --ref origin/$BRANCH 처럼 지정하십시오."
    exit 2
  fi
fi
if ! TARGET_SHA="$(git_repo rev-parse --verify --quiet "${REF}^{commit}")"; then
  say "그런 대상이 없습니다: $REF"
  exit 2
fi

# ── 2. 무엇이 바뀌는지 먼저 보여 준다 ────────────────────────────────────────
CUR_VERSION="$(git_repo show "$CURRENT_SHA:VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
NEW_VERSION="$(git_repo show "$TARGET_SHA:VERSION" 2>/dev/null | tr -d '[:space:]' || true)"
hr
say "현재  : ${CUR_VERSION:-(버전 파일 없음)}  ${CURRENT_SHA:0:12}  $(git_repo log -1 --format=%cs "$CURRENT_SHA")"
say "대상  : ${NEW_VERSION:-(버전 파일 없음)}  ${TARGET_SHA:0:12}  $(git_repo log -1 --format=%cs "$TARGET_SHA")  ($REF)"
hr

if [ "$CURRENT_SHA" = "$TARGET_SHA" ]; then
  say "이미 최신입니다. 할 일이 없습니다."
  exit 0
fi
if ! git_repo merge-base --is-ancestor "$CURRENT_SHA" "$TARGET_SHA"; then
  say "⚠️ 대상이 현재 커밋의 자손이 아닙니다(되감기 또는 갈라진 이력)."
  say "   내려가는 배포일 수 있습니다. 마이그레이션이 이미 적용돼 있으면 앱이 뜨지 않습니다."
fi

COMMITS="$(git_repo log --no-merges --format='  %h %s' "$CURRENT_SHA..$TARGET_SHA" 2>/dev/null || true)"
COMMIT_COUNT="$(printf '%s\n' "$COMMITS" | grep -c . || true)"
say "변경 내역 ($COMMIT_COUNT 커밋):"
if [ -n "$COMMITS" ]; then
  printf '%s\n' "$COMMITS" | head -n 40
  [ "$COMMIT_COUNT" -gt 40 ] && say "  ... 그 밖에 $((COMMIT_COUNT - 40)) 개"
else
  say "  (없음)"
fi

hr
NEW_MIGRATIONS="$(git_repo diff --name-only --diff-filter=A "$CURRENT_SHA..$TARGET_SHA" -- alembic/versions/ | grep -E '\.py$' || true)"
CHANGED_MIGRATIONS="$(git_repo diff --name-only --diff-filter=M "$CURRENT_SHA..$TARGET_SHA" -- alembic/versions/ | grep -E '\.py$' || true)"

# 되돌릴 수 없어 보이는 마이그레이션인지 본다. 어림짐작이라는 것을 출력에도 적는다.
migration_risk() {
  local path="$1" body up down
  # `</dev/null` 인 이유: 이 함수는 아래에서 heredoc 을 stdin 으로 쓰는 while 루프 안에서
  # 불린다. 자식 명령이 그 stdin 을 한 입이라도 먹으면 목록의 나머지 줄이 사라지고,
  # 마이그레이션 몇 개를 조용히 건너뛴다.
  body="$(git_repo show "$TARGET_SHA:$path" 2>/dev/null </dev/null || true)"
  [ -n "$body" ] || return 1
  up="$(printf '%s\n' "$body" | sed -n '/^def upgrade/,/^def downgrade/p')"
  down="$(printf '%s\n' "$body" | sed -n '/^def downgrade/,$p')"
  if [ -z "$down" ]; then echo "downgrade() 가 없다"; return 0; fi
  if printf '%s\n' "$down" | grep -qE '^[[:space:]]+raise[[:space:]]'; then
    echo "downgrade() 가 예외를 던진다"; return 0
  fi
  if ! printf '%s\n' "$down" | grep -qE '^[[:space:]]+op\.'; then
    echo "downgrade() 가 비어 있다"; return 0
  fi
  if printf '%s\n' "$up" | grep -qE 'op\.drop_(table|column)\(|op\.execute\(.*(DELETE|TRUNCATE|UPDATE)'; then
    echo "upgrade() 가 테이블이나 컬럼을 지운다"; return 0
  fi
  return 1
}

IRREVERSIBLE=0
if [ -z "$NEW_MIGRATIONS" ]; then
  say "마이그레이션: 필요 없음 (새 마이그레이션 파일 없음)"
else
  say "마이그레이션: 필요함"
  while IFS= read -r m; do
    [ -n "$m" ] || continue
    if REASON="$(migration_risk "$m")"; then
      IRREVERSIBLE=$((IRREVERSIBLE + 1))
      say "  [되돌릴 수 없음] $m  ($REASON)"
    else
      say "  [적용] $m"
    fi
  done <<EOF
$NEW_MIGRATIONS
EOF
fi
if [ -n "$CHANGED_MIGRATIONS" ]; then
  say "⚠️ 이미 있던 마이그레이션 파일이 수정되었습니다. 이 서버에는 옛 내용이 이미 적용돼"
  say "   있어서, 수정분은 저절로 반영되지 않습니다. 손으로 확인하십시오:"
  printf '%s\n' "$CHANGED_MIGRATIONS" | sed 's/^/     /'
fi

if [ "$IRREVERSIBLE" -gt 0 ]; then
  hr
  say "⚠️ 되돌릴 수 없는 마이그레이션 ${IRREVERSIBLE}개가 들어 있습니다."
  say "   지금 이 업데이트가 실패하면, 이 스크립트는 백업한 DB 파일을 그대로 되돌립니다."
  say "   그 자리에서는 안전합니다(서비스를 멈춘 뒤 백업을 뜨기 때문입니다)."
  say "   문제는 나중입니다. 새 버전으로 며칠 일한 뒤 되돌리고 싶어지면, 방법은 그때의"
  say "   백업을 복원하는 것뿐이고 그 사이의 작업은 사라집니다. 다른 길이 없습니다."
  say "   판정은 어림짐작이라 놓칠 수 있습니다. 경고가 없다고 안전하다는 뜻은 아닙니다."
fi
hr

if [ "$DRY_RUN" = 1 ]; then
  say "--dry-run 이라 여기서 멈춥니다. 아무것도 바꾸지 않았습니다."
  exit 0
fi

if [ "$ASSUME_YES" != 1 ]; then
  if [ ! -t 0 ]; then
    say "확인 입력을 받을 수 없는 환경입니다. 계속하려면 --yes 를 붙이십시오."
    exit 3
  fi
  printf '계속하시겠습니까? [y/N] '
  read -r ANSWER
  case "$ANSWER" in
    y|Y|yes|YES) ;;
    *) say "중단했습니다. 아무것도 바꾸지 않았습니다."; exit 0 ;;
  esac
fi

# ── 3. 코드 교체. 서비스는 아직 건드리지 않는다 ──────────────────────────────
# 실행 중인 앱은 /opt 에서 돌기 때문에, 여기서 clone 을 옮겨도 서비스는 그대로 산다.
# 다음 단계(번들 신선도)에서 걸리면 **무정지로** 되돌아갈 수 있다.
say "코드 교체: ${CURRENT_SHA:0:12} -> ${TARGET_SHA:0:12}"
if ! git_repo reset --hard --quiet "$TARGET_SHA"; then
  say "git reset 실패. 아무것도 바꾸지 않았습니다."
  exit 4
fi

# ── 4. 번들 신선도. 서비스를 멈추기 전에 본다 ────────────────────────────────
# 여기서 걸리면 배포하지 않는 것이 맞다. 통과시키면 이 서버는 옛 화면을 조용히 계속 쓴다.
say "번들 신선도 검사..."
if ! python3 "$REPO_DIR/scripts/check_bundle_fresh.py"; then
  say ""
  say "커밋된 프런트 번들이 소스보다 낡았습니다. 이 커밋은 배포하면 안 됩니다."
  say "서비스는 건드리지 않았습니다. 코드를 원래대로 되돌립니다."
  git_repo reset --hard --quiet "$CURRENT_SHA" || true
  exit 21
fi

# ── 5. 서비스 정지 -> 백업 ───────────────────────────────────────────────────
# 순서가 중요하다. 백업을 먼저 뜨고 멈추면 그 사이에 쓰인 데이터가 롤백 때 사라진다.
say "서비스 정지(worker 먼저 - 진행 중인 잡을 마치게 한다)..."
systemctl stop clovirone-web-worker.service 2>/dev/null || true
systemctl stop clovirone-web-assistant.service 2>/dev/null || true

say "백업..."
BACKUP_OUT="$(bash "$REPO_DIR/scripts/backup-clovirone-web-assistant.sh" 2>&1 || true)"
printf '%s\n' "$BACKUP_OUT"
BACKUP_DIR="$(printf '%s\n' "$BACKUP_OUT" | sed -n 's/^BACKUP_OK //p' | tail -1)"
if [ -z "$BACKUP_DIR" ] || [ ! -d "$BACKUP_DIR" ]; then
  BACKUP_DIR=""
  say "백업이 만들어지지 않았습니다. 되돌릴 지점 없이 진행하지 않습니다."
  say "서비스를 다시 올립니다."
  systemctl start clovirone-web-assistant.service 2>/dev/null || true
  systemctl start clovirone-web-worker.service 2>/dev/null || true
  exit 5
fi
say "되돌릴 지점: $BACKUP_DIR"

# ── 6. 설치 (원본 배포 + 의존성 + 마이그레이션 + 유닛 + nginx + 기동) ────────
say "설치(install --from-repo)..."
if ! DNS_NAME="$DNS_NAME" BIND_IP="$BIND_IP" \
     bash "$REPO_DIR/scripts/install-clovirone-web-assistant.sh" --from-repo; then
  rollback_now "설치 스크립트가 실패했습니다"
fi

# ── 7. 검증 ─────────────────────────────────────────────────────────────────
# validate-clovirone-web-assistant.sh 를 판정 기준으로 쓰지 않는 이유: 그 스크립트는
# 같은 서버의 n8n 까지 확인한다. n8n 이 없는 설치에서는 우리와 무관한 이유로 FAIL 이
# 나고, 그러면 멀쩡한 업데이트가 롤백된다. 여기서는 **우리 것만** 본다.
say "검증..."
VERIFY_FAIL=""
for i in $(seq 1 30); do
  if curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1; then break; fi
  sleep 1
done
curl -fsS http://127.0.0.1:8080/healthz >/dev/null 2>&1 || VERIFY_FAIL="healthz 응답 없음"
if [ -z "$VERIFY_FAIL" ]; then
  # readyz 는 DB 까지 본다. 마이그레이션이 어긋났을 때 healthz 만으로는 안 걸린다.
  curl -fsS http://127.0.0.1:8080/readyz >/dev/null 2>&1 || VERIFY_FAIL="readyz 실패(DB 또는 마이그레이션)"
fi
if [ -z "$VERIFY_FAIL" ]; then
  systemctl is-active --quiet clovirone-web-assistant.service || VERIFY_FAIL="web 서비스가 active 가 아님"
fi
if [ -z "$VERIFY_FAIL" ]; then
  systemctl is-active --quiet clovirone-web-worker.service || VERIFY_FAIL="worker 서비스가 active 가 아님"
fi
if [ -n "$VERIFY_FAIL" ]; then
  journalctl -u clovirone-web-assistant -n 50 --no-pager 2>/dev/null || true
  rollback_now "$VERIFY_FAIL"
fi

hr
say "[OK ] healthz / readyz / web / worker"
# 여기서부터는 참고용이다. 실패해도 롤백하지 않는다(n8n 등 우리 것이 아닌 항목이 섞여 있다).
if [ -x "$REPO_DIR/scripts/validate-clovirone-web-assistant.sh" ] || [ -f "$REPO_DIR/scripts/validate-clovirone-web-assistant.sh" ]; then
  say "참고: 전체 검증 스크립트 결과(판정에는 쓰지 않습니다)"
  DNS_NAME="$DNS_NAME" bash "$REPO_DIR/scripts/validate-clovirone-web-assistant.sh" 2>&1 | sed 's/^/  /' || true
fi
hr
say "이전 버전으로 되돌리려면:"
say "  bash $REPO_DIR/scripts/rollback-clovirone-web-assistant.sh $BACKUP_DIR"
say "  git -C $REPO_DIR reset --hard $CURRENT_SHA"
if [ "$IRREVERSIBLE" -gt 0 ]; then
  say "  (되돌릴 수 없는 마이그레이션이 있었습니다. 위 복원은 그 백업 시점으로 돌아갑니다.)"
fi
say "UPDATE_OK ${CURRENT_SHA:0:12} -> ${TARGET_SHA:0:12}"
