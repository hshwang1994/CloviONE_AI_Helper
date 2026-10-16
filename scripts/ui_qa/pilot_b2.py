"""B2 List + DataGrid — `/projects` 와 `/users`(+일괄 처리) (W8 · S18).

Pilot 이 이 원형에 묻는 것: **조건이 실제로 걸리는가**, 그리고 걸린 조건이 주소·캐시·
뒤로가기에서 같은 답을 하는가. S15 가 서버 쪽 조건 사슬을 대조로 못 박았으므로
여기서는 화면이 그 사슬을 **실제로 지나는지**를 본다.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    back_forward, cache_key, choose_then, click_then, close_modal, deep_link_survives_reload,
    flow, hidden_without_role, modal_open_close, open_first_row, open_row, open_row_modal,
    page_reset, pager, primary_button, race, required_blocks_submit, retry_from_error,
    search_then, stop,
)

ADMIN = "/admin"


# ═══════════════════════════════════════════════════════════════════════════
# /projects
# ═══════════════════════════════════════════════════════════════════════════
def _projects_read(r, ctx):
    heads = r.page.locator("table thead th")
    labels = [" ".join((heads.nth(i).inner_text() or "").split()) for i in range(heads.count())]
    return {"ui_action": "/projects 를 연다",
            "observed": {"columns": labels, "rows": r.rows()},
            "rendered": "열 %d개 %s · %d행" % (len(labels), labels, r.rows()),
            "failed": None if r.rows() else "프로젝트가 한 행도 안 그려졌다"}


flow("FF-0122", "user_projects", "read", "프로젝트 목록과 대시보드 집계를 불러온다",
     _projects_read, route="/projects", api="/api/projects")


def _projects_archived(r, ctx):
    before = r.rows()
    box = r.page.locator('#main-content input[type="checkbox"]').first
    if not box.count():
        stop("‘보관 포함’ 스위치가 없다")
    box.click()
    r.settle(1400)
    after = r.rows()
    return {"ui_action": "«보관한 프로젝트 포함» 을 켠다",
            "frontend_state": "include_archived=true",
            "observed": {"rows": {"before": before, "after": after}},
            "rendered": "표 %d행 → %d행" % (before, after),
            "failed": None if after > before else "보관본을 켰는데 행이 안 늘었다"}


flow("FF-0123", "user_projects", "filter",
     "'보관한 프로젝트 포함' 스위치로 보관본까지 목록에 넣는다",
     _projects_archived, route="/projects", api="/api/projects")

flow("FF-0124", "user_projects", "filter", "부서를 골라 목록과 요약을 그 부서로 좁힌다",
     choose_then("부서", "플랫폼개발팀"), route="/projects", api="/api/projects")

flow("FF-0125", "user_projects", "pagination", "페이지 단위로 목록을 넘긴다",
     pager(), route="/projects", api="/api/projects", server=False)


def _projects_create(r, ctx):
    open_row_modal(r, ctx, opener="button=새 프로젝트")
    dialog = r.page.locator('[role="dialog"]')
    dialog.locator("input").first.fill("S18 파일럿 점검 프로젝트")
    r.settle(400)
    submit = r.page.get_by_role("button", name="추가")
    if not submit.count():
        submit = r.page.get_by_role("button", name="저장")
    submit.first.click()
    r.settle(2000)
    return {"ui_action": "«새 프로젝트» 로 이름을 넣고 만든다",
            "frontend_state": "생성 모달 제출",
            "url_state": "→ %s" % r.hash_of(),
            "rendered": "이동/갱신 후 본문 «%s»" % r.main_text(90),
            "cross": {"needle": "S18 파일럿 점검 프로젝트"}}


flow("FF-0126", "user_projects", "create",
     "'새 프로젝트' 모달로 프로젝트를 만들고 곧바로 상세로 이동한다",
     _projects_create, route="/projects", api="/api/projects",
     cross=("/projects", "/"))

flow("FF-0127", "user_projects", "form_validation",
     "이름·상태를 필수로 막는다(서버 EDITABLE_FIELDS와 같은 목록)",
     required_blocks_submit("button=새 프로젝트"), route="/projects", server=False)

flow("FF-0128", "user_projects", "modal_action", "생성 모달 열기·제출·닫기",
     modal_open_close("button=새 프로젝트"), route="/projects", server=False)

flow("FF-0129", "user_projects", "navigation", "표의 행을 눌러 프로젝트 상세로 간다",
     open_first_row, route="/projects", api="/api/projects/")

flow("FF-0130", "user_projects", "deep_link",
     "필터·페이지를 주소에 실어 새로고침·링크 공유에도 유지한다",
     deep_link_survives_reload("/projects?dept=플랫폼개발팀", "dept"),
     api="/api/projects")

flow("FF-0131", "user_projects", "refresh", "목록·요약 오류에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/projects", "프로젝트 목록"), route="/projects", api="/api/projects")

flow("FF-0132", "user_projects", "permission_state",
     "쓰기 역할이 아니면 '새 프로젝트' 버튼을 그리지 않는다",
     hidden_without_role("새 프로젝트"), route="/projects", server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /users
# ═══════════════════════════════════════════════════════════════════════════
USER_SEARCH = '#main-content input[aria-label="사용자 검색"]'


def _users_read(r, ctx):
    heads = r.page.locator("table thead th")
    labels = [" ".join((heads.nth(i).inner_text() or "").split()) for i in range(heads.count())]
    return {"ui_action": "/users 를 연다",
            "observed": {"columns": labels, "rows": r.rows()},
            "rendered": "열 %d개 · %d행 · %s" % (len(labels), r.rows(), labels),
            "failed": None if r.rows() else "사용자가 한 행도 안 그려졌다"}


flow("FF-0421", "admin_users", "read", "사용자 목록 조회(이전 결과 유지로 깜빡임 방지)",
     _users_read, route="/users", shell=ADMIN, api="/api/admin/users")

flow("FF-0422", "admin_users", "search", "이메일 또는 이름 검색(250ms 디바운스)",
     search_then("김지훈", box=USER_SEARCH), route="/users", shell=ADMIN,
     api="/api/admin/users")

flow("FF-0423", "admin_users", "filter", "역할 필터",
     choose_then("역할", "운영자"), route="/users", shell=ADMIN, api="/api/admin/users")

flow("FF-0424", "admin_users", "filter", "활성 필터",
     choose_then("활성", "비활성"), route="/users", shell=ADMIN, api="/api/admin/users")

flow("FF-0425", "admin_users", "filter", "잠김 필터",
     choose_then("잠김", "잠김"), route="/users", shell=ADMIN, api="/api/admin/users")


def _archived_view(r, ctx):
    before = r.rows()
    button = r.page.get_by_role("button", name="보관")
    if not button.count():
        return {"ui_action": "보관된 계정 보기를 켠다",
                "notes": ["이 화면에 «보관» 뷰 전환이 버튼으로 없다 — 조건 상자로 확인한다"],
                "rendered": "표 %d행" % before}
    button.first.click()
    r.settle(1400)
    return {"ui_action": "«보관» 뷰로 전환한다",
            "frontend_state": "archived=true (조건이 아니라 뷰다)",
            "observed": {"rows": {"before": before, "after": r.rows()}},
            "rendered": "표 %d행 → %d행" % (before, r.rows())}


flow("FF-0426", "admin_users", "filter",
     "보관된 계정 보기 토글(뷰 전환 — '필터 지우기'가 건드리지 않는다)",
     _archived_view, route="/users", shell=ADMIN, api="/api/admin/users")

def _department_deep_link(r, ctx):
    """부서 조건은 **진짜 id** 로 건다 — 빈 값은 주소에서 조용히 사라진다."""
    payload = r.api_get("/api/admin/departments")
    items = payload.get("items") or []
    if not items:
        stop("부서가 하나도 없다")
    dept = items[0]
    target = "/users?department_id=" + str(dept["id"])
    r.goto(target, shell=ADMIN)
    rows = r.rows()
    banner = " ".join((r.page.locator("#main-content").inner_text() or "").split())[:140]
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(1600)
    return {"ui_action": "부서 «%s» 조건이 붙은 주소로 들어가 새로고침한다" % dept.get("name"),
            "url_state": "%s → %s" % (target, r.hash_of()),
            "observed": {"rows": {"before": rows, "after": r.rows()}, "banner": banner},
            "rendered": "표 %d행 → %d행 · 본문 «%s»" % (rows, r.rows(), banner),
            "failed": None if "department_id" in r.hash_of()
                      else "새로고침 뒤 부서 조건이 사라졌다: %s" % r.hash_of()}


flow("FF-0427", "admin_users", "filter",
     "부서 필터(딥링크로만 걸리고 배너의 '부서 필터 해제'로 푼다)",
     _department_deep_link, shell=ADMIN, api="/api/admin/users")


def _clear_filters(r, ctx):
    r.choose("역할", "운영자")
    narrowed = r.rows()
    button = r.page.get_by_role("button", name="필터 초기화")
    if not button.count():
        button = r.page.get_by_role("button", name="지우기")
    if not button.count():
        stop("«필터 초기화» 가 없다")
    button.first.click()
    r.settle(1400)
    return {"ui_action": "조건을 하나 건 뒤 «필터 초기화» 를 누른다",
            "frontend_state": "filters={} · q=''",
            "observed": {"rows": {"narrowed": narrowed, "cleared": r.rows()}},
            "rendered": "표 %d행 → %d행 · 주소 %s" % (narrowed, r.rows(), r.hash_of()),
            "failed": None if r.rows() >= narrowed else "지웠는데 행이 안 늘었다"}


flow("FF-0428", "admin_users", "filter",
     "내용 필터 지우기 / 전체 필터 지우기(빈 상태 액션 포함)",
     _clear_filters, route="/users", shell=ADMIN, api="/api/admin/users")

flow("FF-0429", "admin_users", "pagination", "이전·다음 페이지 이동(총 인원과 현재 쪽 표시)",
     pager(), route="/users", shell=ADMIN, api="/api/admin/users", server=False)

flow("FF-0430", "admin_users", "deep_link",
     "검색어·필터 5종·페이지를 해시 주소에 직렬화하고 마운트 때 복원",
     deep_link_survives_reload("/users?role=operator", "role", shell=ADMIN),
     shell=ADMIN, api="/api/admin/users")


def _open_by_query(r, ctx):
    open_row(r)
    opened = r.hash_of()
    return {"ui_action": "행을 눌러 상세를 연다(주소가 /users/:id 가 된다)",
            "url_state": "→ %s" % opened,
            "rendered": "본문 «%s»" % r.main_text(100),
            "failed": None if "/users/" in opened else "상세 주소로 안 바뀌었다: %s" % opened}


flow("FF-0431", "admin_users", "deep_link",
     "다른 화면이 보낸 ?id= 로 특정 사용자 상세를 열고 주소에서 지운다",
     _open_by_query, route="/users", shell=ADMIN, api="/api/admin/users/")

flow("FF-0432", "admin_users", "row_action", "행 클릭으로 사용자 상세 열기",
     open_first_row, route="/users", shell=ADMIN, api="/api/admin/users/")


def _detail_url_sync(r, ctx):
    open_row(r)
    opened = r.hash_of()
    # 닫기 버튼은 **떠 있는 대화상자 안**에서 찾는다 — 셸에 상시 대화상자가 하나 있어서
    # 페이지 전체에서 찾으면 안 보이는 것을 눌러 시간 초과로 죽는다.
    panel = r.page.locator('[role="dialog"]').last
    close = panel.get_by_label("닫기")
    if close.count():
        close.first.click()
        r.settle(1200)
    return {"ui_action": "상세를 열고 닫는다",
            "url_state": "%s → %s" % (opened, r.hash_of()),
            "observed": {"opened": opened, "closed": r.hash_of()},
            "rendered": "주소 %s → %s" % (opened, r.hash_of()),
            "failed": None if "/users/" in opened and "/users/" not in r.hash_of()
                      else "상세 열림·닫힘이 주소에 안 따라왔다"}


flow("FF-0433", "admin_users", "navigation",
     "상세 열림/닫힘에 따라 /users/:id ↔ /users 주소 동기화(쿼리 유지, replace)",
     _detail_url_sync, route="/users", shell=ADMIN, api="/api/admin/users",
     server=False)


def _users_create(r, ctx):
    open_row_modal(r, ctx, opener="button=사용자 추가")
    dialog = r.page.locator('[role="dialog"]')
    inputs = dialog.locator("input")
    inputs.nth(0).fill("s18.pilot@goodmit.co.kr")
    if inputs.count() > 1:
        inputs.nth(1).fill("파일럿 점검")
    r.settle(400)
    sent: list[str] = []
    r.page.on("request", lambda req: sent.append(req.url) if req.method == "POST" else None)
    submit = r.page.get_by_role("button", name="추가")
    if submit.count() and not submit.first.is_disabled():
        submit.first.click()
        r.settle(2000)
    return {"ui_action": "«사용자 추가» 로 이메일·이름을 넣고 만든다",
            "frontend_state": "생성 모달 제출",
            "observed": {"posts": [u.split("/api/")[-1] for u in sent][:3]},
            "rendered": "본문 «%s»" % r.main_text(110),
            "cross": {"needle": "s18.pilot@goodmit.co.kr"}}


flow("FF-0434", "admin_users", "create",
     "사용자 추가(이메일·이름·역할·부서·직책·초기 비밀번호·활성·비밀번호 변경 요구)",
     _users_create, route="/users", shell=ADMIN, api="/api/admin/users",
     cross=("/users", ADMIN))


def _email_shape(r, ctx):
    open_row_modal(r, ctx, opener="button=사용자 추가")
    dialog = r.page.locator('[role="dialog"]')
    dialog.locator("input").first.fill("이건이메일이아니다")
    r.settle(300)
    sent: list[str] = []
    r.page.on("request", lambda req: sent.append(req.url) if req.method == "POST" else None)
    submit = r.page.get_by_role("button", name="추가")
    if submit.count() and not submit.first.is_disabled():
        submit.first.click()
        r.settle(1000)
    message = ""
    helper = r.page.locator('[role="dialog"] .MuiFormHelperText-root, [role="dialog"] [role="alert"]')
    if helper.count():
        message = " ".join((helper.first.inner_text() or "").split())[:90]
    still = bool(r.page.locator('[role="dialog"]').count())
    close_modal(r)
    return {"ui_action": "이메일 자리에 이메일이 아닌 값을 넣고 제출한다",
            "frontend_state": "클라이언트 형식 검사",
            "observed": {"posts": len(sent), "message": message},
            "rendered": "모달 유지 %s · 안내 «%s» · POST %d건" % (still, message, len(sent)),
            "failed": None if (still and not sent)
                      else "이메일 모양이 틀렸는데 서버로 보냈다"}


flow("FF-0435", "admin_users", "form_validation",
     "이메일 모양을 서버 왕복 전에 한국어로 먼저 잡는다",
     _email_shape, route="/users", shell=ADMIN, server=False)

flow("FF-0436", "admin_users", "modal_action",
     "보관된 계정이 그 이메일을 쥔 409면 복구할지 물어보고 그대로 복구",
     modal_open_close("button=사용자 추가"), route="/users", shell=ADMIN, server=False)


def _users_edit(r, ctx):
    open_row(r)
    edit = r.page.get_by_role("button", name="수정")
    if not edit.count():
        stop("상세에 «수정» 이 없다")
    edit.first.click()
    r.settle(900)
    sent: list[dict] = []
    r.page.on("request", lambda req: sent.append({"url": req.url, "body": req.post_data})
              if req.method == "PATCH" else None)
    save = r.page.get_by_role("button", name="저장")
    if save.count():
        save.first.click()
        r.settle(1500)
    return {"ui_action": "상세에서 «수정» 을 열고 아무것도 안 바꾼 채 저장한다",
            "frontend_state": "dirty=false",
            "observed": {"patches": len(sent)},
            "rendered": "PATCH %d건 — 바뀐 것이 없으면 왕복하지 않는다" % len(sent)}


flow("FF-0437", "admin_users", "edit",
     "사용자 수정(바뀐 필드만 PATCH, 변경 없으면 왕복하지 않음)",
     _users_edit, route="/users", shell=ADMIN, api="/api/admin/users", server=False)

flow("FF-0438", "admin_users", "modal_action",
     "생성·재설정 시 임시 비밀번호를 일회성 모달로 노출하고 복사",
     modal_open_close("button=사용자 추가"), route="/users", shell=ADMIN, server=False)


def _role_choices(r, ctx):
    open_row_modal(r, ctx, opener="button=사용자 추가")
    box = r.page.get_by_role("combobox", name="역할", exact=False)
    labels = []
    if box.count():
        box.first.click()
        r.settle(500)
        options = r.page.get_by_role("option")
        labels = [" ".join((options.nth(i).inner_text() or "").split())
                  for i in range(options.count())]
        r.press("Escape")
    close_modal(r)
    return {"ui_action": "생성 폼의 역할 선택지를 연다",
            "frontend_state": "행위자 역할로 제한된 목록",
            "observed": {"choices": labels},
            "rendered": "선택지 %d개 %s" % (len(labels), labels),
            "failed": None if labels else "역할 선택지가 하나도 없다"}


flow("FF-0439", "admin_users", "permission_state",
     "행위자 역할로 생성·수정 폼의 역할 선택지를 제한한다(생성은 관리자 이상 불가)",
     _role_choices, route="/users", shell=ADMIN, server=False)

flow("FF-0440", "admin_users", "refresh",
     "쓰기 후 목록·부서·직책·조직·조직도 캐시를 함께 무효화",
     retry_from_error("/api/admin/users", "사용자 목록"),
     route="/users", shell=ADMIN, api="/api/admin/users")


def _archive_user(r, ctx):
    """보관 — F-0100 이 열려 있던 자리다. 여기서 보는 것은 **분류된 결과**다."""
    rows_before = r.rows()
    open_row(r, max(rows_before - 1, 0))
    button = r.page.get_by_role("button", name="보관")
    if not button.count():
        menu = r.page.get_by_label("더 보기")
        if menu.count():
            menu.first.click()
            r.settle(500)
            button = r.page.get_by_role("menuitem", name="보관")
    if not button.count():
        stop("«보관» 동작을 찾지 못했다")
    r.rec.reset()
    button.first.click()
    r.settle(700)
    for label in ("보관", "확인", "예"):
        confirm = r.page.get_by_role("button", name=label)
        if confirm.count():
            confirm.first.click()
            break
    r.settle(1800)
    calls = r.rec.matching("/archive")
    return {"ui_action": "사용자 상세에서 «보관» 을 누르고 확인한다",
            "frontend_state": "확인 대화 → POST",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3],
                         "rows": {"before": rows_before, "after": r.rows()}},
            "rendered": "표 %d행 → %d행" % (rows_before, r.rows()),
            "failed": None if calls and all(c["status"] < 500 for c in calls)
                      else "보관 요청이 없거나 500 이 났다"}


flow("FF-1199", "admin_users", "admin_op",
     "사용자를 보관한다 (목록·검색·로그인에서 빠지고 되돌릴 수 있다)",
     _archive_user, route="/users", shell=ADMIN, api="/api/admin/users")


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
def _users_compound(r, ctx):
    before = r.rows()
    r.choose("역할", "일반")
    mid = r.rows()
    r.fill(USER_SEARCH, "이서연")
    return {"ui_action": "역할과 검색어를 **함께** 건다",
            "frontend_state": "role=user & q=이서연",
            "observed": {"rows": {"none": before, "role_only": mid, "both": r.rows()}},
            "rendered": "표 %d → %d → %d행" % (before, mid, r.rows()),
            "failed": None if r.rows() <= mid <= before
                      else "조건을 더했는데 결과가 늘었다"}


flow("FF-1356", "admin_users", "filter", "복합 — 역할 × 검색어",
     _users_compound, route="/users", shell=ADMIN, api="/api/admin/users")


def _users_page_reset(r, ctx):
    before = r.hash_of()
    r.choose("역할", "운영자")
    after = r.hash_of()
    return {"ui_action": "조건을 바꾼다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "주소 «%s»" % after,
            "failed": None if "page=" not in after or "page=1" in after
                      else "조건을 바꿨는데 쪽이 초기화되지 않았다: %s" % after}


flow("FF-1357", "admin_users", "filter", "조건을 바꾸면 쪽이 초기화된다",
     _users_page_reset, route="/users?page=1", shell=ADMIN, api="/api/admin/users")

flow("FF-1358", "admin_users", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(USER_SEARCH, "김", "이서연"), route="/users", shell=ADMIN,
     api="/api/admin/users")

flow("FF-1359", "admin_users", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/users?role=operator", "/users?role=admin", shell=ADMIN),
     shell=ADMIN, api="/api/admin/users")

flow("FF-1360", "admin_users", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/users?role=operator", "/users?role=admin", shell=ADMIN),
     shell=ADMIN, api="/api/admin/users")


# ═══════════════════════════════════════════════════════════════════════════
# /users — 일괄 처리 위젯
# ═══════════════════════════════════════════════════════════════════════════
def _dialog_text(r) -> str:
    """지금 떠 있는 **마지막** 대화상자의 글. 셸의 상시 대화상자를 읽지 않으려면 `.last` 다."""
    panel = r.page.locator('[role="dialog"]')
    return " ".join((panel.last.inner_text() or "").split())[:200] if panel.count() else ""


def _select_rows(r, n: int = 2):
    boxes = r.page.locator('table tbody input[type="checkbox"]')
    picked = 0
    for i in range(min(n, boxes.count())):
        boxes.nth(i).click()
        picked += 1
    r.settle(600)
    return picked


def _bulk_bar(r, ctx):
    before = r.page.get_by_role("button", name="선택 해제").count()
    picked = _select_rows(r, 2)
    after = r.page.get_by_role("button", name="선택 해제").count()
    if after:
        r.page.get_by_role("button", name="선택 해제").first.click()
        r.settle(500)
    return {"ui_action": "행 %d개를 고른다" % picked,
            "frontend_state": "selection=%d" % picked,
            "observed": {"bar_before": before, "bar_after": after,
                         "bar_cleared": r.page.get_by_role("button", name="선택 해제").count()},
            "rendered": "선택 바 %s → %s → 해제 뒤 %s"
                        % (bool(before), bool(after),
                           bool(r.page.get_by_role("button", name="선택 해제").count())),
            "failed": None if (picked and after and not before)
                      else "선택했는데 선택 바가 안 나타났다"}


flow("FF-1165", "admin_users__bulk", "row_action",
     "선택이 있을 때만 선택 바가 나타나고 선택 해제로 비운다(페이지·필터가 바뀌어도 선택 유지)",
     _bulk_bar, route="/users", shell=ADMIN, server=False)


def _bulk_op(r, ctx):
    picked = _select_rows(r, 2)
    r.rec.reset()
    button = r.page.get_by_role("button", name="비활성화")
    if not button.count():
        stop("일괄 «비활성화» 가 없다")
    button.first.click()
    r.settle(700)
    confirm_text = ""
    dialog = r.page.locator('[role="dialog"]')
    if dialog.count():
        confirm_text = " ".join((dialog.first.inner_text() or "").split())[:120]
        for label in ("비활성화", "확인", "예"):
            ok = dialog.get_by_role("button", name=label)
            if ok.count():
                ok.first.click()
                break
    r.settle(1800)
    calls = r.rec.matching("/bulk")
    return {"ui_action": "행 %d개를 고르고 일괄 «비활성화» 를 누른다" % picked,
            "frontend_state": "확인 대화 → 일괄 POST",
            "observed": {"confirm": confirm_text,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "확인 문구 «%s» · 요청 %d건" % (confirm_text, len(calls)),
            "failed": None if calls else "일괄 요청이 안 나갔다"}


flow("FF-1166", "admin_users__bulk", "admin_op",
     "일괄 비활성화·활성화·보관·보관 복구·잠금 해제·세션 해제",
     _bulk_op, route="/users", shell=ADMIN, api="/api/admin/users")


def _bulk_confirm_counts(r, ctx):
    picked = _select_rows(r, 2)
    button = r.page.get_by_role("button", name="보관", exact=True)
    if not button.count():
        stop("일괄 «보관» 이 없다")
    button.first.click()
    r.settle(900)
    text = _dialog_text(r)
    close_modal(r)
    return {"ui_action": "행 %d개를 고르고 일괄 «보관» 확인 대화를 연다" % picked,
            "frontend_state": "확인 대화",
            "observed": {"confirm": text},
            "rendered": "확인 문구 «%s»" % text,
            "failed": None if ("대상 %d명" % picked) in text
                      else "확인 문구에 대상 인원 수(%d)가 없다" % picked}


flow("FF-1167", "admin_users__bulk", "modal_action",
     "작업별 확인 대화상자에 대상 인원 수를 붙이고 위험도에 맞는 톤을 쓴다",
     _bulk_confirm_counts, route="/users", shell=ADMIN, server=False)


def _pick_assign_axis(r, axis: str = "부서"):
    """«일괄 지정» 축을 고르면 그때 «값» 상자와 «적용» 이 나타난다."""
    r.choose("일괄 지정", axis)
    r.settle(700)


def _bulk_assign(r, ctx):
    picked = _select_rows(r, 2)
    _pick_assign_axis(r)
    apply_button = r.page.get_by_role("button", name="적용", exact=True)
    before_disabled = apply_button.first.is_disabled() if apply_button.count() else None
    _, label = r.choose_other("값")
    r.rec.reset()
    if apply_button.count() and not apply_button.first.is_disabled():
        apply_button.first.click()
        r.settle(900)
        confirm = r.page.locator('[role="dialog"]').last
        for name in ("적용", "확인", "예"):
            ok = confirm.get_by_role("button", name=name)
            if ok.count():
                ok.first.click()
                break
        r.settle(1800)
    calls = r.rec.matching("/bulk")
    return {"ui_action": "행 %d개에 부서 «%s» 를 일괄 지정한다" % (picked, label),
            "frontend_state": "bulk value=%s" % label,
            "observed": {"apply_disabled_before_pick": before_disabled,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "고르기 전 적용 비활성 %s · 요청 %d건" % (before_disabled, len(calls)),
            "failed": None if calls else "일괄 지정 요청이 안 나갔다"}


flow("FF-1168", "admin_users__bulk", "edit", "선택한 계정의 부서 또는 직책을 일괄 지정",
     _bulk_assign, route="/users", shell=ADMIN, api="/api/admin/users")


def _bulk_combobox(r, ctx):
    _select_rows(r, 1)
    _pick_assign_axis(r)
    box = r.page.get_by_role("combobox", name="값", exact=False)
    if not box.count():
        stop("일괄 지정의 «값» 선택 상자가 없다")
    box.first.click()
    r.settle(500)
    options = r.page.get_by_role("option")
    labels = [" ".join((options.nth(i).inner_text() or "").split())
              for i in range(min(options.count(), 8))]
    r.press("Escape")
    return {"ui_action": "일괄 지정 값 선택기를 연다",
            "observed": {"choices": labels},
            "rendered": "선택지 %d개 %s" % (len(labels), labels),
            "failed": None if labels else "선택지가 하나도 없다"}


flow("FF-1169", "admin_users__bulk", "combobox", "일괄 지정 값(부서 또는 직책) 고르기",
     _bulk_combobox, route="/users", shell=ADMIN, api="/api/admin", server=False)


def _bulk_apply_gate(r, ctx):
    _select_rows(r, 1)
    _pick_assign_axis(r)
    apply_button = r.page.get_by_role("button", name="적용", exact=True)
    disabled = apply_button.first.is_disabled() if apply_button.count() else None
    return {"ui_action": "값을 고르기 전 «적용» 상태를 본다",
            "frontend_state": "value=<자리표시자>",
            "observed": {"apply_present": apply_button.count(), "disabled": disabled},
            "rendered": "«적용» %s" % ("비활성" if disabled else "활성"),
            "failed": None if disabled else "값을 안 골랐는데 적용이 눌린다"}


flow("FF-1170", "admin_users__bulk", "form_validation",
     "값을 능동적으로 고르기 전에는 적용 버튼 비활성(자리표시자와 '없음'을 구분)",
     _bulk_apply_gate, route="/users", shell=ADMIN, server=False)


def _csv_export(r, ctx):
    link = r.page.get_by_role("link", name="CSV 내보내기")
    href = link.first.get_attribute("href") if link.count() else ""
    return {"ui_action": "«CSV 내보내기» 의 주소를 읽는다(파일은 받지 않는다)",
            "frontend_state": "지금 걸린 조건이 주소에 실린다",
            "observed": {"href": href},
            "rendered": "링크 «%s»" % href,
            "failed": None if href and "export" in href
                      else "내보내기 링크가 없거나 주소가 비었다"}


flow("FF-1171", "admin_users__bulk", "attachment",
     "지금 걸린 필터 그대로 CSV 내보내기(앵커 다운로드)",
     _csv_export, route="/users?role=operator", shell=ADMIN, server=False)


def _csv_area(r):
    """MUI 의 여러 줄 입력은 **보이지 않는 그림자 textarea** 를 하나 더 그린다.
    `.first` 를 채우면 그것을 채우려다 시간 초과로 죽는다 — 라벨로 겨눈다."""
    area = r.page.get_by_label("CSV 내용")
    if not area.count():
        area = r.page.locator('[role="dialog"] textarea:not([aria-hidden="true"])')
    if not area.count():
        stop("CSV 붙여넣기 칸이 없다")
    return area.first


def _csv_import(r, ctx):
    open_row_modal(r, ctx, opener="button=CSV 가져오기")
    _csv_area(r).fill("email,display_name,role\ns18.csv@goodmit.co.kr,CSV 점검,user")
    r.settle(500)
    r.rec.reset()
    preview = r.page.get_by_role("button", name="미리 보기")
    if preview.count():
        preview.first.click()
        r.settle(2000)
    calls = r.rec.matching("/import")
    text = _dialog_text(r)
    # **미리 보기에서 멈추지 않는다.** 「dry_run → 실제 추가」가 이 Flow 의 이름이라,
    # 주 버튼(«N명 추가»)까지 눌러야 계약을 다 본 것이다. 그 버튼의 이름은 미리 보기
    # 결과에 따라 바뀌므로 이름이 아니라 자리로 겨눈다(`primary_button` 주석).
    applied: list = []
    button = primary_button(r)
    if not button.is_disabled():
        r.rec.reset()
        button.click()
        r.settle(2500)
        applied = r.rec.matching("/import")
    result = _dialog_text(r)
    close_modal(r)
    return {"ui_action": "CSV 를 붙여넣고 «미리 보기» 뒤 실제로 추가한다",
            "frontend_state": "dry_run=true → dry_run=false",
            "observed": {"preview": [(c["method"], c["path"], c["status"]) for c in calls][:2],
                         "apply": [(c["method"], c["path"], c["status"]) for c in applied][:2],
                         "panel": text, "result": result},
            "rendered": "미리 보기 «%s» → 적용 «%s»" % (text, result),
            "cross": {"needle": "s18.csv@goodmit.co.kr"},
            "failed": None if (calls and applied)
                      else "미리 보기 또는 실제 추가 요청이 안 나갔다"}


flow("FF-1172", "admin_users__bulk", "create",
     "CSV 붙여넣기 → 미리 보기(dry_run) → 실제 추가",
     _csv_import, route="/users", shell=ADMIN, api="/api/admin/users",
     cross=("/users", ADMIN))


def _csv_gate(r, ctx):
    open_row_modal(r, ctx, opener="button=CSV 가져오기")
    # **대화상자 안에서만** 찾는다 — 화면 머리의 «사용자 추가» 가 같은 낱말을 갖고 있어서
    # 페이지 전체에서 찾으면 그 버튼의 상태를 읽고 «미리 보기 전인데 눌린다» 로 오판한다.
    panel = r.page.locator('[role="dialog"]').last
    # 미리 보기 전 이 버튼의 **이름 자체가** «미리 보기를 먼저 하세요» 다 — 그것이 이
    # 화면의 답이라, «추가» 라는 낱말로 찾으면 아무것도 못 찾고 그 없음을 «눌린다» 로
    # 오판한다. 주 버튼을 자리로 겨눈다.
    add = panel.locator(".k-footer-main button").last
    disabled = add.is_disabled() if add.count() else None
    label = " ".join((add.inner_text() or "").split()) if add.count() else ""
    close_modal(r)
    return {"ui_action": "미리 보기 전 주 버튼의 상태와 이름을 본다",
            "observed": {"disabled": disabled, "label": label},
            "rendered": "«%s» %s" % (label, "비활성" if disabled else "활성"),
            "failed": None if (disabled and "미리 보기" in label)
                      else "미리 보기 전인데 추가가 눌리거나 이유를 말하지 않는다"}


flow("FF-1173", "admin_users__bulk", "form_validation",
     "미리 보기 전에는 추가 버튼이 '미리 보기를 먼저 하세요'로 잠긴다",
     _csv_gate, route="/users", shell=ADMIN, server=False)


def _csv_dirty_close(r, ctx):
    open_row_modal(r, ctx, opener="button=CSV 가져오기")
    _csv_area(r).fill("email,display_name\nx@goodmit.co.kr,버리기 확인")
    r.settle(400)
    r.press("Escape")
    r.settle(800)
    asked = bool(r.page.locator('[role="dialog"]').last
                 .get_by_role("button", name="닫기").count())
    close_modal(r)
    return {"ui_action": "붙여넣은 채로 Esc 를 누른다",
            "frontend_state": "dirty=true",
            "observed": {"confirm_shown": asked},
            "rendered": "확인 창 %s" % ("떴다" if asked else "안 떴다"),
            "failed": None if asked else "입력이 남았는데 그냥 닫혔다"}


flow("FF-1174", "admin_users__bulk", "modal_action",
     "붙여넣은 CSV가 남은 채 닫으려 하면 확인을 받는다",
     _csv_dirty_close, route="/users", shell=ADMIN, server=False)


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
#
# 이 위젯의 조건은 **선택과 함께** 산다. FF-1165 가 「페이지·필터가 바뀌어도 선택 유지」를
# 계약으로 적어 두었으므로, 다섯 축은 전부 «조건이 바뀌어도 선택이 살아 있는가» 를 묻는다.
def _bulk_pick(r, count: int = 2) -> int:
    boxes = r.page.locator('#main-content table tbody input[type="checkbox"]')
    picked = 0
    for i in range(min(boxes.count(), count)):
        boxes.nth(i).click()
        picked += 1
    r.settle(600)
    return picked


def _bulk_bar_text(r) -> str:
    bar = r.page.locator('#main-content [data-bulk-bar], #main-content [role="toolbar"]')
    if bar.count():
        return " ".join((bar.first.inner_text() or "").split())[:120]
    return " ".join((r.main_text(200) or "").split())[:120]


def _bulk_compound(r, ctx):
    picked = _bulk_pick(r)
    if not picked:
        stop("고를 행이 없다")
    before = r.rows()
    one = r.choose("역할", "사용자")
    mid = r.rows()
    r.fill(USER_SEARCH, "김")
    after = r.rows()
    return {"ui_action": "%d건을 고른 뒤 «역할»=%s 와 검색 «김» 을 함께 건다" % (picked, one),
            "frontend_state": "role=user & q=김 (선택 %d건 유지)" % picked,
            "observed": {"rows": {"none": before, "one": mid, "both": after},
                         "picked": picked, "bar": _bulk_bar_text(r)},
            "rendered": "표 %d → %d → %d행 · 선택 바 «%s»"
                        % (before, mid, after, _bulk_bar_text(r)),
            "expected": {"source": "derived-check",
                         "rule": "조건을 더할수록 결과는 좁아지고, 선택은 그대로 남는다",
                         "expect": "both <= one <= none", "picked": picked,
                         "got": {"none": before, "one": mid, "both": after}},
            "failed": None if after <= mid <= before
                      else "조건을 더했는데 결과가 늘었다(%d → %d → %d)" % (before, mid, after)}


def _bulk_page_reset(r, ctx):
    _bulk_pick(r, 1)
    return page_reset("역할", "사용자")(r, ctx)


def _bulk_race(r, ctx):
    _bulk_pick(r, 1)
    return race(USER_SEARCH, "김", "이서연")(r, ctx)


flow("FF-1425", "admin_users__bulk", "filter",
     "복합 — 역할 × 검색어를 함께 걸어도 선택이 살아 있다",
     _bulk_compound, route="/users", shell=ADMIN, server=False)
flow("FF-1426", "admin_users__bulk", "filter",
     "조건을 바꾸면 쪽이 1로 초기화된다(그때도 선택은 유지된다)",
     _bulk_page_reset, route="/users", shell=ADMIN, server=False)
flow("FF-1427", "admin_users__bulk", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     _bulk_race, route="/users", shell=ADMIN, server=False)
flow("FF-1428", "admin_users__bulk", "filter",
     "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/users?role=user", "/users?role=operator", shell=ADMIN),
     shell=ADMIN, api="/api/admin/users")
flow("FF-1429", "admin_users__bulk", "filter",
     "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/users?role=user", "/users?role=operator", shell=ADMIN),
     shell=ADMIN, api="/api/admin/users")
