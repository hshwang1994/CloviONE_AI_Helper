#!/usr/bin/env bash
# Static checks (spec §31.1). Run from the repo root. Cross-platform (Git Bash / Linux).
set -uo pipefail
export LC_ALL=C.UTF-8
FAIL=0
step() { echo ""; echo "== $1 =="; }
fail() { echo "[FAIL] $1"; FAIL=1; }
ok()   { echo "[OK ] $1"; }

PY="${PY:-python}"
command -v "$PY" >/dev/null 2>&1 || PY=python3
# Prefer the project venv if present
[ -x ".venv/Scripts/python.exe" ] && PY=".venv/Scripts/python.exe"
[ -x ".venv/bin/python" ] && PY=".venv/bin/python"

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

step "Bash syntax"
for s in scripts/*.sh deploy/*.sh; do
  [ -f "$s" ] || continue
  if bash -n "$s" 2>/dev/null; then ok "bash -n $s"; else fail "bash -n $s"; fi
done

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

step "User-facing text does not comma-splice two sentences (PA-RC-0002)"
# docs/UX_WRITING.md §1: 두 문장은 마침표로 구분한다. "-습니다/-세요" 등으로 끝난 절 바로
# 뒤에 쉼표로 다음 문장을 잇는 관용이 kit.jsx를 포함해 화면 20여 개에 흩어져 있었다(감사가
# kit.jsx 내부의 6:5 불일치를 지목했는데, 실제로는 저장소 전체가 같은 패턴이었다). 목록
# 나열(예: "중단, 응답 없음")은 서술어 종결 어미로 안 끝나 이 정규식에 안 걸린다. 프런트만
# 본다 — frontend/src/ui/ux-writing-punctuation.test.js 가 같은 규칙을 npm test 경로에서
# 지킨다(둘 다 static_checks.sh 는 npm test 를 안 부르므로 독립된 게이트가 필요하다).
SPLICE="$(grep -rnE '(습니다|입니다|합니다|됩니다|세요|까요),\s*[가-힣]' frontend/src \
  --include='*.js' --include='*.jsx' | grep -vE '\.test\.jsx?:' || true)"
if [ -z "$SPLICE" ]; then ok "no comma-spliced sentences in user-facing text"; else echo "$SPLICE"; fail "쉼표로 이어붙인 문장(마침표여야 함)"; fi

step "User-facing text uses the standard verb table (PA-RC-0002 §3)"
# docs/UX_WRITING.md §3: 같은 개념(새로 만든다/고친다/없앤다/막는다/다시 쓰게 한다)에
# 생성·등록·만들다/편집·변경/제거·지우다/끄기·중지·정지/켜기 같은 동의어가 섞여 있었다.
# JSX 텍스트 자식(`>...텍스트...<`)만 본다 — registry/*.js처럼 문구를 객체 속성으로 정의하고
# 다른 컴포넌트가 나중에 렌더링하는 간접 정의는 정적 grep으로 못 따라간다(의도적 범위 제한,
# frontend/src/ui/ux-writing-verb-table.test.js 상단 주석 참고 — 그 파일에 "문서 생성"처럼
# 정당한 도메인 용어와 부딪혀 범위를 넓히길 포기한 이유가 적혀 있다). 6번째 축(반영/적용→저장)
# 은 예외가 너무 다양해 여기도 안 건다. 허용 문구는 위 vitest 파일의 allow 목록과 반드시
# 같게 유지한다 — 둘이 갈라지면 이 게이트만 통과하고 npm test는 실패하거나 그 반대가 된다.
#
# grep은 한 줄씩만 보므로(-z 등 없이는 여러 줄에 안 걸친다) vitest 버전과 달리 폭 제한이
# 필요 없다 — 애초에 JS 비교연산자 `>`가 몇 줄 뒤 `<`와 잘못 짝지어질 수가 없다. 다만 grep
# -E(POSIX ERE)는 부정 전방탐색이 없어 "편집기"(동사 아닌 컴포넌트 고유명사, 편집 뒤 "기")를
# 정규식 안에서 못 뺀다 — 별도 grep -v 단계로 그 줄만 다시 뺀다. 주석은 안 지운다(한 줄
# 기준이라 vitest만큼 오탐 위험이 크지 않고, 주석 스트리핑을 bash에서 안전하게 하기 어렵다) —
# 그래서 코멘트에서 우연히 걸리면 아래 허용 목록에 추가한다(계속 인간이 감시).
VERB_HITS="$(grep -rnE '>[^<]*(생성|등록|만들기|만들다|편집|변경|제거|지우기|지우다|끄기|중지|정지|켜기)[^<]*<' \
  frontend/src --include='*.js' --include='*.jsx' | grep -vE '\.test\.jsx?:' | grep -v '편집기' || true)"
VERB_VIOLATIONS="$(echo "$VERB_HITS" | grep -vE \
  '(AI로 문제 생성|생성 중…|주제를 적고 생성하면|문장 요약 만들기|요약 만드는 중|AI 요약 생성|등록된 부서|등록된 직책|등록된 조직|임시 비밀번호는 생성|예: 서버 등록 IP|역할 변경|비밀번호 변경|시 변경을 요구|변경 이력|변경 기록|새 변경으로 다시 기록|적용 시점은 항목마다|이전 변경 이력을 볼|어떤 변경도 저장되지|차단된 변경 시도|>변경<|필터 지우기|검색어 지우기|카테고리 지우기)' || true)"
if [ -z "$VERB_VIOLATIONS" ]; then ok "no banned verb synonyms in user-facing text"; else echo "$VERB_VIOLATIONS"; fail "표준 동사표(UX_WRITING.md §3) 위반 — 금지된 동의어가 화면 텍스트에 있다"; fi

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

step "User-facing text avoids the banned glyphs"
# 사용자 지시(§8): 화면 문구에서 가운뎃점(·)과 em 대시(—)를 쓰지 않는다.
# 한 번 훑고 끝내면 다음 화면에서 다시 새어 나가므로 검사로 고정한다.
# grep 을 쓰지 않는 이유는 검사기 docstring 에 적어 뒀다 — 저장소의 두 문자 5,985개 중
# 86%가 한국어 주석·docstring 이라 단순 grep 은 오탐 5,157개를 낸다.
if UTEXT="$("$PY" scripts/check_user_text.py 2>&1)"; then
  ok "$(echo "$UTEXT" | tail -1)"
else
  echo "$UTEXT"; fail "사용자에게 보이는 문구에 쓰지 않기로 한 문자가 있다"
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

step "fieldLimits.json matches backend Pydantic schemas (PA-RC-0005)"
# 관리자 폼 maxLength의 정본은 Pydantic 스키마다 - 생성기를 다시 안 돌리면 화면이 조용히
# 낡은 상한을 계속 보여준다(check_bundle_fresh.py와 같은 관용).
if FLIM="$("$PY" scripts/check_field_limits_fresh.py 2>&1)"; then
  ok "$(echo "$FLIM" | tail -1)"
else
  echo "$FLIM"; fail "fieldLimits.json이 지금의 백엔드 스키마와 다르다"
fi

step "Committed frontend bundle matches the sources"
# 이 저장소는 빌드 산출물을 git 에 커밋한다(서버에 Node 불필요). 대신 소스만 고치고 번들을
# 안 만들면 git 으로 설치한 서버가 **조용히 옛 UI 를 돌린다** - 로그에도 화면에도 흔적이 없다.
# 0-E-11 에서 "최종 빌드 뒤에 연결한다"고 적어 두고 실제로는 안 걸었다. 감사가 그걸 찾았다.
if BFRESH="$("$PY" scripts/check_bundle_fresh.py 2>&1)"; then
  ok "$(echo "$BFRESH" | tail -1)"
else
  echo "$BFRESH"; fail "프런트 소스가 커밋된 번들보다 새롭다"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then echo "STATIC_CHECKS_OK"; else echo "STATIC_CHECKS_FAILED"; fi
exit $FAIL
