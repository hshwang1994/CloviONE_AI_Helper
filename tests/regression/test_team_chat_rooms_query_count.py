"""채팅방 목록이 방 개수에 비례해 질의를 늘리지 않는다 (H4).

## 왜 이 파일이 있는가

`GET /api/team-chat/rooms` 는 **모든 화면에서** 주기적으로 돈다(사이드바 안 읽음 배지).
그런데 이 응답을 만들 때 방 하나마다 참여자와 마지막 메시지를 따로 물었다 — 방이 늘면
질의가 그만큼 늘고, SQLite 는 writer 가 하나라 사람이 늘수록 이 경로가 먼저 막힌다.
증상은 "요즘 좀 느리다" 라서 원인이 안 보인다.

## 어떻게 판정하는가

방 개수를 **바꿔 가며** 실행한 SELECT 개수를 세고, 그 차이를 본다. 절대 개수를 못 박지
않는 이유: 이 경로에는 세션·인증·기능 플래그 같은 곁가지 질의가 붙었다 떨어졌다 하고,
그때마다 이 검사가 틀린 이유로 빨개지면 사람이 곧 무시한다. **우리가 지키려는 성질은
'방이 늘어도 질의가 늘지 않는다' 하나**이므로 그것만 본다.

값이 실제로 달라지는 표본을 쓴다 — 방 2개와 방 8개.

측정값(2026-08-07, 이 저장소에서 직접 셈):
  고치기 전  방 2개 15질의 · 방 8개 33질의   (방 하나당 +3)
  고친 뒤    방 2개 10질의 · 방 8개 10질의   (방 개수와 무관)
"""

from __future__ import annotations

import pytest
from sqlalchemy import event

from tests.conftest import DEFAULT_TEST_PASSWORD

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
    """1:1 방을 count 개 만든다 — 방마다 참여자 2명, 마지막 메시지 1개."""
    for i in range(count):
        rid = client.post(
            "/api/team-chat/rooms/direct",
            json={"user_id": others[i].id},
            headers={"X-CSRF-Token": csrf},
        ).json()["room"]["id"]
        client.post(
            f"/api/team-chat/rooms/{rid}/messages",
            json={"body": f"안녕 {i}"},
            headers={"X-CSRF-Token": csrf},
        )


def test_room_list_query_count_does_not_grow_with_rooms(app, client, login_as, make_user):
    csrf = login_as("user", email="qc-me@goodmit.co.kr")
    others = [make_user(email=f"qc-p{i}@goodmit.co.kr", display_name=f"상대{i}") for i in range(8)]

    _make_rooms(client, csrf, others, 2)
    # 첫 호출은 팀 방 보장 같은 1회성 쓰기를 유발할 수 있다 — 기준선 앞에서 한 번 흘린다.
    client.get("/api/team-chat/rooms")
    with QueryCounter(app.state.engine) as small:
        assert client.get("/api/team-chat/rooms").status_code == 200
    small_count = small.count

    _make_rooms(client, csrf, others[2:], 6)
    client.get("/api/team-chat/rooms")
    with QueryCounter(app.state.engine) as big:
        body = client.get("/api/team-chat/rooms").json()
    big_count = big.count

    # 표본이 실제로 다른지 먼저 확인한다 — 방이 안 늘었으면 아래 비교는 아무 뜻이 없다.
    assert len(body["items"]) == 8, body["items"]

    grew = big_count - small_count
    assert grew <= 2, (
        f"방 2개일 때 {small_count}질의, 8개일 때 {big_count}질의 — 방 6개가 늘 때 "
        f"{grew}질의가 늘었다. 방 하나당 질의가 붙는 구조다(H4)."
    )


def test_room_list_still_answers_correctly(app, client, login_as, make_user):
    """질의를 줄이면서 **답이 달라지지 않았는지** 본다.

    성능 수정에서 가장 흔한 사고는 '빨라졌는데 값이 틀린' 것이다. 제목(1:1 은 상대 이름),
    참여자 수, 마지막 메시지 미리보기, 안 읽음 합계 — 목록이 실제로 쓰는 값을 다 본다.
    """
    csrf = login_as("user", email="qcv-me@goodmit.co.kr")
    other = make_user(email="qcv-p@goodmit.co.kr", display_name="상대사람")
    rid = client.post(
        "/api/team-chat/rooms/direct", json={"user_id": other.id}, headers={"X-CSRF-Token": csrf}
    ).json()["room"]["id"]

    # 상대가 말을 건다 — 그래야 내 안 읽음이 0이 아니다.
    from fastapi.testclient import TestClient

    c2 = TestClient(app, raise_server_exceptions=False)
    c2.post("/login", json={"email": "qcv-p@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    csrf2 = c2.get("/api/me").json()["csrf_token"]
    with c2:
        c2.post(
            f"/api/team-chat/rooms/{rid}/messages",
            json={"body": "먼저 인사"},
            headers={"X-CSRF-Token": csrf2},
        )

    body = client.get("/api/team-chat/rooms").json()
    row = next(x for x in body["items"] if x["id"] == rid)
    assert row["title"] == "상대사람"
    assert row["member_count"] == 2
    assert row["last_preview"] == "먼저 인사"
    assert row["unread"] == 1
    assert body["unread_total"] >= 1
