"""PA-RC-0024 — GET /api/admin/audit/{id}(신규 단건 조회)가 목록과 같은 경계를 지킨다.

관리자 콘솔에 /audit/:id 딥링크를 추가하려면 감사 로그 단건 조회 엔드포인트가 먼저
있어야 했다(목록만 있었다) — 그 엔드포인트를 새로 만들면서 목록이 이미 지키는 두 경계를
그대로 물려받는지 확인한다: (1) 역할 게이트(SENSITIVE_READ_ROLES) (2) 행위자 기준 범위
(scope_clause) — 범위 밖 id는 존재 자체를 노출하지 않도록 없는 id와 같은 404여야 한다.
"""

from __future__ import annotations

import pytest

pytestmark = pytest.mark.security


@pytest.fixture()
def world(db, make_user):
    """부서 둘 + 각 팀 사람 + 우리 팀만 관리하는 관리자 + 양쪽 팀의 감사 로그 한 건씩."""
    from app.audit.models import AuditLog
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    mate = make_user("detail-mate@goodmit.co.kr", role="user", display_name="우리팀사람")
    victim = make_user("detail-victim@goodmit.co.kr", role="user", display_name="남의팀사람")
    boss = make_user("detail-boss@goodmit.co.kr", role="admin", display_name="팀관리자")
    plain = make_user("detail-plain@goodmit.co.kr", role="user", display_name="일반사용자")
    mate.department_id = mine.id
    victim.department_id = theirs.id
    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    db.commit()

    mine_log = AuditLog(user_id=mate.id, action="auth.login", object_type="session",
                        object_id="s-mine", result="success")
    theirs_log = AuditLog(user_id=victim.id, action="auth.login", object_type="session",
                          object_id="s-theirs", result="success")
    db.add_all([mine_log, theirs_log])
    db.commit()

    return {
        "mine_log_id": mine_log.id, "theirs_log_id": theirs_log.id,
        "mate_email": "detail-mate@goodmit.co.kr", "plain_email": "detail-plain@goodmit.co.kr",
    }


def _boss(login_as):
    return {"X-CSRF-Token": login_as("admin", email="detail-boss@goodmit.co.kr")}


def test_scoped_admin_can_open_their_own_scope_log(client, login_as, world):
    r = client.get("/api/admin/audit/" + world["mine_log_id"], headers=_boss(login_as))
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["id"] == world["mine_log_id"]
    assert body["actor_email"] == world["mate_email"]


def test_scoped_admin_cannot_open_another_teams_log_and_it_404s_not_403(client, login_as, world):
    """범위 밖은 403(권한 없음)이 아니라 404(없는 것과 동일)여야 한다 — 그 id가 실제로
    존재한다는 사실 자체가 범위 밖 관리자에게 노출되면 안 된다(users/departments의
    get_scoped_user_or_404·get_or_404와 같은 원칙)."""
    r = client.get("/api/admin/audit/" + world["theirs_log_id"], headers=_boss(login_as))
    assert r.status_code == 404, (
        f"범위 밖 id가 404가 아니다(status={r.status_code}) — 존재 여부가 새고 있다: {r.text}"
    )
    # 값 자체도 응답에 없어야 한다(제출값 미노출 원칙과 같은 방향 — 404 몸통에 실제 데이터가
    # 실려 있으면 상태 코드만 바꾼 반쪽짜리 차단이다).
    assert world.get("theirs_log_id", "") not in r.text or "detail-victim" not in r.text


def test_unknown_id_also_404s_with_the_same_shape(client, login_as, world):
    """존재하지 않는 id와 범위 밖 id가 같은 응답 모양이어야, 응답만 보고 둘을 구분해
    "그 id는 존재하는구나(범위 문제일 뿐)"를 추론할 수 없다."""
    known_scope = client.get("/api/admin/audit/" + world["theirs_log_id"], headers=_boss(login_as))
    unknown = client.get("/api/admin/audit/00000000-0000-0000-0000-000000000000", headers=_boss(login_as))
    assert known_scope.status_code == unknown.status_code == 404
    assert set(known_scope.json()["error"].keys()) == set(unknown.json()["error"].keys())


def test_role_without_sensitive_read_gets_403(client, login_as, world):
    """SENSITIVE_READ_ROLES(admin/system_admin/auditor) 밖의 role은 라우터 게이트에서부터
    막힌다 — 목록(GET /api/admin/audit)과 같은 라우터 의존성을 그대로 물려받는지 확인."""
    headers = {"X-CSRF-Token": login_as("user", email=world["plain_email"])}
    r = client.get("/api/admin/audit/" + world["mine_log_id"], headers=headers)
    assert r.status_code == 403, f"user 역할이 감사 로그 단건 조회에 접근할 수 있다: {r.text}"


def test_global_admin_sees_both(client, login_as, world):
    """전역 관리자는 범위 제한이 없다 — 이 시험이 헛것이 되지 않도록, 범위가 실제로
    걸려 있는지(위 테스트들)와 대조되는 통제군을 남긴다."""
    headers = {"X-CSRF-Token": login_as("system_admin")}
    r1 = client.get("/api/admin/audit/" + world["mine_log_id"], headers=headers)
    r2 = client.get("/api/admin/audit/" + world["theirs_log_id"], headers=headers)
    assert r1.status_code == 200
    assert r2.status_code == 200


def test_detail_shape_matches_a_list_item(client, login_as, world):
    """단건 조회와 목록의 한 항목이 같은 필드 집합을 준다 — 딥링크로 연 상세와 행 클릭으로
    연 상세가 화면에서 다르게 다뤄질 이유가 없어야 한다(_serialize_row 공용화의 목적)."""
    headers = _boss(login_as)
    detail = client.get("/api/admin/audit/" + world["mine_log_id"], headers=headers).json()
    listing = client.get("/api/admin/audit", headers=headers).json()
    list_item = next(i for i in listing["items"] if i["id"] == world["mine_log_id"])
    assert set(detail.keys()) == set(list_item.keys())
    assert detail == list_item
