"""B11 Split view — `/organizations` (W8 · S18).

이 원형의 계약은 **navigator 하나, 상세 하나, 관련 컬렉션 하나**다. 계획서가 이 화면의
결함으로 이름 대어 적어 둔 것이 「우측 pane 이 자체 PageHeader·검색·SavedViews 를 가진
DataScreen 을 통째로 렌더한다」였고, S18 이 그것을 정정했다 — 그래서 이 표는 **없어진
것도 함께 잰다**: 검색 상자가 하나인가, 저장된 뷰가 상세 판에 없는가.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    back_forward, blocked_route, cache_key, choose_then, click_then, close_modal,
    dialog_text, dialogs, flow, modal_open_close, no_page_axis, open_row, open_row_modal,
    race, required_blocks_submit, retry_from_error, stop, unquote_hash,
)

ADMIN = "/admin"
TREE = '[data-testid="org-console-tree"]'
PANEL = '[data-testid="org-console-panel"]'
PEOPLE = '[data-testid="org-console-people"]'
# navigator(왼쪽 트리)의 검색 상자 — 이 화면의 «조건» 은 저기서 시작한다.
ORG_SEARCH = TREE + ' input[type="search"], ' + TREE + ' input[aria-label*="검색"]'


def _panel_search(r, ctx):
    """상세 판에는 **자기 검색 상자가 없다** — navigator 가 그것을 갖는다."""
    tree_boxes = r.page.locator(TREE + ' input[type="search"], ' + TREE + ' input[aria-label*="검색"]')
    panel_boxes = r.page.locator(PANEL + ' input[type="search"], ' + PANEL + ' input[aria-label*="검색"]')
    saved = r.page.locator(PANEL).get_by_role("button", name="저장된 뷰")
    before = r.rows()
    if not tree_boxes.count():
        stop("navigator 에 검색 상자가 없다")
    tree_boxes.first.fill("default")
    r.settle(1200)
    nodes = r.page.locator(TREE + ' [role="treeitem"]').count()
    return {"ui_action": "navigator 검색에 식별자 «default» 를 넣는다",
            "frontend_state": "트리 검색 = name·path·slug",
            "observed": {"search_boxes": {"tree": tree_boxes.count(),
                                          "panel": panel_boxes.count()},
                         "saved_views_in_panel": saved.count(),
                         "tree_nodes_after": nodes, "panel_rows_before": before},
            "rendered": "검색 상자 트리 %d · 상세 판 %d · 저장된 뷰 %d · 트리 마디 %d개"
                        % (tree_boxes.count(), panel_boxes.count(), saved.count(), nodes),
            "failed": None if (panel_boxes.count() == 0 and saved.count() == 0 and nodes)
                      else "상세 판이 자기 검색·저장된 뷰를 그렸거나 식별자로 못 찾는다"}


flow("FF-0522", "admin_organizations", "search",
     "조직 이름 또는 식별자로 검색한다(searchFields name·slug — 분할 뷰에서는 navigator 가 갖는다)",
     _panel_search, route="/organizations", shell=ADMIN, server=False)

flow("FF-0523", "admin_organizations", "filter",
     "상태(사용 중·미사용)로 조직 목록을 화면에서 거른다(clientFilter)",
     choose_then("상태", "미사용"), route="/organizations", shell=ADMIN, server=False)


def _sort_cycle(r, ctx):
    """**누른 그 칸**의 정렬 상태를 읽는다.

    예전에는 아무 칸의 정렬 버튼을 누르고 **첫 칸**의 `aria-sort` 를 읽었다. 이 표의 첫
    열(조직 이름)은 정렬 대상이 아니라 그 칸에는 `aria-sort` 자체가 없다 — 그래서 세 번
    눌러도 언제나 `none` 이었고, 제품이 3단으로 잘 돌고 있는데 「안 바뀐다」로 적혔다.
    머리글에는 정렬 버튼 말고 **열 필터 버튼**도 있으므로(S18 이후) 그것도 걸러 낸다.
    """
    cells = r.page.locator(PANEL + " table thead th")
    if not cells.count():
        stop("표 머리가 없다")
    index, head = -1, None
    for i in range(cells.count()):
        button = cells.nth(i).locator('button:not([aria-label$="필터"])')
        if button.count():
            index, head = i, button.first
            break
    if head is None:
        stop("정렬할 수 있는 열 머리가 없다")
    label = " ".join((head.inner_text() or "").split())[:24]
    states = []
    for _ in range(3):
        head.click()
        r.settle(700)
        cell = r.page.locator(PANEL + " table thead th").nth(index)
        states.append(cell.get_attribute("aria-sort") or "none")
    return {"ui_action": "열 머리 «%s» 를 세 번 누른다" % label,
            "frontend_state": "오름 → 내림 → 해제",
            "observed": {"aria_sort": states, "column": label, "column_index": index},
            "rendered": "«%s» 정렬 상태 %s" % (label, states),
            "failed": None if len(set(states)) > 1
                      else "세 번 눌러도 정렬 상태가 안 바뀐다: %s" % states}


flow("FF-0524", "admin_organizations", "sort",
     "열 머리를 눌러 오름차순·내림차순·해제 3단으로 정렬한다(페이지네이션 없는 화면이라 활성)",
     _sort_cycle, route="/organizations", shell=ADMIN, server=False)


def _org_create(r, ctx):
    open_row_modal(r, ctx, opener="button=조직 추가")
    dialog = r.page.locator('[role="dialog"]')
    inputs = dialog.locator("input")
    inputs.nth(0).fill("S18 파일럿 조직")
    if inputs.count() > 1:
        inputs.nth(1).fill("s18-pilot")
    r.settle(500)
    r.rec.reset()
    submit = r.page.get_by_role("button", name="추가")
    if submit.count() and not submit.first.is_disabled():
        submit.first.click()
        r.settle(2000)
    calls = [c for c in r.rec.calls if c["method"] == "POST"]
    return {"ui_action": "«조직 추가» 로 이름·식별자를 넣고 만든다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "표 %d행 · 본문 «%s»" % (r.rows(), r.main_text(90)),
            "cross": {"row": "S18 파일럿 조직", "expect": "s18-pilot"},
            "failed": None if calls else "추가했는데 요청이 없었다"}


flow("FF-0525", "admin_organizations", "create",
     "'조직 추가'로 조직 이름·식별자를 입력해 조직을 만든다",
     _org_create, route="/organizations", shell=ADMIN, api="/api/admin/organizations",
     cross=("/organizations", ADMIN))

flow("FF-0526", "admin_organizations", "form_validation",
     "조직 이름·식별자는 필수라 비우면 제출되지 않는다",
     required_blocks_submit("button=조직 추가"), route="/organizations", shell=ADMIN,
     server=False)


def _org_detail(r, ctx):
    if not r.page.locator(PANEL + " table tbody tr").count():
        stop("조직 표에 행이 없다")
    open_row(r)
    text = dialog_text(r) or r.main_text(200)
    return {"ui_action": "조직 행을 눌러 상세를 연다",
            "observed": {"detail": text},
            "rendered": "상세 «%s»" % text,
            "failed": None if text else "상세가 비었다"}


flow("FF-0527", "admin_organizations", "read",
     "행을 눌러 조직 ID·식별자·포함 관계·삭제 안내 상세를 연다",
     _org_detail, route="/organizations", shell=ADMIN, api="/api/admin/organizations")


def _org_edit(r, ctx):
    open_row(r)
    edit = r.page.get_by_role("button", name="수정")
    if not edit.count():
        stop("상세에 «수정» 이 없다")
    edit.first.click()
    r.settle(900)
    box = r.page.locator('[role="dialog"] input').first
    before = box.input_value()
    box.fill(before + " ")
    r.settle(400)
    r.rec.reset()
    save = r.page.get_by_role("button", name="저장")
    if save.count():
        save.first.click()
        r.settle(1800)
    calls = [c for c in r.rec.calls if c["method"] == "PATCH"]
    return {"ui_action": "상세에서 «수정» 으로 이름을 고친다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "본문 «%s»" % r.main_text(90),
            "failed": None if calls else "저장했는데 PATCH 가 없었다"}


flow("FF-0528", "admin_organizations", "edit",
     "상세에서 '수정'으로 조직 이름을 바꾼다(변경된 필드만 PATCH)",
     _org_edit, route="/organizations", shell=ADMIN, api="/api/admin/organizations")


def _org_suspend_confirm(r, ctx):
    # 취소하고 나면 **아무것도 안 바뀐 것**이 계약이라, 지금 그 조직의 이름과 상태를
    # 적어 둔다 — 뒤에서 새로 읽어 같은 자리에 같은 상태가 있는지 본다.
    first = r.page.locator("table tbody tr").first
    row_text = " ".join((first.inner_text() or "").split()) if first.count() else ""
    org_name = row_text.split(" ")[0] if row_text else ""
    status = "미사용" if "미사용" in row_text else ("사용 중" if "사용 중" in row_text else "")
    open_row(r)
    for name in ("비활성화", "활성화"):
        button = r.page.get_by_role("button", name=name)
        if not button.count():
            menu = r.page.get_by_label("더 보기")
            if menu.count():
                menu.first.click()
                r.settle(500)
                button = r.page.get_by_role("menuitem", name=name)
        if button.count():
            r.rec.reset()
            button.first.click()
            r.settle(900)
            text = dialog_text(r, 220)
            cancel = r.page.get_by_role("button", name="취소")
            if cancel.count():
                cancel.first.click()
                r.settle(500)
            writes = [c for c in r.rec.calls if c["method"] in ("POST", "PATCH")]
            return {"ui_action": "«%s» 를 누르고 확인 문구를 읽은 뒤 취소한다" % name,
                    "observed": {"confirm": text, "writes_before_confirm": len(writes),
                                 "row": org_name, "status_before": status},
                    "rendered": "확인 문구 «%s»" % text,
                    "cross": ({"row": org_name, "expect": status} if (org_name and status) else {}),
                    "failed": None if (name == "활성화" or (text and not writes))
                              else "확인 문구가 없거나 확인 전에 이미 보냈다"}
    stop("활성/비활성 동작을 찾지 못했다")


flow("FF-0529", "admin_organizations", "status_change", "조직을 비활성화하거나 다시 활성화한다",
     _org_suspend_confirm, route="/organizations", shell=ADMIN, server=False,
     cross=("/organizations", ADMIN))
flow("FF-0530", "admin_organizations", "modal_action",
     "비활성화 전 '소속 사용자 N명이 즉시 로그아웃된다' 확인 대화를 띄운다",
     _org_suspend_confirm, route="/organizations", shell=ADMIN, server=False)


def _detail_link(name: str, href_part: str):
    def _act(r, ctx):
        open_row(r)
        target = r.page.get_by_role("button", name=name)
        if not target.count():
            target = r.page.get_by_role("menuitem", name=name)
        if not target.count():
            menu = r.page.get_by_label("더 보기")
            if menu.count():
                menu.first.click()
                r.settle(500)
                target = r.page.get_by_role("menuitem", name=name)
        if not target.count():
            stop("«%s» 를 찾지 못했다" % name)
        target.first.click()
        r.settle(1600)
        return {"ui_action": "«%s» 를 누른다" % name,
                "url_state": "→ %s" % r.hash_of(),
                "rendered": "본문 «%s»" % r.main_text(90),
                "failed": None if href_part in r.hash_of()
                          else "%s 로 안 갔다: %s" % (href_part, r.hash_of())}
    return _act


flow("FF-0531", "admin_organizations", "navigation", "'조직도에서 보기'로 #/org-tree 로 이동한다",
     _detail_link("조직도에서 보기", "org-tree"), route="/organizations", shell=ADMIN,
     server=False)
flow("FF-0532", "admin_organizations", "deep_link",
     "'감사 로그에서 보기'로 이 조직의 변경 이력으로 딥링크한다",
     _detail_link("감사 로그에서 보기", "/audit"), route="/organizations", shell=ADMIN,
     api="/api/admin/audit")


def _overflow_in_detail(r, ctx):
    open_row(r)
    menu = r.page.get_by_label("더 보기")
    if not menu.count():
        stop("상세에 넘침 메뉴가 없다")
    menu.first.click()
    r.settle(600)
    items = r.page.get_by_role("menuitem")
    labels = [" ".join((items.nth(i).inner_text() or "").split())
              for i in range(items.count())]
    r.press("Escape")
    return {"ui_action": "상세 하단 넘침 메뉴를 연다",
            "observed": {"items": labels},
            "rendered": "메뉴 %s" % labels,
            "failed": None if labels else "넘침 메뉴가 비었다"}


flow("FF-0533", "admin_organizations", "overflow_action",
     "확인 대화가 붙은 위험 액션·저빈도 액션은 상세 하단 넘침 메뉴로 내려간다",
     _overflow_in_detail, route="/organizations", shell=ADMIN, server=False)


def _no_saved_views(r, ctx):
    """저장된 뷰는 **여기 없는 것이 계약이다** (B11). 있으면 그것이 결함이다."""
    in_panel = r.page.locator(PANEL).get_by_role("button", name="저장된 뷰").count()
    in_page = r.page.get_by_role("button", name="저장된 뷰").count()
    copy_link = r.page.locator(PANEL).get_by_role("button", name="링크 복사").count()
    return {"ui_action": "상세 판에 저장된 뷰가 있는지 본다",
            "frontend_state": "inSplitView=true",
            "observed": {"saved_views_in_panel": in_panel, "saved_views_in_page": in_page,
                         "copy_link_in_panel": copy_link},
            "rendered": "상세 판의 저장된 뷰 %d개 · 링크 복사 %d개" % (in_panel, copy_link),
            "failed": None if in_panel == 0
                      else "분할 뷰의 상세 판이 저장된 뷰를 그렸다"}


flow("FF-0534", "admin_organizations", "settings_apply",
     "지금 필터 조합을 저장된 뷰로 저장·적용·삭제하고 링크를 복사한다 "
     "— 분할 뷰의 상세 판에는 **두지 않는다**",
     _no_saved_views, route="/organizations", shell=ADMIN, server=False)

flow("FF-0535", "admin_organizations", "refresh",
     "목록 조회 실패 시 ErrorState의 '다시 시도'로 재조회한다",
     retry_from_error("/api/admin/organizations", "조직 목록"),
     route="/organizations", shell=ADMIN, api="/api/admin/organizations")

flow("FF-0536", "admin_organizations", "permission_state",
     "admin·system_admin만 진입 가능하고 추가·수정·상태 변경 버튼은 WRITE_ROLES에만 보인다",
     blocked_route("/organizations", role="user", shell=ADMIN),
     route="/organizations", shell=ADMIN, server=False)


def _tree_search(r, ctx):
    box = r.page.locator(TREE + ' input[aria-label*="검색"]')
    if not box.count():
        stop("트리 검색 상자가 없다")
    before = r.page.locator(TREE + ' [role="treeitem"]').count()
    box.first.fill("플랫폼개발")
    r.settle(1000)
    after = r.page.locator(TREE + ' [role="treeitem"]').count()
    return {"ui_action": "트리 검색에 «플랫폼개발» 을 넣는다",
            "frontend_state": "pruneTree — 맞는 마디와 그 조상만 남는다",
            "observed": {"nodes": {"before": before, "after": after}},
            "rendered": "마디 %d개 → %d개" % (before, after),
            "failed": None if after < before else "걸렀는데 마디가 안 줄었다"}


flow("FF-0537", "admin_organizations", "search", "왼쪽 트리에서 조직·부서 이름으로 검색한다",
     _tree_search, route="/organizations", shell=ADMIN, server=False)


def _tree_active_filter(r, ctx):
    box = r.page.locator(TREE).get_by_role("combobox", name="사용", exact=False)
    if not box.count():
        stop("트리의 «사용» 필터가 없다")
    before = r.page.locator(TREE + ' [role="treeitem"]').count()
    r.rec.reset()
    box.first.click()
    r.settle(400)
    option = r.page.get_by_role("option", name="사용", exact=False).last
    option.click()
    r.settle(1400)
    calls = r.rec.matching("/tree")
    after = r.page.locator(TREE + ' [role="treeitem"]').count()
    return {"ui_action": "트리의 «사용» 필터를 바꾼다",
            "observed": {"nodes": {"before": before, "after": after},
                         "calls": [(c["path"], c["query"][:50]) for c in calls][:2]},
            "rendered": "마디 %d개 → %d개 · 서버 요청 %d회" % (before, after, len(calls)),
            "failed": None if calls else "필터가 서버로 안 갔다"}


flow("FF-0538", "admin_organizations", "filter", "왼쪽 트리를 사용 여부로 거른다",
     _tree_active_filter, route="/organizations", shell=ADMIN,
     api="/api/admin/departments/tree")


def _pick_department(r, ctx):
    nodes = r.page.locator(TREE + ' [role="treeitem"]')
    target = None
    for i in range(nodes.count()):
        text = " ".join((nodes.nth(i).inner_text() or "").split())
        if "팀" in text and "본부" not in text:
            target = i
            break
    if target is None:
        stop("부서 마디를 못 찾았다")
    label = " ".join((nodes.nth(target).inner_text() or "").split())[:30]
    before_title = " ".join((r.page.locator(PANEL + " h2").first.inner_text() or "").split())
    nodes.nth(target).click()
    r.settle(1600)
    after_title = " ".join((r.page.locator(PANEL + " h2").first.inner_text() or "").split())
    people = " ".join((r.page.locator(PEOPLE).inner_text() or "").split())[:120]
    return {"ui_action": "트리에서 부서 «%s» 를 고른다" % label,
            "frontend_state": "screenKey=departments",
            "observed": {"panel_title": {"before": before_title, "after": after_title},
                         "people_pane": people},
            "rendered": "상세 판 «%s» → «%s» · 셋째 판 «%s»"
                        % (before_title, after_title, people),
            "failed": None if after_title != before_title
                      else "부서를 골랐는데 상세 판이 안 바뀌었다"}


flow("FF-0539", "admin_organizations", "navigation",
     "트리에서 부서 노드를 고르면 오른쪽이 '부서 관리' 패널로 갈아 끼워진다",
     _pick_department, route="/organizations", shell=ADMIN,
     api="/api/admin/departments")


def _org_compound(r, ctx):
    """이 화면의 «복합» 은 **판 두 개에 걸친다** — 왼쪽 트리의 조건과 오른쪽 표의 조건.

    분할 뷰의 조건은 한 표 안에서 겹치지 않는다. 겹치는 자리는 「트리에서 고른 것」과
    「표에서 거른 것」 사이다 — 그 둘이 서로를 덮지 않는지가 이 축의 질문이다.
    """
    before = r.rows()
    picked = r.choose("상태", "사용 중")
    narrowed = r.rows()
    box = r.page.locator(ORG_SEARCH)
    typed = ""
    if box.count():
        typed = "플랫폼"
        box.first.fill(typed)
        r.settle(1200)
    after = r.rows()
    return {"ui_action": "표의 «상태»=%s 와 트리 검색 «%s» 를 함께 건다" % (picked, typed),
            "frontend_state": "status=active & tree_q=%s" % typed,
            "observed": {"rows": {"none": before, "one": narrowed, "both": after},
                         "tree_query": typed},
            "rendered": "표 %d → %d → %d행" % (before, narrowed, after),
            "expected": {"source": "derived-check",
                         "rule": "트리 조건은 표의 조건을 덮지 않는다 — 결과가 넓어지지 않는다",
                         "expect": "both <= one <= none",
                         "got": {"none": before, "one": narrowed, "both": after}},
            "failed": None if after <= narrowed <= before
                      else "조건을 더했는데 결과가 늘었다(%d → %d → %d)"
                           % (before, narrowed, after)}


# ── 조건 다섯 축 (C11) ──────────────────────────────────────────────────────
#
# 이 화면은 **전량을 받아 화면에서 거른다**(쪽이 없다). 그래서 「쪽 초기화」의 답은
# «초기화할 쪽이 없다» 이고, 그 사실은 주소에 `page=` 가 안 붙는 것으로 확인된다.
flow("FF-1415", "admin_organizations", "filter", "복합 — 상태 × 트리 사용 여부",
     _org_compound, route="/organizations", shell=ADMIN, server=False)
flow("FF-1416", "admin_organizations", "filter",
     "조건을 바꿔도 쪽 초기화가 필요 없다 — 전량을 받아 화면에서 거른다",
     no_page_axis("상태", "사용 중"), route="/organizations", shell=ADMIN, server=False)
flow("FF-1417", "admin_organizations", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(ORG_SEARCH, "플", "플랫폼"), route="/organizations", shell=ADMIN, server=False)
flow("FF-1418", "admin_organizations", "filter",
     "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/organizations?status=active", "/organizations?status=suspended",
               shell=ADMIN),
     shell=ADMIN, api="/api/admin/organizations")
flow("FF-1419", "admin_organizations", "filter",
     "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/organizations?status=active", "/organizations?status=suspended",
                  shell=ADMIN),
     shell=ADMIN, api="/api/admin/organizations")
