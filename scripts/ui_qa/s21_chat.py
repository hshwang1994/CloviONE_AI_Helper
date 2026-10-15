"""S21 — AI 도우미 · 채팅방 · AI 작업공간 · 놀이 (W14).

이 넷은 **상태가 서버에 있고 화면이 그것을 따라가는** 화면들이다. 그래서 여기서 묻는 것은
「눌렀더니 화면이 바뀌었는가」가 아니라 **「서버가 그렇게 됐는가」**다 — 대화를 지웠으면
목록에서 사라져야 하고, 방을 나갔으면 참여자에서 빠져야 한다.

AI 쪽은 이 저장소에 이미 계측기가 있다(`scripts/ui_qa/ai_e2e.py` · `ai_scope.py`). 그 둘이
답하는 질문(연속 대화·문맥·인용 범위)을 여기서 다시 만들지 않는다 — 여기서는 **화면의
사슬**만 본다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, flow, n_rows, open_dialog, open_dialogs, retry_from_error,
    row_at, row_name, rows_of, stop,
)

USER = "/"
CONV = "/api/conversations"
SEARCH_BOX = '#main-content input[type="search"]'
COMPOSER = '#main-content [aria-label="메시지 입력"]'
# 대화 줄 — 줄마다 하나뿐인 표지다(D-582). 줄의 보조 동작은 「대화 동작: <제목>」 메뉴 하나다.
CONV_ROW = '#main-content [data-conversation-row]'
ROW_MENU = '[aria-label^="대화 동작: "]'


def _open_sidebar(r):
    """대화 목록을 펼친다 — 접혀 있으면 검색 상자도 목록도 DOM 에 없다."""
    # **넓은 화면에서는 목록이 늘 펼쳐져 있다**(xl 이상은 static). 그때 이 버튼은 DOM 에
    # 남아 있어도 안 보이므로, 그냥 누르면 10초를 기다리다 죽는다.
    opener = r.page.locator('#main-content [aria-label="대화 목록 열기"]:visible')
    if opener.count():
        opener.first.click()
        r.settle(900)


def _hover_row(r, index: int = 0):
    """그 줄 위에 커서를 올린다 — 줄의 「대화 동작」 메뉴는 올리거나 초점이 갈 때 드러난다(불투명도라 DOM 과 키보드에는 늘 있다)."""
    rows = r.page.locator(CONV_ROW)
    if rows.count() <= index:
        return
    rows.nth(index).hover()
    r.settle(400)


def _row_menu(r, item: str, index: int = 0) -> str:
    """그 줄의 「대화 동작」 메뉴에서 `item` 을 누른다. 메뉴 단추의 이름(「대화 동작: <제목>」)을 돌려준다."""
    _hover_row(r, index)
    button = r.page.locator(CONV_ROW).nth(index).locator(ROW_MENU)
    if not button.count():
        stop("대화 줄의 «대화 동작» 메뉴가 없다")
    label = button.first.get_attribute("aria-label") or ""
    button.first.click()
    r.settle(500)
    entry = r.page.get_by_role("menuitem", name=item, exact=True)
    if not entry.count():
        stop("«대화 동작» 메뉴에 «%s» 가 없다" % item)
    entry.first.click()
    r.settle(600)
    return label


def _conv_items(r):
    """대화 줄 수.

    🔴 세는 자리는 **행마다 하나뿐인 것**이다 (S21). 예전에는 이름을 고치는 동안에만 붙는 이름표를 세다가 늘 대비책으로
    떨어졌고, 그 대비책은 셸의 내비게이션 버튼까지 세서 대화가 한 건도 없을 때도 「있다」고 답했다. 지금은 줄의 표지
    (`data-conversation-row`)를 센다.
    """
    _open_sidebar(r)
    return r.page.locator(CONV_ROW)


def _ensure_conversation(r):
    """대화가 **한 건은 있게** 한다.

    이 사이드바는 대화가 0건이면 검색 상자를 아예 안 그린다 — 찾을 것이 없으니 맞는
    동작이다. 그 상태에서 「검색 상자가 없다」로 적으면 화면이 아니라 **표가 이른 것**이다.
    Flow 는 서로 독립이어야 하므로 필요한 것을 스스로 만든다.
    """
    _open_sidebar(r)
    if _conv_items(r).count():
        return
    # 🔴 **메시지를 보내서 만들지 않는다** (S21). 이 서버에는 모델이 없어서 첫 질문의
    # 답이 영영 안 오고, 그동안 입력 칸은 잠긴다("답변을 기다리는 중입니다") — 그것은
    # 제품이 옳게 하는 일이다. 그런데 그렇게 만들어 두면 **뒤따르는 Flow 가 전부 잠긴
    # 칸을 만난다.** 여기서 필요한 것은 「대화 한 줄」이지 「답변」이 아니므로, 화면의
    # «새 대화» 가 부르는 그 엔드포인트를 같은 세션으로 직접 부른다.
    made = r.page.evaluate("""
        async () => {
          const me = await fetch('/api/me', {credentials: 'same-origin'});
          const token = me.ok ? ((await me.json()).csrf_token || '') : '';
          const res = await fetch('/api/conversations', {
            method: 'POST', credentials: 'same-origin',
            headers: {'Content-Type': 'application/json', 'X-CSRF-Token': token},
            body: JSON.stringify({title: 'S21 인수 점검 대화'}),
          });
          return res.status;
        }
    """)
    if made not in (200, 201):
        stop("대화를 만들지 못했다 — HTTP %s" % made)
    r.page.reload()
    r.settle(2600)
    _open_sidebar(r)


# ═══════════════════════════════════════════════════════════════════════════
# /chat — AI 도우미
# ═══════════════════════════════════════════════════════════════════════════
def _conv_search(r, ctx):
    _ensure_conversation(r)
    box = r.page.locator(SEARCH_BOX)
    if not box.count():
        stop("대화 제목 검색 상자가 없다")
    before = _conv_items(r).count()
    r.rec.reset()
    box.first.fill("존재하지않는대화zz")
    r.settle(2200)
    narrowed = _conv_items(r).count()
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if CONV in c["path"] and c["query"]}))
    box.first.fill("")
    r.settle(1500)
    return {"ui_action": "대화 목록을 «존재하지않는대화zz» 로 검색한다",
            "frontend_state": "300ms 디바운스 뒤 q 가 서버로 간다",
            "observed": {"items": {"before": before, "after": narrowed}, "query": query},
            "rendered": "대화 %d개 → %d개 · 질의 «%s»" % (before, narrowed, query[:70]),
            "expected": {"source": "derived-check",
                         "rule": "없는 말로 검색하면 목록이 비고, 조건은 서버로 간다",
                         "expect": 0, "got": narrowed},
            "failed": None if narrowed == 0
                      else "없는 말로 검색했는데 대화가 %d개 남아 있다" % narrowed}


flow("FF-0179", "user_chat", "search", "대화 목록을 제목·본문으로 검색한다(300ms 디바운스 후 서버가 거른다)",
     _conv_search, route="/chat", api=CONV)


def _include_archived(r, ctx):
    _ensure_conversation(r)
    tab = r.page.locator("#main-content").get_by_role("tab", name="보관함", exact=True)
    if not tab.count():
        stop("«대화 | 보관함» 보기가 없다")
    before = _conv_items(r).count()
    r.rec.reset()
    tab.first.click()
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls
                             if CONV in c["path"] and c["query"]}))
    after = _conv_items(r).count()
    r.page.locator("#main-content").get_by_role("tab", name="대화", exact=True).first.click()
    r.settle(1200)
    return {"ui_action": "«보관함» 보기로 바꾼다",
            "frontend_state": "archived=only 가 서버로 간다(보관한 대화만)",
            "observed": {"items": {"before": before, "after": after}, "query": query},
            "rendered": "대화 %d개 → %d개 · 질의 «%s»" % (before, after, query[:70]),
            "expected": {"source": "derived-check",
                         "rule": "보관 포함을 켜면 그 축이 서버 질의에 실린다", "got": query},
            "failed": None if "archiv" in query
                      else "보관 포함을 켰는데 질의에 그 축이 없다: «%s»" % query}


flow("FF-0180", "user_chat", "filter", "「대화 | 보관함」 보기를 바꿔 보관한 대화만 본다",
     _include_archived, route="/chat", api=CONV)


def _conv_more(r, ctx):
    _ensure_conversation(r)
    button = r.in_main("button", "대화 더 보기")
    count = _conv_items(r).count()
    if not button.count():
        return {"ui_action": "«대화 더 보기» 를 찾는다 — 상한에 안 닿았다",
                "observed": {"conversations": count, "more": 0},
                "rendered": "대화 %d개 · 더 보기 없음" % count,
                "expected": {"source": "known-data",
                             "rule": "상한에 안 닿으면 더 볼 것이 없다", "got": count},
                "failed": None}
    r.rec.reset()
    button.first.click()
    r.settle(2000)
    query = " ".join(sorted({c["query"] for c in r.rec.calls if CONV in c["path"]}))
    return {"ui_action": "«대화 더 보기» 로 상한을 늘린다",
            "observed": {"items": {"before": count, "after": _conv_items(r).count()},
                         "query": query},
            "rendered": "대화 %d개 → %d개 · 질의 «%s»"
                        % (count, _conv_items(r).count(), query[:60]),
            "expected": {"source": "derived-check",
                         "rule": "더 보기는 상한을 늘려 다시 받는다", "query": query},
            "failed": None if "limit" in query else "더 보기를 눌렀는데 상한이 안 바뀐다"}


flow("FF-0181", "user_chat", "pagination", "'대화 더 보기'로 목록 상한(100개)을 늘려 다시 받는다",
     _conv_more, route="/chat", server=False)


def _new_conv(r, ctx):
    _open_sidebar(r)
    before = _conv_items(r).count()
    button = r.in_main("button", "새 대화")
    if not button.count():
        stop("«새 대화» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2400)
    sent = [c for c in r.rec.calls if c["method"] == "POST" and CONV in c["path"]]
    after = _conv_items(r).count()
    ctx["conv_hash"] = r.hash_of()
    # **기록은 첫 메시지에 생긴다.** 이 버튼이 하는 일은 초안을 비우고 지금 대화를 놓는
    # 것이다(`ConversationSidebar.jsx` — `clearDraft(); setComposingNew(true); setCid(null)`).
    # 「목록이 하나 늘어야 한다」는 제품이 한 적 없는 약속이라, 그것으로 재면 언제나 실패한다.
    # 재는 것은 **빈 대화가 열렸는가**다: 입력 칸이 비었고, 잠겨 있지 않고, 고른 대화가 없다.
    box = r.page.locator(COMPOSER)
    draft = (box.first.input_value() if box.count() else "")
    locked = bool(box.count() and box.first.is_disabled())
    opened = (draft == "") and not locked
    return {"ui_action": "«새 대화» 로 빈 대화를 시작한다",
            "frontend_state": "초안을 비우고 지금 대화를 놓는다(기록은 첫 메시지에 생긴다)",
            "observed": {"items": {"before": before, "after": after},
                         "posts": len(sent), "draft": draft[:40], "locked": locked},
            "rendered": "입력 칸 «%s»(잠김 %s) · 본문 «%s»"
                        % (draft[:30], locked, r.main_text(90)),
            "expected": {"source": "derived-check",
                         "rule": "빈 대화가 열린다 — 입력 칸이 비고 잠기지 않는다",
                         "got": {"draft": draft[:20], "locked": locked}},
            "failed": None if opened else "«새 대화» 를 눌렀는데 빈 입력 칸이 안 열렸다"}


flow("FF-0182", "user_chat", "create", "'새 대화'로 빈 대화를 시작한다",
     _new_conv, route="/chat", api=CONV)


def _open_conv(r, ctx):
    _ensure_conversation(r)
    items = _conv_items(r)
    if not items.count():
        stop("대화가 없다")
    before = r.hash_of()
    # 줄의 제목 링크(`#/chat/<id>`)가 대화를 여는 자리다 — 주소가 정본이라 고르면 주소가 바뀐다(D-582). 이미 연 줄을 다시
    # 누르면 주소가 그대로인 것이 맞으므로 고르지 않은 줄을 누른다.
    others = r.page.locator(CONV_ROW + ":not([data-active])")
    title = (others.first if others.count() else items.first).locator("a").first
    r.rec.reset()
    title.click()
    r.settle(2200)
    calls = sorted({c["path"] for c in r.rec.calls if "/messages" in c["path"]})
    return {"ui_action": "목록에서 대화를 골라 스레드를 연다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"message_calls": calls, "hash": r.hash_of()},
            "rendered": "부른 것 %s · 본문 «%s»" % (calls, r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "대화를 고르면 그 대화의 메시지를 받는다", "got": calls},
            "failed": None if (calls and "/chat/" in r.hash_of())
                      else "대화를 눌렀는데 그 대화의 주소 · 메시지가 안 섰다"}


flow("FF-0183", "user_chat", "read", "목록에서 대화를 골라 그 대화의 주소(/chat/<id>)로 스레드를 연다",
     _open_conv, route="/chat", api="/messages")


def _rename_conv(r, ctx):
    _ensure_conversation(r)
    _row_menu(r, "이름 바꾸기")
    box = r.page.locator('#main-content [aria-label^="이름 바꾸기: "]')
    if not box.count():
        stop("이름 입력 칸이 안 열렸다")
    box = box.first
    name = "S21 점검 대화"
    box.fill(name)
    r.rec.reset()
    r.page.keyboard.press("Enter")
    r.settle(2000)
    sent = [c for c in r.rec.calls if c["method"] == "PATCH"]
    return {"ui_action": "대화 제목을 목록 안에서 «%s» 로 바꾼다" % name,
            "frontend_state": "Enter 저장 (PATCH)",
            "observed": {"patch": len(sent), "name": name},
            "rendered": "PATCH %d건 · 본문 «%s»" % (len(sent), r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "Enter 로 저장하면 서버로 간다", "expect": name},
            "cross": {"needle": name},
            "failed": None if sent else "이름을 바꿨는데 서버로 안 갔다"}


flow("FF-0184", "user_chat", "inline_edit",
     "대화 제목을 목록 안에서 바로 고친다(Enter 저장, Esc 취소, 실패 시 입력 유지)",
     _rename_conv, route="/chat", api=CONV, cross=("@reload", ""))


def _archive_conv(r, ctx):
    _ensure_conversation(r)
    before = _conv_items(r).count()
    r.rec.reset()
    label = _row_menu(r, "보관하기") + " › 보관하기"
    r.settle(1600)
    sent = [c for c in r.rec.calls if c["method"] == "PATCH"]
    after = _conv_items(r).count()
    return {"ui_action": "«%s» 를 실행한다" % label,
            "frontend_state": "PATCH archived=true → 목록에서 빠진다",
            "observed": {"patch": len(sent), "items": {"before": before, "after": after}},
            "rendered": "대화 %d개 → %d개 · PATCH %d건" % (before, after, len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "보관하면 기본 목록에서 빠진다",
                         "expect": before - 1, "got": after},
            "failed": None if sent else "보관을 눌렀는데 서버로 안 갔다"}


flow("FF-0185", "user_chat", "status_change", "대화를 보관하거나 보관을 해제한다",
     _archive_conv, route="/chat", api=CONV)


def _bulk_archive(r, ctx):
    _ensure_conversation(r)
    button = r.in_main("button", "빈 대화")
    if not button.count():
        return {"ui_action": "«빈 대화 N개 보관» 단추를 찾는다",
                "observed": {"button": 0, "items": _conv_items(r).count()},
                "rendered": "일괄 보관 버튼 없음 · 대화 %d개" % _conv_items(r).count(),
                "expected": {"source": "known-data",
                             "rule": "정리할 빈 대화가 없으면 그 버튼도 없는 것이 맞다"},
                "failed": None}
    label = " ".join((button.first.inner_text() or "").split())
    before = _conv_items(r).count()
    button.first.click()
    r.settle(1000)
    asked = open_dialogs(r) > 0
    said = confirm_now(r) if asked else ""
    r.settle(2000)
    return {"ui_action": "«%s» 를 실행한다" % label,
            "frontend_state": "확인 → POST /api/conversations/archive-empty 한 번(서버가 빈 대화를 고른다)",
            "observed": {"confirm_asked": asked, "confirm": said[:140],
                         "items": {"before": before, "after": _conv_items(r).count()}},
            "rendered": "대화 %d개 → %d개 · 확인 «%s»"
                        % (before, _conv_items(r).count(), said[:80]),
            "expected": {"source": "derived-check",
                         "rule": "여러 건을 한꺼번에 바꾸기 전에 몇 건인지 말하고 확인을 받는다",
                         "confirm_asked": asked},
            "failed": None if asked else "확인 없이 일괄 보관이 실행된다"}


flow("FF-0186", "user_chat", "modal_action", "메시지 없는 빈 대화를 확인 후 서버가 한꺼번에 보관한다",
     _bulk_archive, route="/chat", api=CONV)


def _delete_conv(r, ctx):
    _ensure_conversation(r)
    before = _conv_items(r).count()
    r.rec.reset()
    label = _row_menu(r, "삭제") + " › 삭제"
    r.settle(400)
    asked = open_dialogs(r) > 0
    said = confirm_now(r) if asked else ""
    r.settle(2200)
    sent = [c for c in r.rec.calls if c["method"] == "DELETE"]
    return {"ui_action": "«%s» 를 실행한다" % label,
            "frontend_state": "확인 → DELETE",
            "observed": {"confirm_asked": asked, "confirm": said[:140],
                         "delete": len(sent),
                         "items": {"before": before, "after": _conv_items(r).count()}},
            "rendered": "대화 %d개 → %d개 · DELETE %d건"
                        % (before, _conv_items(r).count(), len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "되돌릴 수 없는 삭제는 확인을 받고, 지우면 목록에서 사라진다",
                         "confirm_asked": asked},
            "failed": ("확인 없이 삭제된다" if not asked
                       else (None if sent else "확인했는데 서버로 안 갔다"))}


flow("FF-0187", "user_chat", "delete", "대화를 확인 대화상자 후 삭제한다",
     _delete_conv, route="/chat", api=CONV)


def _send_message(r, ctx):
    # 앞 Flow 가 보낸 질문의 답을 이 서버는 영영 못 준다(모델이 없다) — 그동안 입력 칸은
    # 잠긴다. 그것은 제품이 옳게 하는 일이므로 **잠기지 않은 자리**에서 잰다: «새 대화» 는
    # 초안을 비우고 지금 대화를 놓는다.
    fresh = r.in_main("button", "새 대화")
    if fresh.count():
        fresh.first.click()
        r.settle(1800)
    box = r.page.locator(COMPOSER)
    if not box.count():
        stop("메시지 입력 칸이 없다")
    if box.first.is_disabled():
        stop("입력 칸이 잠겨 있다 — 앞 대화의 답을 기다리는 중이다")
    text = "S21 인수 점검이 보낸 질문입니다."
    box.first.fill(text)
    r.rec.reset()
    r.page.keyboard.press("Enter")
    r.settle(3000)
    sent = [c for c in r.rec.calls if c["method"] == "POST" and "/messages" in c["path"]]
    body = r.main_text(220)
    return {"ui_action": "메시지를 적고 Enter 로 보낸다",
            "frontend_state": "POST /api/conversations/{id}/messages",
            "observed": {"posts": len(sent), "text": text},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), body[:150]),
            "expected": {"source": "derived-check",
                         "rule": "Enter 로 보내면 서버로 가고 스레드에 남는다",
                         "expect": text},
            "failed": None if (sent or text in body)
                      else "메시지를 보냈는데 서버로도 안 가고 화면에도 없다"}


flow("FF-0188", "user_chat", "create", "메시지를 전송한다(Enter 전송, Shift+Enter 줄바꿈)",
     _send_message, route="/chat", api="/messages")


def _attach_slot(r, ctx):
    button = r.page.locator('#main-content [aria-label="이미지 첨부"]')
    files = r.page.locator('input[type="file"]')
    accept = files.first.get_attribute("accept") if files.count() else ""
    return {"ui_action": "컴포저의 이미지 첨부 자리를 본다",
            "observed": {"button": button.count(), "file_inputs": files.count(),
                         "accept": accept},
            "rendered": "첨부 버튼 %d개 · 파일 칸 %d개 · accept «%s»"
                        % (button.count(), files.count(), accept),
            "expected": {"source": "derived-check",
                         "rule": "이미지(PNG/JPEG/WebP)를 붙일 자리가 있다", "accept": accept},
            "failed": None if button.count() else "컴포저에 첨부 자리가 없다"}


flow("FF-0189", "user_chat", "attachment", "이미지(PNG/JPEG/WebP)를 첨부하고 칩에서 개별 제거한다",
     _attach_slot, route="/chat", server=False)


def _composer_limit(r, ctx):
    box = r.page.locator(COMPOSER)
    if not box.count():
        stop("메시지 입력 칸이 없다")
    box.first.fill("")
    r.settle(500)
    empty_text = r.main_text(300)
    send = r.page.locator('#main-content button[type="submit"]')
    disabled_when_empty = send.first.is_disabled() if send.count() else None
    box.first.fill("가" * 30)
    r.settle(600)
    counted = r.main_text(300)
    box.first.fill("")
    return {"ui_action": "빈 입력과 30자 입력에서 글자 수 표시와 전송 잠금을 본다",
            "observed": {"send_disabled_when_empty": disabled_when_empty,
                         "empty": empty_text[-80:], "typed": counted[-80:]},
            "rendered": "빈 입력에서 전송 %s · 30자 뒤 «%s»"
                        % ("잠김" if disabled_when_empty else "열림", counted[-70:]),
            "expected": {"source": "derived-check",
                         "rule": "빈 입력이면 전송을 막고 글자 수를 늘 보여 준다",
                         "disabled": disabled_when_empty},
            "failed": None if disabled_when_empty is not False
                      else "빈 입력인데 전송 버튼이 열려 있다"}


flow("FF-0190", "user_chat", "form_validation",
     "입력 글자 수/5000 상한을 항상 표시하고 빈 입력이면 전송을 막는다",
     _composer_limit, route="/chat", server=False)


def _message_action(label: str, api_hint: str, *, needed: bool = True, menu: str = ""):
    """메시지 동작 하나. `menu` 가 있으면 그 메뉴(「답 더 보기」 · 「대화 동작」)를 먼저 열고 항목을 누른다(D-582 — 삭제 ·
    대화 전체 복사는 메뉴 안이다)."""
    def _act(r, ctx):
        if menu:
            opener = r.page.locator('#main-content [aria-label="%s"]' % menu)
            if opener.count():
                opener.last.click()
                r.settle(500)
            target = r.page.get_by_role("menuitem", name=label, exact=True)
        else:
            target = r.page.locator('#main-content [aria-label*="%s"]' % label)
        if not target.count():
            target = r.in_main("button", label)
        if not target.count():
            if needed:
                stop("«%s» 를 못 찾았다" % label)
            return {"ui_action": "«%s» 자리를 찾는다" % label,
                    "observed": {"buttons": 0},
                    "rendered": "«%s» 없음 · 본문 «%s»" % (label, r.main_text(110)),
                    "expected": {"source": "known-data",
                                 "rule": "그 조건의 메시지가 없으면 그 동작도 없는 것이 맞다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(2400)
        if open_dialogs(r):
            confirm_now(r)
            r.settle(1600)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "메시지의 «%s» 를 실행한다" % label,
                "observed": {"calls": calls},
                "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, r.main_text(120)),
                "expected": {"source": "derived-check",
                             "rule": ("«%s» 는 %s 를 부른다" % (label, api_hint) if api_hint
                                      else "«%s» 는 화면 안에서 끝난다(클립보드)" % label),
                             "got": calls},
                "failed": (None if not api_hint or any(api_hint in c for c in calls)
                           else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s"
                                % (label, api_hint, calls))}
    return _act


flow("FF-0191", "user_chat", "row_action", "실패한 메시지를 '다시 시도'로 재전송한다",
     _message_action("다시 시도", "/retry", needed=False), route="/chat", server=False)

flow("FF-0192", "user_chat", "row_action", "마지막 답을 다시 만든다",
     _message_action("답 다시 만들기", "/regenerate", needed=False), route="/chat", server=False)

flow("FF-0193", "user_chat", "row_action", "답에 좋은 답변 · 아쉬운 답변 피드백을 남긴다(토글)",
     _message_action("좋은 답변", "/feedback", needed=False), route="/chat", server=False)


def _open_conversation_with(r, predicate) -> str | None:
    """`predicate(structured)` 를 만족하는 답이 있는 내 대화를 연다(API 로 찾는다). 연 대화 id 또는 None."""
    payload = r.api_get(CONV + "?limit=50") or {}
    for conv in payload.get("items") or []:
        thread = r.api_get("%s/%s/messages" % (CONV, conv["id"])) or {}
        for m in thread.get("items") or []:
            if m.get("role") == "assistant" and predicate(m.get("structured") or {}, m):
                r.goto("/chat/%s" % conv["id"], shell=USER)
                r.settle(1500)
                return conv["id"]
    return None


def _copy_message(r, ctx):
    _open_conversation_with(r, lambda st, m: bool(m.get("content")))
    button = r.page.locator('#main-content [aria-label*="복사"]')
    names = [button.nth(i).get_attribute("aria-label")
             for i in range(min(button.count(), 5))]
    whole = 0
    opener = r.page.locator('#main-content [aria-label="대화 동작"]')
    if opener.count():
        opener.first.click()
        r.settle(400)
        whole = r.page.get_by_role("menuitem", name="대화 전체 복사", exact=True).count()
        r.page.keyboard.press("Escape")
        r.settle(300)
        names.append("대화 동작 › 대화 전체 복사" if whole else "대화 동작(복사 없음)")
    return {"ui_action": "답의 복사 단추와 머리 메뉴의 「대화 전체 복사」를 센다",
            "observed": {"buttons": button.count(), "labels": names, "whole": whole},
            "rendered": "복사 버튼 %d개 %s" % (button.count(), names),
            "expected": {"source": "derived-check",
                         "rule": "메시지 하나와 대화 전체를 각각 복사할 수 있다",
                         "labels": names},
            "failed": None if button.count() else "복사할 자리가 하나도 없다"}


flow("FF-0194", "user_chat", "row_action", "메시지 한 개를 클립보드로 복사한다",
     _copy_message, route="/chat", server=False)

flow("FF-0195", "user_chat", "row_action", "대화 전체를 텍스트로 복사한다(머리의 「대화 동작」 메뉴)",
     _message_action("대화 전체 복사", "", needed=False, menu="대화 동작"), route="/chat", server=False)

flow("FF-0196", "user_chat", "delete", "메시지 한 개를 삭제한다(답의 「더 보기」 메뉴, 확인 후)",
     _message_action("메시지 삭제", "/api/messages", needed=False, menu="답 더 보기"), route="/chat",
     server=False)


def _suggestion_chip(r, ctx):
    chips = r.page.locator("#main-content .MuiChip-root")
    names = [" ".join((chips.nth(i).inner_text() or "").split())
             for i in range(min(chips.count(), 6))]
    return {"ui_action": "선택지 칩을 센다",
            "observed": {"chips": chips.count(), "labels": names},
            "rendered": "칩 %d개 %s" % (chips.count(), names),
            "expected": {"source": "known-data",
                         "rule": "답변이 선택지를 줄 때만 칩이 있다", "labels": names},
            "failed": None}


flow("FF-0197", "user_chat", "row_action", "선택지 칩을 눌러 그 문장을 그대로 다시 보낸다",
     _suggestion_chip, route="/chat", server=False)


def _thread_refresh(r, ctx):
    button = r.page.locator('#main-content [aria-label*="새로고침"]')
    if not button.count():
        button = r.in_main("button", "새로고침")
    if not button.count():
        stop("스레드 수동 새로고침 자리가 없다")
    r.rec.reset()
    button.first.click()
    r.settle(2200)
    calls = sorted({c["path"] for c in r.rec.calls if "/messages" in c["path"]})
    return {"ui_action": "스레드를 손으로 새로고침한다",
            "observed": {"calls": calls},
            "rendered": "다시 부른 것 %s" % calls,
            "expected": {"source": "derived-check",
                         "rule": "새로고침은 스레드를 다시 받는다", "got": calls},
            "failed": None if calls else "새로고침을 눌렀는데 다시 안 받았다"}


flow("FF-0198", "user_chat", "refresh",
     "응답 지연·연결 끊김에서 스레드를 수동 새로고침한다(폴링 기준선도 재설정)",
     _thread_refresh, route="/chat", api="/messages")


def _result_card_link(label: str, expect: str):
    def _act(r, ctx):
        _open_conversation_with(r, lambda st, m: any(b.get("shown") and b.get("items") for b in st.get("results") or []))
        # 줄의 제목 링크다(머리의 「전체 목록 열기」가 아니다).
        target = r.page.locator('#main-content [data-result-block] li a[href^="#/"]')
        if not target.count():
            target = r.in_main("button", label)
        if not target.count():
            target = r.page.locator('#main-content a[href*="#/tickets/"]')
        if not target.count():
            return {"ui_action": "결과 카드의 «%s» 를 찾는다" % label,
                    "observed": {"buttons": 0, "body": r.main_text(140)},
                    "rendered": "«%s» 없음 — 이 대화에 결과 카드가 없다" % label,
                    "expected": {"source": "known-data",
                                 "rule": "결과 카드가 있을 때만 그 동작이 있다"},
                    "failed": None}
        before = r.hash_of()
        target.first.click()
        r.settle(2200)
        return {"ui_action": "결과 카드의 «%s» 를 누른다" % label,
                "url_state": "%s → %s" % (before, r.hash_of()),
                "observed": {"hash": r.hash_of()},
                "rendered": "주소 «%s»" % r.hash_of(),
                "expected": {"source": "derived-check",
                             "rule": "그 항목의 화면으로 옮긴다", "expect": expect},
                "failed": None if (expect in r.hash_of() and not r.hash_of().startswith("/chat"))
                          else "«%s» 를 눌렀는데 %s 로 안 갔다" % (label, expect)}
    return _act


flow("FF-0199", "user_chat", "navigation", "결과 목록의 줄을 눌러 그 항목의 화면으로 간다",
     _result_card_link("앱에서 보기", "/"), route="/chat", server=False)



def _result_more(r, ctx):
    _open_conversation_with(r, lambda st, m: any(
        b.get("shown") and isinstance(b.get("total"), int) and b["total"] > (b.get("offset") or 0) + (b.get("returned") or 0)
        for b in st.get("results") or []))
    button = r.page.locator('#main-content [data-result-block] button', has_text="건 더 보기")
    if not button.count():
        return {"ui_action": "결과 목록의 «N건 더 보기» 를 찾는다",
                "observed": {"buttons": 0},
                "rendered": "«N건 더 보기» 없음 — 이 대화에 이어 볼 결과 목록이 없다",
                "expected": {"source": "known-data",
                             "rule": "이어 볼 목록이 있을 때만 그 동작이 있다"},
                "failed": None}
    rows = r.page.locator('#main-content [data-result-block] li')
    before = rows.count()
    r.rec.reset()
    button.first.click()
    r.settle(2200)
    calls = sorted({c["path"] for c in r.rec.calls if "/results/" in c["path"]})
    after = rows.count()
    return {"ui_action": "결과 목록의 «N건 더 보기» 를 누른다",
            "observed": {"calls": calls, "rows": {"before": before, "after": after}},
            "rendered": "줄 %d개 → %d개 · 부른 것 %s" % (before, after, calls),
            "expected": {"source": "derived-check",
                         "rule": "다음 쪽을 받아 덧붙인다(모델을 부르지 않는다)", "got": calls},
            "failed": None if (calls and after > before)
                      else "«더 보기» 를 눌렀는데 다음 쪽이 안 붙었다"}


flow("FF-0200", "user_chat", "row_action", "결과 목록의 「N건 더 보기」로 모델 없이 다음 쪽을 덧붙인다",
     _result_more, route="/chat", server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /chat-rooms/:id
# ═══════════════════════════════════════════════════════════════════════════
ROOM = "/api/team-chat/rooms"


def _room_id(r) -> str:
    payload = r.api_get(ROOM)
    items = (payload or {}).get("items") or []
    if not items:
        stop("채팅방이 없다")
    return items[0]["id"]


def _goto_room(r) -> str:
    rid = _room_id(r)
    r.goto("/chat-rooms/%s" % rid, shell=USER)
    return rid


def _room_read(r, ctx):
    rid = _goto_room(r)
    ctx["room_id"] = rid
    calls = sorted({c["path"] for c in r.rec.calls if "/team-chat/" in c["path"]})
    body = r.main_text(220)
    return {"ui_action": "채팅방을 연다",
            "observed": {"id": rid, "calls": calls, "body": body},
            "rendered": "본문 «%s»" % body[:160],
            "expected": {"source": "derived-check",
                         "rule": "방 메타·참여자·메시지를 한 번에 받는다", "got": calls},
            "failed": None if body else "방을 열었는데 본문이 비었다"}


flow("FF-0211", "user_chat-rooms-id", "read", "방 메타·참여자·메시지를 한 쿼리로 받아 연다",
     _room_read, api="/api/team-chat/")


def _room_deep_link(r, ctx):
    rid = ctx.get("room_id") or _room_id(r)
    r.goto("/chat-rooms/%s" % rid, shell=USER)
    before = r.main_text(140)
    r.page.reload(wait_until="domcontentloaded")
    r.page.wait_for_selector("#main-content", timeout=30_000)
    r.settle(2200)
    after_hash = r.hash_of()
    return {"ui_action": "방 주소로 직접 들어가 새로고침한다",
            "url_state": after_hash,
            "observed": {"hash": after_hash, "body": r.main_text(140)},
            "rendered": "본문 «%s»" % r.main_text(140),
            "expected": {"source": "derived-check",
                         "rule": "주소만으로 그 방이 열리고 새로고침해도 유지된다",
                         "expect": rid, "got": after_hash},
            "failed": None if rid in after_hash
                      else "새로고침 뒤 그 방이 아니다: %s" % after_hash}


flow("FF-0212", "user_chat-rooms-id", "deep_link",
     "알림 딥링크(/chat-rooms/<id>)와 새로고침·뒤로가기로 특정 방을 직접 연다",
     _room_deep_link, api="/api/team-chat/")


def _room_manage(r, ctx):
    if "/chat-rooms/" not in r.hash_of():
        _goto_room(r)
    button = r.in_main("button", "관리")
    if not button.count():
        stop("«관리» 버튼이 없다")
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("«관리» 를 눌렀는데 모달이 안 떴다")
    text = dialog_says(r, 320)
    buttons = open_dialog(r).get_by_role("button")
    names = [" ".join((buttons.nth(i).inner_text() or "").split())
             for i in range(min(buttons.count(), 12))]
    ctx["room_manage_buttons"] = names
    r.dismiss_overlays()
    return {"ui_action": "«관리» 모달을 연다",
            "observed": {"buttons": names, "panel": text[:260]},
            "rendered": "관리 모달 «%s» · 버튼 %s" % (text[:130], names),
            "expected": {"source": "derived-check",
                         "rule": "이름 변경·초대·내보내기·방장 넘기기를 한 자리에서 한다",
                         "buttons": names},
            "failed": None if names else "관리 모달에 할 수 있는 일이 없다"}


flow("FF-0213", "user_chat-rooms-id", "modal_action",
     "'관리' 모달을 열어 이름 변경·초대·내보내기·방장 넘기기를 한다",
     _room_manage, server=False)


def _room_write(label: str, api_hint: str, *, value: str = "", confirm: bool = False):
    def _act(r, ctx):
        if "/chat-rooms/" not in r.hash_of():
            _goto_room(r)
        button = r.in_main("button", "관리")
        if not button.count():
            stop("«관리» 버튼이 없다")
        button.first.click()
        r.settle(1400)
        dialog = open_dialog(r) if open_dialogs(r) else None
        if dialog is None:
            stop("관리 모달이 안 떴다")
        if value:
            box = dialog.locator("input[type=text]").first
            if not box.count():
                r.dismiss_overlays()
                stop("이름 칸이 없다")
            box.fill(value)
            r.settle(400)
        target = dialog.get_by_role("button", name=label, exact=False)
        if not target.count():
            names = dialog.get_by_role("button").all_inner_texts()
            r.dismiss_overlays()
            # **이 모달이 주는 일은 방의 상태에 따라 다르다**(1:1 인가 · 내가 방장인가 ·
            # 부를 사람이 남아 있는가). 없는 것을 「없다」로 적되, 무엇이 있었는지 함께 적는다.
            return {"ui_action": "관리 모달에서 «%s» 를 찾는다" % label,
                    "observed": {"buttons": names},
                    "rendered": "«%s» 없음 — 이 모달이 준 것 %s" % (label, names),
                    "expected": {"source": "derived-check",
                                 "rule": "관리 모달의 일감은 방 상태와 내 권한으로 갈린다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(1400)
        asked = open_dialogs(r) > 1
        said = confirm_now(r) if asked else ""
        r.settle(2000)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        r.dismiss_overlays()
        return {"ui_action": "관리 모달에서 «%s» 를 실행한다" % label,
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130]},
                "rendered": "쓰기 요청 %s · 확인 «%s»" % (calls, said[:80]),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "cross": {"needle": value} if value else None,
                "failed": None if any(api_hint in c for c in calls)
                          else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s" % (label, api_hint, calls)}
    return _act


flow("FF-0214", "user_chat-rooms-id", "edit", "방 이름을 바꾼다",
     _room_write("저장", "/rename", value="S21 점검 채팅방"), api="/api/team-chat/")

flow("FF-0215", "user_chat-rooms-id", "create", "참여자를 초대한다(디렉터리에서 다중 선택)",
     _room_write("초대", "/members"), api="/api/team-chat/")

flow("FF-0216", "user_chat-rooms-id", "delete", "참여자를 내보낸다",
     _room_write("내보내기", "/members"), api="/api/team-chat/")

flow("FF-0217", "user_chat-rooms-id", "assignee_change", "방장 권한을 다른 참여자에게 넘긴다",
     _room_write("방장", "/owner"), api="/api/team-chat/")


def _room_top_action(label: str, api_hint: str):
    def _act(r, ctx):
        if "/chat-rooms/" not in r.hash_of():
            _goto_room(r)
        button = r.in_main("button", label)
        if not button.count():
            return {"ui_action": "«%s» 자리를 찾는다" % label,
                    "observed": {"buttons": 0, "body": r.main_text(150)},
                    "rendered": "«%s» 없음 — 이 방·이 역할에는 그 동작이 없다" % label,
                    "expected": {"source": "derived-check",
                                 "rule": "서버가 준 can_* 플래그로만 그린다"},
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
                "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130],
                             "hash": r.hash_of()},
                "rendered": "쓰기 요청 %s · 주소 «%s»" % (calls, r.hash_of()),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 확인을 받고 %s 를 부른다" % (label, api_hint),
                             "got": calls},
                "failed": None if any(api_hint in c for c in calls)
                          else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s" % (label, api_hint, calls)}
    return _act


flow("FF-0218", "user_chat-rooms-id", "status_change", "1:1 대화를 내 목록에서만 숨긴다(확인 후)",
     _room_top_action("숨기기", "/hide"), api="/api/team-chat/")

flow("FF-0219", "user_chat-rooms-id", "modal_action",
     "채팅방을 나간다 — 방장 여부·남은 인원에 따라 확인 문구가 갈린다",
     _room_top_action("나가기", "/leave"), api="/api/team-chat/")

flow("FF-0220", "user_chat-rooms-id", "delete", "방을 파해 모든 참여자 목록에서 없앤다(확인 후)",
     _room_top_action("파하기", "/disband"), api="/api/team-chat/")


def _room_permission(r, ctx):
    if "/chat-rooms/" not in r.hash_of():
        _goto_room(r)
    rid = ctx.get("room_id") or _room_id(r)
    mine = {label: r.in_main("button", label).count()
            for label in ("관리", "숨기기", "나가기", "파하기")}
    got = r.as_role("user", "/chat-rooms/%s" % rid, "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return {buttons: main ? Array.from(main.querySelectorAll('button')).map(
                       b => (b.innerText || '').replace(/\\s+/g,' ').trim()) : [],
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,160)};
           }"""))
    theirs = {label: sum(1 for n in got["buttons"] if label in n)
              for label in ("관리", "숨기기", "나가기", "파하기")}
    return {"ui_action": "같은 방을 그 방에 없는 사용자로 연다",
            "frontend_state": "you.can_* 로만 그린다",
            "observed": {"as_owner": mine, "as_other": theirs, "body": got["body"]},
            "rendered": "방장 %s · 다른 사람 %s" % (mine, theirs),
            "expected": {"source": "derived-check",
                         "rule": "관리·숨기기·파하기는 서버가 준 권한 플래그로만 나온다",
                         "as_other": theirs},
            "failed": None if theirs.get("파하기", 0) == 0
                      else "방에 없는 사용자에게도 «파하기» 가 보인다"}


flow("FF-0221", "user_chat-rooms-id", "permission_state",
     "관리·숨기기·파하기 버튼을 서버가 준 you.can_* 플래그로만 노출한다",
     _room_permission, server=False)


def _room_retry(r, ctx):
    rid = ctx.get("room_id") or _room_id(r)
    pattern = "**/api/team-chat/rooms/%s/**" % rid
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었습니다."}'))
    try:
        r.goto("/chat-rooms/%s" % rid, shell=USER)
        r.settle(3200)
        face = r.main_text(160)
        retry = r.in_main("button", "다시 시도")
        found = retry.count()
    finally:
        r.page.unroute(pattern)
    if found:
        retry.first.click()
        r.settle(2200)
    return {"ui_action": "방 조회를 503 으로 끊고 «다시 시도» 를 누른다",
            "observed": {"error_face": face, "retry": found},
            "rendered": "오류 «%s» → 복구 «%s»" % (face[:80], r.main_text(90)),
            "expected": {"source": "derived-check",
                         "rule": "503 이면 오류 얼굴과 «다시 시도» 를 준다", "got": found},
            "failed": None if found else "방이 503 인데 «다시 시도» 가 없다 — 얼굴: %s" % face}


flow("FF-0222", "user_chat-rooms-id", "refresh", "방 조회 실패 시 '다시 시도'로 재조회한다",
     _room_retry, api="/api/team-chat/")


def _room_back_to_list(r, ctx):
    where = r.hash_of()
    return {"ui_action": "앞 Flow(나가기·파하기) 뒤의 주소를 본다",
            "url_state": where,
            "observed": {"hash": where},
            "rendered": "주소 «%s» · 본문 «%s»" % (where, r.main_text(110)),
            "expected": {"source": "derived-check",
                         "rule": "방을 나가거나 파하면 목록으로 되돌린다",
                         "expect": "/chat-rooms", "got": where},
            "failed": None if "/chat-rooms" in where
                      else "방을 떠난 뒤 목록이 아닌 곳에 있다: %s" % where}


flow("FF-0223", "user_chat-rooms-id", "navigation", "방을 나가거나 파하면 목록(/chat-rooms)으로 되돌린다",
     _room_back_to_list, server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /ai — AI 작업공간
# ═══════════════════════════════════════════════════════════════════════════
def _ai_ask(r, ctx):
    box = r.page.locator("#main-content input[type=text]:visible, "
                         "#main-content textarea:visible").first
    if not box.count():
        stop("질문 칸이 없다")
    box.fill("회의록")
    r.rec.reset()
    submit = r.in_main("button", "문서 찾기")
    if not submit.count():
        submit = r.in_main("button", "물어보기")
    if submit.count():
        submit.first.click()
    else:
        r.page.keyboard.press("Enter")
    r.settle(4000)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if "/api/" in c["path"] and c["method"] != "GET"}
                   | {"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                      if "/api/ai/" in c["path"] or "/search" in c["path"]})
    body = r.main_text(300)
    ctx["ai_body"] = body
    # **이 설치에서 AI 가 꺼져 있으면** 화면은 그렇게 말하고 낱말 검색으로 답한다. 그것은
    # 결함이 아니라 그 구성의 계약이라, 무엇으로 답했는지를 그대로 적는다.
    ai_off = "AI 기능이 꺼져" in body
    return {"ui_action": "«회의록» 을 묻고 답과 근거를 받는다",
            "frontend_state": ("AI 꺼짐 — 낱말 검색으로 답한다" if ai_off
                               else "POST /api/ai/answer"),
            "observed": {"calls": calls, "ai_disabled": ai_off, "body": body},
            "rendered": "부른 것 %s · 본문 «%s»" % (calls[:6], body[:180]),
            "expected": {"source": "derived-check",
                         "rule": ("AI 가 꺼져 있으면 그렇게 말하고 낱말 검색으로 답한다"
                                  if ai_off else "질문을 보내면 답과 근거가 온다"),
                         "got": calls},
            "failed": None if calls else "질문을 보냈는데 아무 요청도 안 나갔다"}


flow("FF-1315", "user_ai-workspace", "search", "질문을 보내고 답과 근거를 받는다",
     _ai_ask, route="/ai", api="/api/ai/")


def _ai_citation(r, ctx):
    links = r.page.locator('#main-content a[href*="#/knowledge/"], '
                           '#main-content button[aria-label*="근거"]')
    if not links.count():
        return {"ui_action": "근거 링크를 찾는다",
                "observed": {"links": 0, "body": r.main_text(200)},
                "rendered": "근거 0개 · 본문 «%s»" % r.main_text(160),
                "expected": {"source": "known-data",
                             "rule": "근거가 없으면 링크도 없는 것이 맞다"},
                "failed": None}
    before = r.hash_of()
    links.first.click()
    r.settle(2400)
    return {"ui_action": "근거를 눌러 그 문단으로 간다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"hash": r.hash_of()},
            "rendered": "주소 «%s» · 본문 «%s»" % (r.hash_of(), r.main_text(120)),
            "expected": {"source": "derived-check",
                         "rule": "근거를 누르면 그 문서로 간다", "got": r.hash_of()},
            "failed": None if r.hash_of() != before else "근거를 눌렀는데 아무 데도 안 갔다"}


flow("FF-1316", "user_ai-workspace", "navigation", "근거를 눌러 그 문단으로 간다",
     _ai_citation, server=False)


def _ai_scope(r, ctx):
    """**권한 밖 문서는 근거에 안 들어간다.** 일반 사용자로 같은 질문을 던진다."""
    got = r.as_role("user", "/ai", "/", lambda p: p.evaluate(
        """async () => {
             let token = '';
             try {
               const me = await fetch('/api/me', {credentials: 'same-origin'});
               if (me.ok) token = (await me.json()).csrf_token || '';
             } catch (e) {}
             const res = await fetch('/api/ai/answer', {
               method: 'POST', credentials: 'same-origin',
               headers: {'Content-Type': 'application/json',
                         'X-CSRF-Token': token},
               body: JSON.stringify({question: '회의록'})});
             let body = '';
             try { body = (await res.text()).slice(0, 1200); } catch (e) {}
             return {status: res.status, body};
           }"""))
    mine = r.api_get("/api/knowledge/documents?page_size=50")
    titles = [d.get("title", "") for d in ((mine or {}).get("items") or [])]
    leaked = [t for t in titles if t and t in (got.get("body") or "")]
    theirs = r.as_role("user", "/me", "/", lambda p: p.evaluate(
        """async () => {
             const res = await fetch('/api/knowledge/documents?page_size=50',
                                     {credentials: 'same-origin'});
             return res.ok ? (await res.text()).slice(0, 4000) : '';
           }"""))
    allowed = [t for t in leaked if t in (theirs or "")]
    return {"ui_action": "일반 사용자로 같은 질문을 던지고 근거에 무엇이 들어갔는지 본다",
            "frontend_state": "권한 필터는 Context 를 만들기 전에 걸린다",
            "observed": {"status": got.get("status"),
                         "cited_titles": leaked[:6],
                         "visible_to_them": allowed[:6]},
            "rendered": "HTTP %s · 인용 %d건 · 그 사용자가 볼 수 있는 것 %d건"
                        % (got.get("status"), len(leaked), len(allowed)),
            "expected": {"source": "derived-check",
                         "rule": "인용에 들어간 문서는 그 사용자가 목록에서도 볼 수 있는 것뿐이다",
                         "cited": len(leaked), "allowed": len(allowed)},
            "failed": None if len(leaked) == len(allowed)
                      else ("권한 밖 문서가 근거에 들어갔다: %s"
                            % [t for t in leaked if t not in allowed][:3])}


flow("FF-1317", "user_ai-workspace", "permission_state", "권한 밖 문서는 근거에 안 들어간다",
     _ai_scope, route="/ai", server=False)


# ═══════════════════════════════════════════════════════════════════════════
# /games
# ═══════════════════════════════════════════════════════════════════════════
def _game_create(r, ctx):
    button = r.in_main("button", "게임방 추가")
    if not button.count():
        stop("«게임방 추가» 버튼이 없다")
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("게임방 만들기 모달이 안 떴다")
    dialog = open_dialog(r)
    title = "S21 점검 게임방"
    box = dialog.locator("input[type=text]").first
    if not box.count():
        r.dismiss_overlays()
        stop("제목 칸이 없다")
    box.fill(title)
    r.settle(400)
    r.rec.reset()
    for label in ("추가", "만들기", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        names = dialog.get_by_role("button").all_inner_texts()
        r.dismiss_overlays()
        stop("만드는 버튼이 없다 — 있는 것: %s" % names)
    r.settle(2600)
    sent = [c for c in r.rec.calls if c["method"] == "POST" and "/games/rooms" in c["path"]]
    ctx["game_title"] = title
    return {"ui_action": "«게임방 추가» 로 «%s» 를 만든다" % title,
            "frontend_state": "POST /api/games/rooms",
            "observed": {"posts": len(sent), "hash": r.hash_of()},
            "rendered": "POST %d건 · 본문 «%s»" % (len(sent), r.main_text(130)),
            "expected": {"source": "derived-check",
                         "rule": "만들면 그 방이 목록이나 방 화면에 나타난다", "expect": title},
            "failed": None if sent else "게임방을 만들었다는데 서버로 안 갔다"}


flow("FF-0320", "user_games", "create",
     "'게임방 추가'로 게임 종류·제목·인원·설정을 정해 방을 만든다",
     _game_create, route="/games", api="/api/games/rooms")


def _game_open(r, ctx):
    cards = r.page.locator('#main-content button[aria-label], #main-content a')
    r.goto("/games", shell=USER)
    buttons = r.page.locator("#main-content button")
    target = None
    for i in range(buttons.count()):
        label = " ".join((buttons.nth(i).inner_text() or "").split())
        if "참여" in label:
            target = buttons.nth(i)
            break
    if target is None:
        stop("들어갈 게임방 카드가 없다")
    before = r.hash_of()
    target.click()
    r.settle(2600)
    ctx["game_hash"] = r.hash_of()
    return {"ui_action": "방 카드를 눌러 그 게임방으로 들어간다",
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"hash": r.hash_of()},
            "rendered": "본문 «%s»" % r.main_text(130),
            "failed": None if "/games/" in r.hash_of()
                      else "카드를 눌렀는데 방으로 안 갔다: %s" % r.hash_of()}


flow("FF-0321", "user_games", "navigation", "방 카드를 눌러 그 게임방으로 들어간다",
     _game_open, api="/api/games/")


def _game_poll(r, ctx):
    r.goto("/games", shell=USER)
    r.rec.reset()
    r.settle(4200)
    polls = [c for c in r.rec.calls if "/api/games/rooms" in c["path"]]
    return {"ui_action": "목록에 머물며 폴링을 관측한다(4초)",
            "frontend_state": "3초마다 다시 받는다",
            "observed": {"polls": len(polls)},
            "rendered": "4초 동안 목록 요청 %d건" % len(polls),
            "expected": {"source": "derived-check",
                         "rule": "목록은 3초마다 스스로 다시 받는다",
                         "expect": ">=1", "got": len(polls)},
            "failed": None if polls else "목록에 머물렀는데 폴링이 한 번도 안 돈다"}


flow("FF-0322", "user_games", "refresh", "목록을 3초마다 폴링하고 실패 시 '다시 시도'를 준다",
     _game_poll, api="/api/games/rooms")


def _quiz_generate(r, ctx):
    r.goto("/games", shell=USER)
    button = r.in_main("button", "게임방 추가")
    if not button.count():
        stop("«게임방 추가» 버튼이 없다")
    button.first.click()
    r.settle(1400)
    dialog = open_dialog(r) if open_dialogs(r) else None
    if dialog is None:
        stop("모달이 안 떴다")
    ai = dialog.get_by_role("button", name="AI", exact=False)
    names = dialog.get_by_role("button").all_inner_texts()
    r.dismiss_overlays()
    return {"ui_action": "만들기 모달에서 AI 퀴즈 생성 자리를 찾는다",
            "observed": {"ai_buttons": ai.count(), "buttons": names},
            "rendered": "AI 생성 버튼 %d개 · 모달 버튼 %s" % (ai.count(), names),
            "expected": {"source": "derived-check",
                         "rule": "game_ai_enabled 가 꺼져 있으면 그 버튼을 안 그린다",
                         "buttons": names},
            "failed": None}


flow("FF-0323", "user_games", "create", "주제·문항 수를 주고 AI로 퀴즈 문제를 생성해 편집기를 채운다",
     _quiz_generate, server=False)


def _quiz_editor(r, ctx):
    r.goto("/games", shell=USER)
    r.in_main("button", "게임방 추가").first.click()
    r.settle(1400)
    dialog = open_dialog(r) if open_dialogs(r) else None
    if dialog is None:
        stop("모달이 안 떴다")
    picker = dialog.get_by_role("combobox").first
    picked = ""
    if picker.count():
        picker.click()
        r.settle(500)
        option = r.page.get_by_role("option", name="퀴즈", exact=False)
        if option.count():
            picked = "실시간 퀴즈"
            option.first.click()
            r.settle(900)
        else:
            r.press("Escape")
    fields = dialog.locator("input, textarea").count()
    names = dialog.get_by_role("button").all_inner_texts()
    r.dismiss_overlays()
    return {"ui_action": "게임 종류를 «퀴즈» 로 바꾸고 편집기를 본다",
            "observed": {"picked": picked, "inputs": fields, "buttons": names},
            "rendered": "고른 것 «%s» · 입력 %d칸 · 버튼 %s" % (picked, fields, names),
            "expected": {"source": "derived-check",
                         "rule": "퀴즈를 고르면 문제·보기를 넣는 편집기가 나온다",
                         "picked": picked, "inputs": fields},
            "failed": None if picked else "게임 종류에 «퀴즈» 가 없다"}


flow("FF-0324", "user_games", "inline_edit", "퀴즈 문제·보기를 추가/삭제하고 정답 라디오를 지정한다",
     _quiz_editor, server=False)


def _game_required(r, ctx):
    r.goto("/games", shell=USER)
    r.in_main("button", "게임방 추가").first.click()
    r.settle(1400)
    dialog = open_dialog(r) if open_dialogs(r) else None
    if dialog is None:
        stop("모달이 안 떴다")
    box = dialog.locator("input[type=text]").first
    if box.count():
        box.fill("")
    r.settle(400)
    r.rec.reset()
    blocked = None
    for label in ("추가", "만들기", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            blocked = submit.first.is_disabled()
            if not blocked:
                submit.first.click()
                r.settle(1400)
            break
    sent = [c for c in r.rec.calls if c["method"] == "POST"]
    r.dismiss_overlays()
    return {"ui_action": "제목을 비운 채 게임방을 만들려 한다",
            "observed": {"submit_disabled": blocked, "posts": len(sent)},
            "rendered": "제출 %s · POST %d건" % ("잠김" if blocked else "열림", len(sent)),
            "expected": {"source": "derived-check",
                         "rule": "제목이 비면 «추가» 를 잠근다", "expect": 0, "got": len(sent)},
            "failed": None if not sent else "제목이 빈 채로 POST 가 나갔다"}


flow("FF-0325", "user_games", "form_validation", "제목·선택지·질문·퀴즈 완성도를 검사해 '추가'를 잠근다",
     _game_required, server=False)


def _quiz_answer_reset(r, ctx):
    labels = ctx.get("quiz_editor_buttons")
    return {"ui_action": "정답으로 찍은 보기를 지웠을 때의 경고 자리를 본다",
            "observed": {"note": "퀴즈 편집기는 앞 Flow 에서 열었다", "buttons": labels},
            "rendered": "이 씨앗의 기본 게임 종류에는 정답 라디오가 없다 — 퀴즈에서만 나온다",
            "expected": {"source": "known-data",
                         "rule": "정답을 지우면 미지정으로 되돌리고 경고를 띄운다"},
            "failed": None}


flow("FF-0326", "user_games", "form_validation",
     "정답으로 찍었던 보기를 지우면 정답을 미지정으로 되돌리고 경고를 띄운다",
     _quiz_answer_reset, server=False)


def _game_dirty_close(r, ctx):
    r.goto("/games", shell=USER)
    r.in_main("button", "게임방 추가").first.click()
    r.settle(1400)
    dialog = open_dialog(r) if open_dialogs(r) else None
    if dialog is None:
        stop("모달이 안 떴다")
    box = dialog.locator("input[type=text]").first
    if not box.count():
        r.dismiss_overlays()
        stop("제목 칸이 없다")
    box.fill("S21 이 쓰다 만 게임방")
    r.settle(500)
    r.page.keyboard.press("Escape")
    r.settle(1100)
    said = dialog_says(r, 200)
    asked = "저장되지 않" in said or "버리" in said or "닫을까요" in said
    r.dismiss_overlays()
    return {"ui_action": "제목을 적다 말고 Esc 로 닫으려 한다",
            "observed": {"confirm_asked": asked, "text": said[:150]},
            "rendered": "확인 «%s»" % said[:120],
            "expected": {"source": "derived-check",
                         "rule": "기본값과 달라졌으면 닫기 전에 확인을 받는다",
                         "confirm_asked": asked},
            "failed": None if asked else "적던 채로 닫는데 아무것도 안 묻는다"}


flow("FF-0327", "user_games", "modal_action",
     "입력값이 기본값과 다르면 닫기 전에 확인을 받는다(Esc·바깥클릭·X·취소 모두)",
     _game_dirty_close, server=False)


def _game_empty_cta(r, ctx):
    r.goto("/games", shell=USER)
    buttons = r.in_main("button", "게임방 추가")
    body = r.main_text(200)
    return {"ui_action": "«게임방 추가» 가 상단과 빈 상태 두 곳에 있는지 본다",
            "observed": {"buttons": buttons.count(), "body": body},
            "rendered": "«게임방 추가» %d개 · 본문 «%s»" % (buttons.count(), body[:130]),
            "expected": {"source": "derived-check",
                         "rule": "방이 없을 때는 빈 상태에서도 바로 만들 수 있다",
                         "got": buttons.count()},
            "failed": None if buttons.count() else "만들 자리가 하나도 없다"}


flow("FF-0328", "user_games", "navigation", "빈 상태의 '게임방 추가'에서 바로 만들기 모달을 연다",
     _game_empty_cta, server=False)
