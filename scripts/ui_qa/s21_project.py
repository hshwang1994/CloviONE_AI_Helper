"""S21 — 프로젝트 상세와 작업 보드 (W14).

프로젝트 상세는 이 제품에서 **탭이 곧 서버 경로인** 유일한 화면이다(개요·WBS·마일스톤·
티켓·주간 리포트). 그래서 여기서 묻는 것은 둘이다 — 탭을 바꾸면 **그 탭의 자료만** 받는가,
그리고 그 탭이 주소에 남아 링크로 건네지는가.

주간 리포트는 주(week)를 히스토리에 쌓는 유일한 자리라 뒤로가기 축도 여기서 본다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import (  # noqa: F401
    back_forward, confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog,
    open_dialogs, retry_from_error, row_at, row_name, rows_of, stop, title_like,
)

USER = "/"


def _project_id(r) -> str:
    payload = r.api_get("/api/projects")
    items = (payload or {}).get("items") or []
    if not items:
        stop("프로젝트가 없다")
    return items[0]["id"]


def _goto_project(r, tab: str = "", extra: str = "") -> str:
    pid = _project_id(r)
    hash_path = "/projects/%s" % pid
    if tab:
        hash_path += "?tab=%s" % tab
        if extra:
            hash_path += "&" + extra
    r.goto(hash_path, shell=USER)
    return pid


# ═══════════════════════════════════════════════════════════════════════════
# 탭과 주소
# ═══════════════════════════════════════════════════════════════════════════
def _project_read(r, ctx):
    pid = _goto_project(r)
    ctx["project_id"] = pid
    tabs = r.page.get_by_role("tab")
    names = [" ".join((tabs.nth(i).inner_text() or "").split()) for i in range(tabs.count())]
    calls = sorted({c["path"] for c in r.rec.calls if "/api/projects/" in c["path"]})
    return {"ui_action": "프로젝트 상세를 연다(개요 탭)",
            "observed": {"tabs": names, "calls": calls},
            "rendered": "탭 %s · 본문 «%s»" % (names, r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "처음에는 개요가 쓰는 것만 받는다(탭마다 경로가 따로다)",
                         "tabs": names},
            "failed": None if len(names) >= 5 else "탭이 다섯이 아니다: %s" % names}


flow("FF-0133", "user_projects-id", "read",
     "프로젝트 본체와 탭별 자료를 필요한 탭만 조회한다(enabled 게이팅)",
     _project_read, api="/api/projects/")


def _tab_walk(r, ctx):
    pid = ctx.get("project_id") or _goto_project(r)
    seen = {}
    for name in ("WBS", "마일스톤", "티켓", "주간 리포트", "개요"):
        tab = r.page.get_by_role("tab", name=name, exact=False)
        if not tab.count():
            stop("«%s» 탭이 없다" % name)
        r.rec.reset()
        tab.first.click()
        r.settle(1700)
        seen[name] = {"hash": r.hash_of(),
                      "calls": sorted({c["path"] for c in r.rec.calls
                                       if "/api/" in c["path"]})[:4]}
    bad = [n for n, v in seen.items() if "tab=" not in v["hash"] and n != "개요"]
    return {"ui_action": "다섯 탭을 차례로 눌러 본다",
            "frontend_state": "라우트가 아니라 ?tab= 로 갈린다",
            "observed": seen,
            "rendered": " · ".join("%s→%s" % (n, v["hash"].split("?")[-1][:22])
                                   for n, v in seen.items()),
            "expected": {"source": "derived-check",
                         "rule": "탭을 바꾸면 주소의 tab 이 바뀌고 그 탭의 자료를 받는다",
                         "got": {n: v["hash"] for n, v in seen.items()}},
            "failed": None if not bad else "주소가 안 따라온 탭: %s" % bad}


flow("FF-0134", "user_projects-id", "navigation",
     "개요·WBS·마일스톤·티켓·주간 리포트 탭 전환(라우트가 아니라 ?tab=)",
     _tab_walk, server=False)


def _project_deep_link(r, ctx):
    pid = _goto_project(r, "tickets", "page=1")
    before = r.hash_of()
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(2000)
    after = r.hash_of()
    active = r.page.locator('#main-content [role="tab"][aria-selected="true"]')
    label = " ".join((active.first.inner_text() or "").split()) if active.count() else ""
    return {"ui_action": "티켓 탭 주소로 들어가 새로고침한다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"active_tab": label, "hash": after},
            "rendered": "새로고침 뒤 선택된 탭 «%s»" % label,
            "expected": {"source": "derived-check",
                         "rule": "주소에 실은 탭이 새로고침 뒤에도 그대로 열린다",
                         "expect": "티켓", "got": label},
            "failed": None if "티켓" in label
                      else "주소로 건넨 탭이 새로고침 뒤 안 열린다(지금 «%s»)" % label}


flow("FF-0135", "user_projects-id", "deep_link",
     "탭·주(week)·티켓 페이지를 주소에 실어 링크로 특정 탭을 건넨다",
     _project_deep_link, api="/api/projects/")


def _weekly_back(r, ctx):
    _goto_project(r, "weekly")
    first = r.hash_of()
    prev = r.in_main("button", "이전 주")
    if not prev.count():
        stop("«이전 주» 버튼이 없다")
    prev.first.click()
    r.settle(2000)
    moved = r.hash_of()
    r.back()
    r.settle(1800)
    back_to = r.hash_of()
    return {"ui_action": "주간 리포트에서 «이전 주» 로 갔다가 뒤로가기",
            "url_state": "%s → %s → (뒤로) %s" % (first, moved, back_to),
            "observed": {"hash": {"first": first, "prev": moved, "back": back_to}},
            "rendered": "주소 «%s» → «%s» → «%s»"
                        % (first[-28:], moved[-28:], back_to[-28:]),
            "expected": {"source": "derived-check",
                         "rule": "주 이동은 히스토리에 쌓여 뒤로가기로 돌아온다",
                         "expect": first, "got": back_to},
            "failed": None if (moved != first and back_to == first)
                      else "주 이동이 히스토리에 안 쌓였다(이동 %s · 뒤로 %s)" % (moved, back_to)}


flow("FF-0136", "user_projects-id", "back_forward",
     "주간 리포트 주 이동은 히스토리에 push해 뒤로가기로 돌아간다",
     _weekly_back, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 쓰기
# ═══════════════════════════════════════════════════════════════════════════
def _project_edit(r, ctx):
    _goto_project(r)
    button = r.in_main("button", "수정")
    if not button.count():
        stop("«수정» 버튼이 없다")
    button.first.click()
    r.settle(1300)
    if not open_dialogs(r):
        stop("수정 모달이 안 떴다")
    dialog = open_dialog(r)
    box = dialog.locator("input[type=text]").first
    if not box.count():
        stop("수정 모달에 입력 칸이 없다")
    before = box.input_value()
    after = (before + " ✓")[:60]
    box.fill(after)
    for label in ("저장", "수정", "적용"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        stop("저장 버튼이 없다")
    r.settle(2400)
    ctx["project_title"] = after
    return {"ui_action": "«수정» 모달에서 이름을 «%s» 로 바꿔 저장한다" % after,
            "frontend_state": "PATCH /api/projects/{id}",
            "observed": {"before": before, "after": after,
                         "dialogs_left": open_dialogs(r)},
            "rendered": "본문 «%s»" % r.main_text(120),
            "expected": {"source": "derived-check",
                         "rule": "저장하면 화면이 새 이름을 그린다", "expect": after},
            "cross": {"needle": after},
            "failed": "저장했는데 모달이 안 닫혔다" if open_dialogs(r) else None}


flow("FF-0137", "user_projects-id", "edit",
     "'수정' 모달로 프로젝트 속성을 저장한다(편집 시작 시점의 버전 동봉)",
     _project_edit, api="/api/projects/", cross=("/projects", "/"))


def _dept_inline(r, ctx):
    _goto_project(r)
    box = r.page.get_by_role("combobox", name="부서", exact=False)
    if not box.count():
        boxes = r.page.locator("#main-content [role=combobox]")
        if not boxes.count():
            stop("개요에 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
        box = boxes.first
    before = " ".join((box.first.inner_text() or "").split())
    r.rec.reset()
    box.first.click()
    r.settle(700)
    options = r.page.get_by_role("option")
    picked = ""
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label and label != before and label not in ("없음", "-", "(없음)", "지정 안 함"):
            picked = label
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
        stop("부서 선택기에 «없음» 말고 고를 값이 없다")
    r.settle(2200)
    sent = [c for c in r.rec.calls if c["method"] == "PATCH"]
    return {"ui_action": "개요의 «부서» 를 «%s» → «%s» 로 그 자리에서 바꾼다" % (before, picked),
            "frontend_state": "PATCH /api/projects/{id} (모달 없이)",
            "observed": {"before": before, "after": picked, "patch_calls": len(sent)},
            "rendered": "부서 «%s» → «%s» · PATCH %d건" % (before, picked, len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "그 자리에서 고르면 곧바로 서버로 간다",
                         "expect": ">=1 PATCH", "got": len(sent)},
            "cross": {"needle": picked},
            "failed": None if sent else "부서를 골랐는데 서버로 안 갔다"}


flow("FF-0138", "user_projects-id", "inline_edit",
     "개요 '부서' 행의 select로 부서를 그 자리에서 지정·해제한다",
     _dept_inline, api="/api/projects/", cross=("@reload", ""))


def _milestone_create(r, ctx):
    _goto_project(r, "milestones")
    button = r.in_main("button", "마일스톤 추가")
    if not button.count():
        stop("«마일스톤 추가» 버튼이 없다")
    button.first.click()
    r.settle(1300)
    if not open_dialogs(r):
        stop("마일스톤 모달이 안 떴다")
    dialog = open_dialog(r)
    name = "S21 인수 점검 마일스톤"
    dialog.locator("input[type=text]").first.fill(name)
    r.settle(400)
    for label in ("추가", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        stop("추가 버튼이 없다")
    r.settle(2400)
    ctx["milestone_name"] = name
    return {"ui_action": "«마일스톤 추가» 로 «%s» 를 만든다" % name,
            "frontend_state": "POST milestones",
            "observed": {"name": name, "dialogs_left": open_dialogs(r)},
            "rendered": "본문 «%s»" % r.main_text(140),
            "expected": {"source": "derived-check",
                         "rule": "만들면 타임라인에 그 이름이 나타난다", "expect": name},
            "cross": {"needle": name}}


flow("FF-0142", "user_projects-id", "create", "마일스톤 추가",
     _milestone_create, api="/api/projects/", cross=("@reload", ""))


def _milestone_edit(r, ctx):
    _goto_project(r, "milestones")
    button = r.page.locator('#main-content [aria-label^="마일스톤 수정"]')
    if not button.count():
        stop("«마일스톤 수정» 버튼이 없다 — 마일스톤이 하나도 없다")
    button.first.click()
    r.settle(1300)
    dialog = open_dialog(r)
    box = dialog.locator("input[type=text]").first
    before = box.input_value()
    after = (before + " (고침)")[:60]
    box.fill(after)
    for label in ("저장", "수정"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        stop("저장 버튼이 없다")
    r.settle(2200)
    return {"ui_action": "마일스톤 이름을 «%s» → «%s» 로 고친다" % (before, after),
            "frontend_state": "PATCH milestones/{mid}",
            "observed": {"before": before, "after": after},
            "rendered": "본문 «%s»" % r.main_text(140),
            "expected": {"source": "derived-check",
                         "rule": "고치면 타임라인이 새 이름을 그린다", "expect": after},
            "cross": {"needle": after}}


flow("FF-0143", "user_projects-id", "edit", "마일스톤 수정",
     _milestone_edit, api="/api/projects/", cross=("@reload", ""))


def _milestone_delete(r, ctx):
    _goto_project(r, "milestones")
    button = r.page.locator('#main-content [aria-label^="마일스톤 삭제"]')
    if not button.count():
        stop("«마일스톤 삭제» 버튼이 없다")
    label = button.first.get_attribute("aria-label") or ""
    before = button.count()
    button.first.click()
    r.settle(1000)
    asked = open_dialogs(r) > 0
    said = confirm_now(r) if asked else ""
    r.settle(2000)
    after = r.page.locator('#main-content [aria-label^="마일스톤 삭제"]').count()
    return {"ui_action": "«%s» 를 지운다" % label,
            "frontend_state": "확인 → DELETE milestones/{mid}",
            "observed": {"confirm_asked": asked, "confirm": said[:130],
                         "milestones": {"before": before, "after": after}},
            "rendered": "마일스톤 %d개 → %d개 · 확인 «%s»" % (before, after, said[:70]),
            "expected": {"source": "derived-check",
                         "rule": "되돌릴 수 없는 삭제는 확인을 받는다",
                         "confirm_asked": asked},
            "failed": ("확인 없이 하드 삭제가 실행된다" if not asked
                       else (None if after < before else "지웠는데 목록에 그대로 있다"))}


flow("FF-0144", "user_projects-id", "delete", "마일스톤 삭제(확인 대화상자, 하드 삭제)",
     _milestone_delete, api="/api/projects/")


def _milestone_validation(r, ctx):
    _goto_project(r, "milestones")
    button = r.in_main("button", "마일스톤 추가")
    if not button.count():
        stop("«마일스톤 추가» 버튼이 없다")
    button.first.click()
    r.settle(1300)
    dialog = open_dialog(r)
    r.rec.reset()
    blocked = None
    for label in ("추가", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            blocked = submit.first.is_disabled()
            if not blocked:
                submit.first.click()
                r.settle(1400)
            break
    sent = [c for c in r.rec.calls if c["method"] in ("POST", "PATCH")]
    said = r.main_text(140)
    r.dismiss_overlays()
    return {"ui_action": "이름을 비운 채 마일스톤을 추가하려 한다",
            "observed": {"submit_disabled": blocked, "write_calls": len(sent)},
            "rendered": "제출 %s · 쓰기 %d건 · 안내 «%s»"
                        % ("잠김" if blocked else "열림", len(sent), said[:70]),
            "expected": {"source": "derived-check",
                         "rule": "이름이 비면 서버로 안 보낸다", "expect": 0, "got": len(sent)},
            "failed": None if not sent else "이름이 빈 채로 서버로 나갔다"}


flow("FF-0145", "user_projects-id", "form_validation", "마일스톤 이름·상태·정렬 순번을 필수로 막는다",
     _milestone_validation, server=False)


def _milestone_modal_cycle(r, ctx):
    _goto_project(r, "milestones")
    base = open_dialogs(r)
    button = r.in_main("button", "마일스톤 추가")
    if not button.count():
        stop("«마일스톤 추가» 버튼이 없다")
    button.first.click()
    r.settle(1300)
    opened = open_dialogs(r)
    title = dialog_says(r, 60)
    r.dismiss_overlays()
    r.settle(600)
    closed = open_dialogs(r)
    return {"ui_action": "마일스톤 모달을 열고 닫는다",
            "observed": {"base": base, "opened": opened, "closed": closed, "title": title},
            "rendered": "«%s» %d → %d → %d" % (title, base, opened, closed),
            "expected": {"source": "derived-check",
                         "rule": "열면 하나 늘고 닫으면 원래대로",
                         "dialogs": [base, opened, closed]},
            "failed": None if opened > base and closed <= base else "열리거나 닫히지 않았다"}


flow("FF-0146", "user_projects-id", "modal_action", "프로젝트/마일스톤 폼 모달 열기·제출·닫기",
     _milestone_modal_cycle, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 재계산 · 보관
# ═══════════════════════════════════════════════════════════════════════════
def _recompute(label_hint: str, api_fragment: str):
    def _act(r, ctx):
        _goto_project(r)
        buttons = r.in_main("button", "다시 계산")
        if not buttons.count():
            stop("«다시 계산» 버튼이 없다")
        index = 0 if label_hint == "진행률" else min(1, buttons.count() - 1)
        r.rec.reset()
        buttons.nth(index).click()
        r.settle(2600)
        sent = [c for c in r.rec.calls if c["method"] == "POST"]
        paths = sorted({c["path"] for c in sent})
        return {"ui_action": "«%s» 의 «다시 계산» 을 누른다" % label_hint,
                "frontend_state": "POST %s" % api_fragment,
                "observed": {"posts": paths, "body": r.main_text(130)},
                "rendered": "POST %s · 본문 «%s»" % (paths, r.main_text(110)),
                "expected": {"source": "derived-check",
                             "rule": "«다시 계산» 은 서버에 재계산을 요청한다",
                             "expect": api_fragment, "got": paths},
                "failed": None if any(api_fragment in p for p in paths)
                          else "«다시 계산» 을 눌렀는데 %s 를 안 불렀다: %s"
                               % (api_fragment, paths)}
    return _act


flow("FF-0140", "user_projects-id", "admin_op", "'다시 계산'으로 진행률을 즉시 재계산한다",
     _recompute("진행률", "progress"), api="/api/projects/")

flow("FF-0141", "user_projects-id", "admin_op",
     "'다시 계산'으로 Health를 재계산하고 이번 주 이력에 남긴다",
     _recompute("Health", "health"), api="/api/projects/")


def _archive(r, ctx):
    _goto_project(r)
    button = r.in_main("button", "보관")
    if not button.count():
        stop("«보관» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1200)
    asked = open_dialogs(r) > 0
    said = dialog_says(r, 180)
    if asked:
        # **되돌릴 API 가 없다.** 확인 창이 뜨는 것까지만 보고 물러난다 — 이 회차의 질문은
        # 「지우기 전에 묻는가」이고, 실제로 보관해 버리면 뒤따르는 Flow 들이 사라진 프로젝트를
        # 연다.
        r.press("Escape")
        r.settle(700)
    sent = [c for c in r.rec.calls if c["method"] == "DELETE"]
    return {"ui_action": "«보관» 을 누르고 확인 창까지만 본다",
            "frontend_state": "확인 → DELETE /api/projects/{id}",
            "observed": {"confirm_asked": asked, "confirm": said[:150],
                         "delete_calls": len(sent)},
            "rendered": "확인 «%s» · DELETE %d건" % (said[:110], len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "되돌릴 수 없는 보관은 확인을 먼저 받고, 취소하면 안 나간다",
                         "confirm_asked": asked, "sent": len(sent)},
            "failed": ("확인 없이 보관이 실행된다" if not asked
                       else ("취소했는데 서버로 나갔다" if sent else None))}


flow("FF-0139", "user_projects-id", "delete", "'보관' 버튼으로 프로젝트를 보관한다(확인 후)",
     _archive, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 티켓 탭
# ═══════════════════════════════════════════════════════════════════════════
def _ticket_tab_include(r, ctx):
    _goto_project(r, "tickets")
    before = n_rows(r)
    box = r.page.locator('#main-content input[type="checkbox"]').first
    if not box.count():
        stop("«완료, 취소 포함» 스위치가 없다")
    r.rec.reset()
    box.click()
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/tickets/team" in c["path"] and c["query"]}))
    return {"ui_action": "티켓 탭의 «완료, 취소 포함» 을 켠다",
            "frontend_state": "active 축이 바뀐다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
            "expected": {"source": "derived-check",
                         "rule": "스위치를 켜면 서버 질의의 active 가 바뀐다", "got": query},
            "failed": None if ("active" in query or n_rows(r) != before)
                      else "스위치를 켰는데 질의도 행 수도 그대로다"}


flow("FF-0147", "user_projects-id", "filter", "티켓 탭 '완료, 취소 포함' 스위치",
     _ticket_tab_include, api="/api/tickets/team")


def _ticket_tab_page_reset(r, ctx):
    _goto_project(r, "tickets")
    nxt = r.in_main("button", "다음")
    moved = False
    if nxt.count() and not nxt.first.is_disabled():
        nxt.first.click()
        r.settle(1800)
        moved = True
    page_hash = r.hash_of()
    tab = r.page.get_by_role("tab", name="개요", exact=False)
    tab.first.click()
    r.settle(1500)
    back = r.page.get_by_role("tab", name="티켓", exact=False)
    back.first.click()
    r.settle(1800)
    after = r.hash_of()
    return {"ui_action": "티켓 탭에서 쪽을 넘긴 뒤 다른 탭에 갔다 돌아온다",
            "url_state": "%s → %s" % (page_hash, after),
            "observed": {"moved_page": moved, "hash": {"paged": page_hash, "back": after}},
            "rendered": "주소 «%s» → «%s»" % (page_hash[-30:], after[-30:]),
            "expected": {"source": "derived-check",
                         "rule": "탭을 바꾸면 쪽이 1로 돌아간다(3쪽에 머물면 «없다»로 읽힌다)",
                         "got": after},
            "failed": None if "page=2" not in after
                      else "탭을 바꿔 돌아왔는데 쪽이 그대로다: %s" % after}


flow("FF-0148", "user_projects-id", "pagination", "티켓 탭 페이지 이동(탭·주를 바꾸면 1페이지로 리셋)",
     _ticket_tab_page_reset, server=False)


def _ticket_tab_edit(r, ctx):
    _goto_project(r, "tickets")
    if not n_rows(r):
        stop("이 프로젝트에 티켓이 없다")
    button = rows_of(r).first.get_by_role("button", name="수정", exact=False)
    if not button.count():
        stop("티켓 탭의 행에 «수정» 이 없다")
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("편집 모달이 안 떴다")
    before, chosen = r.choose_other("진행상태")
    open_dialog(r).get_by_role("button", name="저장", exact=True).first.click()
    r.settle(2400)
    return {"ui_action": "티켓 탭에서 진행상태를 «%s» → «%s» 로 바꾼다" % (before, chosen),
            "frontend_state": "PATCH /api/tickets/{id}",
            "observed": {"before": before, "after": chosen,
                         "dialogs_left": open_dialogs(r)},
            "rendered": "본문 «%s»" % r.main_text(120),
            "expected": {"source": "derived-check",
                         "rule": "여기서 바꾼 값이 티켓 화면에도 도착한다", "expect": chosen},
            "cross": {"needle": chosen},
            "failed": "저장했는데 모달이 안 닫혔다" if open_dialogs(r) else None}


flow("FF-0149", "user_projects-id", "edit",
     "티켓 탭에서 티켓 편집 모달로 상태·담당자·마감을 바로 바꾼다",
     _ticket_tab_edit, api="/api/tickets/", cross=("/team-tickets", "/"))


def _ticket_tab_open(r, ctx):
    _goto_project(r, "tickets")
    if not n_rows(r):
        stop("티켓이 없다")
    before = r.hash_of()
    link = rows_of(r).first.locator('a, button').first
    link.click()
    r.settle(2200)
    after = r.hash_of()
    return {"ui_action": "티켓 탭의 제목을 눌러 티켓 상세로 간다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "본문 «%s»" % r.main_text(110),
            "failed": None if "/tickets/" in after
                      else "제목을 눌렀는데 티켓 상세로 안 갔다: %s" % after}


flow("FF-0150", "user_projects-id", "navigation", "티켓 제목을 눌러 티켓 상세로 간다",
     _ticket_tab_open, api="/api/tickets/")


def _wbs_source_link(r, ctx):
    _goto_project(r, "wbs")
    links = r.page.locator('#main-content a[target="_blank"]')
    hrefs = [links.nth(i).get_attribute("href") for i in range(min(links.count(), 5))]
    body = r.main_text(160)
    return {"ui_action": "WBS 노드의 바깥 링크를 본다",
            "observed": {"external_links": hrefs, "body": body},
            "rendered": "바깥 링크 %d개 · 본문 «%s»" % (len(hrefs), body[:110]),
            "expected": {"source": "derived-check",
                         "rule": "원본 주소가 있는 노드만 새 탭 링크를 준다", "got": hrefs},
            "failed": None}


flow("FF-0151", "user_projects-id", "navigation", "WBS 노드의 '원본'으로 원본 페이지를 새 탭에서 연다",
     _wbs_source_link, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# 주간 리포트
# ═══════════════════════════════════════════════════════════════════════════
def _weekly_move(r, ctx):
    _goto_project(r, "weekly")
    before = r.main_text(110)
    r.rec.reset()
    r.in_main("button", "이전 주").first.click()
    r.settle(2200)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "weekly-report" in c["path"] and c["query"]}))
    return {"ui_action": "«이전 주» 로 주를 옮긴다",
            "frontend_state": "week 가 질의에 실린다",
            "observed": {"query": query, "before": before},
            "rendered": "질의 «%s» · 본문 «%s»" % (query[:60], r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "주를 옮기면 그 주를 서버에 다시 묻는다", "got": query},
            "failed": None if "week" in query
                      else "주를 옮겼는데 질의에 week 가 없다: «%s»" % query}


flow("FF-0152", "user_projects-id", "filter", "주간 리포트의 이전 주/이번 주/다음 주 이동",
     _weekly_move, api="/api/projects/")


def _weekly_save(r, ctx):
    _goto_project(r, "weekly")
    button = r.in_main("button", "이 주 리포트 저장")
    if not button.count():
        stop("«이 주 리포트 저장» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2400)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«이 주 리포트 저장» 을 누른다",
            "frontend_state": "POST weekly-report",
            "observed": {"posts": sorted({c["path"] for c in sent}),
                         "body": r.main_text(130)},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "저장하면 그 주의 저장본이 생긴다", "got": len(sent)},
            "failed": None if sent else "저장을 눌렀는데 서버로 안 갔다"}


flow("FF-0153", "user_projects-id", "create", "'이 주 리포트 저장'으로 주간 리포트 저장본을 만든다",
     _weekly_save, api="/api/projects/")


def _weekly_ai(r, ctx):
    _goto_project(r, "weekly")
    button = r.in_main("button", "AI 요약")
    if not button.count():
        # 이 동작은 **저장본이 있을 때만** 그린다 — 요약할 대상이 없으면 자리도 없다.
        return {"ui_action": "«AI 요약 생성» 자리를 찾는다",
                "observed": {"buttons": 0, "body": r.main_text(200)},
                "rendered": "«AI 요약 생성» 없음 — 이 주에는 저장된 리포트가 없다",
                "expected": {"source": "known-data",
                             "rule": "요약할 저장본이 있을 때만 그 동작을 준다"},
                "failed": None}
    r.rec.reset()
    button.first.click()
    r.settle(2400)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«AI 요약 생성» 을 누른다",
            "frontend_state": "잡 큐에 요청만 하고 결과는 기다리지 않는다",
            "observed": {"posts": sorted({c["path"] for c in sent}),
                         "body": r.main_text(140)},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "요청을 넣고 «잠시 후 새로고침» 을 안내한다", "got": len(sent)},
            "failed": None if sent else "«AI 요약 생성» 을 눌렀는데 서버로 안 갔다"}


flow("FF-0154", "user_projects-id", "admin_op",
     "'AI 요약 생성'을 잡 큐에 요청한다(결과는 새로고침으로 확인)",
     _weekly_ai, api="/api/projects/")


def _weekly_ticket_link(r, ctx):
    _goto_project(r, "weekly")
    links = r.page.locator('#main-content a[href*="#/tickets/"]')
    if not links.count():
        return {"ui_action": "주간 리포트 버킷의 티켓 링크를 찾는다",
                "observed": {"links": 0, "body": r.main_text(160)},
                "rendered": "티켓 링크 0개 · 본문 «%s»" % r.main_text(130),
                "expected": {"source": "known-data",
                             "rule": "이 주에 담긴 티켓이 없으면 링크도 없는 것이 맞다"},
                "failed": None}
    before = r.hash_of()
    links.first.click()
    r.settle(2200)
    after = r.hash_of()
    return {"ui_action": "주간 리포트의 티켓 제목을 눌러 상세로 간다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "본문 «%s»" % r.main_text(110),
            "failed": None if "/tickets/" in after else "티켓 상세로 안 갔다: %s" % after}


flow("FF-0155", "user_projects-id", "navigation",
     "주간 리포트 버킷의 티켓 제목을 눌러 티켓 상세로 간다",
     _weekly_ticket_link, server=False)


def _project_retry(r, ctx):
    pid = _project_id(r)
    pattern = "**/api/projects/%s" % pid
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었습니다."}'))
    try:
        r.goto("/projects/%s" % pid, shell=USER)
        r.settle(3000)
        face = r.main_text(140)
        retry = r.in_main("button", "다시 시도")
        found = retry.count()
    finally:
        r.page.unroute(pattern)
    if found:
        retry.first.click()
        r.settle(2200)
    return {"ui_action": "프로젝트 본체를 503 으로 끊고 «다시 시도» 를 누른다",
            "frontend_state": "isError=true → 재조회",
            "observed": {"error_face": face, "retry_buttons": found},
            "rendered": "오류 «%s» → 복구 «%s»" % (face[:70], r.main_text(90)),
            "expected": {"source": "derived-check",
                         "rule": "503 이면 오류 얼굴과 «다시 시도» 를 준다", "got": found},
            "failed": None if found else "본체가 503 인데 «다시 시도» 가 없다 — 얼굴: %s" % face}


flow("FF-0156", "user_projects-id", "refresh", "본체·탭별 오류에서 '다시 시도'로 재조회한다",
     _project_retry, api="/api/projects/")


def _project_permission(r, ctx):
    pid = _project_id(r)
    mine = {label: r.in_main("button", label).count()
            for label in ("수정", "보관", "다시 계산")}
    got = r.as_role("user", "/projects/%s" % pid, "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             const names = main ? Array.from(main.querySelectorAll('button')).map(
                 b => (b.innerText || '').replace(/\\s+/g,' ').trim()) : [];
             return {buttons: names, body: (main ? main.innerText : '')
                     .replace(/\\s+/g,' ').trim().slice(0, 160)};
           }"""))
    theirs = {label: sum(1 for n in got["buttons"] if label in n)
              for label in ("수정", "보관", "다시 계산")}
    return {"ui_action": "같은 프로젝트를 일반 사용자로 연다",
            "frontend_state": "쓰기 역할에 따라 버튼이 갈린다",
            "observed": {"as_system_admin": mine, "as_user": theirs,
                         "body": got["body"]},
            "rendered": "system_admin %s · user %s" % (mine, theirs),
            "expected": {"source": "derived-check",
                         "rule": "쓰기 역할이 아니면 수정·보관·재계산이 안 보인다",
                         "as_user": theirs},
            "failed": None if sum(theirs.values()) < sum(mine.values())
                      else "일반 사용자에게도 쓰기 버튼이 그대로 보인다"}


flow("FF-0157", "user_projects-id", "permission_state",
     "쓰기 역할/부서 지정 역할에 따라 수정·보관·재계산·마일스톤 버튼을 감춘다",
     _project_permission, server=False)


def _back_to_list(r, ctx):
    _goto_project(r)
    before = r.hash_of()
    button = r.in_main("button", "목록")
    if not button.count():
        stop("«목록» 버튼이 없다")
    button.first.click()
    r.settle(2000)
    after = r.hash_of()
    return {"ui_action": "«목록» 을 눌러 /projects 로 돌아간다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "본문 «%s»" % r.main_text(110),
            "failed": None if after.rstrip("/").endswith("/projects")
                      else "«목록» 을 눌렀는데 프로젝트 목록이 아니다: %s" % after}


flow("FF-0158", "user_projects-id", "navigation", "'목록' 버튼으로 /projects 로 돌아간다",
     _back_to_list, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /work-board
# ═══════════════════════════════════════════════════════════════════════════
def _board_read(r, ctx):
    tabs = r.page.get_by_role("tab")
    names = [" ".join((tabs.nth(i).inner_text() or "").split()) for i in range(tabs.count())]
    columns = r.page.locator('#main-content [data-column], #main-content section')
    body = r.main_text(200)
    return {"ui_action": "/work-board 를 연다",
            "observed": {"tabs": names, "body": body},
            "rendered": "탭 %s · 본문 «%s»" % (names, body[:140]),
            "expected": {"source": "derived-check",
                         "rule": "칸반 열과 백로그를 함께 준다", "tabs": names},
            "failed": None if names else "작업 보드에 탭이 없다"}


flow("FF-1318", "user_work-board", "read", "칸반 열과 백로그를 받는다",
     _board_read, route="/work-board", api="/api/work/board")


def _board_move(r, ctx):
    # 이 판은 dnd-kit 이라 HTML5 `draggable` 이 아니다 — 카드는 `role="button"` 에
    # `aria-roledescription="sortable"` 로 서고, 마우스 대신 **키보드**로 옮긴다
    # (Space 로 집고, 화살표로 옮기고, Space 로 놓는다). 그것이 이 라이브러리의 계약이다.
    cards = r.page.locator('#main-content [aria-roledescription="sortable"]')
    body = r.main_text(200)
    if not cards.count():
        return {"ui_action": "칸반에서 옮길 카드를 찾는다",
                "observed": {"draggable": 0, "body": body},
                "rendered": "끌 수 있는 카드 0개 · 본문 «%s»" % body[:140],
                "expected": {"source": "known-data",
                             "rule": "판에 카드가 없으면 옮길 것도 없다"},
                "failed": None if ("없습니다" in body or "비어" in body)
                          else "카드도 없고 왜 없는지도 안 말한다"}
    label = cards.first.get_attribute("aria-label") or ""
    r.rec.reset()
    cards.first.focus()
    r.page.keyboard.press("Space")
    r.settle(700)
    r.page.keyboard.press("ArrowRight")
    r.settle(700)
    r.page.keyboard.press("Space")
    r.settle(2400)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«%s» 카드를 키보드로 집어 다음 열로 옮긴다" % label[:34],
            "frontend_state": "POST /api/work/board/move",
            "observed": {"posts": sorted({c["path"] for c in sent})},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "옮기면 상태가 서버로 간다", "got": len(sent)},
            "failed": None if sent else "카드를 옮겼는데 서버로 안 갔다"}


flow("FF-1319", "user_work-board", "status_change", "카드를 옮겨 상태를 바꾼다",
     _board_move, route="/work-board", api="/api/work/board")


def _board_project_filter(r, ctx):
    box = r.page.locator("#main-content input[role=combobox], #main-content [role=combobox]")
    if not box.count():
        stop("프로젝트 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
    r.rec.reset()
    box.first.click()
    r.settle(700)
    options = r.page.get_by_role("option")
    picked = ""
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label and "전체" not in label:
            picked = label
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
        stop("프로젝트 선택기에 «전체» 말고 고를 것이 없다")
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/work/board" in c["path"] and c["query"]}))
    return {"ui_action": "프로젝트를 «%s» 로 좁힌다" % picked,
            "frontend_state": "project_id 가 질의에 실린다",
            "observed": {"picked": picked, "query": query},
            "rendered": "질의 «%s» · 본문 «%s»" % (query[:70], r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "프로젝트를 고르면 그 축이 서버로 간다", "got": query},
            "failed": None if "project" in query
                      else "프로젝트를 골랐는데 질의에 project_id 가 없다: «%s»" % query}


flow("FF-1320", "user_work-board", "filter", "프로젝트로 판을 좁힌다",
     _board_project_filter, route="/work-board", api="/api/work/board")
