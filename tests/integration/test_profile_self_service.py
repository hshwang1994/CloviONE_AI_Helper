"""프로필 셀프서비스 — 아바타·알림 설정·방해금지·투어·저장된 뷰 (계획서 Phase 6 사용자).

## 이 파일이 지키는 가장 중요한 계약

**방해금지는 알림을 삼키지 않는다.** DND 중에 온 알림이 사라지면 사용자는 일을 놓치고,
한 번 놓친 사람은 두 번 다시 이 기능을 켜지 않는다. 그래서 아래 테스트는 DND 중에도
  1) 알림 행이 그대로 만들어지고,
  2) 목록에 그대로 나오고,
  3) `unread` 총계도 그대로이며,
  4) **`badge` 만 0** 이 되고,
  5) DND 를 풀면 그동안 쌓인 것이 배지에 한꺼번에 돌아오는지
를 전부 확인한다.

**투어는 건너뛴 사람에게 다시 뜨지 않는다.** 서버가 판정하므로 다른 브라우저·시크릿 창·
재로그인 어느 쪽으로 들어와도 같다 — 그것까지 확인한다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration

EMAIL = "selfservice@goodmit.co.kr"

# 최소 PNG (매직바이트 검사 통과용). 확장자·Content-Type 이 아니라 이 앞 8바이트가 형식을 정한다.
PNG_BYTES = (
    b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x06"
    b"\x00\x00\x00\x1f\x15\xc4\x89\x00\x00\x00\nIDATx\x9cc\x00\x01\x00\x00\x05"
    b"\x00\x01\r\n-\xb4\x00\x00\x00\x00IEND\xaeB`\x82"
)


@pytest.fixture()
def me(client, login_as):
    csrf = login_as("user", email=EMAIL)
    user = client.get("/api/me").json()["user"]
    return csrf, user


def _notify(db, user_id, clock, *, type_="job_failed", title="알림"):
    from app.notifications.service import notify_user

    notify_user(db, user_id, type_=type_, title=title, now=clock.now())
    db.commit()


# ── 설정 기본값 ───────────────────────────────────────────────────────────────

def test_preferences_have_a_complete_shape_before_anything_is_saved(client, me):
    """행이 없어도 화면이 그릴 모양은 온전해야 한다. 그리고 행을 만들지 않는다."""
    body = client.get("/api/me/preferences").json()
    assert body["dnd"]["enabled"] is False and body["dnd"]["quiet_now"] is False
    assert body["notifications"]["muted_types"] == []
    assert body["notifications"]["catalog"], "설정 화면이 그릴 유형 목록이 서버에서 온다"
    assert body["tour"]["show"] is True
    assert body["avatar"]["url"] is None

    from app.profiles.models import UserPreference

    with client.app.state.session_factory() as session:
        assert session.query(UserPreference).count() == 0, "조회가 행을 만들면 안 된다"


# ── 방해금지: 미루기이지 삼키기가 아니다 ─────────────────────────────────────

def test_dnd_silences_the_badge_but_keeps_every_notification(client, db, fake_clock, me):
    csrf, user = me

    on = client.patch(
        "/api/me/preferences", json={"dnd_enabled": True}, headers={"X-CSRF-Token": csrf}
    )
    assert on.status_code == 200, on.text
    assert on.json()["dnd"]["quiet_now"] is True

    _notify(db, user["id"], fake_clock, title="DND 중에 온 알림")

    count = client.get("/api/notifications/unread-count").json()
    assert count["unread"] == 1, "알림은 그대로 쌓인다 — 삼키지 않는다"
    assert count["badge"] == 0, "배지만 조용해진다"
    assert count["quiet"] is True and count["quiet_reason"] == "manual"

    listing = client.get("/api/notifications").json()
    assert listing["total"] == 1
    assert listing["items"][0]["title"] == "DND 중에 온 알림"

    off = client.patch(
        "/api/me/preferences", json={"dnd_enabled": False}, headers={"X-CSRF-Token": csrf}
    )
    assert off.json()["dnd"]["quiet_now"] is False
    restored = client.get("/api/notifications/unread-count").json()
    assert restored["badge"] == 1, "DND 가 끝나면 그동안 쌓인 것이 배지로 돌아온다"


def test_timed_dnd_expires_on_its_own_and_the_state_is_cleaned_up(client, fake_clock, me):
    csrf, _user = me
    client.patch(
        "/api/me/preferences",
        json={"dnd_enabled": True, "dnd_minutes": 5},
        headers={"X-CSRF-Token": csrf},
    )
    assert client.get("/api/me/preferences").json()["dnd"]["quiet_now"] is True

    # 세션 유휴 만료(30분)보다 짧게 넘긴다 — 더 넘기면 401 이 나서 무엇을 확인하는
    # 테스트인지 알 수 없게 된다.
    fake_clock.advance(6 * 60)
    body = client.get("/api/me/preferences").json()
    assert body["dnd"]["quiet_now"] is False
    # 판정만 하고 두면 화면이 '켜짐(하지만 조용하지 않음)'을 계속 그린다.
    assert body["dnd"]["enabled"] is False
    assert body["dnd"]["until"] is None


def test_dnd_cannot_be_set_beyond_the_cap(client, me):
    csrf, _user = me
    response = client.patch(
        "/api/me/preferences",
        json={"dnd_enabled": True, "dnd_minutes": 60 * 48},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_muted_type_leaves_the_badge_alone_but_stays_in_the_list(client, db, fake_clock, me):
    csrf, user = me
    client.patch(
        "/api/me/preferences",
        json={"muted_types": ["job_failed"]},
        headers={"X-CSRF-Token": csrf},
    )
    _notify(db, user["id"], fake_clock, type_="job_failed", title="뮤트한 유형")
    _notify(db, user["id"], fake_clock, type_="chat_mentioned", title="안 뮤트한 유형")

    count = client.get("/api/notifications/unread-count").json()
    assert count["unread"] == 2, "뮤트해도 안 읽음 총계는 그대로다"
    assert count["badge"] == 1, "배지에서만 빠진다"

    items = {it["title"]: it for it in client.get("/api/notifications").json()["items"]}
    assert items["뮤트한 유형"]["muted"] is True
    assert items["안 뮤트한 유형"]["muted"] is False


def test_unknown_notification_type_is_rejected_not_silently_dropped(client, me):
    csrf, _user = me
    response = client.patch(
        "/api/me/preferences",
        json={"muted_types": ["job_failed", "made_up_type"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422
    assert "made_up_type" in response.json()["error"]["message"]


def test_security_notification_cannot_be_muted(client, me):
    """계정 잠금 알림을 끌 수 있으면 침해를 알리는 유일한 신호를 본인이 끄게 된다."""
    csrf, _user = me
    response = client.patch(
        "/api/me/preferences",
        json={"muted_types": ["account_locked"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_quiet_hours_reject_a_zero_length_window(client, me):
    csrf, _user = me
    response = client.patch(
        "/api/me/preferences",
        json={"quiet_hours_enabled": True, "quiet_start": "09:00", "quiet_end": "09:00"},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_preference_update_requires_csrf(client, me):
    response = client.patch("/api/me/preferences", json={"dnd_enabled": True})
    assert response.status_code == 403


# ── 첫 로그인 투어 ───────────────────────────────────────────────────────────

def test_skipped_tour_never_comes_back_even_in_a_new_browser(app, client, me):
    csrf, _user = me
    assert client.get("/api/me/preferences").json()["tour"]["show"] is True

    response = client.post(
        "/api/me/tour", json={"action": "skip"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 200
    assert response.json()["tour"]["show"] is False
    assert response.json()["tour"]["skipped"] is True

    # 다른 브라우저(=새 세션)로 다시 들어와도 안 뜬다 — 브라우저 저장소가 아니라 서버가
    # 판정하기 때문이다.
    fresh = TestClient(app, raise_server_exceptions=False)
    assert fresh.post(
        "/login", json={"email": EMAIL, "password": DEFAULT_TEST_PASSWORD}
    ).status_code == 200
    assert fresh.get("/api/me/preferences").json()["tour"]["show"] is False


def test_completing_the_tour_also_stops_it(client, me):
    csrf, _user = me
    body = client.post(
        "/api/me/tour", json={"action": "complete"}, headers={"X-CSRF-Token": csrf}
    ).json()
    assert body["tour"]["show"] is False and body["tour"]["skipped"] is False


def test_user_can_ask_to_see_the_tour_again(client, me):
    csrf, _user = me
    client.post("/api/me/tour", json={"action": "skip"}, headers={"X-CSRF-Token": csrf})
    body = client.post(
        "/api/me/tour", json={"action": "reset"}, headers={"X-CSRF-Token": csrf}
    ).json()
    assert body["tour"]["show"] is True


def test_unknown_tour_action_is_refused(client, me):
    csrf, _user = me
    response = client.post(
        "/api/me/tour", json={"action": "nope"}, headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 422


# ── 아바타 ───────────────────────────────────────────────────────────────────

def test_avatar_upload_serve_and_delete(client, me):
    csrf, user = me
    response = client.post(
        "/api/me/avatar",
        files={"file": ("me.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 200, response.text
    url = response.json()["avatar_url"]
    assert url and url.startswith(f"/api/profile/avatar/{user['id']}")

    # /api/me 가 셸을 위해 같은 URL 을 실어 준다(별도 요청 없이 상단바가 그린다).
    assert client.get("/api/me").json()["user"]["avatar_url"] == url

    served = client.get(url)
    assert served.status_code == 200
    assert served.headers["content-type"].startswith("image/png")
    assert served.headers["X-Content-Type-Options"] == "nosniff"
    assert served.content == PNG_BYTES

    removed = client.delete("/api/me/avatar", headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 200 and removed.json()["avatar_url"] is None
    assert client.get(url).status_code == 404
    # 두 번 지워도 성공이다(멱등).
    assert client.delete("/api/me/avatar", headers={"X-CSRF-Token": csrf}).status_code == 200


def test_avatar_rejects_a_non_image_regardless_of_filename(client, me):
    csrf, _user = me
    response = client.post(
        "/api/me/avatar",
        files={"file": ("evil.png", b"<?php echo 1; ?>", "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_avatar_rejects_pdf_even_though_uploads_allows_it_elsewhere(client, me):
    csrf, _user = me
    response = client.post(
        "/api/me/avatar",
        files={"file": ("doc.pdf", b"%PDF-1.4 x", "application/pdf")},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


def test_avatar_upload_requires_csrf(client, me):
    response = client.post(
        "/api/me/avatar", files={"file": ("me.png", PNG_BYTES, "image/png")}
    )
    assert response.status_code == 403


def test_avatar_of_an_unknown_user_is_404_not_403(client, me):
    """403 이면 '그런 계정이 있다'가 새어 나간다."""
    assert client.get("/api/profile/avatar/does-not-exist").status_code == 404


def test_avatar_requires_login(app, client, me):
    csrf, user = me
    client.post(
        "/api/me/avatar",
        files={"file": ("me.png", PNG_BYTES, "image/png")},
        headers={"X-CSRF-Token": csrf},
    )
    anonymous = TestClient(app, raise_server_exceptions=False)
    assert anonymous.get(f"/api/profile/avatar/{user['id']}").status_code == 401


# ── 저장된 뷰 ────────────────────────────────────────────────────────────────

def test_saved_view_roundtrip_keeps_the_url_query_verbatim(client, me):
    csrf, _user = me
    query = "q=%EC%8B%A4%ED%8C%A8&status=failed&page=2"
    created = client.post(
        "/api/me/views",
        json={"screen_key": "jobs", "name": "실패한 작업", "query": "?" + query},
        headers={"X-CSRF-Token": csrf},
    )
    assert created.status_code == 200, created.text
    view = created.json()["view"]
    # 앞의 '?' 만 떼고 나머지는 한 글자도 해석하지 않는다 — 화면의 필터 정의가 바뀌어도
    # 저장된 뷰를 마이그레이션할 필요가 없다.
    assert view["query"] == query

    listed = client.get("/api/me/views?screen_key=jobs").json()["items"]
    assert [v["name"] for v in listed] == ["실패한 작업"]
    assert client.get("/api/me/views?screen_key=audit").json()["items"] == []

    removed = client.delete(f"/api/me/views/{view['id']}", headers={"X-CSRF-Token": csrf})
    assert removed.status_code == 200
    assert client.get("/api/me/views").json()["items"] == []


def test_duplicate_view_name_is_a_conflict_until_overwrite_is_asked_for(client, me):
    csrf, _user = me
    body = {"screen_key": "audit", "name": "내 뷰", "query": "action=user.login"}
    assert client.post("/api/me/views", json=body, headers={"X-CSRF-Token": csrf}).status_code == 200

    clash = client.post(
        "/api/me/views",
        json={**body, "query": "action=user.logout"},
        headers={"X-CSRF-Token": csrf},
    )
    assert clash.status_code == 409

    overwritten = client.post(
        "/api/me/views",
        json={**body, "query": "action=user.logout", "overwrite": True},
        headers={"X-CSRF-Token": csrf},
    )
    assert overwritten.status_code == 200
    assert overwritten.json()["view"]["query"] == "action=user.logout"
    assert len(client.get("/api/me/views").json()["items"]) == 1


def test_saved_views_are_private_to_their_owner(app, client, make_user, me):
    csrf, _user = me
    client.post(
        "/api/me/views",
        json={"screen_key": "audit", "name": "비밀 뷰", "query": "user_id=x"},
        headers={"X-CSRF-Token": csrf},
    )
    make_user("other@goodmit.co.kr")
    other = TestClient(app, raise_server_exceptions=False)
    other.post("/login", json={"email": "other@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD})
    assert other.get("/api/me/views").json()["items"] == []

    view_id = client.get("/api/me/views").json()["items"][0]["id"]
    csrf_other = other.get("/api/me").json()["csrf_token"]
    assert other.delete(
        f"/api/me/views/{view_id}", headers={"X-CSRF-Token": csrf_other}
    ).status_code == 404
    assert len(client.get("/api/me/views").json()["items"]) == 1


def test_saved_view_needs_a_name(client, me):
    csrf, _user = me
    response = client.post(
        "/api/me/views",
        json={"screen_key": "audit", "name": "   ", "query": ""},
        headers={"X-CSRF-Token": csrf},
    )
    assert response.status_code == 422


# ── 내 활동 피드 ─────────────────────────────────────────────────────────────

def test_activity_feed_merges_what_i_did_and_what_happened_to_me(client, db, fake_clock, me):
    csrf, user = me
    # '나에게 일어난 일'
    _notify(db, user["id"], fake_clock, type_="chat_mentioned", title="누가 나를 불렀다")
    # '내가 한 일' — 실제 쓰기 경로가 감사 로그를 남긴다(로그인도 이미 남아 있다).
    client.patch(
        "/api/me/preferences", json={"dnd_enabled": True}, headers={"X-CSRF-Token": csrf}
    )

    body = client.get("/api/me/activity").json()
    kinds = {it["kind"] for it in body["items"]}
    assert kinds == {"did", "happened"}
    titles = [it["title"] for it in body["items"]]
    assert "누가 나를 불렀다" in titles
    assert "알림·방해금지 설정을 바꿨습니다" in titles
    # 시간 역순.
    assert titles == [it["title"] for it in sorted(body["items"], key=lambda i: i["at"], reverse=True)]


def test_activity_feed_can_be_narrowed_to_one_side(client, db, fake_clock, me):
    _csrf, user = me
    _notify(db, user["id"], fake_clock, title="나에게 온 것")

    only_mine = client.get("/api/me/activity?kind=did").json()
    assert only_mine["items"] and all(it["kind"] == "did" for it in only_mine["items"])
    only_theirs = client.get("/api/me/activity?kind=happened").json()
    assert [it["title"] for it in only_theirs["items"]] == ["나에게 온 것"]


def test_activity_feed_only_shows_my_own_rows(app, client, make_user, db, fake_clock, me):
    _csrf, _user = me
    other_user = make_user("stranger@goodmit.co.kr")
    _notify(db, other_user.id, fake_clock, title="남의 알림")

    titles = [it["title"] for it in client.get("/api/me/activity").json()["items"]]
    assert "남의 알림" not in titles


def test_activity_feed_rejects_an_unknown_kind(client, me):
    assert client.get("/api/me/activity?kind=nope").status_code == 422
