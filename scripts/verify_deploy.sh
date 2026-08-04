#!/usr/bin/env bash
# 배포 직후 헬스 게이트. sudo 없이 밖에서 확인할 수 있는 것만 본다.
#
#   bash scripts/verify_deploy.sh            # 기본 https://10.100.64.71
#   BASE=https://clovirone-ai.gooddi.lab bash scripts/verify_deploy.sh
#
# 확인하는 것(docs/DEPLOY_VERIFICATION.md 9번 게이트):
#   * /healthz /readyz 200
#   * 로그인 화면이 새 제품명(ClovirAssist)으로 바뀌었다
#   * 정적 자산 해시가 새 번들의 것으로 갱신됐다
#   * 새 라우트가 **404 가 아니라 401** 이다(라우터가 실려 있고 인증벽만 막는다)
#   * CSP 가 새 정책이다(외부 웹폰트·아이콘이 로드되려면 필요하다)
set -uo pipefail
BASE="${BASE:-https://10.100.64.71}"
CURL="curl -sk --max-time 15"
fail=0

say() { printf '%-52s %s\n' "$1" "$2"; }
ok()  { say "$1" "OK   $2"; }
bad() { say "$1" "FAIL $2"; fail=$((fail + 1)); }

code() { $CURL -o /dev/null -w '%{http_code}' "$1"; }

echo "== 대상: $BASE =="

for p in /healthz /readyz; do
  c=$(code "$BASE$p")
  [ "$c" = "200" ] && ok "$p" "$c" || bad "$p" "$c (기대 200)"
done

html=$($CURL "$BASE/login")
if grep -q "ClovirAssist" <<<"$html"; then
  ok "로그인 화면 제품명" "ClovirAssist"
else
  bad "로그인 화면 제품명" "아직 옛 이름이다"
fi

# 자산 해시 — 로컬 번들과 같은 파일명이 서빙되어야 한다.
local_assets=$(ls app/static/react/assets/*.js 2>/dev/null | xargs -n1 basename 2>/dev/null | sort)
shell=$($CURL "$BASE/")
missing=0
for a in $local_assets; do
  grep -q "$a" <<<"$shell" || missing=$((missing + 1))
done
if [ -z "$local_assets" ]; then
  bad "정적 자산 해시" "로컬에 빌드 산출물이 없다 — 먼저 npm run build"
elif [ "$missing" -gt 0 ]; then
  # 지연 로드 청크는 진입 HTML 에 안 실린다. 진입 번들 하나만 맞으면 통과로 본다.
  entry=$(ls app/static/react/assets/index.*.js 2>/dev/null | head -1 | xargs -n1 basename 2>/dev/null)
  if [ -n "$entry" ] && grep -q "$entry" <<<"$shell"; then
    ok "정적 자산 해시" "진입 번들 $entry 서빙 중"
  else
    bad "정적 자산 해시" "옛 번들이 서빙되고 있다"
  fi
else
  ok "정적 자산 해시" "전부 새 번들"
fi

# 이번에 새로 추가한 라우트 — 404 면 코드가 안 올라간 것이고, 401 이면 올라갔다.
for p in /api/admin/organizations /api/tickets/attachments/none; do
  c=$(code "$BASE$p")
  [ "$c" = "401" ] && ok "새 라우트 $p" "401 (라우터 있음)" \
    || bad "새 라우트 $p" "$c (기대 401, 404 면 배포 안 된 것)"
done

csp=$($CURL -D - -o /dev/null "$BASE/login" | tr -d '\r' | grep -i '^content-security-policy:')
if grep -q "script-src 'self' 'unsafe-inline' 'unsafe-eval' https:" <<<"$csp"; then
  ok "CSP" "새 정책"
else
  bad "CSP" "옛 정책 (외부 폰트·아이콘이 막힌다)"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "DEPLOY_VERIFY_OK"
  exit 0
fi
echo "DEPLOY_VERIFY_FAILED ($fail 건)"
exit 1
