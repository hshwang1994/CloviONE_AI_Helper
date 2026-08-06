"""알림 딥링크 목적지 표 (related_object_type → 화면 경로).

**표 하나만 고친다.** 예전엔 "이 알림을 누르면 어디로 가나"가 프런트 NotificationBell 의
`OBJ_ROUTE`/`OBJ_ID_PARAM` 두 개와 registry.js 에 흩어져 있었고, 새 유형이 생길 때마다
`if` 가 한 줄씩 늘었다. 목적지는 **어떤 객체가 어디에 사는지**에 대한 서버의 지식이므로
서버가 계산해서 응답에 실어 준다 — 프런트는 받은 경로로 이동만 한다.

경로는 **해시 라우터 경로**(`/chat-rooms/<id>`)다. 앞에 `#` 이 없는 것이 정상이며,
링크로 쓸 때만 `"#" + route` 로 붙인다(React Router 의 `navigate()` 는 `#` 없는 경로를 받는다).

새 유형을 추가할 때 지켜야 할 것:
- **그 화면이 실제로 그 id 를 소비해야 한다.** 소비하지 않는 화면으로 보내면 목록만 열리고
  사용자는 대상을 다시 찾아야 한다 — 그런 유형은 표에 넣지 않는다(정적 알림으로 남긴다).
- **경로는 권한과 무관하다.** 접근 통제는 서버 라우터가 한다. 프런트는 역할에 맞지 않는
  목적지를 감출 수 있지만 그건 UX 이지 경계가 아니다.
"""

from __future__ import annotations

# related_object_type → 경로 템플릿. `{id}` 가 related_object_id 자리다.
# id 가 없으면(템플릿에 `{id}` 가 있는데 값이 비었으면) 딥링크를 만들지 않는다.
RELATED_DESTINATIONS: dict[str, str] = {
    # 채팅 초대(chat_invited) — 초대된 방으로 바로 들어간다.
    "chat_room": "/chat-rooms/{id}",
    # @멘션(chat_mentioned) — 불린 그 방으로 들어간다. id 는 room_id 다.
    #
    # `chat_room` 과 경로가 같은데 왜 키를 나눴나: 목적지는 **관련 객체의 종류**로 정하는데,
    # 멘션이 가리키는 것은 '방'이 아니라 '그 방에서 나를 부른 말'이다. 한 칸으로 합치면
    # 나중에 메시지 앵커(`/chat-rooms/{id}?seq=…`)로 정밀해질 때 초대 알림까지 같이 끌려가고,
    # 그때 둘을 다시 떼려면 프런트에 유형 분기를 넣어야 한다 — 이 표를 만든 이유가 그걸
    # 없애는 것이었다. 지금 나누는 비용은 한 줄이고, 나중에 합치는 비용은 프런트 분기다.
    "chat_mention": "/chat-rooms/{id}",
    # 티켓(ticket_assigned, ticket_comment) — 티켓 상세로 바로 들어간다. id 는 Notion page id
    # 이고, `/tickets/:id` 가 그 값을 그대로 `GET /api/tickets/{page_id}` 에 쓴다
    # (frontend/src/screens/Ticket.jsx). 즉 위 첫 번째 규칙("그 화면이 실제로 그 id 를
    # 소비해야 한다")을 만족한다.
    #
    # 배정 알림을 만들면서 넣었지만 **댓글 알림(ticket_comment)도 같이 살아난다** — 그쪽은
    # related 를 이미 ("ticket", page_id) 로 싣고 있었는데 표에 칸이 없어 목적지가 늘 null
    # 이었다. 한 표만 고치면 둘 다 따라오는 것이 이 표를 만든 이유다.
    "ticket": "/tickets/{id}",
}

# 문서 생성 완료(document_ready)는 일부러 여기 없다. 관리 콘솔의 문서 화면은 목록 화면이라
# 경로가 `#/documents?id=…` 형태이고, 그 질의 파라미터 지식은 이미 프런트 표
# (frontend/src/screens/registry.js 의 OBJ_ROUTE/OBJ_ID_PARAM)가 `document_generation` 으로
# 들고 있다. 같은 지식을 여기 한 벌 더 쓰면 두 표가 어긋나는 날이 온다 — 그 화면이 단건
# 라우트(`/documents/{id}`)를 갖게 되면 그때 여기 한 줄 추가하고 프런트 쪽을 지운다.

# 아직 표에 없는 관련 유형(approval / schedule / job / runner / user)은 **일부러** 비워 둔다.
# 그 화면들은 전부 목록 화면(DataScreen)이라 경로에 id 자리가 없다 — 보내 봐야 목록만 열리고
# 사용자는 대상을 눈으로 다시 찾아야 한다. 위 docstring 의 첫 번째 규칙이 그것이다.
# 그 화면들이 단건 라우트를 갖게 되는 날 여기 한 줄씩 추가하면 프런트는 손대지 않는다.


def destination_for(related_object_type: str | None, related_object_id: str | None) -> str | None:
    """딥링크 경로 또는 None(목적지가 없거나 id 가 없으면)."""
    template = RELATED_DESTINATIONS.get(related_object_type or "")
    if not template:
        return None
    if "{id}" in template:
        if not related_object_id:
            return None
        # id 는 서버가 만든 UUID 다. 그래도 경로를 깨뜨릴 문자는 통과시키지 않는다.
        if any(ch in related_object_id for ch in "/?#\\ "):
            return None
        return template.replace("{id}", related_object_id)
    return template
