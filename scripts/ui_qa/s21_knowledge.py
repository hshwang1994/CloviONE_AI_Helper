"""S21 — 문서·휴지통·게시판·제안 (W14).

읽고 쓰는 축이 티켓 말고 하나 더 있다. 문서는 **판(version)** 이 쌓이는 유일한 자료라
「고쳤다」가 「덮어썼다」가 아니라는 것을 여기서 본다. 게시판과 제안은 같은 부품을 쓰는
두 화면이라 **조건 축 하나(제안 상태)만 다르다** — 그 차이가 실제로 서버까지 가는지가
이 묶음의 질문이다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import (  # noqa: F401
    api_says, back_forward, cache_key, confirm_now, deep_link_survives_reload, dialog_says,
    first_row_text, flow, n_rows, open_dialog, open_dialogs, race, retry_from_error,
    row_at, row_name, rows_of, sort_by, stop,
)

USER = "/"


def _first_doc_id(r) -> str:
    payload = r.api_get("/api/knowledge/documents?page_size=1")
    items = (payload or {}).get("items") or []
    if not items:
        stop("문서가 한 건도 없다 — 상세를 열 자리가 없다")
    return items[0]["id"]


def _goto_doc(r):
    doc_id = _first_doc_id(r)
    r.goto("/knowledge/%s" % doc_id, shell=USER)
    return doc_id


# ═══════════════════════════════════════════════════════════════════════════
# /knowledge
# ═══════════════════════════════════════════════════════════════════════════
def _knowledge_read(r, ctx):
    """공간을 고르면 **그 공간의 문서가 화면에 도착하는가**.

    「어떤 요청을 불렀는가」로 재지 않는다 — 화면을 여는 동안 오간 요청은 엔진이 따로
    담아 두므로 act 안에서 다시 세면 언제나 0 이다.
    """
    server = r.api_get("/api/knowledge/documents?page_size=50")
    titles = [d.get("title", "") for d in ((server or {}).get("items") or [])][:12]
    text = r.main_text(1200)
    shown = [t for t in titles if t and t in text]
    tree = r.page.locator('#main-content [role="tree"], #main-content [role="treeitem"]')
    return {"ui_action": "/knowledge 를 연다 — 공간을 고르면 트리와 목록을 함께 받는다",
            "observed": {"server_titles": titles[:5], "shown": shown[:5],
                         "tree_nodes": tree.count()},
            "rendered": "서버 %d건 중 화면에 %d건 · 트리 마디 %d개"
                        % (len(titles), len(shown), tree.count()),
            "expected": {"source": "known-data",
                         "rule": "서버가 준 문서가 화면 목록에 그대로 그려진다",
                         "expect": len(titles), "got": len(shown)},
            "failed": None if shown else "서버에는 문서가 있는데 화면에 한 건도 없다"}


flow("FF-1301", "user_knowledge", "read", "공간을 고르면 그 공간의 폴더 트리와 문서 목록을 받는다",
     _knowledge_read, route="/knowledge", api="/api/knowledge/")


def _favorites_only(r, ctx):
    before = r.main_text(200)
    chip = r.in_main("button", "즐겨찾기만")
    if not chip.count():
        stop("«즐겨찾기만» 칩이 없다")
    r.rec.reset()
    chip.first.click()
    r.settle(1800)
    calls = [c for c in r.rec.calls if "/api/knowledge/documents" in c["path"]]
    query = " ".join(sorted({c["query"] for c in calls if c["query"]}))
    return {"ui_action": "«즐겨찾기만» 을 켠다",
            "frontend_state": "favorites=true",
            "observed": {"query": query, "calls": len(calls)},
            "rendered": "질의 «%s» · 본문 «%s»" % (query[:80], r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "즐겨찾기만 켜면 서버 질의에 favorites 가 실린다",
                         "expect": "favorites", "got": query},
            "failed": None if "favorite" in query
                      else "즐겨찾기만 켰는데 서버 질의에 그 축이 없다: «%s»" % query}


flow("FF-1304", "user_knowledge", "filter", "즐겨찾기만 보기로 좁힌다",
     _favorites_only, route="/knowledge", api="/api/knowledge/documents")


def _folder_scope(r, ctx):
    r.rec.reset()
    add = r.in_main("button", "폴더 추가")
    tree_nodes = r.page.locator('#main-content [role="treeitem"]')
    if tree_nodes.count():
        tree_nodes.first.click()
        r.settle(1600)
        calls = [c for c in r.rec.calls if "/api/knowledge/documents" in c["path"]]
        query = " ".join(sorted({c["query"] for c in calls if c["query"]}))
        return {"ui_action": "폴더 하나를 골라 목록을 그 아래로 좁힌다",
                "frontend_state": "folder_id 가 질의에 실린다",
                "observed": {"query": query, "folders": tree_nodes.count()},
                "rendered": "폴더 %d개 · 질의 «%s»" % (tree_nodes.count(), query[:70]),
                "expected": {"source": "derived-check",
                             "rule": "폴더를 고르면 folder_id 가 서버로 간다", "got": query},
                "failed": None if "folder" in query
                          else "폴더를 골랐는데 질의에 folder_id 가 없다"}
    return {"ui_action": "폴더 트리를 본다 — 씨앗에 폴더가 없다",
            "observed": {"treeitems": 0, "add_folder_button": add.count()},
            "rendered": "폴더 0개 · «폴더 추가» %d개 · 본문 «%s»"
                        % (add.count(), r.main_text(90)),
            "expected": {"source": "known-data",
                         "rule": "폴더가 없으면 만들 자리를 준다(좁힐 대상이 없는 것이 맞다)",
                         "expect": ">=1 «폴더 추가»", "got": add.count()},
            "failed": None if add.count() else "폴더도 없고 만들 자리도 없다"}


flow("FF-1305", "user_knowledge", "filter", "폴더를 고르면 그 아래 전부로 좁힌다",
     _folder_scope, route="/knowledge", server=False)


def _create_doc(r, ctx):
    title = "S21 인수 점검 문서"
    button = r.in_main("button", "새 문서")
    if not button.count():
        stop("«새 문서» 버튼이 없다")
    button.first.click()
    r.settle(1200)
    if not open_dialogs(r):
        stop("«새 문서» 를 눌렀는데 모달이 안 떴다")
    dialog = open_dialog(r)
    box = dialog.locator("input[type=text]").first
    if not box.count():
        stop("문서 제목 칸이 없다")
    box.fill(title)
    r.settle(400)
    for label in ("추가", "만들기", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        stop("문서를 만드는 버튼이 없다")
    r.settle(2400)
    ctx["s21_doc_title"] = title
    return {"ui_action": "«새 문서» 로 «%s» 를 만든다" % title,
            "frontend_state": "POST /api/knowledge/documents",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"title": title},
            "rendered": "본문 «%s»" % r.main_text(110),
            "expected": {"source": "derived-check",
                         "rule": "만들면 그 문서가 목록이나 상세에 나타난다", "expect": title},
            "cross": {"needle": title}}


flow("FF-1307", "user_knowledge", "create", "문서를 만든다",
     _create_doc, route="/knowledge", api="/api/knowledge/documents",
     cross=("/knowledge", "/"))


def _open_doc(r, ctx):
    before = r.hash_of()
    link = r.page.locator('#main-content a[href*="#/knowledge/"]')
    if not link.count():
        link = r.in_main("button", "문서 0")
    if not link.count():
        stop("문서 줄을 못 찾았다")
    link.first.click()
    r.settle(2200)
    after = r.hash_of()
    return {"ui_action": "문서 줄을 눌러 상세로 간다",
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "본문 «%s»" % r.main_text(110),
            "failed": None if "/knowledge/" in after and after != before
                      else "문서 줄을 눌렀는데 상세로 안 갔다: %s" % after}


flow("FF-1308", "user_knowledge", "navigation", "문서 줄을 눌러 상세로 간다",
     _open_doc, route="/knowledge", api="/api/knowledge/documents/")


def _space_scope_denied(r, ctx):
    """**권한 밖 공간은 목록에도 상세에도 없다.** 서버에 직접 물어 본다."""
    doc_id = _first_doc_id(r)
    got = r.as_role("user", "/me", "/", lambda p: p.evaluate(
        """async ([docId]) => {
             const list = await fetch('/api/knowledge/documents?page_size=50',
                                      {credentials: 'same-origin'});
             const body = list.ok ? await list.text() : '';
             const one = await fetch('/api/knowledge/documents/' + docId,
                                     {credentials: 'same-origin'});
             return {list_status: list.status, has_doc: body.includes(docId),
                     detail_status: one.status};
           }""", [doc_id]))
    consistent = (got["has_doc"] and got["detail_status"] == 200) or \
                 (not got["has_doc"] and got["detail_status"] in (403, 404))
    return {"ui_action": "일반 사용자로 문서 목록과 그 문서의 상세를 함께 부른다",
            "frontend_state": "가시성은 서버가 정한다",
            "observed": got,
            "rendered": "목록 HTTP %s · 목록에 %s · 상세 HTTP %s"
                        % (got["list_status"], "있음" if got["has_doc"] else "없음",
                           got["detail_status"]),
            "expected": {"source": "derived-check",
                         "rule": "목록에 없는 문서는 주소로도 안 열린다(둘이 같은 답을 한다)",
                         "got": got},
            "failed": None if consistent
                      else "목록에는 없는데 상세는 열린다 — 주소로 우회된다"}


flow("FF-1309", "user_knowledge", "permission_state", "범위 밖 공간은 목록에도 상세에도 없다",
     _space_scope_denied, route="/knowledge", server=False)

flow("FF-1342", "user_knowledge", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race("#main-content input[type=search], #main-content input[placeholder*='찾기']", "문서 0", "문서 1"),
     route="/knowledge", api="/api/knowledge/documents")

flow("FF-1343", "user_knowledge", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/knowledge?q=문서 01", "/knowledge?q=문서 02"),
     api="/api/knowledge/documents")


# ═══════════════════════════════════════════════════════════════════════════
# /knowledge/:id
# ═══════════════════════════════════════════════════════════════════════════
def _doc_read(r, ctx):
    doc_id = _goto_doc(r)
    ctx["doc_id"] = doc_id
    tabs = r.page.get_by_role("tab")
    names = [" ".join((tabs.nth(i).inner_text() or "").split()) for i in range(tabs.count())]
    body = r.page.locator("#main-content textarea")
    return {"ui_action": "문서 상세를 연다",
            "observed": {"tabs": names, "editors": body.count(), "id": doc_id},
            "rendered": "탭 %s · 편집기 %d개 · 본문 «%s»" % (names, body.count(), r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "본문과 판 이력 탭을 함께 그린다", "got": names},
            "failed": None if names else "문서 상세에 탭이 하나도 없다"}


flow("FF-1310", "user_knowledge-doc", "read", "문서 본문과 메타데이터를 받는다",
     _doc_read, api="/api/knowledge/documents/")


def _doc_edit(r, ctx):
    if "/knowledge/" not in r.hash_of():
        _goto_doc(r)
    # **이 본문은 `textarea` 가 아니다.** 블록 편집기(TipTap)라 `contenteditable` 안에
    # 글자를 넣어야 한다 — 숨은 textarea 를 채우면 편집기 상태가 안 바뀌고, 저장해도
    # 판이 안 쌓인다(그 자리에서 「판이 하나도 없다」가 나왔다).
    editor = r.page.locator('#main-content [contenteditable="true"]')
    if not editor.count():
        editor = r.page.locator("#main-content textarea:visible")
    if not editor.count():
        stop("본문 편집기가 없다")
    mark = "S21 이 본문을 한 번 고쳤습니다."
    editor.first.click()
    r.page.keyboard.press("Control+A")
    r.page.keyboard.type(mark)
    r.settle(700)
    save = r.in_main("button", "저장")
    if not save.count():
        stop("«저장» 버튼이 없다")
    save.first.click()
    r.settle(2400)
    return {"ui_action": "본문을 고치고 저장한다",
            "frontend_state": "PUT + base_version (낙관적 잠금)",
            "observed": {"typed": mark},
            "rendered": "본문 «%s»" % r.main_text(120),
            "expected": {"source": "derived-check",
                         "rule": "저장하면 새 판이 쌓이고 그 글이 서버에 남는다",
                         "expect": mark},
            "cross": {"needle": mark}}


flow("FF-1311", "user_knowledge-doc", "edit", "본문을 고치고 저장한다(낙관적 잠금)",
     _doc_edit, api="/api/knowledge/documents/", cross=("@reload", ""))


def _doc_versions(r, ctx):
    if "/knowledge/" not in r.hash_of():
        _goto_doc(r)
    tab = r.page.get_by_role("tab", name="이력", exact=False)
    if not tab.count():
        stop("«이력» 탭이 없다")
    tab.first.click()
    r.settle(1800)
    items = r.page.locator("#main-content li")
    compare = r.in_main("button", "지금 판과 비교")
    said = ""
    if compare.count() and not compare.first.is_disabled():
        r.rec.reset()
        compare.first.click()
        r.settle(2000)
        said = r.main_text(160)
    return {"ui_action": "«이력» 탭에서 판을 보고 «지금 판과 비교» 를 누른다",
            "observed": {"versions": items.count(), "compare_buttons": compare.count(),
                         "diff": said[:140]},
            "rendered": "판 %d개 · 비교 뒤 본문 «%s»" % (items.count(), (said or r.main_text(110))[:110]),
            "expected": {"source": "derived-check",
                         "rule": "판이 쌓이면 그 사이 차이를 볼 수 있다",
                         "versions": items.count()},
            "failed": None if items.count() else "본문을 저장했는데 판이 하나도 안 쌓였다"}


flow("FF-1312", "user_knowledge-doc", "read", "판 목록과 판 사이 차이를 본다",
     _doc_versions, server=False)


def _doc_restore(r, ctx):
    if "/knowledge/" not in r.hash_of():
        _goto_doc(r)
    tab = r.page.get_by_role("tab", name="이력", exact=False)
    if tab.count():
        tab.first.click()
        r.settle(1600)
    buttons = r.in_main("button", "되돌리기")
    if not buttons.count():
        stop("«되돌리기» 버튼이 없다 — 되돌릴 옛 판이 없다")
    target = None
    for i in range(buttons.count()):
        if not buttons.nth(i).is_disabled():
            target = buttons.nth(i)
            break
    if target is None:
        stop("되돌릴 수 있는 판이 없다(전부 지금 판이다)")
    target.click()
    r.settle(1000)
    asked = open_dialogs(r) > 0
    said = confirm_now(r)
    r.settle(1800)
    return {"ui_action": "옛 판으로 되돌린다",
            "frontend_state": "확인 → POST versions/{n}/restore",
            "observed": {"confirm_asked": asked, "confirm": said[:140]},
            "rendered": "확인 «%s» · 본문 «%s»" % (said[:80], r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "되돌리기는 확인을 받고, 지금 본문을 지우지 않고 판을 하나 더 쌓는다",
                         "confirm_asked": asked},
            "failed": None if asked else "되돌리기가 확인 없이 실행된다"}


flow("FF-1313", "user_knowledge-doc", "modal_action", "옛 판으로 되돌린다",
     _doc_restore, api="/api/knowledge/documents/")


def _doc_favorite(r, ctx):
    if "/knowledge/" not in r.hash_of():
        _goto_doc(r)
    button = r.in_main("button", "즐겨찾기")
    if not button.count():
        stop("«즐겨찾기» 버튼이 없다")
    before = " ".join((button.first.inner_text() or "").split())
    button.first.click()
    r.settle(1800)
    after = " ".join((r.in_main("button", "즐겨찾기").first.inner_text() or "").split())
    return {"ui_action": "즐겨찾기를 켠다(그리고 이름이 바뀌는지 본다)",
            "frontend_state": "POST favorite → 버튼 이름이 반대로",
            "observed": {"label": {"before": before, "after": after}},
            "rendered": "버튼 «%s» → «%s»" % (before, after),
            "expected": {"source": "derived-check",
                         "rule": "담으면 «즐겨찾기 해제» 로 바뀐다",
                         "before": before, "after": after},
            "failed": None if before != after
                      else "즐겨찾기를 눌렀는데 버튼이 그대로다"}


flow("FF-1314", "user_knowledge-doc", "row_action", "즐겨찾기에 담고 뺀다",
     _doc_favorite, api="/api/knowledge/documents/")


# ═══════════════════════════════════════════════════════════════════════════
# 옛 문서 주소
# ═══════════════════════════════════════════════════════════════════════════
def _legacy_redirect(r, ctx):
    body = r.main_text(220)
    where = r.hash_of()
    return {"ui_action": "옛 문서 주소로 들어간다(옮겨 오지 않은 id)",
            "frontend_state": "by-legacy 로 지금 문서를 찾는다",
            "observed": {"hash": where, "body": body},
            "rendered": "주소 «%s» · 본문 «%s»" % (where, body[:140]),
            "expected": {"source": "derived-check",
                         "rule": "못 찾으면 이유를 말하고, 찾으면 지금 문서로 데려간다",
                         "got": body[:110]},
            "failed": None if ("찾지 못했" in body or "/knowledge/" in where)
                      else "옛 주소를 열었는데 안내도 이동도 없다"}


flow("FF-1321", "user_legacy-doc-redirect", "deep_link", "옛 문서 주소를 지금 문서로 데려간다",
     _legacy_redirect, route="/team-docs/00000000-0000-0000-0000-000000000000",
     api="/api/knowledge/documents/by-legacy/")


# ═══════════════════════════════════════════════════════════════════════════
# /team-docs/trash
# ═══════════════════════════════════════════════════════════════════════════
def _trash_read(r, ctx):
    server = r.api_get("/api/trash")
    items = (server or {}).get("items") or []
    text = r.main_text(1200)
    shown = [i for i in items if (i.get("title") or "") and (i["title"] in text)]
    return {"ui_action": "휴지통을 연다",
            "observed": {"server": len(items), "rows": n_rows(r), "shown": len(shown)},
            "rendered": "서버 %d건 · 표 %d행 · 본문 «%s»"
                        % (len(items), n_rows(r), r.main_text(110)),
            "expected": {"source": "known-data",
                         "rule": "서버가 든 휴지통 항목이 화면에도 그대로 있다",
                         "expect": len(items), "got": len(shown)},
            "failed": None if (not items or shown)
                      else "서버 휴지통에는 %d건이 있는데 화면에 한 건도 없다" % len(items)}


flow("FF-0294", "user_team-docs-trash", "read", "휴지통 목록을 조회하고 15초마다 다시 받는다",
     _trash_read, route="/team-docs/trash", api="/api/trash")


def _trash_action(label: str, *, expect_confirm: bool):
    def _act(r, ctx):
        if not n_rows(r):
            stop("휴지통이 비어 있다 — 되돌리거나 지울 것이 없다")
        title = row_name(r, 0)
        before = n_rows(r)
        button = row_at(r, 0).get_by_role("button", name=label, exact=False)
        if not button.count():
            stop("행에 «%s» 가 없다" % label)
        button.first.click()
        r.settle(1000)
        asked = open_dialogs(r) > 0
        said = confirm_now(r) if asked else ""
        r.settle(1600)
        return {"ui_action": "«%s» 행의 «%s» 를 누른다" % (title, label),
                "frontend_state": ("확인 → 실행" if asked else "확인 없이 실행"),
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "confirm_asked": asked, "confirm": said[:120]},
                "rendered": "%d행 → %d행 · 본문 «%s»" % (before, n_rows(r), r.main_text(100)),
                "expected": {"source": "derived-check",
                             "rule": ("되돌릴 수 없는 동작은 확인을 받는다" if expect_confirm
                                      else "되돌릴 수 있는 동작은 바로 실행한다"),
                             "confirm_asked": asked},
                "failed": ("확인 없이 영구 삭제가 실행된다" if expect_confirm and not asked
                           else (None if n_rows(r) < before
                                 else "«%s» 를 눌렀는데 목록에 그대로 있다" % label))}
    return _act


flow("FF-0295", "user_team-docs-trash", "row_action", "행의 '복원'으로 원래 목록으로 되돌린다",
     _trash_action("복원", expect_confirm=False), route="/team-docs/trash",
     api="/api/trash/")

flow("FF-0296", "user_team-docs-trash", "row_action",
     "행의 '영구 삭제'로 지금 지운다(확인 대화상자)",
     _trash_action("영구 삭제", expect_confirm=True), route="/team-docs/trash",
     api="/api/trash/")


def _trash_select(r, ctx):
    boxes = rows_of(r).locator('input[type="checkbox"]')
    total = n_rows(r)
    if not total:
        stop("휴지통이 비어 있다")
    if not boxes.count():
        return {"ui_action": "관리할 수 있는 행만 고를 수 있는지 본다",
                "observed": {"rows": total, "checkboxes": 0},
                "rendered": "%d행 중 고를 수 있는 행 0개" % total,
                "expected": {"source": "derived-check",
                             "rule": "관리 권한이 없으면 고를 자리도 없다"},
                "failed": "행은 있는데 고를 자리가 하나도 없다"}
    boxes.first.check()
    r.settle(700)
    picked = boxes.first.is_checked()
    boxes.first.uncheck()
    return {"ui_action": "관리 가능한 행의 선택 상자를 켠다",
            "observed": {"rows": total, "checkboxes": boxes.count(), "checked": picked},
            "rendered": "%d행 중 고를 수 있는 행 %d개" % (total, boxes.count()),
            "expected": {"source": "derived-check",
                         "rule": "관리 가능한 행만 고를 수 있다",
                         "rows": total, "selectable": boxes.count()},
            "failed": None if picked else "선택 상자를 켰는데 안 켜진다"}


flow("FF-0297", "user_team-docs-trash", "row_action", "관리 가능한 행만 체크박스로 고른다",
     _trash_select, route="/team-docs/trash", server=False)


def _trash_bulk(label: str, *, expect_confirm: bool):
    def _act(r, ctx):
        boxes = rows_of(r).locator('input[type="checkbox"]')
        if not boxes.count():
            stop("고를 수 있는 행이 없다")
        before = n_rows(r)
        boxes.first.check()
        r.settle(800)
        button = r.in_main("button", label)
        if not button.count():
            stop("«%s» 버튼이 없다" % label)
        button.first.click()
        r.settle(1000)
        asked = open_dialogs(r) > 0
        said = confirm_now(r) if asked else ""
        r.settle(1800)
        return {"ui_action": "한 건을 골라 «%s» 를 누른다" % label,
                "frontend_state": ("확인 → 일괄 실행" if asked else "일괄 실행"),
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "confirm_asked": asked, "confirm": said[:120]},
                "rendered": "%d행 → %d행" % (before, n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "고른 것만 한꺼번에 처리한다",
                             "confirm_asked": asked},
                "failed": ("확인 없이 일괄 영구 삭제가 실행된다"
                           if expect_confirm and not asked
                           else (None if n_rows(r) < before
                                 else "일괄 처리했는데 목록이 그대로다"))}
    return _act


flow("FF-0298", "user_team-docs-trash", "modal_action",
     "'선택 복원'으로 고른 것을 한꺼번에 되돌린다",
     _trash_bulk("선택 복원", expect_confirm=False), route="/team-docs/trash",
     api="/api/trash/restore-bulk")

flow("FF-0299", "user_team-docs-trash", "delete",
     "'선택 영구 삭제'로 고른 것을 한꺼번에 지운다(확인 후)",
     _trash_bulk("선택 영구 삭제", expect_confirm=True), route="/team-docs/trash",
     api="/api/trash/purge-bulk")


def _trash_more(r, ctx):
    button = r.in_main("button", "더 보기")
    before = n_rows(r)
    if not button.count():
        return {"ui_action": "«휴지통 더 보기» 를 찾는다 — 상한에 안 닿았다",
                "observed": {"rows": before, "more_button": 0},
                "rendered": "%d행 · 더 보기 없음" % before,
                "expected": {"source": "derived-check",
                             "rule": "상한에 안 닿으면 더 볼 것이 없는 것이 맞다",
                             "rows": before},
                "failed": None}
    r.rec.reset()
    button.first.click()
    r.settle(1800)
    query = " ".join(sorted({c["query"] for c in r.rec.calls if "/api/trash" in c["path"]}))
    return {"ui_action": "«휴지통 더 보기» 로 상한을 늘린다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:60]),
            "expected": {"source": "derived-check",
                         "rule": "더 보기는 상한을 늘려 다시 받는다", "query": query},
            "failed": None if "limit" in query else "더 보기를 눌렀는데 상한이 안 바뀐다"}


flow("FF-0300", "user_team-docs-trash", "pagination",
     "'휴지통 더 보기'로 상한(100건)을 늘려 다시 받는다",
     _trash_more, route="/team-docs/trash", server=False)


def _trash_title_link(r, ctx):
    if not n_rows(r):
        stop("휴지통이 비어 있다")
    links = rows_of(r).locator("a")
    hrefs = [links.nth(i).get_attribute("href") for i in range(min(links.count(), 4))]
    external = [h for h in hrefs if h and h.startswith("http")]
    return {"ui_action": "휴지통 행의 제목이 어디로 가는지 본다",
            "observed": {"links": hrefs, "external": external},
            "rendered": "링크 %d개 · 바깥 링크 %d개" % (len(hrefs), len(external)),
            "expected": {"source": "derived-check",
                         "rule": "원본 주소가 있는 행만 바깥으로 나가는 링크를 준다",
                         "got": hrefs},
            "failed": None}


flow("FF-0301", "user_team-docs-trash", "navigation",
     "제목을 눌러 원본을 새 탭에서 연다(safeExternal 통과분만)",
     _trash_title_link, route="/team-docs/trash", server=False)


def _trash_permission(r, ctx):
    """`can_manage` 가 아닌 행에는 **동작 대신 안내**를 그린다."""
    text = r.as_role("user", "/team-docs/trash", "/", lambda p: " ".join(
        (p.locator("#main-content").inner_text(timeout=8000) or "").split())[:220]
        if p.locator("#main-content").count() else "(본문 없음)")
    mine = r.main_text(220)
    return {"ui_action": "같은 휴지통을 일반 사용자로 연다",
            "frontend_state": "can_manage 로 행마다 갈린다",
            "observed": {"as_system_admin": mine, "as_user": text},
            "rendered": "일반 사용자 본문 «%s»" % text[:150],
            "expected": {"source": "derived-check",
                         "rule": "권한이 없는 행에는 동작 대신 «권한 없음» 을 그린다"},
            "failed": None if ("권한" in text or "비어" in text or "없습니다" in text
                               or "본문 없음" in text)
                      else "일반 사용자에게도 관리 동작이 그대로 보인다"}


flow("FF-0302", "user_team-docs-trash", "permission_state",
     "can_manage가 아닌 행에는 액션 대신 '권한 없음'을 그린다",
     _trash_permission, route="/team-docs/trash", server=False)

flow("FF-0303", "user_team-docs-trash", "refresh", "조회 오류에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/trash", "휴지통"), route="/team-docs/trash", api="/api/trash")


# ═══════════════════════════════════════════════════════════════════════════
# /board · /ideas — 같은 부품, 조건 축 하나가 다르다
# ═══════════════════════════════════════════════════════════════════════════
def _board_read(where: str, kind: str):
    def _act(r, ctx):
        heads = r.page.locator("#main-content table thead th")
        labels = [" ".join((heads.nth(i).inner_text() or "").split())
                  for i in range(heads.count())]
        # 메타(카테고리·상태 어휘)가 도착했는지는 **칩이 그려졌는가**로 본다 — 그 칩은
        # 서버가 준 목록으로만 그린다.
        chips = r.page.locator("#main-content button")
        names = [" ".join((chips.nth(i).inner_text() or "").split())
                 for i in range(min(chips.count(), 20))]
        categories = [n for n in names if n in ("자유", "질문", "정보 공유", "맛집", "공지",
                                                "기능", "사용성", "성능", "기타")]
        return {"ui_action": "%s 를 연다" % where,
                "observed": {"columns": labels, "rows": n_rows(r),
                             "category_chips": categories},
                "rendered": "열 %s · %d행 · 분류 칩 %s" % (labels, n_rows(r), categories),
                "expected": {"source": "derived-check",
                             "rule": "목록과 메타(카테고리 어휘)를 함께 받아 그린다",
                             "chips": categories},
                "failed": (None if n_rows(r) and categories
                           else "목록이 비었거나 분류 칩이 안 그려졌다")}
    return _act


flow("FF-0224", "user_board", "read", "게시글 목록과 메타(카테고리·반응 팔레트)를 조회한다",
     _board_read("/board", "free"), route="/board", api="/api/board/")


def _board_search_clear(r, ctx):
    box = r.page.get_by_placeholder("검색")
    if not box.count():
        stop("검색 상자가 없다")
    box.first.fill("존재하지않는말zz")
    r.settle(1800)
    empty_rows = n_rows(r)
    face = r.main_text(160)
    clear = r.in_main("button", "지우기")
    if not clear.count():
        clear = r.in_main("button", "검색, 카테고리 지우기")
    if not clear.count():
        stop("«검색, 카테고리 지우기» 가 없다 — 0건에서 되돌릴 자리가 없다")
    clear.first.click()
    r.settle(1800)
    return {"ui_action": "검색으로 0건을 만들고 «지우기» 로 되돌린다",
            "frontend_state": "q 를 비운다",
            "observed": {"rows": {"filtered": empty_rows, "cleared": n_rows(r)},
                         "empty_face": face},
            "rendered": "0건 얼굴 «%s» → %d행" % (face[:70], n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "조건 때문에 0건인 상태는 되돌릴 자리를 준다",
                         "expect": ">0", "got": n_rows(r)},
            "failed": None if n_rows(r) > empty_rows
                      else "조건을 지웠는데 목록이 안 돌아온다"}


flow("FF-0228", "user_board", "filter", "검색 결과 없음에서 '검색, 카테고리 지우기'로 조건을 되돌린다",
     _board_search_clear, route="/board", api="/api/board/posts")


def _board_create(opener: str, title: str, kind_label: str):
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1300)
        if not open_dialogs(r):
            stop("«%s» 를 눌렀는데 모달이 안 떴다" % opener)
        dialog = open_dialog(r)
        box = dialog.locator("input[type=text]").first
        if not box.count():
            stop("제목 칸이 없다")
        box.fill(title)
        body = dialog.locator("textarea").first
        if body.count():
            body.fill("S21 인수 점검이 남긴 본문입니다.")
        r.settle(500)
        for label in ("등록", "저장", "추가", "올리기"):
            submit = dialog.get_by_role("button", name=label, exact=True)
            if submit.count():
                submit.first.click()
                break
        else:
            stop("올리는 버튼이 없다 — 있는 것: %s" % dialog.get_by_role("button").all_inner_texts())
        r.settle(2600)
        return {"ui_action": "«%s» 로 %s 글 «%s» 를 올린다" % (opener, kind_label, title),
                "frontend_state": "POST /api/board/posts",
                "url_state": "→ %s" % r.hash_of(),
                "observed": {"title": title},
                "rendered": "본문 «%s»" % r.main_text(120),
                "expected": {"source": "derived-check",
                             "rule": "올리면 그 글이 상세나 목록에 나타난다", "expect": title},
                "cross": {"needle": title}}
    return _act


flow("FF-0229", "user_board", "create", "'글쓰기' 모달로 새 글을 쓰고 곧바로 상세로 이동한다",
     _board_create("글쓰기", "S21 인수 점검 게시글", "자유게시판"),
     route="/board", api="/api/board/posts", cross=("/board", "/"))


def _attachment_slot(opener: str):
    """첨부 자리 — **파일을 실제로 올리지는 않는다**(이 회차는 자리와 계약만 본다)."""
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1300)
        dialog = open_dialog(r)
        files = r.page.locator('input[type="file"]')
        # **닫기 전에 세어 둔다.** 로케이터는 게을러서, 모달을 닫은 뒤에 `count()` 를
        # 부르면 0 이 나온다 — 그러면 「첨부 자리가 없다」가 되는데 방금 그 자리의
        # accept 값을 읽은 참이다.
        count = files.count()
        accept = files.first.get_attribute("accept") if count else ""
        multiple = files.first.get_attribute("multiple") if count else None
        text = dialog_says(r, 240)
        r.dismiss_overlays()
        return {"ui_action": "글쓰기 모달의 첨부 자리를 본다",
                "observed": {"file_inputs": count, "accept": accept,
                             "multiple": multiple is not None},
                "rendered": "파일 칸 %d개 · accept «%s» · 여러 개 %s"
                            % (count, accept, multiple is not None),
                "expected": {"source": "derived-check",
                             "rule": "이미지·PDF 를 여러 개 고를 수 있는 자리가 있다",
                             "accept": accept, "dialog": text[:120]},
                "failed": None if count else "글쓰기 모달에 첨부 자리가 없다"}
    return _act


flow("FF-0230", "user_board", "attachment",
     "이미지·PDF 최대 5개(각 10MB)를 골라 글 저장 뒤 순차 업로드한다",
     _attachment_slot("글쓰기"), route="/board", server=False)


def _board_validation(opener: str):
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1300)
        dialog = open_dialog(r)
        r.rec.reset()
        for label in ("등록", "저장", "추가", "올리기"):
            submit = dialog.get_by_role("button", name=label, exact=True)
            if submit.count():
                blocked = submit.first.is_disabled()
                if not blocked:
                    submit.first.click()
                    r.settle(1400)
                break
        else:
            r.dismiss_overlays()
            stop("올리는 버튼이 없다")
        sent = [c for c in r.rec.calls if c["method"] == "POST"]
        said = r.main_text(140)
        r.dismiss_overlays()
        return {"ui_action": "제목을 비운 채 올리려 한다",
                "observed": {"submit_disabled": blocked, "post_calls": len(sent)},
                "rendered": "제출 버튼 %s · POST %d건 · 안내 «%s»"
                            % ("잠김" if blocked else "열림", len(sent), said[:80]),
                "expected": {"source": "derived-check",
                             "rule": "제목이 비면 서버로 안 보낸다",
                             "expect": 0, "got": len(sent)},
                "failed": None if not sent else "제목이 빈 채로 POST 가 나갔다"}
    return _act


flow("FF-0231", "user_board", "form_validation",
     "제목이 비면 저장을 막고, 10MB 초과 파일은 제외하고 알린다",
     _board_validation("글쓰기"), route="/board", server=False)


def _board_dirty_close(opener: str):
    def _act(r, ctx):
        button = r.in_main("button", opener)
        if not button.count():
            stop("«%s» 버튼이 없다" % opener)
        button.first.click()
        r.settle(1300)
        dialog = open_dialog(r)
        box = dialog.locator("input[type=text]").first
        if not box.count():
            stop("제목 칸이 없다")
        box.fill("S21 이 쓰다 만 글")
        r.settle(500)
        r.page.keyboard.press("Escape")
        r.settle(1000)
        said = dialog_says(r, 200)
        asked = "저장되지 않았습니다" in said or "버리" in said or "닫을까요" in said
        r.dismiss_overlays()
        return {"ui_action": "제목을 적다 말고 Esc 로 닫으려 한다",
                "frontend_state": "dirty=true",
                "observed": {"confirm_asked": asked, "text": said[:150]},
                "rendered": "확인 «%s»" % said[:110],
                "expected": {"source": "derived-check",
                             "rule": "적던 것이 있으면 닫기 전에 확인을 받는다",
                             "confirm_asked": asked},
                "failed": None if asked else "적던 채로 닫는데 아무것도 안 묻는다"}
    return _act


flow("FF-0232", "user_board", "modal_action",
     "입력한 내용이 있으면 Esc·바깥클릭·X·취소 모두에서 확인을 받는다",
     _board_dirty_close("글쓰기"), route="/board", server=False)


def _open_post(r, ctx):
    before = r.hash_of()
    if not n_rows(r):
        stop("게시글이 없다")
    title = row_name(r, 0)
    # 행의 **제목 칸**을 누른다 — 행 안의 첫 «보이는» 요소가 선택 상자일 때가 있고,
    # 그것을 누르면 상세가 안 열린다.
    cell = row_at(r, 0).locator("td").first
    link = cell.locator("a:visible, button:visible")
    (link.first if link.count() else cell).click()
    r.settle(2200)
    after = r.hash_of()
    return {"ui_action": "«%s» 행을 눌러 상세로 간다" % title,
            "url_state": "%s → %s" % (before, after),
            "observed": {"hash": after},
            "rendered": "본문 «%s»" % r.main_text(120),
            "failed": None if "/board/" in after and after != before
                      else "행을 눌렀는데 상세로 안 갔다: %s" % after}


flow("FF-0233", "user_board", "navigation", "표의 행을 눌러 게시글 상세로 간다",
     _open_post, route="/board", api="/api/board/posts/")

flow("FF-0234", "user_board", "deep_link",
     "검색·카테고리·정렬을 주소에 실어 뒤로가기·공유에도 유지한다",
     deep_link_survives_reload("/board?category=공지&sort=views", "category="),
     api="/api/board/posts")

flow("FF-0235", "user_board", "refresh", "목록 오류에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/board/posts", "게시글 목록"), route="/board",
     api="/api/board/posts")


def _compound_filter(r, ctx):
    box = r.page.get_by_placeholder("검색")
    if not box.count():
        stop("검색 상자가 없다")
    box.first.fill("게시글")
    r.settle(1800)
    only_search = n_rows(r)
    chip = r.in_main("button", "공지")
    if not chip.count():
        stop("카테고리 칩이 없다")
    r.rec.reset()
    chip.first.click()
    r.settle(1800)
    both = n_rows(r)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/board/posts" in c["path"] and c["query"]}))
    return {"ui_action": "검색어 «게시글» 위에 카테고리 «공지» 를 더 건다",
            "frontend_state": "q + category",
            "observed": {"rows": {"search_only": only_search, "both": both},
                         "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (only_search, both, query[:90]),
            "expected": {"source": "derived-check",
                         "rule": "조건을 더하면 좁아지기만 한다(늘어나면 실패)",
                         "search_only": only_search, "both": both},
            "failed": None if both <= only_search
                      else "조건을 더했는데 결과가 늘었다(%d → %d)" % (only_search, both)}


flow("FF-1346", "user_board", "filter", "복합 — 검색어 × 카테고리",
     _compound_filter, route="/board", api="/api/board/posts")

flow("FF-1347", "user_board", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race("#main-content input[type=search], #main-content input[placeholder*='검색']", "게시글 0", "게시글 1"),
     route="/board", api="/api/board/posts")

flow("FF-1348", "user_board", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/board?category=공지", "/board?category=자유"), api="/api/board/posts")

flow("FF-1349", "user_board", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/board?category=공지", "/board?category=자유"), api="/api/board/posts")


# ── /ideas ────────────────────────────────────────────────────────────────
flow("FF-0236", "user_ideas", "read", "제안 목록과 제안용 메타(카테고리·상태 목록)를 조회한다",
     _board_read("/ideas", "idea"), route="/ideas", api="/api/board/")


def _ideas_search(r, ctx):
    box = r.page.get_by_placeholder("검색")
    if not box.count():
        stop("검색 상자가 없다")
    before = n_rows(r)
    r.rec.reset()
    box.first.fill("제안")
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/board/posts" in c["path"] and c["query"]}))
    return {"ui_action": "«제안» 으로 검색한다",
            "frontend_state": "q 가 서버로 간다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:90]),
            "expected": {"source": "derived-check",
                         "rule": "검색어는 서버 질의에 실린다", "got": query},
            "failed": None if "q=" in query else "검색했는데 서버 질의에 q 가 없다"}


flow("FF-0237", "user_ideas", "search", "제목·내용·작성자 검색",
     _ideas_search, route="/ideas", api="/api/board/posts")


def _ideas_sort(r, ctx):
    before = first_row_text(r)
    box = r.page.get_by_role("combobox").last
    if not box.count():
        stop("정렬 선택기가 없다")
    current = " ".join((box.inner_text() or "").split())
    box.click()
    r.settle(600)
    options = r.page.get_by_role("option")
    picked = ""
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label and label != current:
            picked = label
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
        stop("정렬 선택기에 다른 값이 없다")
    r.settle(1800)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/board/posts" in c["path"] and c["query"]}))
    return {"ui_action": "정렬을 «%s» → «%s» 로 바꾼다" % (current, picked),
            "frontend_state": "sort 가 서버로 간다",
            "observed": {"first_row": {"before": before, "after": first_row_text(r)},
                         "query": query},
            "rendered": "첫 행 «%s» → «%s»" % (before[:40], first_row_text(r)[:40]),
            "expected": {"source": "derived-check",
                         "rule": "정렬을 바꾸면 질의의 sort 가 바뀌거나 첫 행이 바뀐다",
                         "query": query},
            "failed": None if ("sort" in query or first_row_text(r) != before)
                      else "정렬을 바꿨는데 질의도 첫 행도 그대로다"}


flow("FF-0238", "user_ideas", "sort", "공감순(기본)·최신순·조회순 정렬",
     _ideas_sort, route="/ideas", api="/api/board/posts")


def _chip_filter(chip: str, axis: str):
    def _act(r, ctx):
        before = n_rows(r)
        button = r.in_main("button", chip)
        if not button.count():
            stop("«%s» 칩이 없다" % chip)
        r.rec.reset()
        button.first.click()
        r.settle(1800)
        query = " ".join(sorted({c["query"] for c in r.rec.calls
                                 if "/api/board/posts" in c["path"] and c["query"]}))
        return {"ui_action": "«%s» 칩을 눌러 좁힌다" % chip,
                "frontend_state": "%s 가 서버로 간다" % axis,
                "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
                "rendered": "%d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:90]),
                "expected": {"source": "derived-check",
                             "rule": "칩을 누르면 그 축이 서버 질의에 실린다",
                             "axis": axis, "got": query},
                "failed": None if axis in query
                          else "«%s» 를 눌렀는데 질의에 %s 가 없다: «%s»" % (chip, axis, query)}
    return _act


flow("FF-0239", "user_ideas", "filter", "카테고리 칩으로 좁힌다",
     _chip_filter("기능", "category"), route="/ideas", api="/api/board/posts")

flow("FF-0240", "user_ideas", "filter",
     "제안 상태 칩(서버가 준 statuses)으로 좁힌다 — 자유게시판에는 없는 축",
     _chip_filter("검토중", "status"), route="/ideas", api="/api/board/posts")


def _ideas_clear(r, ctx):
    r.in_main("button", "기능").first.click()
    r.settle(1400)
    status = r.in_main("button", "검토중")
    if status.count():
        status.first.click()
        r.settle(1400)
    # 「지우기」는 **0건 얼굴의 CTA** 다 — 결과가 남아 있으면 그 자리가 없는 것이 맞다.
    # 그래서 조건 위에 검색어를 하나 더 얹어 0건으로 만든 뒤 되돌린다.
    box = r.page.get_by_placeholder("검색")
    if box.count():
        box.first.fill("존재하지않는말zz")
        r.settle(1800)
    narrowed = r.hash_of()
    clear = r.in_main("button", "지우기")
    if not clear.count():
        stop("0건인데 «검색, 카테고리 지우기» 가 없다")
    clear.first.click()
    r.settle(1800)
    after = r.hash_of()
    return {"ui_action": "카테고리와 상태를 걸고 «지우기» 를 누른다",
            "url_state": "%s → %s" % (narrowed, after),
            "observed": {"hash": {"narrowed": narrowed, "cleared": after},
                         "rows": n_rows(r)},
            "rendered": "주소 «%s» → «%s»" % (narrowed[:50], after[:50]),
            "expected": {"source": "derived-check",
                         "rule": "«지우기» 는 카테고리뿐 아니라 상태까지 함께 되돌린다",
                         "got": after},
            "failed": None if "status" not in after and "category" not in after
                      else "지웠는데 조건이 주소에 남아 있다: %s" % after}


flow("FF-0241", "user_ideas", "filter", "'검색, 카테고리 지우기'로 상태까지 함께 되돌린다",
     _ideas_clear, route="/ideas", api="/api/board/posts")

flow("FF-0242", "user_ideas", "create", "'제안하기' 모달로 kind=idea 글을 만든다",
     _board_create("제안하기", "S21 인수 점검 제안", "제안"),
     route="/ideas", api="/api/board/posts", cross=("/ideas", "/"))

flow("FF-0243", "user_ideas", "attachment", "제안에도 이미지·PDF를 붙인다(생성 뒤 순차 업로드)",
     _attachment_slot("제안하기"), route="/ideas", server=False)

flow("FF-0244", "user_ideas", "form_validation", "제목 필수·파일 크기 초과 제외",
     _board_validation("제안하기"), route="/ideas", server=False)

flow("FF-0245", "user_ideas", "modal_action", "작성 중 내용이 있으면 닫기 전에 확인",
     _board_dirty_close("제안하기"), route="/ideas", server=False)

flow("FF-0246", "user_ideas", "navigation", "행을 눌러 /board/:id 상세로 간다(상세는 두 게시판 공용)",
     _open_post, route="/ideas", api="/api/board/posts/")

flow("FF-0247", "user_ideas", "deep_link", "검색·카테고리·정렬·상태를 주소에 싣는다",
     deep_link_survives_reload("/ideas?category=기능&status=검토중", "category="),
     api="/api/board/posts")

flow("FF-0248", "user_ideas", "refresh", "목록 오류에서 '다시 시도'",
     retry_from_error("/api/board/posts", "제안 목록"), route="/ideas",
     api="/api/board/posts")
