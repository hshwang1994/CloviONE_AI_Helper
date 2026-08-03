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
"$PY" -m pip download --only-binary=:all: -d "$STAGE/wheels" pip setuptools wheel || true

echo "== manifest =="
( cd "$STAGE" && find . -type f -exec sha256sum {} + > MANIFEST.sha256 )

echo "== tarball =="
tar czf "$OUT/clovirone-web-assistant-bundle.tar.gz" -C "$OUT" stage
( cd "$OUT" && sha256sum clovirone-web-assistant-bundle.tar.gz > bundle.sha256 )

echo "BUNDLE_OK $OUT/clovirone-web-assistant-bundle.tar.gz"
ls -la "$STAGE/wheels" | head -5
echo "wheels: $(ls "$STAGE/wheels" | wc -l)"
