#!/usr/bin/env bash
# `stage-static-update.sh` 가 인쇄만 하던 마지막 두 단계(전송·적용)를 실제로 실행한다.
#
# ## 왜 별도 스크립트인가
#
# `stage-static-update.sh` 는 tarball 을 만들고 **명령을 인쇄만** 한다. 그 설계는 옳다 —
# 사람이 읽고 복사할 문자열이면 설치처를 잘못 고를 위험이 있으니 기본값을 두지 않는 것이다.
# 다만 UI 리뉴얼처럼 Wave 마다 배포 → 실브라우저 재캡처를 반복하는 작업에서는 그 두 단계를
# 매번 손으로 옮기는 것이 실수 지점이 된다(파일 하나를 빠뜨린 채 "배포했다"고 기록하는 것).
#
# ## 자격증명 취급 (CLAUDE.md 불변규칙 3)
#
# 접속 정보와 sudo 비밀번호는 **`dist/ops/server.env`(gitignore)** 에서만 읽는다.
# 비밀번호는 `sudo -S` 의 **stdin** 으로만 건네고 명령행·로그·저장소 어디에도 남기지 않는다.
# 원격 명령행에도 나타나지 않는다(그러면 서버의 프로세스 목록에 노출된다).
#
# ## 쓰는 법
#
#   bash scripts/apply-static-update.sh                 # app/static 전체
#   bash scripts/apply-static-update.sh app/static/css/tokens.css ...
#
# 마지막에 **서버가 실제로 서브하는 바이트의 해시**를 로컬 스테이징 해시와 대조한다 —
# "적용했다"가 아니라 "브라우저가 받는 것이 바뀌었다"를 증명하는 것이 이 단계의 목적이다.
set -uo pipefail
export LC_ALL=C.UTF-8

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CLOVIR_OPS_ENV:-dist/ops/server.env}"
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE 가 없다 (설치처 고유값 + sudo 비밀번호)"; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${SERVER:?SERVER 가 $ENV_FILE 에 없다}"
: "${BASE_URL:?BASE_URL 가 $ENV_FILE 에 없다}"
: "${SUDO_PW:?SUDO_PW 가 $ENV_FILE 에 없다}"

APP_DIR="/opt/clovirone-web-assistant"
REMOTE_STAGE="deploy-static-update"
OUT="dist/static-update"

echo "== stage =="
SERVER="$SERVER" BASE_URL="$BASE_URL" bash scripts/stage-static-update.sh "$@" >/dev/null || {
  echo "FAIL: staging 실패"; exit 1; }
ls -l "$OUT/static-update.tar.gz"

echo "== copy =="
ssh -o BatchMode=yes "$SERVER" "mkdir -p ~/$REMOTE_STAGE" || { echo "FAIL: mkdir"; exit 1; }
scp -q "$OUT/static-update.tar.gz" "$OUT/SHA256SUMS.txt" "$SERVER:~/$REMOTE_STAGE/" || {
  echo "FAIL: scp"; exit 1; }

echo "== apply (sudo -S, 비밀번호는 stdin 으로만) =="
# `sudo -S -p ''` 는 프롬프트를 지우고 stdin 에서 비밀번호를 읽는다. 원격 셸의 명령행에는
# 비밀번호가 없다 — 서버 `ps` 에도 안 보인다.
printf '%s\n' "$SUDO_PW" | ssh -o BatchMode=yes "$SERVER" \
  "sudo -S -p '' tar -xzf ~/$REMOTE_STAGE/static-update.tar.gz -C $APP_DIR \
   && cd $APP_DIR && sudo -n sha256sum -c ~/$REMOTE_STAGE/SHA256SUMS.txt --quiet \
   && echo APPLY_OK" 2>&1 | grep -v '^\[sudo\]' || true

echo "== verify: 서버가 서브하는 바이트가 스테이징한 바이트와 같은가 =="
# `sha256sum` 은 `<hash> *<path>` 로 쓴다(별표는 바이너리 모드 표시다). 이 별표를 안 떼면
# 아래 경로 필터가 한 줄도 통과하지 못하고 **검증 0건인데 초록**이 된다 — 실제로 그랬다.
#
# 전 파일을 curl 로 받으면 수천 건이라 몇 분이 걸리고, 대부분은 이번에 안 바뀐 자산이다.
# 그래서 **이번에 바뀐 것**만 확인한다: git 이 변경으로 보는 `app/static/*` 파일 + 항상
# `react/index.html`(브라우저가 받는 진입점이자 배포 지문의 근거).
CHANGED="$(git status --porcelain -- app/static | awk '{print $NF}')"
ALWAYS="app/static/react/index.html"
TARGETS="$(printf '%s\n%s\n' "$CHANGED" "$ALWAYS" | sed '/^$/d' | sort -u)"

BAD=0
COUNT=0
while IFS= read -r f; do
  [ -n "$f" ] || continue
  case "$f" in app/static/*) : ;; *) continue ;; esac
  [ -f "$OUT/payload/$f" ] || continue
  want="$(sha256sum "$OUT/payload/$f" | cut -d' ' -f1)"
  rel="${f#app/static/}"
  got="$(curl -sk --max-time 30 "$BASE_URL/static/$rel" | sha256sum | cut -d' ' -f1)"
  COUNT=$((COUNT + 1))
  if [ "$got" != "$want" ]; then
    echo "  MISMATCH $rel"
    echo "    want $want"
    echo "    got  $got"
    BAD=$((BAD + 1))
  fi
done <<< "$TARGETS"

if [ "$COUNT" -eq 0 ]; then
  echo "STATIC_UPDATE_FAILED (검증 대상 0건 — 검증하지 않은 것을 통과라고 부르지 않는다)"
  exit 1
fi
if [ "$BAD" -ne 0 ]; then
  echo "STATIC_UPDATE_FAILED ($BAD/$COUNT 불일치)"
  exit 1
fi
echo "STATIC_UPDATE_OK ($COUNT 파일이 서버에서 스테이징본과 동일)"
