#!/usr/bin/env bash
# Build the deployment bundle (D2): LF-normalized source tree + offline wheelhouse
# + sha256 manifest. Run from the repo root on the control machine (Git Bash).
#   PY=py bash scripts/build-bundle.sh
set -euo pipefail
export LC_ALL=C.UTF-8

OUT="${OUT:-dist}"
STAGE="$OUT/stage"
PY="${PY:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
[ -x ".venv/Scripts/python.exe" ] && PY=".venv/Scripts/python.exe"

echo "== bundle freshness gate (frontend/src vs app/static/react) =="
# 이 스크립트는 지금 워킹트리의 app/static/react 를 그대로 패키징한다 - 프런트를 다시
# 빌드하지 않는다. 그래서 이 게이트가 없으면 소스만 고치고 `npm run build` 를 깜빡해도
# 조용히 "성공"하고, 배포되는 건 옛 화면이다. check_bundle_fresh.py 자신의 문서가 적어 둔
# 바로 그 사고이고, 실제로 여기서도 한 번 재현됐다(번들을 새로 안 만든 채 build-bundle.sh
# 만 돌려 배포한 뒤에야 발견) - `--write` 는 지금 소스 해시를 무조건 다시 적기 때문에,
# 빌드를 빼먹고 `--write` 만 돌리면 "최신"이라고 자기암시가 걸린다. 여기서는 plain 모드로
# 검증만 하고 스스로 빌드하지 않는다 - 무엇으로 만들 번들인지는 운영자가 명시적으로 정한다.
if ! "$PY" scripts/check_bundle_fresh.py; then
  echo "[FAIL] app/static/react 가 frontend/src 보다 낡았다 - 이 상태로 패키징하면 옛 화면이 배포된다." >&2
  echo "        고치는 법: cd frontend && npm run build && cd .. && $PY scripts/check_bundle_fresh.py --write" >&2
  exit 1
fi

rm -rf "$STAGE"
mkdir -p "$STAGE/app-src" "$STAGE/wheels"

echo "== copy source (excluding dev artifacts) =="
# rsync if available, else tar-based copy
#
# `.claude` 를 빼는 이유: 에이전트 작업용 worktree 가 그 아래 쌓인다. 실제로 88벌
# (398MB)이 들어가 매니페스트 31,998항목 중 **31,154개(97%)가 .claude** 였고,
# 실제 앱은 844개뿐이었다. install 스크립트가 app-src 를 그대로 /opt 에 rsync 하므로
# 운영 서버에 옛 코드 사본 88벌이 깔린다 — 용량도 문제지만, 서버를 들여다보는 사람이
# 어느 것이 도는 코드인지 알 수 없게 되는 쪽이 더 나쁘다.
# `docs` 도 뺀다 — 운영에서 읽히지 않고 배포 산출물이 커질 이유가 없다.
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.git' --exclude 'var' --exclude '.venv' --exclude 'dist' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
    --exclude '.pytest_cache' --exclude 'node_modules' --exclude '.claude' \
    ./ "$STAGE/app-src/"
else
  tar --exclude='.git' --exclude='var' --exclude='.venv' --exclude='dist' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
      --exclude='.pytest_cache' --exclude='node_modules' --exclude='.claude' \
      -cf - . | tar -xf - -C "$STAGE/app-src"
fi

# 안전망: 위 제외가 어떤 이유로든 빠져나가면 여기서 걸린다. 배포 산출물에 저장소
# 사본이 섞이는 것은 조용히 지나가면 안 되는 종류의 사고다.
if [ -d "$STAGE/app-src/.claude" ]; then
  echo "[FAIL] 번들에 .claude 가 들어갔다 — 에이전트 worktree 사본이 운영에 실린다" >&2
  exit 1
fi

echo "== LF-normalize shell scripts =="
find "$STAGE/app-src" -name '*.sh' -exec sed -i 's/\r$//' {} +

echo "== build offline wheelhouse (manylinux cp312) =="
"$PY" -m pip download \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --implementation cp --python-version 3.12 --abi cp312 --abi abi3 --abi none \
  -d "$STAGE/wheels" -r requirements.txt || {
    echo "WARN: platform-specific wheel download had issues; retrying generic"; }
# AI 실행 환경(S9 · D-258). 같은 wheelhouse 에 넣는 이유: Stage 12 는 `--offline` 일 때
# 이 wheelhouse 하나만 본다. 안 넣으면 폐쇄망에서 `--with-ai` 가 그 자리에서 막힌다.
#
# **실패해도 번들을 안 죽인다.** AI 를 안 쓰는 설치가 훨씬 흔하고, 그 번들도 여전히
# 쓸 수 있어야 한다. 대신 경고를 남긴다 — 조용히 빠지면 폐쇄망에서 처음 알게 된다.
"$PY" -m pip download \
  --only-binary=:all: \
  --platform manylinux2014_x86_64 --platform manylinux_2_17_x86_64 --platform manylinux_2_28_x86_64 \
  --implementation cp --python-version 3.12 --abi cp312 --abi abi3 --abi none \
  -d "$STAGE/wheels" -r requirements-ai.txt || {
    echo "WARN: AI wheel 을 못 받았다 — 이 번들로는 --offline --with-ai 설치가 안 된다"; }
"$PY" -m pip download --only-binary=:all: -d "$STAGE/wheels" pip setuptools wheel || true

echo "== manifest =="
# `! -name MANIFEST.sha256` 가 없으면 안 된다. 리다이렉트가 find 보다 먼저 파일을 만들기 때문에
# find 가 그 빈 파일을 목록에 넣고 그때의 해시(=빈 파일)를 적는데, 다 쓰고 나면 내용이 달라져
# **자기 자신과 절대 일치하지 않는다.** 그 결과 `sha256sum -c MANIFEST.sha256` 이 모든 번들에서
# 항상 "1 computed checksum did NOT match" 로 exit 1 이었다.
#
# 늘 실패하는 검사는 없는 검사보다 나쁘다 — 운영자가 그 한 줄을 정상으로 학습하고 나면, 진짜로
# 파일 하나가 깨진 번들도 똑같아 보인다. 실제로 이 저장소의 배포 절차서가 이 명령을 무결성
# 확인 단계로 적어 두고 있다(docs/MAINTENANCE_PLAYBOOK.md §2-3).
( cd "$STAGE" && find . -type f ! -name MANIFEST.sha256 -exec sha256sum {} + > MANIFEST.sha256 )

echo "== tarball =="
tar czf "$OUT/clovirassist-bundle.tar.gz" -C "$OUT" stage
( cd "$OUT" && sha256sum clovirassist-bundle.tar.gz > bundle.sha256 )

echo "BUNDLE_OK $OUT/clovirassist-bundle.tar.gz"
ls -la "$STAGE/wheels" | head -5
echo "wheels: $(ls "$STAGE/wheels" | wc -l)"
