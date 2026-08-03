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
}


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
