"""B9 Chat — `/chat-rooms` 와 그 대화 판 (W8 · S18).

이 원형이 답해야 하는 것: **대상 없는 입력창을 그리지 않는가**, 그리고 방을 고르면
그 대화가 실제로 열리는가. 폴링이 도는 화면이라 요청 수를 함께 적는다 — 「가만히 둬도
계속 부른다」와 「필요할 때만 부른다」는 화면만 보면 구별되지 않는다.
"""

from __future__ import annotations

from scripts.ui_qa.pilot_kit import (  # noqa: F401
    close_modal, dialog_text, dialogs, flow, modal_open_close, open_row_modal,
    required_blocks_submit, retry_from_error, stop,
)

ROOM_SEARCH = '#main-content input[aria-label="채팅방 이름 검색"]'
COMPOSER = '#main-content textarea, #main-content input[aria-label="메시지 입력"]'


def _room_buttons(r):
    return r.page.locator('[data-testid="chatroom-list-rows"] button')


def _rooms_read(r, ctx):
    rooms = _room_buttons(r)
    labels = [" ".join((rooms.nth(i).inner_text() or "").split())[:40]
              for i in range(min(rooms.count(), 6))]
    return {"ui_action": "/chat-rooms 를 연다",
            "url_state": r.hash_of(),
            "observed": {"rooms": labels},
            "rendered": "방 %d개 %s" % (rooms.count(), labels),
            "failed": None if rooms.count() else "방이 하나도 안 그려졌다"}


flow("FF-0208", "user_chat-rooms", "deep_link",
     "방 미지정으로 들어오면 내 팀 방(없으면 전체 채팅)으로 주소를 교체한다",
     _rooms_read, route="/chat-rooms", api="/api/team-chat/rooms")


def _rooms_search(r, ctx):
    box = r.page.locator(ROOM_SEARCH)
    if not box.count():
        stop("방 이름 검색 상자가 없다")
    before = _room_buttons(r).count()
    r.rec.reset()
    box.first.fill("장애")
    r.settle(1200)
    after = _room_buttons(r).count()
    calls = r.rec.matching("/api/team-chat/rooms")
    return {"ui_action": "방 이름 상자에 «장애» 를 넣는다",
            "frontend_state": "이미 받은 목록에서 거른다(서버 호출 없음)",
            "observed": {"rooms": {"before": before, "after": after},
                         "server_calls": len(calls)},
            "rendered": "방 %d개 → %d개 · 그 사이 목록 요청 %d회"
                        % (before, after, len(calls)),
            "failed": None if after < before else "걸렀는데 방이 안 줄었다"}


flow("FF-0201", "user_chat-rooms", "search",
     "채팅방 이름으로 목록을 거른다(서버 호출 없이 이미 받은 목록에서)",
     _rooms_search, route="/chat-rooms", server=False)


def _open_room(r, ctx):
    rooms = _room_buttons(r)
    if rooms.count() < 2:
        stop("고를 방이 둘 미만이다")
    label = " ".join((rooms.nth(1).inner_text() or "").split())[:40]
    before = r.hash_of()
    rooms.nth(1).click()
    r.settle(1600)
    ctx["room"] = r.hash_of()
    header = " ".join((r.page.locator("#main-content h2, #main-content h3").first
                       .inner_text() or "").split())[:40]
    return {"ui_action": "목록에서 «%s» 를 누른다" % label,
            "url_state": "%s → %s" % (before, r.hash_of()),
            "observed": {"header": header},
            "rendered": "대화 머리 «%s» · 주소 «%s»" % (header, r.hash_of()),
            "failed": None if r.hash_of() != before else "방을 눌렀는데 주소가 그대로다"}


flow("FF-0202", "user_chat-rooms", "navigation", "목록의 방 행을 눌러 오른쪽 칸에 그 대화를 연다",
     _open_room, route="/chat-rooms", api="/api/team-chat/rooms/")


def _new_group(r, ctx):
    open_row_modal(r, ctx, opener="button=새 그룹")
    # 방 이름 칸을 **id 로** 겨눈다 — 이 모달의 첫 `<input>` 은 초대할 사람을 찾는
    # 검색 상자라, 거기 글자를 넣으면 방 이름은 비어 있고 dirty 도 안 켜진다.
    r.page.locator("input#tc-gtitle").fill("S18 파일럿 방")
    r.settle(500)
    r.rec.reset()
    submit = r.page.get_by_role("button", name="추가")
    if not submit.count():
        submit = r.page.get_by_role("button", name="만들기")
    created = False
    if submit.count() and not submit.first.is_disabled():
        submit.first.click()
        r.settle(1800)
        created = True
    else:
        close_modal(r)
    calls = r.rec.matching("/api/team-chat/rooms")
    return {"ui_action": "«새 그룹» 으로 방 이름을 넣고 만든다",
            "observed": {"submitted": created,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:3]},
            "rendered": "방 %d개 · 본문 «%s»" % (_room_buttons(r).count(), r.main_text(70)),
            "cross": {"needle": "S18 파일럿 방"} if created else {},
            "failed": None if (not created or calls) else "만들었는데 요청이 없었다"}


flow("FF-0203", "user_chat-rooms", "create",
     "'새 그룹'으로 방 이름과 초대 인원을 정해 그룹 방을 만든다",
     _new_group, route="/chat-rooms", api="/api/team-chat/rooms",
     cross=("@reload", ""))


def _direct_message(r, ctx):
    # «1:1» 은 목록 행의 종류 꼬리표에도 쓰이는 낱말이라 **정확히** 그 이름만 누른다.
    button = r.page.get_by_role("button", name="1:1", exact=True)
    if not button.count():
        stop("«1:1» 버튼이 없다")
    before = dialogs(r)
    button.first.click()
    r.settle(1200)
    if dialogs(r) <= before:
        stop("«1:1» 을 눌렀는데 대화상자가 안 떴다")
    panel = r.page.locator('[role="dialog"]').last
    text = " ".join((panel.inner_text() or "").split())[:140]
    # 사람 목록은 `role="option"` 이 아니라 **평범한 `<button>`** 이다
    # (`ChatRooms::DirectModal`). `[role="option"]` 로 세면 후보가 늘 0명으로 잡혀,
    # 「패널은 떴는데 아무도 못 고른다」를 통과로 적게 된다.
    count = panel.locator("button").count()
    picked = ""
    r.rec.reset()
    for name in ("이서연", "김지훈", "박민준", "최유나"):
        target = panel.get_by_role("button", name=name)
        if target.count():
            picked = name
            target.first.click()
            r.settle(2400)
            break
    if not picked:
        close_modal(r)
    calls = r.rec.matching("/rooms/direct")
    return {"ui_action": "«1:1» 에서 «%s» 를 골라 대화를 시작한다" % (picked or "(후보 없음)"),
            "url_state": "→ %s" % r.hash_of(),
            "observed": {"panel": text, "buttons": count, "picked": picked,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "패널 «%s» · 고른 사람 «%s»" % (text, picked or "없음"),
            "cross": {"needle": picked} if picked else {},
            "failed": None if (text and picked and calls)
                      else "1:1 패널이 비었거나 대화가 시작되지 않았다"}


flow("FF-0204", "user_chat-rooms", "create",
     "'1:1'로 디렉터리에서 상대를 골라 대화를 시작한다",
     _direct_message, route="/chat-rooms", api="/api/team-chat",
     cross=("@reload", ""))

flow("FF-0205", "user_chat-rooms", "form_validation",
     "방 이름이 비면 '추가'가 비활성이다(서버 MAX_TITLE과 같은 200자 상한)",
     required_blocks_submit("button=새 그룹"), route="/chat-rooms", server=False)


def _dirty_close(r, ctx):
    open_row_modal(r, ctx, opener="button=새 그룹")
    r.page.locator("input#tc-gtitle").fill("버리기 확인")
    r.settle(400)
    r.press("Escape")
    r.settle(900)
    asked = bool(r.page.locator('[role="dialog"]').last
                 .get_by_role("button", name="닫기").count())
    close_modal(r)
    return {"ui_action": "이름을 입력한 채 Esc 를 누른다",
            "frontend_state": "dirty=true",
            "observed": {"confirm_shown": asked},
            "rendered": "확인 창 %s" % ("떴다" if asked else "안 떴다"),
            "failed": None if asked else "입력이 남았는데 그냥 닫혔다"}


flow("FF-0206", "user_chat-rooms", "modal_action",
     "입력한 내용이 있으면 모달 닫기 전에 확인을 받는다(Esc·바깥클릭·X·취소 모두)",
     _dirty_close, route="/chat-rooms", server=False)


def _rooms_polling(r, ctx):
    r.rec.reset()
    r.page.wait_for_timeout(12_000)
    calls = r.rec.matching("/api/team-chat/rooms")
    return {"ui_action": "화면을 그대로 두고 12초를 기다린다",
            "frontend_state": "목록 폴링 5초",
            "observed": {"calls_in_12s": len(calls)},
            "rendered": "12초 동안 목록 요청 %d회" % len(calls),
            "failed": None if calls else "폴링이 돌지 않는다",
            "notes": [] if len(calls) <= 6
                     else ["12초에 %d회는 5초 간격보다 잦다" % len(calls)]}


flow("FF-0207", "user_chat-rooms", "refresh",
     "목록을 5초마다 폴링하고, 조회 실패 시 '다시 시도'를 준다",
     _rooms_polling, route="/chat-rooms", api="/api/team-chat/rooms", tags=("slow",))


def _back_to_list(r, ctx):
    """이 버튼은 **좁은 화면에만** 있다 — 넓은 화면에서는 목록과 대화가 나란히 있으니
    돌아갈 곳이 없다. 그래서 창을 좁혀서 확인하고 원래대로 돌린다."""
    wide = bool(r.page.get_by_role("button", name="목록").count())
    r.page.set_viewport_size({"width": 720, "height": 1080})
    r.settle(1200)
    button = r.page.get_by_role("button", name="목록")
    narrow = bool(button.count())
    if narrow:
        button.first.click()
        r.settle(1200)
    rooms = _room_buttons(r).count()
    r.page.set_viewport_size({"width": 1920, "height": 1080})
    r.settle(900)
    return {"ui_action": "창을 720px 로 좁히고 «목록» 을 누른다",
            "frontend_state": "좁은 화면 = 한 칸씩 보인다",
            "observed": {"button_at_1920": wide, "button_at_720": narrow},
            "rendered": "1920 에서 «목록» %s · 720 에서 %s · 방 %d개"
                        % (wide, narrow, rooms),
            "failed": None if (narrow and not wide)
                      else "좁은 화면 전용 버튼이 아니다(1920 %s · 720 %s)" % (wide, narrow)}


flow("FF-0209", "user_chat-rooms", "navigation",
     "좁은 화면에서 '목록' 버튼으로 방 목록으로 돌아간다",
     _back_to_list, route="/chat-rooms", server=False)


def _directory(r, ctx):
    r.rec.reset()
    open_row_modal(r, ctx, opener="button=1:1")
    r.settle(1200)
    calls = r.rec.matching("/directory")
    close_modal(r)
    return {"ui_action": "«1:1» 을 열어 사용자 디렉터리를 부른다",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "디렉터리 요청 %d회" % len(calls),
            "failed": None if calls else "디렉터리를 부르지 않았다"}


flow("FF-0210", "user_chat-rooms", "read", "초대·1:1 상대 목록으로 사용자 디렉터리를 조회한다",
     _directory, route="/chat-rooms", api="/directory")


# ═══════════════════════════════════════════════════════════════════════════
# 대화 판
# ═══════════════════════════════════════════════════════════════════════════
def _send_message(r, ctx):
    box = r.page.locator(COMPOSER).last
    if not box.count():
        stop("메시지 입력칸이 없다")
    box.fill("S18 파일럿 점검 메시지입니다.")
    r.settle(400)
    r.rec.reset()
    send = r.page.get_by_role("button", name="보내기")
    if not send.count():
        stop("«보내기» 가 없다")
    send.first.click()
    r.settle(1800)
    calls = r.rec.matching("/messages")
    return {"ui_action": "메시지를 쓰고 «보내기» 를 누른다",
            "frontend_state": "draft → 전송 후 비움",
            "observed": {"calls": [(c["method"], c["path"], c["status"]) for c in calls][:3],
                         "draft_after": box.input_value() if box.count() else ""},
            "rendered": "본문 «%s»" % r.main_text(140),
            "cross": {"needle": "S18 파일럿 점검 메시지입니다."},
            "failed": None if calls else "전송 요청이 없었다"}


flow("FF-1155", "user_chat-rooms__chat-pane", "create",
     "메시지를 보낸다(Enter 전송, 2000자 상한)", _send_message,
     route="/chat-rooms", api="/messages", cross=("@reload", ""))


def _empty_send_gate(r, ctx):
    box = r.page.locator(COMPOSER).last
    if box.count():
        box.fill("")
        r.settle(400)
    send = r.page.get_by_role("button", name="보내기")
    disabled = send.first.is_disabled() if send.count() else None
    return {"ui_action": "입력을 비우고 «보내기» 상태를 본다",
            "frontend_state": "draft='' ",
            "observed": {"disabled": disabled},
            "rendered": "«보내기» %s" % ("비활성" if disabled else "활성"),
            "failed": None if disabled else "빈 입력인데 보내기가 눌린다"}


flow("FF-1163", "user_chat-rooms__chat-pane", "form_validation",
     "빈 입력이면 보내기 버튼이 비활성이다", _empty_send_gate,
     route="/chat-rooms", server=False)


def _pane_control(name: str, what: str):
    """대화 판의 컨트롤 하나를 연다 — **그것이 있는 방**을 찾아서.

    「언급할 사람 고르기」는 **다른 사람이 있는 방에만** 그려진다(`ChatPane.jsx` —
    `pickable.length > 0`). 그것이 옳다. 그런데 표가 아무 방에서나 재면 「없다」로 죽고,
    그 죽음은 제품의 정답을 결함처럼 보이게 한다. 방을 하나씩 열어 그 컨트롤이 있는
    자리에서 잰다 — 어느 방에도 없으면 그 사실을 적는다.
    """
    def _act(r, ctx):
        def _find():
            got = r.page.get_by_role("button", name=name)
            return got if got.count() else r.page.get_by_label(name)

        button = _find()
        if not button.count():
            rooms = _room_buttons(r)
            for i in range(min(rooms.count(), 6)):
                rooms.nth(i).click()
                r.settle(1400)
                button = _find()
                if button.count():
                    break
        if not button.count():
            return {"ui_action": "«%s» 가 있는 방을 찾는다" % name,
                    "frontend_state": "이 컨트롤은 조건이 맞는 방에만 그려진다",
                    "observed": {"rooms_tried": _room_buttons(r).count()},
                    "rendered": "이 씨앗의 어느 방에도 «%s» 가 없다" % name,
                    "notes": ["«%s» 는 조건이 맞는 방에만 그려진다 — 없는 것이 답인 경우가 있다"
                              % name]}
        button.first.click()
        r.settle(900)
        panel = r.page.locator('[role="dialog"], [role="menu"], [role="presentation"]').last
        text = " ".join((panel.inner_text() or "").split())[:140] if panel.count() else ""
        r.press("Escape")
        return {"ui_action": "«%s» 를 연다" % name,
                "observed": {"panel": text},
                "rendered": "%s 패널 «%s»" % (what, text),
                "failed": None if text else "%s 패널이 비었다" % what}
    return _act


flow("FF-1158", "user_chat-rooms__chat-pane", "modal_action",
     "이모지 피커에서 골라 커서 자리에 넣는다",
     _pane_control("이모지 넣기", "이모지"), route="/chat-rooms", server=False)
flow("FF-1159", "user_chat-rooms__chat-pane", "modal_action",
     "언급할 사람을 목록에서 골라 @이름 을 넣는다",
     _pane_control("언급할 사람 고르기", "언급"), route="/chat-rooms", server=False)


def _delete_message(r, ctx):
    button = r.page.get_by_role("button", name="메시지 삭제", exact=False)
    if not button.count():
        stop("«메시지 삭제» 가 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1000)
    text = dialog_text(r, 140)
    panel = r.page.locator('[role="dialog"]').last
    for label in ("삭제", "확인"):
        ok = panel.get_by_role("button", name=label, exact=True)
        if ok.count():
            ok.first.click()
            break
    r.settle(2200)
    # 이 제품은 메시지 삭제를 **POST /messages/{seq}/delete** 로 보낸다 — HTTP 동사가
    # 아니라 경로가 그 뜻을 말한다. `method == "DELETE"` 로 세면 실제로 지웠는데도
    # 「삭제 요청이 없었다」가 된다.
    calls = [c for c in r.rec.calls if "/delete" in c["path"]]
    return {"ui_action": "내 메시지를 확인 뒤 삭제한다",
            "observed": {"confirm": text,
                         "calls": [(c["method"], c["path"], c["status"]) for c in calls][:2]},
            "rendered": "본문 «%s»" % r.main_text(140),
            "cross": {"needle": "메시지를 삭제했습니다"},
            "failed": None if calls else "삭제 요청이 없었다"}


flow("FF-1157", "user_chat-rooms__chat-pane", "delete",
     "내 메시지를 확인 후 삭제한다(대화에는 삭제 기록이 남는다)",
     _delete_message, route="/chat-rooms", api="/messages", cross=("@reload", ""))


def _inline_images(r, ctx):
    images = r.page.locator('#main-content [data-testid*="message"] img, #main-content img')
    return {"ui_action": "말풍선 안의 이미지 자리를 본다",
            "observed": {"images": images.count()},
            "rendered": "이미지 %d개 — 이 표본의 메시지에는 이미지가 %s"
                        % (images.count(), "있다" if images.count() else "없다"),
            "notes": [] if images.count()
                     else ["붙여넣기 이미지가 없는 방이다 — 라이트박스는 그릴 것이 없다"]}


flow("FF-1156", "user_chat-rooms__chat-pane", "attachment",
     "Ctrl+V 로 붙여넣은 이미지를 업로드해 말풍선 안에 인라인으로 보낸다",
     _inline_images, route="/chat-rooms", server=False)
flow("FF-1160", "user_chat-rooms__chat-pane", "modal_action",
     "말풍선 안 이미지를 라이트박스로 크게 본다",
     _inline_images, route="/chat-rooms", server=False)


def _unread_badge(r, ctx):
    rooms = _room_buttons(r)
    labels = [" ".join((rooms.nth(i).inner_text() or "").split())
              for i in range(rooms.count())]
    with_badge = [x for x in labels if any(ch.isdigit() for ch in x.split()[-1:])]
    target = None
    for i, text in enumerate(labels):
        if "장애" in text:
            target = i
            break
    before = labels[target] if target is not None else ""
    if target is not None:
        rooms.nth(target).click()
        r.settle(2200)
    after_labels = [" ".join((_room_buttons(r).nth(i).inner_text() or "").split())
                    for i in range(_room_buttons(r).count())]
    after = after_labels[target] if target is not None and target < len(after_labels) else ""
    return {"ui_action": "안 읽은 것이 남은 방을 연다",
            "frontend_state": "읽음 커서 기록 → 목록 배지 감소",
            "observed": {"rooms_with_badge": with_badge,
                         "target": {"before": before, "after": after}},
            "rendered": "«%s» → «%s»" % (before, after),
            "failed": None if before else "안 읽은 방을 못 찾았다"}


flow("FF-1161", "user_chat-rooms__chat-pane", "notification_action",
     "새 메시지를 받으면 읽음 커서를 기록하고 목록 배지를 캐시에서 줄인다",
     _unread_badge, route="/chat-rooms", api="/api/team-chat")


def _pane_poll_fail(r, ctx):
    pattern = "**/messages**"
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었다"}'))
    try:
        r.settle(4000)
        body = r.main_text(160)
        retry = r.page.get_by_role("button", name="다시 시도")
        present = bool(retry.count())
    finally:
        r.page.unroute(pattern)
    r.settle(2000)
    return {"ui_action": "메시지 폴링을 503 으로 끊는다",
            "frontend_state": "폴링 실패 — 대화는 유지",
            "observed": {"retry_present": present, "body": body},
            "rendered": "본문 «%s» · «다시 시도» %s" % (body, present),
            "failed": None if body else "대화가 통째로 사라졌다"}


flow("FF-1162", "user_chat-rooms__chat-pane", "refresh",
     "폴링이 실패해도 대화를 유지한 채 '다시 시도'만 준다",
     _pane_poll_fail, route="/chat-rooms", api="/messages", server=False)


def _pane_poll_interval(r, ctx):
    r.rec.reset()
    r.page.wait_for_timeout(12_000)
    calls = r.rec.matching("/messages")
    return {"ui_action": "대화를 열어 둔 채 12초를 기다린다",
            "frontend_state": "조용한 방일수록 간격이 늘어난다",
            "observed": {"calls_in_12s": len(calls)},
            "rendered": "12초 동안 메시지 요청 %d회" % len(calls),
            "failed": None if calls else "폴링이 아예 안 돈다"}


flow("FF-1164", "user_chat-rooms__chat-pane", "read",
     "방이 조용한 정도·탭 가시성에 따라 폴링 간격을 늘려 메시지를 따라간다",
     _pane_poll_interval, route="/chat-rooms", api="/messages", tags=("slow",))
