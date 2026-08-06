#!/usr/bin/env bash
# 배포 직후 헬스 게이트. sudo 없이 밖에서 확인할 수 있는 것만 본다.
#
#   BASE=https://portal.example.internal bash scripts/verify_deploy.sh
#
# BASE 에 기본값을 두지 않는 이유: 예전엔 최초 고객사 서버 주소가 기본값이었다. 다른 설치처에서
# 아무 생각 없이 실행하면 **남의 서버**를 찌르고 초록불을 냈다. 검증이 무엇을 검증했는지가
# 거짓이 되는 종류의 결함이라, 대상이 없으면 검사하지 않고 멈춘다.
#
# 확인하는 것(docs/DEPLOY_VERIFICATION.md 9번 게이트):
#   * /healthz /readyz 200
#   * 로그인 화면이 새 제품명(ClovirAssist)으로 바뀌었다
#   * 정적 자산 해시가 새 번들의 것으로 갱신됐다
#   * 새 라우트가 **404 가 아니라 401** 이다(라우터가 실려 있고 인증벽만 막는다)
#   * CSP 가 새 정책이다(외부 웹폰트·아이콘이 로드되려면 필요하다)
set -uo pipefail
BASE="${BASE:-}"
if [ -z "$BASE" ]; then
  echo "BASE 를 지정해야 합니다(설치처마다 다른 주소라 기본값이 없습니다)."
  echo "예: BASE=https://portal.example.internal bash $0"
  exit 2
fi
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

# 자산 해시 — **자산 파일을 이름으로 직접 요청한다.**
#
# 처음에는 진입 HTML(`GET /`)에서 번들 이름을 찾으려 했는데, `/` 는 로그인하지 않은 요청을
# 303 으로 /login 에 보낸다. 그래서 늘 로그인 페이지(Jinja, React 자산 없음)를 훑고
# "옛 번들이 서빙되고 있다"고 잘못 말했다 — 실제로는 새 번들이 올라가 있었다.
# 파일명이 곧 내용 해시이므로, 그 이름으로 200 이 나오면 그 빌드가 배포된 것이다.
entry=$(ls app/static/react/assets/index.*.js 2>/dev/null | head -1 | xargs -n1 basename 2>/dev/null)
if [ -z "$entry" ]; then
  bad "정적 자산 해시" "로컬에 빌드 산출물이 없다 — 먼저 npm run build"
else
  c=$(code "$BASE/static/react/assets/$entry")
  if [ "$c" = "200" ]; then
    served=0
    missing_assets=""
    for a in $(ls app/static/react/assets/ 2>/dev/null); do
      [ "$(code "$BASE/static/react/assets/$a")" = "200" ] && served=$((served + 1))         || missing_assets="$missing_assets $a"
    done
    total=$(ls app/static/react/assets/ 2>/dev/null | grep -c "")
    if [ "$served" = "$total" ]; then
      ok "정적 자산 해시" "$served/$total 개 전부 새 번들"
    else
      bad "정적 자산 해시" "$served/$total 개만 일치, 없음:$missing_assets"
    fi
  else
    bad "정적 자산 해시" "$entry → $c (옛 번들이 서빙되고 있다)"
  fi
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
