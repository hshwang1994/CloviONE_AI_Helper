"""개인 결재함 `GET /api/approvals/mine` (0060 §16).

## 왜 이 화면이 생겼는가

승인은 관리자 화면(`/api/admin/approvals`)에만 있었다. 그런데 결재 자체는 역할이 아니라
**위임**으로도 생긴다 — 관리 콘솔을 열 수 없는 사람이 결재자가 될 수 있다. 그 사람에게는
"당신에게 결재할 건이 있다" 를 보여 줄 자리가 아예 없었다.

## 이 파일이 못박는 것

  * **역할 게이트가 없다.** 일반 사용자가 200 을 받아야 한다. 403 이면 위임받은 사람이
    자기 결재함을 못 연다.
  * **세 칸이 서로 다른 것을 센다.** 처리할 것 / 내가 올린 것 / 내가 처리한 것.
  * **권한 없음과 할 일 없음을 구별한다.** 둘 다 빈 목록이지만 화면이 다른 문장을 써야 하고,
    그러려면 응답에 `can_decide` 가 있어야 한다.
  * **자기 요청은 자기 할 일 칸에 없다.** 눌러 봐야 거절당하는 줄이다.

⚠️ 이 파일이 없는 동안 실제로 **500** 이 나갔다: 정렬을 `Approval.created_at` 으로 걸었는데
그 표에는 그 열이 없다(`requested_at` 이다). 화면·배지 양쪽이 이 경로를 부르므로 로그인
직후 모든 사용자에게 오류가 났고, 어떤 시험도 이 경로를 부르지 않아 초록이었다.
"""

from __future__ import annotations

from datetime import datetime, timedelta

import pytest

from app.approvals.models import APPROVAL_PENDING, Approval

pytestmark = pytest.mark.integration

NOW = datetime(2026, 8, 5, 9, 0, 0)


_SEQ = iter(range(1, 1000))


def _mk(db, *, requested_by, approver_id=None, status=APPROVAL_PENDING, kind="user.role_change",
        expires_at=None):
    """승인 한 건.

    `object_id` 를 매번 다르게 준다 — pending 중복 방지 인덱스가
    `(request_type, object_id, request_payload_json)` 유일이라, 같은 값으로 두 건을 심으면
    표본을 만들다가 IntegrityError 로 죽는다(제품의 정상 동작이다).
    """
    row = Approval(
        request_type=kind,
        object_type="user",
        object_id=f"obj-{next(_SEQ)}",
        status=status,
        requested_by=requested_by,
        approver_id=approver_id,
        requested_at=NOW,
        expires_at=expires_at,
    )
    db.add(row)
    db.flush()
    return row


@pytest.fixture()
def world(db, make_user):
    asker = make_user("ma-asker@goodmit.co.kr", role="user", display_name="요청자")
    boss = make_user("ma-boss@goodmit.co.kr", role="admin", display_name="결재자")
    db.commit()
    return {"asker": asker, "boss": boss}


def _mine(client, box=None):
    r = client.get("/api/approvals/mine", params={"box": box} if box else None)
    assert r.status_code == 200, r.text
    return r.json()


def test_a_plain_user_can_open_their_own_inbox(client, login_as, world):
    """역할 게이트가 없어야 한다 — 위임받은 사람은 관리 콘솔을 못 연다."""
    login_as("user", email="ma-asker@goodmit.co.kr")
    body = _mine(client)
    assert body["can_decide"] is False
    assert body["items"] == []


def test_the_requested_box_holds_what_i_asked_for(client, login_as, db, world):
    _mk(db, requested_by=world["asker"].id)
    db.commit()

    login_as("user", email="ma-asker@goodmit.co.kr")
    assert _mine(client, "requested")["total"] == 1
    # 남이 올린 건은 내 '올린 것' 칸에 없다.
    login_as("admin", email="ma-boss@goodmit.co.kr")
    assert _mine(client, "requested")["total"] == 0


def test_the_todo_box_holds_what_i_can_decide(client, login_as, db, world):
    """결재 권한이 있는 사람의 할 일 칸 — 자기 요청은 빠진다."""
    _mk(db, requested_by=world["asker"].id)
    _mk(db, requested_by=world["boss"].id)   # 결재자가 스스로 올린 건
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    body = _mine(client, "todo")
    assert body["can_decide"] is True
    assert body["total"] == 1, (
        "자기 요청이 자기 할 일 칸에 들어갔다 — 눌러 봐야 거절당하는 줄이다"
    )


def test_the_done_box_holds_what_i_decided(client, login_as, db, world):
    _mk(db, requested_by=world["asker"].id, approver_id=world["boss"].id, status="approved")
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    assert _mine(client, "done")["total"] == 1
    login_as("user", email="ma-asker@goodmit.co.kr")
    assert _mine(client, "done")["total"] == 0


def test_paging_the_badge_query_does_not_explode(client, login_as, db, world):
    """배지는 `page_size=1` 로 총계만 묻는다 — 그 조합이 실제로 도는지 본다.

    이 한 줄이 없어서 정렬 열 오타(`created_at`, 없는 열)가 배포까지 갔다. 배지는 셸이
    부르므로 **로그인한 모든 사용자**가 500 을 봤다.
    """
    for _ in range(3):
        _mk(db, requested_by=world["asker"].id)
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    r = client.get("/api/approvals/mine", params={"box": "todo", "page_size": 1})
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["total"] == 3 and len(body["items"]) == 1


# ── 「목록에 있으면 결재된다」 (perm-01 · perm-02) ────────────────────────────
#
# 할 일 칸의 모든 줄에는 승인 버튼이 붙는다. 그러므로 그 칸은 **지금 실제로 결재할 수 있는
# 것만** 담아야 한다. 두 가지가 그 약속을 깨고 있었다.


def test_the_todo_box_leaves_out_rows_that_expired(client, login_as, db, world, fake_clock):
    """만료 시각이 지난 pending 은 결재할 수 없다 — 눌러 봐야 409 인 줄이다.

    관리 큐(`GET /api/admin/approvals?status=pending`)는 이미 그런 행을 빼고 있었다. 개인
    결재함만 저장된 status 를 보고 담아서, 씨앗 서버에서는 결재함 7건이 전부 만료였고
    사이드바 배지가 영원히 0 이 되지 않았다.
    """
    now = fake_clock.now()
    dead = _mk(db, requested_by=world["asker"].id, expires_at=now - timedelta(hours=1))
    alive = _mk(db, requested_by=world["asker"].id, expires_at=now + timedelta(hours=72))
    db.commit()

    login_as("admin", email="ma-boss@goodmit.co.kr")
    body = _mine(client, "todo")
    ids = [i["id"] for i in body["items"]]
    assert dead.id not in ids, "만료된 요청이 할 일 칸에 있다 — 누르면 409 다"
    assert alive.id in ids, "살아 있는 대기 건까지 사라졌다 — 필터가 너무 넓다"
    assert body["total"] == 1

    # 두 화면이 같은 「대기」를 말한다.
    console = client.get("/api/admin/approvals", params={"status": "pending"})
    assert console.status_code == 200, console.text
    assert [i["id"] for i in console.json()["items"]] == [alive.id]


@pytest.fixture()
def two_teams(db, make_user):
    """부서 둘 · 그중 한 부서만 관리하는 admin · 각 부서의 요청자 한 명씩."""
    from app.org.constants import DEFAULT_ORG_ID
    from app.org.models import OrgUnit
    from app.users.models import ADMIN_SCOPE_DEPT

    mine = OrgUnit(name="우리팀", org_id=DEFAULT_ORG_ID)
    theirs = OrgUnit(name="남의팀", org_id=DEFAULT_ORG_ID)
    db.add_all([mine, theirs])
    db.flush()

    boss = make_user("ma-scoped-boss@goodmit.co.kr", role="admin", display_name="우리팀관리자")
    boss.department_id = mine.id
    boss.admin_scope = ADMIN_SCOPE_DEPT
    boss.scope_dept_id = mine.id
    inside = make_user("ma-inside@goodmit.co.kr", role="user", display_name="우리팀사원")
    inside.department_id = mine.id
    outside = make_user("ma-outside@goodmit.co.kr", role="user", display_name="남의팀사원")
    outside.department_id = theirs.id
    db.commit()
    return {"boss": boss, "inside": inside, "outside": outside}


def test_a_scoped_admin_does_not_see_out_of_scope_requests_in_their_inbox(
    client, login_as, db, two_teams
):
    """관리 큐에서 가린 것이 개인 결재함으로 새면 가린 의미가 없다.

    승인 payload 에는 「누구를 무슨 역할로」가 그대로 적혀 있고, 목록에는 요청자 이름과 조직
    경로까지 실린다 — 인사 정보다. 게다가 결재 경로는 같은 범위를 다시 재서 404 를 주므로,
    부서 관리자의 결재함 절반이 누를 수 없는 줄이었다.
    """
    mine = _mk(db, requested_by=two_teams["inside"].id)
    theirs = _mk(db, requested_by=two_teams["outside"].id)
    db.commit()

    csrf = login_as("admin", email="ma-scoped-boss@goodmit.co.kr")
    ids = [i["id"] for i in _mine(client, "todo")["items"]]
    assert theirs.id not in ids, "범위 밖 요청이 부서 관리자의 결재함에 보인다"
    assert mine.id in ids, "자기 범위 요청까지 사라졌다 — 결재함이 죽는다"

    # 목록에 있는 줄은 실제로 결재된다.
    r = client.post(
        f"/api/admin/approvals/{mine.id}/reject", headers={"X-CSRF-Token": csrf}
    )
    assert r.status_code == 200, f"결재함에 보이는 건을 결재할 수 없다: {r.text}"


def test_a_delegate_still_sees_the_delegators_requests(
    client, login_as, db, two_teams, make_user, fake_clock
):
    """오탐 방지 — 위임은 정의상 **남의 범위**를 결재한다(D-385).

    범위를 결재자 본인 기준으로 재면 일반 사용자의 관리 범위는 빈 집합이라 위임받은 사람의
    결재함이 통째로 빈다. 범위는 **위임한 사람** 기준이어야 한다.
    """
    from app.approvals import delegation

    helper = make_user("ma-helper@goodmit.co.kr", role="user", display_name="위임받은사원")
    db.commit()
    now = fake_clock.now()
    delegation.create(
        db, delegator=two_teams["boss"], delegate=helper,
        starts_at=now - timedelta(hours=1), ends_at=now + timedelta(days=3),
        reason="휴가", created_by=two_teams["boss"].id, now=now, visible=None,
    )
    mine = _mk(db, requested_by=two_teams["inside"].id)
    theirs = _mk(db, requested_by=two_teams["outside"].id)
    db.commit()

    login_as("user", email="ma-helper@goodmit.co.kr")
    body = _mine(client, "todo")
    assert body["can_decide"] is True
    ids = [i["id"] for i in body["items"]]
    assert mine.id in ids, "위임받았는데 위임자 범위의 건이 결재함에 없다"
    assert theirs.id not in ids, "대리인이 위임자의 범위를 넘었다"


def test_the_list_is_ordered_newest_first(client, login_as, db, world):
    """id 가 UUID 라 정렬 열이 없으면 순서가 무작위다 — 최신이 위로 와야 한다."""
    old = _mk(db, requested_by=world["asker"].id)
    old.requested_at = datetime(2026, 1, 1, 0, 0, 0)
    new = _mk(db, requested_by=world["asker"].id)
    new.requested_at = datetime(2026, 8, 20, 0, 0, 0)
    db.commit()

    login_as("user", email="ma-asker@goodmit.co.kr")
    ids = [i["id"] for i in _mine(client, "requested")["items"]]
    assert ids == [new.id, old.id], f"최신 순이 아니다: {ids}"
