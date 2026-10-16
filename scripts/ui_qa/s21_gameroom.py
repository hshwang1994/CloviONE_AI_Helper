"""S21 — 게임방 안 (W14).

게임방은 이 제품에서 **서버가 상태를 확정하고 화면은 따라 그리는** 유일한 자리다
(§13.1 — 결과는 클라이언트가 정하지 않는다). 그래서 여기서 묻는 것은 언제나 같다:
누른 뒤 **서버에 그 요청이 갔는가**, 그리고 방 상태가 그 뒤에 바뀌었는가.

방은 이 회차가 **직접 만든다**. 씨앗이 심어 둔 방은 목록을 한 번 부르는 순간 서버의
유령 방 정리(`cleanup_idle_rooms`)가 닫아 버린다 — 사람이 폴링하지 않는 방은 버려진
방이라는 것이 그 계약이다. 남이 만든 방에 기대면 Flow 가 그 계약과 싸우게 된다.
"""

from __future__ import annotations

from scripts.ui_qa.s21_kit import (  # noqa: F401
    confirm_now, dialog_says, flow, open_dialog, open_dialogs, stop,
)

USER = "/"
ROOMS = "/api/games/rooms"


def _ensure_room(r, ctx) -> str:
    """이 회차가 만든 방 안에 있게 한다."""
    if ctx.get("gameroom_hash") and ctx["gameroom_hash"] in r.hash_of():
        return ctx["gameroom_hash"]
    r.goto("/games", shell=USER)
    button = r.in_main("button", "게임방 추가")
    if not button.count():
        stop("«게임방 추가» 버튼이 없다")
    button.first.click()
    r.settle(1400)
    if not open_dialogs(r):
        stop("만들기 모달이 안 떴다")
    dialog = open_dialog(r)
    box = dialog.locator("input[type=text]").first
    if not box.count():
        r.dismiss_overlays()
        stop("제목 칸이 없다")
    box.fill("S21 점검 방")
    r.settle(400)
    for label in ("추가", "만들기", "저장"):
        submit = dialog.get_by_role("button", name=label, exact=True)
        if submit.count():
            submit.first.click()
            break
    else:
        names = dialog.get_by_role("button").all_inner_texts()
        r.dismiss_overlays()
        stop("만드는 버튼이 없다 — 있는 것: %s" % names)
    r.settle(2800)
    if "/games/" not in r.hash_of():
        stop("방을 만들었는데 방 화면으로 안 갔다: %s" % r.hash_of())
    ctx["gameroom_hash"] = r.hash_of()
    return ctx["gameroom_hash"]


def _state_poll(r, ctx):
    _ensure_room(r, ctx)
    r.rec.reset()
    r.settle(4200)
    polls = [c for c in r.rec.calls if "/state" in c["path"]]
    since = sorted({c["query"] for c in polls if c["query"]})[:3]
    return {"ui_action": "방 안에 머물며 상태 폴링을 관측한다(4초)",
            "frontend_state": "since 를 올려 가며 이벤트를 따라간다",
            "observed": {"polls": len(polls), "queries": since},
            "rendered": "4초 동안 상태 요청 %d건 · 질의 %s" % (len(polls), since),
            "expected": {"source": "derived-check",
                         "rule": "방 안에서는 상태를 스스로 계속 받는다",
                         "expect": ">=1", "got": len(polls)},
            "failed": None if polls else "방 안인데 상태 폴링이 한 번도 안 돈다"}


flow("FF-0329", "user_games-id", "read", "방 상태·참여자·이벤트를 폴링으로 따라간다",
     _state_poll, api="/api/games/rooms")


def _auto_join(r, ctx):
    hash_path = _ensure_room(r, ctx)
    r.rec.reset()
    r.goto(hash_path, shell=USER)
    r.settle(2400)
    joins = [c for c in r.rec.calls if "/join" in c["path"]]
    body = r.main_text(200)
    return {"ui_action": "방 주소로 다시 들어간다",
            "frontend_state": "한 번 자동 입장한다(가득/진행 중이면 서버가 관전으로)",
            "observed": {"join_calls": len(joins), "body": body},
            "rendered": "join 요청 %d건 · 본문 «%s»" % (len(joins), body[:150]),
            "expected": {"source": "derived-check",
                         "rule": "이미 들어와 있으면 다시 부르지 않는 것도 정답이다",
                         "joins": len(joins)},
            "failed": None if body else "방을 열었는데 본문이 비었다"}


flow("FF-0330", "user_games-id", "deep_link",
     "방 주소로 들어오면 한 번 자동 입장한다(가득/진행 중이면 서버가 관전으로)",
     _auto_join, api="/api/games/rooms")


def _room_action(label: str, api_hint: str, *, confirm: bool = False,
                 required: bool = True):
    """방 안의 동작 하나 — **서버로 갔는가**가 판정이다."""
    def _act(r, ctx):
        _ensure_room(r, ctx)
        target = r.in_main("button", label)
        if not target.count():
            if required:
                names = [" ".join((r.page.locator("#main-content button").nth(i)
                                   .inner_text() or "").split())
                         for i in range(min(r.page.locator(
                             "#main-content button").count(), 14))]
                stop("«%s» 가 없다 — 지금 있는 버튼: %s" % (label, names))
            return {"ui_action": "«%s» 자리를 찾는다" % label,
                    "observed": {"buttons": 0, "body": r.main_text(150)},
                    "rendered": "«%s» 없음 — 이 게임·이 상태에는 그 동작이 없다" % label,
                    "expected": {"source": "known-data",
                                 "rule": "게임 종류와 상태가 낼 수 있는 동작을 가른다"},
                    "failed": None}
        r.rec.reset()
        target.first.click()
        r.settle(1200)
        asked = open_dialogs(r) > 0
        said = confirm_now(r) if asked else ""
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«%s» 를 누른다" % label,
                "frontend_state": ("확인 → 실행" if asked else "바로 실행"),
                "observed": {"calls": calls, "confirm_asked": asked,
                             "confirm": said[:130], "hash": r.hash_of()},
                "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, r.main_text(120)),
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "failed": (("확인 없이 실행됐다" if confirm and not asked else None)
                           or (None if any(api_hint in c for c in calls)
                               else "«%s» 를 눌렀는데 %s 를 안 불렀다: %s"
                                    % (label, api_hint, calls)))}
    return _act


flow("FF-0331", "user_games-id", "status_change", "준비/준비 해제를 토글한다",
     _room_action("준비", "/ready"), api="/api/games/rooms")

flow("FF-0332", "user_games-id", "status_change", "방장이 게임을 시작한다(게임별 라벨)",
     _room_action("시작", "/start"), api="/api/games/rooms")

flow("FF-0333", "user_games-id", "status_change", "방장이 투표를 종료하거나 결과를 공개한다",
     _room_action("종료", "/finish", required=False), api="/api/games/rooms", server=False)

flow("FF-0334", "user_games-id", "status_change", "방장이 퀴즈 정답을 공개한다",
     _room_action("정답 공개", "/reveal", required=False), api="/api/games/rooms",
     server=False)

flow("FF-0335", "user_games-id", "status_change", "방장이 다음 문제로 넘기거나 결과를 연다",
     _room_action("다음", "/next", required=False), api="/api/games/rooms", server=False)

flow("FF-0336", "user_games-id", "status_change", "방장이 끝난 게임을 '다시 하기'로 초기화한다",
     _room_action("다시 하기", "/reset", required=False), api="/api/games/rooms",
     server=False)


def _vote(r, ctx):
    _ensure_room(r, ctx)
    options = r.page.locator("#main-content button")
    target = None
    for i in range(options.count()):
        label = " ".join((options.nth(i).inner_text() or "").split())
        if label in ("국밥", "돈가스", "비빔밥") or label.startswith("선택지"):
            target = options.nth(i)
            picked = label
            break
    if target is None:
        return {"ui_action": "투표 선택지를 찾는다",
                "observed": {"options": 0, "body": r.main_text(180)},
                "rendered": "선택지 없음 — 이 방은 아직 시작 전이거나 다른 게임이다",
                "expected": {"source": "known-data",
                             "rule": "투표는 시작한 뒤에만 낼 수 있다"},
                "failed": None}
    r.rec.reset()
    target.click()
    r.settle(2200)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    return {"ui_action": "선택지 «%s» 를 눌러 투표한다" % picked,
            "observed": {"calls": calls, "body": r.main_text(160)},
            "rendered": "쓰기 요청 %s · 본문 «%s»" % (calls, r.main_text(140)),
            "expected": {"source": "derived-check",
                         "rule": "선택지를 누르면 서버로 표가 간다", "got": calls},
            "failed": None if any("/vote" in c for c in calls)
                      else "선택지를 눌렀는데 투표가 서버로 안 갔다: %s" % calls}


flow("FF-0337", "user_games-id", "row_action", "투표 선택지를 눌러 제출한다(현재 득표가 함께 보인다)",
     _vote, api="/api/games/rooms", server=False)


def _typed_submit(label: str, api_hint: str, value: str = "7"):
    def _act(r, ctx):
        _ensure_room(r, ctx)
        box = r.page.locator("#main-content input[type=number]:visible")
        if not box.count():
            return {"ui_action": "«%s» 를 낼 자리를 찾는다" % label,
                    "observed": {"inputs": 0, "body": r.main_text(170)},
                    "rendered": "낼 자리 없음 — 이 방은 그 게임이 아니다",
                    "expected": {"source": "known-data",
                                 "rule": "게임 종류가 낼 수단을 정한다"},
                    "failed": None}
        box.first.fill(value)
        r.rec.reset()
        submit = r.in_main("button", "내기")
        if not submit.count():
            submit = r.in_main("button", "제출")
        if submit.count():
            submit.first.click()
        else:
            r.page.keyboard.press("Enter")
        r.settle(2200)
        calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                        if c["method"] != "GET"})
        return {"ui_action": "«%s» 로 %s 를 낸다" % (label, value),
                "observed": {"calls": calls},
                "rendered": "쓰기 요청 %s" % calls,
                "expected": {"source": "derived-check",
                             "rule": "«%s» 는 %s 를 부른다" % (label, api_hint), "got": calls},
                "failed": None if any(api_hint in c for c in calls)
                          else "냈는데 %s 를 안 불렀다: %s" % (api_hint, calls)}
    return _act


flow("FF-0338", "user_games-id", "row_action", "숫자 눈치에서 낼 숫자를 입력해 제출한다",
     _typed_submit("숫자", "/pick"), api="/api/games/rooms", server=False)

flow("FF-0339", "user_games-id", "row_action", "가위바위보에서 낼 것을 고른다",
     _room_action("가위", "/rps", required=False), api="/api/games/rooms", server=False)

flow("FF-0340", "user_games-id", "row_action", "퀴즈 보기를 눌러 답을 제출한다",
     _room_action("보기", "/quiz-answer", required=False), api="/api/games/rooms",
     server=False)


def _ladder_path(r, ctx):
    _ensure_room(r, ctx)
    body = r.main_text(200)
    return {"ui_action": "사다리 결과에서 참가자를 눌러 경로를 강조한다",
            "observed": {"body": body},
            "rendered": "본문 «%s»" % body[:150],
            "expected": {"source": "known-data",
                         "rule": "사다리가 아닌 방에서는 강조할 경로가 없다"},
            "failed": None}


flow("FF-0341", "user_games-id", "row_action", "사다리 결과에서 참가자를 눌러 자기 경로를 강조한다",
     _ladder_path, server=False)


def _room_chat(r, ctx):
    _ensure_room(r, ctx)
    box = r.page.locator("#main-content input[type=text]:visible, "
                         "#main-content textarea:visible")
    if not box.count():
        stop("방 안 채팅 입력 칸이 없다")
    text = "S21 인수 점검 인사"
    box.last.fill(text)
    r.rec.reset()
    r.page.keyboard.press("Enter")
    r.settle(2400)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    body = r.main_text(240)
    return {"ui_action": "방 안 채팅으로 «%s» 를 보낸다" % text,
            "observed": {"calls": calls, "shown": text in body},
            "rendered": "쓰기 요청 %s · 본문에 «%s» %s"
                        % (calls, text, "있음" if text in body else "없음"),
            "expected": {"source": "derived-check",
                         "rule": "보낸 말이 서버로 가고 대화에 남는다", "expect": text},
            "failed": None if any("/chat" in c for c in calls)
                      else "채팅을 보냈는데 서버로 안 갔다: %s" % calls}


flow("FF-0342", "user_games-id", "create", "방 안 채팅으로 메시지를 보낸다(500자)",
     _room_chat, api="/api/games/rooms")


def _room_permission(r, ctx):
    hash_path = _ensure_room(r, ctx)
    mine = {label: r.in_main("button", label).count()
            for label in ("시작", "게임방 종료", "나가기", "준비")}
    got = r.as_role("user", hash_path, "/", lambda p: p.evaluate(
        """() => {
             const main = document.querySelector('#main-content');
             return {buttons: main ? Array.from(main.querySelectorAll('button')).map(
                       b => (b.innerText || '').replace(/\\s+/g,' ').trim()) : [],
                     body: (main ? main.innerText : '').replace(/\\s+/g,' ').trim().slice(0,180)};
           }"""))
    theirs = {label: sum(1 for n in got["buttons"] if label in n)
              for label in ("시작", "게임방 종료", "나가기", "준비")}
    return {"ui_action": "같은 방을 방장이 아닌 사용자로 연다",
            "frontend_state": "방장 여부·관전 여부로 진행 버튼이 갈린다",
            "observed": {"as_host": mine, "as_guest": theirs, "body": got["body"]},
            "rendered": "방장 %s · 손님 %s" % (mine, theirs),
            "expected": {"source": "derived-check",
                         "rule": "진행 버튼(시작·파하기)은 방장에게만 있다",
                         "as_guest": theirs},
            "failed": None if theirs.get("게임방 종료", 0) == 0
                      else "방장이 아닌 사람에게도 «방 파하기» 가 보인다"}


flow("FF-0345", "user_games-id", "permission_state",
     "방장 여부·관전자 여부로 진행 버튼과 제출 수단을 가른다",
     _room_permission, server=False)


def _room_retry(r, ctx):
    hash_path = _ensure_room(r, ctx)
    pattern = "**/api/games/rooms/**"
    r.page.route(pattern, lambda route: route.fulfill(
        status=503, content_type="application/json", body='{"detail":"끊었습니다."}'))
    try:
        r.page.reload(wait_until="domcontentloaded")
        r.page.wait_for_selector("#main-content", timeout=30_000)
        r.settle(3200)
        face = r.main_text(170)
        retry = r.in_main("button", "다시 시도")
        found = retry.count()
    finally:
        r.page.unroute(pattern)
    if found:
        retry.first.click()
        r.settle(2400)
    return {"ui_action": "방 상태 조회를 503 으로 끊는다",
            "observed": {"error_face": face, "retry": found},
            "rendered": "오류 «%s» → 복구 «%s»" % (face[:90], r.main_text(90)),
            "expected": {"source": "derived-check",
                         "rule": "503 이면 오류 얼굴과 «다시 시도» 를 준다", "got": found},
            "failed": None if found else "방이 503 인데 «다시 시도» 가 없다 — 얼굴: %s" % face}


flow("FF-0346", "user_games-id", "refresh", "상태 조회 실패 시 '다시 시도'를 준다",
     _room_retry, api="/api/games/rooms")

# 나가기와 파하기는 **마지막에** 둔다 — 방이 사라지면 앞의 Flow 들이 열 자리가 없다.
flow("FF-0343", "user_games-id", "navigation", "'나가기'로 방을 떠난다",
     _room_action("나가기", "/leave"), api="/api/games/rooms")


def _disband(r, ctx):
    ctx.pop("gameroom_hash", None)
    _ensure_room(r, ctx)
    button = r.in_main("button", "게임방 종료")
    if not button.count():
        stop("«게임방 종료» 버튼이 없다")
    r.rec.reset()
    button.first.click()
    r.settle(1200)
    asked = open_dialogs(r) > 0
    said = confirm_now(r) if asked else ""
    r.settle(2400)
    calls = sorted({"%s %s" % (c["method"], c["path"]) for c in r.rec.calls
                    if c["method"] != "GET"})
    ctx.pop("gameroom_hash", None)
    return {"ui_action": "방장이 «방 파하기» 를 실행한다",
            "frontend_state": "확인 → POST /disband → 목록으로",
            "observed": {"calls": calls, "confirm_asked": asked, "confirm": said[:130],
                         "hash": r.hash_of()},
            "rendered": "쓰기 요청 %s · 주소 «%s»" % (calls, r.hash_of()),
            "expected": {"source": "derived-check",
                         "rule": "되돌릴 수 없는 파하기는 확인을 받는다",
                         "confirm_asked": asked},
            "failed": ("확인 없이 방이 파해진다" if not asked
                       else (None if any("/disband" in c for c in calls)
                             else "확인했는데 서버로 안 갔다: %s" % calls))}


flow("FF-0344", "user_games-id", "delete", "방장이 확인 후 방을 파한다",
     _disband, api="/api/games/rooms")
