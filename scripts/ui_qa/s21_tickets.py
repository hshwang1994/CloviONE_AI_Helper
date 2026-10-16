"""S21 — 티켓 목록 셋과 새 티켓 폼 (W14).

이 넷이 이 제품에서 가장 많이 쓰이는 화면이다. S15 가 **조건 사슬**을 서버 쪽에서
대조로 못 박았고, S18 이 티켓 **상세**를 실브라우저에서 눌렀다. 남은 것이 목록 쪽
상호작용 — 고르고, 고치고, 옮기고, 지우는 자리다.

쓰기 Flow 는 바꾼 값을 **다른 화면에서 다시 찾는다**(D-301). 한 화면이 200 이라고 완료가
아니다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import (  # noqa: F401
    n_rows, row_at, row_name, rows_of, confirm_now, dialog_says, open_dialog,
    open_dialogs,
    api_says, back_forward, cache_key, choose_then, close_modal, deep_link_survives_reload,
    dialog_text, dialogs, first_row_text, flow, forbidden_api, hidden_without_role,
    input_box, modal_open_close, open_first_row, open_row_modal, page_reset, pager,
    primary_button, race, required_blocks_submit, retry_from_error, row_title, rows_showing,
    search_then, sort_by, stop, title_like,
)

USER = "/"
SEARCH = "label=검색어"


# ═══════════════════════════════════════════════════════════════════════════
# 공통 — 세 목록이 같은 부품을 쓴다
# ═══════════════════════════════════════════════════════════════════════════
def _list_read(where: str, api: str):
    def _act(r, ctx):
        heads = r.page.locator("#main-content table thead th")
        labels = [" ".join((heads.nth(i).inner_text() or "").split())
                  for i in range(heads.count())]
        calls = [c for c in r.rec.calls if api in c["path"]]
        return {"ui_action": "%s 를 연다" % where,
                "observed": {"columns": labels, "rows": n_rows(r),
                             "query": (calls[0]["query"] if calls else "")},
                "rendered": "열 %d개 %s · %d행" % (len(labels), labels, n_rows(r)),
                "failed": None if n_rows(r) else "티켓이 한 행도 안 그려졌다"}
    return _act


def _clear_filters(combo: str, option: str):
    """조건을 하나 걸고 «필터 초기화» 로 **한 번에** 비운다."""
    def _act(r, ctx):
        r.choose(combo, option)
        narrowed = n_rows(r)
        hash_with = r.hash_of()
        clear = r.in_main("button", "필터 초기화")
        if not clear.count():
            clear = r.in_main("button", "초기화")
        if not clear.count():
            stop("«필터 초기화» 가 없다 — 조건을 걸었는데 비울 자리가 없다")
        clear.first.click()
        r.settle(1600)
        after = r.hash_of()
        return {"ui_action": "«%s = %s» 를 걸고 «필터 초기화» 를 누른다" % (combo, option),
                "frontend_state": "조건 전부 해제",
                "url_state": "%s → %s" % (hash_with, after),
                "observed": {"rows": {"filtered": narrowed, "cleared": n_rows(r)}},
                "rendered": "표 %d행 → %d행" % (narrowed, n_rows(r)),
                "expected": {"source": "derived-check",
                             "rule": "«필터 초기화» 뒤 주소에 그 조건이 안 남는다",
                             "expect": "조건 없음", "got": after},
                "failed": None if option not in after and "status" not in after
                          else "조건을 비웠는데 주소에 그대로 남아 있다: %s" % after}
    return _act


def _open_edit_modal(index: int = 0):
    def _act(r, ctx):
        rows = rows_of(r)
        if not rows.count():
            stop("행이 없다")
        button = rows.nth(index).get_by_role("button", name="수정", exact=False)
        if not button.count():
            stop("행에 «수정» 버튼이 없다")
        title = row_title(r, index)
        button.first.click()
        r.settle(1200)
        if not open_dialogs(r):
            stop("«수정» 을 눌렀는데 모달이 안 떴다")
        ctx["edit_row_title"] = title
        boxes = open_dialog(r).get_by_role("combobox")
        fields = [" ".join((boxes.nth(i).inner_text() or "").split())
                  for i in range(boxes.count())]
        text = dialog_says(r, 160)
        r.press("Escape")
        r.settle(500)
        return {"ui_action": "«%s» 행의 «수정» 을 누른다" % title,
                "frontend_state": "TicketEditModal open=true",
                "observed": {"selects": fields},
                "rendered": "모달 «%s»" % text}
    return _act


def _edit_and_save(field: str, *, cross_row: bool = True):
    """모달에서 값 하나를 **지금과 다른 것**으로 바꾸고 저장한다."""
    def _act(r, ctx):
        rows = rows_of(r)
        if not rows.count():
            stop("행이 없다")
        title = row_title(r, 0)
        rows.nth(0).get_by_role("button", name="수정", exact=False).first.click()
        r.settle(1200)
        if not open_dialogs(r):
            stop("모달이 안 떴다")
        before, chosen = r.choose_other(field)
        open_dialog(r).get_by_role("button", name="저장", exact=True).first.click()
        r.settle(2200)
        left = open_dialogs(r)
        return {"ui_action": "«%s» 의 %s 를 «%s» → «%s» 로 바꿔 저장한다"
                             % (title, field, before, chosen),
                "frontend_state": "바뀐 칸만 PATCH",
                "observed": {"field": field, "before": before, "after": chosen,
                             "dialogs_left": left},
                "rendered": "표 %d행 · 본문 «%s»" % (n_rows(r), r.main_text(80)),
                "expected": {"source": "derived-check",
                             "rule": "저장하면 모달이 닫히고 목록이 새 값을 그린다",
                             "expect": chosen},
                "cross": ({"row": title, "expect": chosen} if cross_row
                          else {"needle": chosen}),
                "failed": "저장했는데 모달이 안 닫혔다" if left else None}
    return _act


def _bulk_select_and_trash(confirm_only: bool):
    """행을 골라 휴지통으로 — `confirm_only` 면 **확인 대화까지만** 보고 되돌린다."""
    def _act(r, ctx):
        boxes = rows_of(r).locator('input[type="checkbox"]')
        if not boxes.count():
            stop("행 선택 상자가 없다")
        title = row_title(r, 0)
        boxes.first.check()
        r.settle(900)
        button = r.in_main("button", "휴지통")
        if not button.count():
            button = r.in_main("button", "삭제")
        if not button.count():
            stop("고른 뒤에도 휴지통 버튼이 안 나타났다")
        label = " ".join((button.first.inner_text() or "").split())
        button.first.click()
        r.settle(1000)
        asked = open_dialogs(r) > 0
        said = dialog_says(r, 160) if asked else ""
        if confirm_only:
            if asked:
                r.press("Escape")
                r.settle(600)
            boxes.first.uncheck()
            return {"ui_action": "한 건을 고르고 «%s» 를 누른다 — 확인 대화만 본다" % label,
                    "frontend_state": "확인 대화 open",
                    "observed": {"confirm_asked": asked, "text": said},
                    "rendered": "확인 «%s»" % said,
                    "expected": {"source": "derived-check",
                                 "rule": "지우기 전에 몇 건인지 말하고 확인을 받는다",
                                 "confirm_asked": asked},
                    "failed": None if asked else "확인 없이 바로 지우려 한다"}
        if not asked:
            stop("확인 대화 없이 바로 지우려 한다")
        confirm_now(r)
        r.settle(1400)
        return {"ui_action": "«%s» 한 건을 골라 휴지통으로 보낸다" % title,
                "frontend_state": "POST /api/tickets/trash-bulk",
                "observed": {"confirm": said, "rows_after": n_rows(r)},
                "rendered": "표 %d행 · 본문 «%s»" % (n_rows(r), r.main_text(80)),
                "expected": {"source": "derived-check",
                             "rule": "휴지통으로 보낸 티켓은 이 목록에서 사라지고 휴지통에 나타난다",
                             "moved": title},
                "cross": {"needle": title}}
    return _act


# ═══════════════════════════════════════════════════════════════════════════
# /my-tickets
# ═══════════════════════════════════════════════════════════════════════════
flow("FF-0021", "user_my-tickets", "read", "필터를 질의 문자열로 붙여 내 담당 티켓 한 페이지를 받는다",
     _list_read("/my-tickets", "/api/tickets/mine"),
     route="/my-tickets?priority=High", api="/api/tickets/mine")

flow("FF-0029", "user_my-tickets", "filter",
     "'필터 지우기'로 걸린 조건을 한 번에 비운다(빈 상태 버튼과 같은 동작)",
     _clear_filters("우선순위", "높음"), route="/my-tickets", api="/api/tickets/mine")

flow("FF-0030", "user_my-tickets", "deep_link",
     "필터와 페이지가 주소에 남아 새로고침·공유에서 그대로 복원된다",
     deep_link_survives_reload("/my-tickets?priority=High&page=1", "priority=High"),
     api="/api/tickets/mine")

flow("FF-0031", "user_my-tickets", "pagination", "서버 페이지네이션 — Pager 로 페이지를 옮긴다",
     pager(), route="/my-tickets", api="/api/tickets/mine")

flow("FF-0032", "user_my-tickets", "navigation",
     "티켓 제목 링크로 상세(/tickets/:id)로 간다 — from:\"/my-tickets\"",
     open_first_row, route="/my-tickets", api="/api/tickets/")

flow("FF-0033", "user_my-tickets", "row_action", "행의 '수정' 버튼으로 편집 모달을 연다",
     _open_edit_modal(), route="/my-tickets", server=False)


def _row_checkbox(r, ctx):
    boxes = rows_of(r).locator('input[type="checkbox"]')
    if not boxes.count():
        stop("행 선택 상자가 없다")
    title = row_title(r, 0)
    boxes.first.check()
    r.settle(800)
    bar = r.main_text(140)
    checked = boxes.first.is_checked()
    boxes.first.uncheck()
    r.settle(500)
    return {"ui_action": "«%s» 행의 선택 상자를 켠다" % title,
            "frontend_state": "selected=[1]",
            "observed": {"checked": checked, "bar": bar},
            "rendered": "선택 뒤 본문 «%s»" % bar,
            "expected": {"source": "derived-check",
                         "rule": "행을 고르면 일괄 동작 줄이 나타난다",
                         "checked": checked},
            "failed": None if checked else "선택 상자를 켰는데 안 켜진다"}


flow("FF-0034", "user_my-tickets", "row_action", "행 선택 체크박스로 일괄 대상에 넣는다",
     _row_checkbox, route="/my-tickets", server=False)


def _modal_dirty_close(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("행이 없다")
    rows.nth(0).get_by_role("button", name="수정", exact=False).first.click()
    r.settle(1200)
    if not dialogs(r):
        stop("모달이 안 떴다")
    title_box = open_dialog(r).locator("#te-title")
    if not title_box.count():
        stop("모달에 «제목» 칸이 없다")
    title_box.first.fill("업무 — S21 이 잠깐 고쳐 본 제목")
    r.settle(500)
    r.page.keyboard.press("Escape")
    r.settle(900)
    said = dialog_says(r, 200)
    asked = open_dialogs(r) > 1 or "저장되지 않았습니다" in said
    r.dismiss_overlays()
    return {"ui_action": "모달에서 제목을 고친 뒤 Esc 로 닫으려 한다",
            "frontend_state": "dirty=true",
            "observed": {"confirm_asked": asked, "text": said},
            "rendered": "확인 «%s»" % said,
            "expected": {"source": "derived-check",
                         "rule": "고친 것이 있으면 닫기 전에 확인을 받는다",
                         "confirm_asked": asked},
            "failed": None if asked else "고친 채로 닫는데 아무것도 안 묻는다"}


flow("FF-0035", "user_my-tickets", "modal_action",
     "TicketEditModal 열기/닫기 — 변경이 있으면 닫을 때 확인을 받는다",
     _modal_dirty_close, route="/my-tickets", server=False)

flow("FF-0036", "user_my-tickets", "edit", "편집 모달 저장이 바뀐 필드만 PATCH 한다",
     _edit_and_save("난이도"), route="/my-tickets", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0037", "user_my-tickets", "status_change", "편집 모달의 진행상태 select",
     _edit_and_save("진행상태"), route="/my-tickets", api="/api/tickets/",
     cross=("/my-tickets", "/"))

flow("FF-0038", "user_my-tickets", "priority_change", "편집 모달의 우선순위 select",
     _edit_and_save("우선순위"), route="/my-tickets", api="/api/tickets/",
     cross=("/my-tickets", "/"))


def _assignee_change(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("행이 없다")
    title = row_title(r, 0)
    rows.nth(0).get_by_role("button", name="수정", exact=False).first.click()
    r.settle(1300)
    dialog = open_dialog(r)
    box = dialog.locator('input[role="combobox"]')
    if not box.count():
        stop("담당자 선택 상자(Autocomplete)가 모달에 없다")
    before = " ".join((dialog.inner_text() or "").split())[:140]
    box.first.click()
    r.settle(600)
    options = r.page.get_by_role("option")
    if not options.count():
        r.press("Escape")
        stop("담당자 후보가 하나도 안 뜬다")
    picked = " ".join((options.first.inner_text() or "").split())[:40]
    options.first.click()
    r.settle(700)
    # **Esc 를 그냥 누르지 않는다.** 다중 선택 상자는 고른 뒤에도 열린 채로 있는 것이
    # 계약이지만(pilot_kit.close_listbox), 이미 닫혀 있으면 그 Esc 가 **모달을** 닫는다 —
    # 그러면 다음 줄의 «저장» 이 30초를 기다리다 죽고, 기록에는 「저장이 안 됐다」가 남는다.
    r.close_listbox()
    if not open_dialogs(r):
        stop("담당자를 고른 뒤 모달이 닫혀 버렸다")
    open_dialog(r).get_by_role("button", name="저장", exact=True).first.click()
    r.settle(2200)
    return {"ui_action": "«%s» 의 담당자에 «%s» 를 더해 저장한다" % (title, picked),
            "frontend_state": "assignee_user_ids 가 바뀐 칸으로 나간다",
            "observed": {"picked": picked, "modal_before": before},
            "rendered": "본문 «%s»" % r.main_text(90),
            "expected": {"source": "derived-check",
                         "rule": "담당자를 바꾸면 목록의 담당자 열이 따라 바뀐다",
                         "expect": picked},
            "cross": {"needle": picked.split()[0] if picked else title}}


flow("FF-0039", "user_my-tickets", "assignee_change",
     "편집 모달의 담당자 Autocomplete 로 배정을 바꾼다",
     _assignee_change, route="/my-tickets", api="/api/tickets/",
     cross=("/my-tickets", "/"))


def _assignee_combobox(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("행이 없다")
    rows.nth(0).get_by_role("button", name="수정", exact=False).first.click()
    r.settle(1300)
    dialog = open_dialog(r)
    box = dialog.locator('input[role="combobox"]')
    if not box.count():
        stop("담당자 Autocomplete 가 없다")
    box.first.fill("김")
    r.settle(900)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())[:30]
             for i in range(min(options.count(), 6))]
    multiple = box.first.get_attribute("aria-expanded")
    chips = dialog.locator(".MuiChip-root").count()
    r.press("Escape")
    r.dismiss_overlays()
    return {"ui_action": "담당자 상자에 «김» 을 쳐 후보를 좁힌다",
            "frontend_state": "Autocomplete multiple · 칩 %d개" % chips,
            "observed": {"options": names, "chips": chips, "expanded": multiple},
            "rendered": "후보 %d명 %s · 칩 %d개" % (len(names), names, chips),
            "expected": {"source": "derived-check",
                         "rule": "검색형 다중 선택이라 친 글자로 후보가 좁혀진다",
                         "typed": "김", "got": names},
            "failed": None if names else "«김» 을 쳤는데 후보가 하나도 안 뜬다"}


flow("FF-0040", "user_my-tickets", "combobox",
     "담당자 선택은 검색형 Autocomplete(다중 선택 + 칩)다",
     _assignee_combobox, route="/my-tickets", server=False)


def _edit_validation(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("행이 없다")
    rows.nth(0).get_by_role("button", name="수정", exact=False).first.click()
    r.settle(1300)
    dialog = open_dialog(r)
    dialog.locator("#te-title").first.fill("")
    r.settle(400)
    r.rec.reset()
    dialog.get_by_role("button", name="저장", exact=True).first.click()
    r.settle(1400)
    sent = [c for c in r.rec.calls if c["method"] == "PATCH"]
    still = dialogs(r) > 0
    said = r.main_text(140)
    wd = dialog.locator("#te-wd")
    typed = wd.first.get_attribute("type") if wd.count() else ""
    r.dismiss_overlays()
    return {"ui_action": "제목을 비우고 저장을 누른다",
            "frontend_state": "제출 전 검사에서 막힌다",
            "observed": {"patch_calls": len(sent), "modal_open": still,
                         "wd_input_type": typed},
            "rendered": "PATCH %d건 · 모달 %s · 안내 «%s»"
                        % (len(sent), "열림" if still else "닫힘", said[:70]),
            "expected": {"source": "derived-check",
                         "rule": "필수값이 비면 서버로 보내지 않는다",
                         "expect": 0, "got": len(sent)},
            "failed": None if not sent else "제목이 빈 채로 PATCH 가 나갔다"}


flow("FF-0041", "user_my-tickets", "form_validation",
     "저장 전 제목·진행상태 필수와 예상/실제 WD 숫자 검사",
     _edit_validation, route="/my-tickets", server=False)

flow("FF-0042", "user_my-tickets", "delete", "선택한 티켓을 일괄로 휴지통에 보낸다",
     _bulk_select_and_trash(False), route="/my-tickets", api="/api/tickets/trash-bulk",
     cross=("/team-docs/trash", "/"))

flow("FF-0043", "user_my-tickets", "modal_action",
     "일괄 삭제 전 '티켓 N건을 휴지통으로' 확인 대화",
     _bulk_select_and_trash(True), route="/my-tickets", server=False)

flow("FF-0044", "user_my-tickets", "refresh",
     "오류 상태의 '다시 시도'와 연동 안내의 '다시 불러오기'",
     retry_from_error("/api/tickets/mine", "내 티켓"), route="/my-tickets",
     api="/api/tickets/mine")


# ═══════════════════════════════════════════════════════════════════════════
# /unassigned
# ═══════════════════════════════════════════════════════════════════════════
flow("FF-0045", "user_unassigned", "read", "담당자 없는 활성 티켓 한 페이지를 받는다",
     _list_read("/unassigned", "/api/tickets/unassigned"),
     route="/unassigned", api="/api/tickets/unassigned")


def _claim(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("미할당 티켓이 없다 — 배정할 자리가 없다")
    title = row_title(r, 0)
    before = n_rows(r)
    button = rows.nth(0).get_by_role("button", name="나에게 배정", exact=False)
    if not button.count():
        stop("«나에게 배정» 버튼이 없다")
    asked_before = dialogs(r)
    button.first.click()
    r.settle(2400)
    ctx["claimed_title"] = title
    return {"ui_action": "«%s» 의 «나에게 배정» 을 누른다" % title,
            "frontend_state": "POST /api/tickets/{id}/claim — 확인 대화 없이 즉시",
            "observed": {"rows": {"before": before, "after": n_rows(r)},
                         "dialogs_before": asked_before, "dialogs_after": dialogs(r)},
            "rendered": "표 %d행 → %d행 · 본문 «%s»" % (before, n_rows(r), r.main_text(80)),
            "expected": {"source": "derived-check",
                         "rule": "배정하면 미할당 목록에서 빠지고 내 티켓에 나타난다",
                         "expect": before - 1, "got": n_rows(r), "ticket": title},
            "cross": {"row": title, "expect": ""},
            "failed": None if n_rows(r) < before
                      else "배정했는데 미할당 목록에 그대로 있다"}


flow("FF-0046", "user_unassigned", "assignee_change",
     "'나에게 배정'을 누르면 그 티켓의 담당자가 된다(확인 대화 없음, 즉시 실행)",
     _claim, route="/unassigned", api="/api/tickets/", cross=("/my-tickets", "/"))


def _claim_button_present(r, ctx):
    rows = rows_of(r)
    if not rows.count():
        stop("행이 없다")
    n = 0
    for i in range(min(rows.count(), 5)):
        n += rows.nth(i).get_by_role("button", name="나에게 배정", exact=False).count()
    return {"ui_action": "미할당 목록의 행마다 «나에게 배정» 이 있는지 센다",
            "observed": {"rows": rows.count(), "claim_buttons": n},
            "rendered": "%d행 중 앞 %d행에 «나에게 배정» %d개"
                        % (rows.count(), min(rows.count(), 5), n),
            "failed": None if n else "미할당인데 «나에게 배정» 버튼이 한 행에도 없다"}


flow("FF-0047", "user_unassigned", "row_action", "행의 '나에게 배정' 버튼",
     _claim_button_present, route="/unassigned", server=False)

flow("FF-0048", "user_unassigned", "row_action",
     "행의 '수정' 버튼으로 편집 모달을 연다(다른 사람 배정은 여기서)",
     _open_edit_modal(), route="/unassigned", server=False)

flow("FF-0054", "user_unassigned", "filter", "기한 버킷으로 거른다",
     choose_then("기한", "지연"), route="/unassigned", api="/api/tickets/unassigned")

flow("FF-0056", "user_unassigned", "filter", "'필터 지우기'로 조건을 비운다",
     _clear_filters("우선순위", "높음"), route="/unassigned",
     api="/api/tickets/unassigned")

flow("FF-0057", "user_unassigned", "deep_link", "필터와 페이지가 주소에 남는다",
     deep_link_survives_reload("/unassigned?priority=High", "priority=High"),
     api="/api/tickets/unassigned")

flow("FF-0058", "user_unassigned", "pagination", "Pager 로 페이지를 옮긴다",
     pager(), route="/unassigned", api="/api/tickets/unassigned")

flow("FF-0059", "user_unassigned", "navigation", "티켓 제목 링크로 상세로 간다 — from:\"/unassigned\"",
     open_first_row, route="/unassigned", api="/api/tickets/")

flow("FF-0060", "user_unassigned", "modal_action", "TicketEditModal 열기/닫기",
     modal_open_close("button=수정"), route="/unassigned", server=False)

flow("FF-0061", "user_unassigned", "edit", "편집 모달 저장 PATCH",
     _edit_and_save("난이도"), route="/unassigned", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0062", "user_unassigned", "status_change", "편집 모달의 진행상태 select",
     _edit_and_save("진행상태"), route="/unassigned", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0063", "user_unassigned", "priority_change", "편집 모달의 우선순위 select",
     _edit_and_save("우선순위"), route="/unassigned", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0064", "user_unassigned", "combobox", "담당자 Autocomplete(다중 선택 + 칩)",
     _assignee_combobox, route="/unassigned", server=False)

flow("FF-0065", "user_unassigned", "form_validation", "저장 전 제목·상태 필수와 WD 숫자 검사",
     _edit_validation, route="/unassigned", server=False)

flow("FF-0066", "user_unassigned", "delete", "선택한 티켓을 일괄로 휴지통에 보낸다",
     _bulk_select_and_trash(False), route="/unassigned", api="/api/tickets/trash-bulk",
     cross=("/team-docs/trash", "/"))

flow("FF-0067", "user_unassigned", "modal_action", "일괄 삭제 확인 대화",
     _bulk_select_and_trash(True), route="/unassigned", server=False)

flow("FF-0068", "user_unassigned", "refresh", "오류 상태 '다시 시도' / 연동 안내 '다시 불러오기'",
     retry_from_error("/api/tickets/unassigned", "미할당 티켓"), route="/unassigned",
     api="/api/tickets/unassigned")

flow("FF-1335", "user_unassigned", "filter", "조건을 바꾸면 쪽이 초기화된다",
     page_reset("우선순위", "높음"), route="/unassigned", api="/api/tickets/unassigned")

flow("FF-1336", "user_unassigned", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(SEARCH, "업무 0", "업무 1"), route="/unassigned", api="/api/tickets/unassigned")

flow("FF-1337", "user_unassigned", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/unassigned?priority=High", "/unassigned?priority=Low"),
     api="/api/tickets/unassigned")

flow("FF-1338", "user_unassigned", "filter", "뒤로가기에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/unassigned?priority=High", "/unassigned?priority=Low"),
     api="/api/tickets/unassigned")


# ═══════════════════════════════════════════════════════════════════════════
# /team-tickets
# ═══════════════════════════════════════════════════════════════════════════
flow("FF-0097", "user_team-tickets", "read", "조건·범위를 붙여 팀 티켓 한 페이지를 받는다",
     _list_read("/team-tickets", "/api/tickets/team"),
     route="/team-tickets", api="/api/tickets/team")


def _include_done(r, ctx):
    before = n_rows(r)
    box = r.page.locator('#main-content input[type="checkbox"]').first
    if not box.count():
        stop("«완료, 취소 포함» 스위치가 없다")
    r.rec.reset()
    box.click()
    r.settle(1800)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/tickets/team" in c["path"] and c["query"]}))
    return {"ui_action": "«완료, 취소 포함» 을 켠다",
            "frontend_state": "active=false 로 범위를 넓힌다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "표 %d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:80]),
            "expected": {"source": "derived-check",
                         "rule": "완료·취소를 포함하면 서버 질의의 active 축이 바뀐다",
                         "query": query},
            "failed": None if ("active" in query or n_rows(r) != before)
                      else "스위치를 켰는데 질의도 행 수도 그대로다"}


flow("FF-0106", "user_team-tickets", "filter",
     "'완료, 취소 포함' 스위치로 목록 범위를 넓힌다(서버 active 파라미터)",
     _include_done, route="/team-tickets", api="/api/tickets/team")


def _scope_pick(r, ctx):
    before = n_rows(r)
    box = r.page.get_by_placeholder("내 범위 전체")
    if not box.count():
        box = r.page.get_by_role("combobox", name="범위", exact=False)
    if not box.count():
        stop("범위 선택기가 없다 — 지금 선택 상자: %s" % r.combobox_names())
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
        stop("범위 선택기에 «전체» 말고 고를 것이 없다")
    r.settle(1800)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if "/api/tickets/team" in c["path"] and c["query"]}))
    return {"ui_action": "범위를 «%s» 로 좁힌다" % picked,
            "frontend_state": "department_id 가 질의에 실린다",
            "observed": {"rows": {"before": before, "after": n_rows(r)}, "query": query},
            "rendered": "표 %d행 → %d행 · 질의 «%s»" % (before, n_rows(r), query[:90]),
            "expected": {"source": "derived-check",
                         "rule": "범위를 고르면 서버 질의에 그 축이 실린다",
                         "picked": picked, "query": query},
            "failed": None if query else "범위를 골랐는데 서버에 아무 조건도 안 갔다"}


flow("FF-0107", "user_team-tickets", "filter", "부서 선택으로 조회 범위를 좁힌다(서버 department_id)",
     _scope_pick, route="/team-tickets", api="/api/tickets/team")

flow("FF-0108", "user_team-tickets", "filter", "'필터 지우기'가 조건과 부서 범위를 함께 비운다",
     _clear_filters("우선순위", "높음"), route="/team-tickets", api="/api/tickets/team")

flow("FF-0109", "user_team-tickets", "deep_link", "조건·부서·페이지가 주소에 남는다",
     deep_link_survives_reload("/team-tickets?priority=High", "priority=High"),
     api="/api/tickets/team")

flow("FF-0111", "user_team-tickets", "navigation",
     "티켓 제목 링크로 상세로 간다 — from:\"/team-tickets\"",
     open_first_row, route="/team-tickets", api="/api/tickets/")

flow("FF-0112", "user_team-tickets", "row_action", "행의 '수정' 버튼으로 편집 모달을 연다",
     _open_edit_modal(), route="/team-tickets", server=False)

flow("FF-0113", "user_team-tickets", "modal_action", "TicketEditModal 열기/닫기",
     modal_open_close("button=수정"), route="/team-tickets", server=False)

flow("FF-0114", "user_team-tickets", "edit", "편집 모달 저장 PATCH",
     _edit_and_save("난이도"), route="/team-tickets", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0115", "user_team-tickets", "status_change", "편집 모달의 진행상태 select",
     _edit_and_save("진행상태"), route="/team-tickets", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0116", "user_team-tickets", "priority_change", "편집 모달의 우선순위 select",
     _edit_and_save("우선순위"), route="/team-tickets", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0117", "user_team-tickets", "assignee_change", "편집 모달의 담당자 Autocomplete",
     _assignee_change, route="/team-tickets", api="/api/tickets/",
     cross=("@reload", ""))

flow("FF-0121", "user_team-tickets", "refresh", "오류 상태 '다시 시도'",
     retry_from_error("/api/tickets/team", "팀 티켓"), route="/team-tickets",
     api="/api/tickets/team")

flow("FF-1324", "user_team-tickets", "filter", "조건을 바꾸면 쪽이 초기화된다",
     page_reset("우선순위", "높음"), route="/team-tickets", api="/api/tickets/team")

flow("FF-1325", "user_team-tickets", "filter",
     "조건을 빠르게 바꿔도 옛 응답이 최신 조건을 덮지 않는다(경합)",
     race(SEARCH, "업무 0", "업무 1"), route="/team-tickets", api="/api/tickets/team")

flow("FF-1326", "user_team-tickets", "filter", "다른 조건이 같은 캐시를 재사용하지 않는다(캐시 키)",
     cache_key("/team-tickets?priority=High", "/team-tickets?priority=Low"),
     api="/api/tickets/team")

flow("FF-1327", "user_team-tickets", "filter",
     "뒤로가기·새로고침에서 화면이 말하는 조건과 실제 질의가 같다",
     back_forward("/team-tickets?priority=High", "/team-tickets?priority=Low"),
     api="/api/tickets/team")


# ═══════════════════════════════════════════════════════════════════════════
# /new-ticket
# ═══════════════════════════════════════════════════════════════════════════
def _pick_project(r):
    """프로젝트를 **실제로 하나** 고른다.

    이 선택기의 첫 후보는 «프로젝트 선택» 이다 — 값이 빈 «전체» 항목이라, 그것을 고르면
    아무것도 안 고른 것과 같다. 실제로 그 자리에서 담당자 상자가 잠긴 채로 남았고 Flow 는
    「프로젝트를 골랐는데 잠겨 있다」로 죽었다. 값이 있는 후보를 고른다.
    """
    project = r.page.get_by_placeholder("프로젝트 선택")
    if not project.count():
        stop("프로젝트 선택기가 없다")
    project.first.click()
    r.settle(500)
    options = r.page.get_by_role("option")
    if not options.count():
        project.first.press("ArrowDown")
        r.settle(700)
        options = r.page.get_by_role("option")
    if not options.count():
        r.press("Escape")
        stop("프로젝트 후보가 없다")
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label and "선택" not in label and "전체" not in label:
            options.nth(i).click()
            r.settle(1400)
            return label
    r.press("Escape")
    stop("프로젝트 후보에 «선택»·«전체» 말고 고를 것이 없다")


def _new_ticket_read(r, ctx):
    """폼이 **고를 수 있는 값을 실제로 들고 있는가**를 화면에서 확인한다.

    「부른 요청이 있는가」로 재지 않는다 — 화면을 여는 동안 오간 요청은 엔진이 따로
    담아 두고, act 안에서 다시 세면 언제나 0 이다. 물어야 하는 것은 그것이 아니라
    **후보가 화면에 도착했는가** 다.
    """
    project = r.page.get_by_placeholder("프로젝트 선택")
    if not project.count():
        stop("프로젝트 선택기가 없다")
    project.first.click()
    r.settle(900)
    options = r.page.get_by_role("option")
    names = [" ".join((options.nth(i).inner_text() or "").split())[:30]
             for i in range(min(options.count(), 5))]
    r.press("Escape")
    status = r.page.get_by_role("combobox").first
    status_text = " ".join((status.inner_text() or "").split()) if status.count() else ""
    return {"ui_action": "/new-ticket 을 열고 프로젝트 후보와 메타 선택지를 본다",
            "observed": {"projects": names, "status_default": status_text},
            "rendered": "프로젝트 후보 %d개 %s · 상태 기본값 «%s»"
                        % (len(names), names, status_text),
            "expected": {"source": "known-data",
                         "rule": "폼을 열면 프로젝트·메타를 함께 받아 고를 수 있다",
                         "got": names},
            "failed": None if names else "프로젝트 후보가 하나도 안 왔다"}


flow("FF-0071", "user_new-ticket", "read",
     "프로젝트 목록·티켓 메타(상태/우선순위/난이도)·담당자 후보를 불러온다",
     _new_ticket_read, route="/new-ticket", api="/api/tickets/")


def _new_ticket_validation(r, ctx):
    r.rec.reset()
    submit = r.in_main("button", "티켓 추가")
    if not submit.count():
        stop("«티켓 추가» 버튼이 없다")
    submit.first.click()
    r.settle(1500)
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    said = r.main_text(160)
    return {"ui_action": "제목·프로젝트를 비운 채 «티켓 추가» 를 누른다",
            "frontend_state": "제출 전 검사에서 막힌다",
            "observed": {"post_calls": len(sent), "message": said},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), said[:90]),
            "expected": {"source": "derived-check",
                         "rule": "필수값이 비면 서버로 안 보낸다",
                         "expect": 0, "got": len(sent)},
            "failed": None if not sent else "필수값이 빈 채로 POST 가 나갔다"}


flow("FF-0070", "user_new-ticket", "form_validation",
     "제목 필수·프로젝트 필수·예상 WD 숫자 형식을 제출 전에 검사한다",
     _new_ticket_validation, route="/new-ticket", server=False)


def _new_ticket_assignee_gate(r, ctx):
    box = r.page.locator("#main-content input[role=combobox]")
    before = box.last.is_disabled() if box.count() else None
    picked = _pick_project(r)
    box = r.page.locator("#main-content input[role=combobox]")
    after = box.last.is_disabled() if box.count() else None
    ctx["new_ticket_project"] = picked
    return {"ui_action": "프로젝트 «%s» 를 고른 뒤 담당자 상자를 본다" % picked,
            "frontend_state": "프로젝트를 고른 뒤에만 담당자 후보를 받는다",
            "observed": {"assignee_disabled": {"before": before, "after": after}},
            "rendered": "담당자 상자 %s → %s"
                        % ("잠김" if before else "열림", "잠김" if after else "열림"),
            "expected": {"source": "derived-check",
                         "rule": "프로젝트를 고르기 전에는 담당자를 못 고른다",
                         "before": before, "after": after},
            "failed": None if after is False
                      else "프로젝트를 골랐는데 담당자 상자가 아직 잠겨 있다"}


flow("FF-0072", "user_new-ticket", "combobox",
     "담당자를 검색형 Autocomplete 로 다중 선택한다 — 프로젝트를 고른 뒤에만 활성",
     _new_ticket_assignee_gate, route="/new-ticket", api="/api/tickets/assignees")


def _writing_help(r, ctx):
    button = r.in_main("button", "검증 범위 명시")
    if not button.count():
        stop("«작성 도움» 항목이 없다")
    body = r.page.get_by_placeholder("예: 재현 절차와 기대 결과")
    if not body.count():
        body = r.page.locator("#main-content textarea").first
    before = body.first.input_value() if body.count() else ""
    button.first.click()
    r.settle(900)
    after = body.first.input_value() if body.count() else ""
    disabled = button.first.is_disabled()
    return {"ui_action": "«설명에 '검증 범위 명시' 절 넣기» 를 누른다",
            "frontend_state": "본문 초안에 절이 삽입된다",
            "observed": {"len": {"before": len(before), "after": len(after)},
                         "now_disabled": disabled},
            "rendered": "본문 %d자 → %d자 · 버튼 %s"
                        % (len(before), len(after), "잠김" if disabled else "열림"),
            "expected": {"source": "derived-check",
                         "rule": "누르면 본문에 절이 실제로 들어가고, 이미 있으면 비활성이다",
                         "grew": len(after) > len(before), "disabled": disabled},
            "failed": None if len(after) > len(before)
                      else "«작성 도움» 을 눌렀는데 본문이 안 늘었다"}


flow("FF-0073", "user_new-ticket", "inline_edit",
     "'작성 도움'의 항목을 누르면 설명 본문에 '## 검증 범위' 같은 절이 실제로 삽입된다"
     "(이미 있으면 비활성)",
     _writing_help, route="/new-ticket", server=False)


def _body_toolbar(r, ctx):
    body = r.page.get_by_placeholder("예: 재현 절차와 기대 결과")
    if not body.count():
        body = r.page.locator("#main-content textarea").first
    if not body.count():
        stop("본문 입력 칸이 없다")
    body.first.fill("확인할 것을 적습니다.")
    r.settle(400)
    before = body.first.input_value()
    marks = {}
    for label in ("제목", "글머리", "번호", "구분선"):
        button = r.in_main("button", label)
        if not button.count():
            continue
        button.first.click()
        r.settle(500)
        marks[label] = body.first.input_value()[:40]
    after = body.first.input_value()
    return {"ui_action": "서식 도구(제목·글머리·번호·구분선)를 차례로 누른다",
            "frontend_state": "커서 줄에 표식이 붙는다",
            "observed": {"marks": marks, "len": {"before": len(before), "after": len(after)}},
            "rendered": "본문 %d자 → %d자 · «%s»" % (len(before), len(after), after[:70]),
            "expected": {"source": "derived-check",
                         "rule": "서식 도구는 본문에 실제 표식을 남긴다",
                         "grew": len(after) > len(before)},
            "failed": None if len(after) > len(before)
                      else "서식 도구를 눌렀는데 본문이 안 바뀐다"}


flow("FF-0074", "user_new-ticket", "inline_edit",
     "본문 서식 도구(제목·글머리·번호·구분선)가 커서 줄에 표식을 붙이고 아래 미리보기가 갱신된다",
     _body_toolbar, route="/new-ticket", server=False)


def _create_ticket(r, ctx):
    title = "S21 인수 점검 티켓"
    box = r.page.get_by_placeholder("예: 서버 등록 IP 중복 방지")
    if not box.count():
        stop("제목 칸이 없다")
    box.first.fill(title)
    _pick_project(r)
    r.in_main("button", "티켓 추가").first.click()
    r.settle(2600)
    ctx["created_ticket_hash"] = r.hash_of()
    # 화면이 아니라 **서버**에 묻는다. 담당자가 없는 티켓은 «내 티켓» 에 안 나오고,
    # 미할당 목록은 조건·쪽에 걸려 있어 화면 대조가 자꾸 다른 것을 말한다.
    found = r.api_get("/api/tickets/team?q=" + title)
    items = (found or {}).get("items") or []
    return {"ui_action": "제목과 프로젝트를 채워 «티켓 추가» 를 누른다",
            "frontend_state": "POST /api/tickets → 목록으로 이동",
            "observed": {"title": title, "server_hits": len(items),
                         "landed": ctx["created_ticket_hash"]},
            "url_state": "→ %s" % r.hash_of(),
            "rendered": "주소 «%s» · 서버에서 %d건 · 본문 «%s»"
                        % (ctx["created_ticket_hash"], len(items), r.main_text(90)),
            "expected": {"source": "known-data",
                         "rule": "만든 티켓은 서버 목록에서 그 제목으로 다시 찾힌다",
                         "expect": title, "got": len(items)},
            "failed": None if items else "만들었다는데 서버 목록에 그 티켓이 없다"}


flow("FF-0069", "user_new-ticket", "create", "폼을 제출하면 티켓을 만든다",
     _create_ticket, route="/new-ticket", api="/api/tickets")


def _after_create_navigation(r, ctx):
    """만든 **직후**의 주소를 본다 — 앞 Flow 가 적어 둔 값이다.

    여기서 다시 재면 그 사이에 다른 Flow 가 화면을 옮겨 놓은 뒤를 보게 된다.
    """
    where = ctx.get("created_ticket_hash") or r.hash_of()
    return {"ui_action": "만든 직후 주소를 본다",
            "url_state": where,
            "observed": {"hash": where},
            "rendered": "주소 «%s» · 본문 «%s»" % (where, r.main_text(80)),
            "expected": {"source": "derived-check",
                         "rule": "생성에 성공하면 #/my-tickets 로 옮긴다",
                         "expect": "/my-tickets", "got": where},
            "failed": None if "my-tickets" in where
                      else "만든 뒤에도 새 티켓 폼에 그대로 있다: %s" % where}


flow("FF-0075", "user_new-ticket", "navigation", "생성 성공 시 #/my-tickets 로 이동한다",
     _after_create_navigation, server=False)


def _ai_help_links(r, ctx):
    links = r.page.locator('#main-content a[href*="#/chat"]')
    n = links.count()
    labels = [" ".join((links.nth(i).inner_text() or "").split())[:24]
              for i in range(min(n, 4))]
    return {"ui_action": "«AI 도우미» 링크를 센다",
            "observed": {"count": n, "labels": labels},
            "rendered": "#/chat 링크 %d개 %s" % (n, labels),
            "expected": {"source": "derived-check",
                         "rule": "폼 안내와 작성 도움 레일 두 곳에 있다",
                         "expect": ">=1", "got": n},
            "failed": None if n else "«AI 도우미» 로 가는 링크가 한 개도 없다"}


flow("FF-0076", "user_new-ticket", "navigation",
     "'AI 도우미'(#/chat) 링크가 폼 안내와 작성 도움 레일 두 곳에 있다",
     _ai_help_links, route="/new-ticket", server=False)


def _create_blocked_face(r, ctx):
    """프로젝트를 못 받으면 폼 대신 **안내만** 그린다.

    이 Flow 가 원장에 적혀 있던 원인(«Notion 연동 미설정»)은 S14 가 걷어서 이제 없다.
    갈래 자체는 살아 있고 조건만 바뀌었다 — 프로젝트 목록을 못 받는 상태다.
    """
    pattern = "**/api/tickets/projects**"
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었습니다."}'))
    try:
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(3000)
        face = r.main_text(200)
        submit = r.in_main("button", "티켓 추가").count()
    finally:
        r.page.unroute(pattern)
    return {"ui_action": "프로젝트 목록을 503 으로 끊고 화면을 다시 연다",
            "frontend_state": "폼 대신 안내",
            "observed": {"submit_buttons": submit, "face": face},
            "rendered": "본문 «%s» · 제출 버튼 %d개" % (face[:110], submit),
            "expected": {"source": "derived-check",
                         "rule": "만들 수 없는 상태면 폼 대신 이유를 말한다",
                         "face": face[:90]},
            "failed": None if ("만들 수 없습니다" in face or submit == 0)
                      else "프로젝트를 못 받았는데 폼이 그대로 서 있다"}


flow("FF-0077", "user_new-ticket", "permission_state",
     "프로젝트 목록을 못 받으면 폼 대신 '티켓을 만들 수 없습니다' 안내만 그린다",
     _create_blocked_face, route="/new-ticket", api="/api/tickets/projects")
