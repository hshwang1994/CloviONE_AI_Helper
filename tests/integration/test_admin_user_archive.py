"""사용자 '보관'(archive) — 삭제 대신 감추되 되돌릴 수 있어야 한다.

계정을 정말 지우면 감사 로그의 '누가 했는지'가 빈칸이 된다(§25.7의 행위자 추적이
끊긴다). 그래서 행은 DB에 남기고 목록·검색·로그인에서만 뺀다.
"""

import pytest

from tests.conftest import DEFAULT_TEST_PASSWORD

pytestmark = pytest.mark.integration


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def admin_csrf(login_as):
    return login_as("admin")


def test_archive_hides_user_from_default_list(client, admin_csrf, make_user):
    target = make_user("archive-me@goodmit.co.kr")

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "archive-me@goodmit.co.kr" in [u["email"] for u in r.json()["items"]]

    r = client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "archive-me@goodmit.co.kr" not in [u["email"] for u in r.json()["items"]]


def test_archived_user_hidden_from_search_too(client, admin_csrf, make_user):
    """검색은 목록의 '다른 문'이다 — 여기로 새면 감춘 것이 아니다."""
    target = make_user("findme@goodmit.co.kr", display_name="찾아줘")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.get("/api/admin/users", params={"q": "findme"}, headers=_headers(admin_csrf))
    assert r.json()["total"] == 0
    assert r.json()["items"] == []


def test_archived_visible_only_with_archived_true(client, admin_csrf, make_user):
    """복구하려면 보관된 계정을 볼 수 있어야 한다."""
    target = make_user("only-archived@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.get("/api/admin/users", params={"archived": "true"}, headers=_headers(admin_csrf))
    emails = [u["email"] for u in r.json()["items"]]
    assert emails == ["only-archived@goodmit.co.kr"], "보관 목록에는 보관된 계정만 나와야 한다"
    assert r.json()["items"][0]["archived_at"] is not None


def test_unarchive_restores_to_default_list(client, admin_csrf, make_user):
    target = make_user("comeback@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))
    assert r.status_code == 200, r.text

    r = client.get("/api/admin/users", headers=_headers(admin_csrf))
    assert "comeback@goodmit.co.kr" in [u["email"] for u in r.json()["items"]]
    r = client.get(f"/api/admin/users/{target.id}", headers=_headers(admin_csrf))
    assert r.json()["archived_at"] is None


def test_archived_user_cannot_log_in(client, admin_csrf, make_user, app):
    """보관은 '되돌릴 수 있는 퇴사 처리'다 — 그 계정으로 들어올 수는 없어야 한다."""
    from fastapi.testclient import TestClient

    target = make_user("gone@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    with TestClient(app, raise_server_exceptions=False) as fresh:
        r = fresh.post(
            "/login", json={"email": "gone@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert r.status_code == 403, r.text
        assert r.json()["error"]["code"] == "account_archived"


def test_archive_revokes_existing_sessions(client, admin_csrf, make_user, app):
    """이미 들어와 있는 세션이 살아 있으면 보관은 로그인만 막은 시늉이다."""
    from fastapi.testclient import TestClient

    target = make_user("kickme@goodmit.co.kr")
    with TestClient(app, raise_server_exceptions=False) as victim:
        victim.post(
            "/login", json={"email": "kickme@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert victim.get("/api/me").status_code == 200

        client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
        assert victim.get("/api/me").status_code == 401


def test_unarchived_user_can_log_in_again(client, admin_csrf, make_user, app):
    from fastapi.testclient import TestClient

    target = make_user("returning@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))

    with TestClient(app, raise_server_exceptions=False) as fresh:
        r = fresh.post(
            "/login", json={"email": "returning@goodmit.co.kr", "password": DEFAULT_TEST_PASSWORD}
        )
        assert r.status_code == 200, r.text


def test_archive_writes_audit_row(client, admin_csrf, make_user, db):
    from app.audit.models import AuditLog

    target = make_user("audited@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    rows = db.query(AuditLog).filter(AuditLog.action == "user.archive").all()
    assert len(rows) == 1
    assert rows[0].object_id == target.id
    assert rows[0].user_id is not None, "누가 보관했는지가 남아야 한다"


def test_unarchive_writes_audit_row(client, admin_csrf, make_user, db):
    from app.audit.models import AuditLog

    target = make_user("audited2@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))
    client.post(f"/api/admin/users/{target.id}/unarchive", headers=_headers(admin_csrf))

    assert db.query(AuditLog).filter(AuditLog.action == "user.unarchive").count() == 1


def test_creating_user_with_archived_email_explains_and_offers_restore(
    client, admin_csrf, make_user
):
    """이메일은 유일 제약이다. 보관된 계정이 그 주소를 쥐고 있으면 새로 만들 수 없는데,
    500이나 '이미 등록된 이메일'만 보여 주면 사용자는 목록에 없는 계정 때문에 막힌
    이유를 알 방법이 없다."""
    target = make_user("recycled@goodmit.co.kr")
    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    r = client.post(
        "/api/admin/users",
        json={"email": "recycled@goodmit.co.kr", "display_name": "다시 온 사람", "role": "user"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409, r.text
    err = r.json()["error"]
    assert err["code"] == "archived_email_conflict"
    assert "보관된 계정" in err["message"]
    assert "복구" in err["message"]
    # UI가 '복구하시겠습니까?'를 실제 동작으로 이어 주려면 그 계정을 가리킬 수 있어야 한다.
    assert err["details"]["archived_user_id"] == target.id


def test_live_email_conflict_message_unchanged(client, admin_csrf, make_user):
    """살아 있는 계정과의 충돌은 기존 그대로 — 보관 안내로 헷갈리게 하지 않는다."""
    make_user("living@goodmit.co.kr")
    r = client.post(
        "/api/admin/users",
        json={"email": "living@goodmit.co.kr", "display_name": "중복", "role": "user"},
        headers=_headers(admin_csrf),
    )
    assert r.status_code == 409
    assert r.json()["error"]["code"] == "conflict"


def test_archive_is_idempotent(client, admin_csrf, make_user):
    target = make_user("twice@goodmit.co.kr")
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200
    assert client.post(
        f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf)
    ).status_code == 200


def test_archived_user_owned_schedules_are_disabled(client, admin_csrf, make_user, db):
    """비활성화와 같은 이유다(§11.5) — 보관한 사람의 스케줄이 계속 돌면 안 된다."""
    from app.schedules.models import Schedule

    target = make_user("owner@goodmit.co.kr")
    schedule = Schedule(
        name="보관자의 스케줄", schedule_type="cron", cron_expression="0 9 * * 1",
        timezone="Asia/Seoul", target_type="workflow", target_ref="wf-1",
        owner_user_id=target.id, enabled=True,
    )
    db.add(schedule)
    db.commit()

    client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(admin_csrf))

    db.expire_all()
    assert db.get(Schedule, schedule.id).enabled is False
