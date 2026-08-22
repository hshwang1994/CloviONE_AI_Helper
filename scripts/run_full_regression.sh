#!/usr/bin/env bash
# PA-RC-0009 — 백엔드 전체 회귀(2,903건, CLAUDE.md §12 "Backend full")를 완주 가능한
# 청크로 나눠 돌리고 exit code를 합산한다.
#
# 왜 필요했나: 단일 `pytest` 호출은 45분+ 걸려 세션/호출 경계를 못 넘는다(Product Audit
# PA-RC-0009 실측 — 두 번 시도해 27%·49%에서 잘렸다). 그 결과 `docs/WORK_STATE.md`가
# 세 사이클 동안 이것을 "진짜 행(hang)"으로 잘못 기록했다. tests/unit·tests/regression·
# tests/security는 각각 단독 실행하면 완주하고, tests/integration(1,313건)만 알파벳순
# 파일 목록을 4등분한 **고정 청크**로 나눈다 — 매번 같은 파일 목록이면 같은 경계로
# 나뉘어야 재현 가능하다(PA-RC-0009 regression_risk: 청크 분할이 순서 의존 결함을 가릴
# 수 있으니 경계를 고정해 재현 가능하게 할 것).
set -uo pipefail
export LC_ALL=C.UTF-8

PY="${PY:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
[ -x ".venv/Scripts/python.exe" ] && PY=".venv/Scripts/python.exe"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

START=$(date +%s)
FAIL=0
step() { echo ""; echo "== $1 =="; }

run_suite() {
  local name="$1"; shift
  step "$name"
  # 🔴 `< /dev/null` 이 없으면 **영원히 멈춘다** (P-09e). `tests/regression/
  # test_stage_static_update.py` 가 `subprocess.run(capture_output=True, timeout=300)` 으로
  # 셸 스크립트를 부르는데, 이 러너를 백그라운드로 돌리면 stdin 이 **안 닫힌 파이프**라
  # 그 자식이 stdin 을 읽다 막힌다. 파이썬의 `timeout=` 은 **손자 프로세스를 안 죽여서**
  # 파이프가 안 닫히고, 그래서 5분이 지나도 안 풀린다.
  #
  # 증상이 고약하다: pytest 가 한 자리에서 멈추고 **CPU 도 0** 이라 「오래 걸리는 시험」과
  # 구별되지 않는다. S5 가 여기서 두 번 걸려 완주한 회귀를 두 번 버렸다.
  # 근본 조치는 그 시험이 `stdin=subprocess.DEVNULL` 을 넘기는 것이다(P-09e).
  if "$PY" -m pytest "$@" -q < /dev/null; then
    echo "[OK ] $name"
  else
    echo "[FAIL] $name"
    FAIL=1
  fi
}

run_suite "unit" tests/unit
run_suite "regression" tests/regression
run_suite "security" tests/security

# tests/integration: 파일 목록을 알파벳순으로 4등분한다. 테스트가 추가/삭제되면 경계도
# 자연히 다시 계산된다 — 파일명을 하드코딩하지 않는다.
mapfile -t INT_FILES < <(find tests/integration -maxdepth 1 -name 'test_*.py' | sort)
TOTAL=${#INT_FILES[@]}
CHUNK_SIZE=$(( (TOTAL + 3) / 4 ))
for i in 0 1 2 3; do
  IDX=$(( i * CHUNK_SIZE ))
  CHUNK=("${INT_FILES[@]:IDX:CHUNK_SIZE}")
  [ ${#CHUNK[@]} -eq 0 ] && continue
  run_suite "integration chunk $((i + 1))/4 (${#CHUNK[@]} files)" "${CHUNK[@]}"
done

END=$(date +%s)
ELAPSED=$(( END - START ))
echo ""
echo "elapsed: ${ELAPSED}s ($((ELAPSED / 60))m $((ELAPSED % 60))s)"
if [ "$FAIL" -eq 0 ]; then echo "FULL_REGRESSION_OK"; else echo "FULL_REGRESSION_FAILED"; fi
exit $FAIL
