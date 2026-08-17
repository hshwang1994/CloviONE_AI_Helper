"""승인 **결재**에도 범위가 있다 (§0-A 1순위).

목록(`GET /api/admin/approvals`)만 `visible_user_ids` 로 좁혀 놨고, 단건 GET·approve·
reject·cancel 은 `get_approval_or_404` 만 부르고 범위 판정이 **전혀 없었다.**

여기서 새는 것은 읽기 유출이 아니라 **권한 부여 실행**이다. 부서 범위 관리자가 남의 팀
사람이 올린 `user.role_change` 요청을 승인 id 하나로 결재해 **그 팀 사람을 admin 으로
만들어 버릴 수 있다.** 목록에서 가려 놓은 것이 id 하나로 뚫리는 전형적인 IDOR 인데,
결과가 되돌리기 어려운 쪽(권한 상승)이라 가장 나쁜 부류다.

범위 밖은 **404** — 403 은 그 승인이 존재한다는 사실을 알려 준다(승인 id 를 찍어 보며
403/404 를 세면 다른 팀의 승인 큐 존재를 열거할 수 있다).

그리고 **위임을 깨뜨리면 안 된다.** 위임받은 운영자는 CONSOLE_WRITE_ROLES 가 아니지만
결재할 수 있어야 한다 — 범위 판정을 넣다가 그 길이 막히면 위임 기능이 조용히 죽는다.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

import pytest

pytestmark = pytest.mark.security


@dataclass(frozen=True)
class World:
    boss_email: str
    mate_id: str
    delegate_email: str
    delegate_id: str
    promotee_id: str
    victim_id: str
    inside_id: str
    outside_id: str


@pytest.fixture()
def world(db, make_user, fake_clock) -> World:
    """부서 둘 + 우리 팀만 관리하는 관리자 + 각 팀에서 올라온 역할 변경 요청 하나씩."""
    from app.approvals.service import create_approval
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import Department

    mine = Department(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = Department(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.commit()

    boss = make_user("ap-boss@goodmit.co.kr", role="admin", display_name="우리팀관리자")
    mate = make_user("ap-mate@goodmit.co.kr", role="admin", display_name="우리팀동료")
    outsider = make_user("ap-outsider@goodmit.co.kr", role="admin", display_name="남의팀관리자")
    promotee = make_user("ap-promotee@goodmit.co.kr", role="user", display_name="우리팀사원")
    victim = make_user("ap-victim@goodmit.co.kr", role="user", display_name="남의팀사원")
    # 위임받을 운영자. 부서는 우리 팀이지만 admin_scope 는 기본값(global)이다 — 위임은
    # 범위가 아니라 권한을 빌려주는 것이므로 이 사람은 좁혀지지 않아야 한다.
    stand_in = make_user("ap-standin@goodmit.co.kr", role="operator", display_name="대리결재자")

    boss.department_id = mine.id
    boss.admin_scope = "dept"
    boss.scope_dept_id = mine.id
    mate.department_id = mine.id
    promotee.department_id = mine.id
    stand_in.department_id = mine.id
    outsider.department_id = theirs.id
    victim.department_id = theirs.id
    db.commit()

    now = fake_clock.now()
    inside = create_approval(
        db, request_type="user.role_change", object_type="user",
        object_id=promotee.id, requested_by=mate, payload={"role": "operator"}, now=now,
    )
    outside = create_approval(
        db, request_type="user.role_change", object_type="user",
        object_id=victim.id, requested_by=outsider, payload={"role": "admin"}, now=now,
    )
    db.commit()

    return World(
        boss_email="ap-boss@goodmit.co.kr",
        mate_id=mate.id,
        delegate_email="ap-standin@goodmit.co.kr",
        delegate_id=stand_in.id,
        promotee_id=promotee.id,
        victim_id=victim.id,
        inside_id=inside.id,
        outside_id=outside.id,
    )


def _boss(login_as, world: World) -> dict:
    return {"X-CSRF-Token": login_as("admin", email=world.boss_email)}


def _status_of(db, approval_id: str) -> str:
    from app.approvals.models import Approval

    db.expire_all()
    return db.get(Approval, approval_id).status


def _role_of(db, user_id: str) -> str:
    from app.users.models import User

    db.expire_all()
    return db.get(User, user_id).role


def test_a_scoped_admin_cannot_approve_an_out_of_scope_request(client, login_as, db, world):
    """가장 나쁜 경우 — 남의 팀 사람을 admin 으로 올리는 요청을 승인해 버린다."""
    r = client.post(
        f"/api/admin/approvals/{world.outside_id}/approve", headers=_boss(login_as, world)
    )
    assert r.status_code == 404, f"범위 밖 승인을 결재할 수 있다: {r.status_code} {r.text}"
    # 404 를 돌려주면서 실제로는 실행됐을 수도 있다 — 상태를 직접 확인한다.
    assert _status_of(db, world.outside_id) == "pending", "404 인데 요청이 처리돼 버렸다"
    assert _role_of(db, world.victim_id) == "user", "남의 팀 사람의 역할이 올라갔다"


def test_a_scoped_admin_cannot_reject_an_out_of_scope_request(client, login_as, db, world):
    """거절도 결재다 — 남의 팀 인사 결정을 대신 죽일 수 있으면 안 된다."""
    r = client.post(
        f"/api/admin/approvals/{world.outside_id}/reject", headers=_boss(login_as, world)
    )
    assert r.status_code == 404, f"범위 밖 승인을 거절할 수 있다: {r.status_code} {r.text}"
    assert _status_of(db, world.outside_id) == "pending", "404 인데 요청이 거절돼 버렸다"


def test_a_scoped_admin_cannot_cancel_an_out_of_scope_request(client, login_as, db, world):
    """취소도 같은 판정을 지나야 한다 — 한 경로만 빠뜨리면 그 경로로 새 나간다."""
    r = client.post(
        f"/api/admin/approvals/{world.outside_id}/cancel", headers=_boss(login_as, world)
    )
    assert r.status_code == 404, f"범위 밖 승인을 취소할 수 있다: {r.status_code} {r.text}"
    assert _status_of(db, world.outside_id) == "pending", "404 인데 요청이 취소돼 버렸다"


def test_a_scoped_admin_cannot_read_an_out_of_scope_request(client, login_as, world):
    """단건 GET 도 목록과 같은 답을 해야 한다.

    승인 payload 에는 **누구를 무슨 역할로 바꾸려 하는가**가 그대로 적혀 있다.
    목록에서 가려 놓고 상세를 열어 두면 가린 의미가 없다.
    """
    r = client.get(f"/api/admin/approvals/{world.outside_id}", headers=_boss(login_as, world))
    assert r.status_code == 404, f"범위 밖 승인 상세가 열린다: {r.status_code} {r.text}"


def test_a_scoped_admin_still_decides_their_own_teams_request(client, login_as, db, world):
    """오탐 방지 — 자기 범위 요청까지 막히면 그건 승인 기능이 고장난 것이다."""
    headers = _boss(login_as, world)

    detail = client.get(f"/api/admin/approvals/{world.inside_id}", headers=headers)
    assert detail.status_code == 200, f"자기 팀 승인 상세를 못 본다: {detail.text}"

    r = client.post(f"/api/admin/approvals/{world.inside_id}/approve", headers=headers)
    assert r.status_code == 200, f"자기 팀 승인을 결재할 수 없다: {r.status_code} {r.text}"
    assert r.json()["approval"]["status"] == "approved"
    assert _role_of(db, world.promotee_id) == "operator", "승인했는데 실제로 적용되지 않았다"


def test_a_delegate_can_still_decide(client, login_as, db, world, fake_clock):
    """회귀 방지 — 위임받은 운영자는 CONSOLE_WRITE_ROLES 가 아니지만 결재할 수 있어야 한다.

    범위 판정을 잘못 끼워 넣으면(예: 결재자를 부서로 좁히면) 위임이 조용히 죽는다.
    """
    from app.approvals import delegation
    from app.users.models import User

    now = fake_clock.now()
    delegator = db.get(User, world.mate_id)
    delegate = db.get(User, world.delegate_id)
    delegation.create(
        db, delegator=delegator, delegate=delegate,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason="휴가", created_by=delegator.id, now=now,
    )
    db.commit()

    headers = {"X-CSRF-Token": login_as("operator", email=world.delegate_email)}
    r = client.post(f"/api/admin/approvals/{world.outside_id}/approve", headers=headers)
    assert r.status_code == 200, f"위임받은 사람이 결재할 수 없다: {r.status_code} {r.text}"
    assert r.json()["approval"]["decided_on_behalf_of"] == world.mate_id
    assert _role_of(db, world.victim_id) == "admin", "승인했는데 실제로 적용되지 않았다"


def test_a_delegate_sees_can_decide_before_deciding(client, login_as, db, world, fake_clock):
    """FN-11 — 위임받은 사람이 결재하기 전에, 프런트가 승인/거절 버튼을 켤 근거(can_decide)를
    API가 줘야 한다. 위임 없이는 결재 자체가 안 되므로(test_a_delegate_can_still_decide) 이건
    별개 시험이다 — '결재할 수 있다'와 '결재할 수 있다는 사실을 목록/상세가 미리 알려준다'는
    다른 주장이고, 후자가 빠지면 버튼 자체가 영원히 안 뜬다."""
    from app.approvals import delegation
    from app.users.models import User

    now = fake_clock.now()
    delegator = db.get(User, world.mate_id)
    delegate = db.get(User, world.delegate_id)
    delegation.create(
        db, delegator=delegator, delegate=delegate,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason="휴가", created_by=delegator.id, now=now,
    )
    db.commit()

    headers = {"X-CSRF-Token": login_as("operator", email=world.delegate_email)}
    detail = client.get(f"/api/admin/approvals/{world.outside_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["approval"]["can_decide"] is True

    listing = client.get("/api/admin/approvals?status=pending", headers=headers)
    assert listing.status_code == 200
    item = next(i for i in listing.json()["items"] if i["id"] == world.outside_id)
    assert item["can_decide"] is True


def test_a_non_delegate_operator_sees_can_decide_false(client, login_as, world, make_user):
    """오탐 방지 — 위임이 없으면(operator 역할만으로는) can_decide 가 여전히 False 여야 한다.
    이게 항상 True 로 새면 모든 operator 화면에 승인/거절 버튼이 뜨는 반대 방향 회귀가 된다."""
    make_user("ap-plain-operator@goodmit.co.kr", role="operator", display_name="평범한운영자")
    headers = {"X-CSRF-Token": login_as("operator", email="ap-plain-operator@goodmit.co.kr")}
    detail = client.get(f"/api/admin/approvals/{world.inside_id}", headers=headers)
    assert detail.status_code == 200
    assert detail.json()["approval"]["can_decide"] is False


def test_list_scope_is_requester_scope_not_a_personal_approver_assignment(client, login_as, world):
    """PA-RC-0038 acceptance (5) — `/approvals` 목록의 범위를 고정한다.

    `Approval.approver_id` 컬럼이 있어 "나에게 배정된 건만 목록에 뜬다"로 오해하기
    쉽지만, 그 컬럼은 `decide()`(approve/reject) 시점에만 채워지는 **결정 기록**이지
    (누가 결재했는가) 목록 쿼리는 그 컬럼을 필터로 쓰지 않는다(service.py의 list 쿼리는
    request_type·requested_by·status·apply_scope만 본다). 그래서 `boss`가 만들지도,
    결재하지도 않은 `mate`의 요청(같은 부서=범위 안)이 `boss`의 목록에 뜬다 — 목록은
    "나에게 배정된 것"이 아니라 "내 조회 범위 안에서 올라온 것" 전부를 돌려준다.
    """
    headers = _boss(login_as, world)
    listing = client.get("/api/admin/approvals?status=pending", headers=headers)
    assert listing.status_code == 200
    ids = [i["id"] for i in listing.json()["items"]]
    assert world.inside_id in ids, (
        "같은 범위(우리팀) 안, boss가 요청자도 결재자도 아닌 건이 목록에서 빠졌다 — "
        "목록이 '나에게 배정된 것'으로 좁혀졌다면 이게 실패한다"
    )
    # 범위 판정 자체는 위 test_a_scoped_admin_cannot_read_an_out_of_scope_request 등이
    # 이미 고정하고 있다 — 여기서 다시 outside_id가 빠지는지까지 검사하면 중복이다.


def test_no_role_can_be_told_apart_from_a_missing_approval(client, login_as, world):
    """범위 밖과 '없는 id' 는 **구별되지 않아야** 한다 — 구별되면 큐를 열거할 수 있다."""
    headers = _boss(login_as, world)
    hidden = client.get(f"/api/admin/approvals/{world.outside_id}", headers=headers)
    missing = client.get("/api/admin/approvals/does-not-exist-at-all", headers=headers)
    assert hidden.status_code == missing.status_code == 404

    def _shape(response) -> tuple[str, str]:
        # request_id 는 요청마다 다르다 — 코드와 문구만 비교한다.
        body = response.json()["error"]
        return body["code"], body["message"]

    assert _shape(hidden) == _shape(missing), (
        f"범위 밖과 없는 id 의 응답이 다르다: {hidden.text} vs {missing.text}"
    )
