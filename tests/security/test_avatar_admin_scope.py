"""프로필 사진 서빙의 범위는 **목록이 쓰는 범위 함수와 같다** (D-556, 음성 포함).

관리자는 사용자 관리 · 조직 관리 목록에서 보는 사람의 얼굴을 받아야 한다(보관 · 비활성 · 다른 조직도
전역 관리자의 목록에는 있다). 그러나 **목록에 없는 사람은 사진도 없다** — 부서 범위 관리자가 범위 밖
사람의 보관된 사진을 id 로 긁을 수 있으면 목록에서 가린 것이 URL 로 뚫린 것이다.

이 파일도 `test_avatar_org_scope.py` 처럼 같은 URL 이 조건 하나만 다를 때 200 이었음을 먼저 확인한다.
"""

from __future__ import annotations

import pytest

from tests.fakes.images import png_bytes

pytestmark = pytest.mark.security

pytest.importorskip("PIL", reason="Pillow 가 없으면 아바타 업로드 경로 자체가 없다")
PNG_BYTES = png_bytes()


def _upload_avatar_as(client, login_as, email: str) -> str:
    csrf = login_as("user", email=email)
    r = client.post("/api/me/avatar", files={"file": ("me.png", PNG_BYTES, "image/png")},
                    headers={"X-CSRF-Token": csrf})
    assert r.status_code == 200, r.text
    url = r.json()["avatar_url"]
    assert client.get(url).status_code == 200, "올린 본인도 자기 사진을 못 받는다"
    return url


def _archive(db, user) -> None:
    from app.core.models_base import utcnow

    user.archived_at = utcnow()
    db.commit()


def test_global_admin_sees_another_organizations_photo_because_the_user_list_does(client, login_as, two_orgs):
    """전역 관리자의 사용자 목록은 모든 조직을 담는다 — 그 얼굴도 받는다(양성)."""
    url = _upload_avatar_as(client, login_as, "orgb@goodmit.co.kr")
    login_as("admin")
    assert client.get(url).status_code == 200


def test_department_scoped_admin_cannot_fetch_an_archived_photo_outside_the_department(
    client, login_as, two_orgs, make_user, db,
):
    """부서 범위 관리자 — 자기 부서의 보관 사용자 사진은 200, 다른 부서의 보관 사용자 사진은 404(음성)."""
    from app.org.models import Department
    from app.users.service import get_user_by_email

    other = Department(name="다른팀", org_id=two_orgs.org_a_id)
    db.add(other)
    db.flush()
    inside = make_user("inside@goodmit.co.kr", role="user", display_name="안사람")
    outside = make_user("outside@goodmit.co.kr", role="user", display_name="밖사람")
    inside.org_id = two_orgs.org_a_id
    inside.department_id = two_orgs.dept_a.id
    outside.org_id = two_orgs.org_a_id
    outside.department_id = other.id
    db.commit()

    url_inside = _upload_avatar_as(client, login_as, "inside@goodmit.co.kr")
    url_outside = _upload_avatar_as(client, login_as, "outside@goodmit.co.kr")
    _archive(db, inside)
    _archive(db, outside)

    boss = make_user("deptboss@goodmit.co.kr", role="admin", display_name="팀장")
    boss.org_id = two_orgs.org_a_id
    boss.department_id = two_orgs.dept_a.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = two_orgs.dept_a.id
    db.commit()
    login_as("admin", email="deptboss@goodmit.co.kr")

    with client.app.state.session_factory() as s:
        assert get_user_by_email(s, "inside@goodmit.co.kr").archived_at is not None, "보관이 안 됐으면 아래 판정은 무의미하다"

    assert client.get(url_inside).status_code == 200, "자기 부서의 보관 사용자는 목록에 있는데 얼굴만 404 다"
    r = client.get(url_outside)
    assert r.status_code == 404, f"범위 밖 보관 사용자의 사진이 id 로 나간다({r.status_code})"
    assert r.content != PNG_BYTES


def test_plain_user_rules_are_unchanged(client, login_as, two_orgs, make_user, db):
    """일반 사용자의 관리 범위는 없다 — 다른 조직 404 · 같은 조직 다른 팀 200 그대로."""
    url_b = _upload_avatar_as(client, login_as, "orgb@goodmit.co.kr")
    url_a = _upload_avatar_as(client, login_as, "orga@goodmit.co.kr")

    mate = make_user("mate@goodmit.co.kr", role="user", display_name="동료")
    mate.org_id = two_orgs.org_a_id
    db.commit()
    login_as("user", email="mate@goodmit.co.kr")
    assert client.get(url_a).status_code == 200
    assert client.get(url_b).status_code == 404
