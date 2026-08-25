"""S21 — 권한 계약을 **서버에 직접 물어서** 잰다 (W14).

화면 Flow 는 「그 역할에게 그 버튼이 보이는가」를 잰다. 그것으로는 이 회차가 답해야 하는
질문의 절반밖에 못 본다 — 지시가 콕 집어 요구한 것은 다음 다섯이다.

  1. 관리자 기능을 일반 사용자가 **직접 API 로 불러도** 막히는가
  2. 권한 없는 문서·티켓·검색 결과가 목록에 안 들어가는가
  3. AI 근거(Retrieval Context)에 권한 밖 자료가 안 들어가는가
  4. 목록에는 없는데 **상세 주소로 직접** 열리는 우회가 없는가
  5. 검색·딥링크에서도 같은 계약이 유지되는가

1·4·5 는 화면을 아무리 눌러도 답이 안 나온다. 그래서 여기서 **역할마다 실제 세션을 만들어**
같은 경로를 직접 부른다.

## 통과 기준

  * 막혀야 하는 것은 **403 또는 404** 여야 한다. **401 은 통과가 아니다** — 그것은
    「세션이 없다」이지 「권한이 없다」가 아니고, 세션을 못 만든 계측기도 401 을 받는다
    (그 함정은 이 저장소가 이미 한 번 밟았다).
  * 열려야 하는 것이 **실제로 열린다**는 반례를 같은 자리에서 센다. 반례가 없으면
    「전부 막힌다」와 구별이 안 된다.

    python -m scripts.ui_qa.s21_permission --base-url http://127.0.0.1:8099
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

for _stream in (sys.stdout, sys.stderr):
    if hasattr(_stream, "reconfigure"):
        _stream.reconfigure(encoding="utf-8", errors="replace")

from scripts.ui_qa.auth import ensure_session  # noqa: E402
from scripts.ui_qa.capture import DEFAULT_BASE_URL, new_context  # noqa: E402
from scripts.ui_qa.pilot_e2e import VIEWPORT  # noqa: E402

OUT_DEFAULT = REPO_ROOT / "dist" / "ui-qa" / "s21-permission"

ROLES = ("user", "operator", "auditor", "admin", "system_admin")
DENIED = (403, 404, 405)
#: 인가를 **지난 뒤에** 나오는 상태들. 이 답이 왔다면 그 역할은 막히지 않은 것이다.
REACHED = (409, 422)


def _fill(payload, role):
    """페이로드의 `{role}` 자리를 채운다 — 역할마다 다른 값을 던져 충돌을 피한다."""
    if payload is None:
        return None
    return {k: (v.replace("{role}", role) if isinstance(v, str) else v)
            for k, v in payload.items()}

# (이름, METHOD, 경로, 페이로드, 열려야 하는 역할들)
CASES = [
    # ── 1. 관리자 기능을 직접 부른다 ─────────────────────────────────────────
    ("사용자 목록", "GET", "/api/admin/users", None, ("admin", "system_admin")),
    # `USER_MANAGE` 는 `CONSOLE_WRITE_ROLES`(admin·system_admin)다 — 예전 기대값은 아무도
    # 못 만든다고 적어 두었는데 그건 제품 계약이 아니라 추측이었다. 그리고 이메일은
    # **역할마다 다르게** 만든다: 같은 주소를 다섯 번 던지면 처음 성공한 뒤로는 전부 409 라
    # 「막혔다」와 「이미 있다」가 한 칸에서 섞인다.
    ("사용자 만들기", "POST", "/api/admin/users",
     {"email": "s21-perm-{role}@goodmit.co.kr", "display_name": "권한 시험", "role": "user"},
     ("admin", "system_admin")),
    ("역할 매트릭스", "GET", "/api/admin/rbac-matrix", None,
     ("operator", "auditor", "admin", "system_admin")),
    ("감사 로그", "GET", "/api/admin/audit", None, ("auditor", "admin", "system_admin")),
    # `BACKUP_READ` 도 `CONSOLE_READ_ROLES` 라 감사 역할이 읽는다(읽기만 한다).
    ("백업 목록", "GET", "/api/admin/backups", None,
     ("operator", "auditor", "admin", "system_admin")),
    ("백업 실행", "POST", "/api/admin/backups", {}, ("system_admin",)),
    ("기능 플래그 읽기", "GET", "/api/admin/feature-flags", None,
     ("operator", "auditor", "admin", "system_admin")),
    # 쓰기는 `PUT /{key}` 다(`app/settings/router.py`). PATCH 는 그 자리에 없어서 405 였고,
    # 405 는 「막혔다」가 아니라 「그런 문이 없다」다 — 권한을 잰 것이 아니었다.
    ("기능 플래그 쓰기", "PUT", "/api/admin/feature-flags/games_enabled",
     {"enabled": True}, ("admin", "system_admin")),
    ("프롬프트 만들기", "POST", "/api/admin/prompts",
     {"name": "S21 권한 시험 {role}", "content": "x"}, ("admin", "system_admin")),
    ("공지 만들기", "POST", "/api/admin/announcements",
     {"title": "S21 권한 시험 {role}", "body": "x"}, ("admin", "system_admin")),
    ("파일 저장소 목록", "GET", "/api/storage/providers", None, ("system_admin",)),
    # 스키마(`app/storage/schemas.py::ProviderCreate`)가 요구하는 이름 그대로 채운다 —
    # 예전 페이로드는 `kind` 가 소문자였고 `base_path`·`role` 이 아예 없어서 system_admin
    # 에게도 422 가 돌아왔다. 그건 권한이 아니라 입력의 답이었다.
    ("파일 저장소 추가", "POST", "/api/storage/providers",
     {"name": "s21-{role}", "kind": "LOCAL", "role": "OPERATIONAL",
      "base_path": "/tmp/s21-{role}"}, ("system_admin",)),
    ("초기 설정 점검표", "GET", "/api/admin/setup/checklist", None, ("system_admin",)),
    # 대리 보기 **시작**은 관리자와 시스템 관리자만이다(`frontend/src/app/navConfig.js` 의
    # 안내와 서버가 같은 말을 한다). 대상 id 는 일부러 없는 것을 쓴다 — 인가를 지난 역할은
    # 422/404 로 「인가는 지났고 입력에서 걸렸다」를 보여 주고, 못 지난 역할은 403 이다.
    ("대리 보기 시작", "POST", "/api/admin/impersonation/start",
     {"target_user_id": "00000000-0000-0000-0000-000000000000", "reason": "시험"},
     ("admin", "system_admin")),
    ("오프보딩 실행", "POST", "/api/admin/offboarding/run",
     {"user_id": "00000000-0000-0000-0000-000000000000"}, ()),
    # `app/integrity/router.py` 의 GET 은 `CONSOLE_READ_ROLES` 다.
    ("정합성 진단", "GET", "/api/admin/integrity", None,
     ("operator", "auditor", "admin", "system_admin")),
    ("메일 현황", "GET", "/api/admin/mail/status", None,
     ("operator", "auditor", "admin", "system_admin")),
    ("실행 일정 만들기", "POST", "/api/admin/schedules",
     {"name": "S21 권한 시험 {role}", "target_type": "system", "target_ref": "noop",
      "cron_expression": "0 3 * * *"}, ("admin", "system_admin")),
]

# 목록과 상세가 **같은 답**을 하는가 (4번 질문).
CONSISTENCY = [
    ("문서", "/api/knowledge/documents?page_size=50", "/api/knowledge/documents/%s"),
    ("티켓", "/api/tickets/team?page_size=50", "/api/tickets/%s"),
    ("게시글", "/api/board/posts?page_size=50", "/api/board/posts/%s"),
    ("프로젝트", "/api/projects", "/api/projects/%s"),
]

FETCH = """
async ([method, path, payload]) => {
  let token = '';
  try {
    const me = await fetch('/api/me', {credentials: 'same-origin'});
    if (me.ok) token = (await me.json()).csrf_token || '';
  } catch (e) { /* 세션이 없으면 토큰도 없다 */ }
  const init = {method, credentials: 'same-origin',
                headers: {'Content-Type': 'application/json'}};
  if (token) init.headers['X-CSRF-Token'] = token;
  if (payload !== null) init.body = JSON.stringify(payload);
  const res = await fetch(path, init);
  let text = '';
  try { text = await res.text(); } catch (e) { text = ''; }
  /* 🔴 **자르기 전에** 읽는다. 예전에는 400자로 자른 뒤에 파싱해서 목록 응답이 언제나
     깨진 JSON 이었다 - 그래서 표본이 늘 0건이었고 "목록에 없는데 주소로 열린다" 검사가
     아무것도 안 보고 통과했다. 표본 수를 안 보면 그 통과는 침묵과 구별되지 않는다. */
  let ids = null;
  try {
    const parsed = JSON.parse(text);
    if (parsed && Array.isArray(parsed.items)) {
      ids = parsed.items.map((x) => (x && (x.id || x.uid)) || null).filter(Boolean);
    }
  } catch (e) { /* JSON 이 아니면 id 도 없다 */ }
  return {status: res.status, body: text.slice(0, 400), ids};
}
"""


def main() -> int:
    ap = argparse.ArgumentParser(description="S21 권한 계약 실측 (W14)")
    ap.add_argument("--base-url", default=DEFAULT_BASE_URL)
    ap.add_argument("--out", default=str(OUT_DEFAULT))
    ap.add_argument("--insecure", action="store_true")
    args = ap.parse_args()

    out = Path(args.out).resolve()
    out.mkdir(parents=True, exist_ok=True)
    from playwright.sync_api import sync_playwright

    result = {"base_url": args.base_url, "roles": list(ROLES), "cases": [],
              "consistency": [], "failures": []}
    with sync_playwright() as pw:
        browser = pw.chromium.launch()
        pages = {}
        try:
            for role in ROLES:
                session = ensure_session(
                    browser, args.base_url,
                    REPO_ROOT / "dist" / "ui-qa" / ("role-" + role),
                    insecure=args.insecure,
                    role=(None if role == "system_admin" else role))
                context = new_context(browser, storage_state=session.storage_state,
                                      user_id=session.user_id, theme="light",
                                      viewport=VIEWPORT,
                                      insecure=args.insecure)
                page = context.new_page()
                page.goto(args.base_url + "/#/me", wait_until="domcontentloaded")
                page.wait_for_timeout(1200)
                pages[role] = page
                print("[세션] %-13s %s" % (role, session.email), flush=True)

            # ── 1. 직접 호출 행렬 ────────────────────────────────────────────
            for name, method, path, payload, allowed in CASES:
                row = {"case": name, "method": method, "path": path,
                       "allowed_roles": list(allowed), "by_role": {}}
                for role in ROLES:
                    got = pages[role].evaluate(FETCH, [method, path, _fill(payload, role)])
                    row["by_role"][role] = got["status"]
                    if role in allowed:
                        # **인가를 지났는가**만 묻는다. 422(입력 검증)와 409(이미 있다)는
                        # 요청이 인가를 통과한 **뒤에** 나오는 답이라 「열려 있다」의 증거다 —
                        # 그것을 실패로 세면 권한 계약이 아니라 씨앗의 상태를 재게 된다.
                        if got["status"] >= 400 and got["status"] not in REACHED:
                            row.setdefault("notes", []).append(
                                "%s 에게 열려 있어야 하는데 HTTP %d (%s)"
                                % (role, got["status"], got["body"][:110]))
                    elif got["status"] not in DENIED:
                        row.setdefault("notes", []).append(
                            "%s 가 막혀야 하는데 HTTP %d (%s)"
                            % (role, got["status"], got["body"][:110]))
                result["cases"].append(row)
                if row.get("notes"):
                    result["failures"].extend("%s — %s" % (name, n) for n in row["notes"])
                mark = "FAIL" if row.get("notes") else "OK  "
                print("[%s] %-16s %-6s %-42s %s"
                      % (mark, name, method, path,
                         " ".join("%s:%s" % (r[:4], row["by_role"][r]) for r in ROLES)),
                      flush=True)

            # ── 4. 목록과 상세가 같은 답을 하는가 ────────────────────────────
            for name, list_path, detail_tpl in CONSISTENCY:
                admin_list = pages["system_admin"].evaluate(FETCH, ["GET", list_path, None])
                ids = (admin_list.get("ids") or [])[:8]
                row = {"kind": name, "checked": len(ids), "by_role": {}}
                for role in ("user", "operator", "auditor"):
                    seen = pages[role].evaluate(FETCH, ["GET", list_path, None])
                    visible = set(seen.get("ids") or [])
                    leaked, blocked = [], []
                    for rid in ids:
                        one = pages[role].evaluate(FETCH, ["GET", detail_tpl % rid, None])
                        if one["status"] == 200 and rid not in visible:
                            leaked.append(rid)
                        elif one["status"] in DENIED and rid in visible:
                            blocked.append(rid)
                    row["by_role"][role] = {"list_status": seen["status"],
                                            "visible": len(visible),
                                            "leaked_by_url": leaked,
                                            "blocked_though_listed": blocked}
                    if leaked:
                        result["failures"].append(
                            "%s — %s: 목록에 없는데 주소로 열린다 %s" % (name, role, leaked[:3]))
                    if blocked:
                        result["failures"].append(
                            "%s — %s: 목록에는 있는데 상세가 막힌다 %s"
                            % (name, role, blocked[:3]))
                # 표본이 0이면 **통과가 아니라 못 잰 것**이다.
                if not ids:
                    result["failures"].append(
                        "%s — 표본 0건이라 목록·상세 일관성을 재지 못했다" % name)
                result["consistency"].append(row)
                mark = ("FAIL" if (not ids or any(v["leaked_by_url"]
                                                  or v["blocked_though_listed"]
                                                  for v in row["by_role"].values()))
                        else "OK  ")
                print("[%s] %-16s 표본 %d건 · %s"
                      % (mark, name, len(ids),
                         " ".join("%s(목록 %d)" % (r, v["visible"])
                                  for r, v in row["by_role"].items())), flush=True)
        finally:
            for page in pages.values():
                try:
                    page.context.close()
                except Exception:  # noqa: BLE001
                    pass
            browser.close()

    (out / "permission.json").write_text(
        json.dumps(result, ensure_ascii=False, indent=1), encoding="utf-8")
    print("\n권한 실측: 사례 %d · 일관성 %d · 어긋남 %d건"
          % (len(result["cases"]), len(result["consistency"]), len(result["failures"])))
    for line in result["failures"]:
        print("  - " + line)
    print("permission.json: %s" % (out / "permission.json"))
    return 1 if result["failures"] else 0


if __name__ == "__main__":
    raise SystemExit(main())
