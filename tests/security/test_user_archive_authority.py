"""보관/복구는 계정 수명주기 변경이다 — reset-password·disable과 똑같은 안전장치를
거쳐야 한다. 여기가 새면 일반 admin이 system_admin을 목록에서 치우고(=사실상 정지),
마지막 system_admin을 보관해 아무도 못 들어오는 상태를 만들 수 있다.
"""

import pytest

pytestmark = pytest.mark.security


def _headers(csrf):
    return {"X-CSRF-Token": csrf}


@pytest.fixture()
def sysadmin_target(make_user):
    return make_user("sa-archive-target@goodmit.co.kr", role="system_admin")


def test_admin_cannot_archive_system_admin(client, login_as, sysadmin_target):
    csrf = login_as("admin", email="attacker-arch@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/archive", headers=_headers(csrf)
    )
    assert r.status_code == 403, r.text


def test_admin_cannot_unarchive_system_admin(client, login_as, sysadmin_target, db):
    """복구도 같은 권한 경계다 — 보관된 system_admin을 되살리는 것도 그 계정을 만지는 일이다."""
    from app.core.models_base import utcnow

    sysadmin_target.archived_at = utcnow()
    db.commit()

    csrf = login_as("admin", email="attacker-unarch@goodmit.co.kr")
    r = client.post(
        f"/api/admin/users/{sysadmin_target.id}/unarchive", headers=_headers(csrf)
    )
    assert r.status_code == 403, r.text


def test_cannot_archive_self(client, login_as, db):
    """자기를 보관하면 그 순간 자기 세션이 끊기고, 자기를 되돌릴 사람이 화면 안에 없다."""
    from app.users.service import get_user_by_email

    csrf = login_as("admin", email="selfarchive@goodmit.co.kr")
    with client.app.state.session_factory() as session:
        me = get_user_by_email(session, "selfarchive@goodmit.co.kr")

    r = client.post(f"/api/admin/users/{me.id}/archive", headers=_headers(csrf))
    assert r.status_code in (400, 409), r.text
    assert "자기 자신" in r.json()["error"]["message"] or "본인" in r.json()["error"]["message"]


def test_cannot_archive_last_system_admin(db, settings, make_user, app):
    """마지막 system_admin을 보관하면 아무도 관리자 콘솔에 들어올 수 없다 — 비활성화를
    막는 것과 같은 이유로 막아야 한다(§32.8).

    이 규칙은 서비스 계층에서 검증한다. HTTP로는 도달할 수 없는 규칙이기 때문이다:
    마지막 남은 활성 system_admin을 보관하려면 그 사람이 로그인해 있어야 하는데(다른
    역할은 system_admin을 만질 수 없다), 그러면 대상이 곧 행위자라 '자기 자신 금지'에
    먼저 걸린다. 반면 CLI(§29)에는 '자기 자신'이 없어 이 규칙이 유일한 방어선이다.
    """
    from app.core.errors import ConflictError
    from app.users.service import archive_user

    only_admin = make_user("last-sa@goodmit.co.kr", role="system_admin")

    with pytest.raises(ConflictError):
        archive_user(
            db, only_admin,
            session_service=app.state.session_service,
            actor_role="system_admin",
            actor_id=None,  # CLI처럼 행위자가 없는 경로
        )

    db.expire_all()
    assert db.get(type(only_admin), only_admin.id).archived_at is None


def test_cli_cannot_archive_last_system_admin(db, make_user, settings, monkeypatch, capsys):
    """CLI가 같은 서비스를 쓰는지 실제로 확인한다 — 규칙이 라우터에만 있으면 CLI로 샌다."""
    from app.cli.user_cli import main

    make_user("cli-last-sa@goodmit.co.kr", role="system_admin")
    monkeypatch.setenv("DATABASE_URL", settings.database_url)

    code = main(["archive", "--email", "cli-last-sa@goodmit.co.kr"])
    assert code == 1, "CLI가 마지막 system_admin을 보관해 버렸다"
    assert "마지막 system_admin" in capsys.readouterr().err


def test_archive_requires_csrf(client, login_as, make_user):
    target = make_user("csrf-arch@goodmit.co.kr")
    login_as("admin", email="csrfadmin@goodmit.co.kr")
    r = client.post(f"/api/admin/users/{target.id}/archive")  # 헤더 없음
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


def test_unarchive_requires_csrf(client, login_as, make_user):
    target = make_user("csrf-unarch@goodmit.co.kr")
    login_as("admin", email="csrfadmin2@goodmit.co.kr")
    r = client.post(f"/api/admin/users/{target.id}/unarchive")
    assert r.status_code == 403
    assert r.json()["error"]["code"] == "csrf_failed"


@pytest.mark.parametrize("role", ["user", "operator", "auditor"])
def test_non_admin_cannot_archive(client, login_as, make_user, role):
    target = make_user("victim-arch@goodmit.co.kr")
    csrf = login_as(role, email=f"{role}-arch@goodmit.co.kr")
    r = client.post(f"/api/admin/users/{target.id}/archive", headers=_headers(csrf))
    assert r.status_code == 403


def test_archived_system_admin_does_not_count_as_active(client, login_as, make_user, db):
    """보관된 system_admin은 '아직 한 명 있다'로 세어지면 안 된다 — 세어지면 마지막
    관리자를 비활성화하는 문이 열린다."""
    from app.users.service import count_active_system_admins

    csrf = login_as("system_admin", email="counter@goodmit.co.kr")
    spare = make_user("spare-sa@goodmit.co.kr", role="system_admin")

    with client.app.state.session_factory() as session:
        assert count_active_system_admins(session) >= 2

    client.post(f"/api/admin/users/{spare.id}/archive", headers=_headers(csrf))

    with client.app.state.session_factory() as session:
        ids = [u.id for u in session.query(type(spare)).filter_by(role="system_admin").all()]
        assert spare.id in ids, "행은 DB에 남아 있어야 한다(감사 추적)"
        assert count_active_system_admins(session) == 1, "보관된 계정이 활성으로 세어졌다"
