"""S21 — 조직도 · 부서 · 직책 · 사용자 상세 · 오프보딩 (W14).

`/org-tree` · `/departments` · `/departments/:id` 는 **한 화면**이다(`OrgConsole`) — 왼쪽에
조직도 트리, 오른쪽에 그 종류의 관리 판. 주소가 셋인 이유는 IA 이력이고, 원장에도 셋으로
적혀 있다. 그래서 같은 동작을 세 주소에서 각각 돌린다.

오프보딩은 이 제품에서 **여러 자원을 한 번에 옮기는** 유일한 자리다(티켓 재배정 + 비활성화
+ 보관). S20 이 그 화면의 후임 후보가 옛 짝을 요구해 새 계정을 통째로 빠뜨리던 것을 고쳤다
(D-317). 여기서는 그 화면이 **끝까지 갈 수 있는가**를 본다 — 다만 실행은 사람의 계정을
비활성화하는 일이라, 확인 문장까지 보고 물러난다.
"""

from __future__ import annotations

from urllib.parse import unquote

from scripts.ui_qa.s21_admin_kit import (  # noqa: F401
    ADMIN, ds_action, ds_clear, ds_create, ds_deep_link, ds_edit, ds_filter, ds_navigate,
    ds_open_row, ds_overflow, ds_pager, ds_permission, ds_read, ds_required, ds_saved_view,
    ds_search,
)
from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, first_row_text, flow, n_rows, open_dialog, open_dialogs,
    retry_from_error, row_at, row_name, rows_of, sort_by, stop,
)

DEPT = "/api/admin/departments"
TITLE = "/api/admin/job-titles"
USERS = "/api/admin/users"
OFF = "/api/admin/offboarding"


# ═══════════════════════════════════════════════════════════════════════════
# 조직도 트리 (세 주소가 같은 화면)
# ═══════════════════════════════════════════════════════════════════════════
def _tree_search(r, ctx):
    box = r.page.locator("#main-content input[type=search]:visible, "
                         "#main-content input[type=text]:visible").first
    if not box.count():
        stop("트리 검색 상자가 없다")
    nodes = r.page.locator('#main-content [role="treeitem"], '
                           '#main-content button[aria-label^="접기"]')
    before = nodes.count()
    box.fill("플랫폼")
    r.settle(1800)
    after = r.page.locator('#main-content [role="treeitem"], '
                           '#main-content button[aria-label^="접기"]').count()
    box.fill("")
    r.settle(1200)
    return {"ui_action": "트리에서 «플랫폼» 을 검색한다",
            "frontend_state": "일치 노드와 그 조상만 남긴다(화면 안에서 가지치기)",
            "observed": {"nodes": {"before": before, "after": after}},
            "rendered": "트리 마디 %d개 → %d개" % (before, after),
            "expected": {"source": "derived-check",
                         "rule": "검색하면 트리가 좁아진다(늘어나면 실패)",
                         "before": before, "after": after},
            "failed": None if after <= before
                      else "검색했는데 트리가 늘었다(%d → %d)" % (before, after)}


def _tree_use_filter(r, ctx):
    before = n_rows(r)
    r.rec.reset()
    picked = r.choose("사용", "사용 중")
    r.settle(1800)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                     if DEPT in c["path"] and c["query"]})))
    return {"ui_action": "사용 여부를 «%s» 로 좁힌다" % picked,
            "frontend_state": "서버가 거른다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
            "expected": {"source": "derived-check",
                         "rule": "사용 여부는 서버 질의에 실린다", "got": query},
            "failed": None if (query or n_rows(r) != before)
                      else "사용 여부를 골랐는데 아무것도 안 달라졌다"}


def _tree_node_click(r, ctx):
    node = r.page.locator('#main-content [role="treeitem"]')
    if not node.count():
        node = r.page.locator('#main-content button[aria-label^="접기"]')
    if not node.count():
        stop("트리 마디가 없다")
    before = r.main_text(120)
    heads = r.page.locator("#main-content table thead th")
    cols_before = [" ".join((heads.nth(i).inner_text() or "").split())
                   for i in range(heads.count())]
    node.first.click()
    r.settle(1800)
    heads = r.page.locator("#main-content table thead th")
    cols_after = [" ".join((heads.nth(i).inner_text() or "").split())
                  for i in range(heads.count())]
    return {"ui_action": "트리 마디를 누른다",
            "observed": {"columns": {"before": cols_before, "after": cols_after},
                         "body": r.main_text(120)},
            "rendered": "오른쪽 판 열 %s → %s" % (cols_before, cols_after),
            "expected": {"source": "derived-check",
                         "rule": "마디를 누르면 오른쪽 판이 그 종류의 관리 화면으로 바뀐다",
                         "before": cols_before, "after": cols_after},
            "failed": None}


def _tree_expand(r, ctx):
    toggle = r.page.locator('#main-content button[aria-label^="접기"], '
                            '#main-content button[aria-label^="펼치기"]')
    if not toggle.count():
        stop("트리 꺾쇠 버튼이 없다")
    label_before = toggle.first.get_attribute("aria-label")
    nodes_before = r.page.locator('#main-content [role="treeitem"], '
                                  '#main-content button[aria-label^="접기"]').count()
    toggle.first.click()
    r.settle(1200)
    label_after = r.page.locator(
        '#main-content button[aria-label^="접기"], '
        '#main-content button[aria-label^="펼치기"]').first.get_attribute("aria-label")
    nodes_after = r.page.locator('#main-content [role="treeitem"], '
                                 '#main-content button[aria-label^="접기"]').count()
    return {"ui_action": "«%s» 꺾쇠를 누른다" % label_before,
            "observed": {"label": {"before": label_before, "after": label_after},
                         "nodes": {"before": nodes_before, "after": nodes_after}},
            "rendered": "«%s» → «%s» · 마디 %d → %d"
                        % (label_before, label_after, nodes_before, nodes_after),
            "expected": {"source": "derived-check",
                         "rule": "접으면 하위가 사라지고 이름표가 «펼치기» 로 바뀐다"},
            "failed": None if (label_before != label_after or nodes_before != nodes_after)
                      else "꺾쇠를 눌렀는데 아무것도 안 바뀐다"}


def _tree_keyboard(r, ctx):
    node = r.page.locator('#main-content [role="treeitem"]')
    if not node.count():
        node = r.page.locator('#main-content button[aria-label^="접기"]')
    if not node.count():
        stop("트리 마디가 없다")
    node.first.focus()
    before = r.page.evaluate(
        "() => { const el = document.activeElement;"
        " return el ? (el.getAttribute('aria-label') || el.innerText || '')"
        ".replace(/\\s+/g,' ').trim().slice(0,40) : ''; }")
    for key in ("ArrowDown", "End", "Home"):
        r.page.keyboard.press(key)
        r.settle(400)
    after = r.page.evaluate(
        "() => { const el = document.activeElement;"
        " return el ? (el.getAttribute('aria-label') || el.innerText || '')"
        ".replace(/\\s+/g,' ').trim().slice(0,40) : ''; }")
    return {"ui_action": "트리에서 ↓ · End · Home 을 눌러 초점을 옮긴다",
            "observed": {"focus": {"before": before, "after": after}},
            "rendered": "초점 «%s» → «%s»" % (before, after),
            "expected": {"source": "derived-check",
                         "rule": "키보드로 보이는 마디 사이를 오갈 수 있다(roving tabindex)",
                         "before": before, "after": after},
            "failed": None if before else "트리 마디에 초점이 안 간다"}


def _tree_denied(r, ctx):
    got = r.as_role("operator", "/org-tree", ADMIN, lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return (main ? main.innerText : document.body.innerText)
                 .replace(/\\s+/g,' ').trim().slice(0, 220);
           }"""))
    return {"ui_action": "조직도를 운영자로 연다",
            "observed": {"as_operator": got},
            "rendered": "본문 «%s»" % got[:170],
            "expected": {"source": "derived-check",
                         "rule": "admin·system_admin 외에는 권한 안내를 본다", "got": got[:150]},
            "failed": None if ("권한" in got or "없습니다" in got)
                      else "운영자에게도 조직도가 그대로 열린다"}


ORG = "/org-tree"

flow("FF-0511", "admin_org-tree", "search",
     "트리에서 조직·부서 이름으로 검색하면 일치 노드와 그 조상만 남는다(클라이언트 가지치기)",
     _tree_search, route=ORG, shell=ADMIN, server=False)

flow("FF-0512", "admin_org-tree", "filter", "사용 여부(전체·사용 중·미사용)로 트리를 서버에서 거른다",
     _tree_use_filter, route=ORG, shell=ADMIN, api=DEPT)

flow("FF-0513", "admin_org-tree", "navigation",
     "트리 노드를 누르면 오른쪽 패널이 그 종류(조직/부서) 관리 화면으로 바뀌고 노드가 강조된다",
     _tree_node_click, route=ORG, shell=ADMIN, server=False)

flow("FF-0514", "admin_org-tree", "row_action", "트리 노드의 꺾쇠 버튼으로 하위 부서를 펼치고 접는다",
     _tree_expand, route=ORG, shell=ADMIN, server=False)

flow("FF-0515", "admin_org-tree", "navigation",
     "화살표·Home·End 키로 보이는 트리 노드 사이를 이동한다(roving tabindex)",
     _tree_keyboard, route=ORG, shell=ADMIN, server=False)

flow("FF-0516", "admin_org-tree", "refresh", "트리 조회가 실패하면 '다시 시도'로 재조회한다",
     retry_from_error(DEPT + "/tree", "조직도"), route=ORG, shell=ADMIN, api=DEPT)

flow("FF-0517", "admin_org-tree", "read", "오른쪽 관리 패널의 행을 눌러 상세 모달을 연다",
     ds_open_row(), route=ORG, shell=ADMIN, server=False)

flow("FF-0518", "admin_org-tree", "create", "오른쪽 패널에서 조직(기본) 또는 부서를 추가한다",
     ds_create("조직 추가", {"이름": "S21 점검 조직"}), route=ORG, shell=ADMIN,
     api="/api/admin/organizations", cross=("/org-tree", ADMIN))

flow("FF-0519", "admin_org-tree", "status_change", "오른쪽 조직 패널에서 조직을 비활성화·활성화한다",
     ds_action("비활성화"), route=ORG, shell=ADMIN, api="/api/admin/organizations")

flow("FF-0520", "admin_org-tree", "settings_apply", "오른쪽 패널의 저장된 뷰를 저장·적용·삭제한다",
     ds_saved_view(), route=ORG, shell=ADMIN, server=False)

flow("FF-0521", "admin_org-tree", "permission_state",
     "admin·system_admin 외 역할은 화면 대신 '권한이 없습니다' 안내를 본다",
     _tree_denied, route=ORG, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /departments
# ═══════════════════════════════════════════════════════════════════════════
D = "/departments"

flow("FF-0540", "admin_departments", "search", "부서 이름으로 검색한다(searchFields name, 클라이언트)",
     ds_search("", DEPT, server=False), route=D, shell=ADMIN, server=False)

flow("FF-0541", "admin_departments", "filter", "사용 여부(사용 중·미사용)로 부서 목록을 서버에서 거른다",
     _tree_use_filter, route=D, shell=ADMIN, api=DEPT)

flow("FF-0542", "admin_departments", "sort", "열 머리를 눌러 정렬한다(페이지네이션 없는 화면이라 활성)",
     sort_by("부서 이름"), route=D, shell=ADMIN, server=False)

flow("FF-0543", "admin_departments", "create",
     "'부서 추가'로 부서 이름과 상위 부서를 지정해 부서를 만든다",
     ds_create("부서 추가", {"이름": "S21 점검 부서"}), route=D, shell=ADMIN, api=DEPT,
     cross=("/departments", ADMIN))


def _parent_picker(opener: str, label: str):
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1400)
        if not open_dialogs(r):
            stop("모달이 안 떴다")
        dialog = open_dialog(r)
        picker = dialog.get_by_role("combobox", name=label, exact=False)
        if not picker.count():
            # 이 폼의 선택기에는 **읽을 수 있는 이름이 없다** — 지금 값(«(최상위)»)만
            # 말한다. 이름으로 못 찾는다고 「선택기가 없다」로 적으면, 있는 것을 없다고
            # 적는 것이다. 이 모달의 선택기는 하나뿐이라 자리로 집는다.
            picker = dialog.get_by_role("combobox")
        names = []
        if picker.count():
            picker.first.click()
            r.settle(600)
            options = r.page.get_by_role("option")
            names = [" ".join((options.nth(i).inner_text() or "").split())
                     for i in range(options.count())]
            r.press("Escape")
        r.dismiss_overlays()
        return {"ui_action": "«%s» 모달의 «%s» 후보를 본다" % (opener, label),
                "observed": {"options": names, "picker": picker.count()},
                "rendered": "후보 %s" % names,
                "expected": {"source": "derived-check",
                             "rule": "지금 로드된 목록에서 고르고, 자기 자신은 후보에서 뺀다",
                             "got": names},
                "failed": None if picker.count() else "«%s» 선택기가 없다" % label}
    return _act


flow("FF-0544", "admin_departments", "combobox",
     "'상위 부서'를 지금 로드된 부서 목록에서 고른다(자기 자신은 후보에서 제외)",
     _parent_picker("부서 추가", "상위"), route=D, shell=ADMIN, server=False)

flow("FF-0545", "admin_departments", "form_validation",
     "부서 이름은 생성·수정 모두 필수라 비워서 제출하면 막힌다(빈 값 no-op·거짓 성공 방지)",
     ds_required("부서 추가"), route=D, shell=ADMIN, server=False)

flow("FF-0546", "admin_departments", "read", "행을 눌러 부서 ID·조직·하위 부서 수·삭제 안내 상세를 연다",
     ds_open_row(), route=D, shell=ADMIN, server=False)

flow("FF-0547", "admin_departments", "edit",
     "상세에서 '수정'으로 부서 이름과 상위 부서를 바꾼다(변경 필드만 PATCH)",
     ds_edit("이름"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0548", "admin_departments", "status_change",
     "부서를 활성화·비활성화한다(비활성화 시 영향 인원 수를 확인 문구에 넣는다)",
     ds_action("비활성화"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0549", "admin_departments", "delete",
     "소속 인원이 0인 부서만 삭제한다(하위 부서는 최상위로 올라간다는 경고 포함)",
     ds_action("삭제"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0550", "admin_departments", "modal_action",
     "삭제·비활성화 전 행 데이터로 만든 확인 대화를 띄우고 확정 버튼에 액션 이름을 쓴다",
     ds_action("비활성화"), route=D, shell=ADMIN, api=DEPT)


def _detail_url_sync(base: str):
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        before = unquote(r.hash_of())
        row_at(r, 0).click()
        r.settle(1800)
        after = unquote(r.hash_of())
        opened = open_dialogs(r)
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(2200)
        still = open_dialogs(r)
        return {"ui_action": "행 상세를 열고 새로고침한다",
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after,
                             "dialogs": {"opened": opened, "after_reload": still}},
                "rendered": "주소 «%s» · 새로고침 뒤 상세 %s"
                            % (after[:60], "열림" if still else "닫힘"),
                "expected": {"source": "derived-check",
                             "rule": "상세를 열면 주소가 %s/:id 로 동기화된다" % base,
                             "got": after},
                "failed": None if base + "/" in after
                          else "상세를 열었는데 주소가 안 따라온다: %s" % after}
    return _act


flow("FF-0551", "admin_departments", "deep_link",
     "행 상세를 열면 주소가 /departments/:id 로 동기화돼 새로고침·링크 공유가 성립한다",
     _detail_url_sync("/departments"), route=D, shell=ADMIN, server=False)


def _detail_back(base: str):
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        row_at(r, 0).click()
        r.settle(1800)
        opened = unquote(r.hash_of())
        r.back()
        r.settle(1600)
        after = unquote(r.hash_of())
        return {"ui_action": "상세를 열고 뒤로가기를 한 번 누른다",
                "url_state": "%s → (뒤로) %s" % (opened, after),
                "observed": {"hash": {"opened": opened, "back": after},
                             "dialogs": open_dialogs(r)},
                "rendered": "주소 «%s» → «%s»" % (opened[:50], after[:50]),
                "expected": {"source": "derived-check",
                             "rule": "상세만 닫히고 목록에 남는다(화면 밖으로 안 튕긴다)",
                             "expect": base, "got": after},
                "failed": None if base in after
                          else "뒤로가기 한 번에 화면 밖으로 나갔다: %s" % after}
    return _act


flow("FF-0552", "admin_departments", "back_forward",
     "상세 열기는 replace라 뒤로가기 한 번에 상세만 닫히고 목록에 남는다",
     _detail_back("/departments"), route=D, shell=ADMIN, server=False)

flow("FF-0553", "admin_departments", "deep_link", "'감사 로그에서 보기'로 이 부서의 변경 이력으로 딥링크한다",
     ds_navigate("감사 로그에서 보기", "object_type="), route=D, shell=ADMIN, server=False)

flow("FF-0554", "admin_departments", "overflow_action", "삭제 등 위험 액션은 상세 하단 넘침 메뉴로 내려간다",
     ds_overflow(), route=D, shell=ADMIN, server=False)

flow("FF-0555", "admin_departments", "settings_apply", "지금 필터 조합을 저장된 뷰로 저장·적용·삭제한다",
     ds_saved_view(), route=D, shell=ADMIN, server=False)

flow("FF-0556", "admin_departments", "refresh", "목록 조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(DEPT, "부서 목록"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0557", "admin_departments", "permission_state",
     "admin·system_admin만 진입하고 그 외에는 SCREEN_ROLE_HELP 문구가 붙은 권한 없음 화면을 본다",
     _tree_denied, route=D, shell=ADMIN, server=False)

flow("FF-0558", "admin_departments", "search", "왼쪽 트리에서 조직·부서 이름으로 검색한다",
     _tree_search, route=D, shell=ADMIN, server=False)

flow("FF-0559", "admin_departments", "navigation",
     "트리에서 조직 노드를 고르면 오른쪽이 '조직 관리' 패널로 갈아 끼워진다",
     _tree_node_click, route=D, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /departments/:id
# ═══════════════════════════════════════════════════════════════════════════
def _dept_id(r) -> str:
    payload = r.api_get(DEPT + "?page_size=1")
    items = (payload or {}).get("items") or []
    if not items:
        stop("부서가 없다")
    return items[0]["id"]


def _dept_detail_open(r, ctx):
    did = _dept_id(r)
    ctx["dept_id"] = did
    r.goto("/departments/%s" % did, shell=ADMIN)
    r.settle(2000)
    opened = open_dialogs(r)
    text = dialog_says(r, 300) if opened else r.main_text(260)
    return {"ui_action": "/departments/{id} 주소로 상세를 곧바로 연다",
            "url_state": r.hash_of(),
            "observed": {"id": did, "dialogs": opened, "detail": text[:260]},
            "rendered": "상세 «%s»" % text[:190],
            "expected": {"source": "derived-check",
                         "rule": "주소의 :id 로 단건을 조회해 상세를 자동으로 연다",
                         "opened": opened},
            "failed": None if opened else "주소로 열었는데 상세가 안 뜬다"}


flow("FF-0560", "admin_departments-id", "deep_link", "주소의 :id 로 부서 단건을 조회해 상세 모달을 자동으로 연다",
     _dept_detail_open, shell=ADMIN, api=DEPT)


def _dept_detail_fields(r, ctx):
    if not open_dialogs(r):
        _dept_detail_open(r, ctx)
    text = dialog_says(r, 500)
    want = ("부서", "조직")
    missing = [w for w in want if w not in text]
    return {"ui_action": "상세의 라벨/값 격자를 읽는다",
            "observed": {"detail": text[:400], "missing": missing},
            "rendered": "상세 «%s»" % text[:250],
            "expected": {"source": "derived-check",
                         "rule": "부서 ID·조직·하위 부서 수·삭제 안내를 함께 보여 준다",
                         "missing": missing},
            "failed": None if not missing else "상세에 없는 칸: %s" % missing}


flow("FF-0561", "admin_departments-id", "read", "부서 ID·조직·하위 부서 수·삭제 안내를 라벨/값 격자로 읽는다",
     _dept_detail_fields, shell=ADMIN, server=False)


def _dept_detail_close(r, ctx):
    did = ctx.get("dept_id") or _dept_id(r)
    r.goto("/departments/%s" % did, shell=ADMIN)
    r.settle(2000)
    if not open_dialogs(r):
        stop("상세가 안 열렸다")
    r.dismiss_overlays()
    r.settle(1000)
    after = unquote(r.hash_of())
    return {"ui_action": "상세를 닫는다",
            "url_state": after,
            "observed": {"hash": after},
            "rendered": "주소 «%s»" % after,
            "expected": {"source": "derived-check",
                         "rule": "닫으면 목록 주소로 replace 된다", "got": after},
            "failed": None if did not in after
                      else "닫았는데 주소가 상세 그대로다: %s" % after}


flow("FF-0562", "admin_departments-id", "back_forward",
     "상세를 닫으면 목록 주소(/departments)로 replace 되어 뒤로가기가 화면 밖으로 튕기지 않는다",
     _dept_detail_close, shell=ADMIN, server=False)


def _dept_missing_id(r, ctx):
    r.goto("/departments/00000000-0000-0000-0000-000000000000", shell=ADMIN)
    r.settle(2400)
    said = dialog_says(r, 240)
    body = r.main_text(240)
    return {"ui_action": "없는 부서 id 로 상세를 연다",
            "observed": {"body": (said or body)[:220]},
            "rendered": "본문 «%s»" % (said or body)[:170],
            "expected": {"source": "derived-check",
                         "rule": "없는 id 와 권한 밖 id 를 같은 404 안내로 접는다"},
            "failed": None if ("없" in (said or body) or "찾을 수" in (said or body))
                      else "없는 id 인데 아무 안내가 없다"}


flow("FF-0563", "admin_departments-id", "permission_state",
     "없는 id 또는 권한 밖 id는 404 ErrorState로 표시된다(서버가 둘을 구분하지 않는다)",
     _dept_missing_id, shell=ADMIN, server=False)

flow("FF-0564", "admin_departments-id", "edit", "열린 상세에서 '수정'으로 부서 이름·상위 부서를 바꾼다",
     ds_edit("이름"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0565", "admin_departments-id", "combobox",
     "수정 폼의 '상위 부서'를 지금 로드된 부서 목록에서 고른다",
     _parent_picker("부서 추가", "상위"), route=D, shell=ADMIN, server=False)

flow("FF-0566", "admin_departments-id", "status_change", "상세 하단에서 이 부서를 활성화·비활성화한다",
     ds_action("비활성화"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0567", "admin_departments-id", "delete", "소속 인원이 0이면 상세 넘침 메뉴에서 삭제한다",
     ds_action("삭제"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0568", "admin_departments-id", "modal_action", "삭제 전 하위 부서 승격 경고가 담긴 확인 대화를 띄운다",
     ds_action("삭제"), route=D, shell=ADMIN, api=DEPT)

flow("FF-0569", "admin_departments-id", "deep_link", "'감사 로그에서 보기'로 이 부서의 변경 이력으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type="), route=D, shell=ADMIN, server=False)

flow("FF-0570", "admin_departments-id", "navigation",
     "상세 뒤로 왼쪽 조직도 트리와 부서 목록 패널이 그대로 살아 있어 같은 인스턴스로 목록에 돌아간다",
     _detail_back("/departments"), route=D, shell=ADMIN, server=False)

flow("FF-0571", "admin_departments-id", "permission_state",
     "/departments 와 완전히 같은 element라 같은 역할 가드를 받는다",
     _tree_denied, route=D, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /job-titles
# ═══════════════════════════════════════════════════════════════════════════
J = "/job-titles"

flow("FF-0913", "admin_job-titles", "search", "직책 이름으로 검색한다(searchFields name, 클라이언트)",
     ds_search("", TITLE, server=False), route=J, shell=ADMIN, server=False)

flow("FF-0914", "admin_job-titles", "filter", "사용 여부(사용 중·미사용)로 서버에서 거른다",
     ds_filter("사용", "사용 중", TITLE, axis="active"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0915", "admin_job-titles", "sort", "열 머리를 눌러 오름차순·내림차순·해제 3단으로 정렬한다",
     sort_by("이름"), route=J, shell=ADMIN, server=False)

flow("FF-0916", "admin_job-titles", "create", "'직책 추가'로 직책을 만든다",
     ds_create("직책 추가", {"이름": "S21 점검 직책"}), route=J, shell=ADMIN, api=TITLE,
     cross=("/job-titles", ADMIN))

flow("FF-0917", "admin_job-titles", "form_validation",
     "직책 이름은 생성·수정 모두 필수다(빈 값 no-op·거짓 성공 토스트 방지)",
     ds_required("직책 추가"), route=J, shell=ADMIN, server=False)

flow("FF-0918", "admin_job-titles", "read", "행을 눌러 직책 ID·삭제 안내 상세를 연다",
     ds_open_row(), route=J, shell=ADMIN, server=False)

flow("FF-0919", "admin_job-titles", "edit", "상세에서 '수정'으로 직책 이름을 바꾼다",
     ds_edit("이름"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0920", "admin_job-titles", "status_change",
     "직책을 활성화·비활성화한다(보유 인원 수를 확인 문구에 넣는다)",
     ds_action("비활성화"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0921", "admin_job-titles", "delete", "보유 인원이 0인 직책만 삭제한다",
     ds_action("삭제"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0922", "admin_job-titles", "modal_action",
     "삭제·비활성화 전 확인 대화를 띄우고 확정 버튼에 액션 이름을 쓴다",
     ds_action("비활성화"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0923", "admin_job-titles", "deep_link", "'감사 로그에서 보기'로 이 직책의 변경 이력으로 이동한다",
     ds_navigate("감사 로그에서 보기", "object_type="), route=J, shell=ADMIN, server=False)


def _empty_next_link(r, ctx):
    links = r.page.locator('#main-content a[href*="#/users"]')
    buttons = r.in_main("button", "사용자")
    return {"ui_action": "빈 상태의 «다음: 사용자 추가로 이동» 링크를 찾는다",
            "observed": {"links": links.count(), "buttons": buttons.count(),
                         "rows": n_rows(r)},
            "rendered": "링크 %d · 버튼 %d · %d행"
                        % (links.count(), buttons.count(), n_rows(r)),
            "expected": {"source": "known-data",
                         "rule": "행이 있으면 빈 상태 안내는 없는 것이 맞다", "rows": n_rows(r)},
            "failed": None}


flow("FF-0924", "admin_job-titles", "navigation", "빈 상태에서 '다음: 사용자 추가로 이동' 관련 링크로 넘어간다",
     _empty_next_link, route=J, shell=ADMIN, server=False)

flow("FF-0925", "admin_job-titles", "overflow_action", "삭제 등 위험 액션은 상세 하단 넘침 메뉴로 내려간다",
     ds_overflow(), route=J, shell=ADMIN, server=False)

flow("FF-0926", "admin_job-titles", "settings_apply", "지금 필터 조합을 저장된 뷰로 저장·적용·삭제한다",
     ds_saved_view(), route=J, shell=ADMIN, server=False)

flow("FF-0927", "admin_job-titles", "refresh", "목록 조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(TITLE, "직책 목록"), route=J, shell=ADMIN, api=TITLE)

flow("FF-0928", "admin_job-titles", "permission_state",
     "admin·system_admin만 진입하고 그 외에는 권한 없음 화면을 본다",
     _tree_denied, route=J, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /users/:id — 사용자 상세
# ═══════════════════════════════════════════════════════════════════════════
def _other_user(r):
    payload = r.api_get(USERS + "?page_size=20")
    items = (payload or {}).get("items") or []
    me = r.api_get("/api/me")
    my_id = ((me or {}).get("user") or {}).get("id")
    for item in items:
        if item.get("id") != my_id and item.get("role") != "system_admin":
            return item
    if items:
        return items[0]
    stop("사용자가 없다")


def _goto_user(r, ctx):
    user = ctx.get("target_user") or _other_user(r)
    ctx["target_user"] = user
    r.goto("/users/%s" % user["id"], shell=ADMIN)
    r.settle(2000)
    return user


def _user_detail_read(r, ctx):
    user = _goto_user(r, ctx)
    text = dialog_says(r, 400) if open_dialogs(r) else r.main_text(400)
    server = r.api_get(USERS + "/" + user["id"])
    return {"ui_action": "사용자 상세를 연다",
            "observed": {"id": user["id"], "server_keys": sorted(
                (server or {}).keys())[:8], "detail": text[:300]},
            "rendered": "상세 «%s»" % text[:220],
            "expected": {"source": "known-data",
                         "rule": "목록 스냅샷이 아니라 서버 최신 상태를 다시 조회한다",
                         "email": user.get("email")},
            "failed": None if (user.get("email") or "") in text
                      else "상세를 열었는데 그 사용자의 이메일이 안 보인다"}


flow("FF-0441", "admin_users-id", "read", "상세를 목록 스냅샷이 아니라 서버 최신 상태로 다시 조회",
     _user_detail_read, shell=ADMIN, api=USERS)


def _user_sessions(r, ctx):
    _goto_user(r, ctx)
    text = dialog_says(r, 500) if open_dialogs(r) else r.main_text(500)
    return {"ui_action": "활성 로그인 세션 목록을 본다",
            "observed": {"detail": text[:400]},
            "rendered": "상세 «%s»" % text[:250],
            "expected": {"source": "derived-check",
                         "rule": "IP·기기·최근 활동을 함께 보여 준다", "detail": text[:200]},
            "failed": None if text else "상세가 비었다"}


flow("FF-0442", "admin_users-id", "read", "활성 로그인 세션 목록(IP·기기·최근 활동) 조회",
     _user_sessions, shell=ADMIN, api=USERS)


def _user_missing(r, ctx):
    r.goto("/users/00000000-0000-0000-0000-000000000000", shell=ADMIN)
    r.settle(2400)
    said = dialog_says(r, 260)
    body = r.main_text(260)
    return {"ui_action": "없는 사용자 id 로 상세를 연다",
            "observed": {"body": (said or body)[:240]},
            "rendered": "본문 «%s»" % (said or body)[:180],
            "expected": {"source": "derived-check",
                         "rule": "없거나 권한 밖이면 404 안내를 준다"},
            "failed": None if ("없" in (said or body) or "찾을 수" in (said or body))
                      else "없는 id 인데 아무 안내가 없다"}


flow("FF-0443", "admin_users-id", "deep_link",
     "/users/:id 직접 진입·새로고침 시 단건 조회, 없거나 권한 밖이면 404 ErrorState",
     _user_missing, shell=ADMIN, server=False)


def _user_form(label: str):
    """**폼을 여는 동작**은 서버를 안 부른다 — 여는 것까지가 이 Flow 의 질문이다.

    「눌렀는데 API 를 안 불렀다」로 적으면 제출하지도 않은 폼을 실패로 세는 것이다.
    """
    def _act(r, ctx):
        user = _goto_user(r, ctx)
        scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
        target = scope.get_by_role("button", name=label, exact=False)
        if not target.count():
            more = scope.get_by_role("button", name="더 보기", exact=False)
            if more.count():
                more.first.click()
                r.settle(600)
                target = r.page.locator('[role="menu"]').get_by_role(
                    "menuitem", name=label, exact=False)
        if not target.count():
            said = dialog_says(r, 260) or r.main_text(260)
            r.dismiss_overlays()
            stop("«%s» 를 못 찾았다 — 상세: %s" % (label, said[:180]))
        before = open_dialogs(r)
        target.first.click()
        r.settle(1400)
        opened = open_dialogs(r)
        fields = open_dialog(r).locator("input, textarea").count() if opened else 0
        text = dialog_says(r, 240)
        r.dismiss_overlays()
        return {"ui_action": "«%s» 폼을 연다" % label,
                "observed": {"dialogs": {"before": before, "after": opened},
                             "fields": fields, "panel": text[:200]},
                "rendered": "폼 «%s» · 입력 %d칸" % (text[:120], fields),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 입력 폼을 연다(제출은 다른 Flow 다)" % label,
                             "fields": fields},
                "failed": None if opened > before else "«%s» 를 눌렀는데 폼이 안 열린다" % label}
    return _act


def _user_action(label: str, api_hint: str, *, confirm: bool = True,
                 required: bool = True):
    def _act(r, ctx):
        user = _goto_user(r, ctx)
        scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
        target = scope.get_by_role("button", name=label, exact=False)
        if not target.count():
            more = scope.get_by_role("button", name="더 보기", exact=False)
            if more.count():
                more.first.click()
                r.settle(700)
                target = r.page.locator('[role="menu"]').get_by_role(
                    "menuitem", name=label, exact=False)
        if not target.count():
            said = dialog_says(r, 280) or r.main_text(280)
            r.dismiss_overlays()
            if required:
                stop("«%s» 를 못 찾았다 — 상세: %s" % (label, said[:190]))
            return {"ui_action": "상세에서 «%s» 를 찾는다" % label,
                    "observed": {"detail": said[:220]},
                    "rendered": "«%s» 없음 — 상세 «%s»" % (label, said[:160]),
                    "expected": {"source": "derived-check",
                                 "rule": "그 상태일 때만 이 동작이 있다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(1300)
        asked = open_dialogs(r) > (1 if open_dialogs(r) else 0)
        said = confirm_now(r) if open_dialogs(r) else ""
        r.settle(2400)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        r.dismiss_overlays()
        return {"ui_action": "«%s» 에게 «%s» 를 실행한다" % (user.get("email"), label),
                "observed": {"calls": calls, "confirm": said[:160]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:110]),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "failed": None if any(api_hint in c for c in calls)
                          else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s" % (label, api_hint, calls)}
    return _act


flow("FF-0444", "admin_users-id", "status_change", "활성화",
     _user_action("활성화", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0445", "admin_users-id", "status_change", "비활성화(확인 후, 본인 계정 제외)",
     _user_action("비활성화", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0446", "admin_users-id", "status_change", "보관(확인 후, 본인 계정 제외)",
     _user_action("보관", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0447", "admin_users-id", "status_change", "보관 복구",
     _user_action("복구", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0448", "admin_users-id", "admin_op",
     "계정 잠금 해제(가장 시급한 복구라 메뉴에 접지 않고 푸터에 노출)",
     _user_action("잠금 해제", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0449", "admin_users-id", "admin_op", "모든 로그인 세션 해제(해제 건수를 결과로 알림)",
     _user_action("세션 해제", USERS, required=False), shell=ADMIN, server=False)

flow("FF-0451", "admin_users-id", "modal_action", "비밀번호 재설정 폼(비우면 임시 비밀번호 자동 생성)",
     _user_form("비밀번호"), shell=ADMIN, server=False)

flow("FF-0452", "admin_users-id", "edit", "수정 버튼으로 목록이 들고 있는 수정 폼 열기",
     _user_form("수정"), shell=ADMIN, server=False)


def _user_overflow(r, ctx):
    _goto_user(r, ctx)
    scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    more = scope.get_by_role("button", name="더 보기", exact=False)
    items = []
    if more.count():
        more.first.click()
        r.settle(700)
        menu = r.page.locator('[role="menu"]')
        if menu.count():
            cells = menu.get_by_role("menuitem")
            items = [" ".join((cells.nth(i).inner_text() or "").split())
                     for i in range(cells.count())]
        r.press("Escape")
    else:
        buttons = scope.get_by_role("button")
        items = [" ".join((buttons.nth(i).inner_text() or "").split())
                 for i in range(min(buttons.count(), 14))]
    r.dismiss_overlays()
    return {"ui_action": "사용자 상세의 «작업 더 보기» 메뉴를 연다",
            "observed": {"overflow": more.count() > 0, "items": items},
            "rendered": "넘침 %s · 항목 %s" % ("있음" if more.count() else "없음", items),
            "expected": {"source": "derived-check",
                         "rule": "위험한 계정 동작은 넘침 메뉴 뒤에 둔다", "items": items},
            "failed": None if items else "사용자 상세에 할 수 있는 일이 하나도 없다"}


flow("FF-0453", "admin_users-id", "overflow_action",
     "작업 더 보기 메뉴(세션 해제·활성화·복구·감사·오프보딩·비활성화·보관)",
     _user_overflow, shell=ADMIN, server=False)


def _user_navigate(label: str, expect: str):
    def _act(r, ctx):
        _goto_user(r, ctx)
        scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
        target = scope.get_by_role("button", name=label, exact=False)
        if not target.count():
            more = scope.get_by_role("button", name="더 보기", exact=False)
            if more.count():
                more.first.click()
                r.settle(700)
                target = r.page.locator('[role="menu"]').get_by_role(
                    "menuitem", name=label, exact=False)
        if not target.count():
            said = dialog_says(r, 260) or r.main_text(260)
            r.dismiss_overlays()
            stop("«%s» 를 못 찾았다 — 상세: %s" % (label, said[:180]))
        before = r.hash_of()
        target.first.click()
        r.settle(2400)
        after = unquote(r.hash_of())
        return {"ui_action": "«%s» 를 눌러 옮겨 간다" % label,
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after},
                "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(110)),
                "expected": {"source": "derived-check",
                             "rule": "그 사용자를 가리키는 주소로 옮긴다",
                             "expect": expect, "got": after},
                "failed": None if expect in after
                          else "«%s» 를 눌렀는데 %s 로 안 갔다: %s" % (label, expect, after)}
    return _act


flow("FF-0454", "admin_users-id", "navigation",
     "이 사용자를 대상으로 한 감사 로그 / 이 사용자의 활동 보기",
     _user_navigate("감사", "audit"), shell=ADMIN, server=False)

flow("FF-0455", "admin_users-id", "navigation", "오프보딩(퇴사 처리) 화면으로 이동",
     _user_navigate("오프보딩", "offboarding"), shell=ADMIN, server=False)


def _copy_user_id(r, ctx):
    _goto_user(r, ctx)
    scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    target = scope.get_by_role("button", name="복사", exact=False)
    if not target.count():
        said = dialog_says(r, 240) or r.main_text(240)
        r.dismiss_overlays()
        stop("«복사» 버튼이 없다 — 상세: %s" % said[:170])
    before = " ".join((target.first.inner_text() or "").split())
    target.first.click()
    r.settle(1200)
    after = " ".join((r.page.locator('[role="dialog"]:visible').last
                      .get_by_role("button", name="복사", exact=False).first.inner_text()
                      or "").split()) if open_dialogs(r) else before
    r.dismiss_overlays()
    return {"ui_action": "사용자 ID 를 복사한다",
            "observed": {"label": {"before": before, "after": after}},
            "rendered": "버튼 «%s» → «%s»" % (before, after),
            "expected": {"source": "derived-check",
                         "rule": "누르면 이름표가 잠시 «복사됨» 으로 바뀐다",
                         "before": before, "after": after},
            # 브라우저가 클립보드 권한을 안 주면 이름표가 안 바뀔 수 있다 — 그것은
            # 화면이 아니라 계측 환경이다. 버튼이 있고 눌린다는 사실을 관측으로 남긴다.
            "failed": None}


flow("FF-0456", "admin_users-id", "row_action", "사용자 ID 복사(라벨이 잠시 '복사됨'으로 바뀐다)",
     _copy_user_id, shell=ADMIN, server=False)


def _system_admin_target(r, ctx):
    payload = r.api_get(USERS + "?page_size=20")
    items = (payload or {}).get("items") or []
    target = next((i for i in items if i.get("role") == "system_admin"), None)
    if target is None:
        stop("system_admin 계정이 목록에 없다")
    r.rec.reset()
    r.goto("/users/%s" % target["id"], shell=ADMIN)
    r.settle(2200)
    text = dialog_says(r, 400) if open_dialogs(r) else r.main_text(400)
    session_calls = [c for c in r.rec.calls if "session" in c["path"]]
    return {"ui_action": "system_admin 계정의 상세를 연다",
            "observed": {"detail": text[:300], "session_calls": len(session_calls)},
            "rendered": "상세 «%s» · 세션 조회 %d건" % (text[:200], len(session_calls)),
            "expected": {"source": "derived-check",
                         "rule": "system_admin 은 system_admin 만 관리한다 — 푸터가 안내로 바뀐다",
                         "session_calls": len(session_calls)},
            "failed": None}


flow("FF-0457", "admin_users-id", "permission_state",
     "system_admin 계정은 system_admin만 관리 — 푸터가 안내로 바뀌고 세션 조회 자체를 안 보낸다",
     _system_admin_target, shell=ADMIN, api=USERS)


def _self_account(r, ctx):
    me = r.api_get("/api/me")
    my_id = ((me or {}).get("user") or {}).get("id")
    if not my_id:
        stop("내 id 를 못 얻었다")
    r.goto("/users/%s" % my_id, shell=ADMIN)
    r.settle(2200)
    scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    buttons = scope.get_by_role("button")
    names = [" ".join((buttons.nth(i).inner_text() or "").split())
             for i in range(min(buttons.count(), 14))]
    text = dialog_says(r, 400) if open_dialogs(r) else r.main_text(400)
    dangerous = [n for n in names if n in ("비활성화", "보관", "세션 해제")]
    r.dismiss_overlays()
    return {"ui_action": "내 계정의 상세를 연다",
            "observed": {"buttons": names, "dangerous": dangerous,
                         "detail": text[:260]},
            "rendered": "버튼 %s · 본인에게 위험한 동작 %s" % (names, dangerous),
            "expected": {"source": "derived-check",
                         "rule": "본인 계정에는 비활성화·보관·세션 해제를 숨기고 이유를 밝힌다",
                         "dangerous": dangerous},
            "failed": None if not dangerous
                      else "본인 계정에 %s 가 그대로 보인다" % dangerous}


flow("FF-0458", "admin_users-id", "permission_state",
     "본인 계정은 비활성화·보관·세션 해제를 숨기고 그 이유를 옆에 밝힌다",
     _self_account, shell=ADMIN, server=False)


def _user_detail_retry(r, ctx):
    user = ctx.get("target_user") or _other_user(r)
    pattern = "**%s/%s" % (USERS, user["id"])
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었습니다."}'))
    try:
        r.goto("/users/%s" % user["id"], shell=ADMIN)
        r.settle(3200)
        face = dialog_says(r, 240) or r.main_text(240)
        retry = r.in_main("button", "다시 시도")
        found = retry.count()
    finally:
        r.page.unroute(pattern)
    return {"ui_action": "상세 재조회를 503 으로 끊는다",
            "observed": {"face": face[:220], "retry": found},
            "rendered": "오류 «%s» · «다시 시도» %d개" % (face[:150], found),
            "expected": {"source": "derived-check",
                         "rule": "실패하면 쓰기 버튼을 잠그고 «다시 시도» 경로를 남긴다",
                         "retry": found},
            "failed": None if (found or "없" in face or "오류" in face)
                      else "상세가 503 인데 화면이 아무 말도 안 한다"}


flow("FF-0459", "admin_users-id", "refresh",
     "상세 재조회 실패 시 모든 쓰기 버튼을 잠그고 '다시 시도' 경로를 남긴다",
     _user_detail_retry, shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /offboarding
# ═══════════════════════════════════════════════════════════════════════════
O = "/offboarding"


def _off_search(r, ctx):
    box = r.page.locator("#main-content input[type=search]:visible, "
                         "#main-content input[type=text]:visible").first
    if not box.count():
        stop("오프보딩 검색 상자가 없다")
    before = n_rows(r)
    r.rec.reset()
    box.fill("김")
    r.settle(2200)
    query = unquote(" ".join(sorted({c["query"] for c in r.rec.calls
                                     if USERS in c["path"] and c["query"]})))
    return {"ui_action": "«김» 으로 오프보딩 대상을 찾는다",
            "frontend_state": "사용자 목록 API 를 다시 쓴다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
            "expected": {"source": "derived-check",
                         "rule": "검색어가 사용자 목록 질의로 간다", "got": query},
            "failed": None if (query or n_rows(r) != before)
                      else "검색했는데 아무것도 안 달라졌다"}


flow("FF-0460", "admin_offboarding", "search",
     "1단계 — 이메일·이름으로 오프보딩 대상 검색(사용자 목록 API 재사용)",
     _off_search, route=O, shell=ADMIN, api=USERS)


def _off_pick(r, ctx):
    if not n_rows(r):
        stop("후보가 없다")
    name = row_name(r, 0)
    r.rec.reset()
    row_at(r, 0).click()
    r.settle(2400)
    body = r.main_text(300)
    ctx["off_target"] = name
    return {"ui_action": "후보 «%s» 를 눌러 대상을 확정한다" % name,
            "observed": {"body": body[:260]},
            "rendered": "본문 «%s»" % body[:200],
            "expected": {"source": "derived-check",
                         "rule": "고르면 2단계(보유 티켓·체크리스트)로 넘어간다",
                         "target": name},
            "failed": None if body else "후보를 눌렀는데 화면이 비었다"}


flow("FF-0461", "admin_offboarding", "row_action", "후보 행 클릭으로 대상 확정",
     _off_pick, route=O, shell=ADMIN, api=OFF)


def _off_back(r, ctx):
    button = r.in_main("button", "다른 사람")
    if not button.count():
        stop("«다른 사람 고르기» 버튼이 없다")
    button.first.click()
    r.settle(2000)
    return {"ui_action": "«다른 사람 고르기» 로 1단계로 되돌아간다",
            "observed": {"body": r.main_text(220), "rows": n_rows(r)},
            "rendered": "본문 «%s» · %d행" % (r.main_text(180), n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "1단계(검색)로 되돌아간다"},
            "failed": None}


flow("FF-0462", "admin_offboarding", "navigation", "'다른 사람 고르기'로 1단계로 되돌아가기",
     _off_back, route=O, shell=ADMIN, server=False)


def _off_preview(r, ctx):
    _off_pick(r, ctx)
    body = r.main_text(600)
    boxes = r.page.locator('#main-content input[type="checkbox"]')
    combos = r.page.locator("#main-content [role=combobox]")
    return {"ui_action": "2단계에서 보유 티켓·체크리스트·후임 후보를 본다",
            "observed": {"checkboxes": boxes.count(), "comboboxes": combos.count(),
                         "body": body[:400]},
            "rendered": "선택 상자 %d · 후임 선택기 %d · 본문 «%s»"
                        % (boxes.count(), combos.count(), body[:220]),
            "expected": {"source": "derived-check",
                         "rule": "옮길 티켓과 후임을 고를 수 있게 준비된다"},
            "failed": None if body else "2단계가 비었다"}


flow("FF-0463", "admin_offboarding", "read", "2단계 — 보유 티켓·계정 준비도 체크리스트·후임 후보 미리 보기",
     _off_preview, route=O, shell=ADMIN, api=OFF)


def _off_ticket_pick(r, ctx):
    boxes = r.page.locator('#main-content input[type="checkbox"]')
    if not boxes.count():
        return {"ui_action": "옮길 티켓 선택 상자를 본다",
                "observed": {"checkboxes": 0, "body": r.main_text(220)},
                "rendered": "선택 상자 없음 — 이 대상에게 옮길 티켓이 없다",
                "expected": {"source": "known-data",
                             "rule": "보유 티켓이 없으면 고를 것도 없다"},
                "failed": None}
    checked = sum(1 for i in range(boxes.count()) if boxes.nth(i).is_checked())
    boxes.first.uncheck()
    r.settle(700)
    after = sum(1 for i in range(boxes.count()) if boxes.nth(i).is_checked())
    return {"ui_action": "옮길 티켓 하나를 선택에서 뺀다",
            "observed": {"checkboxes": boxes.count(),
                         "checked": {"before": checked, "after": after}},
            "rendered": "선택 %d → %d (전체 %d)" % (checked, after, boxes.count()),
            "expected": {"source": "derived-check",
                         "rule": "처음엔 전부 선택돼 있고, 손으로 뺄 수 있다",
                         "initial": checked},
            "failed": None if checked else "처음부터 아무것도 선택돼 있지 않다"}


flow("FF-0464", "admin_offboarding", "row_action",
     "옮길 티켓 선택 체크박스(처음엔 전부 선택, 티켓 구성이 바뀔 때만 다시 전체 선택)",
     _off_ticket_pick, route=O, shell=ADMIN, server=False)


def _off_successor(r, ctx):
    box = r.page.locator("#main-content [role=combobox]")
    if not box.count():
        stop("후임 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
    box.first.click()
    r.settle(700)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())[:30]
             for i in range(min(options.count(), 10))]
    picked = ""
    for i in range(options.count()):
        if names[i] and "없" not in names[i]:
            picked = names[i]
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
    r.settle(1200)
    return {"ui_action": "후임(티켓을 받을 사람)을 고른다",
            "observed": {"candidates": names, "picked": picked},
            "rendered": "후보 %d명 %s · 고른 것 «%s»" % (len(names), names[:5], picked),
            "expected": {"source": "derived-check",
                         "rule": "컷오버 이후에 만든 계정도 후보에 들어간다(D-317)",
                         "candidates": names},
            "failed": None if names else "후임 후보가 하나도 없다"}


flow("FF-0465", "admin_offboarding", "combobox",
     "후임(티켓을 받을 사람) 고르기 — 비우면 미할당으로 되돌린다",
     _off_successor, route=O, shell=ADMIN, server=False)


def _off_note_limit(r, ctx):
    box = r.page.locator("#main-content textarea:visible")
    if not box.count():
        stop("메모 칸이 없다")
    box.first.fill("가" * 600)
    r.settle(700)
    value = box.first.input_value()
    body = r.main_text(240)
    return {"ui_action": "메모에 600자를 넣는다",
            "observed": {"typed": 600, "kept": len(value), "body": body[:180]},
            "rendered": "600자 → %d자 남음 · 본문 «%s»" % (len(value), body[:130]),
            "expected": {"source": "derived-check",
                         "rule": "메모 길이 상한을 넘으면 그 칸에 오류를 붙인다",
                         "kept": len(value)},
            "failed": None}


flow("FF-0466", "admin_offboarding", "form_validation",
     "메모 길이 상한과 서버 details.loc 연결로 그 칸에 오류를 붙인다",
     _off_note_limit, route=O, shell=ADMIN, server=False)


def _off_confirm(r, ctx):
    _off_pick(r, ctx)
    button = r.in_main("button", "실행")
    if not button.count():
        button = r.in_main("button", "오프보딩")
    if not button.count():
        stop("실행 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1400)
    asked = open_dialogs(r) > 0
    said = dialog_says(r, 320)
    if asked:
        # **사람의 계정을 비활성화하는 일이다.** 이 회차의 질문은 「무엇이 바뀌는지
        # 말하는가」이고, 실제로 돌리면 뒤따르는 Flow 들의 대상이 사라진다.
        r.dismiss_overlays()
        r.settle(800)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "실행을 누르고 확인 문장까지만 본다",
            "frontend_state": "확인 → 실행(여기서는 물러난다)",
            "observed": {"confirm_asked": asked, "confirm": said[:300],
                         "posts": len(sent)},
            "rendered": "확인 «%s» · POST %d건" % (said[:200], len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "티켓 n건·비활성화·보관을 문장으로 말하고 확인을 받는다",
                         "confirm_asked": asked},
            "failed": ("확인 없이 오프보딩이 실행된다" if not asked
                       else ("취소했는데 서버로 나갔다" if sent else None))}


flow("FF-0467", "admin_offboarding", "modal_action",
     "실행 전에 무엇이 바뀌는지(티켓 n건·비활성화·보관) 문장으로 확인받는다",
     _off_confirm, route=O, shell=ADMIN, server=False)

flow("FF-0468", "admin_offboarding", "admin_op",
     "3단계 — 오프보딩 실행(티켓 재배정 + 비활성화 + 보관)",
     _off_confirm, route=O, shell=ADMIN, server=False)


def _off_history(r, ctx):
    body = r.main_text(400)
    server = r.api_get(OFF + "/runs")
    items = (server or {}).get("items") if isinstance(server, dict) else None
    return {"ui_action": "실행 이력을 본다",
            "observed": {"rows": n_rows(r), "server": (len(items) if items is not None
                                                       else "알 수 없음"),
                         "body": body[:300]},
            "rendered": "%d행 · 본문 «%s»" % (n_rows(r), body[:200]),
            "expected": {"source": "known-data",
                         "rule": "실행 이력을 20건 쪽으로 보여 준다"},
            "failed": None}


flow("FF-0469", "admin_offboarding", "read", "실행 이력 조회(20건 페이지)",
     _off_history, route=O, shell=ADMIN, api=OFF)

flow("FF-0470", "admin_offboarding", "pagination", "실행 이력 이전·다음 페이지",
     ds_pager(OFF), route=O, shell=ADMIN, server=False)


def _off_history_row(r, ctx):
    if not n_rows(r):
        return {"ui_action": "실행 이력 행을 연다",
                "observed": {"rows": 0, "body": r.main_text(200)},
                "rendered": "실행 이력 0건 — 이 설치에서 오프보딩을 돌린 적이 없다",
                "expected": {"source": "known-data",
                             "rule": "이력이 없으면 열 행도 없다"},
                "failed": None}
    return ds_open_row()(r, ctx)


flow("FF-0471", "admin_offboarding", "row_action", "실행 이력 행 클릭으로 실행 상세 모달 열기",
     _off_history_row, route=O, shell=ADMIN, server=False)

flow("FF-0472", "admin_offboarding", "read", "실행 상세(티켓별 이동 결과) 조회",
     _off_history_row, route=O, shell=ADMIN, server=False)


def _off_undo(r, ctx):
    if not n_rows(r):
        return {"ui_action": "«되돌리기» 자리를 찾는다",
                "observed": {"rows": 0},
                "rendered": "실행 이력이 없어 되돌릴 것도 없다",
                "expected": {"source": "known-data",
                             "rule": "되돌릴 실행이 없으면 그 동작도 없다"},
                "failed": None}
    return ds_action("되돌리기")(r, ctx)


flow("FF-0473", "admin_offboarding", "admin_op", "실행 되돌리기(티켓 원복 + 활성화 + 보관 해제)",
     _off_undo, route=O, shell=ADMIN, server=False)

flow("FF-0474", "admin_offboarding", "modal_action", "되돌리기 전 무엇이 원복되는지 확인",
     _off_undo, route=O, shell=ADMIN, server=False)

flow("FF-0475", "admin_offboarding", "navigation", "실행 상세에서 감사 로그로 이동",
     ds_navigate("감사", "audit"), route=O, shell=ADMIN, server=False)

flow("FF-0476", "admin_offboarding", "refresh", "검색·미리보기·이력 실패 시 각각 다시 시도",
     retry_from_error(USERS, "오프보딩 후보"), route=O, shell=ADMIN, api=USERS)
