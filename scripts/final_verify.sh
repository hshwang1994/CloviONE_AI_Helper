#!/usr/bin/env bash
# 최종 검증 한 번에 (§C).
#
# 이 스크립트는 **모든 병렬 작업이 끝난 뒤에만** 뜻이 있다. 작업자가 트리를 편집하는 동안
# 돌리면 결과가 오염된다 — 실제로 그것 때문에 한 번 잘못된 결론을 냈다(계획서 0-E-14).
#
# 순서에 이유가 있다:
#   1) 정적 검사 먼저 — 몇 초 만에 끝나고, 여기서 걸리면 20분짜리 스위트를 돌릴 이유가 없다
#   2) 마이그레이션 왕복 — 스키마가 깨졌으면 그 뒤 전부가 무의미하다
#   3) 백엔드 스위트 — 가장 오래 걸린다
#   4) 프런트
#   5) **번들을 마지막에** 만든다 — 앞의 검사를 통과한 소스로만 만든다
#   6) 번들 신선도 기준 기록 + 검사
set -uo pipefail
cd "$(dirname "$0")/.."
export PYTHONIOENCODING=utf-8
PY=".venv/Scripts/python.exe"
[ -x "$PY" ] || PY="python"

FAILED=()
step() {
  local name="$1"; shift
  echo ""
  echo "=== $name ==="
  if "$@"; then
    echo "[OK ] $name"
  else
    echo "[FAIL] $name"
    FAILED+=("$name")
  fi
}

step "정적 검사" bash scripts/static_checks.sh
step "마이그레이션 왕복" bash scripts/migration_rehearsal.sh
step "백엔드 스위트" "$PY" -m pytest tests/ -q --tb=line -p no:randomly
step "프런트 스위트" bash -c 'cd frontend && npx vitest run'
step "번들 빌드" bash -c 'cd frontend && npx vite build'
step "번들 기준 기록" "$PY" scripts/check_bundle_fresh.py --write
step "번들 신선도" "$PY" scripts/check_bundle_fresh.py
step "번들 예산" bash scripts/check_bundle_size.sh

echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "FINAL_VERIFY_OK"
  exit 0
fi
echo "FINAL_VERIFY_FAILED: ${FAILED[*]}"
exit 1
