#!/usr/bin/env bash
# 커밋한 소스를 랩 서버로 보내고 `install.sh upgrade` 를 돌린다.
#
# ## 왜 이 스크립트가 필요한가
#
# `apply-static-update.sh` 는 `app/static` 만 바꾼다 — 프런트만 고친 회차에는 그것으로
# 충분하지만, 백엔드나 **마이그레이션**이 낀 회차는 소스 전체가 가야 하고 alembic 이
# 돌아야 한다. 그 두 단계를 매번 손으로 옮기면 실수 지점이 생긴다(파일 하나를 빠뜨린 채
# 「배포했다」고 기록하는 것).
#
# ## 무엇을 보내는가 — `git archive HEAD`
#
# `rsync` 가 이 경로에 없다. 그리고 **작업 트리가 아니라 커밋을 보낸다** — 배포된 것이
# 어느 커밋인지 나중에 말할 수 있어야 하고, 커밋 안 한 실험이 서버로 새면 안 된다.
#
# ## 자격증명 취급 (CLAUDE.md 불변규칙 3)
#
# 접속 정보와 sudo 비밀번호는 `dist/ops/server.env`(gitignore)에서만 읽는다. 비밀번호는
# `sudo -S` 의 **stdin** 으로만 건넨다 — 명령행·로그·원격 `ps` 어디에도 안 남는다.
# `echo "$PW" | ssh` 형태로 원격 명령행에 넣지 않는다(그러면 서버 프로세스 목록에 뜬다).
#
# ## 쓰는 법
#
#   bash scripts/deploy-upgrade.sh
set -uo pipefail
export LC_ALL=C.UTF-8

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

ENV_FILE="${CLOVIR_OPS_ENV:-dist/ops/server.env}"
[ -f "$ENV_FILE" ] || { echo "FAIL: $ENV_FILE 가 없다"; exit 2; }
# shellcheck disable=SC1090
set -a; . "$ENV_FILE"; set +a
: "${SERVER:?SERVER 가 $ENV_FILE 에 없다}"
: "${SUDO_PW:?SUDO_PW 가 $ENV_FILE 에 없다}"

REMOTE_SRC="clovirassist-upgrade"
REF="${1:-HEAD}"
SHA="$(git rev-parse --short "$REF")"

echo "== 커밋 $SHA 를 tar 로 만든다 =="
git status --porcelain | grep -q . && {
  echo "FAIL: 작업 트리가 깨끗하지 않다 — 커밋한 것만 보낸다"; exit 1; }
TARBALL="dist/upgrade-src.tar.gz"
mkdir -p dist
git archive --format=tar.gz -o "$TARBALL" "$REF" || { echo "FAIL: git archive"; exit 1; }
ls -l "$TARBALL"

echo "== 보낸다 =="
# 옛 소스를 지우고 새로 푼다 — 지운 파일이 서버에 남으면 「배포했는데 옛 코드가 돈다」가 된다.
ssh -o BatchMode=yes "$SERVER" "rm -rf ~/$REMOTE_SRC && mkdir -p ~/$REMOTE_SRC" \
  || { echo "FAIL: 원격 정리"; exit 1; }
scp -q "$TARBALL" "$SERVER:~/$REMOTE_SRC/src.tar.gz" || { echo "FAIL: scp"; exit 1; }
ssh -o BatchMode=yes "$SERVER" "cd ~/$REMOTE_SRC && tar -xzf src.tar.gz && rm src.tar.gz && echo EXTRACT_OK" \
  || { echo "FAIL: 원격 해제"; exit 1; }

echo "== upgrade (sudo -S, 비밀번호는 stdin 으로만) =="
printf '%s\n' "$SUDO_PW" | ssh -o BatchMode=yes "$SERVER" \
  "sudo -S -p '' bash ~/$REMOTE_SRC/deploy/install.sh upgrade --source local --yes" 2>&1 \
  | grep -v '^\[sudo\]'
