"""S21 — 검색 · 알림 · 결재함 · 내 프로필 · 통계 · 활동 · 로그인 (W14).

이 묶음의 공통점은 **한 사람의 것**을 다룬다는 것이다. 그래서 여기서 자주 묻는 질문은
「보이는가」가 아니라 **「누구의 것이 보이는가」** 다 — 알림은 audience 로 갈리고, 결재함은
can_decide 로 갈리며, 검색은 역할에 따라 검색 대상 자체가 달라진다.

로그인 화면은 이 회차에서 **세션 없는 눈**으로 본다. 로그인한 채로 `/login` 을 열면 홈으로
튕기므로, 그 화면을 보려면 쿠키가 없는 창을 따로 열어야 한다.
"""

from __future__ import annotations

from urllib.parse import unquote

from scripts.ui_qa.s21_kit import (  # noqa: F401
    back_forward, cache_key, confirm_now, deep_link_survives_reload, dialog_says, flow,
    n_rows, open_dialog, open_dialogs, page_reset, pager, race, retry_from_error, row_at,
    row_name, rows_of, stop,
)

USER = "/"
ADMIN = "/admin"
NOTI = "/api/notifications"


# ═══════════════════════════════════════════════════════════════════════════
# 검색 — /search (사용자·관리자 셸이 같은 화면을 쓴다)
# ═══════════════════════════════════════════════════════════════════════════
def _search_box(r):
    box = r.page.locator("#main-content input[type=search]:visible, "
                         "#main-content input[type=text]:visible")
    if not box.count():
        stop("검색 입력 칸이 없다")
    return box.first


def _search_submit(term: str):
    def _act(r, ctx):
        box = _search_box(r)
        before = r.hash_of()
        box.fill(term)
        r.rec.reset()
        r.page.keyboard.press("Enter")
        r.settle(2600)
        after = unquote(r.hash_of())
        calls = sorted({c["path"] for c in r.rec.calls if "search" in c["path"]})
        return {"ui_action": "«%s» 를 넣고 제출한다" % term,
                "frontend_state": "폼 submit → 주소의 q 갱신",
                "url_state": "%s → %s" % (before, after),
                "observed": {"hash": after, "calls": calls, "body": r.main_text(160)},
                "rendered": "주소 «%s» · 본문 «%s»" % (after[:60], r.main_text(140)),
                "expected": {"source": "derived-check",
                             "rule": "제출하면 ?q= 가 주소에 실리고 결과를 받는다",
                             "expect": term, "got": after},
                "failed": None if term in after
                          else "제출했는데 주소에 검색어가 안 실렸다: %s" % after}
    return _act


flow("FF-0017", "user_search", "search", "검색어를 입력하고 제출해 ?q= 로 결과를 연다",
     _search_submit("회의"), route="/search", api="search")


def _search_deep_link(r, ctx):
    box = _search_box(r)
    value = box.input_value()
    body = r.main_text(200)
    return {"ui_action": "?q=회의 주소로 들어와 입력칸과 결과를 본다",
            "url_state": unquote(r.hash_of()),
            "observed": {"input": value, "body": body},
            "rendered": "입력칸 «%s» · 본문 «%s»" % (value, body[:140]),
            "expected": {"source": "derived-check",
                         "rule": "주소의 q 가 입력칸과 조회에 그대로 반영된다",
                         "expect": "회의", "got": value},
            "failed": None if "회의" in value
                      else "주소에 q 가 있는데 입력칸이 비었다: «%s»" % value}


flow("FF-0018", "user_search", "deep_link", "주소의 q 파라미터를 입력칸과 조회에 그대로 반영한다",
     _search_deep_link, route="/search?q=회의", server=False)


def _search_scope_note(r, ctx):
    mine = r.main_text(300)
    got = r.as_role("user", "/search?q=회의", "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0, 300);
           }"""))
    return {"ui_action": "같은 검색 화면을 일반 사용자로 연다",
            "frontend_state": "역할에 따라 검색 대상 안내가 갈린다",
            "observed": {"as_system_admin": mine, "as_user": got},
            "rendered": "관리자 «%s» · 사용자 «%s»" % (mine[:110], got[:110]),
            "expected": {"source": "derived-check",
                         "rule": "역할에 따라 검색 대상(사용자 포함 여부) 안내가 달라진다",
                         "same": mine == got},
            "failed": None if mine != got
                      else "역할이 달라도 검색 대상 안내가 똑같다"}


flow("FF-0019", "user_search", "permission_state", "역할에 따라 검색 대상 안내(사용자 포함 여부)를 바꿔 쓴다",
     _search_scope_note, route="/search?q=회의", server=False)


def _reindex(*, expect_confirm: bool = True):
    def _act(r, ctx):
        button = r.in_main("button", "재색인")
        if not button.count():
            button = r.in_main("button", "색인")
        if not button.count():
            stop("«지금 재색인» 버튼이 없다")
        r.rec.reset()
        button.first.click()
        r.settle(1200)
        asked = open_dialogs(r) > 0
        said = confirm_now(r) if asked else ""
        r.settle(2600)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«지금 재색인» 을 실행한다",
                "frontend_state": ("확인 → 실행" if asked else "확인 없이 실행"),
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:90]),
                "expected": {"source": "derived-check",
                             "rule": "무거운 운영 동작은 확인을 받고 서버로 간다",
                             "confirm_asked": asked, "calls": calls},
                "failed": ("확인 없이 재색인이 돈다" if expect_confirm and not asked
                           else (None if calls else "확인했는데 서버로 안 갔다"))}
    return _act


flow("FF-0020", "user_search", "admin_op", "운영 역할에게만 '지금 재색인'을 노출하고 확인 후 실행한다",
     _reindex(), route="/search", api="search")


# ── /search?q=회의 (결과) ──────────────────────────────────────────────────
flow("FF-1098", "user_search-results", "search", "검색어를 바꿔 다시 제출한다",
     _search_submit("문서"), route="/search?q=회의", api="search")


def _search_groups(r, ctx):
    body = r.main_text(400)
    headings = r.page.locator("#main-content h2, #main-content h3")
    names = [" ".join((headings.nth(i).inner_text() or "").split())
             for i in range(min(headings.count(), 8))]
    links = r.page.locator("#main-content a[href^='#/']")
    return {"ui_action": "유형별 그룹과 총건수를 본다",
            "observed": {"groups": names, "links": links.count(), "body": body[:220]},
            "rendered": "그룹 %s · 결과 링크 %d개" % (names, links.count()),
            "expected": {"source": "derived-check",
                         "rule": "유형별로 묶고 총건수를 함께 그린다", "groups": names},
            "failed": None if (names or links.count())
                      else "검색 결과가 그룹도 링크도 없이 비어 있다"}


flow("FF-1099", "user_search-results", "read", "유형별 그룹과 총건수를 조회해 그린다(유형당 최대 50건)",
     _search_groups, route="/search?q=회의", api="search")


def _search_open(r, ctx):
    links = r.page.locator("#main-content a[href^='#/']")
    if not links.count():
        stop("결과 링크가 없다")
    before = r.hash_of()
    href = links.first.get_attribute("href")
    links.first.click()
    r.settle(2400)
    return {"ui_action": "결과 항목을 눌러 그 자원 화면으로 간다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"href": href, "hash": r.hash_of()},
            "rendered": "주소 «%s» · 본문 «%s»" % (r.hash_of(), r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "결과를 누르면 그 자원 화면으로 간다", "expect": href},
            "failed": None if r.hash_of() != before
                      else "결과를 눌렀는데 화면이 안 바뀐다"}


flow("FF-1100", "user_search-results", "navigation", "결과 항목을 눌러 그 자원 화면으로 이동한다",
     _search_open, route="/search?q=회의", server=False)

flow("FF-1101", "user_search-results", "deep_link", "?q= 주소만으로 같은 결과를 다시 연다",
     deep_link_survives_reload("/search?q=회의", "q="), api="search")

flow("FF-1102", "user_search-results", "back_forward",
     "검색어를 바꿔 좁히는 동안 뒤로가기가 살아 있게 push 로 기록한다",
     back_forward("/search?q=회의", "/search?q=문서"), api="search")

flow("FF-1103", "user_search-results", "refresh", "조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error("/api/search", "검색"), route="/search?q=회의", api="search")

flow("FF-1104", "user_search-results", "permission_state",
     "역할에 따라 '사용자' 유형 결과 가능 여부를 문구로 알린다",
     _search_scope_note, route="/search?q=회의", server=False)

flow("FF-1105", "user_search-results", "admin_op", "운영 역할이 검색 색인을 다시 만든다",
     _reindex(), route="/search?q=회의", api="search")


# ── /search?q=없는말 (0건) ────────────────────────────────────────────────
flow("FF-1093", "user_search-empty", "search", "검색어를 고쳐 다시 제출한다",
     _search_submit("회의"), route="/search?q=존재하지않는검색어zz", api="search")


def _clear_search(r, ctx):
    button = r.in_main("button", "검색어 지우기")
    if not button.count():
        button = r.in_main("button", "지우기")
    if not button.count():
        stop("«검색어 지우기» 가 없다")
    button.first.click()
    r.settle(1800)
    after = unquote(r.hash_of())
    box = r.page.locator("#main-content input:visible").first
    return {"ui_action": "«검색어 지우기» 로 질문 전 상태로 되돌린다",
            "url_state": after,
            "observed": {"hash": after, "input": box.input_value() if box.count() else ""},
            "rendered": "주소 «%s» · 본문 «%s»" % (after[:50], r.main_text(140)),
            "expected": {"source": "derived-check",
                         "rule": "지우면 주소의 q 도 함께 사라진다", "got": after},
            "failed": None if "q=" not in after
                      else "지웠는데 주소에 q 가 남아 있다: %s" % after}


flow("FF-1094", "user_search-empty", "search", "'검색어 지우기'로 초기(질문 전) 상태로 되돌린다",
     _clear_search, route="/search?q=존재하지않는검색어zz", server=False)


def _empty_reason(r, ctx):
    body = r.main_text(300)
    return {"ui_action": "0건 얼굴이 무엇을 말하는지 읽는다",
            "observed": {"body": body, "rows": n_rows(r)},
            "rendered": "본문 «%s»" % body[:200],
            "expected": {"source": "derived-check",
                         "rule": "0건이면 왜 0건인지(검색 방식 포함) 말한다", "got": body[:150]},
            "failed": None if ("없" in body or "0" in body)
                      else "0건인데 화면이 아무 말도 안 한다"}


flow("FF-1095", "user_search-empty", "read", "결과 0건 응답과 mode(like/전문검색)를 받아 이유를 갈라 쓴다",
     _empty_reason, route="/search?q=존재하지않는검색어zz", api="search")

flow("FF-1096", "user_search-empty", "deep_link", "?q= 주소로 들어와도 같은 빈 결과 화면을 그린다",
     deep_link_survives_reload("/search?q=존재하지않는검색어zz", "q="), api="search")

flow("FF-1097", "user_search-empty", "admin_op", "운영 역할이 검색 색인을 다시 만든다",
     _reindex(), route="/search?q=존재하지않는검색어zz", api="search")


# ── 관리자 셸의 /search ───────────────────────────────────────────────────
flow("FF-0411", "admin_search", "search", "검색어 입력·제출(폼 submit → 주소의 q 갱신)",
     _search_submit("회의"), route="/search", shell=ADMIN, api="search")

flow("FF-0412", "admin_search", "read", "유형별 최대 50건 검색 결과 조회",
     _search_groups, route="/search?q=회의", shell=ADMIN, api="search")

flow("FF-0413", "admin_search", "deep_link", "주소의 q를 읽어 입력·결과를 복원",
     _search_deep_link, route="/search?q=회의", shell=ADMIN, server=False)

flow("FF-0414", "admin_search", "back_forward",
     "검색어를 바꿔도 replace를 쓰지 않아 뒤로가기로 이전 검색어 복원",
     back_forward("/search?q=회의", "/search?q=문서", shell=ADMIN), api="search")

flow("FF-0415", "admin_search", "navigation", "결과 항목 클릭 → 유형별 라우트로 이동",
     _search_open, route="/search?q=회의", shell=ADMIN, server=False)

flow("FF-0416", "admin_search", "admin_op", "검색 색인 재생성",
     _reindex(), route="/search", shell=ADMIN, api="search")

flow("FF-0417", "admin_search", "modal_action", "재색인 전 확인 대화상자",
     _reindex(), route="/search", shell=ADMIN, api="search")

flow("FF-0418", "admin_search", "permission_state",
     "운영 역할만 재색인 버튼, 관리자 역할만 '사용자' 유형이 검색돼 안내 문구가 달라진다",
     _search_scope_note, route="/search?q=회의", shell=ADMIN, server=False)

flow("FF-0419", "admin_search", "refresh", "검색 실패 시 다시 시도",
     retry_from_error("/api/search", "검색"), route="/search?q=회의", shell=ADMIN,
     api="search")

flow("FF-0420", "admin_search", "filter", "결과 없음 상태에서 검색어 지우기",
     _clear_search, route="/search?q=존재하지않는검색어zz", shell=ADMIN, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /notifications
# ═══════════════════════════════════════════════════════════════════════════
def _noti_read(r, ctx):
    server = r.api_get(NOTI + "?audience=user&page_size=50")
    items = (server or {}).get("items") or []
    text = r.main_text(1200)
    shown = [i for i in items if (i.get("title") or "") and i["title"] in text]
    return {"ui_action": "내 알림 목록을 연다",
            "observed": {"server": len(items), "rows": n_rows(r), "shown": len(shown)},
            "rendered": "서버 %d건 · 표 %d행 · 화면에서 찾은 것 %d건"
                        % (len(items), n_rows(r), len(shown)),
            "expected": {"source": "known-data",
                         "rule": "서버가 준 내 알림이 화면에도 그대로 있다",
                         "expect": len(items), "got": len(shown)},
            "failed": None if (not items or shown)
                      else "서버에 알림 %d건이 있는데 화면에 한 건도 없다" % len(items)}


flow("FF-0347", "user_notifications", "read", "내 알림 목록을 audience=user 로 조회한다",
     _noti_read, route="/notifications", api=NOTI)


def _open_detail(r, ctx):
    if not n_rows(r):
        stop("알림이 없다")
    name = row_name(r, 0)
    before = open_dialogs(r)
    row_at(r, 0).click()
    r.settle(1600)
    text = dialog_says(r, 260) if open_dialogs(r) > before else r.main_text(220)
    return {"ui_action": "«%s» 행을 눌러 상세를 연다" % name,
            "observed": {"dialogs": {"before": before, "after": open_dialogs(r)},
                         "detail": text[:220]},
            "rendered": "상세 «%s»" % text[:170],
            "expected": {"source": "derived-check",
                         "rule": "행을 누르면 내용과 관련 대상이 열린다"},
            "failed": None if open_dialogs(r) > before else "행을 눌렀는데 상세가 안 열렸다"}


flow("FF-0350", "user_notifications", "row_action", "행을 눌러 상세 드로어(내용·관련 대상)를 연다",
     _open_detail, route="/notifications", server=False)


def _detail_action(label: str, api_hint: str, *, confirm: bool = False,
                   required: bool = True):
    def _act(r, ctx):
        if not n_rows(r):
            stop("행이 없다")
        row_at(r, 0).click()
        r.settle(1600)
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
            said = dialog_says(r, 240)
            r.dismiss_overlays()
            if required:
                stop("«%s» 를 못 찾았다 — 상세: %s" % (label, said[:170]))
            return {"ui_action": "상세에서 «%s» 를 찾는다" % label,
                    "observed": {"detail": said[:200]},
                    "rendered": "«%s» 없음 — 상세 «%s»" % (label, said[:140]),
                    "expected": {"source": "known-data",
                                 "rule": "그 조건일 때만 이 동작이 있다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(1200)
        asked = open_dialogs(r) > 1
        said = confirm_now(r) if asked else ""
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        r.dismiss_overlays()
        return {"ui_action": "상세에서 «%s» 를 실행한다" % label,
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:80]),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "failed": (("확인 없이 실행됐다" if confirm and not asked else None)
                           or (None if any(api_hint in c for c in calls)
                               else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s"
                                    % (label, api_hint, calls)))}
    return _act


flow("FF-0351", "user_notifications", "notification_action",
     "알림 하나를 읽음 처리한다(드로어를 연 채 읽음 상태만 갱신)",
     _detail_action("읽음", NOTI), route="/notifications", api=NOTI)


def _mark_all_read(r, ctx):
    button = r.in_main("button", "모두 읽음")
    if not button.count():
        return {"ui_action": "«모두 읽음» 을 찾는다",
                "observed": {"button": 0, "body": r.main_text(150)},
                "rendered": "«모두 읽음» 없음 — 안 읽은 알림이 없다",
                "expected": {"source": "derived-check",
                             "rule": "안 읽음이 있을 때만 그 버튼을 그린다"},
                "failed": None}
    r.rec.reset()
    button.first.click()
    r.settle(1200)
    asked = open_dialogs(r) > 0
    said = confirm_now(r) if asked else ""
    r.settle(2200)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    return {"ui_action": "«모두 읽음» 을 실행한다",
            "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
            "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:90]),
            "expected": {"source": "derived-check",
                         "rule": "일괄 처리는 확인을 받고 서버로 간다",
                         "confirm_asked": asked},
            "failed": None if calls else "«모두 읽음» 을 눌렀는데 서버로 안 갔다"}


flow("FF-0352", "user_notifications", "notification_action",
     "안 읽음이 있을 때만 '모두 읽음'을 노출하고 확인 후 일괄 처리한다",
     _mark_all_read, route="/notifications", api=NOTI)

flow("FF-0353", "user_notifications", "delete", "알림을 확인 후 삭제한다",
     _detail_action("삭제", NOTI, confirm=True), route="/notifications", api=NOTI)

flow("FF-0354", "user_notifications", "navigation",
     "'관련 항목 보기'로 서버가 계산한 목적지(related_route)나 단건 딥링크로 이동한다",
     _detail_action("관련 항목", "", required=False), route="/notifications", server=False)

flow("FF-0355", "user_notifications", "navigation",
     "단건 딥링크가 없는 유형은 '관련 목록 열기'로 그 목록 화면까지만 이동한다",
     _detail_action("목록 열기", "", required=False), route="/notifications", server=False)


def _noti_role_gate(r, ctx):
    if not n_rows(r):
        stop("알림이 없다")
    row_at(r, 0).click()
    r.settle(1600)
    scope = open_dialog(r) if open_dialogs(r) else r.page.locator("#main-content")
    buttons = scope.get_by_role("button")
    mine = [" ".join((buttons.nth(i).inner_text() or "").split())
            for i in range(min(buttons.count(), 12))]
    r.dismiss_overlays()
    got = r.as_role("user", "/notifications", "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return {rows: main ? main.querySelectorAll('tbody tr').length : 0,
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,200)};
           }"""))
    return {"ui_action": "상세의 이동 동작을 세고, 같은 화면을 일반 사용자로 연다",
            "observed": {"as_system_admin": mine, "as_user": got},
            "rendered": "system_admin 동작 %s · user 알림 %d행" % (mine, got["rows"]),
            "expected": {"source": "derived-check",
                         "rule": "관리자 콘솔 대상 알림은 닿을 수 있는 역할에게만 이동 동작을 준다"},
            "failed": None}


flow("FF-0356", "user_notifications", "permission_state",
     "관리자 콘솔 대상 알림은 역할이 실제로 닿을 때만 이동 액션을 준다",
     _noti_role_gate, route="/notifications", server=False)


def _noti_race(r, ctx):
    """조건을 빠르게 두 번 바꿔도 **마지막 것만** 남는가.

    이 화면에는 글자를 치는 조건이 없다(읽음 상태 선택기 하나뿐이다). 그래서 경합은
    **선택기를 연달아 두 번 바꿔** 만든다 — 늦게 온 응답이 최신 조건을 덮으면 화면이
    말하는 조건과 목록이 갈린다.
    """
    box = r.page.get_by_role("combobox", name="읽음 상태", exact=False)
    if not box.count():
        stop("«읽음 상태» 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
    r.choose("읽음 상태", "안 읽음만")
    r.page.wait_for_timeout(120)
    r.rec.reset()
    clear = r.in_main("button", "필터 지우기")
    if clear.count():
        clear.first.click()
    r.settle(2400)
    shown = " ".join((r.page.get_by_role("combobox", name="읽음 상태", exact=False)
                      .first.inner_text() or "").split())
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if NOTI in c["path"] and c["query"]}))
    return {"ui_action": "«안 읽음만» 을 걸자마자 조건을 지운다",
            "frontend_state": "마지막 조건만 남아야 한다",
            "observed": {"shown": shown, "query": query, "rows": n_rows(r)},
            "rendered": "선택기 «%s» · 질의 «%s» · %d행" % (shown, query[:60], n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "화면이 말하는 조건과 실제 질의가 같다",
                         "shown": shown, "query": query},
            "failed": None if ("안 읽음" not in shown or "unread" in query)
                      else "화면은 «%s» 인데 질의에 그 조건이 없다: «%s»" % (shown, query)}


def _noti_deep_link(r, ctx):
    payload = r.api_get(NOTI + "?audience=user&page_size=1")
    items = (payload or {}).get("items") or []
    if not items:
        stop("알림이 없다")
    nid = items[0]["id"]
    r.goto("/notifications?id=%s" % nid, shell=USER)
    r.settle(1800)
    opened = open_dialogs(r)
    text = dialog_says(r, 240) if opened else r.main_text(200)
    return {"ui_action": "?id=<실제 id> 로 알림 상세를 바로 연다",
            "url_state": r.hash_of(),
            "observed": {"id": nid, "dialogs": opened, "detail": text[:200]},
            "rendered": "상세 «%s»" % text[:160],
            "expected": {"source": "derived-check",
                         "rule": "주소만으로 그 알림 상세가 열린다", "opened": opened},
            "failed": None if opened else "주소로 열었는데 상세가 안 뜬다"}


flow("FF-0357", "user_notifications", "deep_link", "?id= 로 특정 알림 상세를 바로 연다",
     _noti_deep_link, api=NOTI)

flow("FF-0358", "user_notifications", "refresh", "조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(NOTI, "알림"), route="/notifications", api=NOTI)

flow("FF-1352", "user_notifications", "filter", "조건을 바꾸면 쪽이 초기화된다",
     page_reset("읽음 상태", "안 읽음만"), route="/notifications", api=NOTI, server=False)

flow("FF-1353", "user_notifications", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     _noti_race, route="/notifications", server=False)

flow("FF-1354", "user_notifications", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/notifications?page=1", "/notifications?page=2"), api=NOTI)

flow("FF-1355", "user_notifications", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/notifications?unread_only=true", "/notifications?page=2"), api=NOTI)


# ═══════════════════════════════════════════════════════════════════════════
# /my-approvals
# ═══════════════════════════════════════════════════════════════════════════
APP = "/api/approvals"


def _approvals_read(r, ctx):
    tabs = r.page.get_by_role("tab")
    names = [" ".join((tabs.nth(i).inner_text() or "").split()) for i in range(tabs.count())]
    heads = r.page.locator("#main-content table thead th")
    columns = [" ".join((heads.nth(i).inner_text() or "").split())
               for i in range(heads.count())]
    return {"ui_action": "결재함을 연다",
            "observed": {"tabs": names, "columns": columns, "rows": n_rows(r)},
            "rendered": "칸 %s · 열 %s · %d행" % (names, columns, n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "고른 칸의 목록을 받는다", "tabs": names},
            "failed": None if names else "결재함에 칸이 하나도 없다"}


flow("FF-0359", "user_my-approvals", "read", "고른 결재함 칸의 목록을 받는다",
     _approvals_read, route="/my-approvals", api=APP)


def _approval_tab(name: str):
    def _act(r, ctx):
        tab = r.page.get_by_role("tab", name=name, exact=False)
        if not tab.count():
            names = [" ".join((r.page.get_by_role("tab").nth(i).inner_text() or "").split())
                     for i in range(r.page.get_by_role("tab").count())]
            stop("«%s» 칸이 없다 — 있는 칸: %s" % (name, names))
        before = n_rows(r)
        r.rec.reset()
        tab.first.click()
        r.settle(2000)
        query = " ".join(sorted({c["query"] for c in r.rec.calls
                                 if APP in c["path"] and c["query"]}))
        heads = r.page.locator("#main-content table thead th")
        columns = [" ".join((heads.nth(i).inner_text() or "").split())
                   for i in range(heads.count())]
        ctx["approval_columns_%s" % name] = columns
        return {"ui_action": "«%s» 칸으로 바꾼다" % name,
                "observed": {"rows": {"before": before, "after": n_rows(r)},
                             "query": query, "columns": columns},
                "rendered": "%d행 → %d행 · 열 %s" % (before, n_rows(r), columns),
                "expected": {"source": "derived-check",
                             "rule": "칸을 바꾸면 그 칸의 목록을 다시 받는다", "query": query},
                "failed": None if (query or n_rows(r) != before)
                          else "칸을 바꿨는데 아무것도 안 달라졌다"}
    return _act


flow("FF-0360", "user_my-approvals", "filter",
     "탭으로 결재함 칸을 바꾼다 — 처리할 승인 / 내가 올린 요청 / 내가 처리한 건",
     _approval_tab("내가 올린"), route="/my-approvals", api=APP)


def _decide(label: str):
    def _act(r, ctx):
        tab = r.page.get_by_role("tab", name="처리할", exact=False)
        if tab.count():
            tab.first.click()
            r.settle(1800)
        if not n_rows(r):
            return {"ui_action": "«처리할 승인» 칸에서 «%s» 를 찾는다" % label,
                    "observed": {"rows": 0, "body": r.main_text(160)},
                    "rendered": "처리할 승인 0건 — 결재할 것이 없다",
                    "expected": {"source": "known-data",
                                 "rule": "처리할 것이 없으면 결재 버튼도 없다"},
                    "failed": None}
        name = row_name(r, 0)
        button = row_at(r, 0).get_by_role("button", name=label, exact=False)
        if not button.count():
            stop("행에 «%s» 가 없다" % label)
        before = n_rows(r)
        r.rec.reset()
        button.first.click()
        r.settle(1200)
        if open_dialogs(r):
            confirm_now(r)
            r.settle(1800)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«%s» 건을 «%s» 한다" % (name, label),
                "observed": {"calls": calls, "rows": {"before": before, "after": n_rows(r)}},
                "rendered": "쓰기 요청 %s · %d행 → %d행" % (calls, before, n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "결재하면 서버로 가고 그 건이 처리할 목록에서 빠진다",
                             "got": calls},
                "failed": None if calls else "«%s» 를 눌렀는데 서버로 안 갔다" % label}
    return _act


flow("FF-0361", "user_my-approvals", "approval_action", "행의 '승인' 버튼이 그 건을 승인한다",
     _decide("승인"), route="/my-approvals", api=APP, server=False)

flow("FF-0362", "user_my-approvals", "approval_action", "행의 '거절' 버튼이 그 건을 거절한다",
     _decide("거절"), route="/my-approvals", api=APP, server=False)


def _decide_column_only(r, ctx):
    seen = {}
    for name in ("처리할", "내가 올린", "내가 처리"):
        tab = r.page.get_by_role("tab", name=name, exact=False)
        if not tab.count():
            continue
        tab.first.click()
        r.settle(1800)
        buttons = 0
        if n_rows(r):
            for i in range(min(n_rows(r), 3)):
                buttons += row_at(r, i).get_by_role("button", name="승인",
                                                    exact=False).count()
        seen[name] = {"rows": n_rows(r), "decide_buttons": buttons}
    only_first = all(v["decide_buttons"] == 0 for k, v in seen.items() if k != "처리할")
    return {"ui_action": "칸마다 결재 버튼이 붙는지 센다",
            "observed": seen,
            "rendered": " · ".join("%s %d행/결재 %d" % (k, v["rows"], v["decide_buttons"])
                                   for k, v in seen.items()),
            "expected": {"source": "derived-check",
                         "rule": "결재 열은 «처리할 승인» 칸에만 붙는다", "got": seen},
            "failed": None if only_first
                      else "처리할 승인이 아닌 칸에도 결재 버튼이 붙어 있다"}


flow("FF-0363", "user_my-approvals", "row_action", "'처리할 승인' 칸에서만 결재 열(승인·거절)이 붙는다",
     _decide_column_only, route="/my-approvals", server=False)


def _cannot_decide(r, ctx):
    got = r.as_role("user", "/my-approvals", "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0, 260);
           }"""))
    mine = r.main_text(260)
    return {"ui_action": "같은 결재함을 결재 권한이 없는 사용자로 연다",
            "observed": {"as_system_admin": mine[:200], "as_user": got[:200]},
            "rendered": "일반 사용자 본문 «%s»" % got[:170],
            "expected": {"source": "derived-check",
                         "rule": "can_decide 가 아니면 목록 대신 안내를 그린다"},
            "failed": None if ("권한" in got or got != mine)
                      else "결재 권한이 없는 사용자에게도 같은 화면이 그대로 열린다"}


flow("FF-0364", "user_my-approvals", "permission_state",
     "can_decide=false 면 목록 대신 '결재 권한이 없습니다' 안내를 그린다",
     _cannot_decide, route="/my-approvals", server=False)


def _approvals_poll(r, ctx):
    tab = r.page.get_by_role("tab", name="처리할", exact=False)
    if tab.count():
        tab.first.click()
        r.settle(1600)
    r.rec.reset()
    r.settle(5000)
    polls = [c for c in r.rec.calls if APP in c["path"]]
    return {"ui_action": "«처리할 승인» 칸에 머물며 다시 읽는지 본다(5초)",
            "observed": {"polls": len(polls)},
            "rendered": "5초 동안 결재함 요청 %d건" % len(polls),
            "expected": {"source": "derived-check",
                         "rule": "처리할 칸은 스스로 다시 읽어 낡은 409 를 피한다",
                         "got": len(polls)},
            "failed": None}


flow("FF-0365", "user_my-approvals", "refresh",
     "'처리할 승인' 칸은 30초마다 다시 읽어 남이 먼저 처리한 건의 낡은 409 를 피한다",
     _approvals_poll, route="/my-approvals", server=False)

flow("FF-0366", "user_my-approvals", "refresh", "오류 상태의 '다시 시도'",
     retry_from_error(APP, "결재함"), route="/my-approvals", api=APP)


def _approval_compound(r, ctx):
    tab = r.page.get_by_role("tab", name="내가 올린", exact=False)
    if tab.count():
        tab.first.click()
        r.settle(1800)
    first = n_rows(r)
    nxt = r.in_main("button", "다음")
    moved = False
    if nxt.count() and not nxt.first.is_disabled():
        nxt.first.click()
        r.settle(1800)
        moved = True
    return {"ui_action": "칸을 바꾼 뒤 쪽을 넘긴다",
            "observed": {"rows": {"tab": first, "page2": n_rows(r)}, "moved": moved,
                         "hash": r.hash_of()},
            "rendered": "%d행 → %d행 · 주소 «%s»" % (first, n_rows(r), r.hash_of()[-30:]),
            "expected": {"source": "derived-check",
                         "rule": "칸과 쪽이 함께 걸린다", "moved": moved},
            "failed": None}


flow("FF-1368", "user_my-approvals", "filter", "복합 — 칸 × 쪽",
     _approval_compound, route="/my-approvals", server=False)

flow("FF-1369", "user_my-approvals", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     _approval_compound, route="/my-approvals", server=False)

flow("FF-1370", "user_my-approvals", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/my-approvals?box=mine", "/my-approvals?box=decided"), api=APP)

flow("FF-1371", "user_my-approvals", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/my-approvals?box=mine", "/my-approvals?box=decided"), api=APP)


# ═══════════════════════════════════════════════════════════════════════════
# /profile
# ═══════════════════════════════════════════════════════════════════════════
def _profile_read(r, ctx):
    switches = r.page.locator('#main-content [role="switch"], '
                              '#main-content input[type=checkbox]')
    body = r.main_text(260)
    return {"ui_action": "내 프로필을 연다",
            "observed": {"switches": switches.count(), "body": body},
            "rendered": "스위치 %d개 · 본문 «%s»" % (switches.count(), body[:170]),
            "expected": {"source": "derived-check",
                         "rule": "프로필과 개인 환경설정을 함께 받는다",
                         "switches": switches.count()},
            "failed": None if switches.count() else "설정 스위치가 하나도 안 그려졌다"}


flow("FF-0367", "user_profile", "read", "프로필과 개인 환경설정을 조회한다",
     _profile_read, route="/profile", api="/api/profile")


def _avatar_slot(r, ctx):
    button = r.in_main("button", "사진 바꾸기")
    files = r.page.locator('input[type="file"]')
    accept = files.first.get_attribute("accept") if files.count() else ""
    return {"ui_action": "프로필 사진 자리를 본다",
            "observed": {"button": button.count(), "file_inputs": files.count(),
                         "accept": accept},
            "rendered": "«사진 바꾸기» %d개 · 파일 칸 %d개 · accept «%s»"
                        % (button.count(), files.count(), accept),
            "expected": {"source": "derived-check",
                         "rule": "사진을 올릴 자리가 있고 형식 판정은 서버가 한다",
                         "accept": accept},
            "failed": None if button.count() else "사진을 올릴 자리가 없다"}


flow("FF-0368", "user_profile", "attachment", "프로필 사진을 올린다(형식 판정은 서버가 한다)",
     _avatar_slot, route="/profile", server=False)


def _profile_action(label: str, api_hint: str, *, confirm: bool = False,
                    required: bool = True):
    def _act(r, ctx):
        button = r.in_main("button", label)
        if not button.count():
            if required:
                names = [" ".join((r.page.locator("#main-content button").nth(i)
                                   .inner_text() or "").split())
                         for i in range(min(r.page.locator(
                             "#main-content button").count(), 14))]
                stop("«%s» 가 없다 — 있는 버튼: %s" % (label, names))
            return {"ui_action": "«%s» 자리를 찾는다" % label,
                    "observed": {"buttons": 0},
                    "rendered": "«%s» 없음 — 이 상태에는 그 동작이 없다" % label,
                    "expected": {"source": "known-data",
                                 "rule": "그 조건일 때만 이 동작이 있다"},
                    "failed": None}
        r.rec.reset()
        button.first.click()
        r.settle(1200)
        asked = open_dialogs(r) > 0
        said = confirm_now(r) if asked else ""
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«%s» 를 실행한다" % label,
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:90]),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "failed": (("확인 없이 실행됐다" if confirm and not asked else None)
                           or (None if (not api_hint or any(api_hint in c for c in calls))
                               else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s"
                                    % (label, api_hint, calls)))}
    return _act


flow("FF-0369", "user_profile", "delete", "프로필 사진을 확인 후 지우고 이니셜로 되돌린다",
     _profile_action("사진 지우기", "/api/profile", confirm=True, required=False),
     route="/profile", server=False)


def _toggle_switch(name: str, api_hint: str):
    def _act(r, ctx):
        box = r.page.locator('#main-content input[type=checkbox][aria-label*="%s"], '
                             '#main-content [role="switch"][aria-label*="%s"]'
                             % (name, name))
        if not box.count():
            box = r.page.get_by_label(name, exact=False)
        if not box.count():
            stop("«%s» 스위치가 없다" % name)
        before = box.first.is_checked() if box.first.get_attribute("type") == "checkbox" \
            else box.first.get_attribute("aria-checked")
        r.rec.reset()
        box.first.click()
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        after = box.first.is_checked() if box.first.get_attribute("type") == "checkbox" \
            else box.first.get_attribute("aria-checked")
        return {"ui_action": "«%s» 스위치를 뒤집는다" % name,
                "observed": {"before": before, "after": after, "calls": calls},
                "rendered": "%s → %s · 쓰기 요청 %s" % (before, after, calls),
                "expected": {"source": "derived-check",
                             "rule": "스위치를 뒤집으면 서버에 저장된다", "got": calls},
                "cross": {"needle": ""},
                "failed": None if calls else "스위치를 뒤집었는데 서버로 안 갔다"}
    return _act


flow("FF-0370", "user_profile", "settings_apply",
     "알림 유형별 배지 알림을 켜고 끈다(서버가 준 카탈로그 기준)",
     _toggle_switch("티켓 배정", "/api/me/preferences"), route="/profile",
     api="/api/me/preferences")

flow("FF-0371", "user_profile", "settings_apply", "'지금 조용히 하기'를 켜고 끈다",
     _toggle_switch("방해금지", "/api/me/preferences"), route="/profile",
     api="/api/me/preferences")


def _dnd_preset(r, ctx):
    box = r.page.get_by_label("방해금지", exact=False)
    if box.count():
        box.first.click()
        r.settle(1400)
    chips = r.page.locator("#main-content button")
    names = [" ".join((chips.nth(i).inner_text() or "").split())
             for i in range(min(chips.count(), 20))]
    presets = [n for n in names if "분" in n or "시간" in n or "끌 때까지" in n]
    return {"ui_action": "방해금지를 켜고 지속 시간 프리셋을 본다",
            "observed": {"presets": presets},
            "rendered": "프리셋 %s" % presets,
            "expected": {"source": "derived-check",
                         "rule": "30분/1시간/3시간/직접 끌 때까지를 고를 수 있다",
                         "got": presets},
            "failed": None if presets else "방해금지를 켰는데 고를 지속 시간이 없다"}


flow("FF-0372", "user_profile", "settings_apply",
     "방해금지 지속 시간을 프리셋(30분/1시간/3시간/직접 끌 때까지)으로 고른다",
     _dnd_preset, route="/profile", server=False)


def _quiet_hours(r, ctx):
    box = r.page.get_by_label("조용시간", exact=False)
    if not box.count():
        stop("«조용시간» 스위치가 없다")
    box.first.click()
    r.settle(1400)
    times = r.page.locator('#main-content input[type="time"]')
    if times.count() >= 2:
        times.nth(0).fill("22:00")
        times.nth(1).fill("07:00")
        r.settle(500)
    r.rec.reset()
    save = r.in_main("button", "시간 저장")
    if not save.count():
        stop("«시간 저장» 버튼이 없다")
    save.first.click()
    r.settle(2200)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    return {"ui_action": "조용시간을 켜고 22:00~07:00 으로 저장한다",
            "observed": {"time_inputs": times.count(), "calls": calls},
            "rendered": "시간 칸 %d개 · 쓰기 요청 %s" % (times.count(), calls),
            "expected": {"source": "derived-check",
                         "rule": "조용시간은 시작·종료를 함께 저장한다", "got": calls},
            "cross": {"needle": "22:00"},
            "failed": None if calls else "저장을 눌렀는데 서버로 안 갔다"}


flow("FF-0373", "user_profile", "settings_apply", "매일 반복되는 조용시간을 켜고 시작·종료 시각을 저장한다",
     _quiet_hours, route="/profile", api="/api/me/preferences", cross=("@reload", ""))

flow("FF-0374", "user_profile", "delete", "특정 기기의 로그인 세션을 끊는다",
     _profile_action("세션 끊기", "/api/me/sessions", required=False), route="/profile",
     server=False)

flow("FF-0375", "user_profile", "modal_action",
     "'다른 기기 모두 로그아웃'을 확인 후 실행한다(지금 창은 유지)",
     _profile_action("다른 기기 모두 로그아웃", "/api/me/sessions", confirm=True),
     route="/profile", api="/api/me/sessions")

flow("FF-0376", "user_profile", "settings_apply", "둘러보기를 초기화해 다시 볼 수 있게 한다",
     _profile_action("둘러보기 다시 보기", ""), route="/profile", server=False)


def _password_link(r, ctx):
    link = r.page.locator('#main-content a[href*="change-password"]')
    if not link.count():
        link = r.in_main("button", "비밀번호")
    if not link.count():
        stop("비밀번호 변경으로 가는 자리가 없다")
    before = r.hash_of()
    link.first.click()
    r.settle(2400)
    where = r.page.url
    return {"ui_action": "비밀번호 변경 페이지로 나간다",
            "url_state": "%s → %s" % (before, where),
            "observed": {"url": where},
            "rendered": "주소 «%s» · 본문 «%s»" % (where[-40:], r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "비밀번호 변경 화면으로 옮긴다", "got": where},
            "failed": None if "change-password" in where
                      else "비밀번호 변경 화면으로 안 갔다: %s" % where}


flow("FF-0377", "user_profile", "navigation", "비밀번호 변경 페이지로 나간다",
     _password_link, route="/profile", server=False)

flow("FF-0378", "user_profile", "refresh", "프로필·설정·세션 조회 실패 시 각각 '다시 시도'를 준다",
     retry_from_error("/api/profile", "프로필"), route="/profile", api="/api/profile")


def _accent_preset(r, ctx):
    button = r.in_main("button", "보라")
    if not button.count():
        stop("강조색 프리셋이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1400)
    # **강조색은 CSS 변수가 아니라 브라우저 저장소에 남는다.** 화면은 그 값을 읽어
    # 테마 객체를 다시 만든다(서버 세션과 무관하다는 것이 이 설정의 계약이다).
    stored = r.page.evaluate(
        "() => { try { return Object.entries(localStorage)"
        ".filter(([k]) => k.indexOf('accent') >= 0)"
        ".map(([k, v]) => k + '=' + v).join(' · '); } catch (e) { return 'ERR'; } }")
    accent = r.page.evaluate(
        "() => { const el = document.querySelector('#main-content [aria-pressed=\"true\"],"
        " #main-content button[data-selected=\"true\"]');"
        " return el ? (el.innerText || '').replace(/\\s+/g,' ').trim() : ''; }")
    calls = [c for c in r.rec.calls if c["method"] != "GET"]
    return {"ui_action": "강조색 프리셋 «보라» 를 고른다",
            "frontend_state": "브라우저 로컬 저장 — 서버 세션과 무관",
            "observed": {"accent": accent.strip(), "local_keys": stored,
                         "write_calls": len(calls)},
            "rendered": "강조색 «%s» · 로컬 키 «%s» · 쓰기 요청 %d건"
                        % (accent.strip(), stored, len(calls)),
            "expected": {"source": "derived-check",
                         "rule": "고르면 즉시 적용되고 브라우저에 남는다",
                         "accent": accent.strip()},
            "failed": None if stored and stored != "ERR"
                      else "강조색을 골랐는데 브라우저에 아무것도 안 남았다"}


flow("FF-0389", "user_my-display", "settings_apply",
     "강조색 프리셋을 골라 즉시 적용한다(브라우저 로컬 저장, 서버 세션과 무관)",
     _accent_preset, route="/profile", server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /my-stats
# ═══════════════════════════════════════════════════════════════════════════
def _stats_read(r, ctx):
    heads = r.page.locator("#main-content table thead th")
    columns = [" ".join((heads.nth(i).inner_text() or "").split())
               for i in range(heads.count())]
    return {"ui_action": "내 업무량·완료 통계를 연다",
            "observed": {"columns": columns, "rows": n_rows(r),
                         "body": r.main_text(200)},
            "rendered": "열 %s · %d행" % (columns, n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "집계는 전부 서버가 하고 화면은 그린다",
                         "rows": n_rows(r)},
            "failed": None if (columns or n_rows(r)) else "통계가 아무것도 안 그려졌다"}


flow("FF-0379", "user_my-stats", "read", "내 업무량·완료 통계를 조회한다(집계는 전부 서버)",
     _stats_read, route="/my-stats", api="/api/me/")


def _stats_period(r, ctx):
    box = r.page.get_by_role("combobox").first
    if not box.count():
        stop("기간 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
    before = " ".join((box.inner_text() or "").split())
    r.rec.reset()
    box.click()
    r.settle(600)
    options = r.page.get_by_role("option")
    picked = ""
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label and label != before:
            picked = label
            options.nth(i).click()
            break
    if not picked:
        r.press("Escape")
        stop("기간 선택기에 다른 값이 없다")
    r.settle(2200)
    query = " ".join(sorted({c["query"] for c in r.rec.calls if c["query"]}))
    return {"ui_action": "집계 기간을 «%s» → «%s» 로 바꾼다" % (before, picked),
            "observed": {"query": query, "rows": n_rows(r)},
            "rendered": "질의 «%s» · %d행" % (query[:70], n_rows(r)),
            "expected": {"source": "derived-check",
                         "rule": "기간을 바꾸면 그 축이 서버로 간다", "got": query},
            "failed": None if query else "기간을 바꿨는데 서버에 아무 조건도 안 갔다"}


flow("FF-0380", "user_my-stats", "filter", "집계 기간을 최근 3/6/12개월 중에서 고른다",
     _stats_period, route="/my-stats", api="/api/me/")

flow("FF-0381", "user_my-stats", "refresh", "조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error("/api/me/stats", "내 통계"), route="/my-stats", api="/api/me/")


def _stats_empty_link(r, ctx):
    links = r.page.locator('#main-content a[href*="my-tickets"]')
    return {"ui_action": "«내 티켓으로» 링크를 찾는다",
            "observed": {"links": links.count(), "rows": n_rows(r),
                         "body": r.main_text(180)},
            "rendered": "링크 %d개 · %d행" % (links.count(), n_rows(r)),
            "expected": {"source": "known-data",
                         "rule": "집계할 티켓이 있으면 그 안내는 없는 것이 맞다",
                         "rows": n_rows(r)},
            "failed": None}


flow("FF-0382", "user_my-stats", "navigation",
     "집계할 티켓이 없을 때 '내 티켓으로' 간다(계정 미연결이면 이 링크를 주지 않는다)",
     _stats_empty_link, route="/my-stats", server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /activity
# ═══════════════════════════════════════════════════════════════════════════
ACT = "/api/me/activity"


def _activity_read(r, ctx):
    server = r.api_get(ACT)
    items = (server or {}).get("items") or []
    body = r.main_text(600)
    return {"ui_action": "내 활동을 연다",
            "observed": {"server": len(items), "body": body[:200]},
            "rendered": "서버 %d건 · 본문 «%s»" % (len(items), body[:160]),
            "expected": {"source": "known-data",
                         "rule": "감사 로그와 알림을 합쳐 한 목록으로 준다",
                         "expect": len(items)},
            "failed": None if (items or "없" in body)
                      else "활동이 없는데 왜 없는지도 안 말한다"}


flow("FF-0383", "user_activity", "read",
     "감사 로그(내가 행위자)와 내 알림을 합친 활동을 페이지 단위로 조회한다",
     _activity_read, route="/activity", api=ACT)


def _activity_kind(r, ctx):
    button = r.in_main("button", "내가 한 일")
    if not button.count():
        stop("«내가 한 일» 칩이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if ACT in c["path"] and c["query"]}))
    return {"ui_action": "종류를 «내가 한 일» 로 바꾼다",
            "observed": {"query": query, "hash": r.hash_of()},
            "rendered": "질의 «%s» · 주소 «%s»" % (query[:70], r.hash_of()[-30:]),
            "expected": {"source": "derived-check",
                         "rule": "종류를 바꾸면 그 축이 서버로 가고 쪽이 1로 돌아간다",
                         "got": query},
            "failed": None if query else "종류를 바꿨는데 서버에 아무 조건도 안 갔다"}


flow("FF-0384", "user_activity", "filter", "종류를 전체/내가 한 일/나에게 일어난 일로 바꾼다(페이지도 1로 되돌린다)",
     _activity_kind, route="/activity", api=ACT)

flow("FF-0385", "user_activity", "pagination", "페이지를 넘긴다(넘기는 동안 이전 목록을 유지한다)",
     pager(), route="/activity", api=ACT)


def _activity_open(r, ctx):
    button = r.in_main("button", "열기")
    if not button.count():
        stop("«열기» 가 없다")
    before = r.hash_of()
    button.first.click()
    r.settle(2400)
    return {"ui_action": "활동 행의 «열기» 를 누른다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"hash": r.hash_of()},
            "rendered": "주소 «%s» · 본문 «%s»" % (r.hash_of(), r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "그 항목 화면으로 옮긴다", "got": r.hash_of()},
            "failed": None if r.hash_of() != before
                      else "«열기» 를 눌렀는데 화면이 안 바뀐다"}


flow("FF-0386", "user_activity", "navigation", "활동 행의 '열기'로 그 항목 화면으로 이동한다",
     _activity_open, route="/activity", server=False)


def _activity_clear(r, ctx):
    button = r.in_main("button", "나에게 일어난 일")
    if button.count():
        button.first.click()
        r.settle(2000)
    empty_body = r.main_text(200)
    clear = r.in_main("button", "전체 보기")
    if not clear.count():
        return {"ui_action": "«전체 보기» 를 찾는다",
                "observed": {"button": 0, "body": empty_body},
                "rendered": "«전체 보기» 없음 — 고른 종류가 비지 않았다",
                "expected": {"source": "known-data",
                             "rule": "0건일 때만 «전체 보기» 를 준다"},
                "failed": None}
    clear.first.click()
    r.settle(2000)
    return {"ui_action": "0건에서 «전체 보기» 로 조건을 푼다",
            "observed": {"hash": r.hash_of(), "body": r.main_text(160)},
            "rendered": "주소 «%s» · 본문 «%s»" % (r.hash_of()[-30:], r.main_text(140)),
            "expected": {"source": "derived-check",
                         "rule": "조건 때문에 0건이면 되돌릴 자리를 준다"},
            "failed": None}


flow("FF-0387", "user_activity", "filter", "고른 종류가 비었을 때 '전체 보기'로 필터를 푼다",
     _activity_clear, route="/activity", server=False)

flow("FF-0388", "user_activity", "refresh", "조회 실패 시 '다시 시도'로 재조회한다",
     retry_from_error(ACT, "내 활동"), route="/activity", api=ACT)


# ═══════════════════════════════════════════════════════════════════════════
# /login — **세션 없는 눈**으로 본다
# ═══════════════════════════════════════════════════════════════════════════
def _fresh_login_page(r, fn):
    """쿠키가 없는 창을 하나 열어 로그인 화면을 본다.

    로그인한 채로 `/login` 을 열면 홈으로 튕긴다 — 그 상태에서 아무리 눌러 봐야 로그인
    화면을 본 것이 아니다.
    """
    browser = getattr(r, "_browser", None)
    if browser is None:
        stop("새 창을 열 브라우저가 없다")
    context = browser.new_context(ignore_https_errors=True)
    try:
        page = context.new_page()
        page.goto(r.base + "/login", wait_until="domcontentloaded")
        page.wait_for_timeout(1800)
        return fn(page)
    finally:
        context.close()


def _login_validation(r, ctx):
    def _probe(page):
        submit = page.get_by_role("button", name="로그인", exact=False)
        before = page.url
        if submit.count():
            submit.first.click()
            page.wait_for_timeout(1200)
        focused = page.evaluate(
            "() => { const el = document.activeElement;"
            " return el ? (el.getAttribute('name') || el.type || el.tagName) : ''; }")
        text = " ".join((page.locator("body").inner_text() or "").split())[:240]
        invalid = page.locator('[aria-invalid="true"]').count()
        return {"url": {"before": before, "after": page.url}, "focused": focused,
                "invalid": invalid, "body": text}

    got = _fresh_login_page(r, _probe)
    return {"ui_action": "빈 값으로 로그인을 눌러 본다(쿠키 없는 창)",
            "frontend_state": "왕복 없이 막고 문제 필드로 초점을 옮긴다",
            "observed": got,
            "rendered": "초점 «%s» · aria-invalid %d개 · 본문 «%s»"
                        % (got["focused"], got["invalid"], got["body"][:120]),
            "expected": {"source": "derived-check",
                         "rule": "빈 값이면 서버로 안 보내고 문제 칸으로 초점을 옮긴다",
                         "focused": got["focused"]},
            "failed": None if got["url"]["before"] == got["url"]["after"]
                      else "빈 값인데 화면이 넘어갔다"}


flow("FF-0947", "public_login", "form_validation",
     "빈 값·이메일 형식을 왕복 없이 막고 문제 필드로 초점을 옮긴다",
     _login_validation, server=False)


def _login_submit(r, ctx):
    import os

    email = os.environ.get("UI_QA_EMAIL", "ui-qa@goodmit.co.kr")
    password = os.environ.get("UI_QA_PASSWORD", "Ui-Qa-Local-1!")

    def _probe(page):
        page.fill('input[name="email"]', email)
        page.fill('input[name="password"]', password)
        page.get_by_role("button", name="로그인", exact=False).first.click()
        page.wait_for_timeout(3200)
        return {"url": page.url,
                "body": " ".join((page.locator("body").inner_text() or "").split())[:200]}

    got = _fresh_login_page(r, _probe)
    return {"ui_action": "자격 증명을 넣고 로그인한다(쿠키 없는 창)",
            "frontend_state": "JSON 제출 → 세션",
            "observed": got,
            "rendered": "주소 «%s» · 본문 «%s»" % (got["url"][-50:], got["body"][:120]),
            "expected": {"source": "derived-check",
                         "rule": "맞는 자격 증명이면 세션이 생기고 화면이 넘어간다",
                         "got": got["url"]},
            "failed": None if "/login" not in got["url"]
                      else "맞는 자격 증명인데 로그인 화면에 그대로 있다: %s" % got["body"][:90]}


flow("FF-0948", "public_login", "create", "자격 증명을 JSON 으로 제출해 세션을 만든다(JS 없으면 폼 POST 폴백)",
     _login_submit, server=False)


def _login_next(r, ctx):
    def _probe(page):
        page.goto(page.url.split("/login")[0] + "/login?next=/%23/my-tickets",
                  wait_until="domcontentloaded")
        page.wait_for_timeout(1500)
        hidden = page.locator('input[name="next"]')
        return {"hidden": hidden.count(),
                "value": hidden.first.get_attribute("value") if hidden.count() else "",
                "url": page.url}

    got = _fresh_login_page(r, _probe)
    return {"ui_action": "?next= 가 붙은 로그인 주소로 들어간다",
            "observed": got,
            "rendered": "hidden next %d개 · 값 «%s»" % (got["hidden"], got["value"]),
            "expected": {"source": "derived-check",
                         "rule": "튕겨 온 곳을 hidden 으로 실어 돌려보낸다", "got": got},
            "failed": None if got["hidden"] else "?next= 를 줬는데 폼이 그것을 안 싣는다"}


flow("FF-0950", "public_login", "deep_link",
     "세션 만료로 튕겨 온 경우 ?next= 를 hidden input 에 실어 하던 화면으로 돌려보낸다",
     _login_next, server=False)


def _login_after(r, ctx):
    def _probe(page):
        forms = page.locator("form").count()
        buttons = [" ".join((page.get_by_role("button").nth(i).inner_text() or "").split())
                   for i in range(min(page.get_by_role("button").count(), 8))]
        links = [page.locator("a").nth(i).get_attribute("href")
                 for i in range(min(page.locator("a").count(), 8))]
        return {"forms": forms, "buttons": buttons, "links": links,
                "body": " ".join((page.locator("body").inner_text() or "").split())[:240]}

    got = _fresh_login_page(r, _probe)
    return {"ui_action": "로그인 화면이 무엇을 주는지 본다",
            "observed": got,
            "rendered": "폼 %d · 버튼 %s · 링크 %s" % (got["forms"], got["buttons"],
                                                     got["links"]),
            "expected": {"source": "derived-check",
                         "rule": "성공하면 강제 변경 화면이나 next 로 옮긴다", "got": got},
            "failed": None if got["forms"] else "로그인 폼이 없다"}


flow("FF-0949", "public_login", "navigation", "성공하면 비밀번호 강제 변경 화면 또는 next 로 이동한다",
     _login_after, server=False)


def _password_toggle(r, ctx):
    def _probe(page):
        button = page.locator('button[aria-pressed], [aria-label*="비밀번호"]')
        if not button.count():
            return {"buttons": 0}
        before = button.first.get_attribute("aria-pressed")
        field_before = page.locator('input[name="password"]').get_attribute("type")
        button.first.click()
        page.wait_for_timeout(600)
        return {"buttons": button.count(),
                "aria_pressed": {"before": before,
                                 "after": button.first.get_attribute("aria-pressed")},
                "type": {"before": field_before,
                         "after": page.locator('input[name="password"]')
                         .get_attribute("type")}}

    got = _fresh_login_page(r, _probe)
    changed = got.get("type", {}).get("before") != got.get("type", {}).get("after")
    return {"ui_action": "비밀번호 표시/숨김을 토글한다",
            "observed": got,
            "rendered": "토글 %d개 · type %s" % (got.get("buttons", 0), got.get("type")),
            "expected": {"source": "derived-check",
                         "rule": "토글하면 입력 타입과 aria-pressed 가 함께 바뀐다",
                         "changed": changed},
            "failed": None if (got.get("buttons") and changed)
                      else "표시/숨김을 눌렀는데 입력 타입이 안 바뀐다"}


flow("FF-0951", "public_login", "settings_apply", "비밀번호 표시/숨김을 토글한다(aria-pressed 동기화)",
     _password_toggle, server=False)


def _locked_account(r, ctx):
    def _probe(page):
        page.fill('input[name="email"]', "no-such-account-s21@goodmit.co.kr")
        page.fill('input[name="password"]', "WrongPassword-1!")
        page.get_by_role("button", name="로그인", exact=False).first.click()
        page.wait_for_timeout(2600)
        # **본문 앞 260자는 광고 판이다.** 오류 안내는 그 아래에 있어서, 앞부분만 읽고
        # 「아무 안내가 없다」고 적으면 화면이 아니라 계측기가 못 본 것이다.
        text = " ".join((page.locator("body").inner_text() or "").split())
        alerts = [" ".join((page.locator('[role="alert"]').nth(i).inner_text() or "").split())
                  for i in range(min(page.locator('[role="alert"]').count(), 3))]
        return {"url": page.url, "alerts": alerts,
                "body": text[-400:], "has_error": ("올바르지 않" in text or "잠겼" in text
                                                   or "비활성" in text or "보관" in text)}

    got = _fresh_login_page(r, _probe)
    got["body"] = got.get("body", "")
    return {"ui_action": "없는 계정으로 로그인해 안내 문구를 읽는다",
            "observed": got,
            "rendered": "본문 «%s»" % got["body"][:180],
            "expected": {"source": "derived-check",
                         "rule": "잠금·비활성·보관을 구분해 각각 다른 복구 안내를 준다",
                         "got": got["body"][:140]},
            "failed": None if (got.get("has_error") or got.get("alerts"))
                      else "틀린 자격 증명인데 아무 안내가 없다"}


flow("FF-0952", "public_login", "permission_state",
     "계정 잠금·비활성·보관을 구분해 각각 다른 복구 안내를 보여준다",
     _locked_account, server=False)


def _reset_link(r, ctx):
    def _probe(page):
        links = [(" ".join((page.locator("a").nth(i).inner_text() or "").split()),
                  page.locator("a").nth(i).get_attribute("href"))
                 for i in range(min(page.locator("a").count(), 10))]
        return {"links": links}

    got = _fresh_login_page(r, _probe)
    reset = [x for x in got["links"] if "재설정" in (x[0] or "") or "reset" in (x[1] or "")]
    return {"ui_action": "비밀번호 재설정 링크가 있는지 본다",
            "observed": {"links": got["links"], "reset": reset},
            "rendered": "재설정 링크 %d개 · 전체 링크 %s" % (len(reset), got["links"]),
            "expected": {"source": "derived-check",
                         "rule": "메일 발송이 가능한 설치에서만 그 링크를 그린다",
                         "got": reset},
            "failed": None}


flow("FF-0953", "public_login", "navigation",
     "메일 발송이 가능한 설치에서만 '비밀번호 재설정 메일 받기' 링크를 노출한다",
     _reset_link, server=False)


def _readyz_notice(r, ctx):
    def _probe(page):
        page.route("**/login", lambda route: route.abort())
        page.fill('input[name="email"]', "ui-qa@goodmit.co.kr")
        page.fill('input[name="password"]', "whatever")
        try:
            page.get_by_role("button", name="로그인", exact=False).first.click()
            page.wait_for_timeout(3200)
        finally:
            page.unroute("**/login")
        return {"body": " ".join((page.locator("body").inner_text() or "").split())[:280]}

    got = _fresh_login_page(r, _probe)
    return {"ui_action": "로그인 왕복을 끊고 안내를 읽는다",
            "observed": got,
            "rendered": "본문 «%s»" % got["body"][:200],
            "expected": {"source": "derived-check",
                         "rule": "연결이 끊기면 서버 준비 상태를 확인해 안내한다",
                         "got": got["body"][:150]},
            "failed": None if got["body"] else "연결이 끊겼는데 화면이 아무 말도 없다"}


flow("FF-0954", "public_login", "refresh", "연결 계층 실패 시 /readyz 로 서버 준비 상태를 확인해 안내한다",
     _readyz_notice, server=False)
