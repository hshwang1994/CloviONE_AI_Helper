"""홈 '오늘'의 채팅 안읽음 합계가 방 개수에 비례해 질의를 늘리지 않는다 (M2).

## 왜 이 파일이 있는가

`GET /api/home/today` 는 사이드바 '오늘' 진입점에서 자주 뜬다. 이 응답의 `inbox.chat_unread`
는 `app/home/readers.chat_unread` 가 만드는데, 이 함수는 사용자가 속한 방을 모두 읽은 뒤
**방마다** `chat_repo.get_member(db, room.id, user.id)` 를 따로 물었다 — 방이 늘면 질의가
그만큼 늘어난다. `GET /api/team-chat/rooms` 는 이미 이 함정을 한 번 겪고 고쳤지만
(tests/regression/test_team_chat_rooms_query_count.py, H4), 그 수정은 team_chat 라우터
안에만 있었고 홈이 같은 계산을 다시 구현한 이 경로는 그대로 남아 있었다(M2).

## 어떻게 판정하는가

방 개수를 **바꿔 가며** 실행한 SELECT 개수를 세고, 그 차이를 본다. 절대 개수를 못 박지
않는 이유는 team_chat 쪽 테스트와 같다 — 이 경로에도 세션·인증 같은 곁가지 질의가 붙는다.
**방이 늘어도 질의가 늘지 않는다** 하나만 본다. 값이 실제로 달라지는 표본을 쓴다 — 방 2개와
방 8개.
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

pytestmark = pytest.mark.regression


class QueryCounter:
    """엔진에 붙여 실행된 SELECT 문을 센다. 커서 단위라 ORM 지연 로딩도 잡힌다."""

    def __init__(self, engine):
        self.engine = engine
        self.statements: list[str] = []

    def _on_execute(self, conn, cursor, statement, parameters, context, executemany):
        if statement.lstrip().upper().startswith("SELECT"):
            self.statements.append(statement)

    def __enter__(self):
        event.listen(self.engine, "before_cursor_execute", self._on_execute)
        return self

    def __exit__(self, *exc):
        event.remove(self.engine, "before_cursor_execute", self._on_execute)
        return False

    @property
    def count(self) -> int:
        return len(self.statements)


def _make_rooms(client, csrf, others, count):
    """1:1 방을 count 개 만든다 — 방마다 상대가 먼저 말을 걸어(내 안읽음 발생)."""
    for i in range(count):
        client.post(
            "/api/team-chat/rooms/direct",
            json={"user_id": others[i].id},
            headers={"X-CSRF-Token": csrf},
        )


def test_home_today_chat_unread_query_count_does_not_grow_with_rooms(
    app, client, login_as, make_user
):
    csrf = login_as("user", email="home-qc-me@goodmit.co.kr")
    others = [make_user(email=f"home-qc-p{i}@goodmit.co.kr", display_name=f"홈상대{i}") for i in range(8)]

    _make_rooms(client, csrf, others, 2)
    # 첫 호출은 팀 방 보장 같은 1회성 곁가지 질의를 유발할 수 있다 — 기준선 앞에서 한 번 흘린다.
    client.get("/api/home/today")
    with QueryCounter(app.state.engine) as small:
        assert client.get("/api/home/today").status_code == 200
    small_count = small.count

    _make_rooms(client, csrf, others[2:], 6)
    client.get("/api/home/today")
    with QueryCounter(app.state.engine) as big:
        body = client.get("/api/home/today").json()
    big_count = big.count

    assert isinstance(body["inbox"]["chat_unread"], int)

    grew = big_count - small_count
    assert grew <= 2, (
        f"방 2개일 때 {small_count}질의, 8개일 때 {big_count}질의 — 방 6개가 늘 때 "
        f"{grew}질의가 늘었다. 방 하나당 질의가 붙는 구조다(M2)."
    )


def test_home_today_chat_unread_still_answers_correctly(app, client, login_as, make_user):
    """질의를 줄이면서 **답이 달라지지 않았는지** 본다 — 상대가 보낸 메시지만큼 안읽음이 잡힌다."""
    from fastapi.testclient import TestClient

    from tests.conftest import DEFAULT_TEST_PASSWORD

    csrf = login_as("user", email="home-qcv-me@goodmit.co.kr")
    other = make_user(email="home-qcv-p@goodmit.co.kr", display_name="홈상대사람")
    rid = client.post(
        "/api/team-chat/rooms/direct", json={"user_id": other.id}, headers={"X-CSRF-Token": csrf}
    ).json()["room"]["id"]

    c2 = TestClient(app, raise_server_exceptions=False)
    c2.post("/login", json={"email": "home-qcv-p@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    csrf2 = c2.get("/api/me").json()["csrf_token"]
    with c2:
        c2.post(
            f"/api/team-chat/rooms/{rid}/messages",
            json={"body": "먼저 인사"},
            headers={"X-CSRF-Token": csrf2},
        )

    body = client.get("/api/home/today").json()
    assert body["inbox"]["chat_unread"] == 1
