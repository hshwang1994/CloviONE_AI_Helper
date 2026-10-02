#!/usr/bin/env bash
# Static checks (spec §31.1). Run from the repo root. Cross-platform (Git Bash / Linux).
#
# 일반 개발: python scripts/verify.py
# 전량(Exit/커밋) 게이트: bash scripts/static_checks.sh [--scope full]
# --scope dev 는 값싼 린트만 돌리고 번들 신선도·git fsck·(조건부) coverage/시험 강도를 건너뛴다.
set -uo pipefail
export LC_ALL=C.UTF-8
FAIL=0
step() { echo ""; echo "== $1 =="; }
fail() { echo "[FAIL] $1"; FAIL=1; }
ok()   { echo "[OK ] $1"; }
skip() { echo ""; echo "== $1 =="; echo "(건너뜀 — scope=$SCOPE) $2"; }

SCOPE=full
while [ $# -gt 0 ]; do
  case "$1" in
    --scope)
      SCOPE="${2:-}"
      shift 2
      ;;
    --scope=*)
      SCOPE="${1#*=}"
      shift
      ;;
    *)
      echo "unknown argument: $1 (expected --scope dev|full)" >&2
      exit 2
      ;;
  esac
done
case "$SCOPE" in
  dev|full) ;;
  *) echo "--scope 는 dev 또는 full 이어야 한다 (받은 값: $SCOPE)" >&2; exit 2 ;;
esac

CHANGED="$(git diff --name-only HEAD 2>/dev/null; git ls-files --others --exclude-standard 2>/dev/null)" || true
changed_match() { echo "$CHANGED" | grep -qE "$1"; }

PY="${PY:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
# Prefer the project venv if present
[ -x ".venv/Scripts/python.exe" ] && PY=".venv/Scripts/python.exe"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

echo "static_checks scope=$SCOPE"

step "Python compile"
if "$PY" -m compileall -q app scripts >/dev/null 2>&1; then ok "compileall"; else fail "compileall"; fi

step "Import check"
if "$PY" -c "import app.main; import app.worker_main; import app.models_registry" 2>/dev/null; then ok "imports"; else fail "imports"; fi

step "async route-handler ban (spec §2 invariant 1: sync consistency)"
# FastAPI runs sync `def` handlers in a threadpool but `async def` handlers on the
# event loop. An async handler doing Argon2 / sync SQLAlchemy blocks the whole loop.
# Flag any async def decorated with an HTTP-method router/app decorator. Exception
# handlers, middleware dispatch/__call__, and body-reading helper dependencies are
# NOT route handlers and are correctly left async.
if "$PY" - <<'PYEOF'
import ast
import pathlib
import sys

HTTP = {"get", "post", "put", "patch", "delete", "head", "options", "websocket"}


def is_route_decorator(node):
    call = node.func if isinstance(node, ast.Call) else node
    return isinstance(call, ast.Attribute) and call.attr in HTTP


offenders = []
for path in sorted(pathlib.Path("app").rglob("*.py")):
    tree = ast.parse(path.read_text(encoding="utf-8"))
    for node in ast.walk(tree):
        if isinstance(node, ast.AsyncFunctionDef) and any(
            is_route_decorator(d) for d in node.decorator_list
        ):
            offenders.append(f"{path.as_posix()}:{node.lineno} async def {node.name}")
if offenders:
    print("\n".join(offenders))
    sys.exit(1)
PYEOF
then ok "no async route handlers"; else fail "async route handler(s) present (violates sync invariant)"; fi

step "httpx choke-point guard"
OFFENDERS="$(grep -rlE '^(import httpx|from httpx)' app --include='*.py' | grep -v 'app/core/http_client.py' || true)"
if [ -z "$OFFENDERS" ]; then ok "only http_client imports httpx"; else fail "httpx imported outside choke point: $OFFENDERS"; fi

step "Notion 모듈 import 경계 (저장소 seam)"
# httpx 단일 관문 검사와 같은 발상이다: Notion 구현 세부(속성 이름·스키마·페이지네이션)를 아무
# 데서나 import 하면 소스를 바꿀 때 고칠 곳이 화면 수만큼 흩어진다. 저장소 인터페이스 뒤에
# 가두고, 이 세 모듈을 import 해도 되는 곳을 여기서 못박는다.
#   허용: 구현체(*_notion.py), 미러 동기화(*/sync.py — 미러 채우기 자체가 소스 특화 동작),
#         그리고 그 세 모듈 자신(notion_write.py 는 notion_source 를 쓴다).
# 함수 안 지연 import 로 규칙을 피해 가지 못하게 ^ 앵커 대신 앞쪽 공백을 허용한다.
NOTION_OFFENDERS="$(grep -rlE '^[[:space:]]*(from|import)[[:space:]]+.*(notion_source|notion_write|notion_docs)' app --include='*.py' \
  | grep -vE '(_notion\.py|/sync\.py|/notion_write\.py|/notion_source\.py|/notion_docs\.py)$' || true)"
if [ -z "$NOTION_OFFENDERS" ]; then ok "notion modules imported only behind the repository seam"; else echo "$NOTION_OFFENDERS"; fail "notion 구현 모듈이 저장소 seam 밖에서 import 됨"; fi

step "Secret / hardcoded-password scan"
# Flag likely plaintext secrets, ignoring test fixtures and the .example env.
HITS="$(grep -rnE '(password|secret|token|api[_-]?key)\s*=\s*["'\''][^"'\'' ]{8,}' app --include='*.py' \
  | grep -vE '(test|example|dev-only|__GENERATED|password_hash|reveal|mask|SESSION_SECRET|change-me)' || true)"
if [ -z "$HITS" ]; then ok "no hardcoded secrets"; else echo "$HITS"; fail "possible hardcoded secret"; fi

if [ "$SCOPE" = "full" ]; then
step "Repository hygiene — stash/reflog/dangling objects scanned for credentials (PA-RC-0003)"
# 위 검사는 워킹트리·HEAD만 본다 — git stash/reflog에 남은 옛 값은 못 본다(실제로
# stash@{0}에서 TEST 서버 자격증명이 이 사각지대로 새 있었다). 값은 출력하지 않는다.
# git fsck 는 전량/커밋 게이트에서만 돈다. 일상 개발은 워킹트리 secret 스캔(위 단계)만.
if "$PY" scripts/check_git_secrets.py; then ok "git internals clean"; else fail "credential-like value in stash/reflog/dangling object — see above (object+line only, no value printed)"; fi
else
skip "Repository hygiene (git fsck)" "전량 게이트: bash scripts/static_checks.sh --scope full"
fi

step "Bash syntax"
for s in scripts/*.sh deploy/*.sh; do
  [ -f "$s" ] || continue
  if bash -n "$s" 2>/dev/null; then ok "bash -n $s"; else fail "bash -n $s"; fi
done

step "배포 자산의 줄바꿈 (S4)"
# 🔴 실제로 이것 때문에 LXD 리허설 한 회차를 통째로 버렸다. CRLF 로 저장된 셸 스크립트는
# `set -euo pipefail\r` 에서 «set: pipefail: invalid option name» 으로 죽는다 — 스크립트
# 안의 CRLF 가드는 그 줄보다 **뒤에** 있어 영원히 안 울린다(옛 installer 도 같다).
# .gitattributes 가 커밋 내용을 LF 로 정규화하지만, 작업 트리 파일을 그대로 서버에 올려
# 돌리는 것이 실제 개발 경로다. 그 경로를 여기서 막는다.
CRLF_HITS=""
for f in deploy/*.sh deploy/systemd/*.service deploy/nginx/* deploy/*.example scripts/*.sh; do
  [ -f "$f" ] || continue
  if grep -qU $'\r' "$f" 2>/dev/null; then CRLF_HITS="$CRLF_HITS $f"; fi
done
if [ -z "$CRLF_HITS" ]; then ok "배포 자산이 전부 LF"; else echo "$CRLF_HITS"; fail "CRLF 로 저장된 배포 자산 — 리눅스에서 실행되지 않는다"; fi

step "systemd unit sanity"
for u in deploy/systemd/*.service; do
  grep -q '^\[Service\]' "$u" && grep -q 'NoNewPrivileges=true' "$u" && ok "unit $u" || fail "unit $u missing hardening"
done

step "JS syntax (if node available)"
if command -v node >/dev/null 2>&1; then
  for f in $(find app/static/js -name '*.js'); do
    if node --check "$f" 2>/dev/null; then ok "node --check $f"; else fail "node --check $f"; fi
  done
else
  echo "(node 없음 — JS 구문 검사 건너뜀)"
fi

step "Config allowlist JSON valid"
for f in config/*.json; do
  "$PY" -c "import json,sys; json.load(open('$f', encoding='utf-8'))" 2>/dev/null && ok "json $f" || fail "invalid json $f"
done

step "MUI icon barrel-import guard"
# @mui/icons-material 배럴에서 가져오면 아이콘 수천 개가 번들 그래프에 들어온다.
# 깊은 기본 import(@mui/icons-material/HomeOutlined)만 쓴다.
BARREL="$(grep -rnE "from ['\"]@mui/icons-material['\"]" frontend/src 2>/dev/null || true)"
if [ -z "$BARREL" ]; then ok "icons imported deeply"; else echo "$BARREL"; fail "barrel import from @mui/icons-material (번들이 폭증한다)"; fi

step "MUI icon prop guard (PLAN «Icon System» ⓐ)"
# `SvgIcon` 에는 `size` prop 이 없고 fill 기반이라 `strokeWidth` 도 무효다. React 는 모르는
# prop 을 조용히 흘려보내므로 화면에는 기본값 24px 이 그려진다 — 사이드바 자식 아이콘이
# 그렇게 부모 그룹 아이콘(20px)보다 크게 나왔고 시험은 전부 초록이었다(F-W1R-05·F-W1R-38).
# 검사기는 자기 자신을 먼저 시험한다(--self-test 사례 5개, 검출·위양성 양방향).
if ICONPROPS="$("$PY" scripts/check_icon_props.py 2>&1)"; then
  ok "$(echo "$ICONPROPS" | tail -1)"
else
  echo "$ICONPROPS"; fail "MUI 아이콘에 없는 prop 으로 크기를 정한다"
fi

step "잉크 3단이 다시 2단으로 무너지지 않는가 (W4 · F-W1R-03)"
# `text.secondary` 와 `text.faint` 는 대비 1.10:1 이라 눈으로 같은 색이었다 — 3단이라고
# 부르던 위계가 실제로는 2단이었다. W4 가 `faint` 를 AA-large(3:1) 자리로 한정하고 값을
# 벌려(분리도 1.53/1.60) 3단을 만들었다. 그 결정은 소비처가 지켜야 성립한다: 13px 각주에
# `text.faint` 를 한 번 쓰면 조용히 2단으로 돌아간다. RED 확인 완료 — 이 검사를 W4 이전
# 소스에 돌리면 5건(kit·adminKit·CommandPalette)을 정확히 잡는다.
if INKSCALE="$("$PY" scripts/check_ink_scale.py 2>&1)"; then
  ok "$(echo "$INKSCALE" | tail -1)"
else
  echo "$INKSCALE"; fail "본문 크기 글자에 AA-large 전용 잉크를 썼다"
fi

step "논리 테두리가 실제로 그려지는 형태인가 (W4 · F-W2R-01)"
# `sx={{ borderInlineStart: 1 }}` 는 MUI 의 border 스타일 함수가 펴 주지 않는다 — 논리 속성은
# `@mui/system` borders.js 의 compose 목록에 없다. 그대로 emotion 에 닿아 `border-inline-start: 1px`
# 가 나가고, `border-style` 의 초기값이 `none` 이라 **아무것도 그려지지 않는다.** 콘솔에도
# 시험에도 흔적이 없다. 같은 자리를 세 번 밟았다(AppShell 사이드바 모서리 · CommandPalette
# 선택 레일 · kit.jsx 세 자리). 검사기는 자기 자신을 먼저 시험한다(사례 11개, 양방향).
if LBORDER="$("$PY" scripts/check_logical_border_props.py 2>&1)"; then
  ok "$(echo "$LBORDER" | tail -1)"
else
  echo "$LBORDER"; fail "논리 테두리가 선언만 있고 화면에는 없다"
fi

# UX Writing 두 계약(쉼표 이어붙이기 · 표준 동사표)은 **여기 없다.**
#
# 예전에는 같은 규칙을 두 벌 들고 있었다: 여기 bash grep 한 벌, `frontend/src/ui/
# ux-writing-*.test.js` 에 vitest 한 벌. 각자 자기 허용 목록을 손으로 유지했고, 그 둘은
# 실제로 갈라졌다 — 「이 조건 지우기」가 bash 목록에는 없는 형태라 이쪽만 통과하고 vitest 는
# 빨간 채로 남았다(P-46). 「둘을 같게 유지하라」는 주석은 그 자리에 이미 있었고, 그래도
# 갈라졌다.
#
# 정본은 vitest 쪽 하나다(JS 문자열을 JS 가 판정한다 — 주석 제거와 부정 전방탐색이 필요한데
# POSIX ERE 에는 둘 다 없다). 아래 "UX Writing 계약" 단계가 그 파일들을 직접 돌린다.

step "No new typography literals (PA-RC-0001 §5)"
# FONT_SIZE(6단계)가 있는데 fontSize: raw 값을 새로 쓰면 이 Root Cause가 다시 생긴다.
# fontWeight는 이미 0건이라 그대로 지킨다. fontSize는 아이콘·이모지·입력창·서체본문·
# 자격증명표시 같은 검증된 예외가 있어 완전 금지는 아니다 — scripts/check_typography_literals.py의
# EXEMPT_FONT_SIZE_VALUES에 없는 새 값만 잡는다(각 값은 실제 코드 문맥으로 낱개 확인됨, D-81).
if TYPO="$("$PY" scripts/check_typography_literals.py 2>&1)"; then
  ok "$(echo "$TYPO" | tail -1)"
else
  echo "$TYPO"; fail "검증되지 않은 새 fontSize/fontWeight 리터럴"
fi

step "Button hierarchy — destructive actions never primary (PA-RC-0023)"
# registry/*.js 액션이 그 화면의 버튼 색을 정한다(DataScreen.jsx가 variant를 그대로 옮긴다).
# 삭제·비활성화·보관 등은 항상 danger(채운 빨간 버튼)여야 한다 — primary(채운 파란 버튼)로
# 새는 걸 문서가 아니라 이 검사가 잡는다. primary:true(빈 상태 CTA 승격)는 variant:"primary"와
# 항상 짝지어야 한다(안 그러면 평소 툴바에서만 외곽선으로 보인다 — notion-mapping이 실제로
# 이 상태였다). scripts/check_button_hierarchy.py 참고.
if BTNH="$("$PY" scripts/check_button_hierarchy.py 2>&1)"; then
  ok "$(echo "$BTNH" | tail -1)"
else
  echo "$BTNH"; fail "버튼 위계 규범 위반 — 파괴적 동작이 primary이거나 primary:true 짝이 안 맞다"
fi

step "Success toast labels have a sentence-form dictionary entry (PA-RC-0025)"
# DataScreen.jsx의 finishAction()/SubListDrawer.jsx의 act()는 액션이 a.result()로 자기
# 메시지를 안 만들면 data-screen/successMessages.js의 사전에서 라벨로 문장을 찾는다(예전엔
# "라벨 + 완료"로 이어 붙여 "삭제 완료"처럼 마침표 없는 명사형이 났다). 새 라벨이 이 기본
# 경로를 타는데 사전에 등록을 안 하면 GENERIC_SUCCESS_MESSAGE로는 떨어지지만(안전망), 그
# 라벨 고유의 문장이 빠진 채로 넘어가는 걸 이 검사가 잡는다. scripts/check_success_toast_labels.py 참고.
if TOASTLBL="$("$PY" scripts/check_success_toast_labels.py 2>&1)"; then
  ok "$(echo "$TOASTLBL" | tail -1)"
else
  echo "$TOASTLBL"; fail "기본 경로를 타는 액션 라벨이 successMessages.js 사전에 없다"
fi

step "Heading variant/component separation (PA-RC-0012)"
# variant="h6"는 시각 크기 선택이면서 동시에(component= 없으면) 실제 <h6> 태그도 정해
# 버린다 — 손으로 쓴 화면 5개가 이 함정으로 h1 다음에 h6을 놓아 문서 heading 구조가
# 네 단계를 건너뛰었다. component=로 시각/의미를 분리하는 관용은 이미 27곳에 있다
# (ui/adminKit.jsx:52 등) — scripts/check_heading_variant_mapping.py 참고.
if HEAD="$("$PY" scripts/check_heading_variant_mapping.py 2>&1)"; then
  ok "$(echo "$HEAD" | tail -1)"
else
  echo "$HEAD"; fail "heading variant/component 분리 위반 — component= 없이 h3~h6를 썼다"
fi

step "No external origins fetched by frontend"
# 사내 LAN 전용이라 CDN·외부 폰트·외부 이미지를 런타임에 '받아오면' 오프라인에서 깨지고,
# CSP(default-src 'self')에도 걸린다. 사용자가 눌러서 여는 링크(Notion 문서 등)는 문제가
# 아니므로, 여기서는 '가져오는' 표현만 본다: import/fetch/src=/href=/url().
# 테스트 파일은 URL 검증 로직을 시험하느라 외부 문자열을 일부러 쓰므로 제외한다.
CDN="$(grep -rnE "(from|import|fetch|src=|href=|url\()\s*\(?\s*['\"]https?://" frontend/src \
  --include='*.js' --include='*.jsx' --include='*.css' 2>/dev/null \
  | grep -vE '\.test\.jsx?:' \
  | grep -vE '(w3\.org|localhost|127\.0\.0\.1)' || true)"
if [ -z "$CDN" ]; then ok "no external fetches in frontend/src"; else echo "$CDN"; fail "external URL fetched by frontend (오프라인 LAN에서 깨진다)"; fi

step "Mascot frames/layers are reference-only"
# docs/mascot-animation-spec.md §5: 프레임/레이어를 런타임에 합성하면 손목이 분리되거나
# 배경색이 어긋난다. 런타임은 완성된 포즈 PNG만 교체한다.
# 주석에서 규칙 자체를 설명하는 줄은 참조가 아니다 — 코드에서 경로를 만드는 줄만 본다.
COMPOSITE="$(grep -rnE "['\"\`][^'\"\`]*brand/mascot/(frames|layers)" frontend/src app/templates_html 2>/dev/null || true)"
if [ -z "$COMPOSITE" ]; then ok "mascot frames/layers not referenced at runtime"; else echo "$COMPOSITE"; fail "runtime reference to mascot frames/layers"; fi

step "No undefined CSS variables without a fallback"
# 실제로 로그인 화면에서 터졌다. 정의되지 않은 var()를 fallback 없이 쓰면 그 선언 하나가
# 아니라 **선언 전체가 무효**가 된다(invalid at computed-value time). eye-error 키프레임이
# 이것 때문에 transform 을 통째로 잃어 오류 상태에서 눈이 튀었다. 빌드·린트·테스트 전부
# 못 잡고, 자주 안 나오는 상태면 배포 후에도 한참 모른다.
if CSSVARS="$("$PY" scripts/check_css_vars.py 2>&1)"; then
  ok "$(echo "$CSSVARS" | tail -1)"
else
  echo "$CSSVARS"; fail "정의되지 않은 CSS 변수를 fallback 없이 참조한다"
fi

step "Tracked files do not import untracked modules"
# 실제로 한 번 터진 결함이다. 백엔드 작업의 일부만 커밋되면서 추적되는 파일이
# 미추적 모듈을 import 하는 상태가 HEAD에 올라갔다 — 워킹트리에서는 전부 통과하고
# fresh clone 에서만 죽는다. 즉 배포 서버에서 처음 발견된다.
if TRACKED="$("$PY" scripts/check_tracked_imports.py 2>&1)"; then
  ok "$(echo "$TRACKED" | tail -1)"
else
  echo "$TRACKED"; fail "커밋 누락 — 추적 파일이 미추적 모듈을 import 한다"
fi

step "No leftover sabotage markers"
# 이 저장소의 완료 판정은 "결함을 재도입해 FAIL 을 본 뒤 복원" 이다(계획서 규칙 ①).
# 그 과정에서 코드에 임시로 남기는 마커가 **복원되지 않은 채 남으면** 보안 수정이 꺼진
# 상태로 배포된다 — 실제로 병렬 작업 중 한 번 남았고, 다른 작업자가 우연히 발견했다.
# 우연에 기대지 않는다.
MARKERS="$(grep -rn "SABOTAGE" app frontend/src tests scripts   --include='*.py' --include='*.js' --include='*.jsx' --include='*.sh' 2>/dev/null   | grep -v 'scripts/static_checks.sh' || true)"
if [ -z "$MARKERS" ]; then
  ok "NO_SABOTAGE_MARKERS"
else
  echo "$MARKERS"; fail "RED 확인용 마커가 복원되지 않은 채 남아 있다"
fi

step "Scoped modules gate their id routes too"
# 같은 실수를 **네 번** 했다: 목록에는 범위를 걸고 단건·쓰기는 안 걸었다(승인 결재·잡 재시도·
# 게시판 상세·티켓 첨부). 그중 승인은 범위 밖 **권한 부여를 실행**할 수 있었다.
# 사람 기억에 맡기면 또 잊는다 — 막지 않기로 한 결정도 EXEMPT 에 이유를 적게 한다.
if GATES="$("$PY" scripts/check_scope_gates.py 2>&1)"; then
  ok "$(echo "$GATES" | tail -1)"
else
  echo "$GATES"; fail "범위 있는 모듈의 id 경로에 게이트가 없다"
fi

step "List, detail and Search share one visibility function"
# D-194: 「같은 규칙을 따른다」는 주석은 증거가 아니다. S5 이전에는 소속 판정만 공유하고
# 열람 제한(SEC-10)은 목록과 검색에 따로 있었다 — 절반만 사실이었다.
if VIS="$("$PY" scripts/check_visibility_single_source.py 2>&1)"; then
  ok "$(echo "$VIS" | tail -1)"
else
  echo "$VIS"; fail "가시성 판정이 app/authz/visibility.py 밖에서 갈라졌다"
fi

step "Each derived value in a domain has exactly one writer"
# S6: canonical_key 는 트리거만, 번호는 numbering.py 만, Key 는 keys.py 만, 상하위는
# relations.py 만 쓴다 (D-195 · D-196).
# S7: 본문 파생은 blocks.py 만, 판은 versions.py 만, 폴더 path·depth 는 트리거만,
# 멘션은 mentions.py 만 쓴다 (D-198 · D-244).
# 전부 어겨도 오류가 안 나고, 증상은 한참 뒤 「링크가 안 열린다」·「번호가 겹친다」·
# 「검색해도 안 나오는 문서」로 나타난다.
if DOMAIN="$("$PY" scripts/check_domain_single_source.py 2>&1)"; then
  ok "$(echo "$DOMAIN" | tail -1)"
else
  echo "$DOMAIN"; fail "도메인 파생 값의 쓰기 입구가 갈라졌다"
fi

step "No customer-specific identifiers in source defaults / install scripts"
# 출시 차단 사유였다. app/core/config.py 의 **기본값**에 개발 워크스페이스의 Notion DB id 두
# 개와 최초 고객사의 이메일 도메인이, 설치 스크립트에 그 고객사의 호스트명·IP 가 박혀 있었다.
# 다른 고객사에 설치하면 아무 설정 없이도 조용히 남의 워크스페이스를 가리키고, 왜 안 되는지는
# 어디에도 안 뜬다 — "연결은 됐는데 안 된다"로 보인다. 한 번 지우고 끝내면 다음 기능에서 다시
# 들어오므로 검사로 고정한다. 문서·테스트 픽스처 예외는 검사기의 EXEMPT 한 곳에 이유와 함께 있다.
if TENANT="$("$PY" scripts/check_tenant_defaults.py 2>&1)"; then
  ok "$(echo "$TENANT" | tail -1)"
else
  echo "$TENANT"; fail "소스 기본값·설치 스크립트에 고객사 고유 식별자가 남아 있다"
fi

step "Install docs use only commands and options the installer takes"
# README 와 설치 상세 문서의 명령은 사람이 그대로 복사해 실행한다. 스크립트에서 옵션 이름이 바뀌었는데 문서가 옛 이름을
# 들고 있으면 설치하는 사람은 첫 명령에서 멈춘다(D-523). 검사기가 스스로 맞는 문장과 틀린 문장을 가르는지도 함께 본다.
if INSTDOCS="$("$PY" scripts/check_install_docs.py --selftest 2>&1 && "$PY" scripts/check_install_docs.py 2>&1)"; then
  ok "$(echo "$INSTDOCS" | tail -1)"
else
  echo "$INSTDOCS"; fail "설치 문서의 명령이 설치 스크립트와 다르다"
fi

step "Form labels stay above the input"
# 계약 시험은 `FormField` 하나만 렌더한다 — 이미 지키는 컴포넌트 위에서만 초록이다(F-W5D-133).
# 브라우저 프로브도 «그려진 것» 만 본다(모달 안·권한 없는 폼·조건부 필드는 못 본다).
# 선언을 읽는 이 검사가 그 사각을 덮는다.
if LBLABOVE="$("$PY" scripts/check_label_above.py 2>&1)"; then
  ok "$(echo "$LBLABOVE" | tail -1)"
else
  echo "$LBLABOVE"; fail "라벨이 입력 칸 안으로 내려앉는 자리가 있다"
fi

step "Screens use the canonical kit parts, not raw MUI primitives"
# 화면이 정본 부품 대신 MUI 원재료(Alert · Chip · Tabs · Paper …)를 직접 쓰면 그 자리는 정본 계약(높이 ·
# 모서리 · 톤 · 접근성)을 자기 식으로 다시 그린 사본이 되고, 갤러리와 계약 시험은 그 사본을 보지 못한다.
# 대장(`docs/ui-renewal/COMPONENT_LEDGER.md`) 「예외」 표에 적힌 자리만 통과하고, 적혀 있는데 더는 안 쓰는
# 예외도 실패다(핸드오프 계획 §0-7 · §0-11 · B-9).
if KITC="$("$PY" scripts/check_kit_consumers.py 2>&1)"; then
  ok "$(echo "$KITC" | tail -1)"
else
  echo "$KITC"; fail "화면이 정본 부품 대신 MUI 원재료를 직접 쓴다(대장 예외 없음)"
fi

step "Screens compose lists, filters and footers through the canonical composites"
# 부품이 전부 정본이어도 화면이 그 낱개를 제각각 조립하면 조합이 화면마다 달라진다 — 필터 면 밖의 칩 · 결과 줄,
# 여백 판으로 한 번 더 감싼 표, 표 밖 가운데의 목록 발, 열 render 안의 채움 단추(UI 3차 · 조합 계약 C-1 ~ C-5).
# 대장 「조합 예외」 표에 적힌 자리만 통과하고, 죽은 예외와 더는 안 걸리는 대기 항목(stale)도 실패다.
if COMPC="$("$PY" scripts/check_composition.py --selftest 2>&1 && "$PY" scripts/check_composition.py 2>&1)"; then
  ok "$(echo "$COMPC" | tail -1)"
else
  echo "$COMPC"; fail "화면이 목록 · 필터 · 발을 정본 조합 부품 대신 낱개로 조립한다"
fi

step "QA harness targets the canonical product host"
# 「검사를 돌렸다」와 「검사가 이 제품을 봤다」는 다른 사실이다. 보조 프로브 14개가 제품 이름이
# 바뀐 뒤에도 각자 옛 호스트 문자열을 들고 있었고, 그중 하나는 검색 3중 구조를 재는 유일한
# 프로브였다 — 돌려도 canonical 호스트를 한 번도 치지 않았다(W5 · F-W5D-129).
if QAHOST="$("$PY" scripts/check_qa_target_host.py 2>&1)"; then
  ok "$(echo "$QAHOST" | tail -1)"
else
  echo "$QAHOST"; fail "QA 프로브가 대상 호스트를 직접 들고 있다"
fi

step "Every table column says what it is"
# 몸통 칸의 정렬·폭·자릿수 고정은 열의 `type` 에서 파생한다(`ui/columnTypes.js`). 타입을
# 안 적은 열은 `UNTYPED`(가운데 정렬)로 떨어지고, 그 기본값은 **조용히 틀린다** — 정렬이
# 아니라 폭과 줄바꿈이 틀린다(말줄임이 안 걸려 산문이 여러 줄로 접힌다). 어휘 자체는
# `column-types.test.jsx` 가 지키지만 그 어휘를 **쓰는가**는 아무도 안 봤다 — 이 검사가
# 그 자리다.
if COLTYPE="$("$PY" scripts/check_column_types.py 2>&1)"; then
  ok "$(echo "$COLTYPE" | tail -1)"
else
  echo "$COLTYPE"; fail "열이 자기가 무엇인지 안 말한다 — 정렬·폭이 화면마다 갈린다"
fi

step "User-facing text avoids the banned glyphs"
# 사용자 지시(§8): 화면 문구에서 가운뎃점(·)과 em 대시(—)를 쓰지 않는다.
# 한 번 훑고 끝내면 다음 화면에서 다시 새어 나가므로 검사로 고정한다.
# grep 을 쓰지 않는 이유는 검사기 docstring 에 적어 뒀다 — 저장소의 두 문자 5,985개 중
# 86%가 한국어 주석·docstring 이라 단순 grep 은 오탐 5,157개를 낸다.
# 같은 검사가 개발 내부 용어(Postfix · worker · password_ref …)도 본다(계획 5절) — 자기 시험으로 검사기부터 잰다.
if UTEXTST="$("$PY" scripts/check_user_text.py --self-test 2>&1)"; then
  ok "$(echo "$UTEXTST" | tail -1)"
else
  echo "$UTEXTST"; fail "문구 검사기가 자기 견본을 잘못 판정한다"
fi
if UTEXT="$("$PY" scripts/check_user_text.py 2>&1)"; then
  ok "$(echo "$UTEXT" | tail -1)"
else
  echo "$UTEXT"; fail "사용자에게 보이는 문구에 쓰지 않기로 한 문자나 개발 내부 용어가 있다"
fi

step "subprocess text mode declares its encoding"
# 이 결함을 **세 번** 고쳤다(sysops/runner.py, tests/conftest.py, 마이그레이션 회귀 6개).
# 그중 둘은 같은 라운드에 새로 만들면서 다시 넣은 것이다 - 새 파일을 쓰는 사람은 옆 파일을
# 복사하고, 옆 파일이 낡았으면 결함도 함께 복사된다. 사람 기억에 맡길 종류가 아니다.
# 증상: 자식이 UTF-8 한글을 뱉으면 리더 스레드가 죽어 **result.stderr 를 못 읽는다** -
# 마이그레이션이 실패했을 때 정작 그 이유가 사라진다.
if SPENC="$("$PY" scripts/check_subprocess_encoding.py 2>&1)"; then
  ok "$(echo "$SPENC" | tail -1)"
else
  echo "$SPENC"; fail "subprocess 텍스트 모드에 encoding 이 없다"
fi

step "sortKeys.json matches backend sort whitelists"
if SORTK="$("$PY" scripts/check_sort_keys_fresh.py 2>&1)"; then
  ok "$SORTK"
else
  echo "$SORTK"; fail "sortKeys.json 이 지금의 서버 정렬 계약과 다르다"
fi

step "fieldLimits.json matches backend Pydantic schemas (PA-RC-0005)"
# 관리자 폼 maxLength의 정본은 Pydantic 스키마다 - 생성기를 다시 안 돌리면 화면이 조용히
# 낡은 상한을 계속 보여준다(check_bundle_fresh.py와 같은 관용).
if FLIM="$("$PY" scripts/check_field_limits_fresh.py 2>&1)"; then
  ok "$(echo "$FLIM" | tail -1)"
else
  echo "$FLIM"; fail "fieldLimits.json이 지금의 백엔드 스키마와 다르다"
fi

step "Design token CSS matches theme.js (D-141)"
# 디자인 토큰의 정본은 frontend/src/ui/theme.js 하나다. tokens.css 두 벌(SPA·Jinja)은
# scripts/generate_design_tokens.mjs 가 만든다. 생성기를 안 돌리면 **로그인 화면만 옛
# 팔레트로 남는다** - 예전에 app/static/css/tokens.css 가 정확히 그렇게 낡아 있었다
# (흰 사이드바, 56px 상단바, surface 계층 없음). fieldLimits 와 같은 관용이다.
if command -v node >/dev/null 2>&1; then
  if TOK="$(node scripts/generate_design_tokens.mjs --check 2>&1)"; then
    ok "$(echo "$TOK" | tail -1)"
  else
    echo "$TOK"; fail "tokens.css 가 theme.js 와 다르다 — node scripts/generate_design_tokens.mjs 를 돌려라"
  fi
else
  ok "node 없음 - 토큰 드리프트 검사 건너뜀"
fi

step "클로비 자산 경계 잠금 (지시 71)"
# 화면은 «보이는 캐릭터 40px» 을 말하고 Mascot.jsx 가 자산의 여백 비율로 나눠 CSS 박스를
# 만든다. 그래서 PNG 를 갈아 끼우면 화면 크기가 **조용히** 바뀐다 — 바꾼 사람은 자기가
# 크기를 건드렸다는 사실을 모른다. 생성물 둘(mascot-bounds.json · mascotBounds.js)이 지금
# 자산에서 나온 그대로인지 본다. tokens.css 와 같은 관용이다.
if MB="$("$PY" scripts/gen_mascot_bounds.py --check 2>&1)"; then
  ok "$(echo "$MB" | tail -1)"
else
  echo "$MB"; fail "클로비 자산 경계 잠금이 낡았다 — python scripts/gen_mascot_bounds.py 를 돌려라"
fi

step "Brand 토큰이 화면에 실제로 도달한다 (지시 0-1)"
# 두 가지를 막는다. (a) 화면 파일이 자기 gradient 를 들고 있으면 그 색은 테마 밖이라 대비
# 시험이 존재 자체를 모른다 - 예전 Gradient Chrome 이 정확히 그 경로로 미측정 배포됐다.
# (b) `palette.brand` 에 theme.js 밖 소비처가 0이면 Brand 는 "정의만 되고 화면에 없는" 상태다.
# 이번 리뉴얼 직전이 실제로 그 상태였고, 아무 검사도 그것을 말하지 않았다.
if BRD="$("$PY" scripts/check_brand_tokens.py 2>&1)"; then
  ok "$(echo "$BRD" | tail -1)"
else
  echo "$BRD"; fail "Brand 토큰이 화면에 도달하지 않는다"
fi

if [ "$SCOPE" = "full" ] || changed_match '^(tests/|frontend/.+\.test\.(js|jsx|ts|tsx)$)'; then
step "시험이 약해지지 않았다 (재작성은 되고 약화는 안 된다)"
# 전면 리뉴얼은 옛 구조를 고정하던 Contract Test 를 반드시 깬다. 빨간 시험을 초록으로
# 만드는 방법은 재작성과 약화 둘뿐이고 커밋 로그에서는 똑같이 "테스트 갱신"으로 보인다.
# 기준(HEAD) 대비 단언 수가 줄거나 skip 이 늘면 실패한다. 사유는 파일 머리에 적는다.
if TSTR="$("$PY" scripts/check_test_strength.py 2>&1)"; then
  ok "$(echo "$TSTR" | tail -1)"
else
  echo "$TSTR"; fail "시험이 약해졌다"
fi
else
skip "시험 강도" "시험 파일이 이번 변경에 없다 — 전량: --scope full"
fi

step "폐기한 목업(preview-standalone.html)을 아직 참조하는 곳이 없다 (지시 64)"
# 목업은 이번 리뉴얼에서 디자인 정본이 아니다. 파일을 지운 뒤에도 주석·스크립트가 그 이름을
# 계속 부르면, 다음 세션이 "정본이 있다"고 믿고 다시 그쪽으로 값을 맞춘다.
# 확장자 목록에 `.mjs`·`.md` 가 빠져 있어 `generate_design_tokens.mjs` 와
# `ui_qa/README.md` 의 참조를 못 잡고 있었다(2026-08-19 전수 감사) — 검사가 있는데
# 통과하던 자리다. 결정·이력 문서는 폐기 **경위**를 적어야 하므로 제외 목록에 둔다.
# 시험 파일은 제외한다 — "그 경로가 없다"를 단언하려면 문자열 자체를 적어야 한다.
STALE_BASELINE="$(grep -rlE "preview-standalone|design/baseline" \
  app frontend/src scripts tests docs --include='*.py' --include='*.js' --include='*.jsx' \
  --include='*.mjs' --include='*.css' --include='*.html' --include='*.sh' --include='*.md' 2>/dev/null \
  | grep -vE '\.test\.(js|jsx)$|static_checks\.sh$|docs/(DECISIONS|BACKLOG|WORK_STATE|BUILD_LOG|UI_RENEWAL_TRACEABILITY|UI_INVENTORY)\.md$|docs/ui-renewal/|scripts/check_ui_renewal_coverage\.py$' || true)"
if [ -z "$STALE_BASELINE" ]; then
  ok "목업 참조 0건"
else
  echo "$STALE_BASELINE"; fail "폐기한 목업을 아직 참조한다"
fi

step "JS 진실은 JS 가 증명한다 — REGISTRY 대조 + UX Writing 계약"
# 세 가지를 한 번에 돌린다. 셋 다 **JS 소스 자체가 판정 대상**이라 Python·grep 이 대신 못 한다.
#
#   registry-surface-parity  REGISTRY 는 7개 도메인 파일의 객체 조립 결과라 정규식으로 훑으면
#                            조용히 놓친다 — 실제로 `admin-notifications` 하나를 놓쳤고 그
#                            화면은 한 번도 캡처된 적이 없었다. vitest 는 import 해서 센다.
#   ux-writing-punctuation   "-습니다," 로 두 문장을 잇는 관용. 주석을 먼저 지워야 오탐이 안 난다.
#   ux-writing-verb-table    표준 동사표. "편집기" 를 빼려면 부정 전방탐색이 필요한데 POSIX
#                            ERE 에 없다. 예전에는 이 둘을 bash grep 으로 한 벌 더 들고 있었고,
#                            두 허용 목록이 갈라져 한쪽만 통과하는 상태가 실제로 생겼다(P-46).
#
# 실행기는 `frontend/node_modules/.bin` 을 먼저 본다 — 윈도우에서 `npx` 는 `npx.CMD` 라
# 부르는 쪽이 셸 없이 넘기면 안 뜬다(같은 함정을 `scripts/verify.py` 가 P-48 로 겪었다).
# `registry-filter-axes` 가 여기 있는 이유는 `registry-surface-parity` 와 같다 — REGISTRY 는
# 일곱 파일의 객체 조립 결과라 Python 정규식으로 훑으면 조용히 놓친다. 그 검사가 막는 것은
# 「서버가 묶음을 자르는 화면에서 받아 둔 행만 보고 거르거나 후보를 뽑는」 선언이다.
JS_CONTRACT_TESTS="src/screens/registry-surface-parity.test.js src/screens/registry-filter-axes.test.js src/ui/ux-writing-punctuation.test.js src/ui/ux-writing-verb-table.test.js"
VITEST_BIN=""
for cand in frontend/node_modules/.bin/vitest frontend/node_modules/.bin/vitest.cmd; do
  [ -x "$cand" ] || [ -f "$cand" ] && VITEST_BIN="$cand" && break
done
if [ -n "$VITEST_BIN" ]; then
  VITEST_CMD="../$VITEST_BIN"
elif command -v npx >/dev/null 2>&1; then
  VITEST_CMD="npx vitest"
else
  VITEST_CMD=""
fi
if [ -n "$VITEST_CMD" ]; then
  # shellcheck disable=SC2086
  if PARITY="$(cd frontend && $VITEST_CMD run $JS_CONTRACT_TESTS 2>&1)"; then
    ok "$(echo "$PARITY" | grep -E 'Tests +[0-9]+ passed' | tail -1)"
  else
    echo "$PARITY" | tail -30; fail "JS 계약 시험이 실패했다 (REGISTRY 대조 · UX Writing)"
  fi
else
  fail "vitest 를 못 찾아 JS 계약 시험을 못 돌렸다 — 건너뛸 수 없다(Python 이 대신 못 한다). cd frontend && npm ci"
fi

step "프로브 판정 «규칙» 반례 (브라우저 없이 — S1)"
# W5 가 아팠던 자리 둘은 DOM 이 아니라 로직이었다: `--fail-on` 으로 건 검사가 한 번도 돌지
# 않았는데 종료 코드 0 이 나갔고, 프로브 19개가 각자 TLS 검증을 꺼서 호스트 불일치가
# 구조적으로 안 보였다. 둘 다 브라우저 없이 증명된다 — 그래서 여기서 매번 돈다.
# DOM 반례 19건은 브라우저가 필요해 `python -m scripts.ui_qa.probe_selftest` 로 따로 돌린다.
if PSELF="$("$PY" -m scripts.ui_qa.probe_selftest --logic-only 2>&1)"; then
  ok "$(echo "$PSELF" | tail -1)"
else
  echo "$PSELF" | tail -15; fail "프로브 판정 규칙이 반례를 통과하지 못한다"
fi

step "재진입 하네스 판정 «규칙» 반례 (브라우저 없이 — P0)"
# `reactivate_e2e` 는 「두 번 누른 끝 상태 ≠ 한 번 누른 끝 상태」 · 「첫 클릭 뒤 누른 자리의 항목이 바뀜」 · 렌더 예외
# 폴백을 가르는 판정을 측정과 떼어 둔 순수 함수로 갖는다. 그 규칙이 결함은 잡고 정상은 안 잡는지를 합성 관측값으로
# 여기서 매번 증명한다(표본이 모자란 포인터 판정이 통과로 새지 않는 것까지). 합성 DOM 반례(밀리는 목록 · 폴백 ·
# 질의 변경 · 안 움직이는 목록)는 브라우저가 필요해 `python -m scripts.ui_qa.reactivate_e2e --selftest` 로 따로 돈다.
if RSELF="$("$PY" -m scripts.ui_qa.reactivate_e2e --selftest --logic-only 2>&1)"; then
  ok "$(echo "$RSELF" | tail -1)"
else
  echo "$RSELF" | tail -15; fail "재진입 하네스의 판정 규칙이 반례를 통과하지 못한다"
fi

if [ "$SCOPE" = "full" ] || changed_match '^(docs/ui-renewal/|scripts/check_ui_renewal_coverage\.py|scripts/ui_qa/)'; then
step "UI 리뉴얼 Control Plane Gate — 계획 구조 · 요구사항 추적표 (지시 56 · R-96)"
# `check_traceability.py`(174줄)가 이 자리에 있었고, 삭제된 `docs/UI_RENEWAL_TRACEABILITY.md`
# 를 요구하며 스크립트 전체를 빨갛게 만들고 있었다 — "static checks green" 을 전제로 쓰는
# 모든 Wave 종료 조건이 그래서 도달 불가였다. 네 검사(번호 누락·빈 필드·없는 Wave 참조·
# 자기모순)는 `check_ui_renewal_coverage.py` 가 그대로 이어받고 범위를 넓혔다.
# Gate 가 둘이면 갈라진다 — 하나만 둔다.
if TRACE="$("$PY" scripts/check_ui_renewal_coverage.py --stage plan 2>&1)"; then
  ok "$(echo "$TRACE" | tail -1)"
else
  echo "$TRACE"; fail "Control Plane 이 Plan Gate 를 통과하지 못한다"
fi
else
skip "coverage --stage plan" "원장/검사기/ui_qa 가 이번 변경에 없다 — 전량: --scope full"
fi

step "번들 신선도 검사기가 스스로 시험을 통과하는가 (S4)"
# 🔴 이 검사기의 해시가 **운영체제를 탔다.** `sorted(Path)` 가 Windows 에서는 대소문자를
# 무시하고 리눅스에서는 바이트로 정렬해, 내용이 한 바이트도 안 달라도 해시가 갈렸다.
# 그래서 Windows 에서 찍은 기준을 들고 리눅스에 설치하면 Stage 5 가 «번들이 낡았다» 로
# 죽었다(S4 LXD 리허설에서 실제로 그렇게 멈췄다). 사례 6개 · 반례 포함.
if BSELF="$("$PY" scripts/check_bundle_fresh.py --self-test 2>&1)"; then
  ok "$(echo "$BSELF" | tail -1)"
else
  echo "$BSELF"; fail "번들 신선도 검사기의 입력 순서가 운영체제를 탄다"
fi

if [ "$SCOPE" = "full" ]; then
step "Committed frontend bundle matches the sources"
# 이 저장소는 빌드 산출물을 git 에 커밋한다(서버에 Node 불필요). 대신 소스만 고치고 번들을
# 안 만들면 git 으로 설치한 서버가 **조용히 옛 UI 를 돌린다** - 로그에도 화면에도 흔적이 없다.
# 0-E-11 에서 "최종 빌드 뒤에 연결한다"고 적어 두고 실제로는 안 걸었다. 감사가 그걸 찾았다.
# 일상 개발(scope=dev)에서는 이 검사가 Vite 전량 빌드를 강제하므로 건너뛴다. 커밋/Exit 는 --scope full.
if BFRESH="$("$PY" scripts/check_bundle_fresh.py 2>&1)"; then
  ok "$(echo "$BFRESH" | tail -1)"
else
  echo "$BFRESH"; fail "프런트 소스가 커밋된 번들보다 새롭다"
fi
else
skip "번들 신선도" "전량 게이트: bash scripts/static_checks.sh --scope full"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then
  if [ "$SCOPE" = "dev" ]; then
    echo "STATIC_CHECKS_DEV_OK"
    echo "이 결과는 커밋/Exit 게이트가 아니다. 전량: bash scripts/static_checks.sh --scope full"
  else
    echo "STATIC_CHECKS_OK"
  fi
else
  echo "STATIC_CHECKS_FAILED"
fi
exit $FAIL
