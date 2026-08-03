"""폴링 엔드포인트의 ETag / 304 (PLAN Phase 4 — 스케일 심).

이런 검사는 **헛돌기 쉽다**. "304 가 나온다"만 보면 서버가 무조건 304 를 내도 통과하고,
"200 이 나온다"만 보면 ETag 가 아예 없어도 통과한다. 그래서 세 방향을 전부 본다:

  1. If-None-Match 없이 부르면 200 + ETag 헤더가 붙는다
  2. 같은 ETag 를 들고 다시 부르면 **304 이고 본문이 실제로 비어 있다**
     (JSONResponse(status_code=304) 로 만들면 상태만 304 이고 본문이 그대로 실려 나가
     대역폭을 하나도 아끼지 못한다 — 그 실수를 여기서 잡는다)
  3. 내용이 바뀌면 **ETag 도 바뀌고 다시 200 이 나온다**
     (ETag 가 고정 문자열이면 내용이 바뀌어도 영영 304 라 화면이 갱신되지 않는다)
"""

import pytest

pytestmark = pytest.mark.integration

# 이 세 곳에만 건다. `/api/notifications`(목록)은 페이지네이션·읽음/유형 필터가 있어 제외하고,
# 실제로 늘 도는 배지(`unread-count`)에 건다 — app/core/etag.py docstring 참조.
POLLING_ENDPOINTS = (
    "/api/notifications/unread-count",
    "/api/games/rooms",
    "/api/trash",
)


@pytest.fixture()
def authed(client, login_as):
    login_as("user")
    return client


@pytest.mark.parametrize("url", POLLING_ENDPOINTS)
def test_first_request_is_200_with_an_etag(authed, url):
    response = authed.get(url)
    assert response.status_code == 200, response.text
    etag = response.headers.get("ETag")
    assert etag, f"{url} 에 ETag 헤더가 없다"
    assert etag.startswith('"') and etag.endswith('"'), f"강한 ETag 형식이 아니다: {etag}"
    assert response.headers.get("Cache-Control") == "private, no-cache"


@pytest.mark.parametrize("url", POLLING_ENDPOINTS)
def test_same_etag_returns_304_with_an_empty_body(authed, url):
    etag = authed.get(url).headers["ETag"]

    second = authed.get(url, headers={"If-None-Match": etag})
    assert second.status_code == 304, second.text
    # **본문이 실제로 비어야 한다.** 이 한 줄이 이 파일의 존재 이유다.
    assert second.content == b"", f"304 인데 본문이 {len(second.content)} 바이트 실려 나갔다"
    assert second.headers.get("ETag") == etag


@pytest.mark.parametrize("url", POLLING_ENDPOINTS)
def test_weak_validator_from_a_proxy_is_still_accepted(authed, url):
    """중간 프록시가 `W/` 를 붙여 되돌려 보내도 304 여야 한다(받는 쪽은 관대하게)."""
    etag = authed.get(url).headers["ETag"]
    response = authed.get(url, headers={"If-None-Match": f"W/{etag}"})
    assert response.status_code == 304


@pytest.mark.parametrize("url", POLLING_ENDPOINTS)
def test_a_stale_etag_gets_a_fresh_200(authed, url):
    response = authed.get(url, headers={"If-None-Match": '"stale-value"'})
    assert response.status_code == 200
    assert response.headers["ETag"] != '"stale-value"'


def test_etag_changes_when_the_notification_count_changes(client, login_as, db):
    """ETag 가 내용 변화에 **반응하는지**. 고정 문자열이면 여기서 걸린다."""
    from app.notifications.service import notify_user
    from app.users.service import get_user_by_email

    login_as("user")
    url = "/api/notifications/unread-count"
    before = client.get(url)
    assert before.json() == {"unread": 0}
    etag_before = before.headers["ETag"]

    with client.app.state.session_factory() as session:
        user = get_user_by_email(session, "user@goodmit.co.kr")
        notify_user(
            session, user.id, type_="system", title="알림", body="본문",
            now=client.app.state.clock.now(),
        )
        session.commit()

    after = client.get(url, headers={"If-None-Match": etag_before})
    assert after.status_code == 200, "내용이 바뀌었는데 304 가 나왔다 — 화면이 영영 갱신되지 않는다"
    assert after.headers["ETag"] != etag_before
    assert after.json() == {"unread": 1}


def test_etag_changes_when_a_game_room_appears(client, login_as):
    login_as("user")
    url = "/api/games/rooms"
    first = client.get(url)
    etag_before = first.headers["ETag"]
    assert first.json()["items"] == []

    csrf = client.post("/login", json={
        "email": "user@goodmit.co.kr", "password": "Str0ng-Passw0rd!"
    }).json()["csrf_token"]
    created = client.post(
        url, json={"title": "테스트 방", "game_type": "ladder"},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text

    after = client.get(url, headers={"If-None-Match": etag_before})
    assert after.status_code == 200
    assert after.headers["ETag"] != etag_before
    assert len(after.json()["items"]) == 1


def test_two_users_do_not_share_a_notification_etag(client, login_as, make_user):
    """개인별 응답에 공용 ETag 가 붙으면 남의 숫자를 보게 된다.

    ETag 는 본문에서 계산하므로 값이 같으면 ETag 도 같다 — 그것 자체는 정상이다
    (본문이 같으니 304 를 줘도 옳다). 여기서 확인하는 것은 **값이 다르면 반드시
    다른 ETag** 라는 것, 즉 사용자 A 의 ETag 로 사용자 B 가 304 를 받아 A 의 숫자를
    쓰는 일이 없다는 것이다.
    """
    from app.notifications.service import notify_user
    from app.users.service import get_user_by_email

    make_user(email="other@goodmit.co.kr", role="user")
    login_as("user")
    with client.app.state.session_factory() as session:
        me = get_user_by_email(session, "user@goodmit.co.kr")
        notify_user(
            session, me.id, type_="system", title="내 알림", body="",
            now=client.app.state.clock.now(),
        )
        session.commit()

    mine = client.get("/api/notifications/unread-count")
    assert mine.json() == {"unread": 1}
    my_etag = mine.headers["ETag"]

    client.post("/login", json={
        "email": "other@goodmit.co.kr", "password": "Str0ng-Passw0rd!"
    })
    theirs = client.get("/api/notifications/unread-count", headers={"If-None-Match": my_etag})
    assert theirs.status_code == 200, "남의 ETag 로 304 를 받았다 — 남의 숫자를 보게 된다"
    assert theirs.json() == {"unread": 0}
