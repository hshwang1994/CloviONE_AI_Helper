"""사이드바 신규 알림 배지와 '확인하면 자동 제거' (S2).

사용자 지적: "페이지 내에서 신규로 확인해야 할 사항이 발생하면 왼쪽 사이드에 표시해 줬으면
좋겠다. 신규 알람을. 확인하면 자동으로 없애는 형태로."

앞절반: 합계(`unread`)만으로는 **어느 메뉴에 생긴 일인지** 알 수 없어 왼쪽에 표시할 수가
없었다. 종류별 개수를 실어 준다.

뒷절반: 화면을 열었다는 것이 곧 확인했다는 뜻이므로 그 유형을 읽음 처리한다.
**폴링이 아니라 화면 진입 이벤트**로만 부른다 — 폴링으로 지우면 열지도 않은 알림이 사라진다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.integration


def _notify(app, user_id, kind, title="알림"):
    from app.notifications.models import Notification

    with app.state.session_factory() as db:
        db.add(Notification(user_id=user_id, type=kind, title=title, body=""))
        db.commit()


def _me_id(client):
    # `/api/me` 는 사용자를 `user` 아래에 감싼다(app/profiles/router.py).
    return client.get("/api/me").json()["user"]["id"]


def test_summary_reports_counts_per_type(client, login_as, app):
    login_as("user")
    uid = _me_id(client)
    _notify(app, uid, "job_failed")
    _notify(app, uid, "job_failed")
    _notify(app, uid, "approval_overdue")

    body = client.get("/api/notifications/unread-count").json()
    assert body["by_type"]["job_failed"] == 2
    assert body["by_type"]["approval_overdue"] == 1
    # 합계는 예전 그대로여야 한다 — 기존 화면(벨)이 이 값을 쓴다.
    assert body["unread"] >= 3


def test_reading_a_type_clears_only_that_type(client, login_as, app):
    csrf = login_as("user")
    uid = _me_id(client)
    _notify(app, uid, "job_failed")
    _notify(app, uid, "approval_overdue")

    r = client.post(
        "/api/notifications/read-types",
        json={"types": ["job_failed"]},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200, r.text
    assert r.json()["read"] == 1

    body = client.get("/api/notifications/unread-count").json()
    assert "job_failed" not in body["by_type"], "읽음 처리한 유형이 남아 있다"
    assert body["by_type"]["approval_overdue"] == 1, "다른 유형까지 지웠다"


def test_empty_type_list_clears_nothing(client, login_as, app):
    """빈 목록을 '전부'로 해석하면 화면 하나를 여는 것이 모든 알림을 지우는 사고가 된다."""
    csrf = login_as("user")
    uid = _me_id(client)
    _notify(app, uid, "job_failed")

    r = client.post(
        "/api/notifications/read-types", json={"types": []},
        headers={"X-CSRF-Token": csrf},
    )
    assert r.status_code == 200
    assert r.json()["read"] == 0
    assert client.get("/api/notifications/unread-count").json()["by_type"]["job_failed"] == 1


def test_read_types_needs_csrf(client, login_as, app):
    login_as("user")
    r = client.post("/api/notifications/read-types", json={"types": ["job_failed"]})
    assert r.status_code == 403


def test_you_cannot_clear_someone_elses_notifications(client, login_as, make_user, app):
    """유형만 받으므로 남의 알림에 닿을 수 없어야 한다 — 소유권은 서버가 건다."""
    from app.users.models import User

    other = make_user("other-badge@goodmit.co.kr")
    _notify(app, other.id, "job_failed")

    csrf = login_as("user")
    client.post(
        "/api/notifications/read-types", json={"types": ["job_failed"]},
        headers={"X-CSRF-Token": csrf},
    )

    with app.state.session_factory() as db:
        from app.notifications.models import Notification

        left = (
            db.query(Notification)
            .filter(Notification.user_id == other.id, Notification.read_at.is_(None))
            .count()
        )
        assert left == 1, "남의 알림이 읽음 처리됐다"
        assert db.query(User).filter(User.id == other.id).count() == 1


def test_me_reports_menu_feature_flags(client, login_as):
    """화면이 꺼진 메뉴를 감추려면 `/api/me` 가 플래그를 줘야 한다 (X4).

    예전에는 플래그가 서버만 껐다 — 껐다고 믿은 메뉴가 사이드바에 남고, 눌리고, 404 를 뱉었다.
    """
    login_as("user")
    features = client.get("/api/me").json().get("features")

    assert features is not None, "/api/me 가 기능 플래그를 안 준다"
    assert set(features) == {
        "board_enabled", "team_docs_enabled", "games_enabled", "team_chat_enabled",
    }, f"메뉴와 대응하지 않는 키가 섞였다: {sorted(features)}"
    assert all(isinstance(v, bool) for v in features.values())
