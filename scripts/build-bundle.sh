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
if command -v rsync >/dev/null 2>&1; then
  rsync -a \
    --exclude '.git' --exclude 'var' --exclude '.venv' --exclude 'dist' \
    --exclude '__pycache__' --exclude '*.pyc' --exclude '.env' \
    --exclude '.pytest_cache' --exclude 'node_modules' \
    ./ "$STAGE/app-src/"
else
  tar --exclude='.git' --exclude='var' --exclude='.venv' --exclude='dist' \
      --exclude='__pycache__' --exclude='*.pyc' --exclude='.env' \
      --exclude='.pytest_cache' --exclude='node_modules' -cf - . | tar -xf - -C "$STAGE/app-src"
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
