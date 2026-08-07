#!/usr/bin/env bash
# 프런트 번들 예산 검사.
#
# 왜 필요한가: MUI를 들이면서 초기 번들이 한 번에 40% 늘었다. 예산이 없으면 화면을 하나씩
# 만들 때마다 조금씩 늘다가, 어느 날 "왜 이렇게 느리지"로 돌아온다. 빌드에서 바로 막는다.
#
# 무엇을 재는가: **초기 로드에 필요한 청크만** 센다. React.lazy로 분리된 화면은 그 화면에
# 들어갈 때만 받으므로 초기 예산에서 뺀다 — index.html 에 없는 파일이 곧 그 화면들이다.
#
# 왜 gzip이 기준인가: 사내 LAN이라 네트워크는 빠르지만 nginx가 gzip으로 내보내고, 실제로
# 전송되는 바이트가 gzip 크기다. 원본 크기는 파싱·실행 비용의 지표라 경고로만 둔다.
set -u

cd "$(dirname "$0")/.."
DIR="app/static/react/assets"

GZIP_BUDGET_KB=${GZIP_BUDGET_KB:-280}
RAW_WARN_KB=${RAW_WARN_KB:-1000}
CSS_BUDGET_KB=${CSS_BUDGET_KB:-120}

# 초기 로드 청크: index.html 이 실제로 즉시 받는 것(<script src> + <link modulepreload>)만.
#
# 예전엔 이 목록을 청크 **파일명 접두어**로 손으로 나열했다(Chat/GameRoom/DevReport/
# AdminRoutes/UserRoutes/datascreen). PF7 로 AdminRoutes 안의 개별 화면들(Dashboard·Ops·
# Settings·Users·OrgConsole·SystemOps…)이 React.lazy 로 갈라지며 각자 새 파일명을 받자,
# 그 이름들이 손으로 적은 목록에 없어서 **진짜로 지연 로딩되는 청크가 초기 예산에
# 잘못 잡혔다**(즉시 로드가 아닌데 즉시 로드로 세어 319KB > 280KB 오탐이 났다).
#
# 그래서 목록을 손으로 유지하지 않는다 — index.html 자체가 정답이다: 브라우저가
# 페이지를 열자마자 받는 파일은 <script type="module" src="...">(엔트리)와
# <link rel="modulepreload" href="...">(Vite 가 엔트리 그래프에서 곧 필요하다고 예측해
# 미리 받으라고 지시한 것)뿐이다. 거기 없는 파일은 런타임 import() 로만 닿을 수 있으므로
# 정의상 지연 로딩이다. 새 화면을 추가해도 이 스크립트를 고칠 일이 없다.
INDEX_HTML="$DIR/../index.html"
if [ ! -f "$INDEX_HTML" ]; then
  echo "index.html 이 없다: $INDEX_HTML — 먼저 'cd frontend && npm run build'" >&2
  exit 1
fi
EAGER_NAMES="$(grep -oE '(src|href)="[^"]*/assets/[^"]+\.js"' "$INDEX_HTML" | sed -E 's#.*/assets/##; s#"$##' | sort -u)"

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
  if ! printf '%s\n' "$EAGER_NAMES" | grep -qxF "$base"; then
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
