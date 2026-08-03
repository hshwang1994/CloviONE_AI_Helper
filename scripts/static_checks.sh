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

step "Tracked files do not import untracked modules"
# 실제로 한 번 터진 결함이다. 백엔드 작업의 일부만 커밋되면서 추적되는 파일이
# 미추적 모듈을 import 하는 상태가 HEAD에 올라갔다 — 워킹트리에서는 전부 통과하고
# fresh clone 에서만 죽는다. 즉 배포 서버에서 처음 발견된다.
if TRACKED="$("$PY" scripts/check_tracked_imports.py 2>&1)"; then
  ok "$(echo "$TRACKED" | tail -1)"
else
  echo "$TRACKED"; fail "커밋 누락 — 추적 파일이 미추적 모듈을 import 한다"
fi

echo ""
if [ "$FAIL" -eq 0 ]; then echo "STATIC_CHECKS_OK"; else echo "STATIC_CHECKS_FAILED"; fi
exit $FAIL
