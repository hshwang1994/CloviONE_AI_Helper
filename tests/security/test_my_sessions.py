"""'내 다른 세션 로그아웃'은 **보안 기능**이다 — 실제로 못 쓰게 되는지 다시 불러서 본다.

이 파일이 고정하는 것:
  * 끊긴 세션으로 API 를 부르면 **401** 이다. "revoked_at 이 채워졌다"를 확인하는 것으로는
    부족하다 — 세션 검증 경로가 그 컬럼을 실제로 보는지까지 통과해야 사용자가 안전해진다.
  * 누른 사람의 세션은 **살아 있다**. 전부 끊기면 '공용 PC 에 로그인해 두고 왔다' 상황에서
    아무도 이 버튼을 못 누른다(자기가 먼저 튕겨나가니까).
  * 남의 세션 id 로는 아무것도 못 끊는다(404 — 403 이면 그런 세션이 있다는 사실이 샌다).
  * 감사 로그에 남는다. 계정 침해 대응의 흔적이 없으면 나중에 무엇이 있었는지 알 수 없다.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import select

from app.audit.models import AuditLog
from app.auth.models import UserSession
from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.security

EMAIL = "sessions@goodmit.co.kr"


def _login(test_client, email=EMAIL):
    response = test_client.post(
        "/login", json={"email": email, "password": DEFAULT_TEST_PASSWORD}
    )
    assert response.status_code == 200, response.text
    return response.json()["csrf_token"]


@pytest.fixture()
def two_sessions(app, client, make_user):
    """같은 계정으로 두 개의 독립 세션(브라우저 두 개에 해당)을 만든다."""
    make_user(EMAIL)
    csrf_a = _login(client)
    other = TestClient(app, raise_server_exceptions=False)
    csrf_b = _login(other)
    # 둘 다 살아 있는지부터 확인한다 — 여기서 이미 하나가 죽어 있으면 아래 검증이 헛돈다.
    assert client.get("/api/me").status_code == 200
    assert other.get("/api/me").status_code == 200
    return client, csrf_a, other, csrf_b


def test_revoked_session_actually_gets_401_on_the_next_call(two_sessions):
    session_a, csrf_a, session_b, _csrf_b = two_sessions

    response = session_a.post(
        "/api/me/sessions/revoke-others", headers={"X-CSRF-Token": csrf_a}
    )
    assert response.status_code == 200, response.text
    assert response.json()["revoked_count"] == 1

    # 끊은 쪽은 계속 쓸 수 있어야 한다.
    assert session_a.get("/api/me").status_code == 200
    # 끊긴 쪽은 **다시 불러 보면** 401 이다. 이게 이 기능의 전부다.
    assert session_b.get("/api/me").status_code == 401
    # 쓰기도 막힌다(읽기만 막고 쓰기가 통하면 아무 의미가 없다).
    assert session_b.post("/logout", headers={"X-CSRF-Token": _csrf_b}).status_code == 401


def test_revoke_others_is_audited(two_sessions, db):
    session_a, csrf_a, _b, _csrf_b = two_sessions
    session_a.post("/api/me/sessions/revoke-others", headers={"X-CSRF-Token": csrf_a})

    rows = db.execute(
        select(AuditLog).where(AuditLog.action == "profile.sessions.revoke_others")
    ).scalars().all()
    assert len(rows) == 1
    assert rows[0].object_type == "session"


def test_session_list_marks_the_current_one(two_sessions):
    session_a, _csrf_a, _b, _csrf_b = two_sessions
    items = session_a.get("/api/me/sessions").json()["items"]
    assert len(items) == 2
    assert sum(1 for it in items if it["current"]) == 1
    # 토큰(해시)은 절대 나가지 않는다.
    assert all("token" not in key for item in items for key in item)


def test_revoking_a_single_other_session_works_and_current_is_refused(two_sessions):
    session_a, csrf_a, session_b, _csrf_b = two_sessions
    items = session_a.get("/api/me/sessions").json()["items"]
    other_id = next(it["id"] for it in items if not it["current"])
    current_id = next(it["id"] for it in items if it["current"])

    # 현재 세션은 이 경로로 끊을 수 없다(로그아웃이 그 일을 한다).
    refused = session_a.delete(
        f"/api/me/sessions/{current_id}", headers={"X-CSRF-Token": csrf_a}
    )
    assert refused.status_code == 422

    ok = session_a.delete(
        f"/api/me/sessions/{other_id}", headers={"X-CSRF-Token": csrf_a}
    )
    assert ok.status_code == 200
    assert session_b.get("/api/me").status_code == 401
    assert session_a.get("/api/me").status_code == 200


def test_cannot_revoke_someone_elses_session(app, client, make_user, db):
    """남의 세션 id 를 알아내도 끊을 수 없다. 존재 여부도 알려 주지 않는다(404)."""
    make_user(EMAIL)
    victim_user = make_user("victim@goodmit.co.kr")
    victim = TestClient(app, raise_server_exceptions=False)
    _login(victim, "victim@goodmit.co.kr")
    victim_session_id = db.execute(
        select(UserSession.id).where(
            UserSession.user_id == victim_user.id, UserSession.revoked_at.is_(None)
        )
    ).scalars().first()
    assert victim_session_id

    csrf = _login(client)
    response = client.delete(
        f"/api/me/sessions/{victim_session_id}", headers={"X-CSRF-Token": csrf}
    )
    assert response.status_code == 404
    # 피해자는 멀쩡하다.
    assert victim.get("/api/me").status_code == 200


def test_revoke_others_requires_csrf(two_sessions):
    session_a, _csrf_a, session_b, _csrf_b = two_sessions
    response = session_a.post("/api/me/sessions/revoke-others")
    assert response.status_code == 403
    # 아무것도 안 끊겼다.
    assert session_b.get("/api/me").status_code == 200
