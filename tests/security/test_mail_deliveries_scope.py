"""메일 발송 기록은 받는 사람의 범위로만 보인다 (D-547).

## 무엇이 뚫려 있었나

발송 기록 목록과 상세는 콘솔 읽기 역할만 봤다. 부서 범위 관리자 · 운영자 · 감사자가 다른 부서 · 다른 조직 사람의
받는 주소, 티켓 제목, 알림 본문(상세의 params)을 읽었다.

## 이 파일이 못박는 것

- 부서 범위 관리자는 자기 부서 사람이 받은 메일만 본다 - 목록 · 건수 · 검색 · 최근 실패 · 상세가 모두 같다.
- 운영자 · 감사자는 자기 조직 사람의 메일만 본다. 조직이 없는 운영자는 아무것도 못 본다.
- 받는 사람이 계정이 아닌 메일은 전역 관리 범위만 본다.
- 범위 밖 상세는 없는 메일과 같은 404 다. 상세에는 params 가 없다.
반례: 전역 관리자와 시스템 관리자는 전부 본다.
"""

from __future__ import annotations

import pytest

from app.org.constants import DEFAULT_ORG_ID
from app.org.models import Department, Organization
from tests.integration.test_password_reset import configure_smtp

pytestmark = pytest.mark.security

PASSWORD = "Str0ng-Passw0rd!"
D_A = "dept-mail-a"
D_B = "dept-mail-b"


@pytest.fixture()
def world(db, make_user, app):
    """부서 A · B(같은 조직), 다른 조직 하나, 받는 사람 셋과 계정 아닌 주소 하나에게 간 메일."""
    from app.mail.service import queue_mail

    other_org = Organization(slug="mail-scope-tenant", name="다른 회사", status="active")
    db.add(other_org)
    db.add(Department(id=D_A, name="메일 부서 A", org_id=DEFAULT_ORG_ID, parent_id=None))
    db.add(Department(id=D_B, name="메일 부서 B", org_id=DEFAULT_ORG_ID, parent_id=None))
    db.commit()

    def person(email, *, dept=None, org=DEFAULT_ORG_ID, role="user", scope="global", scope_dept=None, membership=None):
        user = make_user(email=email, role=role, password=PASSWORD, display_name=email.split("@")[0])
        user.org_id = org
        user.department_id = dept
        if membership:
            user.membership_kind = membership
        elif dept:
            user.membership_kind = "department"
        user.admin_scope = scope
        user.scope_dept_id = scope_dept
        user.scope_org_id = org if scope != "global" else None
        db.add(user)
        db.commit()
        return user

    a = person("mail-a@goodmit.co.kr", dept=D_A)
    b = person("mail-b@goodmit.co.kr", dept=D_B)
    c = person("mail-c@tenant.example", org=other_org.id)
    actors = {
        "dept_admin": person("scope-da@goodmit.co.kr", dept=D_A, role="admin", scope="dept", scope_dept=D_A).email,
        "operator": person("scope-op@goodmit.co.kr", role="operator").email,
        "auditor": person("scope-au@goodmit.co.kr", role="auditor").email,
        "orgless_operator": person("scope-op2@goodmit.co.kr", role="operator", org=None, membership="unassigned").email,
        "global_admin": person("scope-ga@goodmit.co.kr", role="admin").email,
        "system_admin": person("scope-sa@goodmit.co.kr", role="system_admin").email,
    }
    configure_smtp(app)
    rows = {}
    with app.state.session_factory() as s:
        for key, user, email in (("a", a.id, a.email), ("b", b.id, b.email), ("c", c.id, c.email),
                                 ("stranger", None, "stranger@example.com")):
            row = queue_mail(
                s, kind="notification", to_email=email, recipient_user_id=user,
                subject=f"티켓 ABC-{key} 제목 비밀", params={"title": f"본문 {key} 비밀", "user_id": user},
                now=app.state.clock.now(),
            )
            row.status = "failed"
            row.last_error = "SMTPAuthenticationError: 535"
            rows[key] = row.id
        s.commit()
    return {"actors": actors, "rows": rows}


def _login(client, email):
    r = client.post("/login", json={"email": email, "password": PASSWORD})
    assert r.status_code == 200, r.text
    return {"X-CSRF-Token": r.json()["csrf_token"]}


def _visible(client, h, **params):
    body = client.get("/api/admin/mail/deliveries", params={"page_size": 100, **params}, headers=h).json()
    return {i["id"] for i in body["items"]}, body["total"]


EXPECTED = {
    "dept_admin": {"a"},
    "operator": {"a", "b"},
    "auditor": {"a", "b"},
    "orgless_operator": set(),
    "global_admin": {"a", "b", "c", "stranger"},
    "system_admin": {"a", "b", "c", "stranger"},
}


@pytest.mark.parametrize("actor", sorted(EXPECTED))
def test_each_role_sees_only_mail_to_people_in_its_scope(client, world, actor):
    rows = world["rows"]
    h = _login(client, world["actors"][actor])
    want = {rows[k] for k in EXPECTED[actor]}
    ids, total = _visible(client, h)
    assert ids == want and total == len(want), f"{actor}: 범위 밖 메일이 보이거나 범위 안 메일이 빠졌다"
    # 검색어로 범위 밖 메일의 존재를 셀 수 없다.
    ids, total = _visible(client, h, q="mail-b@")
    assert total == (1 if "b" in EXPECTED[actor] else 0)
    # 최근 실패도 같은 범위다.
    status = client.get("/api/admin/mail/status", headers=h).json()
    assert {i["id"] for i in status["recent_failures"]} == want
    for key, row_id in rows.items():
        r = client.get(f"/api/admin/mail/deliveries/{row_id}", headers=h)
        if key in EXPECTED[actor]:
            assert r.status_code == 200, r.text
            assert "params" not in r.json()["delivery"], "상세가 params(알림 본문 등)를 싣는다"
        else:
            assert r.status_code == 404, f"{actor} 가 범위 밖 메일({key}) 상세를 읽었다"
            assert "비밀" not in r.text
