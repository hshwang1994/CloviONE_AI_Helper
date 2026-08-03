#!/usr/bin/env bash
# 프런트 번들 예산 검사.
#
# 왜 필요한가: MUI를 들이면서 초기 번들이 한 번에 40% 늘었다. 예산이 없으면 화면을 하나씩
# 만들 때마다 조금씩 늘다가, 어느 날 "왜 이렇게 느리지"로 돌아온다. 빌드에서 바로 막는다.
#
# 무엇을 재는가: **초기 로드에 필요한 청크만** 센다. React.lazy로 분리된 화면(Chat/GameRoom/
# DevReport)은 그 화면에 들어갈 때만 받으므로 초기 예산에서 뺀다.
#
# 왜 gzip이 기준인가: 사내 LAN이라 네트워크는 빠르지만 nginx가 gzip으로 내보내고, 실제로
# 전송되는 바이트가 gzip 크기다. 원본 크기는 파싱·실행 비용의 지표라 경고로만 둔다.
set -u

cd "$(dirname "$0")/.."
DIR="app/static/react/assets"

GZIP_BUDGET_KB=${GZIP_BUDGET_KB:-280}
RAW_WARN_KB=${RAW_WARN_KB:-1000}
CSS_BUDGET_KB=${CSS_BUDGET_KB:-120}

# 초기 로드 청크: 지연 로딩 청크를 제외한 나머지.
# 관리자/사용자 콘솔은 통째로 별도 청크다 — 서로 다른 사람이 쓰므로 둘 다 받을 이유가 없다.
# registry는 관리자 16화면의 설정 덩어리(1,870줄)라 함께 늦게 온다.
LAZY_RE='^(Chat|GameRoom|DevReport|AdminRoutes|UserRoutes|registry)\.'

if [ ! -d "$DIR" ]; then
  echo "번들이 없다: $DIR — 먼저 'cd frontend && npm run build'" >&2
  exit 1
fi

total_gzip=0
total_raw=0
css_raw=0
echo "== 초기 로드 청크 =="
for f in "$DIR"/*.js; do
  [ -f "$f" ] || continue
  base="$(basename "$f")"
  if echo "$base" | grep -qE "$LAZY_RE"; then
    printf "  (지연) %-28s %6s KB\n" "$base" "$(( $(wc -c < "$f") / 1024 ))"
    continue
  fi
  raw=$(wc -c < "$f")
  gz=$(gzip -c "$f" | wc -c)
  total_raw=$((total_raw + raw))
  total_gzip=$((total_gzip + gz))
  printf "         %-28s %6s KB  (gzip %5s KB)\n" "$base" "$((raw / 1024))" "$((gz / 1024))"
done

for f in "$DIR"/*.css; do
  [ -f "$f" ] || continue
  css_raw=$((css_raw + $(wc -c < "$f")))
done

gz_kb=$((total_gzip / 1024))
raw_kb=$((total_raw / 1024))
css_kb=$((css_raw / 1024))

echo ""
echo "초기 JS  : ${raw_kb} KB (gzip ${gz_kb} KB)   예산 gzip ${GZIP_BUDGET_KB} KB"
echo "CSS      : ${css_kb} KB                      예산 ${CSS_BUDGET_KB} KB"

fail=0
if [ "$gz_kb" -gt "$GZIP_BUDGET_KB" ]; then
  echo "[FAIL] 초기 JS gzip ${gz_kb} KB > 예산 ${GZIP_BUDGET_KB} KB" >&2
  echo "       무거운 화면을 React.lazy로 빼거나, 큰 의존성을 쓰는 곳을 줄여라." >&2
  fail=1
fi
if [ "$css_kb" -gt "$CSS_BUDGET_KB" ]; then
  echo "[FAIL] CSS ${css_kb} KB > 예산 ${CSS_BUDGET_KB} KB" >&2
  fail=1
fi
if [ "$raw_kb" -gt "$RAW_WARN_KB" ]; then
  echo "[WARN] 초기 JS 원본 ${raw_kb} KB > ${RAW_WARN_KB} KB — 전송량은 괜찮아도 파싱·실행이 무거워진다." >&2
fi

if [ "$fail" -eq 0 ]; then echo "BUNDLE_BUDGET_OK"; else echo "BUNDLE_BUDGET_FAILED"; fi
exit $fail
