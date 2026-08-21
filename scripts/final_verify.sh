#!/usr/bin/env bash
# 최종 검증 한 번에 (§C).
#
# 이 스크립트는 **모든 병렬 작업이 끝난 뒤에만** 뜻이 있다. 작업자가 트리를 편집하는 동안
# 돌리면 결과가 오염된다 — 실제로 그것 때문에 한 번 잘못된 결론을 냈다(계획서 0-E-14).
#
# 순서에 이유가 있다:
#   1) 정적 검사 먼저 — 몇 초 만에 끝나고, 여기서 걸리면 20분짜리 스위트를 돌릴 이유가 없다
#   2) **번들 신선도 — 빌드 «전에», 커밋된 상태를 본다**
#   3) 마이그레이션 왕복 — 스키마가 깨졌으면 그 뒤 전부가 무의미하다
#   4) 백엔드 스위트 — 가장 오래 걸린다
#   5) 프런트
#   6) **번들을 마지막에** 만들고 **그 자리에서** 기준을 적는다
#
# 🔴 2번이 왜 앞으로 왔는가 (S1):
#   예전 순서는 `--write` 로 기준을 적은 **바로 다음 줄**에서 같은 검사를 돌렸다. 방금 적은
#   기준과 방금 만든 번들을 비교하니 **그 검사는 절대 실패할 수 없었다** — 초록이 아무것도
#   증명하지 않는 자리였다. 이 검사가 실제로 잡아야 하는 상태는 «소스는 고쳤는데 커밋된
#   번들이 옛것» 이고, 그건 **빌드 전에만** 보인다. 그래서 검사는 앞으로, `--write` 는 빌드
#   스텝에 붙였다.
#   빌드 전 검사가 빨갛게 나오면 그게 정상 동작이다 — 아래 6번이 번들을 새로 만들어 두므로
#   커밋한 뒤 다시 돌리면 초록이 된다.
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

build_and_stamp() {
  ( cd frontend && npx vite build ) && "$PY" scripts/check_bundle_fresh.py --write
}

step "정적 검사" bash scripts/static_checks.sh
step "번들 신선도(커밋된 상태)" "$PY" scripts/check_bundle_fresh.py
step "마이그레이션 왕복" bash scripts/migration_rehearsal.sh
step "백엔드 스위트" "$PY" -m pytest tests/ -q --tb=line -p no:randomly
step "프런트 스위트" bash -c 'cd frontend && npx vitest run'
step "번들 빌드 + 기준 기록" build_and_stamp
step "번들 예산" bash scripts/check_bundle_size.sh

echo ""
if [ ${#FAILED[@]} -eq 0 ]; then
  echo "FINAL_VERIFY_OK"
  exit 0
fi
echo "FINAL_VERIFY_FAILED: ${FAILED[*]}"
exit 1
