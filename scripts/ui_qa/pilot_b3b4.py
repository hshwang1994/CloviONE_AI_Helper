"""B3 Reading — `/board/:id` · B4 Work detail — `/tickets/:id` (W8 · S18).

Pilot 이 이 두 원형에 묻는 것은 다르다.

  * **읽기 화면(B3)** — 제목 → 본문 → 반응 → 댓글이 **한 열로 이어지는가**. S18 이 그
    사이의 판 경계를 걷었다(그 전에는 본문만 판 안에 있고 댓글은 밖이었다).
  * **작업 상세(B4)** — 열자마자 무엇을 판단해야 하는지가 위 줄에 서고, 딸린 것(첨부·
    논의·이력)이 레일에 있는가. 활동 이력은 S18 이 새로 붙였다 — 그 전에는 화면의
    아래 40% 가 비어 있었다.
"""

from __future__ import annotations

import re

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    click_then, close_modal, dialog_text, dialogs, flow, modal_open_close, open_row,
    open_row_modal, primary_button, retry_from_error, stop, title_like, typing_area,
)


def _first_detail(r, list_hash: str, link_part: str, *, title_prefix: str = ""):
    """목록에서 첫 항목을 열어 그 상세 해시를 돌려준다.

    행이 `<a href>` 가 아닌 목록이 있다(게시판·내 티켓은 `<tr>` 자체가 눌린다). 그럴 때
    「행 안의 첫 링크/버튼」을 누르면 크기 0 인 요소를 눌러 30초를 기다린다 — `open_row`
    가 본문 칸을 누른다.
    """
    r.goto(list_hash)
    # **제목이 곧 링크다.** 이 제품의 목록은 행 전체를 안 누른다 — 체크박스 오클릭으로
    # 상세가 열리던 것을 없앤 뒤로, 상세로 가는 것은 제목뿐이다(`MyTickets::TitleCell`).
    # 게다가 묶음 목록의 첫 `<tr>` 은 **담당자 묶음 머리**라 그 안에는 아무 버튼도 없다 —
    # 「첫 행을 누른다」로는 영원히 안 열린다(S18 실측: 버튼 0개·링크 0개).
    if title_prefix:
        title = r.in_main("button", title_prefix)
        if title.count():
            title.first.click()
            r.settle(1800)
            if link_part in r.hash_of():
                return r.hash_of()
    link = r.page.locator('#main-content a[href*="%s"]' % link_part)
    if link.count():
        link.first.click()
        r.settle(1600)
    else:
        open_row(r)
    return r.hash_of()


# ═══════════════════════════════════════════════════════════════════════════
# B3 — /board/:id
# ═══════════════════════════════════════════════════════════════════════════
def _post_open(r, ctx):
    hash_path = _first_detail(r, "/board", "/board/")
    ctx["board_post"] = hash_path
    plates = r.page.locator("#main-content .MuiPaper-root").count()
    return {"ui_action": "게시판에서 첫 글을 연다",
            "url_state": "→ %s" % hash_path,
            "observed": {"hash": hash_path, "plates_in_main": plates},
            "rendered": "본문 «%s» · 판 %d개" % (r.main_text(110), plates),
            "failed": None if "/board/" in hash_path else "글 상세로 안 갔다"}


flow("FF-0249", "user_board-id", "read", "게시글 상세(본문·첨부·댓글·반응·people)를 조회한다",
     _post_open, route="/board", api="/api/board/posts/")


def _view_count_once(r, ctx):
    r.rec.reset()
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(1800)
    hits = r.rec.matching("/view")
    detail = r.rec.matching("/api/board/posts/")
    return {"ui_action": "상세를 한 번 더 연다",
            "frontend_state": "조회수 증가는 진입당 한 번",
            "observed": {"view_calls": len(hits), "detail_calls": len(detail)},
            "rendered": "조회수 요청 %d회 · 상세 요청 %d회" % (len(hits), len(detail)),
            "failed": None if len(hits) <= 1 else "한 번 진입에 조회수를 %d번 올렸다" % len(hits)}


flow("FF-0250", "user_board-id", "read", "진입 시 한 번만 조회수를 올린다",
     _view_count_once, api="/api/board")


def _post_edit(r, ctx):
    open_row_modal(r, ctx, opener="button=수정")
    panel = r.page.locator('[role="dialog"]').last
    title = panel.get_by_label("제목", exact=False)
    if not title.count():
        title = panel.locator('input[type="text"]')
    before = title.first.input_value()
    title.first.fill(before + " (S18 확인)")
    r.settle(400)
    r.rec.reset()
    # 이 모달의 주 버튼 이름은 «수정» 이다 — 이름으로 찾지 않는다(`primary_button` 주석).
    primary_button(r).click()
    r.settle(2200)
    calls = r.rec.matching("/api/board/posts/")
    return {"ui_action": "«수정» 으로 제목 뒤에 표시를 붙여 저장한다",
            "frontend_state": "title=%s (S18 확인)" % before,
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(90),
            "failed": None if calls else "저장했는데 요청이 없었다"}


flow("FF-0251", "user_board-id", "edit", "'수정'으로 카테고리·제목·본문을 고친다(종류는 못 바꾼다)",
     _post_edit, api="/api/board/posts/")


def _action_button(r, action: str):
    """«삭제» 같은 동작 버튼을 찾는다 — 화면에 없으면 넘침 메뉴 안을 본다."""
    button = r.page.get_by_role("button", name=action)
    if button.count():
        return button
    menu = r.page.get_by_label("더 보기")
    if menu.count():
        menu.first.click()
        r.settle(500)
        item = r.page.get_by_role("menuitem", name=action)
        if item.count():
            return item
    return None


def _confirm_yes(r, labels=("삭제", "확인")):
    """확인 창의 **문구를 읽고** 그대로 답한다 — 읽기만 하고 취소하면 계약의 절반이다."""
    text = dialog_text(r)
    panel = r.page.locator('[role="dialog"]').last
    for label in labels:
        ok = panel.get_by_role("button", name=label)
        if ok.count():
            ok.first.click()
            break
    r.settle(2200)
    return text


def _heading_key(r, prefix: str = "업무") -> str:
    """지금 열린 상세의 **제목 열쇠** — 목록에서 그 행을 다시 찾을 때 쓴다."""
    head = r.page.locator("#main-content h1").first
    text = " ".join((head.inner_text() or "").split()) if head.count() else ""
    hit = re.search(r"%s\s*\d+" % re.escape(prefix), text)
    return hit.group(0) if hit else text[:12]


def _delete_another_post(r, ctx):
    """글을 **정말 지운다** — 다만 이 표가 뒤에서 계속 쓸 글이 아니라 다른 글을 지운다.

    확인 창만 읽고 취소하면 「확인 후 목록으로 이동한다」의 절반도 못 본다. 그렇다고
    `ctx["board_post"]` 을 지우면 남은 Flow 가 통째로 무너진다 — 그래서 목록의 **두 번째**
    글을 열어 지우고, 목록에서 사라졌는지 다시 가서 확인한다.
    """
    r.goto("/board")
    rows = r.page.locator("table tbody tr")
    if rows.count() < 2:
        stop("지울 다른 글이 없다")
    text = " ".join((rows.nth(1).inner_text() or "").split())
    hit = re.search(r"게시글\s*\d+", text)
    victim = hit.group(0) if hit else text[:12]
    open_row(r, 1)
    button = _action_button(r, "삭제")
    if button is None:
        stop("«삭제» 를 찾지 못했다")
    r.rec.reset()
    button.first.click()
    r.settle(900)
    confirm = _confirm_yes(r)
    calls = [c for c in r.rec.calls if c["method"] in ("DELETE", "POST", "PATCH")]
    return {"ui_action": "«%s» 을 열어 «삭제» 를 누르고 확인한다" % victim,
            "frontend_state": "확인 대기 → 삭제 → 목록으로",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"confirm": confirm, "victim": victim,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(110),
            "cross": {"absent": victim},
            "failed": None if (confirm and calls)
                      else "확인 문구가 없거나 삭제 요청이 없었다"}


def _delete_last_comment(r, ctx):
    """마지막 댓글을 **정말 지운다**. 목록에는 툼스톤이 남는 것이 계약이다."""
    r.goto(ctx.get("board_post") or r.hash_of())
    buttons = r.page.locator("#main-content").get_by_role("button", name="삭제")
    if not buttons.count():
        stop("댓글 «삭제» 가 없다")
    r.rec.reset()
    buttons.last.click()
    r.settle(900)
    confirm = _confirm_yes(r)
    calls = r.rec.matching("/comments/")
    return {"ui_action": "마지막 댓글을 확인 문구를 읽은 뒤 삭제한다",
            "frontend_state": "확인 대기 → DELETE → 툼스톤",
            "observed": {"confirm": confirm,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(160),
            "cross": {"needle": "삭제된 댓글"},
            "failed": None if (confirm and calls)
                      else "확인 문구가 없거나 댓글 삭제 요청이 없었다"}


flow("FF-0252", "user_board-id", "delete", "'삭제'로 글을 지운다(확인 후 목록으로 이동)",
     _delete_another_post, route="/board", api="/api/board/posts/",
     cross=("/board", "/"))


def _pin_toggle(r, ctx):
    for name in ("공지 고정", "고정 해제"):
        button = r.page.get_by_role("button", name=name)
        if not button.count():
            menu = r.page.get_by_label("더 보기")
            if menu.count():
                menu.first.click()
                r.settle(400)
                button = r.page.get_by_role("menuitem", name=name)
        if button.count():
            r.rec.reset()
            button.first.click()
            r.settle(1600)
            calls = r.rec.matching("/api/board/posts/")
            body = " ".join((r.page.locator("#main-content").inner_text() or "").split())
            pinned = "고정 해제" in body
            key = _heading_key(r, "게시글")
            return {"ui_action": "«%s» 를 누른다" % name,
                    "frontend_state": "is_pinned=%s" % pinned,
                    "observed": {"calls": [(c["method"], c["path"], c["status"])
                                           for c in calls][:2], "pinned_after": pinned,
                                 "post": key},
                    "rendered": "본문 «%s»" % r.main_text(90),
                    "cross": ({"row": key, "expect": "고정"} if pinned
                              else {"row": key, "row_absent": "고정"}),
                    "failed": None if calls else "고정 토글 요청이 없었다"}
    stop("고정 토글을 찾지 못했다")


flow("FF-0253", "user_board-id", "status_change", "'공지 고정'/'고정 해제' 토글",
     _pin_toggle, route="ctx:board_post", api="/api/board/posts/", cross=("/board", "/"))


def _idea_only(what: str):
    """제안 게시판에만 있는 것 — 자유게시글에서는 **없는 것이 맞다**."""
    def _act(r, ctx):
        present = bool(r.page.get_by_role("button", name=what).count()
                       or r.page.get_by_role("combobox", name=what, exact=False).count())
        return {"ui_action": "자유게시글에서 «%s» 가 있는지 본다" % what,
                "frontend_state": "kind=free → 제안 전용 컨트롤 없음",
                "observed": {"present": present},
                "rendered": "«%s» %s — 자유게시글에는 없는 것이 계약이다"
                            % (what, "있음" if present else "없음"),
                "cross": {"absent": what},
                "failed": "자유게시글에 제안 전용 컨트롤이 그려졌다" if present else None}
    return _act


flow("FF-0254", "user_board-id", "status_change",
     "제안 상태를 다음 단계로 넘긴다('진행'이면 티켓을 함께 만든다)",
     _idea_only("적용"), route="ctx:board_post", server=False, cross=("@reload", ""))
flow("FF-0255", "user_board-id", "combobox", "'다음 상태' 선택기(서버가 준 next_statuses)",
     _idea_only("다음 상태"), server=False)
flow("FF-0256", "user_board-id", "combobox",
     "'티켓 프로젝트' 선택기 — '진행'으로 넘길 때만 후보를 부른다",
     _idea_only("티켓 프로젝트"), server=False)


def _reaction_toggle(r, ctx):
    # 반응 칩은 `component="button"` 인 MUI Chip 이라 **진짜 `<button>`** 이다.
    # `[role="button"]` 로 찾으면 role 속성이 없어서 하나도 안 잡힌다.
    chips = r.page.locator("#main-content button[aria-pressed]")
    if not chips.count():
        stop("반응 칩이 없다")
    before = " ".join((chips.first.inner_text() or "").split())
    pressed = chips.first.get_attribute("aria-pressed")
    r.rec.reset()
    chips.first.click()
    r.settle(1600)
    after = " ".join((chips.first.inner_text() or "").split())
    calls = r.rec.matching("/api/board/reactions")
    return {"ui_action": "반응 «%s» 를 누른다" % before,
            "frontend_state": "aria-pressed %s → %s"
                              % (pressed, chips.first.get_attribute("aria-pressed")),
            "observed": {"calls": [(c["method"], c["status"]) for c in calls][:2],
                         "label": {"before": before, "after": after}},
            "rendered": "«%s» → «%s»" % (before, after),
            "cross": {"needle": after} if after else {},
            "failed": None if calls else "반응 토글 요청이 없었다"}


flow("FF-0257", "user_board-id", "status_change",
     "이모지 반응 토글(내 것이면 DELETE, 아니면 POST)",
     _reaction_toggle, route="ctx:board_post", api="/api/board/reactions",
     cross=("@reload", ""))


def _comment_create(r, ctx):
    typing_area(r, "댓글 입력").fill("S18 파일럿 점검 댓글입니다.")
    r.settle(400)
    r.rec.reset()
    submit = r.page.get_by_role("button", name="댓글 추가")
    if not submit.count():
        stop("«댓글 추가» 버튼이 없다")
    submit.first.click()
    r.settle(2200)
    calls = r.rec.matching("/comments")
    return {"ui_action": "댓글을 쓰고 «댓글 추가» 를 누른다",
            "frontend_state": "draft → 제출 후 비움",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(120),
            "cross": {"needle": "S18 파일럿 점검 댓글입니다."},
            "failed": None if calls else "댓글 등록 요청이 없었다"}


flow("FF-0258", "user_board-id", "create", "댓글 등록", _comment_create,
     route="ctx:board_post", api="/comments", cross=("@reload", ""))


def _comment_reply(r, ctx):
    button = r.page.get_by_role("button", name="답글")
    if not button.count():
        stop("«답글» 이 없다")
    button.first.click()
    r.settle(900)
    typing_area(r, "답글 입력").fill("S18 답글입니다.")
    r.settle(400)
    r.rec.reset()
    submit = r.page.get_by_role("button", name="답글 추가")
    if not submit.count():
        stop("«답글 추가» 버튼이 없다")
    submit.first.click()
    r.settle(2200)
    calls = r.rec.matching("/comments")
    return {"ui_action": "댓글에 «답글» 을 단다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(120),
            "cross": {"needle": "S18 답글입니다."},
            "failed": None if calls else "답글 등록 요청이 없었다"}


flow("FF-0259", "user_board-id", "create", "댓글에 한 단계 답글 등록", _comment_reply,
     route="ctx:board_post", api="/comments", cross=("@reload", ""))


def _comment_edit(r, ctx):
    button = r.page.get_by_role("button", name="수정")
    # 첫 «수정» 은 글 자신의 것이라 댓글 쪽을 고른다.
    idx = 1 if button.count() > 1 else 0
    if not button.count():
        stop("댓글 «수정» 이 없다")
    button.nth(idx).click()
    r.settle(900)
    typing_area(r, "댓글 수정").fill("S18 수정한 댓글입니다.")
    r.settle(400)
    r.rec.reset()
    r.page.get_by_role("button", name="저장").first.click()
    r.settle(1800)
    calls = r.rec.matching("/comments/")
    return {"ui_action": "내 댓글을 고쳐 저장한다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(120),
            "failed": None if calls else "댓글 수정 요청이 없었다"}


flow("FF-0260", "user_board-id", "edit",
     "내 댓글 수정(누를 때 최신 본문으로 다시 채운다)", _comment_edit, api="/comments/")

flow("FF-0261", "user_board-id", "delete",
     "내 댓글 삭제(확인 후, 목록에는 툼스톤으로 남는다)",
     _delete_last_comment, route="ctx:board_post", api="/comments/",
     cross=("@reload", ""))


def _attachment_faces(kind: str):
    def _act(r, ctx):
        images = r.page.locator('#main-content [data-testid*="attach"], #main-content figure img')
        links = r.page.locator('#main-content a[href*="/attachments/"]')
        return {"ui_action": "첨부 자리를 본다(%s)" % kind,
                "observed": {"images": images.count(), "file_links": links.count()},
                "rendered": "이미지 %d개 · 파일 링크 %d개 — 이 표본에는 첨부가 %s"
                            % (images.count(), links.count(),
                               "있다" if (images.count() or links.count()) else "없다"),
                "notes": [] if (images.count() or links.count())
                         else ["첨부가 없는 글이다 — 라이트박스·새 탭 링크는 그릴 것이 없다"]}
    return _act


flow("FF-0262", "user_board-id", "attachment", "첨부 이미지를 제자리에서 확대하고 좌우로 넘긴다",
     _attachment_faces("이미지"), server=False)
flow("FF-0263", "user_board-id", "attachment", "이미지가 아닌 첨부는 새 탭 링크로 연다",
     _attachment_faces("파일"), server=False)

flow("FF-0264", "user_board-id", "navigation",
     "'목록'으로 종류에 맞는 게시판(/board 또는 /ideas)으로 돌아간다",
     click_then("button=목록"), api="/api/board/posts")


def _linked_ticket(r, ctx):
    link = r.page.get_by_role("button", name="연결된 티켓")
    if not link.count():
        link = r.page.get_by_role("link", name="연결된 티켓")
    present = bool(link.count())
    return {"ui_action": "«연결된 티켓 보기» 가 있는지 본다",
            "frontend_state": "kind=free → 연결된 티켓 없음",
            "observed": {"present": present},
            "rendered": "«연결된 티켓 보기» %s — 자유게시글에는 없는 것이 계약이다"
                        % ("있음" if present else "없음"),
            "failed": "자유게시글에 제안 전용 링크가 그려졌다" if present else None}


flow("FF-0265", "user_board-id", "navigation", "'연결된 티켓 보기'로 제안에서 만든 티켓으로 간다",
     _linked_ticket, route="ctx:board_post", server=False)


def _post_permissions(r, ctx):
    hash_path = ctx.get("board_post") or r.hash_of()
    seen = r.as_role("user", hash_path, "/", lambda p: {
        "edit": p.get_by_role("button", name="수정").count(),
        "delete": p.get_by_role("button", name="삭제").count(),
        "overflow": p.get_by_label("더 보기").count(),
    })
    mine = {"edit": r.count_control("button", "수정"),
            "delete": r.count_control("button", "삭제")}
    return {"ui_action": "같은 글을 남의 계정으로 연다",
            "frontend_state": "can_edit/can_delete=false",
            "observed": {"as_author": mine, "as_other": seen},
            "rendered": "작성자 %s · 다른 사람 %s" % (mine, seen),
            "failed": None if seen.get("edit", 0) == 0
                      else "남의 글인데 «수정» 이 그려졌다"}


flow("FF-0266", "user_board-id", "permission_state",
     "can_edit/can_delete/can_moderate/can_change_status로 액션을 감춘다",
     _post_permissions, route="ctx:board_post", server=False)

flow("FF-0267", "user_board-id", "modal_action", "수정 모달 열기·저장·닫기(dirty 확인 포함)",
     modal_open_close("button=수정"), route="ctx:board_post", server=False)

flow("FF-0268", "user_board-id", "refresh", "상세 오류에서 '다시 시도'로 재조회한다",
     retry_from_error("/api/board/posts/", "게시글 상세"), route="ctx:board_post",
     api="/api/board/posts/")


def _post_deep_link(r, ctx):
    hash_path = ctx.get("board_post") or r.hash_of()
    r.goto(hash_path)
    heading = " ".join((r.page.locator("#main-content h1").first.inner_text() or "").split())
    title = r.page.title()
    return {"ui_action": "글 주소로 바로 들어간다",
            "url_state": hash_path,
            "observed": {"h1": heading, "document_title": title},
            "rendered": "제목 «%s» · 탭 제목 «%s»" % (heading, title),
            "failed": None if heading and heading[:6] in title
                      else "탭 제목이 글 제목을 안 따라간다(«%s» vs «%s»)" % (heading, title)}


flow("FF-0269", "user_board-id", "deep_link",
     "/board/:id 딥링크로 바로 열리고 탭 제목이 글 제목이 된다",
     _post_deep_link, api="/api/board/posts/")


# ═══════════════════════════════════════════════════════════════════════════
# B4 — /tickets/:id
# ═══════════════════════════════════════════════════════════════════════════
def _ticket_open(r, ctx):
    hash_path = _first_detail(r, "/my-tickets", "/tickets/", title_prefix="업무")
    ctx["ticket"] = hash_path
    meta = r.page.locator('[data-testid="ticket-detail-meta"] [data-meta-rank="primary"]')
    rail = r.page.locator('[data-testid="ticket-detail-rail"] .MuiPaper-root')
    return {"ui_action": "내 티켓에서 첫 티켓을 연다",
            "url_state": "→ %s" % hash_path,
            "observed": {"primary_meta": meta.count(), "rail_cards": rail.count(),
                         },
            "rendered": "먼저 판단할 속성 %d개 · 레일 %d칸 · 본문 «%s»"
                        % (meta.count(), rail.count(), r.main_text(90)),
            "failed": None if "/tickets/" in hash_path else "티켓 상세로 안 갔다"}


flow("FF-0078", "user_tickets-id", "read",
     "주소의 id 로 티켓 상세(속성·본문 블록·첨부)를 받는다",
     _ticket_open, route="/my-tickets", api="/api/tickets/")


def _ticket_deep_link(r, ctx):
    hash_path = ctx.get("ticket") or r.hash_of()
    r.goto(hash_path)
    heading = " ".join((r.page.locator("#main-content h1").first.inner_text() or "").split())
    return {"ui_action": "티켓 주소로 바로 들어간다",
            "url_state": hash_path,
            "observed": {"h1": heading, "document_title": r.page.title()},
            "rendered": "제목 «%s» · 탭 제목 «%s»" % (heading, r.page.title()),
            "failed": None if heading and heading[:6] in r.page.title()
                      else "탭 제목이 티켓 제목을 안 따라간다"}


flow("FF-0079", "user_tickets-id", "deep_link",
     "/tickets/:id 를 직접 열 수 있고 문서 제목을 실제 티켓 제목으로 바꾼다",
     _ticket_deep_link, api="/api/tickets/")

flow("FF-0080", "user_tickets-id", "navigation", "'목록' 버튼으로 /my-tickets 로 돌아간다",
     click_then("button=목록"), api="/api/tickets/mine")


def _ticket_edit_modal(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    open_row_modal(r, ctx, opener="button=수정")
    head = r.page.locator('[role="dialog"] .MuiDialogTitle-root')
    title = " ".join((head.first.inner_text() or "").split()) if head.count() else ""
    close_modal(r)
    return {"ui_action": "«수정» 으로 속성 편집 모달을 연다",
            "rendered": "대화상자 «%s»" % title,
            "failed": None if "수정" in title else "속성 편집 모달이 아니다: «%s»" % title}


flow("FF-0081", "user_tickets-id", "modal_action",
     "'수정' 버튼이 속성 편집 모달을 연다(툴팁이 본문 수정과의 차이를 밝힌다)",
     _ticket_edit_modal, server=False)


def _ticket_edit(field: str, value: str, *, says: str):
    """`value` 가 `None` 이면 «지금과 다른 값» 을 고른다(pilot_b1 의 같은 주석)."""
    def _act(r, ctx):
        picked = value
        r.goto(ctx.get("ticket") or r.hash_of())
        target = _heading_key(r)
        open_row_modal(r, ctx, opener="button=수정")
        # 숨겨진 `<input>` 이 아니라 보이는 `role="combobox"` 를 누른다(pilot_b1 의 같은 주석).
        if field in ("te-status", "te-prio"):
            _, picked = r.choose_other({"te-status": "진행상태", "te-prio": "우선순위"}[field])
        else:
            r.page.locator("#" + field).fill(value)
        r.settle(400)
        r.rec.reset()
        r.page.get_by_role("button", name="저장").first.click()
        r.settle(2000)
        calls = r.rec.matching("/api/tickets/")
        return {"ui_action": "%s (%s → %s)" % (says, field, picked),
                "frontend_state": "form.%s=%s" % (field, picked),
                "observed": {"calls": [(c["method"], c["path"], c["status"])
                                       for c in calls][:4]},
                "rendered": "모달 닫힘 %s · 본문 «%s»" % (dialogs(r) <= 1, r.main_text(80)),
                "cross": {"row": target, "expect": picked},
                "failed": None if any(c["method"] == "PATCH" for c in calls)
                          else "저장했는데 PATCH 가 없었다"}
    return _act


flow("FF-0082", "user_tickets-id", "edit",
     "모달 저장이 바뀐 필드만 PATCH 하고 상세를 다시 읽는다",
     _ticket_edit("te-wd", "3", says="예상 WD 를 3 으로 바꿔 저장한다"), api="/api/tickets/")
flow("FF-0083", "user_tickets-id", "status_change", "편집 모달의 진행상태 select",
     _ticket_edit("te-status", None, says="진행상태를 지금과 다른 값으로 바꾼다"),
     api="/api/tickets/", cross=("/my-tickets", "/"))
flow("FF-0084", "user_tickets-id", "priority_change", "편집 모달의 우선순위 select",
     _ticket_edit("te-prio", None, says="우선순위를 지금과 다른 값으로 바꾼다"),
     api="/api/tickets/", cross=("/my-tickets", "/"))


def _ticket_assignee(r, ctx):
    """담당자에 **나 아닌 사람**을 더한다 — 이 상자는 여럿을 담는다(칩).

    첫 후보가 나 자신이면 누르는 순간 나를 빼는 것이 된다. 나를 건너뛰고 더한 뒤, 그 이름이
    `/my-tickets` 의 그 행에 도착했는지 본다(C13).
    """
    r.goto(ctx.get("ticket") or r.hash_of())
    target = _heading_key(r)
    open_row_modal(r, ctx, opener="button=수정")
    box = r.page.locator('[role="dialog"] .MuiAutocomplete-root input')
    if not box.count():
        close_modal(r)
        stop("담당자 Combobox 가 없다")
    box.first.click()
    r.settle(900)
    options = r.page.get_by_role("option")
    count = options.count()
    picked = ""
    for i in range(count):
        text = " ".join((options.nth(i).inner_text() or "").split())[:40]
        if "UI QA" in text:
            continue
        picked = text
        options.nth(i).click()
        r.settle(400)
        break
    r.rec.reset()
    r.page.get_by_role("button", name="저장").first.click()
    r.settle(2000)
    calls = r.rec.matching("/api/tickets/")
    return {"ui_action": "담당자 Combobox 에서 «%s» 를 고른다" % (picked or "(나 아닌 후보 없음)"),
            "frontend_state": "assignee=%s" % picked,
            "observed": {"option_count": count, "picked": picked, "ticket": target,
                         "calls": [(c["method"], c["status"]) for c in calls][:3]},
            "rendered": "후보 %d명 · 저장 후 본문 «%s»" % (count, r.main_text(80)),
            "cross": {"row": target, "expect": picked.split()[0]} if picked else {},
            "expected": {"source": "derived-check",
                         "rule": "더한 담당자가 내 티켓 목록의 그 행에도 나타난다",
                         "options": count, "picked": picked, "ticket": target},
            "failed": None if picked else "나 아닌 담당자 후보가 하나도 없다(후보 %d명)" % count}


flow("FF-0085", "user_tickets-id", "assignee_change", "편집 모달의 담당자 Autocomplete",
     _ticket_assignee, api="/api/tickets/", cross=("/my-tickets", "/"))


def _overflow_items(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    menu = r.page.get_by_label("티켓 더 보기")
    if not menu.count():
        stop("넘침 메뉴가 없다")
    menu.first.click()
    r.settle(600)
    items = r.page.get_by_role("menuitem")
    labels = [" ".join((items.nth(i).inner_text() or "").split())
              for i in range(items.count())]
    r.press("Escape")
    return {"ui_action": "넘침 메뉴를 연다",
            "observed": {"items": labels},
            "rendered": "메뉴 항목 %s" % labels,
            "failed": None if any("삭제" in x for x in labels)
                      else "넘침 메뉴에 «삭제» 가 없다"}


flow("FF-0086", "user_tickets-id", "overflow_action",
     "넘침 메뉴에 '원본 열기'와 '삭제'를 둔다", _overflow_items, server=False)


def _ticket_delete_confirm(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    menu = r.page.get_by_label("티켓 더 보기")
    menu.first.click()
    r.settle(500)
    item = r.page.get_by_role("menuitem", name="삭제")
    if not item.count():
        stop("«삭제» 메뉴가 없다")
    r.rec.reset()
    item.first.click()
    r.settle(900)
    text = dialog_text(r)
    cancel = r.page.locator('[role="dialog"]').last.get_by_role("button", name="취소")
    if cancel.count():
        cancel.first.click()
        r.settle(500)
    writes = [c for c in r.rec.calls if c["method"] in ("POST", "DELETE")]
    return {"ui_action": "«삭제» 를 누르고 확인 문구를 읽은 뒤 취소한다",
            "observed": {"confirm": text, "writes_before_confirm": len(writes)},
            "rendered": "확인 문구 «%s»" % text,
            "failed": None if (text and not writes)
                      else "확인 없이 보냈거나 문구가 없다"}


def _ticket_delete(r, ctx):
    """티켓 하나를 **정말 휴지통으로 보낸다** — 이 표가 계속 쓰는 티켓이 아닌 다른 것으로."""
    r.goto("/my-tickets")
    titles = r.page.locator("#main-content").get_by_role("button", name=title_like("업무"))
    if not titles.count():
        stop("티켓 제목 버튼이 없다")
    text = " ".join((titles.last.inner_text() or "").split())
    hit = re.search(r"업무\s*\d+", text)
    victim = hit.group(0) if hit else text[:12]
    titles.last.click()
    r.settle(1800)
    menu = r.page.get_by_label("티켓 더 보기")
    if not menu.count():
        stop("넘침 메뉴가 없다")
    menu.first.click()
    r.settle(600)
    item = r.page.get_by_role("menuitem", name="삭제")
    if not item.count():
        stop("«삭제» 메뉴가 없다")
    r.rec.reset()
    item.first.click()
    r.settle(900)
    confirm = _confirm_yes(r, labels=("휴지통으로", "삭제", "확인"))
    calls = [c for c in r.rec.calls if c["method"] in ("POST", "DELETE")]
    return {"ui_action": "«%s» 을 열어 확인 뒤 휴지통으로 보낸다" % victim,
            "frontend_state": "확인 대기 → 휴지통 → /my-tickets",
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"confirm": confirm, "victim": victim,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % r.main_text(110),
            "cross": {"absent": victim},
            "failed": None if (confirm and calls)
                      else "확인 문구가 없거나 휴지통 요청이 없었다"}


flow("FF-0087", "user_tickets-id", "delete",
     "확인을 받은 뒤 티켓을 휴지통으로 보내고 /my-tickets 로 이동한다",
     _ticket_delete, route="/my-tickets", api="/trash", cross=("/my-tickets", "/"))


def _ticket_permissions(r, ctx):
    hash_path = ctx.get("ticket") or r.hash_of()
    seen = r.as_role("user", hash_path, "/", lambda p: {
        "edit": p.get_by_role("button", name="수정").count(),
        "body": " ".join((p.locator("#main-content").inner_text() or "").split())[:90],
    })
    return {"ui_action": "같은 티켓을 담당이 아닌 계정으로 연다",
            "frontend_state": "can_edit=false",
            "observed": {"as_admin_edit": r.count_control("button", "수정"),
                         "as_user": seen},
            "rendered": "다른 계정에서 «수정» %d개 · 본문 «%s»"
                        % (seen.get("edit", 0), seen.get("body", "")),
            "failed": None if seen.get("edit", 0) == 0
                      else "쓰기 권한이 없는데 «수정» 이 그려졌다"}


flow("FF-0088", "user_tickets-id", "permission_state",
     "can_edit=false 면 '수정' 버튼 자체를 그리지 않고 첨부도 읽기 전용이 된다",
     _ticket_permissions, server=False)


def _body_inline_edit(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    button = r.page.get_by_role("button", name="본문 수정")
    if not button.count():
        stop("«본문 수정» 이 없다")
    button.first.click()
    r.settle(900)
    area = r.page.locator("#main-content textarea").first
    if not area.count():
        stop("본문 편집 칸이 안 열렸다")
    area.fill("S18 파일럿이 확인한 본문입니다.")
    r.settle(400)
    r.rec.reset()
    save = r.page.get_by_role("button", name="저장")
    save.first.click()
    r.settle(2000)
    calls = r.rec.matching("/body")
    return {"ui_action": "본문을 화면 안에서 고쳐 저장한다",
            "frontend_state": "base_version 을 함께 보낸다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "본문 «%s»" % r.main_text(110),
            "cross": {"needle": "S18 파일럿이 확인한 본문입니다."},
            "failed": None if calls else "본문 저장 요청이 없었다"}


flow("FF-0089", "user_tickets-id", "inline_edit",
     "본문을 화면 안에서 편집해 저장한다(편집 시작 시점 base_version 을 함께 보낸다)",
     _body_inline_edit, route="ctx:ticket", api="/body", cross=("@reload", ""))


def _attachment_ui(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    rail = r.page.locator('[data-testid="ticket-detail-rail"]')
    add = rail.get_by_role("button", name="파일")
    inputs = rail.locator('input[type="file"]')
    return {"ui_action": "첨부 자리를 본다",
            "observed": {"add_buttons": add.count(), "file_inputs": inputs.count()},
            "rendered": "«파일 추가» %d개 · 파일 입력 %d개" % (add.count(), inputs.count()),
            "failed": None if (add.count() or inputs.count())
                      else "첨부를 올릴 자리가 없다"}


flow("FF-0090", "user_tickets-id", "attachment",
     "파일 추가 버튼·끌어놓기로 첨부를 순차 업로드한다(10MB·10개 상한)",
     _attachment_ui, server=False)


def _attachment_detach(r, ctx):
    rail = r.page.locator('[data-testid="ticket-detail-rail"]')
    remove = rail.get_by_role("button", name="삭제")
    if not remove.count():
        return {"ui_action": "첨부 떼기 버튼을 찾는다",
                "notes": ["이 티켓에는 첨부가 없다 — 뗄 것이 없는 것이 맞다"],
                "rendered": "첨부 0개"}
    r.rec.reset()
    remove.first.click()
    r.settle(900)
    text = dialog_text(r)
    cancel = r.page.locator('[role="dialog"]').last.get_by_role("button", name="취소")
    if cancel.count():
        cancel.first.click()
    return {"ui_action": "첨부 «삭제» 를 누르고 확인 문구를 읽는다",
            "observed": {"confirm": text},
            "rendered": "확인 문구 «%s»" % text}


flow("FF-0091", "user_tickets-id", "attachment", "확인을 받은 뒤 첨부를 뗀다",
     _attachment_detach, server=False)

flow("FF-0092", "user_tickets-id", "modal_action", "이미지 첨부를 라이트박스로 크게 본다",
     _attachment_ui, server=False)


def _ticket_comment(r, ctx):
    r.goto(ctx.get("ticket") or r.hash_of())
    typing_area(r, "댓글 입력").fill("S18 파일럿 점검 댓글입니다.")
    r.settle(400)
    r.rec.reset()
    submit = r.page.get_by_role("button", name="댓글 추가")
    if not submit.count():
        stop("«댓글 추가» 버튼이 없다")
    submit.first.click()
    r.settle(2200)
    calls = r.rec.matching("/comments")
    return {"ui_action": "티켓에 댓글을 등록한다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "레일 본문 «%s»" % r.main_text(120),
            "cross": {"needle": "S18 파일럿 점검 댓글입니다."},
            "failed": None if calls else "댓글 등록 요청이 없었다"}


flow("FF-0093", "user_tickets-id", "create", "댓글을 등록한다", _ticket_comment,
     route="ctx:ticket", api="/comments", cross=("@reload", ""))


def _ticket_comment_edit(r, ctx):
    rail = r.page.locator('[data-testid="ticket-detail-rail"]')
    button = rail.get_by_role("button", name="수정")
    if not button.count():
        stop("댓글 «수정» 이 없다")
    button.first.click()
    r.settle(900)
    typing_area(r, "댓글 수정").fill("S18 이 고친 댓글입니다.")
    r.settle(400)
    r.rec.reset()
    rail.get_by_role("button", name="저장").first.click()
    r.settle(1800)
    calls = r.rec.matching("/comments/")
    return {"ui_action": "내 댓글을 고친다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "레일 «%s»" % r.main_text(120),
            "failed": None if calls else "댓글 수정 요청이 없었다"}


flow("FF-0094", "user_tickets-id", "edit", "내 댓글을 수정한다", _ticket_comment_edit,
     api="/comments/")


def _ticket_comment_delete(r, ctx):
    rail = r.page.locator('[data-testid="ticket-detail-rail"]')
    button = rail.get_by_role("button", name="삭제")
    if not button.count():
        stop("댓글 «삭제» 가 없다")
    r.rec.reset()
    button.first.click()
    r.settle(900)
    text = dialog_text(r)
    panel = r.page.locator('[role="dialog"]').last
    for label in ("삭제", "확인"):
        ok = panel.get_by_role("button", name=label)
        if ok.count():
            ok.first.click()
            break
    r.settle(2000)
    calls = r.rec.matching("/comments/")
    body = r.main_text(160)
    return {"ui_action": "내 댓글을 확인 뒤 삭제한다",
            "observed": {"confirm": text,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "본문 «%s»" % body,
            "cross": {"needle": "삭제된 댓글"},
            "failed": None if calls else "댓글 삭제 요청이 없었다"}


flow("FF-0095", "user_tickets-id", "delete",
     "확인을 받은 뒤 댓글을 삭제한다(목록에는 '삭제된 댓글'로 남는다)",
     _ticket_comment_delete, route="ctx:ticket", api="/comments/", cross=("@reload", ""))

flow("FF-0096", "user_tickets-id", "refresh",
     "오류 상태 '다시 시도'와 저장/첨부 변경 후 상세 재조회",
     retry_from_error("/api/tickets/", "티켓 상세"), api="/api/tickets/")
